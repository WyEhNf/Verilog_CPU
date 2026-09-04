#!/usr/bin/env python3
"""Convert (already filtered) ASAP7 combinational liberty files into a SIS
genlib for ABC's classic `map` mapper, bypassing ABC's broken liberty->genlib
conversion.

Inputs : _asap7_lib_filtered/*.lib (pg_pin stripped, FA/HA removed)
Output : _asap7_lib_filtered/asap7_comb.genlib
Area scaled x10000 into integer genlib cost; divide reports by 10000.
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


# Clock-tree / non-logic / tie cells that must not be emitted as normal gates.
EXCLUDE_PREFIX = ("CKINVDC", "HB", "TIEHI", "TIELO")


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
                    outputs.append(fm.group(1))
        if len(outputs) != 1:
            continue
        expr = outputs[0]
        area_i = max(1, int(round(area * 10000)))
        phase = "NONINV" if not expr.lstrip().startswith("!") else "INV"
        gates.append(f"GATE {name} {area_i} Y={expr}; PIN * {phase} 1 999 1 0 1 0")

# Guarantee a buffer and inverter for the mapper, with realistic ASAP7 areas
# (INVx1 = 0.69984 -> 6998, BUFx2 = 1.1664 -> 11664) so they are never the
# pathological cheapest choice.
gates.insert(0, "GATE BUF 11664 Y=A; PIN * NONINV 1 999 1 0 1 0")
gates.insert(0, "GATE NOT 6998 Y=!A; PIN * INV 1 999 1 0 1 0")
# Constant gates (ASAP7 TIEHIx1/TIELOx1, area 0.04374 -> 437) required by `map`.
# Note: zero-input gates have no PIN line.
gates.insert(0, "GATE ONE 437 Y=CONST1;")
gates.insert(0, "GATE ZERO 437 Y=CONST0;")

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(gates) + "\n")

print(f"wrote {OUT}: {len(gates)} gates")
