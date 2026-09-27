#!/usr/bin/env python3
"""Fully map CPU memories to ASAP7 cells, one hierarchy module per process.

This preserves RTL hierarchy (and counts every instance), bounds peak memory,
and resumes completed stages only when their input/flow fingerprint matches.
No SRAM black boxes or per-bit area estimates are used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LIBDIR = ROOT / "_asap7_lib_filtered"
LIBS = sorted(LIBDIR.glob("*.lib"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="build/synth/p4_i16_d32k_full")
    for name, default in (("fe-width", 4), ("be-width", 4), ("phys-regs", 96),
                          ("rob-entries", 64), ("rs-entries", 16), ("lsq-entries", 16),
                          ("int-issue-width", 4), ("cdb-width", 4),
                          ("icache-mshrs", 16), ("dcache-mshrs", 8), ("dcache-lines", 2048),
                          ("fetch-queue-depth", 16), ("completion-depth", 16),
                          ("cache-stats", 1), ("checkpoint-impl", 0),
                          ("dcache-index-hash", 0),
                          ("dcache-request-pipeline", 0), ("dcache-ways", 1),
                          ("ram-size-bytes", 268435456), ("legacy-sentinel-halt", 0),
                          ("icache-lines", 64), ("icache-ways", 2)):
        parser.add_argument("--" + name, type=int, default=default)
    args = parser.parse_args()
    out = (ROOT / args.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    suite = ROOT / ".deps/oss-cad-suite-install/oss-cad-suite"
    yosys = suite / "bin/yosys.exe"
    env = dict(os.environ)
    env["PATH"] = str(suite / "bin") + os.pathsep + str(suite / "lib") + os.pathsep + env["PATH"]
    config = [args.fe_width, args.be_width, args.phys_regs, args.rob_entries,
              out.as_posix(), args.rs_entries, args.lsq_entries, args.cache_stats, 0, 1, 1,
              args.fetch_queue_depth, args.completion_depth, 0, 0, 8,
              args.checkpoint_impl, 0, 0,
              args.int_issue_width, args.cdb_width, args.icache_mshrs, args.dcache_mshrs,
              args.dcache_lines, args.dcache_index_hash, args.dcache_request_pipeline,
              args.dcache_ways, args.ram_size_bytes, args.legacy_sentinel_halt,
              args.icache_lines, args.icache_ways]
    sources = [ROOT / p.strip() for p in (ROOT / "rtl/filelist.f").read_text().splitlines() if p.strip()]
    sources += list((ROOT / "rtl").rglob("*.vh"))
    sources += [ROOT / "synth/synth.tcl", Path(__file__), *LIBS, LIBDIR / "asap7_comb.genlib"]
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    fingerprint = hashlib.sha256(json.dumps([config, hashes], sort_keys=True).encode()).hexdigest()
    manifest_path = out / "run_manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous["fingerprint"] != fingerprint:
            changed = {key for key in hashes.keys() | previous["source_sha256"].keys()
                       if hashes.get(key) != previous["source_sha256"].get(key)}
            if changed != {"tools/run_full_area.py"} or previous["parameters"] != config:
                raise SystemExit("Design inputs changed; use a new --outdir to preserve the prior run.")
            # A runner fix may resume unchanged stage scripts; each stage has
            # its own content hash. Retain the previous provenance as well.
            history = out / ("run_manifest_" + previous["fingerprint"][:12] + ".json")
            history.write_text(json.dumps(previous, indent=2) + "\n")
            manifest_path.write_text(json.dumps({"fingerprint": fingerprint, "parameters": config,
                                                "source_sha256": hashes}, indent=2) + "\n")
    else:
        manifest_path.write_text(json.dumps({"fingerprint": fingerprint, "parameters": config,
                                            "source_sha256": hashes}, indent=2) + "\n")

    def run(name, script, tcl=False, parameters=None):
        script_path = out / (name + (".tcl" if tcl else ".ys"))
        marker = out / (name + ".done.json")
        digest = hashlib.sha256(script.encode()).hexdigest()
        if marker.exists() and json.loads(marker.read_text())["script_sha256"] == digest:
            print("RESUME " + name, flush=True)
            return
        script_path.write_text(script, encoding="utf-8")
        command = [str(yosys), "-T"]
        if tcl:
            command += ["-p", "tcl " + script_path.as_posix() + " " + " ".join(map(str, parameters or []))]
        else:
            command += ["-s", str(script_path)]
        print("START " + name, flush=True)
        start = time.time()
        with (out / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f"{name} failed ({result.returncode}); see {out / (name + '.log')}")
        marker.write_text(json.dumps({"script_sha256": digest, "seconds": time.time() - start}) + "\n")
        print(f"DONE {name} {time.time() - start:.1f}s", flush=True)

    # Keep the existing flow's complete elaboration/parameter handling, changing
    # only the mapping schedule. All design inputs are recorded above.
    original = (ROOT / "synth/synth.tcl").read_text()
    assert original.count("\nmemory_dff\n") == 1
    elaborate = original.split("\nmemory_dff\n")[0] + "\nwrite_rtlil $outdir/elaborated.il\n"
    run("elaborate", elaborate, tcl=True, parameters=config)
    prep = "yosys -import\nset outdir {" + out.as_posix() + "}\n"
    prep += r'''
read_rtlil $outdir/elaborated.il
# Avoid the optional, potentially unbounded SAT priority/port-sharing passes.
# memory_map preserves the original priority relations without those passes.
opt_mem
opt_mem_feedback
memory_dff
opt_clean
memory_share -nosat
opt_mem_widen
opt_clean
memory_collect
opt_clean
tee -o $outdir/memory_manifest.il dump {t:$mem*}
tee -q -o $outdir/modules.txt select -list-mod
write_rtlil $outdir/prepared.il
set f [open "$outdir/modules.txt" r]
set names [split [string trim [read $f]] "\n"]
close $f
set index [open "$outdir/modules.tsv" w]
set i 0
foreach name $names {
    set name [string trim $name]
    if {$name eq ""} { continue }
    select $name
    write_rtlil -selected $outdir/module_$i.il
    puts $index "$i\t$name"
    incr i
}
close $index
select -clear
'''
    run("prepare", prep, tcl=True, parameters=config)
    modules = [line.split("\t", 1) for line in (out / "modules.tsv").read_text().splitlines()]
    libargs = " ".join("-liberty " + p.as_posix() for p in LIBS)
    libread = "\n".join("read_liberty -lib -ignore_miss_func " + p.as_posix() for p in LIBS)
    seq = LIBDIR / "asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib"
    mapped = []
    for i, module in modules:
        path = out / f"mapped_{i}.il"
        script = f'''read_rtlil {out.as_posix()}/module_{i}.il
memory_map
opt -full
techmap
opt
dfflibmap -liberty {seq.as_posix()}
opt
abc -genlib {LIBDIR.as_posix()}/asap7_comb.genlib -script "+strash;scorr;dc2;dretime;strash;map -a"
opt_clean
select -assert-none t:$* t:$paramod* %d
tee -o {out.as_posix()}/mapped_{i}_stat.log stat {libargs}
write_rtlil {path.as_posix()}
'''
        print(f"MODULE {i}: {module}", flush=True)
        run("map_" + i, script)
        mapped.append(path)
    final = libread + "\n" + "\n".join("read_rtlil " + p.as_posix() for p in mapped)
    final += f'''
hierarchy -check -top cpu_core
select -assert-none t:$* t:$paramod* %d
check -assert
tee -o {out.as_posix()}/synth.log stat {libargs}
tee -o {out.as_posix()}/stat.json stat -json {libargs}
write_verilog -noattr -noexpr {out.as_posix()}/cpu_core_synth.v
'''
    run("assemble", final)
    from audit_synth import parse_synth_log, parse_memory_dump
    audit = parse_synth_log(out / "synth.log")
    if audit["unknown_area_cells"]:
        raise SystemExit("Final report still contains unknown-area cells")
    statistics = json.loads((out / "stat.json").read_text())["design"]
    if statistics["num_memories"] or statistics["num_memory_bits"]:
        raise SystemExit("Final netlist still contains memory objects")
    memories = parse_memory_dump(out / "memory_manifest.il")
    parameter_names = ["fe_width", "be_width", "phys_regs", "rob_entries", "outdir",
                       "rs_entries", "lsq_entries", "cache_stats_enabled", "mul_impl",
                       "caches_enabled", "predictor_enabled", "fetch_queue_depth",
                       "completion_depth", "shift_impl", "phys_tag_impl", "generation_width",
                       "checkpoint_impl", "completion_bypass", "serial_backend",
                       "int_issue_width", "cdb_width", "icache_mshrs", "dcache_mshrs", "dcache_lines",
                       "dcache_index_hash", "dcache_request_pipeline", "dcache_ways",
                       "ram_size_bytes", "legacy_sentinel_halt", "icache_lines",
                       "icache_ways"]
    configuration = dict(zip(parameter_names, config))
    configuration.pop("outdir")
    for key in ("cache_stats_enabled", "caches_enabled", "predictor_enabled", "completion_bypass", "serial_backend"):
        configuration[key] = bool(configuration[key])
    report = {
        "format": "synth-area-audit-v1", "status": "COMPLETE", "complete": True,
        "profile": "ff-reference", "mapping": "hierarchical, SAT memory-port optimizations skipped",
        "configuration": configuration,
        "area_um2": audit["top_area_um2_known_cells_only"],
        "area": {"known_standard_cell_um2": audit["top_area_um2_known_cells_only"],
                 "total_um2": audit["top_area_um2_known_cells_only"],
                 "note": "Complete standard-cell total; all source memories expanded by memory_map."},
        "unknown_area_cells": [], "unknown_area_cell_instances": 0, "unmapped_memory_cells": 0,
        "cell_counts": statistics["num_cells_by_type"], "total_cell_instances": statistics["num_cells"],
        "memories": {"count": len(memories), "entries": memories,
                     "bits_with_known_geometry": sum(m["bits"] or 0 for m in memories)},
        "run_manifest": str(manifest_path),
        "note": "All memories including cache data mapped to flip-flops/muxes. Cell area only; excludes physical-design overhead."
    }
    # Reject a run if inputs changed while synthesis was in progress.
    for source, digest in hashes.items():
        if sha(ROOT / source) != digest:
            raise SystemExit("Source changed during run: " + source)
    (out / "area_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"COMPLETE area={report['area_um2']:.6f} um^2", flush=True)


if __name__ == "__main__":
    main()
