#!/usr/bin/env python3
"""Optimistic ASAP7 sram_0p0 packing scenario; not the grading FakeRAM score.

This ignores read/write port replication, banking conflicts, muxes, adapters,
and timing. Per-array width padding and potential cross-array packing are also
not modeled, so this is not a rigorous mathematical bound. It is useful only
for screening storage-area pressure, never for declaring a complete area.
"""

import argparse
import json
import math
import re
from pathlib import Path


def physical_memories(manifest):
    entries = []
    for memory in manifest['memories']:
        params = memory['parameters']
        width, size, reads, writes = (
            int(params[name], 2) for name in ('WIDTH', 'SIZE', 'RD_PORTS', 'WR_PORTS'))
        if width <= 0 or size <= 0 or reads < 0 or writes < 0:
            raise ValueError('invalid physical memory geometry')
        entries.append(dict(cell=memory['instance'], width=width, size=size,
                            bits=width * size, rd_ports=reads, wr_ports=writes))
    if len(entries) != manifest['memory_boundaries']:
        raise ValueError('physical memory boundary count mismatch')
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--lib-dir", type=Path,
                        default=Path("third_party/asap7/sram_0p0/generated/LIB"))
    parser.add_argument('--boundary-manifest', type=Path,
                        help='use expanded physical instances instead of source definitions')
    parser.add_argument('--logic-area-um2', type=float,
                        help='explicit same-version known logic plus buffers for the scenario')
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    macros = []
    for path in sorted(args.lib_dir.glob("srambank_*_6t122.lib")):
        shape = re.fullmatch(r"srambank_(\d+)x(\d+)x(\d+)_6t122\.lib", path.name)
        if not shape:
            continue
        area_match = re.search(r"\barea\s*:\s*([0-9.]+)\s*;", path.read_text(encoding="utf-8"))
        if not area_match:
            continue
        rows, banks, width = map(int, shape.groups())
        macros.append((rows * banks, width, float(area_match.group(1)), path.stem))
    if not macros:
        raise SystemExit("No local SRAM LIB macros found")

    def optimistic_footprint(depth, width):
        candidates = [m for m in macros if m[0] >= depth]
        if not candidates:
            return None
        best = [(math.inf, ()) for _ in range(width + 1)]
        best[0] = (0.0, ())
        for covered in range(width):
            if not math.isfinite(best[covered][0]):
                continue
            for macro in candidates:
                new_width = min(width, covered + macro[1])
                cost = best[covered][0] + macro[2]
                if cost < best[new_width][0]:
                    best[new_width] = (cost, best[covered][1] + (macro[3],))
        return best[width]

    memories = (physical_memories(json.loads(args.boundary_manifest.read_text(encoding='utf-8')))
                if args.boundary_manifest else audit["memories"]["entries"])
    large = sorted(memories, key=lambda item: item["bits"], reverse=True)[:3]
    floor = sum(optimistic_footprint(int(m["size"]), int(m["width"]))[0] for m in large)
    remaining_bits = sum(int(m["bits"]) for m in memories) - sum(int(m["bits"]) for m in large)
    best_density = min(m[2] / (m[0] * m[1]) for m in macros)
    logic = (args.logic_area_um2 if args.logic_area_um2 is not None else
             float(audit["area"]["known_standard_cell_um2"]))
    if not math.isfinite(logic) or logic <= 0:
        raise SystemExit('known logic area must be finite and positive')
    print('memory_inventory_scope=' + ('expanded_logical_instances_not_macro_count' if args.boundary_manifest else
                                       'definition_geometry_not_instance_total'))
    print(f'memory_instances_or_definitions={len(memories)}')
    print(f'memory_bits={sum(int(m["bits"]) for m in memories)}')
    print(f"known_logic_um2={logic:.6f}")
    print(f"tier3_storage_budget_um2={36000.0 - logic:.6f}")
    for memory in large:
        cost, chosen = optimistic_footprint(int(memory["size"]), int(memory["width"]))
        print(f"large_memory={memory['cell']} {memory['size']}x{memory['width']} "
              f"rd={memory['rd_ports']} wr={memory['wr_ports']} "
              f"ideal_macro_um2={cost:.6f} macros={','.join(chosen)}")
    print(f"top3_ideal_macro_um2={floor:.6f}")
    print(f"remaining_memory_bits={remaining_bits}")
    print(f"best_library_density_um2_per_bit={best_density:.8f}")
    print(f"top3_plus_ideal_remaining_um2={floor + remaining_bits * best_density:.6f}")
    print("WARNING: illustrative scenario, not a rigorous bound or FakeRAM; "
          "ignores ports, replication, cross-array packing, adapters, and timing")


if __name__ == "__main__":
    main()
