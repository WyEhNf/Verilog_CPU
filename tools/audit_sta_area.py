"""Price a memory-free flattened STA netlist, including inserted buffer trees."""
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
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest["memory_boundaries"] or manifest["unhandled_generic_cell_types"]:
        raise SystemExit("Cannot declare complete area with memory/generic boundaries")
    netlist = json.loads(args.netlist_json.read_text())
    counts = Counter(cell["type"] for cell in netlist["modules"][manifest["top"]]["cells"].values())
    if sum(counts.values()) != manifest["standard_or_known_cells"]:
        raise SystemExit("Manifest and input cell counts differ")
    prices = {}
    for path in (Path(__file__).resolve().parents[1] / "_asap7_lib_filtered").glob("*.lib"):
        for name, body in re.findall(r"\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)", path.read_text(), re.S):
            area = re.search(r"\barea\s*:\s*([\d.eE+-]+)", body)
            if area:
                prices[name] = Decimal(area.group(1))
    unknown = set(counts) - prices.keys()
    if unknown:
        raise SystemExit("Unpriced types: " + repr(unknown))
    base = sum((prices[cell] * count for cell, count in counts.items()), Decimal(0))
    buffers = manifest["buffer_tree"]
    buffer_area = prices[buffers["cell"]] * buffers["inserted"]
    result = {"status": "COMPLETE", "flat_standard_cell_area_um2": float(base),
              "buffer_count": buffers["inserted"], "buffer_area_um2": float(buffer_area),
              "timed_netlist_total_area_um2": float(base + buffer_area),
              "total_leaf_instances": sum(counts.values()) + buffers["inserted"],
              "unpriced_leaves": 0, "memory_boundaries": 0,
              "source": str(args.netlist_json), "buffer_manifest": str(args.manifest),
              "note": "Pre-layout standard cells only, with explicitly inserted data-fanout buffers; not a placed/routed die area."}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
