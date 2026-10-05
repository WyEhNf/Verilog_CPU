# ER1 后台期间的结构研究与条件候选 ES

ER1 的一次 Windows 原生课程 timing-only 正在后台执行；本记录不启动新的测试。主工作区与冻结输入保持 ER1 身份，ER1 频率/面积/IPC在撰写时仍未知。EP 361.071932MHz是父版本历史结果，不是ER1结果。

## 平行环形前缀仲裁

EP五条导出最慢路径均经LSQ资格→最老仲裁→根slot编码/载荷查询。ER1已让完整packet沿原树同行，并限制每个最终控制叶≤16个RTL选择位。另一个条件方案ES改变仲裁表示：原power-of-two树的叶顺序是物理行递增，原比较规则相当于先选row≥head的最小可发行；若不存在，再选row<head的最小可发行。

ES将资格按原wrap分成两类，每4行为组。组内与组间静态前缀共同判断是否存在更早同类行；wrapped类再受“没有unwrapped请求”限制。全packet按唯一winner掩码后作平衡OR，不再经过四层108位的串行packet mux与wrap再选择。winner每7个控制域分发，最多16个RTL mask位；没有候选时仍选择原最后物理叶metadata。N1与非2的幂容量完整保留ER1原树。payload仍来自原叶slot截断所索引的行，保留显式SLOT_WIDTH覆盖行为。

候选只改LSQ组合块，零新增状态或事务周期，普通整数10级不变。eligibility、全generation/ROB authority、committed-store许可、hazard、selection_input_fire、forwarding hold与恢复不变。与父版本的源变换、字段/优先级二值推导、时钟块与身份核对单独存档；没有HDL编译、仿真、形式、综合或STA。

这是结构备选，不是预测收益。两级前缀广播、row grant与mask/OR合并可能新增延迟或面积；unknown四态行为也可能不同。等待ER1的新路径决定是否值得进一步采用；不为了测候选而测。单纯将所有hazard寄存化需要对行复用、head变化、store地址/数据更新和recovery建立失效规则，目前没有足够支持将它加入。

## 文献与本CPU的区别

[BOOM的Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)描述静态优先编码器与按年龄组织队列；[香山IssueQueue设计文档](https://docs.xiangshan.cc/projects/design/en/kunminghu-v3/backend/Schedule_And_Issue/IssueQueue/)按entry类分别并行选出最老指令，再按严格类年龄关系合并。可借鉴的是利用已知年龄关系缩小仲裁，而不是照搬另一个CPU的队列或频率。本LSQ两类优先级直接由原环形head规则推导，且不需要新增年龄矩阵状态。开源实现的频率不能换算成本ASAP7课程结果。

## 后续必要程序阶段的准备

新增两个尚未执行的原生调度/观察工具。只有当前完整冻结版本的实际频率收益与面积满足既有阶段条件、且先完成并在对话汇报程序阶段报告后，才会启动一次Verilator5.020构建，运行6个官方perf与19个官方correctness。全部复用该版本的课程综合/STA、source/config/tool/report身份；不重新综合。旧timing-only观察器不能用于这个后续阶段，专用观察器跟踪独立program PID及原始课程PASS/FAIL日志。

工具的静态审查只确认控制流程与现有wrapper接口；没有执行构建、程序或工作流测试。程序阶段尚未创建可调度plan，也没有启动。最终Tier3面积≤36000含SRAM、IPC≥1.0985、频率≥300和完整功能仍是要求；350MHz只是昂贵程序阶段的既有工作门槛。

保存位置：

- `F:/CPU2026Candidates/frequency_research_20261003/ES_lsq_circular_prefix_packet`
- `F:/CPU2026Proofs/ES_source_review_20261005/source_review.json`
- `E:/Verilog_cpu/tools/start_reused_frequency_programs_background.py`
- `E:/Verilog_cpu/tools/record_reused_frequency_program_progress.py`
