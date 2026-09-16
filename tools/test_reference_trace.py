#!/usr/bin/env python3
"""Self-tests for the external reference CommitRecord differential path."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from reference_trace import (
    ReferenceTraceError,
    build_adapter,
    compare_traces,
    find_reference_root,
    load_commits,
    run_adapter,
)


def record(pc: int, value: int, **updates: object) -> dict[str, object]:
    item: dict[str, object] = {
        "cycle": pc // 4 + 1, "lane": 0, "valid": True, "pc": pc,
        "inst": 0x13, "rd": 1, "rd_we": True, "value": value,
        "is_store": False, "store_addr": 0, "store_mask": 0,
        "store_data": 0, "halted": False, "return_value": 0,
    }
    item.update(updates)
    return item


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reference-trace-") as directory:
        root = Path(directory)
        reference = root / "reference.jsonl"
        rtl = root / "rtl.jsonl"
        records = [
            record(0, 7),
            record(4, 7, inst=0x0FF00513, rd=0, rd_we=False, halted=True,
                   return_value=7),
        ]
        write_jsonl(reference, records)
        # Cycle and lane placement may differ between scalar reference and wide RTL.
        rtl_records = [dict(records[0], cycle=20), dict(records[1], cycle=20, lane=1)]
        write_jsonl(rtl, rtl_records)
        summary = compare_traces(reference, rtl)
        if summary["records"] != 2:
            raise RuntimeError("matching traces were not accepted")

        rtl_records[0]["value"] = 8
        write_jsonl(rtl, rtl_records)
        try:
            compare_traces(reference, rtl)
        except ReferenceTraceError as exc:
            if "value" not in str(exc) or "retired instruction 0" not in str(exc):
                raise RuntimeError("mismatch diagnostic lost first-failure context") from exc
        else:
            raise RuntimeError("mismatched traces were accepted")

    # Header discovery is part of the degradation contract.  The checked-in
    # reference checkout is read but never modified.
    found = find_reference_root()
    image = found / "testcases" / "naive.data"
    if not image.is_file():
        image = found / "data" / "testcases" / "naive.data"
    with tempfile.TemporaryDirectory(prefix="reference-adapter-") as directory:
        root = Path(directory)
        executable = root / "reference_trace.exe"
        trace = root / "naive.jsonl"
        build_adapter(found, executable)
        run_adapter(executable, image, trace, 100_000)
        commits = load_commits(trace)
        if not commits[-1]["halted"] or commits[-1]["return_value"] != 94:
            raise RuntimeError("reference adapter did not preserve naive termination")
    print(f"PASS: reference trace compare, public API build, and naive run ({found})")


if __name__ == "__main__":
    main()
