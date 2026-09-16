#!/usr/bin/env python3
"""Audit a Yosys/ASAP7 area report without treating unknown cells as free.

The synthesis scripts emit a pre-mapping RTLIL dump containing every memory
cell.  This tool combines that inventory with the final ``stat -liberty``
section and writes a machine-readable report.  An incomplete result is still
written successfully so exploratory synthesis remains useful; callers that
need a release gate can pass ``--require-complete``.
"""

import argparse
import json
import re
import sys
from pathlib import Path


class AuditError(RuntimeError):
    pass


def _parse_rtlil_int(value):
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    match = re.fullmatch(r"\d+'([01]+)", value)
    if match:
        return int(match.group(1), 2)
    return None


def parse_memory_dump(path):
    if not path.is_file():
        raise AuditError("missing memory dump: {}".format(path))

    memories = []
    module = None
    current = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        module_match = re.match(r"module\s+(\S+)", line)
        if module_match:
            module = module_match.group(1).lstrip("\\")
            continue
        cell_match = re.match(r"cell\s+(\$mem\S*)\s+(\S+)", line)
        if cell_match:
            current = {
                "module": module,
                "cell": cell_match.group(2).lstrip("\\"),
                "type": cell_match.group(1),
                "parameters": {},
            }
            continue
        if current is None:
            continue
        parameter_match = re.match(r"parameter(?:\s+signed)?\s+\\?(\S+)\s+(.+)", line)
        if parameter_match:
            name = parameter_match.group(1)
            if name in ("WIDTH", "SIZE", "ABITS", "RD_PORTS", "WR_PORTS"):
                current["parameters"][name] = _parse_rtlil_int(parameter_match.group(2))
            continue
        if line == "end":
            params = current.pop("parameters")
            current.update({name.lower(): params.get(name) for name in (
                "WIDTH", "SIZE", "ABITS", "RD_PORTS", "WR_PORTS")})
            width = current.get("width")
            size = current.get("size")
            current["bits"] = width * size if width is not None and size is not None else None
            memories.append(current)
            current = None

    return memories


def _final_hierarchy_block(text):
    starts = [match.start() for match in re.finditer(
        r"^=== design hierarchy ===\s*$", text, re.MULTILINE)]
    if not starts:
        raise AuditError("final design hierarchy section not found")
    return text[starts[-1]:]


def parse_synth_log(path):
    if not path.is_file():
        raise AuditError("missing synthesis log: {}".format(path))
    text = path.read_text(encoding="utf-8", errors="replace")
    block = _final_hierarchy_block(text)

    area_match = re.search(
        r"Chip area for top module '\\cpu_core':\s*([0-9.eE+\-]+)", block)
    if not area_match:
        raise AuditError("top cpu_core area not found in {}".format(path))

    cell_counts = {}
    for match in re.finditer(
            r"^\s*(\d+)\s+(?:-|[0-9.eE+\-]+)\s+([^\s]+)\s*$", block, re.MULTILINE):
        cell_counts[match.group(2).lstrip("\\")] = int(match.group(1))

    unknown_types = []
    for match in re.finditer(r"Area for cell type (\S+) is unknown!", block):
        cell_type = match.group(1).lstrip("\\")
        if cell_type not in unknown_types:
            unknown_types.append(cell_type)

    return {
        "top_area_um2_known_cells_only": float(area_match.group(1)),
        "cell_counts": cell_counts,
        "unknown_area_cells": [
            {"type": cell_type, "count": cell_counts.get(cell_type)}
            for cell_type in unknown_types
        ],
    }


def build_report(args):
    synthesis = parse_synth_log(Path(args.synth_log))
    memories = parse_memory_dump(Path(args.memory_dump))
    memory_bits = [entry["bits"] for entry in memories if entry["bits"] is not None]
    unknown_count = sum(
        entry["count"] for entry in synthesis["unknown_area_cells"]
        if entry["count"] is not None)
    # In the ff-reference flow memory_manifest.il records the source array
    # shapes before memory_map; those arrays are subsequently implemented by
    # standard cells and are already included in the final hierarchy area.
    # They are unpriced black boxes only in the logic-blackbox profile.
    complete = not synthesis["unknown_area_cells"] and (
        args.profile == "ff-reference" or not memories)
    known_area = synthesis["top_area_um2_known_cells_only"]

    return {
        "format": "synth-area-audit-v1",
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "profile": args.profile,
        "configuration": {
            "fe_width": args.fe_width,
            "be_width": args.be_width,
            "phys_regs": args.phys_regs,
            "rob_entries": args.rob_entries,
            "rs_entries": args.rs_entries,
            "lsq_entries": args.lsq_entries,
            "cache_stats_enabled": bool(args.cache_stats),
            "caches_enabled": bool(args.caches),
            "predictor_enabled": bool(args.predictor),
            "fetch_queue_depth": args.fetch_queue_depth,
            "completion_depth": args.completion_depth,
            "completion_bypass": bool(args.completion_bypass),
            "serial_backend": bool(args.serial_backend),
            "mul_impl": args.mul_impl,
            "shift_impl": args.shift_impl,
            "phys_tag_impl": args.phys_tag_impl,
            "generation_width": args.generation_width,
            "checkpoint_impl": args.checkpoint_impl,
        },
        "area": {
            "known_standard_cell_um2": known_area,
            "total_um2": known_area if complete else None,
            "note": (
                "Complete standard-cell total; source memories were expanded by memory_map."
                if complete and args.profile == "ff-reference" else
                "Known-area cells only; total remains null until every generic cell and memory has an implementation."
            ),
        },
        "unknown_area_cells": synthesis["unknown_area_cells"],
        "unknown_area_cell_instances": unknown_count,
        "memories": {
            "count": len(memories),
            "bits_with_known_geometry": sum(memory_bits),
            "entries": memories,
        },
        "complete": complete,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth-log", required=True)
    parser.add_argument("--memory-dump", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", choices=("logic-blackbox", "ff-reference"), required=True)
    parser.add_argument("--fe-width", type=int, required=True)
    parser.add_argument("--be-width", type=int, required=True)
    parser.add_argument("--phys-regs", type=int, required=True)
    parser.add_argument("--rob-entries", type=int, required=True)
    parser.add_argument("--rs-entries", type=int, required=True)
    parser.add_argument("--lsq-entries", type=int, required=True)
    parser.add_argument("--cache-stats", type=int, choices=(0, 1), default=0)
    parser.add_argument("--caches", type=int, choices=(0, 1), default=1)
    parser.add_argument("--predictor", type=int, choices=(0, 1), default=1)
    parser.add_argument("--fetch-queue-depth", type=int, default=16)
    parser.add_argument("--completion-depth", type=int, default=4)
    parser.add_argument("--completion-bypass", type=int, choices=(0, 1), default=0)
    parser.add_argument("--serial-backend", type=int, choices=(0, 1), default=0)
    parser.add_argument("--mul-impl", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument("--shift-impl", type=int, choices=(0, 1), default=0)
    parser.add_argument("--phys-tag-impl", type=int, choices=(0, 1), default=0)
    parser.add_argument("--generation-width", type=int, default=8)
    parser.add_argument("--checkpoint-impl", type=int, choices=(0, 1), default=0)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("{}: synthesis area audit known_area={:.6f} unknown_cells={} memories={} bits={} report={}".format(
        report["status"], report["area"]["known_standard_cell_um2"],
        report["unknown_area_cell_instances"], report["memories"]["count"],
        report["memories"]["bits_with_known_geometry"], output))
    if args.require_complete and not report["complete"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AuditError, OSError, ValueError) as exc:
        print("FAIL: synthesis area audit: {}".format(exc), file=sys.stderr)
        sys.exit(1)
