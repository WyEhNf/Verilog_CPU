# Parameterized RV32IM Out-of-Order CPU

The current default RTL is A109: an out-of-order RV32IM core with register renaming, a ROB for in-order commit, instruction/data caches, and the course AXI4-Lite interface. It implements byte, halfword, and word loads/stores and all eight M-extension operations. The top module is `student_top`, listed in `verilog/filelist.f`.

## Course submission entry

The root `Makefile` and all files under `scripts/` are unchanged copies of the official course framework at commit `54fc150ffc290f52aa024209ffb9a29d43856f6d`. Their hashes and origin are recorded in [third_party/cpu2026-framework.json](third_party/cpu2026-framework.json). `config.mk` adds a portable host compilation profile to the official template. The official `testcases` submodule is pinned to `29f980727f7d99a1842a58f34091c7579ba3fe85` and uses a public HTTPS URL.

Use the OJ's **Git repository** submission mode with the repository URL. According to [ACMOJ's official submission help](https://acm.sjtu.edu.cn/OnlineJudge/help/view-submit-and-judge-problems), it clones the repository, runs its Makefile, and collects the root `code` executable. The standalone Verilog language entry (`iverilog answer.v -o code`) uses a different compilation flow. The supplied `3201.zip` identifies correctness problem 3201 with a **180-second compilation limit** and **100 seconds / 320 MiB per testcase**. It selects runner group `verilator` and sets `Verilog=false`. Its configuration has no separate compilation memory limit. The archive hash and exact settings are recorded in [third_party/oj3201-package.json](third_party/oj3201-package.json).

```sh
git submodule update --init testcases
make                 # Build RTL and create ./code for OJ
# Equivalent: make code
```

The build uses the checked-in RTL and official `scripts/sim.cpp`; it does not use a simulator from an earlier experiment. OJ supplies its toolchain and testcase inputs. Tool executables or build outputs do not need to be committed. No file in this submission entry depends on the ignored `.deps/` directory or this machine's drive letters.

Host prerequisites are Python 3.10+, GNU Make, a C++17 compiler, binutils, and the course hardware tools. An optional course AppImage can be placed at the repository root. If it is absent, the official framework uses tools on PATH; explicit tool overrides take precedence. See the [official course instructions](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026).

For machine-specific overrides, create the ignored `config.local.mk` and select it explicitly:

```make
# config.local.mk -- keep this file out of Git
APPIMAGE =
PYTHON = python3
VERILATOR = /path/to/verilator
YOSYS = /path/to/yosys
ABC = /path/to/yosys-abc
STA = /path/to/sta
ASAP7_LIB = /path/to/asap7/lib
```

```sh
make CONFIG=config.local.mk
```

The default `config.mk` selects `tools/verilator_low_memory.py`. It runs Verilator generation first and waits for that process to exit before running C++ compilation with one job. Generated files use a split threshold of 8000, while functions and trace functions retain a threshold of 2000. Verilator uses module inlining, `--unroll-count 1024` and `--unroll-stmts 4096`; larger experimental configurations can override the latter with `CPU2026_UNROLL_STMTS`. This bounds concurrent host memory use and avoids the compiler startup cost of unnecessarily small files. Verilator's split thresholds count operations, not bytes, and do not guarantee a maximum file size or memory footprint.

The default `CPU2026_TRACE_DEPTH=1` generates waveforms for top-level signals, including the AXI interface and diagnostic outputs. The official simulator and its waveform API are unchanged. Full internal waveform visibility can be restored with `make CPU2026_TRACE_DEPTH=0`; that generates substantially more C++ and increases build time. The wrapper prints separate elapsed times and exit statuses for generation and compilation to help locate build failures. Neither this profile nor testcase runtime limits establish that a particular OJ compilation time or memory cap is met.

`CPU2026_COMPACT_IDS=1` shortens private generated C++ identifiers with Verilator's `--protect-ids` option and a fixed public key for reproducible names. It preserves top-level port names and the original RTL remains in the repository. The generated `Vstudent_top__idmap.xml` maps the short names back to their RTL names. To debug full internal waveforms with original names, use `make CPU2026_TRACE_DEPTH=0 CPU2026_COMPACT_IDS=0`. The profile also sets Verilator 5.020's `--comp-limit-parens 32` compiler depth threshold: it materializes subexpressions as temporary values instead of emitting deeply nested packed RAT recovery expressions.

After generation, the wrapper combines small C++ files into compilation units with at most 2 MiB of source per combined unit. The former eight-file cap is removed so tiny units can share a compiler invocation. Larger original files remain separate, and each generated source is included exactly once. Hot, cold, and support categories remain separate. This reduces compiler startup and precompiled-header loading without increasing concurrent jobs. `make CPU2026_CPP_GROUP_BYTES=0` restores separate-file compilation. Only generated files under the build directory are rewritten by grouping. The official framework remains unchanged.

Hot model code and the official C++ simulation driver use `CPU2026_OPT_FAST=-O3`. Runtime-library code keeps `-Os`; cold model code keeps the framework's default. `CPU2026_WORD_SIM=1` selects equivalent two-state word expressions for simulation, preserving register edges, AXI transactions and MDU latency. Synthesis uses the original structural branches. `CPU2026_SPLIT_SCHEDULE=1` splits acyclic selector arrays, avoiding repeated evaluation caused by false array cycles in Verilator 5.020. Both switches can be set to 0 for structural debugging. See [the runtime measurements and equivalence scope](reports/OJ_runtime_2026-10-06.md).

`CPU2026_STABLE_MDU=1` retains the original iterative MDU as a separate generated module. Once every other core state field and its inputs have settled, the simulator reuses that calculation while executing the original MDU transition on every CPU clock. It preserves the cycle counter and all ten core statistics counters, and resumes full evaluation whenever an input or MDU boundary signal changes. Tracing always uses full evaluation. Unrecognized generated layouts also retain full evaluation, with the reason recorded in `Vstudent_top_stable_mdu.json`. Set this build switch to 0 to disable the optimization. Runtime diagnostics and per-edge comparison are available through `CPU2026_STABLE_MDU_DIAGNOSTICS=1` and `CPU2026_STABLE_MDU_VERIFY=1`; these are off in normal submissions. A native Pi fragment of 100,000 cycles improved from 6.0860 to 2.0098 seconds with unchanged instruction and cycle counts. This fragment does not establish a complete Pi pass or the 100-second target. See [the acceleration research report](reports/OJ_pi_acceleration_research_2026-10-07.md).

The word simulation view also scans default RAT recovery rows once, replacing 31 repeated per-register scans. Only ROB=32, PAW=6, IMPL=2 with default index/count widths use this form; other geometries retain the original module. Compositional proofs cover an arbitrary architectural register, arbitrary ROB metadata, and both branch-mapping policies. In a paired native 100,000-cycle Pi window, this reduced wall time from 2.0395 to 1.5539 seconds. Both versions retain 26,484 retired instructions. Synthesis preprocessing remains identical, and no new hardware measurements or complete Pi pass are claimed. See [the proof scope and measurements](reports/OJ_pi_acceleration_research_2026-10-07.md).

`CPU2026_NATIVE_BITS=1` replaces generated scalar ceil-log2 calls with equivalent bit scans, retaining zero/one results and leaving the course runtime library unchanged. Word selectors use complete array rows and preserve multi-event OR behavior. In a paired native Pi window, this reduced 100,000-cycle wall time from 1.5472 to 1.2000 seconds, retaining 26,484 retired instructions. The MDU cache now snapshots every fixed data member, including generated arrays; unsupported types or oversized state retain full evaluation. Set `CPU2026_NATIVE_BITS=0` to use the course scalar loops. These partial results do not establish a complete Pi pass. See [the proof and snapshot scope](reports/OJ_pi_acceleration_research_2026-10-07.md).

`CPU2026_ICO_PAIR=1` reuses the input-combinational calculation between a completed full falling evaluation and its rising evaluation, only when all non-clock inputs are identical. Every original rising register update and iterative MDU step still executes. The generator checks the input widths, clock trigger and skipped call graph; tracing and unsupported layouts use full evaluation. Set the build switch to 0 or `CPU2026_ICO_PAIR_DISABLE=1` at runtime to disable it; `CPU2026_ICO_PAIR_VERIFY=1` compares each proposed transition with the original evaluator. Together with equivalent default ROB/rename bitmaps and sparse LSQ checks, a paired native 100,000-cycle window improved from 1.2432 to 1.0487 seconds, with 26,484 retired instructions. The new path passed 17,105 complete state comparisons, alongside 12,895 stable-MDU comparisons. These remain partial windows; the complete Pi target is unresolved. See [the measurements and proof scope](reports/OJ_pi_acceleration_research_2026-10-07.md).

The wrapper selects the configured AppImage or the installed Verilator. `CPU2026_REAL_VERILATOR` can explicitly select the real executable; setting `VERILATOR` itself bypasses the wrapper. Command-line and machine configuration overrides remain supported. No newer-version `--output-groups` option is used. The default `JOBS` is 1; the wrapper always compiles with one job, including when the caller requested more.

The `SIM` override only applies to local run/test/perf; `make` and `make code` always build RTL. The resulting `code` executable accepts the course `CPU2026-OJ` stdin protocol and writes the exit result to stdout.

## Local course commands

```sh
make help
make build                                  # Produce build/sim
make test Case=correctness_add_to_100
make test MAX_CYCLES=48000000 LATENCY=10      # Local full-suite budget including Pi
make perf LATENCY=10
make synth MODE=opt CLOCK_PERIOD_NS=2.0
```

The official defaults remain `LATENCY=10` and `MAX_CYCLES=1000000`. The measured A109 Pi run needed 38,853,527 cycles and passed with a 48,000,000-cycle limit. Problem 3201 supplies `MAX_CYCLES=1000000000` and `LATENCY=10` in all 21 inputs, including Pi. The existing serializer reproduces all 21 archived inputs and answers exactly, and all 63 testcase source Git blobs match the archive hashes. An earlier word model passed the archived qsort and tak inputs locally in 76.59 and 68.80 seconds, with unchanged A109 cycle counts and about 266.6 MiB peak RSS. Pi remains unresolved: the current word view shares the default D-cache metadata query address and updates only touched state words. Its paired native measurement was 0.8475 seconds for 100,000 cycles, versus 1.1254 seconds for the preceding build, with 26,484 retired instructions. A separate original-Memory/tick probe took 5.4447 seconds for 1,000,000 cycles and retired 98,243 instructions. These are partial results, not complete correctness passes. The frozen full Pi run required 38,853,527 cycles. See [the proof scope and measurements](reports/OJ_pi_acceleration_research_2026-10-07.md).

The archive records framework revision `08d82a829232f782f3b8063686d25d46f7272130`, whereas the available pinned framework is `54fc150ffc290f52aa024209ffb9a29d43856f6d`. The archive's Framework repository URL currently returns repository-not-found. The protocol and testcase checks above establish compatibility with the supplied inputs; exact framework-source equivalence remains unverified. The existing official scripts have been preserved.

For Windows development, the previous Makefile is preserved as `Makefile.windows`:

```text
make -f Makefile.windows gui
make -f Makefile.windows doctor
make -f Makefile.windows lint
```

These are the historical research commands and settings. Course measurements use the pinned native Windows tools recorded in `tools/course_windows_config.json`; use native MSYS2 GNU Make/MinGW when configuring the official entry on Windows. WSL is not used for this project. The compilation profile was measured separately from CPU simulation and synthesis; see [the host build report](reports/OJ_host_build_profile_2026-10-06.md).

For binaries built with the configured F-drive MinGW toolchain, `python tools/run_course_sim_windows.py BINARY [SIM_ARGUMENTS...]` selects its matching runtime DLLs in a child process. The ambient PATH also contains a different MinGW installation; mixing its DLLs with the configured compiler's binary reproduced an access violation. This helper is only for native Windows development. See [the environment audit](reports/OJ_host_environment_audit_2026-10-06.md).

## Current implementation and verified results

| Item | A109 default / existing measured result |
|---|---:|
| Frontend / commit width | 4 / 2 |
| Integer issue / CDB width | 2 / 2 |
| ROB / physical registers / RS / LSQ | 32 / 56 / 8 / 16 |
| I-cache | 128 lines, 2 ways, 16 bytes/line |
| D-cache | 1024 lines, 2 ways, 16 bytes/line |
| Six-benchmark IPC GEOMEAN | 1.115262692 |
| Total area, including SRAM | 35,891.672318 um² |
| Course synthesis/STA estimated Fmax | 321.608040 MHz |

These existing results meet the course Tier3 thresholds. They are measurements of the frozen A109 sources under the pinned course tools, not a new OJ result or post-layout frequency. See [the verified A109 report](reports/ER1_A109_Tier3_verified_2026-10-06.md) for the exact correctness runs, budgets, tool versions, and source identity.

The AXI4-Lite exit convention is a word store to `0x80000000` with `WSTRB=4'hf`; the 32-bit write data is the exit result. External RAM is 256 MiB. `student_top` provides all required course ports and three additional diagnostic outputs accepted by the previously verified official simulator; the simulation view preserves those ports and the synthesis view retains the original hardware structure. Protocol and SRAM specifications are in [docs/axi4-lite.md](docs/axi4-lite.md) and [docs/sram.md](docs/sram.md).

## Repository layout

```text
Makefile           Official course build/OJ/test/synthesis entry
Makefile.windows   Preserved Windows research commands
config.mk          Portable official defaults
scripts/           Unmodified pinned course framework and SRAM model
testcases/         Official testcases submodule
verilog/filelist.f  Relative paths to the submitted RTL
rtl/               A109 RTL and definitions
rv32im_defs.vh      Root include alias required by the course build
tb/ tests/ tools/   Historical development and verification utilities
docs/ reports/     Design documents, exploration, and measured results
history/           Important version and commit indexes
build/             Ignored local outputs
```

The [parameter sensitivity report](reports/parameter_sensitivity.md), [architecture exploration](reports/architecture_exploration.md), and [important version index](history/important_versions/README.md) preserve development evidence. Historical measurements used their documented source and tool settings; the A109 verified report defines the current course results.
