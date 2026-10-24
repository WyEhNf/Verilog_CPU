请你从当前最优的性能出发，我希望你先把三项指标都提高到一个接近标准(Tier3)的水平，然后再做逐项的优化以及trade off

尤其注意SRAM也是要计入面积计算的，相关计算方法与相关要求在[https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026项目中给出了。](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026项目中给出了。)

具体的指标如下：

## Architecture & Project Requirements

### 1. Instruction Set Architecture (RV32IM)

- **Base Integer Instructions**: Full RV32I user-level instruction set.
- **M Extension**: Complete standard multiplication and division extensions: `MUL`, `MULH`, `MULHSU`, `MULHU`, `DIV`, `DIVU`, `REM`, `REMU`.
- **Loads & Stores**: Full integer load and store instructions: `LB`, `LBU`, `LH`, `LHU`, `LW`, `SB`, `SH`, `SW`.
  - Memory accesses are naturally aligned (half-words aligned to 2 bytes, words aligned to 4 bytes). Unaligned memory accesses are not required.
- **Omitted Instructions**:
  - `CSR*` (Control and Status Register) instructions are not required.
  - `FENCE` and `FENCE.I` instructions are not required.
  - `ECALL` and `EBREAK` instructions are not required.

### 2. Microarchitecture Requirements

- **Out-of-Order (OoO) Execution**: Instructions must be dispatched/executed out of program order when operands become available.
- **In-Order Commit**: Instructions must retire in strict program order (e.g., using a Reorder Buffer / ROB).
- **Parameterization**: Key microarchitectural parameters should be parameterized in your design:
  - Issue width
  - Reorder Buffer (ROB) capacity
  - Physical Register File (PRF) size
  - Reservation Station / Issue Queue depth
  - Cache capacity and associativity

### 3. Termination & Output Convention

- The CPU halts and communicates its exit status by performing a **32-bit word store to MMIO address \*\*\*\*`0x80000000`** with write strobe `WSTRB = 4'b1111` (`4'hf`).
- The exit return code is placed in `WDATA[31:0]`.
- Correctness is determined by comparing the final exit result with the reference answer.

### 4. Memory Layout

- **External RAM**: 256 MiB little-endian RAM (`0x00000000`–`0x0fffffff`).

### 5. Final Report

Each team (up to 2 students) must submit a project report covering:

- **Parameter Sensitivity Analysis**: How performance (IPC) changes across different parameter configurations (e.g., varying issue width, PRF size, ROB size, cache configurations).
- **Architectural Exploration**: Key design trade-offs explored during development.

---

## Grading & Milestones

### 1. Correctness (Max 85 Points)

| **StageRequirementsCumulative Score** |                                                            |    |
| ------------------------------------- | ---------------------------------------------------------- | -- |
| Basic Programs                        | Pass: vector multiplication, vector addition, sum 0 to 100 | 75 |
| Simulation Programs                   | Pass remaining CPU simulation test programs                | 85 |

*Note: Passing the preceding stage is a prerequisite for earning points in the subsequent stage. The final exit result must match the reference answer.*

### 2. Performance (Max 15 Points + 4 Frequency Bonus Points)

- **Area**: Standard cell area synthesized with **Yosys + ASAP7** 7.5-track RVT TT libraries, plus estimated FakeRAM SRAM area (in μm2). The report shows total area and its combinational, sequential, and SRAM components.
- **IPC**: Measured dynamically in Verilator as Dynamic InstructionsSimulation Cycles. Overall IPC is calculated as the **geometric mean (GEOMEAN)** across all benchmark testcases under `testcases/perf_*`.

| **TierMaximum Area (μm2)Minimum IPC (Geomean)Minimum frequency (MHz)Cumulative Score** |        |        |     |     |
| -------------------------------------------------------------------------------------- | ------ | ------ | --- | --- |
| Tier 1                                                                                 | 9,000  | 0.6000 | 300 | 90  |
| Tier 2                                                                                 | 18,000 | 0.8450 | 300 | 95  |
| Tier 3                                                                                 | 36,000 | 1.0985 | 300 | 100 |

**Frequency Bonus**: After meeting a tier's area, IPC, and 300 MHz minimum frequency requirements, add the following bonus to that tier's cumulative score.

| **Minimum Frequency (MHz)Bonus Points** |    |
| --------------------------------------- | -- |
| 300                                     | +0 |
| 400                                     | +2 |
| 500                                     | +4 |

For example, Tier 1 at 400 MHz earns 92 points, and Tier 3 at 500 MHz earns 104 points

以上为项目的最终要求，请你将这份要求落盘，并且至少达到Performance的Tier3