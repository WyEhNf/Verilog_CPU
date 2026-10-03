# 结构批次 L：测试前报告

状态：**源码实现与冻结完成，尚未启动测试**。本报告保存于启动任何编译、仿真、综合或 STA 之前。源码推理与文件 SHA 核对不构成硬件验证。

## 本批已完成的改变

主工作树更新 12 个 RTL 文件及 `student_top.v`，保留课程基线的 39 项参数。完整候选为 [L_local_recovery_queries](F:/CPU2026Candidates/frequency_research_20261003/L_local_recovery_queries/candidate.json)，补丁为 [review.patch](F:/CPU2026Candidates/frequency_research_20261003/L_local_recovery_queries/review.patch)。

| 部位 | 最终实现 | 周期与主要代价 |
|---|---|---|
| 恢复链 | preview 发前端 redirect；RAT、回收增量、head、occupancy、kill mask 寄存后 apply；pending 寄存位冻结分配/执行/提交；head/tag 分局部真实驱动 | 后端恢复增加一拍，保留更老指令及已提交 store |
| Decode/rename ready | ROB、RS、LSQ、PRF 分配 credit 寄存，保守公开当前空位减去本拍接受数量 | 不预支同拍释放；紧张时可能损失 IPC |
| 乘法 | 带符号修正项进入 carry-save 部分积树；内部 8 项边界寄存后完成压缩及最终加法 | 常规延迟加一拍，启动间隔一拍 |
| 除法 | 规格化、迭代、最终符号修正分阶段；平衡 CLZ；比较与减法共用借位运算 | 常规加两拍；小于除数快捷路径加一拍 |
| Completion | 并行循环 rank、held 来源保留、one-hot 平衡 payload 树及局部选择驱动 | 保留 CDB3、轮转及反压规则，不加周期 |
| Issue | 四口分别使用两项带 ROB tag 的队列，输入 ready 只依赖寄存占用 | 正常首项延迟不变；满队列释放晚一拍可见 |
| RS 选择 | 分配时缓存 12 项两两 unsigned age 比较，共 66 位 | 保留原数值回卷规则与槽位 tie break |
| RS 数据写 | 每行独立 metadata/operand 写入拥有者；分离 allocation 与 wake；最终写门之后使用计价本库缓冲 | 不加周期；未采用的 legacy 数据寄存应被剪除，须在网表确认 |
| LSQ 请求 | 候选身份及字段先寄存，下一阶段判断 store forwarding 并发 cache；回压时保存 forwarding 快照 | 访存请求加一拍；重验 generation，保护已提交 store/已退休 load |
| Icache | 两项 PC/epoch 寄存队列隔离 tag/MSHR→前端 ready；旧 epoch 请求独立丢弃；tag 查询分局部驱动 | 正常取指入口加一拍；满队列空间晚一拍可见 |
| Dcache | 在已有 query 寄存级上拆出宽请求字段的局部写拥有者 | 不增加 load 级数，保留原 SRAM/转发/flush 语义 |

这已经改变了控制和计算跨越寄存边界的方式，并非仅给组合输出补寄存器。普通整数路径较原八级增加 Icache 请求入口边界；乘除法、访存与恢复分别有自己的阶段，不能相加称为统一的全核固定级数。

## 为什么现在可以进行一次完整测量

旧课程网表最慢路径的 redirect NOR、反相器、decode flush NAND 合计 23.4309 ns，占 30.7973 ns 到达时间约 76.1%。弱单元负载超出 Liberty 表的最大负载约 27.8 倍和 17.8 倍。本批已从恢复事务、反向握手及最终宽字段写控制三处处理成因。

既有 40 项研究及本次扩展已逐项落实或明确取舍。**基于当前旧网表，暂时没有另一项可以有把握地继续叠加、且不依赖新瓶颈证据的结构修改。**这不等于声称全世界的频率方案已被穷尽。分簇调度、PRF 分银行、fast wakeup/replay、RAT 再分级和 way prediction 仍作为替代路线：它们改变端口冲突或依赖/恢复延迟，需要本批新路径和 IPC 数据决定是否采用。后台测量期间继续分析这些方向。

不会通过更换库、改变课程 ABC 脚本、增加 false/multicycle path、忽略 SRAM/缓冲面积、全清 OoO 后端等方式制造达标结果。

## 可见代价与尚未证明的事项

当前配置下源码毛计数：净新增约 **2187 个寄存位**，含 C505、D366、E14、G1012、H66、J148、K76。I 的新拥有者替代既有数据寄存，不应与未采用 legacy 同时计为有效硬件。常量剪除、逻辑共享及映射变化尚未计入。

新增真实 `BUFx16f_ASAP7_75t_R` 毛计数约 **1701 个**，按课程 Liberty 0.32076 µm²/个，毛面积约 **545.61276 µm²**，为旧总面积约 **1.18%**。该数字只是缓冲的源码计数，不是候选总面积。未新增 SRAM 宏；仍完整计价既有 37 个宏。

人工检查了 reset、同时 push/pop、满队列、反压、epoch 丢弃、选择性 recovery、generation 复用、forwarding 数据持有及 committed store 保留。这些是推理，尚未编译或仿真证明。额外取指/访存/恢复延迟及保守 credit 可能影响 IPC；新增寄存和重新映射可能影响面积。**不保证 ±10% 已满足，不预测已经达到 300 MHz。**

唯一有效基线仍为：Fmax **32.3978865441 MHz**、周期 **30.8662109375 ns**、IPC **0.98012794065**、包括 SRAM 的总面积 **46309.6934939443 µm²**。旧工具链结果不用于算增益。±10% 比较窗口为面积约 41678.7241–50940.6628 µm²、IPC 0.8821151466–1.0781407347；这与课程 Tier3 的面积 ≤36000、IPC ≥1.0985 不是同一个判据。

## 冻结版本与一次后台测量

- [冻结 source_manifest.json](F:/CPU2026CourseRuns/architecture_L_20261004/source_manifest.json)：157 个文件，RTL、课程原框架、原测试程序/metrics 的 SHA 全部记录。
- [Windows 配置](F:/CPU2026CourseRuns/architecture_L_20261004/course_windows_config.json)：独立 build/result，不能复用旧 CPU 可执行文件。
- [旧主树备份](F:/CPU2026Candidates/pre_staged_frequency_20261004/backup.json)；[H 主树备份](F:/CPU2026Candidates/pre_L_worktree_20261004/backup.json)。

后台并行运行本批一次原课程综合/STA与原生 CPU 构建；构建后运行六项原 perf（内存延迟 10，官方 metrics 分子），及一次完整 19 项 correctness。正确性用于确认这批跨模块协议修改，不进行逐项小改动重复测试。保留失败日志和阶段结果，不能把未完成/失败称为通过。

环境严格为 Windows 原生，不使用 WSL。原库与工具固定：课程框架 `54fc150`、测试库 `29f9807`、Yosys 0.63 / `70a11c6`、ABC `8e40154`、OpenSTA 3.1.0 / `f89887b`、Verilator 5.020 / `5c5314b`、ASAP7 `f970bd3`。官方 build/sim/testcase/synth 源文件不修改；host runner 仅支持选择新冻结配置及已记录的 Windows make/link 路径兼容恢复。

资料与机理依据见 [研究报告](E:/Verilog_cpu/reports/frequency_research_plan_2026-10-03.md)和 [H 阶段记录](E:/Verilog_cpu/reports/frequency_architecture_progress_2026-10-04.md)。新的实测结果将在独立记录中报告，不改写本测试前报告的状态。
