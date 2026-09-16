#!/usr/bin/env python3
"""Merge JOIN performance and ASAP7 synthesis artifacts into one PPA report."""

import argparse
import json
import math
import re
import sys
from pathlib import Path


CONFIGS = (
    ("fe1_be1_p64_r32", "build/join03/report.json",
     "build/synth/join06_fe1_be1_p64_r32_bb"),
    ("fe2_be2_p64_r32", "build/join03/report_w2.json",
     "build/synth/join06_fe2_be2_p64_r32_bb"),
    ("fe4_be4_p96_r64", "build/join03/report_w4.json",
     "build/synth/join06_fe4_be4_p96_r64_bb"),
)


class Join06Error(RuntimeError):
    pass


def load_performance(root, expected_config, relative_path):
    path = root / relative_path
    if not path.is_file():
        raise Join06Error("missing performance report: {}".format(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    config = data.get("config", expected_config)
    if config not in (expected_config, "unspecified"):
        raise Join06Error("{} reports unexpected config {}".format(path, config))
    programs = {}
    for result in data.get("results", []):
        if result.get("status") != "passed":
            raise Join06Error("{} {} did not pass".format(path, result.get("name")))
        if "cycles" not in result or "instret" not in result:
            raise Join06Error("{} has no cycle data; rerun JOIN-03/04".format(path))
        programs[result["name"]] = {
            "cycles": int(result["cycles"]),
            "instret": int(result["instret"]),
            "ipc": round(float(result["instret"]) / float(result["cycles"]), 6),
        }
    if not programs:
        raise Join06Error("{} contains no passed programs".format(path))
    return programs


def load_synthesis(root, relative_dir):
    synth_log = root / relative_dir / "synth.log"
    if not synth_log.is_file():
        raise Join06Error("missing synthesis report: {}".format(synth_log))
    text = synth_log.read_text(encoding="utf-8", errors="replace")
    areas = re.findall(
        r"Chip area for top module '\\cpu_core':\s*([0-9.eE+\-]+)", text)
    if not areas:
        raise Join06Error("top area not found in {}".format(synth_log))
    memory_counts = re.findall(r"^\s*(\d+)\s+-\s+\$mem_v2\s*$", text, re.MULTILINE)
    return {
        "logic_area_um2": float(areas[-1]),
        "unmapped_memory_cells": int(memory_counts[-1]) if memory_counts else None,
        "metric": "ASAP7 logic/flops excluding unmapped memories",
        "report": str(synth_log.relative_to(root)).replace("\\", "/"),
    }


def geometric_mean(values):
    return math.exp(sum(math.log(value) for value in values) / len(values))


def render_markdown(report):
    lines = [
        "# JOIN-06 performance/area summary",
        "",
        "ASAP7 blackbox logic area excludes unmapped `$mem_v2` arrays. The generated",
        "genlib does not provide sign-off timing, so delay/fmax is intentionally reported",
        "as unavailable rather than as a physical timing result.",
        "",
        "| Config | Logic area (um2) | Area ratio | Geo. speedup | Speedup/area |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for config in report["configurations"]:
        lines.append("| {config} | {area:.4f} | {ratio:.4f} | {speedup:.4f} | {eff:.4f} |".format(
            config=config["config"], area=config["synthesis"]["logic_area_um2"],
            ratio=config["area_ratio"], speedup=config["geomean_speedup"],
            eff=config["performance_per_area_ratio"]))
    lines.extend(["", "Per-program results:", "",
                  "| Config | Program | Cycles | IPC | Speedup |",
                  "| --- | --- | ---: | ---: | ---: |"])
    for config in report["configurations"]:
        for name, result in sorted(config["programs"].items()):
            lines.append("| {config} | {name} | {cycles} | {ipc:.6f} | {speedup:.4f} |".format(
                config=config["config"], name=name, cycles=result["cycles"],
                ipc=result["ipc"], speedup=result["speedup"]))
    lines.extend([
        "",
        "The assignment's 1.3x speedup-at-area-growth gate is not marked complete by",
        "this report. SRAM macro area and real STA are still required for final PPA.",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="build/join06/report.json")
    parser.add_argument("--markdown", default="reports/join06_summary.md")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    loaded = []
    for name, perf_path, synth_dir in CONFIGS:
        loaded.append({
            "config": name,
            "programs": load_performance(root, name, perf_path),
            "synthesis": load_synthesis(root, synth_dir),
        })

    baseline = loaded[0]
    baseline_area = baseline["synthesis"]["logic_area_um2"]
    common_programs = set(baseline["programs"])
    for config in loaded[1:]:
        common_programs &= set(config["programs"])
    if not common_programs:
        raise Join06Error("performance reports have no common programs")

    for config in loaded:
        speedups = []
        for name, result in config["programs"].items():
            if name in common_programs:
                result["speedup"] = round(
                    float(baseline["programs"][name]["cycles"]) / result["cycles"], 6)
                speedups.append(result["speedup"])
            else:
                result["speedup"] = None
        config["area_ratio"] = round(
            config["synthesis"]["logic_area_um2"] / baseline_area, 6)
        config["geomean_speedup"] = round(geometric_mean(speedups), 6)
        config["performance_per_area_ratio"] = round(
            config["geomean_speedup"] / config["area_ratio"], 6)
        config["speedup_at_least_1_3"] = config["geomean_speedup"] >= 1.3

    report = {
        "format": "join06-v1",
        "baseline": baseline["config"],
        "common_programs": sorted(common_programs),
        "area_complete": False,
        "timing_available": False,
        "assignment_gate_complete": False,
        "limitations": [
            "unmapped memories have no SRAM macro area",
            "the generated genlib is not a sign-off timing library",
        ],
        "configurations": loaded,
    }
    json_path = root / args.json
    markdown_path = root / args.markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print("PASS: JOIN-06 report configs={} programs={} json={} markdown={}".format(
        len(loaded), len(common_programs), json_path, markdown_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, Join06Error) as exc:
        print("FAIL: JOIN-06 {}".format(exc), file=sys.stderr)
        sys.exit(1)
