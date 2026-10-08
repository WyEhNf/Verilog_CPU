# Parameterized RV32IM Out-of-Order CPU

The default pipeline and resource configuration retains A109: an out-of-order RV32IM core with register renaming, a ROB for in-order commit, instruction/data caches, and the course AXI4-Lite interface. It implements byte, halfword, and word loads/stores and all eight M-extension operations. The top module is `student_top`, listed in `verilog/filelist.f`.

All tier profiles build the same `cpu_core` and `rv32_backend_joint`. Frontend/backend widths (1, 2 or 4), issue ports, queues, register resources and cache policies are parameters of that implementation. Historical separate backend sources are excluded from both active filelists; profile preparation rejects their selection.

## Course submission entry

The root `Makefile` and the course driver/build scripts are pinned to the official course framework at commit `54fc150ffc290f52aa024209ffb9a29d43856f6d`. Their hashes and origin are recorded in [third_party/cpu2026-framework.json](third_party/cpu2026-framework.json). The SRAM simulation model has a recorded local cleanup for its timescale and masked-write scratch calculation; its interface and clocked access semantics are retained. `config.mk` adds a portable host compilation profile to the official template. The official `testcases` submodule is pinned to `29f980727f7d99a1842a58f34091c7579ba3fe85` and uses a public HTTPS URL.

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

The default `CPU2026_TRACE_DEPTH=1` generates waveforms for top-level signals, including the AXI interface and diagnostic outputs. The official simulator and its waveform API are unchanged. Full internal waveform visibility can be restored with `make CPU2026_TRACE_DEPTH=0`; that generates substantially more C++ and increases build time. The wrapper prints the actual backend/Python version, separate elapsed times and exit statuses. Full generation and compilation logs are kept in the object directory; failures show error diagnostics before a short tail so warning prefixes do not hide the cause in truncated OJ output. Neither this profile nor testcase runtime limits establish that a particular OJ compilation time or memory cap is met.

The default `CPU2026_COMPACT_IDS=0` retains original generated names and avoids the `--protect-ids`/`--trace` conflict (`INSECURE`). The scheduling helpers accept original names with the same field and execution-boundary checks. The optional `CPU2026_COMPACT_IDS=1` for builds without tracing shortens private generated C++ identifiers with Verilator's `--protect-ids` option and a fixed public key for reproducible names. It preserves top-level port names and the original RTL remains in the repository. The generated `Vstudent_top__idmap.xml` maps the short names back to their RTL names. To debug full internal waveforms with original names, use `make CPU2026_TRACE_DEPTH=0 CPU2026_COMPACT_IDS=0`. The profile also sets Verilator 5.020's `--comp-limit-parens 32` compiler depth threshold: it materializes subexpressions as temporary values instead of emitting deeply nested packed RAT recovery expressions.

After generation, the wrapper combines small C++ files into compilation units with at most 2 MiB of source per combined unit. The former eight-file cap is removed so tiny units can share a compiler invocation. Larger original files remain separate, and each generated source is included exactly once. Hot, cold, and support categories remain separate. This reduces compiler startup and precompiled-header loading without increasing concurrent jobs. `make CPU2026_CPP_GROUP_BYTES=0` restores separate-file compilation. Only generated files under the build directory are rewritten by grouping.

Hot model code and the official C++ simulation driver use `CPU2026_OPT_FAST=-O3`. Runtime-library code keeps `-Os`; cold model code keeps the framework's default. `CPU2026_WORD_SIM=1` selects equivalent two-state word expressions for simulation, preserving register edges, AXI transactions and MDU latency. Synthesis uses the original structural branches. `CPU2026_SPLIT_SCHEDULE=1` splits acyclic selector arrays, avoiding repeated evaluation caused by false array cycles in Verilator 5.020. Both switches can be set to 0 for structural debugging. See [the runtime measurements and equivalence scope](reports/OJ_runtime_2026-10-06.md).

`CPU2026_STABLE_MDU=1` retains the original iterative MDU as a separate generated module. Once every other core state field and its inputs have settled, the simulator reuses that calculation while executing the original MDU transition on every CPU clock. It preserves the cycle counter and all ten core statistics counters, and resumes full evaluation whenever an input or MDU boundary signal changes. Tracing always uses full evaluation. Unrecognized generated layouts also retain full evaluation, with the reason recorded in `Vstudent_top_stable_mdu.json`. Set this build switch to 0 to disable the optimization. Runtime diagnostics and per-edge comparison are available through `CPU2026_STABLE_MDU_DIAGNOSTICS=1` and `CPU2026_STABLE_MDU_VERIFY=1`; these are off in normal submissions. A native Pi fragment of 100,000 cycles improved from 6.0860 to 2.0098 seconds with unchanged instruction and cycle counts. This fragment does not establish a complete Pi pass or the 100-second target. See [the acceleration research report](reports/OJ_pi_acceleration_research_2026-10-07.md).

The word simulation view also scans default RAT recovery rows once, replacing 31 repeated per-register scans. Only ROB=32, PAW=6, IMPL=2 with default index/count widths use this form; other geometries retain the original module. Compositional proofs cover an arbitrary architectural register, arbitrary ROB metadata, and both branch-mapping policies. In a paired native 100,000-cycle Pi window, this reduced wall time from 2.0395 to 1.5539 seconds. Both versions retain 26,484 retired instructions. Synthesis preprocessing remains identical, and no new hardware measurements or complete Pi pass are claimed. See [the proof scope and measurements](reports/OJ_pi_acceleration_research_2026-10-07.md).

`CPU2026_NATIVE_BITS=1` replaces generated scalar ceil-log2 calls with equivalent bit scans, retaining zero/one results and leaving the course runtime library unchanged. Word selectors read packed rows directly and preserve multi-event OR behavior. In a paired native Pi window, the original bit-scan optimization reduced 100,000-cycle wall time from 1.5472 to 1.2000 seconds, retaining 26,484 retired instructions. The MDU cache snapshots every fixed data member, including generated arrays; unsupported types or oversized state retain full evaluation. Its rollback buffers copy every byte they subsequently read, and its ten statistics counters use direct field accesses with the same deltas and staging writes. Set `CPU2026_NATIVE_BITS=0` to use the course scalar loops. These partial results do not establish a complete Pi pass. See [the proof and snapshot scope](reports/OJ_pi_acceleration_research_2026-10-07.md).

`CPU2026_ICO_PAIR=1` reuses the input-combinational calculation after a completed full evaluation when all non-clock inputs remain identical. Verilator restores the combinational invariant after register updates by replicating dependent logic in its active/NBA regions. Every original clock edge, active/NBA evaluation and iterative MDU step still executes. The generator checks the input widths, clock trigger and skipped call graph; tracing and unsupported layouts use full evaluation. Set the build switch to 0 or `CPU2026_ICO_PAIR_DISABLE=1` at runtime to disable it; `CPU2026_ICO_PAIR_VERIFY=1` compares every reused transition's complete root and MDU state against the original evaluator. The expanded reuse passed 61,711 Pi, 188,920 qsort and 199,723 tak state comparisons in separate 100,000-cycle windows. A paired 5,000,000-cycle Pi window improved from 22.36 to 14.12 seconds under concurrent background load; this window alone does not establish the full 85-second target. The earlier falling-to-rising implementation and its measurements are documented in [the acceleration research report](reports/OJ_pi_acceleration_research_2026-10-07.md).

Packed selectors passed symbolic equivalence checks for all 67 emitted row geometries, including out-of-range array indices and simultaneous OR-mode events. The packed-selector synthesis branches are byte-identical to the prior version. The expanded input-region reuse and MDU changes passed the complete-state comparisons described above. See [the 5.040 validation record](reports/OJ_5040_settled_inputs_2026-10-07.json) for the proof scope, build and earlier measurements.

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

The official defaults remain `LATENCY=10` and `MAX_CYCLES=1000000`. Problem 3201 supplies `MAX_CYCLES=1000000000` and `LATENCY=10` in all 21 inputs. The serializer reproduces all archived inputs and answers exactly, and all 63 testcase source Git blobs match the archive hashes. The earlier native Windows **Verilator 5.020** build took **104.80 seconds** and completed the original OJ inputs for **Pi in 96.29 seconds**, **qsort in 9.84 seconds**, and **tak in 9.49 seconds**, with the original 256 MiB RAM and latency 10. Those historical measurements are documented in [the acceleration report](reports/OJ_pi_acceleration_research_2026-10-07.md) and [measurement JSON](reports/OJ_pi_pgo_final_2026-10-07.json).

The verified **Verilator 5.040** build recognizes both scheduling caches and emitted zero warnings. Its latest full original Pi execution took **66.47 seconds** (65.28 CPU seconds), returned **112**, and preserved **38,853,527 cycles**; peak working set was **265.71 MiB**. This local native Windows run used the original OJ input, 256 MiB RAM, latency 10 and no waveform, and met the 85-second runtime target. See [the full measurement](reports/OJ_5040_pi_remeasure_20261007-231559.json). The same binary previously took **102.47 seconds** while a concurrent user game was active; the difference is not a new code optimization and these local times do not establish remote OJ runtime. Generation and compilation of that binary took **152.86 seconds**. Its SHA256 is `d084d7128de6453d599addf7faae714707a353ed8aeec40c43bf85a169bfd9cc`.

The latest source additionally replaces 128-bit cache-line insertion/extraction shifts with 64-bit windows under `CPU2026_WORD_SIM`. Extraction selects two adjacent 32-bit words and zero-fills beyond the last word; insertion places the low/high shifted words and discards overflow beyond the line. The synthesis branches remain unchanged. These two changes have not been compiled, formally checked or benchmarked. The **66.47-second measurement applies to verified parent commit `217827c4`** and does not include these byte-window changes.

`CPU2026_PGO=1` is the default for the original driver with GNU GCC. It builds branch instrumentation, runs a bounded 100,000-cycle window of the original Pi input, then rebuilds hot objects with profile use and at most two LTO workers, avoiding GCC's serial-LTO warning. Generated model objects are linked directly: the compiler's linker plugin receives them without depending on `ar` discovering GCC's LTO plugin or indexing its intermediate code. The original Verilator link recipe, user/runtime objects and libraries remain in use. See [the OJ link failure and repair](reports/OJ_lto_archive_fix_2026-10-07.md). Other C++ compilation remains serial. That incomplete training window is not a correctness pass. Profiles are generated inside the clean object directory, never shipped as prebuilt results. The public course Pi training image is vendored as `tools/cpu2026_pgo_pi.txt`, with [origin and hash](third_party/cpu2026-pgo-training.json), so compilation does not require initializing the optional testcases submodule. Use `CPU2026_PGO=0` to disable it; custom drivers, non-GNU compilers and explicit profile/LTO flags use the ordinary compiler path. The frozen pre-cleanup hardware measurements are IPC GEOMEAN 1.1152626918, area including SRAM 35891.672318 μm² and frequency 321.6080402 MHz. They were not remeasured after the RTL warning cleanup. The warning-cleanup native 5.040 generation, C++ compilation and link completed with zero warnings in 98.81 seconds; 5.020 generation also emitted zero warnings. See [the warning cleanup validation and scope](reports/OJ_warning_cleanup_2026-10-07.md).

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

### Area tiers and optimization acceptance

The [official course requirements](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026) use the following joint thresholds. Area includes every SRAM macro, IPC is the geometric mean of all six official `perf_*` programs at latency 10, and frequency comes from the complete course synthesis/STA flow.

| Tier | Maximum area (μm²) | Minimum IPC (geomean) | Minimum frequency (MHz) | Cumulative score |
|---|---:|---:|---:|---:|
| Tier 1 | 9,000 | 0.6000 | 300 | 90 |
| Tier 2 | 18,000 | 0.8450 | 300 | 95 |
| Tier 3 | 36,000 | 1.0985 | 300 | 100 |

[Tier1](configs/tier1.json) and [Tier2](configs/tier2.json) select resource/width configurations of the same `rv32_backend_joint`; neither currently meets all tier gates. Tier1 currently references the small OoO candidate, historically measured at 8,641.61 μm² / IPC 0.427551 / 352.98 MHz. The earlier separate inorder Tier1 experiment reached 8,872.46 μm² / IPC 0.604828 / 355.19 MHz, but is archived as numerical evidence only and is no longer a supported course configuration. Its six perf answers and one small correctness sample passed; [frozen evidence](reports/Tier1_verified_2026-10-08.json) and Git tag `codex/tier1-verified-20261008` preserve that source. [Tier3](configs/tier3.json) retains the source defaults. Widths and capacities use one shared CPU/backend; new profile preparation rejects separate-backend selection. Neither Tier1/Tier2 nor the Tier3 500 MHz target is complete.

The shared [Tier1 SRAM D128 candidate](configs/tier1_shared_sram_d128.json) measured **8,622.19 μm² / 372.36 MHz / IPC 0.432793**. All six perf answers passed, but IPC is below 0.6000, so it is not accepted and no CPU smoke was added. A limited 114-observation native synchronous PRF sample passed; its coverage and the corrected stimulus are recorded in [the measurement record](reports/Tier1_shared_sram_d128_2026-10-08.json). The [shared credit candidate](configs/tier1_shared_current_credits.json) keeps the same resources and removes an extra credit-register delay in direct dispatch. It measured **8,650.41 μm² / 378.00 MHz / IPC 0.506860**; all six answers passed and cycles decreased, but IPC still fails. [Its frozen record](reports/Tier1_shared_current_credits_2026-10-08.json) preserves those results. The [shared window candidate](configs/tier1_shared_window8.json) expanded ROB4/PRF36/LSQ2 to ROB8/PRF40/LSQ4 while retaining widths and caches, but failed area at **9,619.74 μm² / 391.14 MHz**, so build/perf/smoke were skipped. [Its frozen record](reports/Tier1_shared_window8_2026-10-08.json) preserves the result. The [shared load-credit candidate](configs/tier1_shared_load_window8.json) uses operand preview to avoid charging an RS slot for an already-ready load, retains LSQ2 and cache capacities, and uses single-way caches to reduce control cost. It measured **8,878.27 μm² / 369.01 MHz / IPC 0.494717**, failing IPC with all six answers and admission assertions passing; no smoke was added. [Its frozen record](reports/Tier1_shared_load_window8_2026-10-08.json) preserves the result. The [shared dual-issue candidate](configs/tier2_shared_load_credit.json) applies the same backend/credit/preview logic to BE2 and larger cache/LSQ resources. It measured **17,088.20 μm² / 363.12 MHz / IPC 0.807638**, improving all three aggregate metrics over the historical shared balanced-memory candidate, but failing the 0.8450 IPC gate; all six answers and admission assertions passed, and smoke was skipped. [Its frozen record](reports/Tier2_shared_load_credit_2026-10-08.json) preserves the result. All widths continue to use `rv32_backend_joint`.

The [shared PC-index predictor candidate](configs/tier1_shared_pc_predictor.json) changes only the predictor mode in the previously measured Tier1 current-credit profile. It measured **8,517.16 μm² / 393.39 MHz / IPC 0.507100**, reducing area and increasing frequency, but improving geomean IPC by only 0.047% and failing the tier IPC gate; all six answers passed and smoke was skipped. [Its frozen record](reports/Tier1_shared_pc_predictor_2026-10-08.json) preserves the result.

The [shared ROB16 dual-issue candidate](configs/tier2_shared_window16.json) measured **18,066.68 μm² / 323.23 MHz**, failing area; its build, perf and smoke were skipped. [Its frozen record](reports/Tier2_shared_window16_2026-10-08.json) preserves the result. The [FE2/BE1 candidate](configs/tier1_shared_fetch2.json) widens fetch using the existing instruction queue while keeping single issue. It measured **8,629.16 μm² / 368.88 MHz / IPC 0.509285**; all six answers passed, but IPC is below 0.6000, and the 0.43% geomean gain costs area and frequency. Smoke was skipped. [Its frozen record](reports/Tier1_shared_fetch2_2026-10-08.json) preserves the result.

The [shared direct free-bitmap candidate](configs/tier2_shared_direct_free.json) selects the existing allocator path through a default-preserving parameter. It measured **17,082.38 μm² / 362.61 MHz / IPC 0.807826**, improving geomean IPC by only 0.023%; all six answers passed, IPC still fails, and smoke was skipped. [Its frozen record](reports/Tier2_shared_direct_free_2026-10-08.json) preserves the result. The corresponding Tier1 profile is untested; no significant performance gain is inferred from the allocator option.

The shared [Tier1](configs/tier1_shared_writearound.json) and [Tier2](configs/tier2_shared_writearound.json) write-around candidates add `DCACHE_STORE_MISS_WRITE_AROUND=1` to their existing shared-backend profiles. Cold store misses send only their enabled bytes through the existing AXI bridge, preserve cache victims, and acknowledge the original full LSQ tag after the memory write response. Same-line stores wait; covered loads can forward, and uncovered loads wait for write completion. Hits retain write-back behavior. The default is zero at both CPU boundaries, with no around state or extra action decode retained when disabled. Two limited native protocol samples passed before the final default-off guards; [the frozen sample record](reports/Tier_shared_writearound_protocol_2026-10-08.json) identifies exact inputs and limitations. The Tier2 candidate measured **17,142.04 μm² / 360.69 MHz / IPC 0.668030**, with all six answers passing but every benchmark slower than the shared load-credit reference. IPC fails, area/frequency also regress relative to that candidate, and smoke was skipped; [the frozen CPU record](reports/Tier2_shared_writearound_2026-10-08.json) preserves this rejected result. Tier1 remains untested and is not scheduled for the same policy. Neither profile is accepted; the default keeps write-around disabled.


`tools/run_tier_candidate.py` freezes the current tracked RTL and official scripts into a new directory, applies the listed top-level parameter defaults there, and records source/tool/library hashes. An explicit `compact_control: 1` profile also sets the identical control-tree policy macro in both copied headers, allowing synthesis to optimize fanout and delete unused source cones. The default policy retains the original explicit trees. Select each measurement phase explicitly; it never starts a sweep or a full correctness suite. The native Windows defaults can be replaced with `--host-config` during preparation.

The first legal Tier1 candidate measured **12,288.76 μm² / 347.47 MHz**; the first Tier2 candidate measured **19,886.02 μm² / 337.95 MHz**. Both exceed their area limits, so their build and IPC phases were skipped. [Tier1 area-control candidate](configs/tier1_area_control.json) measured **10,281.75 μm² / 130.95 MHz** and was rejected; its optional policy is disabled by default. The corresponding [Tier2 experiment](configs/tier2_area_control.json) has not been run. [Tier1 micro OoO candidate](configs/tier1_micro_ooo.json) measured **9,278.84 μm² / 347.35 MHz** and still exceeds its area limit; its build and IPC phases were skipped. The [Tier1 frontend candidate](configs/tier1_micro_frontend.json) passed PPA at **8,641.61 μm² / 352.98 MHz**, but its six official perf answers passed at geomean IPC **0.4276**, below the tier threshold. [Tier2 micro candidate](configs/tier2_micro_ooo.json) passed PPA at **17,669.81 μm² / 358.04 MHz**, but its six official perf answers passed at geomean IPC **0.7288**, below the tier threshold. The [Tier2 balanced-memory candidate](configs/tier2_balanced_memory.json) passed PPA at **17,146.60 μm² / 353.59 MHz**, but all six perf answers passed at geomean IPC **0.7705**, below the tier threshold. The new [Tier1 inorder-memory candidate](configs/tier1_inorder_memory.json) selects optional `SERIAL_BACKEND=2`, a pipelined single-issue backend with architectural registers, a four-entry completion queue and two committed-store slots, allowing a 256-line D-cache. Its first frozen RTL revision measured **9,705.71 μm² / 190.55 MHz**, failing both PPA thresholds, so build and IPC were skipped. The [Tier1 banked-inorder candidate](configs/tier1_inorder_banked.json) adds distributed operand selection and write enables, shares the store/result field and existing shifter, and passed **8,872.46 μm² / 355.19 MHz / IPC 0.604828**, preserving a historical numerical pass; this separate backend is now archived and cannot satisfy the unified CPU acceptance. The [Tier2 direct-memory candidate](configs/tier2_direct_memory.json) measured **19,434.73 μm² / 347.59 MHz**; it exceeds its area limit, so build and IPC were skipped. The independent [Tier2 lookup-inorder candidate](configs/tier2_inorder_lookup.json) uses a youngest-writer map and launches loads at allocation, retaining the original 1024-line D-cache; its first isolated frozen revision failed PPA at **21,421.33 μm² / 256.19 MHz**, so build and IPC were skipped. These measurements belong to the frozen revisions recorded in [optimization evidence](reports/tier_optimization_2026-10-08.md), rather than unmeasured later RTL revisions of the same profile.

```powershell
python tools/run_tier_candidate.py prepare --profile configs/tier1.json --out F:/CPU2026TierRuns/NEW_TIER1
python tools/run_tier_candidate.py synth --out F:/CPU2026TierRuns/NEW_TIER1
# After the complete area/frequency result supports continuing:
python tools/run_tier_candidate.py build --out F:/CPU2026TierRuns/NEW_TIER1
python tools/run_tier_candidate.py perf --out F:/CPU2026TierRuns/NEW_TIER1
python tools/run_tier_candidate.py smoke --out F:/CPU2026TierRuns/NEW_TIER1
```

Before accepting a Tier3 optimization, all three measured metrics must meet its thresholds and must not regress from the accepted version. The project final version additionally requires at least 500 MHz. Only after preserving that version do the IPC 1.5, 1 GHz and unrestricted-area explorations begin. Candidate measurements and failures remain separate from accepted results; historical evidence is never overwritten.

The AXI4-Lite exit convention is a word store to `0x80000000` with `WSTRB=4'hf`; the 32-bit write data is the exit result. External RAM is 256 MiB. `student_top` provides all required course ports and three additional diagnostic outputs accepted by the previously verified official simulator; the simulation view preserves those ports and the synthesis view retains the original hardware structure. Protocol and SRAM specifications are in [docs/axi4-lite.md](docs/axi4-lite.md) and [docs/sram.md](docs/sram.md).

## Repository layout

```text
Makefile           Official course build/OJ/test/synthesis entry
Makefile.windows   Preserved Windows research commands
config.mk          Portable official defaults
scripts/           Pinned course framework; recorded SRAM warning cleanup
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
