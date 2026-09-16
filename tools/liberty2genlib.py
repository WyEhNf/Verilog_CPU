#!/usr/bin/env python3
"""Convert (already filtered) ASAP7 combinational liberty files into a SIS
genlib for ABC's classic `map` mapper, bypassing ABC's broken liberty->genlib
conversion.

Inputs : _asap7_lib_filtered/*.lib (pg_pin stripped, FA/HA removed)
Output : _asap7_lib_filtered/asap7_comb.genlib
Area is scaled x10000 only to form ABC's integer optimization cost.  Physical
area reports come from ``stat -liberty`` and must not be divided by 10000.
Only single-output combinational cells are emitted.
"""
import os
import re

SRC = "_asap7_lib_filtered"
OUT = os.path.join(SRC, "asap7_comb.genlib")

COMB_LIBS = [
    "asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_AO_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_OA_RVT_TT_nldm_201020.lib",
]

cell_re = re.compile(r"^\s*cell\s*\(\s*([^\s)]+)\s*\)\s*\{", re.M)
area_re = re.compile(r"^\s*area\s*:\s*([0-9.eE+-]+)\s*;", re.M)
pin_block_re = re.compile(r"^\s*pin\s*\(\s*([^\s)]+)\s*\)\s*\{", re.M)
dir_re = re.compile(r"^\s*direction\s*:\s*(\w+)\s*;", re.M)
func_re = re.compile(r'^\s*function\s*:\s*"([^"]+)"\s*;', re.M)


def find_matching_brace(text, open_idx):
    depth = 0
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


# Clock-tree / non-logic cells that must not be emitted as normal gates.
# TIEHI/TIELO are intentionally retained so constants are mapped to priced,
# real ASAP7 cells instead of synthetic ZERO/ONE black boxes.
EXCLUDE_PREFIX = ("CKINVDC", "HB")


def parse_cells(text):
    cells = []
    i = 0
    while True:
        m = cell_re.search(text, i)
        if not m:
            break
        open_idx = text.index("{", m.start())
        close_idx = find_matching_brace(text, open_idx)
        body = text[open_idx + 1:close_idx]
        cells.append((m.group(1), body))
        i = close_idx + 1
    return cells


gates = []
for lib in COMB_LIBS:
    with open(os.path.join(SRC, lib), encoding="utf-8") as f:
        text = f.read()
    for name, body in parse_cells(text):
        if name.startswith(EXCLUDE_PREFIX):
            continue
        am = area_re.search(body)
        if not am:
            continue
        area = float(am.group(1))
        outputs = []
        for pm in pin_block_re.finditer(body):
            po = body.index("{", pm.start())
            pc = find_matching_brace(body, po)
            pbody = body[po + 1:pc]
            if dir_re.search(pbody) and dir_re.search(pbody).group(1) == "output":
                fm = func_re.search(pbody)
                if fm:
                    outputs.append((pm.group(1), fm.group(1)))
        if len(outputs) != 1:
            continue
        output_pin, expr = outputs[0]
        area_i = max(1, int(round(area * 10000)))
        phase = "NONINV" if not expr.lstrip().startswith("!") else "INV"
        genlib_expr = {"0": "CONST0", "1": "CONST1"}.get(expr, expr)
        gate = f"GATE {name} {area_i} {output_pin}={genlib_expr};"
        if expr not in ("0", "1"):
            gate += f" PIN * {phase} 1 999 1 0 1 0"
        gates.append(gate)

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(gates) + "\n")

print(f"wrote {OUT}: {len(gates)} gates")
