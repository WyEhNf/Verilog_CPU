#!/usr/bin/env python3
"""Build GCC branch profiles with the original course simulator and inputs."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from cpu2026_build_log import run_logged


ROOT = Path(__file__).resolve().parents[1]
TRAINING_CYCLES = 100000


def assignment(command, name, default=""):
    return next((item.partition("=")[2] for item in reversed(command)
                 if item.startswith(name + "=")), default)


def with_assignments(command, **values):
    return [item for item in command
            if not any(item.startswith(name + "=") for name in values)] + [
                name + "=" + value for name, value in values.items()]


def objects_in_section(text, name):
    match = re.search(r"^" + name + r"\s*(?:\+=|=)\s*\\\n"
                      r"((?:[ \t]+[^\n]+\\\n)*)", text, re.MULTILINE)
    if not match:
        raise ValueError("unsupported generated object section: " + name)
    names = [line.strip()[:-1].strip() for line in match[1].splitlines()]
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names):
        raise ValueError("unsupported generated object name")
    return names


def plan(generation, command, environment):
    enabled = environment.get("CPU2026_PGO", "1")
    if enabled not in ("0", "1"):
        raise ValueError("CPU2026_PGO must be 0 or 1")
    if enabled == "0":
        return None, "disabled"
    if "+define+CPU2026_WORD_SIM" not in generation:
        return None, "original structural simulation requested"
    if "--top-module" not in generation or generation[
            generation.index("--top-module") + 1] != "student_top":
        return None, "custom top module"
    driver = (ROOT / "scripts/sim.cpp").resolve()
    sources = [Path(item).resolve() for item in generation if item.endswith(".cpp")]
    if sources != [driver] or "-o" not in generation:
        return None, "custom simulation driver or output"
    overrides = [environment.get(name, "") for name in
                 ("CXXFLAGS", "LDFLAGS", "CPPFLAGS", "VM_USER_CFLAGS",
                  "VM_USER_LDFLAGS")]
    if any("-fprofile" in item or "-flto" in item
           for item in command + generation + overrides):
        return None, "explicit compiler profiling or LTO settings"
    compiler = assignment(command, "CXX", environment.get("CXX", "g++"))
    version = subprocess.run([compiler, "--version"], env=environment,
                             capture_output=True, text=True, timeout=10)
    if (version.returncode or "Free Software Foundation" not in version.stdout
            or "clang" in version.stdout.lower()):
        return None, "compiler is not GNU GCC"
    # Public course program, vendored with provenance so a plain OJ clone
    # does not need to download the optional testcase submodule to build.
    image = ROOT / "tools/cpu2026_pgo_pi.txt"
    if not image.is_file():
        return None, "course Pi training input unavailable"
    directory = Path(command[2]).resolve()
    prefix = Path(command[4]).stem
    hot = objects_in_section((directory / (prefix + "_classes.mk")).read_text(),
                             "VM_CLASSES_FAST")
    hot += objects_in_section((directory / (prefix + "_classes.mk")).read_text(),
                              "VM_SUPPORT_FAST")
    hot += objects_in_section((directory / (prefix + ".mk")).read_text(),
                              "VM_USER_CLASSES")
    if len(hot) != len(set(hot)):
        raise ValueError("duplicate generated hot object")
    objects = [directory / (name + ".o") for name in hot]
    if any(path.resolve().parent != directory or path.is_symlink() for path in objects):
        raise ValueError("profile build object escaped its generated directory")
    binary = Path(generation[generation.index("-o") + 1])
    if not binary.is_absolute():
        binary = directory / binary
    binary = binary.resolve()
    profile = directory / "cpu2026_profile"
    if profile.is_symlink() or profile.resolve().parent != directory:
        raise ValueError("profile directory must not be a symbolic link")
    # Official build.py recreates its object directory. Reusing profiles from
    # another generation is unsafe: retain them and use the ordinary build.
    if profile.exists() and any(profile.iterdir()):
        return None, "profile directory already populated; clean build required"
    return {"directory": directory, "profile": profile, "binary": binary,
            "objects": objects, "image": image,
            "compiler": version.stdout.splitlines()[0]}, None


def compile_with_profile(generation, command, environment):
    selected, reason = plan(generation, command, environment)
    if selected is None:
        print("[build] GCC profiles: ordinary build (" + reason + ")",
              file=sys.stderr, flush=True)
        return run_logged(command, environment,
                          Path(command[2]) / "cpu2026_compile.log", "C++ build")
    profile = selected["profile"]
    profile.mkdir(exist_ok=True)
    profile_flag = profile.as_posix()
    fast = assignment(command, "OPT_FAST", "-O3")
    link = assignment(command, "VM_USER_LDFLAGS")
    record = {"compiler": selected["compiler"], "training_cycles": TRAINING_CYCLES,
              "latency": 10, "wave": False, "phases": []}

    def save():
        (selected["directory"] / "cpu2026_pgo.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")

    def build(label, flags):
        # Only known hot objects and the official driver change flags. Cold
        # model/runtime objects remain the course's original -Os build.
        for path in selected["objects"]:
            path.unlink(missing_ok=True)
        step = with_assignments(command, OPT_FAST=fast + " " + flags,
                                VM_USER_LDFLAGS=(link + " " + flags).strip())
        print("[build] " + label + "; jobs=1", file=sys.stderr, flush=True)
        started = time.monotonic()
        logfile = "cpu2026_compile_generate.log" if "-fprofile-generate=" in flags \
                  else "cpu2026_compile_use.log"
        status = run_logged(step, environment,
                            selected["directory"] / logfile, label)
        record["phases"].append({"phase": label, "seconds": time.monotonic() - started,
                                 "status": status, "command": step})
        save()
        return status

    status = build("GCC profile generation", shlex.quote("-fprofile-generate=" +
                   profile_flag) + " -fprofile-update=single")
    if status:
        return status
    binary = selected["binary"]
    if os.name == "nt" and not binary.is_file():
        binary = Path(str(binary) + ".exe")
    if not binary.is_file():
        raise ValueError("profile training simulator was not produced")
    training_environment = environment.copy()
    for key in ("CPU2026_STABLE_MDU_VERIFY", "CPU2026_STABLE_MDU_DISABLE",
                "CPU2026_STABLE_MDU_DIAGNOSTICS", "CPU2026_ICO_PAIR_VERIFY",
                "CPU2026_ICO_PAIR_DISABLE"):
        training_environment.pop(key, None)
    print("[build] Profile training: original Pi; 100000 real cycles; latency=10",
          file=sys.stderr, flush=True)
    started = time.monotonic()
    training = subprocess.run([str(binary), str(selected["image"]), "112",
                               str(TRAINING_CYCLES), "10"],
                              env=training_environment, capture_output=True,
                              text=True, timeout=30)
    record["phases"].append({"phase": "limited Pi profile training",
                             "seconds": time.monotonic() - started,
                             "status": training.returncode,
                             "stdout": training.stdout, "stderr": training.stderr})
    save()
    # The fixed window ends before Pi completes. Its expected failure is only
    # training data, never reported as a correctness pass or test result.
    if (training.returncode != 1 or training.stderr
            or not training.stdout.startswith("FAIL cycles=100000 ")):
        print("[build] Unexpected profile training result: " + training.stdout +
              training.stderr, file=sys.stderr, flush=True)
        return 2
    profiles = list(profile.rglob("*.gcda"))
    if not profiles:
        raise ValueError("GCC produced no branch profile data")
    record["profile_files"] = len(profiles)
    record["profile_bytes"] = sum(path.stat().st_size for path in profiles)
    # GCC's profile counters are collected before link-time optimization.
    # The measured configuration uses serial LTO for the final executable;
    # missing/mismatched profile warnings remain visible and unsuppressed.
    return build("GCC profile use and serial LTO",
                 shlex.quote("-fprofile-use=" + profile_flag) + " -flto=1")
