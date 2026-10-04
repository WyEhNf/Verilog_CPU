# DF1 后台测量与 DG 独立结构研究

上一目标轮属于实现进展：DE/DF/DF1 已落地主工作树、形成新的 157-file 冻结身份并先发送 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_DF1_pretest_2026-10-05.md)，没有运行这些候选的测试。本轮在 2026-10-05 01:54:41（Asia/Shanghai）启动固定 Windows 原生后台根 PID **81648**。

本轮核对 actual process/command line 后，观察到原生 Verilator、Yosys elaborate、随后 Yosys synth/ABC 子进程依次进展。CPU 已编译完成，[构建身份](F:/CPU2026CourseRuns/architecture_DF1_20261005/native_build/build_identity.json)对应 executable SHA256 `3c4baf7c0df501431f7faa52ceb3fc1954bce1a6aa03685c5805fb2ddc695b27`，冻结 manifest 仍为 `d4596d27b02aadb38412092006592954cf72f7114e705de44aeb5b8bad6113e9`。不因旧状态或日志间隔重新启动同批。

六项原课程 perf 完成，总 IPC **0.7823728642**；median/multiply/qsort/rsort/towers/vvadd 周期仍为 12441/32802/259022/169514/5889/4085，与 DD 相同。两个有限程序 lsq_wrap_forward / recovery_reuse 完成 96/80 个架构检查、1015/1228 周期，全部返回 0，见[结果](F:/CPU2026CourseRuns/architecture_DF1_20261005/directed_cases/results.json)。它们使用同一个 exact CPU，不再编译 RTL。没有重复十九项全套，也不能据这两个程序宣称完整正确性已通过。新 STA/面积当时尚未完成，273.94 MHz 属于旧 DD。

DD 原始根完成完整检查：16 passed / 3 failed，pi/qsort/tak 均超时于 1,000,000 周期。该日志、频率/面积/IPC 与输入仍保留在 [DD 历史记录](F:/CPU2026CourseRuns/architecture_DD_20261005/measurement_progress.json)；不放宽上限，不再跑一次获取同样失败。

## DG：任务 owner 直接给普通完成仲裁资格

已生成独立 [DG 源候选](F:/CPU2026Candidates/frequency_research_20261003/DG_local_completion_eligibility/candidate.json)，只对 DF1 的 backend 多改一个文件，由 [准备工具](E:/Verilog_cpu/tools/prepare_local_completion_eligibility.py)落盘。**DG 没有采用、冻结或测试。主工作树与正在测量的输入保持 DF1。**

目前 CY/DB 只把早期 wake 的资格移到执行单元或 LSQ report owner，普通 producer_target_live 仍先查 64 行 ROB valid/generation，再进入直接 CDB 仲裁。在直接模式中，完成网络锁住的是 source index + full tag，数据留在执行单元，不存在独立排队副本。

DG 把相同的本地任务/未退役 load 资格用于这个模式的普通仲裁与接受 load-error 事件。启用条件是 `ISSUE_PIPELINE!=0 && COMPLETION_BYPASS==2`。非本地恢复或任何排队 completion 模式仍用旧全表查询；branch-training 的 ROB 查询和 ROB 最终完整 tag/generation 比较保持。这样有机会消除 MDU 和 LSQ 的两组正常存活查询，并从普通完成到 CDB 的路径移除该查询段；ALU 查询仍可能因 branch training 保留，不能承诺整个查询网全部消失或具体面积数。

## 必须成立的责任和风险

| 责任 | 本地资格依赖的源契约 |
|---|---|
| ALU/MDU 的 valid result | 未完成的 ROB 任务在源被接受前不能 done/退役/释放物理目的；valid/tag/phys/value 随反压保持 |
| 取消 | CX 的 request/current-stage/out-stage 取消在 reclaim/reallocation 前抑制年轻 valid；旧任务保留，不用全局清空 MDU |
| LSQ report | DB 的 unretired 位随完整 report packet；reported 在被接收后置位，已退役保留行不提供本地普通完成资格 |
| 直接完成锁定 | 锁住 source 与完整 tag，源被取消/失效时不允许锁定旧 payload 再写 PRF；BY0/BY1 不采用该优化 |
| ROB | `tag_matches` 仍检查 valid、slot、完整 generation；in-order commit 未变 |
| PRF | PRF 本身只比物理地址，没有独立 ROB generation；DG 的提前写入正确性依赖上述 owner 契约，不能仅用 ROB 最后拒绝 stale tag 来掩盖错误 PRF 写入 |

这是一套源级责任推导，尚未形成覆盖每一种内部状态的证明。若任一 pending request、late load、持有完成或恢复阶段会在目的释放后仍返回源 valid，就必须补 owner 生命周期，或保留该类的完整查询；不能一律删掉安全资格。本轮未用新 HDL 测试来为 DG 这些假设背书。

[BOOM 的执行单元文档](https://docs.boom-core.org/en/latest/sections/execution-stages.html)说明 wrapper 负责分支取消与退出响应资格，支持把责任放在任务所在单元这一设计方向。其 [v4 functional-unit 源码](https://github.com/riscv-boom/riscv-boom/blob/master/src/main/scala/v4/exu/execution-units/functional-unit.scala)里 ALU 与本 CPU 的反压、持有结果契约不同，不能直接移植其 ready/valid 假设，更不能据此认定 DG 正确或预估 MHz。

是否采用 DG 由 DF1 新的实际慢锥与源码责任审阅决定。若频率仍由 SRAM 命令或转发深度主导，应先处理那个锥；不会为了多做一项修改混入当前测量输入。DG 若要测量，也必须另冻身份、先报告完整组合修改，再统一原生后台测量。

## 本轮最终状态更新

随后 DF1 STA 完成：**294.337453291 MHz / 3.3974609375 ns**，含 SRAM 面积 51,368.530674 μm²。根 PID 81648 已终止，`result/result.json` 为课程测量完成；没有重启同批。五条新最差检查已转移到 LSQ report→本地取消资格→RS wake→提前 store 地址的组合链，没有超载门。完整结果见 [DF1 测量报告](E:/Verilog_cpu/reports/frequency_DF1_measurement_2026-10-05.md)。前文“STA 尚未完成”描述的是其写入时点。

DG 继续独立保留、未采用或测试。主工作树现采用四项后续重排的 **DK**，包括字节 merge 分发、LSQ 逐行预计算 cancel、store/RS one-hot 直传和共享地址 carry prefix。157-file 新身份与 DF1 备份已保存，DK 没有测试，所有新指标未知；见 [测试前报告](E:/Verilog_cpu/reports/frequency_batch_DK_pretest_2026-10-05.md)。
