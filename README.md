# Parameterized RV32IM Out-of-Order CPU

This repository develops a synthesizable, Verilog-2005 implementation of a parameterized RV32IM processor. The design is intended to be correct by construction, independently testable, and suitable for synthesis after functional verification.

## Design Scope

The processor implements the RV32I base integer instruction set required by the project acceptance programs, including byte and word loads and stores (`LB`, `LBU`, `LW`, `SB`, and `SW`), together with the RV32M multiply and divide extension (`MUL`, `MULH`, `MULHSU`, `MULHU`, `DIV`, `DIVU`, `REM`, and `REMU`). Unsupported or reserved encodings are reported as illegal instructions rather than being treated as no-ops.

The microarchitecture is an out-of-order Tomasulo-style core with:

- speculative register renaming through a RAT, committed mappings through an RRAT, and a physical register free list;
- a parameterized reorder buffer (ROB) providing in-order retirement, precise exceptions, HALT handling, and branch recovery;
- separate integer, multiply, divide, and load/store reservation stations;
- a completion and writeback network with explicit tags, valid/ready backpressure, and bounded arbitration;
- a branch frontend using a bimodal predictor and a direct-mapped BTB;
- independent L1 instruction and data caches with three-cycle hit latency, write-back data-cache behavior, and single-outstanding miss handling in the initial implementation;
- an explicit two-port, little-endian memory protocol backed by a deterministic 50-cycle memory model in verification.

All inter-module interfaces use packed buses and valid/ready handshakes. Payloads remain stable while valid is asserted without ready. Flush, redirect, writeback, store visibility, and retirement priorities are defined centrally in the public RTL definitions.

## Repository Layout

```text
rtl/           Synthesizable Verilog-2005 RTL and shared definitions
tb/            Unit, integration, and memory-model testbenches
tests/         Bare-metal programs, imported simulator cases, vectors, and manifest
tools/         Image generation, startup/runtime support, and regression utilities
docs/          Component design documentation
synth/         Yosys and ASAP7 synthesis scripts and constraints
build/         Ignored simulation, image, and synthesis intermediates
reports/       Correctness, performance, area, and waveform indexes
third_party/   License and pinned dependency metadata
unit_test/     Additional standalone unit-test workspace
```

The external `RISC-V-CPU-Simulator` directory is reference input only. It is not modified by this project.

## Configuration

The default configuration is a single-issue/single-commit core:

```text
FE_WIDTH       = 1
BE_WIDTH       = 1
PHYS_REGS      = 64
ROB_ENTRIES    = 32
```

Frontend and backend widths independently support 1, 2, and 4 lanes. Physical-register and queue capacities are validated at elaboration. Queue and tag capacities must be powers of two where required by the plan, and at least 33 physical registers are required so that architectural register zero remains permanently mapped to physical register zero.

## Verification Contract

The verification flow is layered. Each RTL unit has an independent testbench before it is connected to the top level. Icarus Verilog is used for fast Verilog-2005 unit simulation, Verilator is used for lint and larger simulations, and Yosys is used for synthesis-oriented structural checks. Testbenches enforce reset determinism, no-X behavior, stable valid/ready payloads, tag-generation checks, watchdog timeouts, and precise retirement ordering.

Programs are converted through a reproducible `C -> object -> ELF -> objdump -> sparse byte image` flow. Images begin at address zero, use a one-mebibyte little-endian memory space, preserve section addresses, and end with the agreed `0x0ff00513` HALT instruction. The architectural result is the committed return value in `a0[7:0]`; cycle counts are reported separately and are not used as an architectural reference.

## Toolchain

The planned environment includes Icarus Verilog, Verilator, GTKWave, Yosys, CMake, GNU Make, Python 3, Git, and a RISC-V GNU toolchain with `rv32i/ilp32` and `rv32im/ilp32` multilib support. Run `make doctor` before simulation. Generated outputs belong under `build/` or `reports/` and are ignored by Git.

## Initial Commands

```text
make doctor       Check required tools and paths
make lint         Run Verilog-2005, Verilator, and Yosys checks
make unit         Run focused RTL unit tests
make smoke        Run short architectural programs
make regression   Run the complete acceptance manifest
make matrix       Check supported parameter combinations
make synth        Run synthesis and area reporting
```

The implementation follows `plan.md`; the plan is the authoritative source for interfaces, timing, acceptance programs, and completion criteria.
