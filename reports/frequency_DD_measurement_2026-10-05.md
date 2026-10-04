# DD 原生课程测量：已完成指标与剩余检查

本报告读取已有课程产物，不启动综合或仿真。DD 源快照位于 [architecture_DD_20261005](F:/CPU2026CourseRuns/architecture_DD_20261005/source_manifest.json)，SHA256 为 `f86f29364ee8691b72c80e4ec2fdfed4aa399acb2b8d4fb99a3a129f465db44a`。

| 指标 | DD 实测 | 同课程基准 | 判断 |
|---|---:|---:|---|
| 频率 | 273.943285 MHz | 32.397887 MHz | 未达到 300 MHz；比旧 CD1 的 99.659367 MHz 提高约 174.9% |
| 最小周期 | 3.650390625 ns | 30.8662109375 ns | 达到 300 MHz 还需缩短约 0.317057292 ns，约 8.69% |
| 总面积，含 SRAM | 51,233.753154 μm² | 46,309.693494 μm² | 高 10.6329%，略超此前 ±10% 范围，也超过 Tier3 的 36,000 |
| 组合面积 | 32,369.568300 μm² | — | 使用课程计量 |
| 时序单元面积 | 11,038.518000 μm² | — | 与 CD1 的 11,037.643200 接近，不能声称声明位数减少即实际 FF 大幅下降 |
| SRAM 面积 | 7,825.666854 μm² | 同上 | 已计入总面积 |
| 六项 IPC 几何平均 | 0.7823728642 | 0.9801279406 | 低 20.1765%，未达到此前 ±10% 范围或 Tier3 的 1.0985 |

[课程综合/STA 报告](F:/CPU2026CourseRuns/architecture_DD_20261005/result/synth/opt/report.json)、[时序数值](F:/CPU2026CourseRuns/architecture_DD_20261005/result/synth/opt/timing_values.json)、[IPC 原始记录](F:/CPU2026CourseRuns/architecture_DD_20261005/result/ipc.json)是指标来源。[首次只读汇总](F:/CPU2026Proofs/DD_existing_reports_20261005/summary.json)生成于 IPC 完成前，其 IPC 字段为 null；不得把那个历史 null 当成现在仍未测出 IPC。

## 六项实际周期

| 程序 | 动态指令数 | DD 周期 | IPC |
|---|---:|---:|---:|
| median | 6,961 | 12,441 | 0.559521 |
| multiply | 21,722 | 32,802 | 0.662216 |
| qsort | 139,900 | 259,022 | 0.540109 |
| rsort | 195,719 | 169,514 | 1.154589 |
| towers | 5,278 | 5,889 | 0.896247 |
| vvadd | 4,524 | 4,085 | 1.107466 |

这六项周期与 CD1 完全相同。本批时序优化没有改变这些程序的周期数。课程 perf_multiply 是软件整数乘法，不能用该程序解释硬件 MUL 流水延迟的得失。

## 最新最慢路径

原课程文件仅输出五条最差检查，它们属于同一个组合控制锥，均从 `_638133_/QN` 到 Dcache way1、word0 的数据 SRAM 地址输入。并非全芯片只有五条路径，也不能把五条当成所有慢锥的完整列表。

| 降序名次 | 终点末尾 | 数据到达时间 |
|---:|---|---:|
| 1 | `storage.lane_0/addr_in[0]` | 3.5490 ns |
| 2 | `storage.lane_0/addr_in[1]` | 3.5490 ns |
| 3 | `storage.lane_0/addr_in[2]` | 3.5490 ns |
| 4 | `storage.lane_0/addr_in[3]` | 3.5490 ns |
| 5 | `storage.lane_0/addr_in[4]` | 3.5490 ns |

根节点 NOR2 输出对应 `local_array_write`，其别名出现在 `tag_write_source_tree.signal_i[0]`。这个别名不意味着瓶颈只在 tag；该信号仍直接驱动八个 `rv32_dcache_command_word` 的真实输入。

| 关键段 | STA 延迟 | STA 负载 | 下一步处理 |
|---|---:|---:|---|
| `_354466_` NOR2，local_array_write | 0.946 ns | 96.36 fF，库上限 23.04 | 将命令译码移到每个 way 的 owner；宽数据选择由最后的局部 grant 分发 |
| word 内 `_159_` NAND2 | 0.787 ns | 8.524 fF，但输入 slew 为 1.917 ns | 上游超载消除后再判断自身深度，不把这 0.787 ns 都当成逻辑门数量问题 |
| word 内 `_160_` NOR2 | 0.403 ns | 16.63 fF | 避免同一命令译码再控制整字；拆分地址和数据消费者 |
| 最终 SRAM 地址驱动 | 0.198 ns | 20 fF，四个字节宏共享 | 每个字节宏分配独立地址叶，保留原宏数量和时序 |
| 上游 OAI221 | 0.310 ns | 24.99 fF | 已记录；观察本轮分发后的剩余控制锥，不先修改未定位字段 |

[名义负载清单](F:/CPU2026Proofs/DD_existing_mapped_loads_20261005/loads.json)另数出根节点 190 个输入引脚、名义负载 98.043126 fF。该值是 Liberty 明示电容之和，和 STA 采用的方向相关电容 96.36 fF 口径不同。[只读反向锥](F:/CPU2026Proofs/DD_existing_mapped_loads_20261005/cones.json)确认另一高负载 AXI enabled_words 别名锥来自 LSQ 的选中地址/访问大小及转发逻辑；别名不能独占归属某个模块。

## 正确性状态

三个有限定向程序全部通过：[结果](F:/CPU2026CourseRuns/architecture_DD_20261005/directed_cases/results.json)。rv32m_edges 为 60 个检查、376 周期，lsq_wrap_forward 为 96 个检查、1,015 周期，recovery_reuse 为 80 个检查、1,228 周期。它们复用同一原生 Verilator CPU，没有再编译 RTL；不代表完整内部状态覆盖。

原十九项 correctness 已结束，**16 项通过、3 项失败**；`correctness_pi`、`correctness_qsort`、`correctness_tak` 均在 1,000,000 周期处超时。最终状态见 [原始日志](F:/CPU2026CourseRuns/architecture_DD_20261005/result/correctness.log)和[独立进度记录](F:/CPU2026CourseRuns/architecture_DD_20261005/measurement_progress.json)。没有放宽时间/周期上限，也没有为失败用例自动再跑。不能宣称整套正确性通过或 Tier3 达标。

DD 根 PID 40700 已结束，输入和结果保留。主工作树随后采用并完成 DF1 的一次测量，结果为 294.337453 MHz、IPC 0.7823728642、含 SRAM 面积 51,368.530674 μm²，见 [DF1 结果](E:/Verilog_cpu/reports/frequency_DF1_measurement_2026-10-05.md)。当前主工作树又更新为未测 DK；各版指标分别归属自己的冻结身份。
