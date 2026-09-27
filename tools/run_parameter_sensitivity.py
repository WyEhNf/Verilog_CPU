#!/usr/bin/env python3
"""Sequential single-knob CPU-2026 sweeps using the Windows Verilator builder.

Every case is freshly built; refuse existing output directories. Retain logs,
executables, generated C++, parameters and source hashes. Only generated PCH
caches from this invocation may be removed after a successful six-test run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = dict(FeWidth=2, BeWidth=2, PhysRegs=48, RobEntries=16, RsEntries=4,
            LsqEntries=8, IntIssueWidth=2, CdbWidth=2, EnableCacheStats=1,
            IcacheMshrs=8, IcacheLines=64, IcacheWays=2,
            DcacheMshrs=4, DcacheLines=128,
            DcacheWays=1, DcacheIndexHash=1,
            DcacheRequestPipeline=0,
            RamSizeBytes=1048576, LegacySentinelHalt=1,
            IMemoryOutstanding=16, DMemoryOutstanding=8, CompletionDepth=8,
            FetchQueueDepth=16, MemoryLatency=20, MulImpl=0, ShiftImpl=0,
            PhysTagImpl=0, GenerationWidth=8, CheckpointImpl=0,
            StoreBufferedRetire=1, CompletionBypass=0, SerialBackend=0)
CASES = dict(baseline={}, rob32=dict(RobEntries=32), rs8=dict(RsEntries=8),
             phys64=dict(PhysRegs=64), lsq16=dict(LsqEntries=16),
             dmshr8=dict(DcacheMshrs=8), issue1=dict(IntIssueWidth=1))
SINGLE_KNOB_CASES = tuple(CASES)
# Explicit opt-in interaction test; never label this as an isolated parameter.
CASES["rob32_rs8"] = dict(RobEntries=32, RsEntries=8)
CASES["rob32_rs8_phys64"] = dict(RobEntries=32, RsEntries=8, PhysRegs=64)
CASES["pipe1"] = dict(DcacheRequestPipeline=1)
CASES["rob32_rs8_pipe1"] = dict(RobEntries=32, RsEntries=8, DcacheRequestPipeline=1)
CASES["d64"] = dict(DcacheLines=64)
CASES["d64_pipe1"] = dict(DcacheLines=64, DcacheRequestPipeline=1)
CASES["assoc2"] = dict(DcacheWays=2)
CASES["assoc2_64"] = dict(DcacheWays=2, DcacheLines=64)
CASES["icache128"] = dict(IcacheLines=128)
CASES["icache1way"] = dict(IcacheWays=1)
CASES["p4"] = dict(FeWidth=4, BeWidth=4, PhysRegs=96, RobEntries=64,
                   RsEntries=16, LsqEntries=16, IntIssueWidth=4, CdbWidth=4,
                   DcacheLines=256, CompletionDepth=16)
CASES["p4_assoc2"] = dict(CASES["p4"], DcacheWays=2)
CASES["p4_assoc2_rs32"] = dict(CASES["p4_assoc2"], RsEntries=32)
CASES["p4_assoc2_lsq32"] = dict(CASES["p4_assoc2"], LsqEntries=32)
CASES["p4_assoc2_d512"] = dict(CASES["p4_assoc2"], DcacheLines=512)
CASES["p4_d512_checkpoint1"] = dict(CASES["p4_assoc2_d512"], CheckpointImpl=1)
CASES["p4_d512_rob32"] = dict(CASES["p4_assoc2_d512"], RobEntries=32)
CASES["p4_d1024"] = dict(CASES["p4_assoc2"], DcacheLines=1024)
CASES["p4_d1024_cp1"] = dict(CASES["p4_d1024"], CheckpointImpl=1)
CASES["p4_d1024_cp1_rob32"] = dict(CASES["p4_d1024_cp1"], RobEntries=32)
CASES["p4_d1024_cp1_phys64"] = dict(CASES["p4_d1024_cp1"], PhysRegs=64)
CASES["p4_d1024_cp1_r32p64"] = dict(CASES["p4_d1024_cp1"],
                                     RobEntries=32, PhysRegs=64)
CASES["p4_d1024_cp1_r16p64"] = dict(CASES["p4_d1024_cp1"],
                                     RobEntries=16, PhysRegs=64)


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_hashes():
    paths = list((ROOT / "rtl").rglob("*.v")) + list((ROOT / "rtl").rglob("*.vh"))
    paths += [ROOT / name for name in (
        "rtl/filelist.f", "tb/models/rv32im_memory_model.v",
        "tb/integration/cpu_core_image_tb.v", "tools/build_join02_verilator.ps1",
        "tools/run_cpu2026.py", "tools/run_parameter_sensitivity.py")]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}


def execute(command, log):
    with log.open("w", encoding="utf-8") as handle:
        subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                       check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--prefix", default="sens_p2_hash_d128")
    parser.add_argument("--compiler-bin", default="E:/mingw64/bin")
    parser.add_argument("--keep-pch", action="store_true")
    args = parser.parse_args()
    if not args.prefix or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in args.prefix):
        parser.error("prefix must contain only lowercase letters, digits and underscores")
    selected = args.case or list(SINGLE_KNOB_CASES)
    if len(set(selected)) != len(selected):
        parser.error("duplicate cases")
    suite = ROOT / "build/cpu2026" / args.prefix
    suite.mkdir(parents=True, exist_ok=True)
    cad = ROOT / ".deps/oss-cad-suite-install/oss-cad-suite"
    toolchain = ROOT / ".deps/riscv-toolchain-install/xpack-riscv-none-elf-gcc-15.2.0-1/bin"
    hashes = source_hashes()
    for case in selected:
        if source_hashes() != hashes:
            raise RuntimeError("sources changed during sweep")
        name = args.prefix + "_" + case
        mdir = ROOT / "build/vlt" / name
        if mdir.exists() or (suite / (case + ".json")).exists():
            raise RuntimeError("refusing existing case: " + name)
        if shutil.disk_usage(ROOT).free < 330_000_000:
            raise RuntimeError("less than 330 MB free; not starting another compilation")
        params = dict(BASE, **CASES[case])
        print("BUILD " + case + " " + json.dumps(CASES[case]), flush=True)
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(ROOT / "tools/build_join02_verilator.ps1"),
                   "-Verilator", str(cad / "bin/verilator_bin.exe"),
                   "-VerilatorRoot", str(cad / "share/verilator"),
                   "-CompilerBin", args.compiler_bin, "-Mdir", str(mdir), "-Output", name]
        for key, value in params.items():
            command += ["-" + key, str(value)]
        execute(command, suite / (case + "_build.log"))
        if source_hashes() != hashes:
            raise RuntimeError("sources changed during build")
        executable = mdir / (name + ".exe")
        command = [sys.executable, str(ROOT / "tools/run_cpu2026.py"),
                   "--executable", str(executable), "--memory-latency", "20",
                   "--config", json.dumps(params, sort_keys=True),
                   "--report", str(suite / (case + ".json"))]
        for tool in ("cc", "objdump", "objcopy", "readelf"):
            binary = "gcc" if tool == "cc" else tool
            command += ["--" + tool, str(toolchain / ("riscv-none-elf-" + binary + ".exe"))]
        execute(command, suite / (case + "_run.log"))
        report = json.loads((suite / (case + ".json")).read_text(encoding="utf-8"))
        if len(report["results"]) != 6 or any(r["status"] != "passed" for r in report["results"]):
            raise RuntimeError("not all six benchmarks passed")
        if source_hashes() != hashes:
            raise RuntimeError("sources changed during benchmark")
        manifest = dict(parameters=params, source_sha256=hashes,
                        executable_sha256=digest(executable),
                        report_sha256=digest(suite / (case + ".json")))
        (suite / (case + "_manifest.json")).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        removed = 0
        if not args.keep_pch:
            expected = (ROOT / "build/vlt" / name).resolve()
            if mdir.resolve() != expected or expected.parent != (ROOT / "build/vlt").resolve():
                raise RuntimeError("unsafe cache cleanup target")
            for cache in mdir.glob("*.gch"):
                if cache.resolve().parent != expected or cache.is_symlink():
                    raise RuntimeError("unsafe PCH cache path")
                removed += cache.stat().st_size
                cache.unlink()
        print("PASS {} cycles={} IPC={:.9f}; removed {} generated PCH bytes".format(
            case, report["total_cycles"], report["aggregate_ipc"], removed), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
