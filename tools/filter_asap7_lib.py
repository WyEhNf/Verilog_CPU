#!/usr/bin/env python3
"""Filter ASAP7 liberty files: drop multi-output cells that corrupt ABC's
liberty->genlib conversion (FAx1 / HAxp5 in the SIMPLE lib).

Writes filtered copies of all five RVT TT NLDM libs into _asap7_lib_filtered/
(workspace root) so the area flow can run without touching third_party/.
"""
import os
import shutil

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

    dst = os.path.join(DST, name)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"{name}: dropped cells {sorted(dropped) if dropped else 'none'} + stripped pg_pin")
