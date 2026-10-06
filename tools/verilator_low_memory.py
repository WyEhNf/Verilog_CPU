#!/usr/bin/env python3
"""Run the course Verilator build in separate, memory-bounded host phases."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
# Match the previously verified native Verilator 5.020 translation settings.
GENERATION_FLAGS = [
    "--unroll-count", "1024", "--unroll-stmts", "1000000",
    "--output-split", "2000", "--output-split-cfuncs", "2000",
    "--output-split-ctrace", "2000",
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
    return GENERATION_FLAGS + generation, compile_command


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
        print("[build] Separate Verilator generation; C++ build jobs=1; "
              "output split=2000", file=sys.stderr)
        status = subprocess.call(backend + generation, env=environment)
        if status:
            return status
        # The generator has exited and released its memory before g++ starts.
        return subprocess.call(compile_command, env=environment)
    except (OSError, ValueError) as error:
        print(f"[build] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
