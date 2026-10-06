# EA 最终组合与测试前汇报（2026-10-05）

实现阶段已结束，当前工作区 **EA 未测**。本报告发布时没有运行 EA 的 HDL 编译、仿真、综合或 STA。下一步仅对全部八组改动做**一次 Windows 原生课程综合/STA**，得到频率和含 SRAM 总面积；不构建 Verilator，不跑 CPU 程序，不分别测试中间候选。实际启动前先在对话中报告这些范围。

## 实测基础及本次判断

EA 沿用有实测数据的 DM1，后者为 **302.1540 MHz、总面积 51,130.6726 μm²、IPC 0.7823728642**。后续 DT 的组合实测回退到 **272.2680 MHz**，总面积 **51,371.6362 μm²**，因此其源码和报告保留，EA 没有继承 DT 的 completion/PRF 重构。EA 的频率、面积、IPC、功能结果现在都是未知，不能沿用 DM1 的结论。

这不是单门补丁。本次把全核控制分发极性、请求资格的消费者分组、完成查询的串行解码和存储地址算术一起改了；基于历史结构统计，全核多叶控制树每条路径少两次反相，而旧 DM1 实例结构的 INV 数量可从 119,936 减至 73,979，减少 45,957（38.32%）。这只是裁剪和映射之前的源实例模型，不能换算成 EA 的实际 MHz 或 μm²。结构变更规模足以支持对完整组合测量一次；是否产生实际质变仍须由课程结果回答。

## 八组实现及范围

|组|实现|保留的行为及风险|
|---:|---|---|
|1|全核控制树根节点反相一次、内部保留负极性、独立叶节点恢复正极性|内部最多四个子门负载，每个消费者仍有自己的真实驱动；不替换库。入口负载和 slew 改变，实际延迟未测|
|2|LSQ 请求/转发构造独立 owner，资格按最多 16 位分组使用|完整 tag、请求无效时零字段、转发临时值原资格、ready/fire 和恢复行为保留|
|3|LSQ 完成报告在行选择前解码 ROB slot 的低/高索引银行|同一报告携带完整 tag 和 16 位组合 one-hot；仍读原 ROB valid/generation 并做原正常代际检查。报告由 75 扩至 91 位，面积代价待测|
|4|分配地址采用 signed-12-bit 专用加法器|CPU store decoder 提供该合同，独立 trace 后端默认保留原通用加法|
|5|共享存储 AGU 采用同一专用加法器|保留地址探测/早到地址的原握手周期，完整 LSQ/ROB 身份不变|
|6|RAT 恢复 killed/upper 谓词分成八组消费者|每叶服务最多四个架构寄存器；恢复 oldest writer、分支映射优先级、掩码完全保留。会增加局部驱动实例|
|7|指令缓存两槽请求队列的读/写选择按 16 位分组|保留两槽现有未复位 payload、相同 push/write slot、read slot、count、epoch 淘汰和回压。payload 的时钟写源码改为既有 word-bank owner，没有新增状态|
|8|指令缓存同周期 promoted response 的 epoch/line/PC 选择按 16 位分组|同一选择位作用于相同字段，error 位和 response 写优先级不变；修复一个具体 64+EPOCH_WIDTH 位宽选择的共享负载|

与 DM1 不同的六个 RTL 文件：backend joint、LSQ、RAT recovery、icache nonblocking、common fanout、CPU core。整数主流水线仍为 10 级，不增加寄存器位或请求/提交周期。

源码文本检查确认 **69 个 begin/end 形式的时钟块**与 DM1 相同。该检查不覆盖所有单语句时钟块；队列 payload 写被改为 word-bank，因此单独记录了“两槽×(32+EPOCH_WIDTH) 状态、相同写边沿/条件、相同读函数”的手工对应。以上不是 HDL 语法接受、形式等价或功能证明。

## 五条最慢路径之外的既有负载证据

只读取旧映射 JSON，没有调用 STA。DM1 `student_top` 中有 447,133 个 cell，2,133 个驱动 bit 有至少 32 个顶层输入连接；DT 对应 447,715 和 2,158。这是顶层连接清单，保留层级的端口可能代表内部负载，不能当作全部物理引脚、电容或全部端点的时序枚举。

|旧网表中的对象|已保存负载证据|此次处置|
|---|---|---|
|LSQ 请求锥共享门|DM1 224 个输入连接；DT 最慢路径 NAND5 实测 220，单门 1.3177 ns|请求及转发整体构造改为分组门控；不只处理 AXI 网名|
|RAT upper 条件位|DM1 最高 86；DT 最高 94|八组架构寄存器消费者；新实际负载尚未映射|
|icache request write 控制叶|DM1 两槽各 72|每组最多 16 个原 payload hold mux|
|icache response 私有控制锥|DM1 OR2 113 个连接，可达 response metadata/data 边界|将源码中具体的 64+EPOCH_WIDTH 位 response_promoted mux 分组。连接可达性不足以证明私有 OR2 的精确布尔身份或关键性|
|复位的公共反相器|DM1 174；输入明确为 reset bit 3|课程 STA reset case 为 0，此高扇出不据此视为正常工作频率瓶颈，也没有为它盲目加面积|

## 更大架构方向的分析结论

PRF 分银行或减少读端口需要考虑同时发射的端口冲突、操作数排队及重发。BOOM 的公开设计文档说明，动态读端口调度可能引入额外阶段及取消/重发机制；旁路发生在寄存器读取阶段末端。[BOOM register file/bypass 文档](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)

提前唤醒可以缩短“完成到下一条指令调度”的依赖链，但固定 ALU 和可变延迟 load/divider 不能按同一条件处理。BOOM 文档区分发射时的 ALU fast wakeup 和写回时的 long-latency wakeup；推测失败要有取消/重试机制。[BOOM issue unit 文档](https://docs.boom-core.org/en/latest/sections/issue-units.html) 对本核的推断是：CDB 回压和恢复期间必须保证数据/身份在消费者取数时实际可用，不能只提前发标签。

复制 ROB 状态、保存查询结果和给 store probe 再加寄存边界也已考虑。局部副本需要同步分配、提交、恢复、槽重用及完整 generation；额外 store-address 边界会推迟旧 store 冲突释放。它们都有具体的时序/IPC/状态代价。当前八组已经改变相关路径，现有旧网表不足以判断哪一个是下一瓶颈；先用一次组合结果决定这些架构方向，不采用删除授权检查或连续盲目加级。

**基于目前已有证据，暂未发现尚未合并、可直接推导收益并值得在本批继续实施的改动。** 若下一次结果出现新的慢锥，就沿新证据继续优化。更大的架构方向没有被当成已经完成或已经证明无用。

## 一次后台测量的具体范围

命令：`python tools/start_frequency_course_background.py --run F:/CPU2026CourseRuns/architecture_EA_20261005 --timing-only`。

课程 framework 为 `54fc150ffc290f52aa024209ffb9a29d43856f6d`，testcases 为 `29f980727f7d99a1842a58f34091c7579ba3fe85`；原生 Yosys 0.63、ABC 对应课程固定修订、OpenSTA 3.1，以及 ASAP7 RVT TT/FakeRAM 均保持原版本与计价。禁用 WSL。没有修改课程 synth/testcase/sim 输入，也没有改变原始时序约束或库。

先只执行课程 synth 一次，包括其本来就有的 ABC 映射与周期搜索。保留所有日志及映射文件。等待时继续源码研究，但不能把新改动混进正在测量的冻结源；另存候选。

若频率显示实质提升且面积可接受，再明确报告并复用同一结果测 IPC 和必要功能；不会因一次综合完成就自动启动大量测试。350 MHz 是昂贵第二阶段的工作判断值，不是已经实现的结果，也不替代原始 300 MHz、面积/IPC±10% 或 Tier3 标准。原始面积 +10% 上限为 50,940.662839 μm²，IPC −10% 下限为 0.882115146585；DM1 尚不满足它们。Tier3 36,000 μm² / 1.0985 IPC 仍未完成。

## 身份与恢复

- 当前 candidate：`F:\CPU2026Candidates\frequency_research_20261003\EA_combined_control_locality`
- Candidate manifest SHA256：`b83fe60fc5df54aeb59a1e17627d3bf62b3bfc6a7b90bb3c5dc256b187fc8bb8`
- 冻结目录：`F:\CPU2026CourseRuns\architecture_EA_20261005`
- 冻结 manifest SHA256：`d5d2f213f5df028d2522f113fb3fadfd302e69f448f81e9518cf6fa850b6ee65`
- 输入：工作区 40，冻结 157，课程 override 39（与原 DM1 一致）。
- 源码检查：`F:\CPU2026Proofs\EA_source_review_20261005\source_review.json`
- 对 DM1 差异：`F:\CPU2026Candidates\frequency_research_20261003\EA_combined_control_locality\changes_vs_measured_DM1.patch`
- 旧负载清单：`F:/CPU2026Proofs/DM1_mapped_load_census_20261005/summary.json`、`F:/CPU2026Proofs/DT_mapped_load_census_20261005/summary.json`
- 私有锥只读追踪：`F:/CPU2026Proofs/DM1_high_load_cones_20261005/summary.json`
- 改动前 DY 备份：`F:/CPU2026Candidates/pre_EA_worktree_20261005`。旧 DM1、DT、DY、DZ 快照和结果均保留。
