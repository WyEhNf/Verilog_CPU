# 结构批次后台测量记录

完整范围与取舍见 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_L_pretest_2026-10-04.md)。课程标准实测基线仍为 32.3978865441 MHz、IPC 0.98012794065、总面积 46309.6934939443 µm²。L1 已有六项 IPC 结果，综合失败，没有候选频率或面积结果。

## L 首次构建

Windows 原生后台进程 PID 65364。Verilator 报两个 `PINNOTFOUND`：Icache parent 信号替换意外改了 MSHR 子模块的 named port `.if_req_pc_i`、`.if_req_epoch_i`。未生成可用 CPU，未进入 IPC/正确性运行。此快照的后台构建/综合树已停止，避免测量无效接口；日志及源码原样保留于 [architecture_L_20261004](F:/CPU2026CourseRuns/architecture_L_20261004/native_build/build.log)。

## L1 接口修正

仅修复上述两处端口标识，信号仍为 `lookup_req_pc`、`lookup_req_epoch`，没有增删架构、阶段、寄存或 SRAM。源码准备脚本也修正了同一替换规则。修正版独立候选 [L1_repaired_icache_ports](F:/CPU2026Candidates/frequency_research_20261003/L1_repaired_icache_ports/candidate.json)，独立冻结快照 [architecture_L1_20261004](F:/CPU2026CourseRuns/architecture_L1_20261004/source_manifest.json)。

测试继续使用测试前报告中的统一批次、工具版本与课程规范。这是首次编译错误修复，不能报告频率收益、测试通过或 ±10% 达成。后续状态与结果另行追加。

## L1：六项 perf 已完成

后台进程 PID 60712；原生 Verilator CPU `build_identity.json` 为 COMPLETE。六项原课程 perf 输出已全部匹配，内存延迟仍为 10；完整 correctness 随后启动。综合的 elaboration 完成后，RAM 检查拒绝外部库缓冲器，未进入映射或 STA。

| benchmark | 官方动态指令 | 新 cycles | 新 IPC |
|---|---:|---:|---:|
| median | 6961 | 11905 | 0.5847 |
| multiply | 21722 | 32174 | 0.6751 |
| qsort | 139900 | 248703 | 0.5625 |
| rsort | 195719 | 166134 | 1.1781 |
| towers | 5278 | 5775 | 0.9139 |
| vvadd | 4524 | 4112 | 1.1002 |

精确几何平均 IPC **0.8004591469676289**，较同规范基线 **0.9801279406499007** 下降 **18.331157212306138%**，**不满足 ±10%**。来源 [perf.log](F:/CPU2026CourseRuns/architecture_L1_20261004/result/perf.log)与只读汇总 [perf_progress.json](F:/CPU2026CourseRuns/architecture_L1_20261004/result/perf_progress.json)。汇总没有调用任何仿真器或追加测试。

检查官方 `perf_multiply/program.S` 后确认该程序使用 RV32I 位移/加法/分支进行软件乘法，无 MUL/DIV 指令；上层 MDU 本来也支持同边沿补充请求。因此不能把 multiply 名称下的退步归因于乘法器拆分或假设 MDU 是单项串行。当前优先分析新增取指入口延迟和分支恢复等待，尚无逐项实测因果分解。

**本阶段没有新频率或面积结果，也不能把全部 19 项 correctness 记为通过。**后续独立、未测试的 M/N/O/P/Q/R 候选及第十级 dispatch 设计见 [继续研究记录](E:/Verilog_cpu/reports/frequency_next_batch_research_2026-10-04.md)和 [阶段拆分设计](E:/Verilog_cpu/reports/frequency_dispatch_stage_design_2026-10-04.md)。未为这些候选启动新测试。

## L1：课程综合拒绝，correctness 最终为 16/19

课程 `fakeram.py` 拒绝 `BUFx16f_ASAP7_75t_R` 外部黑盒，仅允许 `sram_fakeram`。此前“真实库缓冲器可直接计价”的实现假设不成立，1701 个缓冲器和其毛面积估算不能作为有效课程映射结果。不会修改课程白名单、库或面积规则。独立后续 M/N/O/P/Q/R 都继承此问题，需要先改成完整普通 RTL。

原后台测量已经结束，`correctness.log` 完整结果为 **16 passed, 3 failed**。失败名称为 `correctness_pi`、`correctness_qsort`、`correctness_tak`，均达到 `cycles=1000000` 上限。其余 16 项输出匹配。尚不能仅凭超时区分运行变慢与停滞，未启动额外诊断仿真。后台驱动最终生成 [failure.json](F:/CPU2026CourseRuns/architecture_L1_20261004/result/failure.json)，状态 INCOMPLETE，分别记录 correctness 和 synth 失败。

静态阅读课程脚本及固定版本 Yosys 源码后，继续准备普通 RTL 反相器层次分发、32 位写入分组。`keep_hierarchy` 只保留完整功能模块；实际标准门必须由原课程 ABC 产生、由原课程面积统计递归计入。最终门是否保留及负载是否改善尚未测量。

主工作树随后继续更新到独立 **CD 未测试实现**；L1 的结果属于自己的冻结源码。最新修改与剩余方案见 [结构重构记录](E:/Verilog_cpu/reports/frequency_rtl_restructure_2026-10-04.md)。CD 测试启动前不能将 L1 IPC 或基线频率视为 CD 的结果；具体统一范围见 [CD 测试前报告](E:/Verilog_cpu/reports/frequency_batch_CD_pretest_2026-10-04.md)。


## CD1：内部保留字修复与统一测量继续范围

CD 首次 Windows 原生 Verilator 编译在五个 RTL 文件报告 26 个语法错误，全部为内部名称 `matches` 与 SystemVerilog 保留字冲突。CPU 未生成，没有运行 perf/correctness；综合仍在前期处理时已停止，仅停止经 PID/command line 核对的 CD 进程树，保留 [build.log](F:/CPU2026CourseRuns/architecture_CD_20261004/native_build/build.log)、[synth.log](F:/CPU2026CourseRuns/architecture_CD_20261004/result/synth.log)和 [中断记录](F:/CPU2026CourseRuns/architecture_CD_20261004/interruption.json)。CD 没有 IPC、频率或面积结果。

CD1 只把 27 处完整内部标识符 `matches` 改为 `row_match_mask`，五个文件的端口、方程、状态、参数、边沿和架构均未改。它继续同一批测量范围，没有加入新优化或独立测试。新的 23-file 实现、157-file 冻结输入见 [architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)，源码前版本保留在 [pre_CD1](F:/CPU2026Candidates/pre_CD1_worktree_20261004/backup.json)。启动前的完整范围见 [CD1 测试前报告](E:/Verilog_cpu/reports/frequency_batch_CD1_pretest_2026-10-04.md)。

## CD1：原生构建与映射继续推进

2026-10-04 10:31 左右核对原后台根 PID **78248** 的命令行仍对应 CD1。Verilator 已完成生成与 C++ 编译；首次 make 在 Windows 工具路径归档处进入已记录的 host 兼容恢复，原驱动自动使用 `--resume-generated` 继续原对象归档/链接，没有重新生成 RTL 或启动另一批硬件测试。恢复日志见 [link_resume.log](F:/CPU2026CourseRuns/architecture_CD1_20261004/native_build/link_resume.log)，原日志完整保留。

课程 elaboration 进程自然完成，原 SRAM 预处理之后已进入固定的第二阶段综合映射，新的 Yosys PID **42608**；这是同一脚本的下一阶段。此前 elaboration PID 40768 的 CPU 时间持续增加约 35 分钟后退出，不能将长时间日志未刷新误判为停止。当前尚无 report.json、ipc.json 或最终 result.json，不能报告频率/面积/IPC 成功。

运行期间只继续源码/原始资料研究，并准备读取现成结果的汇总工具；冻结实现保持不变。新增条件方案及固定 ABC 流程的精确版本证据见 [冻结后研究](E:/Verilog_cpu/reports/frequency_postfreeze_research_2026-10-04.md)。

2026-10-04 10:33 核对：`native_build/build_identity.json` 为 **COMPLETE**，原 Windows make 恢复成功并完成链接，原驱动已开始本批六项 perf。最先完成的两项为 median 6961 instructions / 12441 cycles、multiply 21722 / 32802，输出经过原课程答案比较；完整六项结果尚未产生，不能报告最终 GEOMEAN，也不能据此判定 correctness suite。第二阶段 Yosys PID 42608 的 CPU 时间持续增加，已有 361568519-byte elaborated.json；尚无映射最终面积或 STA 频率报告。读取这些现成日志没有追加测试。

## CD1：六项课程 perf 完整结果

同一后台驱动已完成一次六项 perf，原课程答案比较全部匹配，耗时 299.6 s，内存延迟仍为 10。完整结果 [ipc.json](F:/CPU2026CourseRuns/architecture_CD1_20261004/result/ipc.json)；当前数据属于 CD1 的冻结源码，未启动补测。

| benchmark | 官方动态指令 | CD1 cycles | CD1 IPC |
|---|---:|---:|---:|
| median | 6961 | 12441 | 0.559520939 |
| multiply | 21722 | 32802 | 0.662215719 |
| qsort | 139900 | 259022 | 0.540108562 |
| rsort | 195719 | 169514 | 1.154589001 |
| towers | 5278 | 5889 | 0.896247241 |
| vvadd | 4524 | 4085 | 1.107466340 |

精确 GEOMEAN **0.7823728642153719**，较同规范完整基线 **0.9801279406499007** 下降 **20.176455361878766%**，**不满足此前 ±10% 控制范围，也未达 Tier3 IPC 1.0985**。当前首先取得并改善频率，随后必须恢复吞吐；不能将这种下降隐藏为“可控”，也不能把它直接归因于某一个修改。19 项 correctness 已由原驱动按原测试前范围继续运行；综合映射仍在运行，当前没有新 Fmax 或面积结果。

## CD1：课程综合与 STA 完成

原课程脚本已完成，耗时 3275.4 s。输入身份、全部冻结源码和所用库的 SHA 已由现成报告读取工具核对；没有调用额外 EDA。原报告 [report.json](F:/CPU2026CourseRuns/architecture_CD1_20261004/result/synth/opt/report.json)，解读及路径样本见 [summary.md](F:/CPU2026Proofs/CD1_existing_reports_20261004/summary.md)。正确性仍在运行，因此这不是整个测量通过或 Tier3 达标。

| 指标 | CD1 | 同规范基线 | 变化/门槛 |
|---|---:|---:|---|
| Fmax MHz | 99.65936739659368 | 32.39788654411997 | +207.6107%，仍低于 300 |
| 最小周期 ns | 10.0341796875 | 30.8662109375 | 明显缩短，仍高于 3.3333 |
| 总面积 µm²，含 SRAM | 49851.29213392186 | 46309.69349394434 | +7.64764%，在 ±10% 内；高于 Tier3 36000 |
| IPC GEOMEAN | 0.7823728642153719 | 0.9801279406499007 | −20.17646%，超出 ±10%；低于 Tier3 1.0985 |

CD1 面积拆分：组合 30987.982079921854、时序 11037.6432、SRAM 7825.666854000001 µm²。300 MHz 尚未达成，目标继续进行。

五条最慢样本都来自 Dcache metadata bank 到另一 metadata bank。共同最大门 `_381339_` 为 AOI31xp33，1255 个实际负载、572.3894 fF，单门延迟 6.6391 ns；其输出 slew 14.3106 ns，又使下一 INV 延迟 2.4430 ns。这两段约占最慢 9.9780 ns 到达时间的 91%。它的输出名字是 `g_mshr_payload_owner[0].victim_selector.values_i[74]`，按 42-bit packet 拼接回溯为 **prefetch_victim_entry[0]**，不能因 net 的别名把根因误写成 MSHR payload 选择器。本地 metadata decode 保留了，但同一最终输入仍直接驱动 64 个 bank，负载没有因此变小。

依据该路径，已准备独立未测试候选 [CE](F:/CPU2026Candidates/frequency_research_20261003/CE_dcache_metadata_input_distribution/candidate.json)：对最终 metadata action、entry、query set/acceptance 等输入进行组合树分发，每个 leaf 只送一个原有 metadata owner。不改边沿、状态、优先级、缓存容量、SRAM 或课程流程；相对 CD1 仅修改 Dcache nonblocking 一个文件。继续检查剩余消费者和其他结构后才汇报下一次统一测试。CD1 的冻结测量和主工作树保留，CE 尚未采用或测试，其频率和面积未知。

当前 correctness 已观察到 `correctness_pi` 在 1000000 cycles 超时，原驱动继续运行 qsort 等剩余项。完整 suite 已不能视为全通过，最终通过/失败数量尚未齐全。此前 pending-branch 修复及物理 wake 的架构推理不能覆盖这项失败；不能声称 CD1 已修复 L1 的全部正确性问题。暂不补跑诊断测试或修改课程周期上限。


## CD1 正确性结束与 CM 未测试实现

CD1 原后台驱动已结束，正确性 **16/19**，pi、qsort、tak 均在课程 1000000 周期上限超时；[failure.json](F:/CPU2026CourseRuns/architecture_CD1_20261004/result/failure.json) 为 INCOMPLETE。Fmax 99.65936739659368 MHz、IPC 0.7823728642153719 和含 SRAM 面积 49851.29213392186 µm² 仍属于 CD1。没有追加诊断仿真或增加周期上限。

主工作树现采用 CM 的八组后续修改，157-file 输入已冻结；**测试尚未启动**，CM 的频率、面积、IPC 和正确性未知。相对 CD1 新增四个 RTL 文件的修改，未增加功能寄存位或流水级。负载定位、参数/优先级推导、已实施修改以及仍可发展的架构方向见 [CM 实现报告](E:/Verilog_cpu/reports/frequency_batch_CM_implementation_2026-10-04.md)。


## CN：请求宽数据资格继续分组，仍未测试

当前工作树由 CM 更新为 CN，第九组修改把 LSQ 的 request-data 选择移至 32 位源并复用 byte insertion，最终 request-valid 按 16 位分组且保留在移位之后。原课程冻结 157-file 输入、备份及身份记录完成；本次仅做源码与现成网表阅读，没有启动硬件测试。详见 [CN 当前实现](E:/Verilog_cpu/reports/frequency_batch_CN_implementation_2026-10-04.md)。旧 CD1 数字仍属于旧源码，CN 所有指标未知。


## CR：DIV、ROB、MDU 和 Icache 继续重排，仍未测试

主工作树更新为 CR，在 CN 上增加四组组合/原边沿写入重排；157-file 课程输入已冻结，CN 备份及 CO/CP/CQ 中间候选保留。十级普通整数流水、容量、课程参数与 SRAM 不变，没有主动增加功能状态。未启动新编译、综合、STA、仿真或形式验证。CR 的 Fmax、IPC、面积和正确性全部未知；最近已测 CD1 数字及 16/19 的失败仍属于旧版本。人工语义推导、负载证据和剩余可行动检查见 [CR 实现报告](E:/Verilog_cpu/reports/frequency_batch_CR_implementation_2026-10-04.md)。


## CU1：MUL、Dcache tag 端口与 ROB reclaim 继续重排，仍未测试

主工作树采用 CU1，继承 CR 并增加三组结构修改；157-file 输入和 CR 备份已保存。十级普通整数流水、功能状态位数、课程参数/版本/延迟不变，按课程 fakeram lane 规则保留 tag SRAM 宏形状与数量。源码身份核对通过，但没有启动任何新 HDL/EDA/仿真测试，所有 CU1 指标未知。负载证据、源码推导和剩余方向见 [CU1 实现报告](E:/Verilog_cpu/reports/frequency_batch_CU1_implementation_2026-10-04.md)。


## CV：LSQ report 与物理目的并行选择，未测试

主工作树采用 CV，继承 CU1 并融合 LSQ report/目的选择。原 96 位物理表移入 LSQ，删除返回后的第二次读取，report 67→73 位但分组仍五个；无新增寄存器或周期。源码和 157 个冻结输入身份一致，没有启动新硬件测试。当前指标全部未知，最近 CD1 测量独立保留。详见 [CV 实现报告](E:/Verilog_cpu/reports/frequency_batch_CV_implementation_2026-10-04.md)。


## CY：低排名直接选择与本地取消/早期唤醒，未测试

主工作树采用 CY，继承 CV/CU1，再加入 decoded low-rank RS、完整 ALU/MDU 本地恢复取消、真实 MDU busy、ALU/MDU 早期 wake 资格分离。LSQ wake 与全部 completion/PRF/ROB generation 防护保留。十级普通流水、课程版本/容量/延迟仍不变，无新增功能寄存器。157 个冻结输入与 40 个活动源码身份一致；没有启动新 HDL/EDA/仿真测试，所有当前指标未知。详见 [CY 实现报告](E:/Verilog_cpu/reports/frequency_batch_CY_implementation_2026-10-04.md)。


## DD：2026-10-05，算术与 LSQ 环形顺序继续重排，采用时未测试

主工作树采用 DD，继承 CY 并加入 carry-select tails、radix4 Booth 三/三层 CSA、load 本地 wake、LSQ 一位环形顺序 tournament 与静态 hazard 化简。十级普通流水、课程 39 项配置/版本/容量/内存延迟 10 保留；MUL S1 少声明 128 位，实际面积未知。40 个活动源码和 157 个冻结输入身份一致；没有启动新 HDL/EDA/仿真测试，所有当前指标未知。详见 [DD 实现报告](E:/Verilog_cpu/reports/frequency_batch_DD_implementation_2026-10-05.md)与 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_DD_pretest_2026-10-05.md)。

## DD 实测与 DF1 新结构，2026-10-05

DD 完成原生课程 STA 和六项 IPC：273.943285 MHz / 3.650390625 ns、IPC 0.7823728642、面积含 SRAM 51,233.753154 μm²。频率尚低于 300 MHz，IPC 比课程基准低 20.1765%，面积高 10.6329%。三个有限程序全部通过；原完整 correctness 仍运行，已观察 pi/qsort 一百万周期超时。详见 [DD 测量报告](E:/Verilog_cpu/reports/frequency_DD_measurement_2026-10-05.md)。

主工作树改为 DF1：每 way 一次 SRAM 命令译码、并行地址选择与每字节宏分发；LSQ 每行局部 forward query、共享七个相对 byte windows、局部八位路由。十级、课程 39 项配置及容量/版本/延迟不变。40/157 文件身份一致，只比 DD 改两个 RTL；没有开始 DF1 新测试。已写 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_DF1_pretest_2026-10-05.md)。旧 DD 冻结输入/进程/日志保留，其结果不属于 DF1。

## DF1 测量结束与 DK 新实现，2026-10-05

上述 DF1 采用时未测；此后原生后台批次完成，实测 **294.337453291 MHz / 3.3974609375 ns**、IPC **0.782372864215**、总面积含 SRAM **51,368.530674 μm²**。对 DD 频率提高 7.4447%、面积增加 0.2631%、六项 perf 周期相同。两个有限程序通过 176 个检查；DF1 十九项完整 correctness 未跑。DD 原完整检查最终为 16 passed / 3 failed，pi/qsort/tak 一百万周期超时。见 [DF1 测量结果](E:/Verilog_cpu/reports/frequency_DF1_measurement_2026-10-05.md)。

新最慢锥转为 LSQ report→取消资格→RS wake→store 地址，五条样本均无超载门。主工作树采用 **DK**，组合逐字节 refill merge 资格、逐行 report cancel 预计算、直接 one-hot 环形 store/RS 选择和共享地址 carry prefix。相对 DF1 改五个 RTL，十级与原 39 项参数保持，40/157 文件身份已保存；**DK 尚未测试，当前频率/IPC/面积全部未知**。现有源码推导及备选架构方向见 [DK 测试前报告](E:/Verilog_cpu/reports/frequency_batch_DK_pretest_2026-10-05.md)。没有因为完成本报告而自动启动测量。

## DM1：关联生命周期与报告范围重排，仍未测试

继续完成 DL/DL1 的 dispatch-owned LSQ→RS links 与 DM/DM1 的 report membership 代数重排，主工作树采用 **DM1**。新 link 以 RS 真实 allocation/release 更新，声明新增 80 位状态、没有新指令周期；store 地址探测的 192 对完整 tag 关联替换为 4 位 owner 索引。report 范围保留原 queue mask/slot 截断/empty/full 语义，不依赖 tail 关系。DK 及中间源候选均未测、独立保留；157-file 新冻结和 DK 备份保存。六组组合已完成源审阅，当前各指标均未知，最近可信数字仍属于 DF1。详见 [DM1 测试前报告](E:/Verilog_cpu/reports/frequency_batch_DM1_pretest_2026-10-05.md)；本轮未启动 HDL/EDA/仿真。
