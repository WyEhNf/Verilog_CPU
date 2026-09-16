#!/usr/bin/env python3
"""Build the read-only C++ reference adapter and compare CommitRecord traces."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


class ReferenceTraceError(RuntimeError):
    pass


COMPARE_FIELDS = (
    "pc", "inst", "rd", "rd_we", "value", "is_store", "store_addr",
    "store_mask", "store_data", "halted", "return_value",
)
BOOLEAN_FIELDS = {"valid", "rd_we", "is_store", "halted"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def reference_candidates(explicit: str | None = None) -> list[Path]:
    root = project_root()
    if explicit:
        return [Path(explicit).expanduser().resolve()]
    configured = os.environ.get("RISCV_REFERENCE_ROOT")
    if configured:
        return [Path(configured).expanduser().resolve()]
    candidates: list[Path] = [
        root / "RISC-V-CPU-Simulator",
        root.parent / "RISC-V-CPU-Simulator",
        root.parent / "CPU-Simu" / "newimpl",
    ]
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def find_reference_root(explicit: str | None = None) -> Path:
    checked = []
    for candidate in reference_candidates(explicit):
        checked.append(str(candidate))
        include = candidate / "include" / "sim"
        if (include / "simulator.h").is_file() and (include / "module_io.h").is_file():
            return candidate
    raise ReferenceTraceError(
        "reference public headers unavailable; checked: " + ", ".join(checked)
    )


def find_compiler(explicit: str | None = None) -> str:
    choices = [explicit, os.environ.get("CXX"), "g++", "clang++"]
    for choice in choices:
        if not choice:
            continue
        found = shutil.which(choice)
        if found:
            return found
    raise ReferenceTraceError("no C++20 compiler found (set CXX or pass --cxx)")


def build_adapter(reference_root: Path, output: Path, cxx: str | None = None) -> Path:
    compiler = find_compiler(cxx)
    source = project_root() / "tools" / "reference_trace.cpp"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-pedantic",
        "-I", str(reference_root / "include"), str(source), "-o", str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ReferenceTraceError(
            "reference adapter did not compile against the public API\n" + detail
        )
    return output


def run_adapter(executable: Path, image: Path, output: Path, max_cycles: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(executable), "--input", str(image), "--output", str(output),
         "--max-cycles", str(max_cycles)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ReferenceTraceError("reference trace generation failed\n" + detail)
    if not output.is_file() or output.stat().st_size == 0:
        raise ReferenceTraceError("reference adapter produced an empty trace")


def _integer(value: object, field: str, path: Path, line: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise ReferenceTraceError(
                f"{path}:{line}: field {field} is not an integer"
            ) from exc
    raise ReferenceTraceError(f"{path}:{line}: field {field} is not an integer")


def load_commits(path: Path) -> list[dict[str, int | bool]]:
    commits: list[dict[str, int | bool]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReferenceTraceError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not record.get("valid", False):
                continue
            missing = [field for field in COMPARE_FIELDS if field not in record]
            if missing:
                raise ReferenceTraceError(
                    f"{path}:{line_number}: missing fields: {', '.join(missing)}"
                )
            normalized: dict[str, int | bool] = {}
            for field in COMPARE_FIELDS:
                value = _integer(record[field], field, path, line_number)
                normalized[field] = bool(value) if field in BOOLEAN_FIELDS else value
            # CommitRecord store payload wires are don't-care for non-stores in
            # the RTL.  Canonicalize them rather than comparing stale ALU data.
            if not normalized["is_store"]:
                normalized["store_addr"] = 0
                normalized["store_mask"] = 0
                normalized["store_data"] = 0
            # rd/value are architectural only when writeback is enabled.  A
            # HALT record is the sole exception: value carries the return byte.
            if not normalized["rd_we"] and not normalized["halted"]:
                normalized["rd"] = 0
                normalized["value"] = 0
            if normalized["halted"]:
                normalized["value"] = int(normalized["value"]) & 0xFF
                normalized["return_value"] = int(normalized["return_value"]) & 0xFF
            normalized["cycle"] = _integer(record.get("cycle", 0), "cycle", path, line_number)
            normalized["lane"] = _integer(record.get("lane", 0), "lane", path, line_number)
            commits.append(normalized)
    if not commits:
        raise ReferenceTraceError(f"{path}: no valid CommitRecord entries")
    return commits


def compare_traces(reference_path: Path, rtl_path: Path, context: int = 2) -> dict[str, int]:
    reference = load_commits(reference_path)
    rtl = load_commits(rtl_path)
    common = min(len(reference), len(rtl))
    mismatch_index = None
    mismatched_fields: list[str] = []
    for index in range(common):
        mismatched_fields = [
            field for field in COMPARE_FIELDS
            if reference[index][field] != rtl[index][field]
        ]
        if mismatched_fields:
            mismatch_index = index
            break
    if mismatch_index is None and len(reference) != len(rtl):
        mismatch_index = common
        mismatched_fields = ["record_count"]
    if mismatch_index is not None:
        start = max(0, mismatch_index - context)
        stop = min(max(len(reference), len(rtl)), mismatch_index + context + 1)
        lines = [
            f"CommitRecord mismatch at retired instruction {mismatch_index}: "
            + ", ".join(mismatched_fields)
        ]
        for index in range(start, stop):
            marker = ">" if index == mismatch_index else " "
            lines.append(f"{marker} [{index}] reference={reference[index] if index < len(reference) else '<end>'}")
            lines.append(f"{marker} [{index}] rtl      ={rtl[index] if index < len(rtl) else '<end>'}")
        raise ReferenceTraceError("\n".join(lines))
    return {"records": len(reference), "reference_last_cycle": int(reference[-1]["cycle"]),
            "rtl_last_cycle": int(rtl[-1]["cycle"])}


def default_executable() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return project_root() / "build" / "reference_trace" / f"reference_trace{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", help="read-only RISC-V-CPU-Simulator root")
    parser.add_argument("--cxx", help="C++20 compiler")
    parser.add_argument("--executable", type=Path, default=default_executable())
    parser.add_argument("--build", action="store_true", help="build the C++ adapter")
    parser.add_argument("--image", type=Path, help="run the adapter for this .data image")
    parser.add_argument("--reference-trace", type=Path, help="reference JSONL output path")
    parser.add_argument("--rtl-trace", type=Path, help="RTL CommitRecord JSONL to compare")
    parser.add_argument("--max-cycles", type=int, default=200_000_000)
    parser.add_argument("--optional", action="store_true",
                        help="report unavailable reference API/compiler as a skip")
    args = parser.parse_args(argv)

    try:
        executable = args.executable.resolve()
        if args.build or args.image:
            reference_root = find_reference_root(args.reference_root)
            build_adapter(reference_root, executable, args.cxx)
            print(f"PASS: reference adapter built from read-only API at {reference_root}")
        if args.image:
            if args.reference_trace is None:
                raise ReferenceTraceError("--image requires --reference-trace")
            run_adapter(executable, args.image.resolve(), args.reference_trace.resolve(),
                        args.max_cycles)
            print(f"PASS: reference trace written to {args.reference_trace.resolve()}")
        if args.rtl_trace:
            if args.reference_trace is None:
                raise ReferenceTraceError("--rtl-trace requires --reference-trace")
            summary = compare_traces(args.reference_trace.resolve(), args.rtl_trace.resolve())
            print("PASS: CommitRecord differential records={records} "
                  "reference_cycles={reference_last_cycle} rtl_cycles={rtl_last_cycle}".format(**summary))
        if not (args.build or args.image or args.rtl_trace):
            parser.error("select --build, --image, or --rtl-trace")
        return 0
    except (OSError, ReferenceTraceError) as exc:
        if args.optional:
            print(f"SKIP: optional reference differential unavailable: {exc}")
            return 0
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
