# ER1 完整组合测试前范围

完整源码组合已实现并完成源审查。本报告生成时尚未启动 ER1 HDL 编译、综合、STA、CPU 构建或程序。先在对话汇报，再只对整体做一次 Windows 原生课程 timing-only；ER、ER1 均未分项测试。

## 当前参考与未知指标

上一个主版本 EP 实测 **361.071932 MHz**、最低周期 **2.76953125 ns**、含 SRAM 总面积 **49,589.945634 μm²**，原面积基线 **+7.0833%**，在 ±10% 内。EP 频率超过300，但低于历史 EF 370.477569MHz；EP 的 IPC、功能未测。EP 相比EL1频率 +35.2962%、面积 -0.04655%。这些指标不能移用于 ER1，ER1 当前所有测量指标未知。

## 新限制与结构修改

EP 导出的五条路径都从 LSQ addr_mem[7][3] 经老store/request资格、最老优先树，到 pick_payload_read 的行号查询/行解码，最后到字段暂存输入。到达时间按降序为2.7107、2.7090、2.7060、2.7039、2.7032ns。四个67/68负载门分别0.3363、0.3228、0.3972、0.3042ns，合计1.3605ns。

公共 index 别名并不是 payload reader 的独占控制：slot 位也可能与原选择决策相等，服务旧地址/年龄等 mux。ER1 同时处理完整节点的最终消费者和“先赢得行号、再查payload”的串行联系。

- 每个节点仍使用原 choose_left、原 valid 合并、原环形/年龄/tie规则。
- slot、age、wrap、address与完整generation、ROB tag、store data、mask、load、size、unsigned 一起传递。当前每节点108位、7个选择控制域，每叶最多16个RTL mux位。
- 去掉根行号确定后再读67位payload的第二次索引查询。通过原树的同一个子节点选择取得全部字段，不让地址与tag来自不同候选。
- 叶packet按原SLOT_WIDTH的slot赋值取数据，保留显式宽度截断。二值归纳下，每节点packet等于原read(该节点slot)；没有候选时仍按原 invalid/invalid 分支选右，不另造row0默认。LSQ单条目时根直接是叶。
- 既有110位 selection bank 在原 selection_input_fire、原边沿捕获相同字段。所有request eligibility、older-store hazard、committed-store、full live/generation、flush/recovery、forwarding hold规则原样保留。

相对EP只修改LSQ的组合结构；累计20组。零新增声明状态，零LSQ/事务新增周期，普通整数流水线仍10级。继承EP的load-hit已有回复寄存边界，首次空槽hit回复多一拍，此项IPC成本仍未知。当前CPU DCACHE_REQUEST_PIPELINE=0，请求保持来自LSQ原有选择暂存；没有假称CPU额外skid已启用。

## 审查与风险

41个候选输入及原EP工作区40/冻结157输入SHA已核对，69个复合时钟块文本相同。审查是源码、字段/优先级二值归纳与原映射数据读取，未调用HDL编译、仿真、形式、综合或STA。四态unknown下mux合并可能与原one-hot读不同；不声称完整四态/全核等价。

选择叶最多16个RTL位不保证实际库输入负载恰好32，也不保证映射面积相同。并行packet与控制分组可能增加面积、增加子节点wrap到父节点的延迟，或让另一条路径成为主限制。不能直接减去1.3605ns来预测MHz。零声明状态增长不等于映射时序面积必然不变。

## 其余方向的取舍

EQ 的MMIO预分类、EM的共享ROB查询以及EH的全部慢wake延后继续独立保存，当前导出路径没有支持它们混入。直接逐行one-hot winner packet需要另建默认/优先掩码；本批使用与原树逐节点严格对应的方案。寄存全矩阵hazard、乐观load重放、缩窗口/issue/PRF端口都涉及额外snapshot、失效、恢复或IPC代价，暂不加入。本轮已有实际路径支持的完整结构变化，未找到更多应加入本批的改动；未来新路径仍可能需要新方案。

## 唯一下一测量

先在对话汇报本报告，再启动完整ER1的一次原生课程synth/ABC/OpenSTA周期搜索，测Fmax和含SRAM总面积。无中间候选/单节点测试，无CPU/IPC/功能程序。本次综合在后台，期间新研究独立保存，冻结输入保持。

framework `54fc150ffc290f52aa024209ffb9a29d43856f6d`、testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`，固定Yosys0.63/课程ABC/OpenSTA3.1/ASAP7 RVT TT/FakeRAM，Windows原生、禁止WSL；原39项override、队列/宽度/cache配置、2ns映射时钟、uncertainty、输入输出/负载预算和计价算法不变。以课程最低可行周期给Fmax，不用2ns负slack直接判300MHz失败。

原面积上限50,940.662839μm²，IPC下限0.882115146585；最终Tier3需area≤36,000含SRAM、IPC≥1.0985、Fmax≥300。频率仍是当前主目标。达到足够频率收益且面积可控后，另行先汇报必要IPC/功能阶段，复用完全相同的综合；不再综合同一身份，也不为每个改动跑程序。350MHz只是昂贵程序阶段的工作门槛，不替代原要求。现在IPC、功能与完整Tier3未证。

## 已保存证据

- EP测量：`E:/Verilog_cpu/reports/frequency_EP_measurement_2026-10-05.md`
- EP映射路径：`F:/CPU2026Proofs/EP_mapped_paths_20261005/saved_path_analysis.json`
- ER1源码审查：`F:/CPU2026Proofs/ER1_source_review_20261005/source_review.json`
- 相对EP变更：`F:/CPU2026Candidates/frequency_research_20261003/ER1_parallel_lsq_pick_slot_identity/changes_vs_parent.patch`
- 原EP工作区备份：`F:/CPU2026Candidates/pre_ER1_worktree_20261005`


## 最终冻结与调度身份

- Candidate：`F:\CPU2026Candidates\frequency_research_20261003\ER1_parallel_lsq_pick_slot_identity`
- Candidate manifest SHA256：`cd2a4d2985fe68aed6b39c554eff17cd1cfcb304970e8a5ea975a19c26d3e940`
- Frozen run：`F:\CPU2026CourseRuns\architecture_ER1_20261005`
- Frozen manifest SHA256：`9206002e2e07824ffd8a4db5a65be70c59f644d5fe87d1052456fbe602e34612`
- 源审查：`F:\CPU2026Proofs\ER1_source_review_20261005\source_review.json`
- 源审查 SHA256：`931d97f77b5b844e24b22c484d0c531f598bbd7404ac5dd6ceca72b3232fbe46`
- 范围文件 SHA256：`bbd376158f1b98483e944ac6bac2e44384c23bb85351b3117cb217b89a025c24`
- 当前主工作区输入：40
- 冻结输入：157
- 后台调用：`tools/start_frequency_course_background.py --run F:/CPU2026CourseRuns/architecture_ER1_20261005 --timing-only`

上述身份只执行一次timing-only，在对话汇报后才能调度。该报告落盘不调用任何测量工具。
