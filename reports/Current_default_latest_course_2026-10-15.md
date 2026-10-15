# Current default CPU: latest course assessment, 2026-10-15

| Metric | Measured result |
|---|---:|
| Total area including SRAM | 37981.394558 μm² |
| Six-program IPC geometric mean | 1.115262691835 |
| Estimated maximum frequency | 338.065368 MHz |
| Minimum clock period | 2.9580078125 ns |
| Course Tier3 joint requirements | FAIL |
| Tier3 joint requirements at500MHz | FAIL |

This is the current student_top default configuration, with no parameter
overrides: FE4/BE2, ROB32,
PRF56, RS8, LSQ16, I-cache
128 lines and D-cache1024 lines. Experimental
candidate profiles are not substituted. CPU RTL remains byte-identical to
`8e2448d9ede31c124f2e9d86b5dec96436d3478f`; assessment source freeze is
`fe35375041b7c33719134db1c416346f7954dc36`.

Official framework:
[`302f0cf3`](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/commit/302f0cf3cccdaa5de084a2120e0d950c663e4cf5).
Testcases: `29f980727f7d99a1842a58f34091c7579ba3fe85`. Original build.py, sim.cpp, RAM, synthesis,
STA and testcase scripts are verified against that upstream checkout. The
new ABC buffering/cell-sizing flow uses its default INVx1_ASAP7_75t_R driving
cell,5fF output load and2ns target; no parameter or constraint sweep is used.
OpenSTA reports estimated ideal-clock/no-parasitic timing, not a post-layout
measurement. All SRAM macros are included in the official total area.

## Six original performance programs

| Program | Original dynamic instructions | Measured cycles | IPC |
|---|---:|---:|---:|
| perf_median | 6961 | 7572 | 0.919307976756 |
| perf_multiply | 21722 | 17490 | 1.241966838193 |
| perf_qsort | 139900 | 143485 | 0.975014809910 |
| perf_rsort | 195719 | 153155 | 1.277914531031 |
| perf_towers | 5278 | 4739 | 1.113737075332 |
| perf_vvadd | 4524 | 3725 | 1.214496644295 |

All six original output comparisons pass at latency10. The IPC numerator is
each original metrics.json dynamic_instructions; geometric mean is recomputed
from the exact instruction/cycle ratios. One correctness_array_test1 smoke
also passes. No broad correctness suite or repeated candidate tests are run.

## Reproducibility and platform

The evaluation uses native Windows Yosys/ABC/OpenSTA at the unchanged course
pinned revisions and ASAP7 library hashes, and Verilator5.040. Official build.py
uses the Windows launcher and existing bounded host compiler driver. The only
extra C++ translation unit is the documented Windows timestamp fallback;
original sim.cpp and testcase timing are unmodified. Simulation uses
WORD_SIM1/native_bits1/split_schedule1, stable_MDU0/ICO0/PGO0 and one compiler
worker. PPA and compilation run sequentially to bound memory.

The frozen manifest contains all217 numeric parameter values, source hashes,
tool/library hashes, exact commands and simulator identity. Source/tool/library,
all phase-log, binary and official report hashes verify at publication.
Old A109/Tier1/Tier2 measurements belong to their earlier source/tool freezes;
they are not relabeled as results of this new flow. This assessment does not
adopt a new optimization profile.

Run directory: `F:/CPU2026CourseRuns/default_latest_302f0cf3_20261015`.

[Structured result](Current_default_latest_course_2026-10-15.json) supersedes the dated running observation.
