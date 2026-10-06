# DM1 原生课程测量：302.154 MHz，频率门槛达到

DM1 六项源码改造已完成一批统一 Windows 原生测量。最终 [课程结果](F:/CPU2026CourseRuns/architecture_DM1_20261005/result/result.json)状态为 `COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE`。driver PID 69172 已结束，不是仅凭旧状态文件判定完成；2026-10-05 03:58:56 的进程观察、完成 identity 和结果/报告/IPC 的 SHA 均已核对。

| 指标 | 已测 DF1 | 本次 DM1 | 相对 DF1 |
|---|---:|---:|---:|
| Fmax | 294.337453291 MHz | **302.154027737 MHz** | **+2.655651%** |
| 最小周期 | 3.3974609375 ns | **3.3095703125 ns** | 缩短 0.087890625 ns |
| 总面积，含 SRAM | 51,368.530674 μm² | **51,130.672554 μm²** | −0.463042%，减少 237.858120 μm² |
| IPC，原六项动态指令数 GEOMEAN | 0.782372864215 | **0.782372864215** | 0%，每项周期都相同 |

300 MHz 对应 3.3333333333 ns；本次周期余量约 **0.0237630208 ns（23.8 ps）**。这是课程库、理想时钟和无互连寄生口径的 Fmax，不扩大为真实布局布线后的频率保证。组合改造的实际增益是 2.66%，不能称为频率翻倍；它将最新已测版本从未满足 300 MHz 推过该门槛。

面积组成：逻辑 43,305.005700 μm²；其中 sequential 11,061.846000 μm²、combinational 32,243.159700 μm²；SRAM 7,825.666854 μm²。正常整数十级结构、原 39 项课程配置、latency10、缓存与队列容量保持。源码增加的 80 位关联状态已在本次综合总面积中计价，未用手工声明位数替代真实面积。

## 本批范围与身份

[测试前报告](E:/Verilog_cpu/reports/frequency_batch_DM1_pretest_2026-10-05.md)先交付，随后启动后台测量。一次课程综合/STA、一次 native CPU build、原六项 perf 各一次；Windows 归档问题的续接复用已有对象，没有重新编译 RTL。综合用时 1456.5 秒，六项 perf 用时 346.8 秒；两者并行运行，时间不能相加当作总耗时。没有使用 WSL。

冻结 manifest SHA256：`752cbc61415c193c4dd9a5a4b4aa009e7cd99bb0a387acb143e3763c1949725e`。主工作树 40 项活动输入与冻结 157 项输入的身份保持；[measurement identity](F:/CPU2026CourseRuns/architecture_DM1_20261005/result/measurement_identity.json)与该 manifest 一致，CPU executable SHA256 `40878a37b02717c012fb468440c8349187f527434e932a7c516ebdfb531c9fcd`。

原课程框架 `54fc150ffc290f52aa024209ffb9a29d43856f6d` 与 cases `29f980727f7d99a1842a58f34091c7579ba3fe85`；Yosys0.63、ABC、OpenSTA3.1.0、Verilator5.020 的固定 source commits、ASAP7 RVT TT 与 FakeRAM、约束和原脚本保持。已核对工具 manifest、库与课程输入的 digest。原 perf 程序实际返回结果通过，IPC 使用其 `metrics.json` 的 dynamic_instructions，而非流水提交猜测计数。

| perf | 周期数 | IPC |
|---|---:|---:|
| median | 12441 | 0.559520939 |
| multiply | 32802 | 0.662215719 |
| qsort | 259022 | 0.540108562 |
| rsort | 169514 | 1.154589001 |
| towers | 5889 | 0.896247241 |
| vvadd | 4085 | 1.107466340 |

两个既有短程序复用 exact CPU，各运行一次：[结果](F:/CPU2026CourseRuns/architecture_DM1_20261005/directed_cases/results.json)为 `lsq_wrap_forward` 96 项/1015 周期和 `recovery_reuse` 80 项/1228 周期，全部 PASS，周期与 DF1 相同。这覆盖有限内存与恢复场景，不证明所有内部关联状态或全 RV32IM。DM1 未自动运行十九项 correctness，不能填成 19/19。

## 新的最慢路径

只解析课程已经发布的五条最差样本，没有再调用 STA。它们的精确 text arrival 均为 **3.2491 ns**，startpoint 为 `_625574_/QN`，endpoint 依次是 `_627348_/D`、`_627521_/D`、`_628732_/D`、`_629424_/D`、`_628559_/D`。原约束请求 2 ns，因此约 −1.309 ns 的 slack 针对 500 MHz 请求；不能把它当成 300 MHz 下仍违例。

| 新路径中的已命名边界 | 累计到达时间，ns |
|---|---:|
| LSQ report_bound_tree 输入 bit4 | 0.3185 |
| report row10 的选择分发 | 0.7724 |
| completion source5 的 ROB 查询输入 | 1.0214 |
| ROB live read 第63行选择 | 1.1420 |
| completion lane2/source1 的 payload 选择 | 1.7280 |
| PRF write_address_tree bit16 | 1.9668 |
| PRF read port6 的 bypass_choice 输入 | 2.1490 |
| read port6 的 bypass 分发叶 | 2.2384 |
| 最终 endpoint D | 3.2491 |

这些是同一路径的累计时间，不是可独立相加的优化收益。source_path 的命名边界说明最慢锥已经穿过完成仲裁与 PRF 写回旁路进入分配；旧 RS 共享 store AGU 不再出现在这五条最差样本中。随后长算术链与 [分配时 store 地址加法](E:/Verilog_cpu/rtl/backend/rv32_backend_joint.v:825)相符，但没有仅凭自动编号宣称已把每个端点精确对应到某个 RTL 数组行。

[课程报告解析](F:/CPU2026Proofs/DM1_existing_reports_20261005/summary.json)、[现成 mapped 路径与门延迟](F:/CPU2026Proofs/DM1_mapped_paths_20261005/saved_path_analysis.json)均保留输入 SHA。另对 normal Verilog 与 JSON 做了 cell 顺序/类型/公开名称及 1,575,364 个 scalar port 的连接对应核对；1,302 个 vector/expression port 未验证，起终点 QN 也没有公开源码别名，所以不把它称为全层级等价证明或完整端点归属清单。

## 尚未满足的要求与下一步

相对原课程基准面积 46,309.693490 μm²、IPC 0.980127940650，本次面积 **+10.410302%**、IPC **−20.176455%**。原 ±10% 条件尚未满足；面积距离其上界还需减少约 190.01 μm²，IPC 恢复到下界还需约 +12.75%。原 Tier3 的面积≤36,000 μm²、IPC≥1.0985 与完整正确性也没有达成。频率门槛达到不等于全部目标完成。

DD 的原默认一百万周期全套结果仍为 16/19，pi/qsort/tak 在该上限超时。本轮只读取既有课程数据发现，这三项参考 dynamic_instructions 分别是 3,117,658 / 1,097,111 / 1,221,227；若要在一百万周期完成，平均 IPC 至少需 3.117658 / 1.097111 / 1.221227。它们的失败证据是周期上限，不是错值；这也不能反过来证明功能正确。本次没有更改上限、重跑或删除失败记录。

已准备的 DN 和 DO1 仍未采用、未测。[后续报告](E:/Verilog_cpu/reports/frequency_DM1_background_directions_2026-10-05.md)中的启用条件没有发生：现有新最慢路径已迁移，不能为了使用已写好的候选继续测试旧锥。先保留已测 DM1，围绕分配时地址运算、完成/PRF 边界以及实际吞吐瓶颈发展后续实现；下一批必须先完成组合并交付测试前报告，再测量。目标保持进行中，不以已达到的频率替代尚未满足的 IPC、面积与正确性要求。
