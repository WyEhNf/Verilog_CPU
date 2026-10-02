# ROB 分银行分配写入候选（2026-10-02）

**10:54新验证结果**：clean baseline首套比较也明确失败于208未证明点，已保留，不据此把缺口归因于原始多驱动。另一个直接原ROB的证明使用普通 `opt_clean -purge` 清理未使用public scratch别名，**不改RTL、综合、输入或任何实际模块端口**；额外核对gold/gate全部端口方向/位宽完全一致、generation_mem与generation_next_mem各容量×GEN位都仍在。BE1/ROB8已证明4196个equiv、未证明0，BE2/ROB8也已通过，BE4与其余六套仍在测。证据 `F:/CPU2026Proofs/rob_banked_allocation_purged_formal_smoke_v1_20261002`，不把证明策略变化当作PPA收益，也不称所有配置/CPU已证明。v2实际RTL SHA `3361098140ceadd09a2af9495fa05f866c7a51f2907513591fc0d083f3ec147f`、显式开启48协议完成；此前所有失败和对照都保留。

过程scratch拆分（不含银行分配）独立ROB基线bank0的完整PPA现已完成：组合11108.254140、时序3842.413200、实际SRAM0，总面积14950.667340µm²，Fmax71.08642832349878MHz、14.0673828125ns，原检查/五库/default ABC与所有实际端口保留。bank1仍在展开；该组件范围与CPU内常量传播/负载不同，不能直接从旧整机面积相减，分配银行候选仍未测PPA。

**10:39更新**：v2显式开启48/48协议已 COMPLETE，证据 `F:/CPU2026Proofs/rob_banked_allocation_protocol_full_v2_20261002/report.json`；v2直接原ROB的首套等价仍有相同208未证明点，失败保留，scratch分名未解决证明缺口。下一独立实际模块比较使用已经八套/51464equiv证明通过的过程scratch拆分候选作gold，以隔离分配写布局变化，证据 `F:/CPU2026Proofs/rob_banked_allocation_clean_formal_smoke_v1_20261002` 正在运行；保留全部generation等状态和所有输入/输出，没有删除失败点或添加输入假设。它是针对明确clean baseline的组件证明，不是直接原CPU证明或正式成绩，证明完成及组合证书的配置覆盖都还需要核验。下文“v2在测”仅保留历史时刻。

目标仍是同一当前整机配置满足完整 Tier3（36000µm²/1.0985/300MHz），不缩减 RV32IM、访存、OoO 或严格顺序提交范围；Pi冻结。本候选未接入主树，未得到新CPU分数。

## 实际实现

`F:/CPU2026Candidates/rob_banked_allocation_20261002` 在已经协议验证的真实ROB分银行读/紧凑指针/过程scratch拆分候选上新增默认关闭 `ALLOC_BANKED_WRITE=0/1`。ROB容量≥发射宽度时，每个 modulo-BE 物理bank从分配lane中选择一个完整payload，并以静态行使能写入实际ROB状态，尝试避免每一行重复多路payload选择。不改变CDB/ACK/退休/分配的写优先级、generation推进、任何端口/字段或流水拍；容量小于发射宽度走原fallback。

特别保留原分配写槽位 `tail+lane`，而不是改成分配计数。这也保留任意输入的invalid-lane hole行为；不假设输入只能为正常前缀。allocation不额外清零value/store地址/数据字段，checkpoint实现0仍完整写入，模式1仍为原无快照存储行为。

第一候选ROB SHA256 `e32006eb5c7da44da07c52a4a78770211a523fea5a82aee8dceb5ddd146a369a`；原全协议开启版48/48、关闭版48/48完成，遍历全部物理head、满宽逆序完成和停顿字段检查，保留所有原store/recovery/stale-generation/HALT协议。证据分别为 `F:/CPU2026Proofs/rob_banked_allocation_protocol_full_v1_20261002/report.json` 和 `F:/CPU2026Proofs/rob_banked_allocation_disabled_protocol_v1_20261002/report.json`。开启版采用冻结TB默认参数1且有dut参数一致断言；关闭版机器parameters显式为0。

## 尚未通过的证明与后续候选

第一套BE1/ROB8实际整模块等价在 `F:/CPU2026Proofs/rob_banked_allocation_formal_smoke_v1_20261002` 已明确失败于208个未证明点，主要为generation链路。这不是证明通过，也没有导出足以声称真实功能错误的反例；不能仅凭协议通过接入主树。

新候选 `F:/CPU2026Candidates/rob_banked_allocation_v2_20261002` 只把按物理行顺序求值的银行generation scratch与原按lane顺序求值的scratch分开命名。实际架构状态、完整输出和所有输入仍由同一整模块证明比较，不删除generation状态或收窄输入；目的是检查是否存在名称匹配过度的证明问题，不预先认定原因已解决。显式模式1的48项协议和八套小/边缘完整模块等价在对应 v2证据目录运行。

尚未开始银行分配候选PPA，没有面积下降或提频结论。原过程scratch隔离（未含银行分配）的严格实际ROB组件PPA仍在 `F:/CPU2026Probes/rob_process_locals_actual_rob_v1_20261002` 映射；完整CPU两套当前源码PPA仍live，不能用组件或冻结旧版补齐三项成绩。
