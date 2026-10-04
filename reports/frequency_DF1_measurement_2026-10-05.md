# DF1 原生课程测量结果与新瓶颈

DF1 已完成此前报告过的单次 Windows 原生后台综合/STA、CPU 构建、六项 perf 和两个有限功能程序。本文件只读取现成产物，没有启动新测试。原始输入与结果保存在 [DF1 冻结记录](F:/CPU2026CourseRuns/architecture_DF1_20261005/source_manifest.json)和[课程结果](F:/CPU2026CourseRuns/architecture_DF1_20261005/result/result.json)。输入 manifest SHA256 为 `d4596d27b02aadb38412092006592954cf72f7114e705de44aeb5b8bad6113e9`。

| 指标 | DF1 实测 | 对 DD 的变化 |
|---|---:|---:|
| Fmax | 294.337453291 MHz | +7.444668% |
| 最小周期 | 3.3974609375 ns | 缩短 0.2529296875 ns |
| 总面积，含 SRAM | 51,368.530674 μm² | +0.263064%，增加 134.777520 μm² |
| 组合面积 | 32,504.345820 μm² | +134.777520 μm² |
| 时序单元面积 | 11,038.518000 μm² | 相同 |
| SRAM 面积 | 7,825.666854 μm² | 相同，已计入总面积 |
| 六项 IPC 几何平均 | 0.782372864215 | 相同 |

达到 300 MHz 还需把最小周期缩短 **0.0641276042 ns**，约 1.8875%。相对同课程基准，总面积仍高 10.9239%，IPC 仍低 20.1765%；此前 ±10% 和原 Tier3 三项要求尚未达成。不得将接近 300 MHz 写成已经达标。

六项 perf 的周期为 median 12,441、multiply 32,802、qsort 259,022、rsort 169,514、towers 5,889、vvadd 4,085；见 [IPC 原始数据](F:/CPU2026CourseRuns/architecture_DF1_20261005/result/ipc.json)。两个有限程序 lsq_wrap_forward 和 recovery_reuse 分别通过 96 和 80 个检查，周期 1,015 和 1,228；见[有限功能结果](F:/CPU2026CourseRuns/architecture_DF1_20261005/directed_cases/results.json)。**DF1 没有运行十九项完整 correctness，完整通过状态未知。** DD 的完整结果为 16/19，pi/qsort/tak 一百万周期超时，独立保留。

## 五条课程最差检查

课程原流程只发布五条最差检查，均从 `_631533_/QN` 出发，数据到达 **3.3370 ns**。终点依次为 `_633825_/D`、`_635382_/D`、`_635209_/D`、`_633998_/D`、`_635036_/D`，属同一组合锥。这不是全芯片所有路径的清单。

该锥沿 LSQ head → load 完成报告选择 → 本地取消资格 → RS wake/base-ready → store 地址选择 → immediate/base 选择 → 地址加法 → LSQ 写入展开。现有五条路径没有超过库最大电容的门，最大单门延迟约 0.0957 ns；串行深度已经成为主要矛盾。名义最大负载不在这五条路径上，不能继续把所有瓶颈解释为同一个超载驱动。

| 原路径观察点 | 累计到达时间 | 关联修改方向 |
|---|---:|---|
| LSQ report 选择控制，示例 row10 | 0.7771 ns | 保持报告顺序，提前计算各行资格 |
| selected tag 别名 `completion...g_live.data[144]` | 1.0710 ns | 该名字是共享别名，不能独占归属 completion |
| RS wake valid，source5 | 1.2960 ns | 取消比较不再等待已选 ROB tag |
| RS row11 base-ready | 1.5660 ns | 后续 store 选择直接传递 one-hot |
| store packet 选择控制，示例 row1 | 2.0900 ns | 去掉环形选择的编码后再解码 |
| selected RS index 分发输入 | 2.2510 ns | 去掉 RS 索引选择、分发、再解码 |
| immediate 选择控制 | 2.3610 ns | 直接使用选出的 RS one-hot |
| immediate 归并后，示例 OR3 | 2.5160 ns | 地址加法改并行块与 carry prefix |
| 加法/后续组合链末端，示例 AOI22 | 3.2020 ns | 不能把该整段未经分解的时间当作一个加法器精确延迟 |
| LSQ 目的 D 输入 | 3.3370 ns | 后续实际最慢锥仍需新映射确认 |

这些时间来自同一条原始 `source_path`，是累计时间，不是互相独立可相加的优化收益。原始 [critical_paths.json](F:/CPU2026CourseRuns/architecture_DF1_20261005/result/synth/opt/critical_paths.json) SHA256 为 `f7127ff835a1b1ced9b14adecc199e4526df303b4b19afba0496942ef9bb21fd`；[只读汇总](F:/CPU2026Proofs/DF1_existing_reports_20261005/summary.json)对应同一输入。

[映射负载清单](F:/CPU2026Proofs/DF1_existing_mapped_loads_20261005/loads.json)还识别出每个 Dcache way 的 `command_response_store` 最终驱动 **144 个输入脚、66.26408 fF**。refill 字节 mask 资格经过映射后仍扩散到整行数据 mux，本轮新增 DH 对最后的字节资格建立保留边界。全局 reset 的高负载不作为频率优化依据：课程 STA 对 reset 设置了 case analysis 0。

主工作树随后采用未测 DK。上述所有指标只属于 DF1；DK 指标全部未知，详见 [DK 测试前报告](E:/Verilog_cpu/reports/frequency_batch_DK_pretest_2026-10-05.md)。
