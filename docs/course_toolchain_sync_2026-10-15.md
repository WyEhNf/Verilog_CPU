# Course toolchain refresh and current default assessment

The official course repository is synchronized to
[`302f0cf3cccdaa5de084a2120e0d950c663e4cf5`](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/commit/302f0cf3cccdaa5de084a2120e0d950c663e4cf5)
(2026-10-14). Its pinned testcase revision remains
`29f980727f7d99a1842a58f34091c7579ba3fe85`. The local dependency checkout,
project Makefile and official scripts are synchronized. CPU RTL is unchanged
from `8e2448d9ede31c124f2e9d86b5dec96436d3478f`.

Relative to the previous54fc150 framework, the upstream code changes are in
Makefile and scripts/synth.py. The new ABC constraints enable buffering and
cell sizing, using INVx1_ASAP7_75t_R and5fF by default. Clock target stays2ns.
OpenSTA constraints and the pinned Yosys/ABC/OpenSTA/ASAP7 revisions are
unchanged. Older PPA results belong to the previous flow and are not reused
as measurements of this updated flow.

The previously adapted local RAM simulation implementation is restored to the
unmodified official sram_fakeram.sv. Official build.py, sim.cpp, testcase.py,
timing scripts, RAM and synthesis scripts are byte-checked against the fetched
upstream checkout when freezing the assessment.

The assessment uses the current student_top parameter defaults, matching the
empty overrides in configs/tier3.json. Experimental policy profiles are not
substituted for that configuration. Record every numeric default and source,
tool, library and testcase hash in an independent snapshot. Run one opt PPA,
the six original perf programs at latency10 and one array1 smoke. This is a
requested measurement: obtain IPC even if area or frequency misses a tier
gate. It does not adopt an optimization candidate or weaken acceptance rules.

Use the existing native Windows pinned synthesis tools and Verilator5.040.
The official builder's --verilator override points to a small Windows launcher
for the existing bounded Python build driver. Original course harness and
memory timing are retained. The additional sc_time_stamp translation unit is
the existing Windows weak-symbol fallback. Simulation options remain
WORD_SIM1/native_bits1/split_schedule1, stable_MDU0/ICO0/PGO0, with one compiler
worker. Record these platform options rather than implying an AppImage/OJ run.

`tools/evaluate_current_course.py prepare --out <fresh-directory>` freezes the
inputs and builds the launcher. Its `run` action performs independent PPA and
build work concurrently, followed by the original six performance programs and
one small correctness point. `check` verifies immutable inputs; `report`
aggregates terminal results without rerunning phases. Existing output
directories and phase records are never overwritten or restarted implicitly.

Status: synchronization complete; updated-flow metrics remain pending until
the frozen official reports and six benchmark results have completed.

## Frozen assessment running

Snapshot `fe353750` retains all217 numeric defaults and no parameter overrides. Actual PPA runner/synthesis/Yosys processes are live. Source, native adapter, tool and library hashes verify. To bound current host memory, the recorded execution is sequential synthesis, build, six perf and one array1 smoke; the optional parallel run action is not used. [Dated progress](../reports/Current_default_latest_course_progress_2026-10-15.json) is not a metric result. The user-requested assessment must finish before further CPU optimization; no old area/IPC/frequency is substituted.
