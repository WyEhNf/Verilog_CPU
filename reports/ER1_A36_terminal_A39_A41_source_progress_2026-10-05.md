# ER1：A36 终态测量与 A39–A41 源码进展

记录时间：2026-10-05T11:08:38.250501+00:00。目标保持 **Fmax >300 MHz、IPC ≥1.1、包含 SRAM 的总面积 ≤36,000 μm²**。目标尚未完成。

## 已测结果与验证范围

A36 原测量已经结束；原 PID 92848 已不存在，原 manager 的 observe 再次确认终态和完整结果，没有重启。课程指定版本 Windows 原生工具链、原六项 perf、latency=10、官方答案和动态指令分子保持不变。

| 指标 | A36 | 目标 | 状态 |
| --- | ---: | ---: | --- |
| IPC 几何平均 | 0.99189779 | ≥1.1 | 还需提升 10.90% |
| Fmax | 297.242380 MHz | >300 MHz | 还差约 2.757620 MHz |
| 总面积 | 35686.138058 μm² | ≤36,000 μm² | 达标，余量 313.861942 μm² |
| SRAM 面积 | 7943.911838 μm² | 计入总面积 | 已计入 |

逻辑面积 27742.226220 μm²（组合 20004.911820、时序 7737.314400）。最小周期 3.3642578125 ns。六项 perf 退出答案全部通过；19 项完整正确性与新增 M/恢复覆盖未运行，不据此宣称完整 RV32IM 验证。

| 程序 | 参考动态指令数 | 官方仿真周期 | IPC |
| --- | ---: | ---: | ---: |
| perf_median | 6961 | 9452 | 0.736458 |
| perf_multiply | 21722 | 18273 | 1.188748 |
| perf_qsort | 139900 | 159725 | 0.875880 |
| perf_rsort | 195719 | 161366 | 1.212889 |
| perf_towers | 5278 | 5815 | 0.907653 |
| perf_vvadd | 4524 | 4010 | 1.128180 |

原始结果：[result.json](F:/CPU2026CourseRuns/ER1_A36_tier3_20261005/result/result.json)、[IPC](F:/CPU2026CourseRuns/ER1_A36_tier3_20261005/result/ipc.json)。全部 157 个冻结源文件重新核对哈希一致。旧完全验证候选 A16R2 仍独立保留（IPC 0.94636559、Fmax 367.420165 MHz、总面积 39,982.760814 μm²），不能把它的频率或正确性与 A36 指标拼接。

## 当前真实关键路径

当前 A36 最慢路径是 `_407113_/QN` → `core.g_cached_memory.g_nonblocking_icache.icache.g_instruction_line_filter.lines.g_sram_lines.g_bank[0].data.lane_0/addr_in[0]`，数据到达 3.263 ns；最后地址门驱动八个 SRAM 宏端口，40 fF，延迟 0.479 ns。A38 已针对该实际新路径去掉 hit-acceptance 对读地址的依赖，并让每个命令叶节点驱动单个宏，原容量、宏数量及读延迟不变。A37 对旧 MDU 高扇出路径的修改也保留，但不能把旧 A21 的瓶颈当作 A36 新瓶颈。

## 一次三程序观察结果

此前已先报告后执行一次 median/qsort/towers 观察；复用 A36 已构建模型，只加入只读宿主 C++ 计数。没有 RTL 重新生成、模型重编译、综合或 STA。三个程序答案通过，周期分别 9452/159725/5815，与原 A36 完全一致。观察已经结束，不重复运行。

| 程序 | 分支 pending 周期占比 | 银行选择反馈正确比例 | LSQ 满占比 | LSQ 平均占用 |
| --- | ---: | ---: | ---: | ---: |
| perf_median | 11.78% | 82.60% | 0.00% | 3.834 |
| perf_qsort | 12.64% | 78.59% | 0.00% | 3.553 |
| perf_towers | 3.07% | 77.24% | 12.92% | 11.735 |

统计分母是排除复位/停机后的 active samples（恰为官方 cycles−11），不替代官方 IPC 分母。停顿计数相互重叠，不能相加成为可回收周期；pending 时 ready RS 可能是错误路径较年轻指令，不能算作较老存活指令。预测计数包含 branch/JAL/JALR、同银行仲裁，不是单独条件方向准确率。主 I-cache 计数不包含 L0 filter 命中。D-cache miss-event 含义尚需继续从原源码归因，不据 752 次事件直接断言 752 次外存读。

证据：[三程序结果](F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json)。

## 本轮已实现源码

以下均是独立 F 盘源码候选，继承 A37/A38，**没有启动 HDL 构建、lint、仿真、综合、STA 或单元测试，没有采用到主工作树，性能指标全部未知**。

1. **A39：恢复 preview 期间较老指令继续执行。** 使用已经登记且获 ROB 验证的误预测分支，只有有效 RS 选择、环形年龄严格小于分支且在 ROB 占用内的指令可以发射；只在 descriptor 未准备好的 preview 那拍放行。apply 那拍仍禁止发射，因为 RS 的 flush 优先级会忽略正常 issue-release，简单同时放行会重复发射。共享 ALU/MDU 的 issue-valid、RS ready 和 MDU 选择资格保持一致。不新增状态或流水拍。ISSUE_PIPELINE/非选择恢复配置保留原回退。
2. **A40：紧凑 gshare、逐路准确索引训练、同拍历史恢复。** 延伸原紧凑目标/间接 BTB 到模式 2；预测时保存的每路索引随同该路有效完整标签反馈一起被同一银行 grant 选择，不用当前历史或另一条分支的索引。提前重定向同拍使用该分支的 checkpoint 加实际方向恢复 GHR，保留原 preview 方式的寄存历史。256 个 BHT 计数器和 6 位历史不缩减；仅间接 BTB 参数化 16/32/64，本配置 32 项。释放 1,280 位，新增元数据及历史声明上界 848 位；按可用位计算约净减少 644 位 /187.79 μm² 的 FF 组件。**这是状态账，不是综合总面积或 IPC 提升保证。** 表读、XOR、控制树需以后统一测量。
3. **A41：LSQ 连续两条回收。** 保留原队首回收条件；若紧随其后的条目是已完成且此前已经成功报告的 load，可同拍清空两行、head 前进两格、occupancy 减二。第二条不能是 store，不扩宽 load report/store ack，不提前提交，不加容量或状态，不绕过 reset/flush/恢复；allocation 仍按原寄存空闲量。解决每拍可分配两条而只回收一条的结构限制，收益未测。

候选：[A39](F:/CPU2026Candidates/tier3_er1_20261005/A39_recovery_preview_older_issue/candidate.json)、[A40](F:/CPU2026Candidates/tier3_er1_20261005/A40_compact_gshare_parallel_feedback/candidate.json)、[A41](F:/CPU2026Candidates/tier3_er1_20261005/A41_lsq_two_prefix_reclaim/candidate.json)。逐项源码论证与待验证场景：[A39 review](F:/CPU2026Candidates/tier3_er1_20261005/A39_source_review.json)、[A40 review](F:/CPU2026Candidates/tier3_er1_20261005/A40_source_review.json)、[A41 review](F:/CPU2026Candidates/tier3_er1_20261005/A41_source_review.json)。

## 继续工作的边界

下一步继续检查合并候选的真实前端、预测恢复和内存服务瓶颈，再确定测试批次。前端已经实现当拍 response/request chaining，LSQ 选择寄存器已允许原操作结束当拍替换，都不再当作新优化。仍有 D-cache miss/合并语义、存储服务和实际分支行为可以从既有数据与源码分析，因此本轮不提前开测。

与方向预测有关的通用依据是 [BOOM 官方 backing predictor 文档](https://docs.boom-core.org/en/latest/sections/branch-prediction/backing-predictor.html)：预测索引使用 PC 与全局历史的组合；投机历史需要快照和误预测恢复。这支持历史管理方式，不证明本 CPU 的 gshare 实际准确率、面积或 IPC。

主 E 盘工作树保持 EU，所有其记录的源文件哈希一致；冻结 A36、旧测量、宿主脚本保持原身份。优化目标不缩减为仅面积达标，下一次测试前仍先汇报。最终通过还需要同源三指标及完整正确性和 M、选择恢复、cache/转发、回压等相关覆盖。
