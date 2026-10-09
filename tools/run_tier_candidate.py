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


def validate_parameters(text, profile):
    """Reject unsupported geometry before an expensive HDL elaboration."""
    defaults = {k: int(v) for k, v in re.findall(r"\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)", text)}
    overrides = profile["parameters"]
    if type(profile.get("balanced_control_tree", 0)) is not int or profile.get("balanced_control_tree", 0) not in (0,1):
        raise ValueError("Balanced control tree policy must be 0 or 1")
    if profile.get("balanced_control_tree", 0) and profile.get("compact_control", 0):
        raise ValueError("Balanced bounded trees and global compact-control aliases are mutually exclusive")
    if type(profile.get("compact_control", 0)) is not int or profile.get("compact_control", 0) not in (0, 1):
        raise ValueError("Compact control policy must be 0 or 1")
    for key, value in overrides.items():
        if key not in defaults or type(value) is not int or value < 0:
            raise ValueError("Invalid override: " + key)
    p = defaults | overrides
    if p["COMPLETION_SOURCE_STATE_QUERY"] not in (0,1,2) or (p["COMPLETION_SOURCE_STATE_QUERY"] and p["COMPLETION_BYPASS"]!=2):
        raise ValueError("Completion source state query requires direct completion")
    if p["ROB_RECOVERY_PENDING_OWNER"] not in (0,1):
        raise ValueError("Pending recovery ownership must be 0 or 1")
    if p["DECODE_STATIC_HALT_CLASS"] not in (0,1):
        raise ValueError("Static HALT class must be 0 or 1")
    if p["LSQ_SAVED_CANDIDATE_STATE_QUERY"] not in (0,1) or (p["LSQ_SAVED_CANDIDATE_STATE_QUERY"] and not p["LSQ_SAVED_REQUEST_QUERY"]):
        raise ValueError("Saved candidate state requires saved request query")
    if p["LSQ_SAVED_REQUEST_QUERY"] not in (0,1) or (p["LSQ_SAVED_REQUEST_QUERY"] and
            (p["DCACHE_MSHRS"]<=1 or not p["DCACHE_TAG_SRAM"] or not p["DCACHE_WAY_PARALLEL_QUERY"])):
        raise ValueError("Saved LSQ request query requires registered parallel SRAM cache query")
    if p["LSQ_PHASED_DIRECT_WRITE_EVENTS"] not in (0,1) or (p["LSQ_PHASED_DIRECT_WRITE_EVENTS"] and not p["LSQ_PHASED_DATA_OWNER"]):
        raise ValueError("Direct phased events require the phased LSQ data owner")
    if p["LSQ_PHASED_DATA_OWNER"] not in (0,1):
        raise ValueError("LSQ phased data owner is 0/1")
    if p["DCACHE_MSHR_DATA_NO_CLEAR"] not in (0,1) or (p["DCACHE_MSHR_DATA_NO_CLEAR"] and
            (p["DCACHE_MSHRS"]<=1 or p["DCACHE_STATIC_UPDATES"]!=2)):
        raise ValueError("MSHR data no-clear requires banked nonblocking cache")
    if p["DCACHE_NARROW_REQUEST_WORD"] not in (0,1) or (p["DCACHE_NARROW_REQUEST_WORD"] and
            (p["DCACHE_MSHRS"]<=1 or not p["DCACHE_TAG_SRAM"] or p["DCACHE_REQUEST_PIPELINE"])):
        raise ValueError("Narrow cache request requires unpipelined synchronous nonblocking cache query")
    if p["MMIO_STORE_ADMISSION_ROUTE"] not in (0,1) or (p["MMIO_STORE_ADMISSION_ROUTE"] and
            (not p["MMIO_SAVED_ROUTE_CLASS"] or not p["LSQ_SAVED_REQUEST_QUERY"] or p["DCACHE_REQUEST_PIPELINE"])):
        raise ValueError("Factored MMIO STORE admission requires direct saved-query routing")
    if p["MMIO_SAVED_ROUTE_CLASS"] not in (0,1) or (p["MMIO_SAVED_ROUTE_CLASS"] and not p["LSQ_SAVED_REQUEST_QUERY"]):
        raise ValueError("Saved MMIO routing requires saved LSQ request classification")
    if p["MMIO_WRITE_CAPACITY_READY"] not in (0,1) or (p["MMIO_WRITE_CAPACITY_READY"] and not p["LSQ_SAVED_REQUEST_QUERY"]):
        raise ValueError("MMIO write capacity ready requires saved LSQ request classification")
    if p["PRF_SRAM_RAW_WRITE"] not in (0,1) or (p["PRF_SRAM_RAW_WRITE"] and not p["PRF_VALUE_SRAM"]):
        raise ValueError("PRF raw write data requires SRAM storage")
    if p["PRF_SRAM_PORT_FORWARD"] not in (0,1) or (p["PRF_SRAM_PORT_FORWARD"] and
            (not p["PRF_VALUE_SRAM"] or not p["PRF_READ_MUX_IMPL"])):
        raise ValueError("PRF SRAM port forwarding requires SRAM and parallel reads")
    if p["ROB_STORE_RETIRE_ADMISSION_BYPASS"] not in (0,1):
        raise ValueError("ROB store retirement admission bypass is 0/1")
    if p["ROB_COMPLETION_COMMIT_BYPASS"] not in (0,1):
        raise ValueError("ROB completion commit bypass is 0/1")
    if p["TAG_SINGLE_GENERATION_OWNER"] not in (0,1):
        raise ValueError("Tag single generation owner is 0/1")
    if p["LSQ_DIRECT_POP_CREDIT"] not in (0,1) or (p["LSQ_DIRECT_POP_CREDIT"] and
            (not p["DIRECT_DISPATCH_CURRENT_CREDITS"] or p["DISPATCH_PIPELINE"] or
             p["DISPATCH_ELASTIC"] or p["DIRECT_DISPATCH_RELEASE_CREDITS"])):
        raise ValueError("LSQ direct pop credit requires current direct dispatch without other release credits")
    if ((p["LSQ_DIRECT_POP_CREDIT"] or p["LSQ_ALLOC_LOAD_REQUEST_BYPASS"]) and
            (p["DCACHE_MSHRS"]<=1 or not p["DCACHE_TAG_SRAM"])):
        raise ValueError("Direct LSQ allocation policies require the registered nonblocking cache query")
    if p["RS_FRESH_DEFAULT_LANE_DATA"] not in (0,1) or (p["RS_FRESH_DEFAULT_LANE_DATA"] and not p["RS_ALLOC_EMPTY_BYPASS"]):
        raise ValueError("Fresh default-lane data requires RS allocation issue bypass")
    if p["RS_ALLOC_EMPTY_BYPASS"] not in (0,1,2) or (p["RS_ALLOC_EMPTY_BYPASS"] and
            (p["DISPATCH_PIPELINE"] or p["DISPATCH_ELASTIC"] or p["ISSUE_PIPELINE"] or
             not p["RS_ALLOC_STATIC_WRITE"] or p["DIRECT_DISPATCH_RELEASE_CREDITS"])):
        raise ValueError("Empty RS bypass requires direct static dispatch without release credits")
    if p["LSQ_ALLOC_LOAD_REQUEST_BYPASS"] not in (0,1) or (p["LSQ_ALLOC_LOAD_REQUEST_BYPASS"] and
            (not p["ALLOC_LOAD_SELECTION_BYPASS"] or not p["STORE_ALLOC_EARLY_ADDRESS"])):
        raise ValueError("Allocation load request bypass requires allocation selection and address")
    if p["MDU_PREFIX_SIGN_CORRECTION"] not in (0,1) or (p["MDU_PREFIX_SIGN_CORRECTION"] and p["MUL_IMPL"]!=2):
        raise ValueError("Prefix sign correction requires unified iterative MUL_IMPL=2")
    if p["MDU_DIVZERO_REMAINDER_REUSE"] not in (0, 1) or (p["MDU_DIVZERO_REMAINDER_REUSE"] and p["MUL_IMPL"]!=2):
        raise ValueError("MDU remainder reuse is 0/1 and requires unified iterative MUL_IMPL=2")
    if p["FETCH_OWNER_PAYLOAD_SELECT"] not in (0, 1):
        raise ValueError("Fetch owner payload selection is 0/1")
    if p["LSQ_COMMITTED_STORE_BYPASS"] not in (0, 1):
        raise ValueError("Committed store selection bypass is 0/1")
    if p["DECODE_EMPTY_BYPASS"] not in (0, 1) or p["DECODE_FULL_REPLACE"] not in (0, 1):
        raise ValueError("Decode queue policies are 0/1")
    depth = p["DECODE_QUEUE_DEPTH"]
    if depth and (depth < p["BE_WIDTH"] or depth & (depth-1)):
        raise ValueError("Decode queue depth is zero (legacy default) or a power of two >= BE_WIDTH")
    if (depth or p["DECODE_EMPTY_BYPASS"] or p["DECODE_FULL_REPLACE"]) and not p["DECODE_PIPELINE"]:
        raise ValueError("Decode queue policies require the decode stage")
    if p["SERIAL_BACKEND"] != 0:
        raise ValueError("Tier profiles must share rv32_backend_joint and vary widths/capacities; old separate-backend experiments require their frozen historical revision")
    if p["DCACHE_STORE_MERGE_POLICY"] not in (0, 1):
        raise ValueError("DCACHE_STORE_MERGE_POLICY is 0/1")
    if p["DCACHE_STORE_MISS_WRITE_AROUND"] not in (0, 1):
        raise ValueError("DCACHE_STORE_MISS_WRITE_AROUND is 0/1")
    if p["RENAME_REGISTERED_FREE_POOL"] not in (0, 1):
        raise ValueError("RENAME_REGISTERED_FREE_POOL is 0/1")
    if p["PRF_VALUE_SRAM"] not in (0, 1) or p["STORE_ALLOC_EARLY_ADDRESS"] not in (0, 1, 2):
        raise ValueError("PRF_VALUE_SRAM is 0/1; STORE_ALLOC_EARLY_ADDRESS is 0/1/2")
    if p["DISPATCH_PIPELINE"] not in (0, 1) or p["DISPATCH_ELASTIC"] not in (0, 1) or (p["DISPATCH_ELASTIC"] and not p["DISPATCH_PIPELINE"]):
        raise ValueError("Elastic dispatch requires its pipeline; both flags must be 0 or 1")
    if p["DIRECT_DISPATCH_CURRENT_CREDITS"] not in (0, 1) or (p["DIRECT_DISPATCH_CURRENT_CREDITS"] and (p["DISPATCH_PIPELINE"] or p["DISPATCH_ELASTIC"])):
        raise ValueError("Current credits require direct nonelastic dispatch")
    if p["DIRECT_DISPATCH_RELEASE_CREDITS"] not in (0, 1) or (p["DIRECT_DISPATCH_RELEASE_CREDITS"] and
            (not p["DIRECT_DISPATCH_CURRENT_CREDITS"] or p["DISPATCH_PIPELINE"] or p["DISPATCH_ELASTIC"] or not p["RS_ALLOC_STATIC_WRITE"])):
        raise ValueError("Release credits require current direct credits and static RS allocation")
    if p["DIRECT_LOAD_RS_CREDIT"] not in (0, 1) or (p["DIRECT_LOAD_RS_CREDIT"] and
            (not p["DIRECT_DISPATCH_CURRENT_CREDITS"] or p["DISPATCH_PIPELINE"] or p["DISPATCH_ELASTIC"] or
             p["EARLY_LOAD_ADDRESS"] < 2 or not p["EARLY_STORE_ADDRESS"] or not p["STORE_ALLOC_EARLY_ADDRESS"])):
        raise ValueError("Load RS credits require current direct credits and allocation-edge load addresses")
    if p["FE_WIDTH"] not in (1, 2, 4) or p["BE_WIDTH"] not in (1, 2, 4):
        raise ValueError("Frontend/backend widths must be 1, 2 or 4")
    if not 1 <= p["INT_ISSUE_WIDTH"] <= p["BE_WIDTH"] or not 1 <= p["CDB_WIDTH"] <= p["BE_WIDTH"]:
        raise ValueError("Issue/CDB width must fit the backend")
    if p["PHYS_REGS"] <= 32 or p["RS_ENTRIES"] < p["BE_WIDTH"]:
        raise ValueError("The OoO profile requires spare physical registers and sufficient RS rows")
    for key in ("ROB_ENTRIES", "LSQ_ENTRIES", "FETCH_QUEUE_DEPTH", "COMPLETION_DEPTH"):
        if p[key] < p["BE_WIDTH"] or p[key] & (p[key] - 1):
            raise ValueError("This profile requires a power-of-two capacity >= backend width: " + key)
    if p["PREDICTOR_COMPACT_BTB_ENTRIES"] not in (4, 8, 16, 32, 64) or p["PREDICTOR_COMPACT_BTB_ENTRIES"] < 2*p["FE_WIDTH"]:
        raise ValueError("The compact BTB requires 4/8/16/32/64 entries and >=2 rows per bank")
    if p["PREDICTOR_BHT_INDEX_BITS"] not in (6, 7, 8):
        raise ValueError("The current BHT supports 64/128/256 total entries")
    if not 1 <= p["PREDICTOR_HISTORY_BITS"] <= p["PREDICTOR_BHT_INDEX_BITS"] - int(math.log2(p["FE_WIDTH"])):
        raise ValueError("Predictor history must fit the banked tables")
    for side in ("I", "D"):
        if not 2 <= p[side + "CACHE_MSHRS"] <= 16:
            raise ValueError("These capacity profiles require the nonblocking cache with 2..16 MSHRs: " + side)
        ways = p[side + "CACHE_WAYS"]
        lines = p[side + "CACHE_LINES"]
        sets = lines // ways if ways else 0
        if ways not in (1, 2) or lines % ways or sets < 2 or sets & (sets - 1):
            raise ValueError("Invalid cache geometry: " + side)
    if not 1 <= p["DCACHE_WAITERS"] <= 16:
        raise ValueError("D-cache requires 1..16 waiters")
    if p["ROB_ENTRIES"] < 4 or p["AXI_RESPONSE_FIFO_DEPTH"] not in (0, 2, 4, 8):
        raise ValueError("ROB requires >=4 rows and response FIFO depth must be 0/2/4/8")
    for key, minimum in (("READ_LINES", 2), ("WRITE_LINES", 2), ("WORD_QUEUE", 4)):
        if p[key] < minimum or p[key] & (p[key]-1):
            raise ValueError("AXI bridge capacity must be a power of two >= " + str(minimum) + ": " + key)


def prepare(out, profile, host):
    if out.exists():
        raise ValueError("Keep existing candidates; choose a fresh output directory")
    validate_parameters((ROOT / "rtl/course/student_top.v").read_text(encoding="utf-8"), profile)
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
    if profile.get("compact_control", 0):
        for name in ("rv32im_defs.vh", "rtl/rv32im_defs.vh"):
            header = source / name
            content, count = re.subn(r"(`define RV32IM_COMPACT_CONTROL_DEFAULT )0\b", r"\g<1>1",
                                    header.read_text(encoding="utf-8"))
            if count != 1:
                raise ValueError("Missing compact control policy in " + name)
            header.write_text(content, encoding="utf-8", newline="")
    if profile.get("balanced_control_tree", 0):
        for name in ("rv32im_defs.vh", "rtl/rv32im_defs.vh"):
            header = source / name
            content, count = re.subn(r"(`define RV32IM_BALANCED_POLARITY_DEFAULT )0\b", r"\g<1>1",
                                    header.read_text(encoding="utf-8"))
            if count != 1:
                raise ValueError("Missing balanced polarity policy in " + name)
            header.write_text(content, encoding="utf-8", newline="")
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


def phase(out, name, performance_first=False):
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
        if not performance_first:
            ppa = read(out / "synth.json")
            if ppa["status"] != "PASSED" or not ppa.get("ppa_thresholds_passed", False):
                raise ValueError("Build requires complete area/frequency thresholds to pass")
            if sha(out / "synth/opt/report.json") != ppa["report_sha256"]:
                raise ValueError("Synthesis report changed")
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
        if name == "smoke":
            ppa, perf = read(out / "synth.json"), read(out / "perf.json")
            if (ppa["status"] != "PASSED" or not ppa.get("ppa_thresholds_passed", False)
                    or sha(out / "synth/opt/report.json") != ppa["report_sha256"]
                    or perf["status"] != "PASSED" or not perf.get("ipc_threshold_passed", False)):
                raise ValueError("Smoke requires this candidate's complete PPA and IPC gates to pass")
        build = read(out / "build.json")
        if build["status"] != "PASSED" or sha(binary) != build["executable_sha256"]:
            raise ValueError("A successful matching build is required")
        command = [sys.executable, str(source / "scripts/testcase.py"), "--testcases", str(source / "testcases"),
            "--sim", str(binary), "--latency", "10", "--max-cycles", "1000000"]
        command += ["--kind", "perf"] if name == "perf" else ["--kind", "correctness", "--case", "correctness_array_test1"]
    log = out / (name + ".log")
    state = dict(status="RUNNING", command=command, manifest_sha256=sha(out / "manifest.json"), phase=name)
    if name == "build":
        state["ppa_gate_checked_before_build"] = not performance_first
        state["performance_first_probe"] = performance_first
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
    parser.add_argument("--performance-first", action="store_true",
                        help="Build one frozen IPC probe before PPA; acceptance still requires full PPA on that snapshot")
    args = parser.parse_args()
    out = args.out.resolve()
    if args.performance_first and args.action != "build":
        parser.error("--performance-first applies only to build")
    if args.action == "prepare":
        if not args.profile:
            parser.error("prepare requires --profile")
        prepare(out, read(args.profile), read(args.host_config) if args.host_config else HOST)
    elif args.action == "check":
        verify(out, read(out / "manifest.json"))
        print("VERIFIED " + str(out))
    else:
        phase(out, args.action, args.performance_first)


if __name__ == "__main__":
    main()
