"""Price a flattened STA netlist, including inserted buffer trees.

Memory boundaries fail the release gate by default. Exploratory callers may
explicitly request a partial audit; its total remains null, never zero-cost RAM.
"""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist_json", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--allow-memory-boundaries", action="store_true",
                        help="write an INCOMPLETE priced-logic audit with null total")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest["unhandled_generic_cell_types"] or (manifest["memory_boundaries"] and
                                                    not args.allow_memory_boundaries):
        raise SystemExit("Cannot declare complete area with memory/generic boundaries")
    netlist = json.loads(args.netlist_json.read_text())
    all_counts = Counter(cell["type"] for cell in netlist["modules"][manifest["top"]]["cells"].values())
    memory_count = sum(count for cell, count in all_counts.items() if cell.startswith("$mem"))
    if memory_count != manifest["memory_boundaries"]:
        raise SystemExit("Manifest and input memory counts differ")
    counts = Counter({cell: count for cell, count in all_counts.items()
                      if not cell.startswith("$mem")})
    if sum(counts.values()) != manifest["standard_or_known_cells"]:
        raise SystemExit("Manifest and input cell counts differ")
    prices = {}
    sequential = set()
    for path in (Path(__file__).resolve().parents[1] / "_asap7_lib_filtered").glob("*.lib"):
        for name, body in re.findall(r"\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)", path.read_text(), re.S):
            area = re.search(r"\barea\s*:\s*([\d.eE+-]+)", body)
            if area:
                prices[name] = Decimal(area.group(1))
                if re.search(r"\b(?:ff|latch)\s*\(", body):
                    sequential.add(name)
    unknown = set(counts) - prices.keys()
    if unknown:
        raise SystemExit("Unpriced types: " + repr(unknown))
    base = sum((prices[cell] * count for cell, count in counts.items()), Decimal(0))
    buffers = manifest["buffer_tree"]
    buffer_area = prices[buffers["cell"]] * buffers["inserted"]
    sequential_area = sum((prices[cell] * count for cell, count in counts.items()
                           if cell in sequential), Decimal(0))
    complete = memory_count == 0
    result = {"status": "COMPLETE" if complete else "INCOMPLETE",
              "flat_standard_cell_area_um2": float(base),
              "sequential_standard_cell_area_um2": float(sequential_area),
              "combinational_standard_cell_area_um2": float(base - sequential_area + buffer_area),
              "buffer_count": buffers["inserted"], "buffer_area_um2": float(buffer_area),
              "known_timed_standard_cell_area_um2": float(base + buffer_area),
              "timed_netlist_total_area_um2": float(base + buffer_area) if complete else None,
              "sram_area_um2": 0.0 if complete else None,
              "total_leaf_instances": sum(all_counts.values()) + buffers["inserted"],
              "unpriced_leaves": memory_count, "memory_boundaries": memory_count,
              "source": str(args.netlist_json), "buffer_manifest": str(args.manifest),
              "note": "Pre-layout standard cells including explicit data-fanout buffers. Unpriced memory leaves make total/SRAM null; not placed/routed die area."}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
