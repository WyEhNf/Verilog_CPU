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

主工作树随后继续更新到独立 **AM 未测试实现**；L1 的结果属于自己的冻结源码。最新修改与剩余方案见 [结构重构记录](E:/Verilog_cpu/reports/frequency_rtl_restructure_2026-10-04.md)。AM 未启动硬件工具，不能将 L1 IPC 或基线频率视为 AM 的结果。
