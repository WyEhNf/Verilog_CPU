# SRAM 宏引脚驱动与官方流程综合（2026-11-26）

本文说明 `rtl/common/rv32_sram_pin_tree.v` 的用途、接法，主工程在课程官方流程下的三条综合约定，以及 ABC 延迟目标对报告频率的影响。测量数据见[测量报告](../../reports/course_D1000_F537_2026-11-26.md)，各步取舍见[优化过程报告](../../reports/CPU_optimization_500MHz_2026-11-26.md)。

## 为什么需要

官方流程把展平后的设计交给 ABC，约束只有一个驱动单元和一个输出负载（默认 INVx1、5 fF）。SRAM 宏在这一步是设计边界：通往宏的每条网络，ABC 都当作一个 5 fF 的输出来选驱动。FakeRAM 库里宏的每个输入引脚也是 5 fF。一条网络只接一个宏引脚时，两边的假设一致；接 N 个宏引脚时，实际负载是 N×5 fF，ABC 仍按 5 fF 选了驱动，OpenSTA 会按真实负载算出很大的延迟和转换时间。

本设计里一条命令线接多个宏是常态：D-cache 每路数据是 16 个 512×8 宏，共用地址和写使能；I-cache 一行是 8 个 128×16 宏；取指行过滤每个 bank 是 8 个 4×16 宏。

## 模块

```verilog
rv32_sram_pin_tree #(.WIDTH(W), .LEAVES(N), .ROOTED(0|1), .GROUP(8)) tree (
    .signal_i(x),          // W 位
    .views_o(x_pins));     // N 份相同的 W 位副本，每份接一个宏
```

`views_o` 是 `signal_i` 的 N 份副本，没有状态，不改变任何时钟沿的行为。每份副本的每一位由一个独立的 `rv32_sram_pin_inverter` 驱动，它只带一个宏引脚。

- `ROOTED=0`：反相器的输入是 `~signal_i`，由普通逻辑产生。上游逻辑看到 N 个反相器输入，约 N×0.6 fF。N 不大时用它。
- `ROOTED=1`：每 `GROUP` 个引脚再放一个根反相器，上游逻辑每组只看到一个门输入。N 较大（如 16）时用它。

`rv32_sram_pin_inverter` 带 `keep_hierarchy`，这是设计里唯一保留的层级边界。没有它，叶子反相器会和上游的反相合并，引脚重新合到一个驱动上。ABC 把每个实例单独映射成一个 INVx1，面积 0.0437 μm²，计入组合面积。仿真时定义 `CPU2026_WORD_SIM`，模块退化为直接连线。

## 使用位置

| 位置 | 文件 | 引脚 |
| --- | --- | --- |
| I-cache 数据阵列，8 个 128×16 | `rtl/cache/rv32_icache_nonblocking.v` | 片选、写使能、地址 |
| 取指行过滤，每 bank 8 个 4×16 | `rtl/cache/rv32_instruction_line_filter.v` | 片选、写使能、地址、写数据 |
| D-cache 数据，每路 16 个 512×8 | `rtl/cache/rv32_dcache_command_line.v` | 写使能、地址（`ROOTED=1`） |
| D-cache 标签，4 个 512×19 | `rtl/cache/rv32_dcache_nonblocking.v` | 写使能、地址、写数据 |
| AXI 读前缀，每行 3 个 1×32 | `rtl/course/rv32_axi_lite_bridge.v` | 写使能 |

新增 SRAM 时的规则：**一条网络如果接到多于一个宏引脚，就经过这个模块。** 只接一个宏的信号不需要处理。

## 三条综合约定

1. **RTL 不使用 `keep` 和 `keep_hierarchy`**，上面的反相器模块除外。官方流程是展平综合，保留层级会阻止跨边界优化和 ABC 的缓冲插入。去掉全部属性后，默认流程的面积从 37,981 降到 32,787 μm²。手写扇出树 `rv32_frequency_control_tree` 仍在源码里，展平后由综合工具决定是否保留。
2. **宏的位宽尽量窄。** FakeRAM 的读出延迟随单个宏的位宽线性增长（每位 1.24 ps），面积只按总位数计。同样的存储拆成多个窄宏，面积不变而读出更快；代价是命令线要接更多引脚，用上面的模块解决。带写掩码的 `sram_fakeram`（`WRITE_GRANULARITY < WIDTH`）由官方封装展开成多个宏，封装内的片选门不经过引脚驱动，需要多宏时在 RTL 里逐个例化。
3. **ABC 延迟目标是 1.0 ns。** `Makefile` 的 `CLOCK_PERIOD_NS` 默认值从上游的 2.0 改成了 1.0，`config.mk` 里也写了同一个值。原因见下一节。

## ABC 延迟目标：关键观察

**`make synth` 报告的频率在很大程度上由 `CLOCK_PERIOD_NS` 决定，而不只由设计决定。上游默认的 2.0 ns 会把这个设计停在约 476 MHz；设成 1.0 ns，同一份 RTL 是 537 MHz，面积只多 19 μm²。**

`CLOCK_PERIOD_NS` 在官方脚本里有两个用处：传给 ABC 作延迟目标（`abc -D`），以及作为 OpenSTA 报告裕量的参考周期。报告的频率来自 OpenSTA 对最小周期的二分搜索，输入输出延迟、时钟不确定度和负载都是固定值，与这个参数无关。所以它只通过 ABC 的映射影响频率，机制有两点：

- ABC 的受约束脚本是 `&nf -D; buffer; upsize -D; dnsize -D`。`upsize` 一达到目标就停，`dnsize` 再把余量换回面积。目标是 2.0 ns 时，ABC 停在它自己估计的 1.99 ns。
- ABC 的估计不含触发器的时钟到输出延迟、建立时间和 0.05 ns 时钟不确定度，比 OpenSTA 少约 0.1 ns。

两者相加，2.0 ns 目标的结果落在 2.1 ns 附近，与设计还能不能更快无关。把目标设成 ABC 达不到的值，`upsize` 就做到没有改进为止。在提交 `a112d5d` 上逐步打印 ABC 的估计，并扫描目标值：

| ABC 步骤之后 | 目标 2.0 ns | 目标 1.0 ns |
| --- | ---: | ---: |
| `&nf` 映射 | 51,865 ps | 51,865 ps |
| `buffer` | 2,543 ps | 2,543 ps |
| `upsize` | 1,954 ps | 1,765 ps |
| `dnsize` | 1,990 ps | 1,765 ps |
| OpenSTA 最小周期 | 2,085 ps | 1,876 ps |

| `CLOCK_PERIOD_NS` | 3.0 | 2.4 | 2.0 | 1.6 | 1.3 | 1.0 | 0.8 | 0.5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 频率 MHz | 437.42 | 437.42 | 479.63 | 533.06 | 533.06 | 533.06 | 533.06 | 533.06 |

目标放宽，频率跟着降；目标收紧到 1.6 ns 以下，结果不再变化，五个取值得到同一份网表。所以 1.0 不是调出来的最优点，只是一个落在平台区里的值。在更早的提交 `49586a5` 上，1.8 ns 是 505 MHz，1.9 ns 是 493 MHz，说明 2.0 和平台区之间是连续过渡。

在 2.0 ns 目标下改另一个官方参数 `ABC_LOAD_FF`（40 / 100 / 250 fF）只得到 477 / 483 / 487 MHz，面积涨到 34,496 / 35,201 / 35,998 μm²，到面积上限也不到 500 MHz。

**官方仓库对评测使用的目标周期没有规定。** 2026-11-26 检查了 `ACMClassCourse-2025/RISC-V-CPU-2026` 的全部内容：`main`（`302f0cf3`）和 `chisel-example` 两个分支、仅有的两次提交、一个没有正文的已关闭 PR，没有 issue 和 release；testcases 仓库没有提到综合。提到这个参数的地方只有：

- `Makefile`：`CLOCK_PERIOD_NS ?= 2.0`；`scripts/synth.py`：`--clock-period` 默认 2。
- `config.mk`：把 `# CLOCK_PERIOD_NS = 2.0` 列在 “Other overrides accepted here or on the command line” 下面。
- README 变量表：默认值 2.0，“综合与时序分析的目标时钟周期”；并说明它 “默认为 2.0 ns（对应 500 MHz 目标频率）”，用于驱动 ABC 并作为 OpenSTA 的时钟基准。
- README 综合示例：`make synth CLOCK_PERIOD_NS=1.0`。

评分标准一节只给出面积、IPC、频率门槛和加分线；“OJ 提交”一节只要求顶层模块名和 filelist。也就是说，README 把它当作可以在 `config.mk` 或命令行调整的参数，并自己用 1.0 作示例，但**没有写评测实际运行的命令**。因此本仓库把默认值设为 1.0，同时两个数字都报告：评测如果在自己的环境里固定用 2.0 ns，这个设计的频率是 475.62 MHz。

改默认值时只动了 `Makefile` 的两行（默认值和帮助文本）。`scripts/` 下的官方脚本保持与上游逐字节相同，`scripts/synth.py` 自己的 `--clock-period` 默认值仍是 2；`make synth` 总是显式传入这个参数。`tools/run_tier_candidate.py`、`tools/evaluate_current_course.py` 等旧评估器直接调用 `synth.py` 并写死了 2.0，没有改，它们对应 Tier1/Tier2 的历史冻结口径。

## 验证

模块是恒等函数，验证依靠整机回归：改动前后六项性能程序周期数逐项相同，19 项正确性程序通过；映射后的门级网表通过六项性能和全部 19 项正确性，周期数与 RTL 相同。没有单独的模块测试，也没有做形式等价检查。
