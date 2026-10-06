# 频率结构优化进度与测试前说明

> 本文为 H 阶段的实现归档。后续 I/J/K/L 已完成并整合；最新冻结范围、取舍与测试入口以 [L 批次测试前报告](E:/Verilog_cpu/reports/frequency_batch_L_pretest_2026-10-04.md)为准。下文的“当前”指 H 阶段记录时刻。

本轮已经修改 RTL，**没有启动编译、lint、仿真、综合、STA 或形式测试**。当前工作树状态为 `WORKTREE_IMPLEMENTED_UNTESTED`，不能把源码改动称为已验证性能提升。仍有值得继续分析的控制局部化与访存分级方案，所以目前不进入测试阶段，也不声称所有优化思路已经穷尽。

主工作树：[E:/Verilog_cpu](E:/Verilog_cpu)。身份记录：[active_frequency_implementation_20261004.json](E:/Verilog_cpu/build/cpu2026/active_frequency_implementation_20261004.json)。可恢复备份：[backup.json](F:/CPU2026Candidates/pre_staged_frequency_20261004/backup.json)。每一步均有独立源码、来源 SHA 和相对课程实测基线的补丁。

## 1. 唯一可引用的课程标准实测基线

| 指标 | 冻结基线实测 | 当前实验工作树 |
|---|---:|---|
| Fmax | 32.3978865441 MHz | 未测 |
| 最小周期 | 30.8662109375 ns | 未测 |
| IPC 几何平均 | 0.98012794065 | 未测 |
| 总面积，包括 SRAM | 46309.6934939443 µm² | 未测 |
| SRAM | 7825.666854 µm²、37 个宏 | 本批未新增 SRAM；仍须完整计价 |

目标频率 ≥300 MHz，对应周期 ≤3.3333333333 ns。原 Tier3 的 IPC ≥1.0985、面积 ≤36000 µm² 仍未达标。用户目前要求频率优先，面积与 IPC 处于可控范围；不能据此宣称三项要求已经满足或擅自更换比较基线。

实测来源：[课程标准复测报告](E:/Verilog_cpu/reports/course_standard_retest_2026-10-03.md)、[冻结结果](F:/CPU2026CourseRuns/current_adopted_20261003/result/result.json)。旧工具链的频率与旧镜像/内存延迟下的 IPC 不用于本轮增益计算。

## 2. 为什么优先重构恢复与握手

现成课程报告的五条最慢路径共用重定向控制链。NOR3 redirect、其反相器和 decode flush NAND3 三段串联延迟合计 23.4309 ns，约占 30.7973 ns 到达时间的 76.1%。相应弱 NOR3/NAND3 负载达到课程 Liberty 最大输出负载的约 27.8 倍、17.8 倍。前后新增数据寄存器无法自动切断绕过它们的恢复和反向 ready。

本批采取两种互补处理：恢复及容量返回真正跨越寄存边界；保留组合控制时，在源与宽字段消费者之间放入课程原库的真实、计价缓冲。没有修改课程 ABC/STA 脚本、增加时序例外或排除面积。

详细旧路径与库证据见[研究报告](E:/Verilog_cpu/reports/frequency_research_plan_2026-10-03.md)。23.43 ns 是旧网表的分解，不能用减法预测候选的新频率。

## 3. 已经实现的结构批次

| 批次 | 实现内容 | 主要代价与语义 |
|---|---|---|
| A/B，包含于 C | Fetch/decode payload 写入与失效有效性分离；恢复源、消费者及字段选择使用真实 ASAP7 缓冲 | 不增加周期；无效 payload 不再保证为零 |
| C | 乘法部分积树 36→24→16→11→8 后寄存，再 8→6→4→3→2 与最终加法；signed high-half 修正在 carry-save 树内完成 | 乘法常规延迟增加一拍，启动间隔仍为一拍 |
| D | 快速前端 redirect 与下一拍后端选择性 recovery 分开；保存 RAT、reclaim delta、年龄边界、RS/ROB kill 信息；pending FF 控制分配/执行冻结 | 常规误预测后端恢复增加一拍；恢复期间提交暂缓 |
| E | ROB/RS/LSQ/PRF 分配容量寄存；ROB head 真实局部缓冲；LSQ 有界指针运算；除法规格化与末尾符号修正独立阶段，比较/减法合并为借位判断 | 资源释放保守地晚一拍可见；正常除法增加两拍，小于除数的快捷结果增加一拍 |
| F | Completion 并行循环顺序 rank；先保留反压锁定来源；one-hot payload 平衡树和局部选择缓冲；锁定 tag 从静态选择数据捕获 | 不增加完成周期，保留 CDB3 吞吐与轮转规则 |
| G | 每个 issue 口由一项弹性槽改为两项带 ROB tag 的保留队列，输入 ready 只取寄存占用状态 | 正常首项延迟仍一拍；满队列出队后容量下一拍可见 |
| H | RS 分配边沿缓存原有 unsigned age 两两比较，从唤醒/选择路径移除重复年龄比较 | RS12 新增 66 个关系位；保持原数值回卷规则与槽位 tie break |

这些批次累计位于以下候选；主工作树目前采用 H 的实验实现，而“已验证采用”的档案仍指向冻结基线。

- [D 的补丁](F:/CPU2026Candidates/frequency_research_20261003/D_staged_recovery/review.patch)
- [E 的补丁](F:/CPU2026Candidates/frequency_research_20261003/E_registered_capacity_and_arithmetic/review.patch)
- [F 的补丁](F:/CPU2026Candidates/frequency_research_20261003/F_parallel_completion/review.patch)
- [G 的补丁](F:/CPU2026Candidates/frequency_research_20261003/G_buffered_issue/review.patch)
- [H 的完整补丁](F:/CPU2026Candidates/frequency_research_20261003/H_cached_issue_age/review.patch)

已更新 10 个 RTL 文件：backend joint、completion、LSQ、RS、ROB、fanout helper、cpu_core、fetch frontend、divider、multiplier。另外更新 `student_top.v`，物化课程已测基线的 39 项采用参数，防止主树旧默认参数与候选配置混淆。这不是新一轮参数搜索。

### 恢复事务的边界

| 时段 | 前端 | 后端 |
|---|---|---|
| 分支结果进入 pending 的边沿 T0 | 尚未 redirect | 捕获存活、generation 合格且被接受的分支 tag/target；同时准备恢复 history |
| T0→T1，preview | 发出一次 PC/epoch redirect，失效未分配 fetch/decode 内容 | pending FF 阻止新分配、新执行及提交；计算恢复信息 |
| T1 边沿 | 可开始正确路径取指 | 捕获 RAT、回收 delta、RS/ROB mask、head/occupancy；旧 completion 可继续写入 |
| T1→T2，apply | 不重复 redirect | 寄存事务驱动选择性 kill、ROB 截断、RAT/free-list 恢复 |
| T2 边沿以后 | 正确路径内容等待并重新得到 credit | 更老指令保留，完成恢复后开放分配/执行 |

保护规则已经落实在源码中，但尚未经工具验证：

1. **更老指令保留**：RS、issue、ALU、LSQ 按 tag/年龄处理，MDU 继续运行并以 ROB generation 过滤输出。
2. **存储的外部副作用受提交控制**：已提交 store 留在 LSQ/cache/AXI 中；没有全清访存系统。
3. **Free-list 保存回收增量**：保存 killed suffix 的 bitmap/count，apply 时合入当前 free state，避免用旧完整 free bitmap 覆盖状态。
4. **Completion 不能保存槽位 mask 后盲用**：完成来源/队列槽位可以变化，apply 时对当前 tag 重新判年龄。
5. **预分配 epoch 与已分配 ROB generation 分开**：不使用全局 epoch 清除所有更老后端指令。
6. **恢复 history 提前可用**：在分支进入 pending 时准备，保证快速 redirect 采样时已有正确 history。
7. **Issue 两项队列保持输出**：未被接受时 read slot/payload 不变；recovery 后重新选择保留槽位，不丢失更老项。

### 容量额度的静态推理

设本拍当前空位为 F、接受数量为 A、同边沿释放数量为 R≥0。下一拍实际空位为 `F'=F-A+R`。寄存后公开的额度取 `min(BE_WIDTH,max(F-A,0))`，没有预支释放，所以不会超过下一拍实际空位。资源恢复/清除只增加可用容量；reset/flush 初始化额度为零。

Decode 的公开 ready 使用这些寄存额度；rename 输入有效前缀也由该 ready 限定，避免“decode 消费了但 rename 未分配”或两者接受数量不一致。PRF 内部仍执行 free-list 合法性选择。

这只是协议推理，不是形式证明。释放晚一拍可见可能降低资源接近满载时的 IPC，后续必须实测，不保证 ±10% 已满足。

## 4. 面积与延迟的可见代价

当前四宽、ROB64、RS12、PHYS64、tag17、payload231-bit 的源码几何下，未计常量剪除、共享和逻辑重映射：

| 新增来源 | 净新增寄存位，源码层面 |
|---|---:|
| C 乘法内部边界 | 505 |
| D backend/ROB 恢复事务 | 366 |
| E 分配 credit 与除法状态 | 14 |
| G 四个两项 issue 队列 | 1012 |
| H RS 年龄关系 | 66 |
| 合计 | **1963** |

相同配置的新增真实 BUFx16f 源码实例毛计数为 816，单价 0.32076 µm²，毛面积 **261.74016 µm²，约基线总面积 0.565%**。它包括 C476、D56、E78、F90、G116；H 没有新缓冲。该计数不含基线已有单元，也不是候选总面积实测。新增 FF、删除逻辑、常量位裁剪及 ABC 映射变化必须在完整课程综合后计价。

普通整数主路径仍沿用现有八级阶段边界；G 增加的是容量，未增加正常首项流水延迟。乘法、除法与恢复有各自新增内部边界，不能把不同路径简单相加称为全核固定级数。

## 5. 继续推进、尚未测试的方向

既有研究列出 40 项方案。本轮新增/落实了两阶段恢复、credit、两项 issue、并行 completion 与年龄关系缓存。以下仍有可做的源码分析，**并非已经穷尽后只剩等待测试**：

| 方向 | 下一步具体审查 | 暂不盲目修改的原因 |
|---|---|---|
| RS 宽 payload 控制 | 每行 grants→字段选择、allocation/wakeup 的最终写优先级；将非操作数 metadata 与 value 更新分别拥有 | 把 buffer 放在 reset/flush 门之前，映射后可能再次形成弱高扇出门；需要从最终写事务处理 |
| LSQ 请求两阶段 | 先选候选并保留 tag，后读 payload/发 cache；检查回压时持有及 recovery 下撤销 | 必须保存请求身份，不能把每拍重新选出的 payload 当成同一握手事务 |
| Cache 查询/响应分级 | 区分 SRAM 地址、tag match、data select、MSHR 命中与响应 ready 依赖 | Dcache 已有 registered index，Icache 已有 parallel match；不能把现有功能重复列为新实现 |
| Completion→RS wakeup/value | 分离固定延迟 ALU tag 与可变延迟 load/div；检查局部 bypass 是否跨越整个调度环 | 无依据承诺 load 命中，不能提前唤醒后永久移除 RS 条目 |
| 局部恢复 tag/head | 看恢复 descriptor 与 branch tag 的真实消费者范围，避免新 FF 又形成广播负载 | 复制 assign 或可被合并的 FF 无法证明电气分离；真实单元需计价 |
| RAT 恢复选择 | 将 ROB64 的 oldest-killed-writer 选择进一步分银行/分阶段 | 现有并行恢复已采用；新增阶段会延长 rename 暂停，需要明确重建协议 |

以下更大路线已比较机制，作为替代方案保留：分裂/聚簇 issue queue、PRF 银行及跨域寄存旁路、分支 mask 与 checkpoint allocation list、cache way prediction。它们会改变端口冲突、依赖延迟或重放协议；不直接套用其他 CPU 的频率数字，也不同时无约束替换所有架构。

不会采用通过时序例外隐藏路径、排除 SRAM/真实 buffer 面积、更换课程库或 ABC 脚本来获得表面频率、仅在组合单元输出后补延迟 FF、无条件全清 OoO 后端等方案。

## 6. 资料依据与测试入口条件

- [BOOM Execute Pipeline](https://docs.boom-core.org/en/latest/sections/execution-stages.html)：立即 redirect、延后 kill 的机制；本实现另补了分配冻结与本项目的 generation/年龄恢复。
- [BOOM Rename Stage](https://docs.boom-core.org/en/latest/sections/rename-stage.html)：checkpoint/free-list 恢复时必须处理被投机分配的物理寄存器。
- [BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)：固定延迟 fast wakeup 与可变延迟 slow wakeup 的区别。
- [香山 RedirectGenerator](https://github.com/OpenXiangShan/XiangShan/blob/kunminghu-v2/src/main/scala/xiangshan/backend/ctrlblock/RedirectGenerator.scala)：分阶段恢复与 pending redirect 源码参考。
- [Palacharla、Jouppi、Smith，ISCA 1997](https://www.eecs.harvard.edu/cs146-246/isca.complexity.pdf)：wakeup/select 与旁路范围对时钟周期的结构影响。
- [Carloni，Proceedings of the IEEE 2015](https://sld.cs.columbia.edu/pubs/carloni_pieee15.pdf)：使用缓冲和协议边界隔离计算/通信延迟。
- [verilog-axi priority encoder](https://github.com/alexforencich/verilog-axi/blob/master/rtl/priority_encoder.v)、[arbiter](https://github.com/alexforencich/verilog-axi/blob/master/rtl/arbiter.v)：平衡选择及轮转/锁定机制参考，未直接复制其实现或频率。

当前只做了源码准备、人工协议推理、文件来源核对和备份。没有编译成功、正确性通过、IPC 稳定或频率提升的结论。

进入测试前，还要完成上述能直接落实的结构审查，另行汇报最终冻结版本、取舍和剩余风险。后续测量继续使用已固定的课程版本、原六项 perf 与内存延迟10；所有构建和测量在 **Windows 原生环境**进行。测试应在后台运行，测试期间继续分析下一批方案。测试不用于逐个小改动筛选，先形成完整结构批次再统一测量。
