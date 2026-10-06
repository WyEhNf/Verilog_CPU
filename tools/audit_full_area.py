#!/usr/bin/env python3
"""Independently price every leaf of the fully mapped hierarchical netlist."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from audit_synth import parse_synth_log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--lib-dir", type=Path,
                        help="price against the synthesis run's exact library directory")
    parser.add_argument("--report", type=Path,
                        help="Markdown output; defaults to a report named after the configuration directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.directory.resolve()
    configuration = json.loads((out / "area_audit.json").read_text())["configuration"]
    prices = {}
    libdir = args.lib_dir or root / "_asap7_lib_filtered"
    libraries = sorted(libdir.glob("*.lib"))
    if len(libraries) != 5:
        raise RuntimeError("Exactly five pricing libraries required")
    manifest = json.loads((out / "run_manifest.json").read_text())
    library_hashes = {}
    for path in libraries:
        key = path.resolve().relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest['source_sha256'].get(key) != digest:
            raise RuntimeError("Pricing library differs from frozen synthesis input: " + key)
        library_hashes[key] = digest
    sequential_cells = set()
    for path in libraries:
        text = path.read_text()
        starts = list(re.finditer(r"\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{", text))
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            # The course r28 INVBUF library omits the optional semicolon.
            area = re.search(r"\barea\s*:\s*([\d.eE+-]+)[ \t]*(?:;|\r?\n)", text[match.end():end])
            if area:
                prices[match.group(1)] = Decimal(area.group(1))
                if re.search(r"\b(?:ff|latch)\s*\(", text[match.end():end]):
                    sequential_cells.add(match.group(1))
    modules = {}
    for path in out.glob("mapped_*.il"):
        module = None
        cells = Counter()
        with path.open() as source:
            for line in source:
                if line.startswith("module "):
                    if module is not None:
                        raise RuntimeError("Expected exactly one module: " + str(path))
                    module = line.split()[1].lstrip("\\")
                elif line.startswith("  cell "):
                    cells[line.split()[1].lstrip("\\")] += 1
                elif line.startswith(("  memory ", "  process ")):
                    raise RuntimeError("Unexpanded memory/process: " + str(path))
        if module is None or module in modules:
            raise RuntimeError("Missing/duplicate module: " + str(path))
        modules[module] = cells
    leaves = Counter()
    instances = Counter()

    def visit(module, multiplier=1, stack=()):
        if module in stack:
            raise RuntimeError("Recursive hierarchy: " + module)
        instances[module] += multiplier
        for cell, count in modules[module].items():
            if cell in modules:
                visit(cell, multiplier * count, stack + (module,))
            elif cell in prices:
                leaves[cell] += multiplier * count
            else:
                raise RuntimeError("Unpriced leaf: " + cell)

    visit("cpu_core")
    area = sum((prices[cell] * count for cell, count in leaves.items()), Decimal(0))
    yosys = parse_synth_log(out / "synth.log")
    if yosys["unknown_area_cells"]:
        raise RuntimeError("Yosys reports unknown cells")
    if abs(area - Decimal(str(yosys["top_area_um2_known_cells_only"]))) > Decimal("0.00001"):
        raise RuntimeError("Independent and Yosys area totals disagree")
    for cell, count in leaves.items():
        if yosys["cell_counts"].get(cell) != count:
            raise RuntimeError("Yosys leaf count differs: " + cell)
    rows = []
    for module, count in instances.items():
        own = sum((prices[cell] * n for cell, n in modules[module].items() if cell in prices), Decimal(0))
        rows.append({"module": module, "instances": count,
                     "own_area_each_um2": float(own), "own_area_all_instances_um2": float(own * count)})
    rows.sort(key=lambda row: row["own_area_all_instances_um2"], reverse=True)
    seq = sum((price * leaves[cell] for cell, price in prices.items()
               if cell in sequential_cells), Decimal(0))
    result = {"status": "COMPLETE", "independent_area_um2": float(area),
              "yosys_area_um2": yosys["top_area_um2_known_cells_only"],
              "leaf_instances": sum(leaves.values()), "unpriced_leaf_instances": 0,
              "sequential_area_um2": float(seq), "other_area_um2": float(area - seq),
              "combinational_area_um2": float(area - seq), "sram_area_um2": 0.0,
              "library_directory": str(libdir.resolve()),
              "library_sha256": library_hashes,
              "modules": rows, "leaf_counts": dict(sorted(leaves.items()))}
    (out / "independent_area_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# Fully expanded ASAP7 standard-cell area", "",
             f"Total: **{area:,.6f} µm²**. Independent leaf-cell summation matches Yosys.", "",
             f"Mapped leaf instances: {sum(leaves.values()):,}; unpriced leaves: 0; generic memories: 0.", "",
             "Configuration: " + ", ".join(f"{key}={value}" for key, value in configuration.items()) + ".", "",
             "All storage, including both cache data arrays, is implemented with standard cells. Hierarchy is retained for bounded-memory synthesis; every repeated instance is counted. Optional SAT memory-port priority/sharing optimizations are skipped, preserving original write priorities. This is the measured area of this mapping, not a minimum-area bound. Area excludes placement whitespace, clock-tree synthesis, physical timing repair, and routing. This run does not establish a new timing or IPC result.", "",
             "| Module | Instances | Total own cell area (µm²) | Share |",
             "|---|---:|---:|---:|"]
    for row in rows:
        short = row["module"].split("\\")[-1]
        value = row["own_area_all_instances_um2"]
        lines.append(f"| {short} | {row['instances']} | {value:,.2f} | {100 * value / float(area):.2f}% |")
    lines += ["", f"Sequential cell area: {seq:,.6f} µm²; other cell area: {area - seq:,.6f} µm².", "",
              "Exact synthesis parameters and source hashes are recorded in `run_manifest.json`; per-stage command files are retained alongside the netlist.", "",
              "Evidence: `run_manifest.json`, `synth.log`, `assemble.log`, `cpu_core_synth.v`, and `independent_area_audit.json` in the synthesis output directory.", ""]
    report = args.report or root / "reports" / (out.name + "_area.md")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("modules", "leaf_counts")}, indent=2))


if __name__ == "__main__":
    main()
