#!/usr/bin/env python3
"""Separate course Verilator generation from bounded-concurrency C++ builds."""
import os
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
# Keep the verified loop/function limits; larger files reduce repeated compiler
# startup/PCH loading. Bound expression depth as well: file/function splitting
# cannot divide a single packed RAT recovery expression. Verilator 5.020's
# compiler depth pass materializes subexpressions in statement temporaries.
GENERATION_FLAGS = [
    "--unroll-count", "1024", "--unroll-stmts", "1000000",
    "--output-split", "8000", "--output-split-cfuncs", "2000",
    "--output-split-ctrace", "2000", "--comp-limit-parens", "32",
]


def executable(value):
    found = shutil.which(str(value))
    if not found:
        raise ValueError(f"executable not found: {value}")
    return os.path.abspath(found)


def select_backend():
    override = os.environ.get("CPU2026_REAL_VERILATOR")
    if override:
        return [executable(override)], False
    appdir = os.environ.get("CPU2026_APPDIR")
    if appdir:
        return [executable(Path(appdir) / "bin/verilator")], False
    image = os.environ.get("CPU2026_BUILD_APPIMAGE",
                           str(ROOT / "cpu2026-tools-x86_64.AppImage"))
    if image and Path(image).expanduser().is_file():
        # Re-enter exactly as the official toolchain selector does. AppRun
        # exports CPU2026_APPDIR, so the child selects the bundled executable.
        return [executable(Path(image).expanduser()), "exec", sys.executable,
                str(Path(__file__).resolve())], True
    return [executable("verilator")], False


def build_plan(arguments):
    """Keep RTL/driver arguments; move only the host make phase out of Verilator."""
    generation = []
    make_flags = []
    directory = None
    module = None
    prefix = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--build":
            index += 1
            continue
        if argument in ("--Mdir", "--top-module", "--prefix", "-MAKEFLAGS",
                        "-j", "--build-jobs"):
            if index + 1 == len(arguments):
                raise ValueError(f"missing value for {argument}")
            value = arguments[index + 1]
            if argument == "-MAKEFLAGS":
                make_flags.extend(shlex.split(value))
            elif argument == "--Mdir":
                directory = value
                generation.extend((argument, value))
            elif argument == "--top-module":
                module = value
                generation.extend((argument, value))
            elif argument == "--prefix":
                prefix = value
                generation.extend((argument, value))
            # -j and --build-jobs are replaced by the single make job below.
            index += 2
            continue
        generation.append(argument)
        index += 1
    if directory is None or module is None:
        raise ValueError("course build requires --Mdir and --top-module")
    prefix = prefix or "V" + module
    make = executable(os.environ.get("MAKE", "make"))
    compile_command = [make, "-C", directory, "-f", prefix + ".mk", "-j1",
                       "VM_PARALLEL_BUILDS=1", *make_flags]
    trace_depth = int(os.environ.get("CPU2026_TRACE_DEPTH", "1"))
    if trace_depth < 0:
        raise ValueError("CPU2026_TRACE_DEPTH must be nonnegative")
    trace_flags = ["--trace-depth", str(trace_depth)] if trace_depth else []
    compact_ids = int(os.environ.get("CPU2026_COMPACT_IDS", "1"))
    if compact_ids not in (0, 1):
        raise ValueError("CPU2026_COMPACT_IDS must be 0 or 1")
    # Shorten private C++ identifiers without changing the public top interface.
    # This fixed, public key is for reproducible names, not IP protection.
    id_flags = (["--protect-ids", "--protect-key", "CPU2026-COMPILE-NAMES-V1"]
                if compact_ids else [])
    if int(os.environ.get("CPU2026_CPP_GROUP_BYTES", "524288")) < 0:
        raise ValueError("CPU2026_CPP_GROUP_BYTES must be nonnegative")
    return GENERATION_FLAGS + trace_flags + id_flags + generation, compile_command


def group_cpp_units(directory, prefix):
    """Combine small generated units, retaining fast/slow compiler categories."""
    limit = int(os.environ.get("CPU2026_CPP_GROUP_BYTES", "524288"))
    if limit < 0:
        raise ValueError("CPU2026_CPP_GROUP_BYTES must be nonnegative")
    if not limit:
        return {"enabled": False}
    directory = Path(directory)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", prefix):
        raise ValueError("unsupported generated C++ prefix")
    classes = directory / (prefix + "_classes.mk")
    manifest = directory / (prefix + "_cpu2026_groups.json")
    content = classes.read_text()
    marker = "# CPU2026 bounded C++ groups\n"
    if content.startswith(marker):
        return json.loads(manifest.read_text())
    pattern = re.compile(
        r"^(VM_(?:CLASSES|SUPPORT)_(?:FAST|SLOW))[ \t]*\+=[ \t]*\\\n"
        r"((?:[ \t]+[^\s]+[ \t]+\\\n)*)", re.MULTILINE)
    matches = list(pattern.finditer(content))
    if len(matches) != 4:
        raise ValueError("unsupported Verilator generated class-list format")
    seen = set()
    sections = []
    writes = []
    replacements = {}
    for match in matches:
        variable = match[1]
        names = [line.strip()[:-1].strip() for line in match[2].splitlines()]
        groups = []
        pending = []
        size = 0
        for name in names:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name in seen:
                raise ValueError("invalid or duplicate generated C++ class")
            seen.add(name)
            source_size = (directory / (name + ".cpp")).stat().st_size
            if pending and (size + source_size > limit or len(pending) == 8):
                groups.append(pending)
                pending = []
                size = 0
            pending.append(name)
            size += source_size
        if pending:
            groups.append(pending)
        outputs = []
        records = []
        for index, members in enumerate(groups):
            if len(members) == 1:
                output = members[0]
            else:
                output = f"{prefix}__cpu2026_{variable.lower()}_{index}"
                includes = "".join(f'#include "{name}.cpp"\n' for name in members)
                writes.append((directory / (output + ".cpp"),
                               "// Bounded group of generated C++ units.\n" + includes))
            outputs.append(output)
            records.append({"unit": output, "members": members})
        replacements[variable] = (variable + " += \\\n"
                                  + "".join(f"\t{name} \\\n" for name in outputs))
        sections.append({"category": variable, "original_units": len(names),
                         "compilation_units": len(outputs), "groups": records})
    result = {"enabled": True, "byte_limit": limit, "max_members": 8,
              "original_units": len(seen),
              "compilation_units": sum(s["compilation_units"] for s in sections),
              "sections": sections}
    for path, text in writes:
        path.write_text(text, newline="\n")
    classes.write_text(marker + pattern.sub(lambda m: replacements[m[1]], content),
                       newline="\n")
    manifest.write_text(json.dumps(result, indent=2) + "\n", newline="\n")
    return result


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        backend, reenter = select_backend()
        if reenter or "--build" not in arguments:
            return subprocess.call(backend + arguments)
        generation, compile_command = build_plan(arguments)
        environment = os.environ.copy()
        # An inherited GNU Make jobserver could override the one-job limit.
        # Compiler, linker, archiver and Python overrides remain explicit in
        # compile_command, copied from the official -MAKEFLAGS argument.
        environment.pop("MAKEFLAGS", None)
        environment.pop("MFLAGS", None)
        print("[build] Phase 1: Verilator generation; trace depth="
              + os.environ.get("CPU2026_TRACE_DEPTH", "1")
              + "; compact ids=" + os.environ.get("CPU2026_COMPACT_IDS", "1")
              + "; output split=8000; function split=2000; expression depth=32", file=sys.stderr,
              flush=True)
        started = time.monotonic()
        status = subprocess.call(backend + generation, env=environment)
        print(f"[build] Phase 1 finished: {time.monotonic() - started:.1f}s; "
              f"status={status}", file=sys.stderr, flush=True)
        if status:
            return status
        grouped = group_cpp_units(compile_command[2], Path(compile_command[4]).stem)
        if grouped["enabled"]:
            print(f"[build] C++ units: {grouped['original_units']} -> "
                  f"{grouped['compilation_units']}; max group bytes="
                  f"{grouped['byte_limit']}; max files=8", file=sys.stderr, flush=True)
        # The generator has exited and released its memory before g++ starts.
        print("[build] Phase 2: C++ compilation; jobs=1", file=sys.stderr,
              flush=True)
        started = time.monotonic()
        status = subprocess.call(compile_command, env=environment)
        print(f"[build] Phase 2 finished: {time.monotonic() - started:.1f}s; "
              f"status={status}", file=sys.stderr, flush=True)
        return status
    except (OSError, ValueError) as error:
        print(f"[build] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
