# 后续架构方向：rename 与 operand/dispatch 分成独立阶段

状态：**AD 已实现，CD1 已测，当前 CM 继承同一边界且尚未测试**。CD1 Fmax 为 99.65936739659368 MHz，IPC 0.7823728642153719，正确性 16/19；这些属于整个冻结批次，不能归因于单独 AD 阶段。CM 继续保留普通整数十级和原 R→D 资源保留/握手，最新未测试修改见 [CM 实现报告](E:/Verilog_cpu/reports/frequency_batch_CM_implementation_2026-10-04.md)。

现有同一个周期包含 free-list 选择、同束 RAT RAW/WAW 旁路、PRF 值/ready 查询、物理 tag 查询、同束源依赖修正、提前 store 地址加法及 RS/LSQ 分配字段选择。仅把 issue 输出寄存并不能切断这条 rename 到分配存储的前向链。

## 拆分边界

R 阶段进行 rename、PRF destination allocation、ROB allocation；把 ROB tag、源物理编号、新物理编号、PC/op/立即数/预测/访存字段放入一项四宽 packet 槽。指令原字及逻辑 rd 已写入 ROB，不重复保存在 D。D 阶段从寄存源编号查 PRF/tag，形成 RS 操作数及 LSQ 字段，完成 RS/LSQ allocation。普通整数路径在 L1 的基础上再增加一个真实阶段，达到原八级加 Icache 入口与此边界的十级；不把 multiplier/divider/recovery 内部阶段叠加称作全核固定级数。当前配置每通道 payload 160 位、tag 17 位及 valid 1 位，共新增 712 个逻辑寄存位；不是映射后面积。

一项 packet 槽支持同边沿出队/补充。若能证明 D 阶段资源已经由 R 保留，其 out-ready 只取 branch/flush 等寄存控制，不需把 RS 动态 payload 选择或 CDB ready 反馈给 R。这可以保留每拍一束的吞吐，避免使用两项整束 FF 造成额外面积。

## 资源保留的守恒关系

RS/LSQ 暂未实际写入的 packet 必须保留资源。令 F 为当前实际空位、Q 为已经 rename 而未 dispatch 的保留数量、A 为本拍新 rename 保留数量、D 为本拍真正 dispatch 数量、R≥0 为本拍释放数量，则：

`F' = F-D+R`，`Q' = Q-D+A`，所以 `F'-Q' = F-Q-A+R`。

因此下一拍保守 credit 可以寄存 `min(BE_WIDTH,max(F-Q-A,0))`，不需要组合预测同拍释放，也不需要用 D 阶段数据路径作上游 ready。对 LSQ 的 Q/A 使用 memory 指令数量，对 RS 使用需占用的条目数量。ROB 在 R 阶段已实际分配，沿用它自身的 F-A+R 计数；物理寄存器由 M 的寄存候选池供应。

初始化 credit 为零；R 只接收不超过寄存额度的前缀。由上述式子，下一拍实际空位至少覆盖所有保留项。此推理仍需实现中与真实 alloc_fire 数量对齐，不能只是计数正确但数据侧消耗另一束。

## 所有权和恢复

R 分配后，pending packet 的指令已属于 ROB，不能当作未分配 decode 内容全清。它们的新物理寄存器必须参与现有 killed suffix 回收；RAT 恢复也必须包含这些 ROB writer。

选择性 recovery 用当前 packet 的 ROB tag 判年龄/代数，保留更老前缀、丢弃更年轻后缀，并同步退还尚未实际写入 RS/LSQ 的保留计数。branch pending 期间暂停新 R，D 可先保留至 apply 后；已提交 store 的 LSQ/cache 状态不属于此 packet，不能清除。

源码检查确认 ROB 的新分配条目 ready 统一为零，原后端让每条接受指令占用 RS，因此没有立即提交而 packet 尚未派发的特殊绕行。ROB→LSQ 映射和 LSQ→physical destination 映射已移到 D 的实际 LSQ allocation 时记录，早于相关 memory completion/retire。

## 操作数正确性

R 已更新 destination busy/tag，D 下一周期再查询源物理编号，同束年轻指令可看到前一项的新 tag 与 not-ready。不能继续套用以活跃 frontend 输入为依据的旧 dependency 代码，所有 D 字段必须来自 packet。

WB bypass 仍需处理 D 同周期的完成；PRF ready 必须对应所读值。回收重用下，CDB 的现有 ROB generation 过滤继续作为所有权依据。只保存 payload 而引用下一束 trace flags/PC/源编号会造成跨束混淆，必须明确拆分 R 和 D 接口。

## 与 IPC 恢复的关系

L1 perf IPC 0.8004591469676，较基线下降 18.331%。本方向会再增加一个依赖阶段，本身不能被称为 IPC 修复。若采用，需要结合寄存 free-pool（免去搜索延迟）、持续取指或 R 空队列直达的权衡方案，以及明确的 fast/slow wakeup 机制评价；频率收益和总代价由新关键路径决定。

后端 `DISPATCH_PIPELINE` 默认零保留独立模块旧接口，当前 cpu_core 显式开启。单束 packet 无 D-ready 反馈，每个不冻结的边沿消费旧束并捕获新束；RS/LSQ 下一拍额度采用上述 F-Q-A 式。branch pending 冻结，恢复应用时按活跃代数和严格更老年龄筛选 valid。旧的同束依赖修正仅在直通模式使用，开启边界时依赖 R 边沿写入的 busy/tag 和 D 同拍 WB 旁路。

上述设计阶段已结束，CD1 完成全部结构修改并作[测试前汇报](E:/Verilog_cpu/reports/frequency_batch_CD1_pretest_2026-10-04.md)后才启动统一后台测量。L1 已结束且综合失败，不能为本方向提供新的 STA；CD1 冻结源码也保持原样。本次阶段状态与具体结果继续记录于[测量记录](E:/Verilog_cpu/reports/frequency_batch_measurement_2026-10-04.md)。

## 后续若采用 metadata-only RS，重新分配既有边界

若新 STA 显示 operand broadcast/issue routing 或 D-stage PRF 查询是主要瓶颈，可考虑让 RS 只保存源物理编号和就绪状态，在选择之后读取 PRF。这不能只是给当前十级再增加一个 register-read 阶段：应评估把现有 D 边界移到 RS 选择之后，R 阶段同时分配 metadata RS/LSQ，选择结果先寄存，下一拍读取 PRF/旁路，再进入 ALU。这样仍以十级为目标，同时把晚到 wake/排序与 PRF 读分开。

该方案没有实施，必须先处理 R 的 rename/同束源依赖到 RS metadata allocation、RS/LSQ credit 的实际消费边沿、同束 busy 标志、held producer 尚未写 PRF 时的旁路、早期 store base 额外读端口和分支恢复。当前 RS 两项 issue FIFO 保存完整值；仅把它改成物理编号 FIFO，然后在输出端直接串 PRF 与 ALU，会制造新的长路径。物理就绪不能简单等同 PRF 已写入：直接 producer wake 在 CDB 尚未接受时已可见；必须在读阶段继续取得该 held value 或明确等待其写入。

若沿用现有 issue FIFO 中两个寄存项，需区分弹性容量与流水阶段：它们当前是同一 FIFO 的两行，不是两个顺次的执行阶段，不能靠改名称声称已存在独立 register-read 边界。所有边界移动必须由具体数据和握手的寄存路径证明。当前尚无证据证明这个方案比 CD1 的实际最慢路径更有效，故暂不扩大冻结实现或补测。
