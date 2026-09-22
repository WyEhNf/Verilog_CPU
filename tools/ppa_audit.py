#!/usr/bin/env python3
"""Assemble the saved large-configuration CPU-2026/Yosys/ASAP7 snapshots."""

import argparse
import json
import re
from pathlib import Path


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def chip_area(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"Chip area for module '\\cpu_core':\s*([0-9.eE+\-]+)", text)
    if not matches:
        raise RuntimeError("cpu_core area missing from {}".format(path))
    return float(matches[-1])


def cell_area(path, cell):
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"cell\s*\(" + re.escape(cell) + r"\)\s*\{.*?\barea\s*:\s*([0-9.eE+\-]+)\s*;",
        text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError("area for {} missing from {}".format(cell, path))
    return float(match.group(1))


def timing_summary(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    units = re.search(r"AUDIT time_unit=ps capacitance_unit=fF clock_period_ps=([0-9.eE+\-]+) uncertainty_ps=([0-9.eE+\-]+)", text)
    if not units or abs(float(units.group(1)) - 1_000_000 / 300) > 0.001:
        raise RuntimeError("Timing report lacks verified 300 MHz / ps constraints: {}".format(path))
    match = re.search(r"period_min\s*=\s*([0-9.eE+\-]+)\s+fmax\s*=\s*([0-9.eE+\-]+)", text)
    wns = re.search(r"wns\s+max\s+([0-9.eE+\-]+)", text)
    if not match:
        raise RuntimeError("timing summary missing from {}".format(path))
    return {
        "minimum_period_ns": float(match.group(1)) / 1000.0,
        "fmax_mhz": float(match.group(2)),
        "wns_ns": (float(wns.group(1)) / 1000.0) if wns else None,
        "clock_period_ns": float(units.group(1)) / 1000.0,
        "clock_uncertainty_ns": float(units.group(2)) / 1000.0,
    }


def yosys_binary_int(value):
    value = str(value).strip()
    if re.fullmatch(r"[01]+", value):
        return int(value, 2)
    return int(value, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    area_report_path = root / "build/synth/p4_i16_d32k_bitmap_fastbb_bb/area_audit.json"
    ipc_report_path = root / "build/cpu2026/report_p4_i16_d32k_l20.json"
    full_area_path = root / "build/synth/p4_i16_d32k_full/area_audit.json"
    flat_area_path = root / "build/timing/p4_i16_d32k_bitmap_fastbb/sta_logic_area.log"
    timing_path = root / "build/timing/p4_i16_d32k_bitmap_fastbb/timing_300mhz_buf16_unitsfixed.rpt"
    boundary_path = root / "build/timing/p4_i16_d32k_bitmap_fastbb/memory_boundaries_buf16.json"

    area_report = load_json(area_report_path)
    ipc_report = load_json(ipc_report_path)
    full_area = load_json(full_area_path)
    if not full_area["complete"] or full_area["unknown_area_cell_instances"]:
        raise RuntimeError("Full standard-cell area is incomplete")
    for result in ipc_report["results"]:
        if result.get("memory", {}).get("latency_cycles") != 20 or result["memory"].get("unified") != 1:
            raise RuntimeError("Benchmark lacks the required unified, 20-cycle memory evidence")
    boundaries = load_json(boundary_path)
    flat_logic_area = chip_area(flat_area_path)
    timing = timing_summary(timing_path)

    filtered_inv = root / "_asap7_lib_filtered/asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib"
    buffer_cell = boundaries["buffer_tree"]["cell"]
    buffer_unit_area = cell_area(filtered_inv, buffer_cell)
    buffer_count = boundaries["buffer_tree"]["inserted"]
    buffer_area = buffer_count * buffer_unit_area

    d_sram_area = 4 * cell_area(
        root / "third_party/asap7/sram_0p0/generated/LIB/srambank_256x4x64_6t122.lib",
        "srambank_256x4x64_6t122",
    )
    i_sram_area = 2 * cell_area(
        root / "third_party/asap7/sram_0p0/generated/LIB/srambank_64x4x64_6t122.lib",
        "srambank_64x4x64_6t122",
    )
    cache_sram_area = d_sram_area + i_sram_area

    source_manifest_bits = area_report["memories"]["bits_with_known_geometry"]
    memory_bits = sum(
        yosys_binary_int(memory["parameters"]["WIDTH"])
        * yosys_binary_int(memory["parameters"]["SIZE"])
        for memory in boundaries["memories"]
    )
    cache_data_bits = 2048 * 128 + 64 * 128
    non_cache_data_bits = memory_bits - cache_data_bits
    dff_bit_area = 0.2916  # DFFHQNx1_ASAP7_75t_R in normalized ASAP7 liberty.
    non_cache_storage_floor = non_cache_data_bits * dff_bit_area
    hybrid_floor = flat_logic_area + cache_sram_area + non_cache_storage_floor
    buffered_hybrid_floor = hybrid_floor + buffer_area
    all_dff_storage_floor = flat_logic_area + memory_bits * dff_bit_area

    aggregate_ipc = ipc_report["aggregate_ipc"]
    all_benchmarks_pass = all(item["status"] == "passed" for item in ipc_report["results"])
    stage_rows = [
        {"stage": 1, "max_area_um2": 10000.0, "min_ipc": 0.6000},
        {"stage": 2, "max_area_um2": 20000.0, "min_ipc": 0.7800},
        {"stage": 3, "max_area_um2": 40000.0, "min_ipc": 1.0140},
    ]
    competition_area = area_report["area"]["known_standard_cell_um2"]
    full_area_um2 = full_area["area"]["total_um2"]
    for row in stage_rows:
        row["area_basis"] = "complete standard-cell reference; external main memory excluded"
        row["area_pass"] = full_area_um2 <= row["max_area_um2"]
        row["ipc_pass"] = aggregate_ipc >= row["min_ipc"]
        row["frequency_pass"] = timing["fmax_mhz"] >= 300.0
        row["overall_pass"] = row["area_pass"] and row["ipc_pass"] and row["frequency_pass"]

    largest_memories = sorted(
        area_report["memories"]["entries"], key=lambda entry: entry.get("bits") or 0, reverse=True
    )[:15]

    report = {
        "format": "cpu-ppa-audit-v1",
        "configuration": area_report["configuration"],
        "ipc": {
            "tool": "Verilator RTL",
            "all_six_pass": all_benchmarks_pass,
            "aggregate_ipc": aggregate_ipc,
            "total_cycles": ipc_report["total_cycles"],
            "total_instret": ipc_report["total_instret"],
            "results": ipc_report["results"],
            "source": str(ipc_report_path),
            "memory": ipc_report["results"][0]["memory"],
            "memory_interface_note": "One backing store; independent I/D request queues. The provided rules do not specify port count or bandwidth.",
        },
        "area": {
            "tool": "Yosys + ASAP7 7.5T RVT TT",
            "competition_logic_blackbox_um2": competition_area,
            "competition_status": area_report["status"],
            "flattened_logic_um2": flat_logic_area,
            "source_manifest_memory_definitions": area_report["memories"]["count"],
            "source_manifest_bits": source_manifest_bits,
            "flattened_memory_boundaries": boundaries["memory_boundaries"],
            "flattened_memory_bits": memory_bits,
            "hierarchical_unknown_memory_occurrences": area_report["unknown_area_cell_instances"],
            "cache_data_sram_macro_um2": cache_sram_area,
            "non_cache_storage_dff_floor_um2": non_cache_storage_floor,
            "hybrid_physical_floor_um2": hybrid_floor,
            "fanout_buffer_count": buffer_count,
            "fanout_buffer_area_um2": buffer_area,
            "timing_repaired_hybrid_floor_um2": buffered_hybrid_floor,
            "all_dff_storage_floor_um2": all_dff_storage_floor,
            "complete_total_um2": full_area_um2,
            "complete": True,
            "complete_profile": "ff-reference (all internal memories implemented as standard cells)",
            "complete_source": str(full_area_path),
            "blackbox_scoring_approved": False,
            "largest_memories": largest_memories,
            "source": str(area_report_path),
        },
        "timing": {
            "tool": "OpenSTA 3.1.0 + ASAP7 RVT TT NLDM",
            "clock_target_mhz": 300.0,
            "clock_period_ns": 3.333,
            "clock_uncertainty_ns": 0.100,
            "coverage": "standard-cell paths only; 134 generic memory boundaries have no timing arcs",
            "buffer_tree": boundaries["buffer_tree"],
            **timing,
            "pass": timing["fmax_mhz"] >= 300.0,
            "critical_region": "ROB recovery/redirect -> backend/RS issue select -> lane-3 ALU input/output register",
            "source": str(timing_path),
        },
        "stages": stage_rows,
        "overall": {
            "achieved": any(row["overall_pass"] for row in stage_rows),
            "highest_stage": max((row["stage"] for row in stage_rows if row["overall_pass"]), default=0),
            "blocking_requirements": [
                "300 MHz timing is not met (measured {:.2f} MHz on already-buffered standard-cell paths).".format(timing["fmax_mhz"]),
                "The complete standard-cell reference area is {:.2f} um^2, above all area limits.".format(full_area_um2),
                "Timing still covers the prior memory-blackbox netlist, not the newly fully expanded netlist.",
            ],
        },
    }

    json_output = args.json_output or root / "build/audit/ppa_audit.json"
    markdown_output = args.markdown_output or root / "reports/ppa_audit_2026-09-22.md"
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# CPU PPA audit: large-configuration reference snapshots (2026-09-22)",
        "",
        "## Verdict",
        "",
        "These saved large-configuration snapshots do **not** satisfy any scoring stage because the 300 MHz gate is not met. "
        "The six CPU-2026 tests pass and aggregate IPC is {:.6f}, but the best audited standard-cell timing variant reaches only {:.2f} MHz.".format(
            aggregate_ipc, timing["fmax_mhz"]),
        "These measurements predate the retired-load LSQ repair. See `evaluation_alignment_2026-09-22.md` for the newer experiments; do not combine snapshots from different RTL versions as proof of qualification.",
        "",
        "## Evidence",
        "",
        "| Item | Result | Status |",
        "|---|---:|---|",
        "| CPU-2026 aggregate IPC | {:.6f} | PASS for stage 3 |".format(aggregate_ipc),
        "| Six benchmark correctness | 6/6 | PASS |",
        "| Complete standard-cell reference area | {:.2f} um^2 | FAIL all area stages; external main memory excluded |".format(full_area_um2),
        "| Historical blackbox logic area | {:.2f} um^2 | Incomplete; not established as an official score |".format(competition_area),
        "| Flattened standard-cell logic area | {:.2f} um^2 | 134 memories excluded |".format(flat_logic_area),
        "| Buffered logic area | {:.2f} um^2 | under 40k, memories excluded |".format(flat_logic_area + buffer_area),
        "| OpenSTA Fmax | {:.2f} MHz | **FAIL** (target 300 MHz) |".format(timing["fmax_mhz"]),
        "| Optimistic hybrid physical floor | {:.2f} um^2 | exceeds 40k; still excludes port/decode overhead |".format(hybrid_floor),
        "| Buffered hybrid physical floor | {:.2f} um^2 | exceeds 40k |".format(buffered_hybrid_floor),
        "",
        "## Area interpretation",
        "",
        "The complete all-standard-cell reference is {:.2f} um^2, with no unpriced leaves or generic memories. The stage table uses this complete figure. Cache-storage exemption is not inferred from the main-memory exemption; a different permitted memory mapping must be assessed separately.".format(full_area_um2),
        "",
        "The {:.2f} um^2 headline is not a complete chip area. It prices ASAP7 standard cells while the flattened timing inventory still has {} live `$mem_v2` boundaries ({} bits) unpriced. "
        "Two cache data arrays need {:.2f} um^2 of characterized SRAM macros. Pricing the remaining {} bits at only one DFF per bit adds {:.2f} um^2 before address decode, read muxes, write priority, banking, replication, or routing. "
        "That produces an optimistic hybrid floor of {:.2f} um^2, not a final total.".format(
            competition_area, boundaries["memory_boundaries"], memory_bits,
            cache_sram_area, non_cache_data_bits, non_cache_storage_floor, hybrid_floor),
        "",
        "## Timing interpretation",
        "",
        "OpenSTA uses the unmodified ASAP7 RVT TT NLDM libraries, a 3.333 ns clock and 0.100 ns uncertainty. "
        "A balanced BUFx8 tree limits data fanout to 16 and adds {} buffers ({:.2f} um^2). "
        "Even then the minimum period is {:.3f} ns ({:.2f} MHz), with the critical region running from ROB recovery/redirect through backend and reservation-station selection into ALU lane 3. "
        "Because this is an actual violating standard-cell path, unmodelled memory timing cannot turn the result into a pass.".format(
            buffer_count, buffer_area, timing["minimum_period_ns"], timing["fmax_mhz"]),
        "",
        "## Stage audit",
        "",
        "| Stage | Area | IPC | 300 MHz | Overall |",
        "|---:|---|---|---|---|",
    ]
    for row in stage_rows:
        lines.append("| {} | {} | {} | {} | {} |".format(
            row["stage"], "PASS" if row["area_pass"] else "FAIL",
            "PASS" if row["ipc_pass"] else "FAIL",
            "PASS" if row["frequency_pass"] else "FAIL",
            "PASS" if row["overall_pass"] else "FAIL"))
    lines.extend([
        "",
        "## Required corrective work",
        "",
        "1. Insert a real registered issue stage (or otherwise split the ROB/RS-to-ALU path); buffer sizing alone improves Fmax only to about 40 MHz.",
        "2. Consolidate cache data-array writes to one physical SRAM port and bind those arrays to the characterized ASAP7 macros.",
        "3. Reduce the now-measured ROB/RS/LSQ/PRF control and multi-port costs; keep every internal structure accounted for.",
        "4. Re-run Verilator CPU-2026, Yosys area, and full OpenSTA after those architectural changes.",
        "",
    ])
    markdown_output.write_text("\n".join(lines), encoding="utf-8")
    print("wrote {} and {}".format(json_output, markdown_output))


if __name__ == "__main__":
    main()
