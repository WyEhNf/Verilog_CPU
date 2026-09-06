# Project Handoff Status

Updated: 2026-09-06 (Asia/Shanghai)

## Goal and acceptance source

The authoritative requirements are `instructions.md` and `plan.md`.  The target
is a synthesizable Verilog-2005, out-of-order RV32IM CPU with independently
parameterized frontend/backend widths of 1/2/4, parameterized physical-register
and ROB capacity, runnable C-program images, and Yosys + ASAP7 performance/area
evaluation.

## Current phase

The repository has a working single-issue speculative out-of-order core and is
transitioning from JOIN-02 to JOIN-03.  Unit-level structures are parameterized,
but the integrated core still transfers only lane zero between the frontend and
backend.  Area-reduction experiments are present but not yet committed.

## Verified baseline on 2026-09-06

The following commands passed on the current workspace:

```text
make doctor
make lint
make unit matrix h01 h02 h03 h04 a01 a02 a03 a04 a05 a06 a07 \
  b01 b02 b03 b04 b05 b06 b07 b08 b09 join01
```

Notable results:

- JOIN-01: return=7, instret=2, cycles=68.
- Generated `accumulate` image: return=186, instret=12, cycles=287.
- A-07 fetched all 18 external images through frontend/cache/bridge.
- The pre-area-optimization source passed all 18 JOIN-02 images, including
  `pi` at return=137, cycles=548099190, instret=101560724.
- The latest uncommitted source passed 17/17 images with `pi` deliberately
  skipped (`.tmp_join02_vlt_mul.log`).  A fresh 18/18 run is still required.

Lint exits successfully but remains noisy: unused/empty connections, array
sensitivity messages, and physical-register tag-width truncation in the MDU at
large configurations must be cleaned before final parameter-matrix signoff.

## Implementation inventory

- Frontend: fetch queue, bimodal/BTB predictor, I-cache and redirect/epoch path.
- Backend: rename/RAT/RRAT/free list, PRF, ROB, integer RS, MDU RS, ALU/branch,
  multiplier/divider, completion network, and LSQ.
- Memory: independent I/D cache paths, memory bridge, deterministic 50-cycle
  two-port byte-addressed model.
- Verification: unit tests for all named A/B/H blocks, JOIN-01, 18-image
  JOIN-02 runner, watchdog and sparse image tooling.
- Synthesis: Yosys + ASAP7 flow and experimental configuration/area logs.

## Hard gaps against the plan

1. True multi-issue is not integrated.  `cpu_core` consumes `fetch_valid[0]`,
   and `rv32_backend_joint` accepts/emits only one scalar trace/commit record.
2. JOIN-03 is incomplete.  Only `accumulate.c` exists, and `-O2` constant-folds
   its loop.  `vvadd`, `vmul`, and an all-ops RV32M smoke program plus objdump
   and retirement evidence are missing.
3. The current uncommitted source has no fresh `pi` run, so it lacks current
   18/18 evidence.
4. Automated C++ reference-vs-RTL retirement comparison is not a maintained
   Make target; old ad-hoc traces exist only under ignored `build/` files.
5. Top-level CommitRecord and branch/cache/stall counters are not exported;
   cache-stat outputs are currently left open.
6. `reports/` is empty.  There is no final correctness/performance/area report.
7. Current ASAP7 figures omit cells reported with unknown area (`$mem*`,
   `$_MUX_`, `$_NOT_`, BUF/ZERO) and SRAM macro area, so they are not final PPA.
8. README mentions `make smoke` and `make report`, but those targets do not
   exist; `make regression` also requires an external `CPU_RUNNER` rather than
   directly running the integrated core.

## Working-tree state at handoff

Root branch: `master`.

Tracked modifications before JOIN-03 work:

```text
Makefile
rtl/backend/rv32_backend_joint.v
rtl/cpu_core.v
rtl/rv32m_multiplier.v
synth/synth.tcl
synth/synth_bb.tcl
tb/integration/cpu_core_image_tb.v
tools/progress_monitor.py
tools/run_join02.ps1
```

Untracked documentation/reference files:

```text
docs/COSMOS-RV_A_Lightweight_Single-Issue_Speculative_Out-of-Order_32-bit_RISC-V_Processor_With_Virtually_Indexed_Physically_Tagged_Cache_Architecture_and_FPGA_Validation.pdf
docs/area_reduction_plan.md
docs/references.md
```

Do not discard these changes.  They contain checkpoint compression, reduced
PHYS/ROB/RS/LSQ experiment parameters, a single-product multiplier experiment,
synthesis parameter plumbing, and a fast regression mode.

## Reference repositories

- `MinorCPU`: clean; reference only.
- `VerilogCPU(Tfoi's)`: clean; reference only.
- `RISC-V-CPU-Simulator`: reference-only by plan, but already dirty on arrival
  (64 status entries, including moved/deleted test data and a modified predictor
  header).  Do not edit or clean it without explicit user direction.  Current
  tests consume its untracked `testcases/` directory.

## Immediate execution order

1. Add JOIN-03 sources and reproducible rv32i/rv32im image targets; prevent
   constant folding and assert M opcodes in objdump/retirement.
2. Replace the multiplier arithmetic `*` implementation with explicit radix-4
   partial products, 3:2 carry-save compressors, a Wallace reduction tree, and
   a final carry-propagate adder while preserving ready/valid/flush timing.
3. Widen the integrated frontend/backend packet and CommitRecord interfaces,
   then close true BE=2 before BE=4.
4. Extend B-07/B-08/B-09 and full-system tests to BE=4; run independent FE/BE
   combinations and PHYS/ROB capacities.
5. Run the current full 18-image regression (including `pi`) and publish
   correctness evidence before final PPA work.
6. Close synthesis mapping/SRAM/delay accounting and generate Pareto reports.

