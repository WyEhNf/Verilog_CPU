#!/usr/bin/env python3
"""Prepare the ASAP7 liberty files used by the auditable area flow.

Besides removing constructs that old ABC cannot read, normalize the INVBUF
cell areas.  That liberty file carries areas exactly 16 times larger than the
official 1x LEF footprints (for example INVx1 is 0.69984 instead of
0.162*0.270 = 0.04374 um^2).  All other libraries already agree with LEF.

Writes filtered copies of all five RVT TT NLDM libs into _asap7_lib_filtered/
(workspace root) so the area flow can run without touching third_party/.
"""
import os
import re
from decimal import Decimal

SRC = "third_party/asap7/lib"
DST = "_asap7_lib_filtered"
os.makedirs(DST, exist_ok=True)

LIBS = [
    "asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_AO_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_OA_RVT_TT_nldm_201020.lib",
    "asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib",
]
DROP = {"FAx1_ASAP7_75t_R", "HAxp5_ASAP7_75t_R"}
INVBUF_LIB = "asap7sc7p5t_INVBUF_RVT_TT_nldm_201020.lib"
INVBUF_AREA_SCALE = Decimal("16")


def normalize_invbuf_areas(text):
    """Return LEF-footprint areas for every cell in the INVBUF liberty."""
    pattern = re.compile(
        r"(^\s*cell\s*\([^\n]+\)\s*\{\s*\n\s*area\s*:\s*)"
        r"([0-9.eE+-]+)(\s*;)",
        re.MULTILINE,
    )

    def replace(match):
        area = Decimal(match.group(2)) / INVBUF_AREA_SCALE
        normalized = format(area.normalize(), "f")
        return match.group(1) + normalized + match.group(3)

    return pattern.subn(replace, text)

for name in LIBS:
    src = os.path.join(SRC, name)
    with open(src, encoding="utf-8") as f:
        lines = f.read().splitlines()
    out = []
    i = 0
    dropped = set()
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        # Drop multi-output cells that corrupt ABC's genlib conversion.
        if s.startswith("cell ("):
            cell = s[len("cell ("):].split(")")[0].strip()
            if cell in DROP:
                depth = 0
                j = i
                while j < len(lines):
                    depth += lines[j].count("{") - lines[j].count("}")
                    j += 1
                    if depth == 0:
                        break
                dropped.add(cell)
                i = j
                continue
        # Drop pg_pin (power/ground) blocks: older ABC genlib conversion
        # cannot classify cells that carry them.
        if s.startswith("pg_pin ("):
            depth = 0
            j = i
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                j += 1
                if depth == 0:
                    break
            i = j
            continue
        out.append(line)
        i += 1

    text = "\n".join(out) + "\n"
    normalized = 0
    if name == INVBUF_LIB:
        text, normalized = normalize_invbuf_areas(text)

    dst = os.path.join(DST, name)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    suffix = f" + normalized {normalized} INVBUF areas /16" if normalized else ""
    print(f"{name}: dropped cells {sorted(dropped) if dropped else 'none'} + stripped pg_pin{suffix}")
