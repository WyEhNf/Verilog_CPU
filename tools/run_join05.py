#!/usr/bin/env python3
"""Elaborate and smoke-test the independent FE/BE/capacity parameter matrix."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


CONFIGS = [
    # Cover every FE/BE width pairing.  Capacity follows backend width so the
    # same run also covers PHYS_REGS={48,64,96} and ROB={16,32,64}.
    (fe, be, {1: 48, 2: 64, 4: 96}[be], {1: 16, 2: 32, 4: 64}[be],
     {1: 8, 2: 8, 4: 16}[be], {1: 8, 2: 8, 4: 16}[be])
    for fe in (1, 2, 4) for be in (1, 2, 4)
]

PROGRAMS = [
    ("accumulate", "build/images/accumulate-rv32i/accumulate.image", 186, 200000),
    ("vvadd", "build/images/vvadd-rv32i/vvadd.image", 72, 300000),
    ("vmul", "build/images/vmul-rv32im/vmul.image", 8, 300000),
]


def run(command, root):
    completed = subprocess.run(command, cwd=str(root), text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, end="")
        raise RuntimeError("command failed with status {}: {}".format(
            completed.returncode, command[0]))
    return completed.stdout or ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iverilog", required=True)
    parser.add_argument("--vvp", required=True)
    parser.add_argument("--report", default="build/join05/report.json")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    results = []

    for fe, be, phys, rob, rs, lsq in CONFIGS:
        name = "fe{}_be{}_p{}_r{}".format(fe, be, phys, rob)
        simulation = root / "build" / "join05" / (name + ".vvp")
        simulation.parent.mkdir(parents=True, exist_ok=True)
        compile_command = [
            args.iverilog, "-g2005", "-Wall", "-I", "rtl",
            "-P", "cpu_core_image_tb.FE_WIDTH={}".format(fe),
            "-P", "cpu_core_image_tb.BE_WIDTH={}".format(be),
            "-P", "cpu_core_image_tb.PHYS_REGS={}".format(phys),
            "-P", "cpu_core_image_tb.ROB_ENTRIES={}".format(rob),
            "-P", "cpu_core_image_tb.RS_ENTRIES={}".format(rs),
            "-P", "cpu_core_image_tb.LSQ_ENTRIES={}".format(lsq),
            "-s", "cpu_core_image_tb", "-o", str(simulation),
            "-c", "rtl/filelist.f", "tb/models/rv32im_memory_model.v",
            "tb/integration/cpu_core_image_tb.v",
        ]
        run(compile_command, root)

        config_result = {
            "config": name, "fe_width": fe, "be_width": be,
            "phys_regs": phys, "rob_entries": rob,
            "rs_entries": rs, "lsq_entries": lsq, "programs": [],
        }
        for program, image, expected, max_cycles in PROGRAMS:
            output = run([
                args.vvp, "-N", str(simulation), "+IMAGE=" + image,
                "+TEST=" + program, "+EXPECTED=" + str(expected),
                "+MAX_CYCLES=" + str(max_cycles),
                "+MAX_NO_RETIRE_CYCLES=100000",
            ], root)
            match = re.search(
                r"PASS: JOIN-02 image={} return={} cycles=(\d+) instret=(\d+)".format(
                    re.escape(program), expected), output)
            if not match:
                print(output, end="")
                raise RuntimeError("{} {} misses PASS marker".format(name, program))
            cycles = int(match.group(1))
            instret = int(match.group(2))
            config_result["programs"].append({
                "name": program, "cycles": cycles, "instret": instret,
                "ipc": round(instret / cycles, 6), "status": "passed",
            })
            print("PASS: JOIN-05 {} {} cycles={} instret={}".format(
                name, program, cycles, instret), flush=True)
        results.append(config_result)

    report = root / args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"format": "join05-v1", "results": results},
                                 indent=2) + "\n", encoding="utf-8")
    print("PASS: JOIN-05 {} configurations, {} executions".format(
        len(results), len(results) * len(PROGRAMS)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print("FAIL: JOIN-05 {}".format(exc), file=sys.stderr)
        sys.exit(1)
