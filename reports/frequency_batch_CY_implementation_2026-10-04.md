# CY：结果所有权与唤醒路径重排，尚未测试

CY 继承 [CU1 的七组实现](E:/Verilog_cpu/reports/frequency_batch_CU1_implementation_2026-10-04.md)，再加入 CV、CW、CX/CX1、CY 四组。冻结输入为 [architecture_CY_20261004](F:/CPU2026CourseRuns/architecture_CY_20261004/source_manifest.json)，采用前的 CV 工作树备份在 [pre_CY](F:/CPU2026Candidates/pre_CY_worktree_20261004/backup.json)。源码候选和准备脚本均保存，未覆盖旧测量输入。

**没有启动新的 HDL 编译、lint、仿真、综合、STA 或形式验证。所有 CY 指标和正确性未知。** 普通整数流水仍为十级；没有新增功能寄存器、固定流水周期或 SRAM 位数。启用本地取消时，MDU 不再使用原三位 inflight FF 计数，busy 从已有段的占用位产生。新增组合控制和译码会影响实际面积与最慢路径，不能从状态位数承诺 ±10% 或 300 MHz。课程版本、原 39 项顶层参数、容量和内存延迟 10 不变。

## 新增四组

| 组 | 原依赖 | 实现 | 仍待测量的边界 |
|---|---|---|---|
| CV：LSQ report/目的并行选择 | 先选 completed row 的 LSQ tag，再查 16×6 位目的表 | 同一 96 位分配表移入 LSQ，目的和 value/tag 一起选择，删除第二次读取；67→73 位 report 仍为五个组 | 无额外 FF/周期；完整 ROB/LSQ 身份、错误、ready、恢复防护保留。无效 report 目的变为零，不能主张无效 payload 位逐位相等。见 [CV 详细推导](E:/Verilog_cpu/reports/frequency_batch_CV_implementation_2026-10-04.md) |
| CW：直接译码低排名 | 已有 balanced binary popcount 后，还要译码 lane0–3 | 对 issue width 1–4，平衡组合直接计算“恰好有 k 个更老 ready 项”；count≥BE_WIDTH 用全零表示；更宽配置保留原 binary rank | 年龄矩阵、ready、tie、lane 映射、发射握手不改。没有新寄存位/周期；布尔网络的真实门数与延迟未知，不能声称旧设计是线性计数 |
| CX/CX1：执行任务本地取消 | MDU 仅 whole-core flush，年轻任务依靠最后的 ROB gen 检查慢慢排空；ALU 有选择性 flush，但可选 shift 的 busy 状态需要独立覆盖 | 注册恢复描述符以 20 位 packet 分发；ALU 含 shift、MDU pending、MUL S1/S2/out、DIV prepare/iterate/finish/result、备选 iterative units 都按自身 tag 年龄取消年轻任务 | 年轻结果当拍隐藏、边沿清有效性；严格更老任务保留。独立模块默认关闭新行为。busy 从真实占用产生，取消不伪造完成。完整完成过滤继续保留 |
| CY：ALU/MDU 早期唤醒资格 | producer tag→64-row ROB valid/gen read→wake→rank→operand route | recovery-aware ALU/MDU 的有效结果直接提供 wake；完整 tag/phys/value 不改，ready 仍不串入早期 wake | load wake 和所有完成/PRF/ROB 路径仍使用原 valid/gen/recovery 检查。新结构的生命周期推导尚未经硬件验证，必须验证恢复、反压和复用 |

## CW 的计数推导

对任一子树，`match[k]` 表示它包含恰好 k 个 older-ready 叶，保留 k=0..BE_WIDTH-1。单叶的 match0=!leaf、match1=leaf，其他为零；padding/self 叶固定零。左右子树合并：`match[k] = OR(left[a] AND right[k-a])`，a=0..k。子树溢出后全部 match 为零，任何更大非负计数都不能在后续合并变成小计数，因此不会出现截位回绕和重复发射。根 match[k] 与原总计数==k 的 ready 选择策略一致。这是人工归纳推导，没有运行穷举、仿真或形式工具。ready/年龄未知值下也不主张四态逻辑逐位等价；有效已分配项的年龄关系必须由原 owner 建立。

## 本地取消与结果生命周期

packet 为 `{apply,occupancy,head,branch_relative_age}`；当前宽度 1+7+6+6=20。head/occupancy 来自已经捕获的恢复描述符，apply 使用原 `recovery_domains[6]`，没有新恢复寄存级。relative age 仍按原六位 slot 减 head 的模运算计算。MDU 的年轻项 `age>branch_age`、无效 tag 或快照区间外项取消；ALU 另取消 resolving branch 本身，即 age≥branch_age。仅 `ISSUE_PIPELINE!=0` 的 joint backend 启用；原 issue FIFO 恢复当拍停止输入输出、按 tag 保留严格更老项，branch_pending 期间不接受新的普通 issue。

| 状态 | 当拍与边沿处理 | 保留的原行为 |
|---|---|---|
| ALU held/shift | 被取消的 exec_valid 当拍为零；结果有效与 shift_busy 优先清除；禁止同拍捕获或继续 shift | 旧 payload 不必清零；严格更老结果可以保持或完成；正常接受边沿和 metadata 写入边沿不改 |
| MDU pending | 年轻 pending 不向任何单位发出 req；恢复当拍不 ref​​ill；pending_valid 清除 | 较老 pending 可向可用单位转移；正常 refill 仍与旧 req_fire 同拍 |
| MUL S1/S2/out | 每段分别形成 discard；取消允许本段释放，原更老上游可替换空出的段；禁止被取消数据进入下游 | 各段原 valid/ready、metadata 与 data 写入条件、CSA/CPA 和 MUL priority 保留 |
| DIV | 一个 tag 覆盖 prepare/iteration/finish/held result；取消时不再迭代、写缓存或发表结果，busy/valid/prepare/finish 清除 | 数值缓存的旧合法历史保留；新请求重建全部事务字段。被取消的 held slot 释放当拍不会接受替换请求，可能使较老 pending 等一拍 |
| MUL_IMPL 1/2 | 分开取消 busy operation 与 held output，禁止取消的最后一步生成 result | 算术过程与正常握手保持原样；它们也加入候选，但课程默认实例不能证明两个备选实现通过 |
| MDU busy | 来自 pending/mul/div 实际占用，取消后自然清空 | 不发出假的 completion_fire，不依赖完成计数减去一个无法表达的多段取消数量；perf_mdu_busy 是其唯一后端消费者 |

早期 wake 的人工不变量推导：

1. 每个有效 ALU/MDU 任务来自一次唯一 issue 接受，并在同边沿捕获完整 tag/物理目的；无效 FIFO payload 不能产生新有效任务。
2. 正常提交前，ROB 必须收到该任务的完成。joint backend 的 ROB completion packet 把 valid 与 `cdb_ready` 同时作为 done 资格；因此普通结果仍被源保持、尚未接受时，不能使 ROB 完成并回收它的目的。PRF 的早写与 ROB done 必须区分，不用“PRF 已写”推出任务已退休。
3. 完成接受的边沿也清除源 valid 或推进相应 stage；在目的可以正常回收、再分配前，旧普通 producer 失去 wake 资格。
4. 恢复当拍，年轻任务在本地输出上隐藏、在 apply 边沿清有效性；rename/ROB 分配在 preview→apply 区间被原 branch_pending/recovery hold 阻止。下一拍再分配已释放物理编号时，旧任务应已无有效输出。
5. 清所有路径的 reset/whole flush 仍有效；load 响应、LSQ generation 与 reported/retire 生命周期仍由原集中检查保护。CDB/PRF/ROB 的完整 generation 检查完全保留，没有减少 tag 宽度或 SRAM 返回身份字段。

这些是设计意图与源码推导，**没有功能或等价证明**。最需关注的是恢复/完成同拍、旧结果受反压、多个 MUL stage 同时取消、DIV 最后一拍取消和目的编号随后复用。应在测试前报告中列入少量针对性场景，而非为每个 gate/word 修改启动一套回归。

## 人工修正记录

CX 最初准备脚本引用了后端不存在的 `recovery_apply` 名称；在源码阅读中发现，未启动编译，也未采用到工作树。CX1 改为已有 `recovery_domains[6]`。CX 源码保留以便审阅，CY 继承的是 CX1。不能将脚本生成成功或文件哈希一致写作 HDL 语法通过。

## 借鉴的范围

[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)区分快/慢唤醒，并说明 speculative issue 需要保留重试责任。[BOOM v4 functional-unit.scala](https://github.com/riscv-boom/riscv-boom/blob/master/src/main/scala/v4/exu/execution-units/functional-unit.scala)包含执行单元的 kill/brupdate 接口。这支持区分本地任务有效性、结果可用性与提交过滤；本候选仍是结果到达后的非推测唤醒，没有改成 issue 时预测结果到达，也没有照搬 BOOM 的队列/分支 mask/周期承诺。CW 的低排名计数是本设计的布尔重排，不宣称来自该项目的频率实测。

## 当前指标与下一步

最近测过的 CD1 仍为 99.65936739659368 MHz / IPC 0.7823728642153719 / 含 SRAM 面积 49851.29213392186 µm² / 正确性 16/19；这些不是 CY 的结果，300 MHz 和 IPC/面积控制范围仍未被证明。相对 CV 新改九个 RTL 文件，相对 CD1 共改十三个 RTL 文件；源与冻结输入一致记录在活动身份文件中。

继续完成源码所有权审阅与剩余方向的采用/暂缓清单。metadata-only RS、分簇、前端 lookahead 和移 cache 边界会改变旁路/资源责任或 IPC；不能在已有 fanout 和串行查表尚未测量时，默认无条件叠加这些变化。匿名 mapped FF 尚未准确归属的字段也不能按猜测修改。测试前另行汇报最终批次、全部改变、未解决风险和一次统一 Windows 原生课程测试范围；此报告不启动测试。
