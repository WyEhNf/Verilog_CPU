"""Freeze a tier candidate, then explicitly measure one phase at a time.

The official synthesis, timing, SRAM, simulator and testcase scripts are copied
without modification. Never sweeps profiles or runs a full correctness suite.
Source-default parameter replacements affect only an independent snapshot.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HOST = {
    "runtime_bin": "F:/c26/msys64/mingw64/bin",
    "build_bin": "F:/c26/msys64/usr/bin",
    "verilator": "F:/CPU2026CourseTools/win5040/source_release/verilator-5.040/bin/verilator_bin.exe",
    "verilator_root": "F:/CPU2026CourseTools/win5040/source_release/verilator-5.040",
    "yosys": "F:/CPU2026CourseTools/win54fc150/yosys/bin/yosys.exe",
    "abc": "F:/CPU2026CourseTools/win54fc150/yosys/bin/yosys-abc.exe",
    "sta": "F:/CPU2026CourseTools/win54fc150/opensta/bin/sta.exe",
    "asap7_lib": "F:/CPU2026CourseTools/win54fc150/asap7/lib",
}
BENCHMARKS = ["perf_median", "perf_multiply", "perf_qsort", "perf_rsort", "perf_towers", "perf_vvadd"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(out, profile, host):
    if out.exists():
        raise ValueError("Keep existing candidates; choose a fresh output directory")
    if not (ROOT / "testcases/perf_median/metrics.json").is_file():
        raise ValueError("Initialize the official testcases submodule first")
    for name in ("yosys", "abc", "sta", "verilator"):
        if not Path(host[name]).is_file():
            raise ValueError("Missing tool: " + name)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    chosen = [name for name in tracked if name and (
        name.startswith(("rtl/", "verilog/", "scripts/", "tools/"))
        or name in ("rv32im_defs.vh", "config.mk", "Makefile")) and (ROOT / name).is_file()]
    out.mkdir(parents=True)
    source = out / "source"
    for name in chosen:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    top = source / "rtl/course/student_top.v"
    text = top.read_text(encoding="utf-8")
    original = text
    for key, value in profile["parameters"].items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or type(value) is not int or value < 0:
            raise ValueError("Invalid override: " + key)
        text, count = re.subn(r"(\b" + key + r"\s*=\s*)\d+", lambda m: m[1] + str(value), text, count=1)
        if count != 1:
            raise ValueError("Missing parameter: " + key)
    top.write_text(text, encoding="utf-8", newline="")
    # Submodules have no tracked files in the parent repository's ls-files.
    cases = ROOT / "testcases"
    testcase_commit = subprocess.check_output(["git", "-C", str(cases), "rev-parse", "HEAD"], text=True).strip()
    expected_commit = subprocess.check_output(["git", "ls-tree", "HEAD", "testcases"], cwd=ROOT, text=True).split()[2]
    if testcase_commit != expected_commit:
        raise ValueError("Testcase submodule differs from the current commit")
    for directory in sorted(cases.iterdir()):
        if not directory.is_dir() or not directory.name.startswith(("perf_", "correctness_")):
            continue
        for name in ("program.data", "expected.txt", "metrics.json"):
            origin = directory / name
            if origin.is_file():
                destination = source / "testcases" / directory.name / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, destination)
    source_sha = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob("*") if p.is_file()}
    manifest = dict(status="PREPARED", base_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), profile=profile,
        host=host, source_sha256=source_sha, original_top_sha256=hashlib.sha256(original.encode()).hexdigest(),
        tool_sha256={k: sha(host[k]) for k in ("yosys", "abc", "sta", "verilator")},
        library_sha256={p.name: sha(p) for p in Path(host["asap7_lib"]).glob("*.lib")},
        testcase_commit=testcase_commit, latency=10)
    save(out / "manifest.json", manifest)
    print("PREPARED " + str(out), flush=True)


def verify(out, manifest):
    for name, expected in manifest["source_sha256"].items():
        if sha(out / "source" / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    for name, expected in manifest["tool_sha256"].items():
        if sha(manifest["host"][name]) != expected:
            raise ValueError("Tool changed: " + name)
    for name, expected in manifest["library_sha256"].items():
        if sha(Path(manifest["host"]["asap7_lib"]) / name) != expected:
            raise ValueError("Library changed: " + name)


def phase(out, name):
    manifest = read(out / "manifest.json")
    verify(out, manifest)
    host = manifest["host"]
    source = out / "source"
    record = out / (name + ".json")
    if record.exists():
        raise ValueError("Phase already recorded; preserve its result")
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    env["PATH"] = os.pathsep.join([host["runtime_bin"], host["build_bin"], env.get("PATH", "")])
    env["VERILATOR_ROOT"] = host["verilator_root"]
    env["CPU2026_REAL_VERILATOR"] = host["verilator"]
    env["MAKE"] = str(Path(host["build_bin"]) / "make.exe")
    env["SHELL"] = str(Path(host["build_bin"]) / "sh.exe")
    env.update(CPU2026_PGO="0", CPU2026_WORD_SIM="1", CPU2026_STABLE_MDU="0",
               CPU2026_ICO_PAIR="0", CPU2026_NATIVE_BITS="1", CPU2026_SPLIT_SCHEDULE="1",
               CPU2026_TRACE_DEPTH="1", CPU2026_COMPACT_IDS="0", CPU2026_UNROLL_STMTS="1000000")
    binary = out / "build/sim.exe"
    if name == "synth":
        command = [sys.executable, str(source / "scripts/synth.py"), "--filelist", "verilog/filelist.f",
            "--out", str(out / "synth"), "--mode", "opt", "--clock-period", "2.0", "--appimage", "",
            "--yosys", host["yosys"], "--abc", host["abc"], "--sta", host["sta"], "--asap7-lib", host["asap7_lib"]]
    elif name == "build":
        if binary.exists():
            raise ValueError("Keep existing binary")
        obj = out / "build/obj"
        obj.mkdir(parents=True)
        files = [(source / "verilog" / line.split("#", 1)[0].strip()).resolve() for line in
                 (source / "verilog/filelist.f").read_text().splitlines() if line.split("#", 1)[0].strip()]
        cpp = (Path(host["runtime_bin"]) / "g++.exe").as_posix()
        ar = (Path(host["runtime_bin"]) / "ar.exe").as_posix()
        flags = f"CXX={cpp} LINK={cpp} AR={ar} PYTHON3={Path(sys.executable).as_posix()}"
        command = [sys.executable, str(source / "tools/verilator_low_memory.py"), "--cc", "--exe", "--build",
            "--trace", "--assert", "-Wall", "-Wno-fatal", "--top-module", "student_top", "--Mdir", str(obj),
            "-o", str(binary), "-j", "1", "-MAKEFLAGS", flags, "-CFLAGS", "-std=c++17",
            str(source / "scripts/ram/sram_fakeram.sv"), *map(str, files),
            str(source / "scripts/sim.cpp"), str(source / "tools/verilator_windows_time_zero.cpp")]
    else:
        build = read(out / "build.json")
        if build["status"] != "PASSED" or sha(binary) != build["executable_sha256"]:
            raise ValueError("A successful matching build is required")
        command = [sys.executable, str(source / "scripts/testcase.py"), "--testcases", str(source / "testcases"),
            "--sim", str(binary), "--latency", "10", "--max-cycles", "1000000"]
        command += ["--kind", "perf"] if name == "perf" else ["--kind", "correctness", "--case", "correctness_array_test1"]
    log = out / (name + ".log")
    state = dict(status="RUNNING", command=command, manifest_sha256=sha(out / "manifest.json"), phase=name)
    save(record, state)
    print("START " + name + " " + str(out), flush=True)
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
    state.update(status="PASSED" if result.returncode == 0 else "FAILED", returncode=result.returncode,
                 seconds=time.monotonic() - start, log_sha256=sha(log))
    if result.returncode == 0:
        verify(out, manifest)
        if name == "build":
            state["executable_sha256"] = sha(binary)
        elif name == "synth":
            report = read(out / "synth/opt/report.json")
            state.update(area_um2=report["area"]["area_um2"], fmax_mhz=report["timing"]["estimated_fmax_mhz"],
                         report_sha256=sha(out / "synth/opt/report.json"))
            p = manifest["profile"]
            state["ppa_thresholds_passed"] = state["area_um2"] <= p["maximum_area_um2"] and state["fmax_mhz"] >= p["minimum_frequency_mhz"]
        elif name == "perf":
            rows = []
            for line in log.read_text().splitlines():
                match = re.fullmatch(r"(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)", line)
                if match:
                    case, instructions, cycles, _ = match.groups()
                    if int(instructions) != read(source / "testcases" / case / "metrics.json")["dynamic_instructions"]:
                        raise ValueError("Wrong instruction count: " + case)
                    rows.append(dict(name=case, instructions=int(instructions), cycles=int(cycles), ipc=int(instructions)/int(cycles)))
            if sorted(r["name"] for r in rows) != BENCHMARKS:
                raise ValueError("Six complete official perf results required")
            state.update(results=rows, geomean_ipc=math.exp(sum(math.log(r["ipc"]) for r in rows)/6))
            state["ipc_threshold_passed"] = state["geomean_ipc"] >= manifest["profile"]["minimum_geomean_ipc"]
    save(record, state)
    print(json.dumps(state, ensure_ascii=False, indent=2), flush=True)
    if result.returncode:
        print(log.read_text(errors="replace")[-5000:], flush=True)
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "synth", "build", "perf", "smoke"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--host-config", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.action == "prepare":
        if not args.profile:
            parser.error("prepare requires --profile")
        prepare(out, read(args.profile), read(args.host_config) if args.host_config else HOST)
    elif args.action == "check":
        verify(out, read(out / "manifest.json"))
        print("VERIFIED " + str(out))
    else:
        phase(out, args.action)


if __name__ == "__main__":
    main()
