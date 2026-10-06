# DM1：六项频率改造汇集完成，测试前报告

主工作树已由未测 DK 更新为 **DM1_lsq_report_bound_widths**。在 DK 的四项实现上，本轮又完成 store→RS 直接关联和 LSQ 报告范围预计算；现有 DF1 最慢路径中报告资格、恢复资格、匹配、选择、加法的串行依赖已分别处理。**本轮没有运行 HDL 编译、lint、仿真、综合、STA 或形式验证。DM1 所有性能和功能结果均未知。** 本文件是统一测量前的实际实现报告。

相对已经测量的 DF1，六个 RTL 文件有变化；相对未测 DK，四个 RTL 文件有变化。40 个活动输入与 157 个课程冻结输入已保存并做文件身份核对。课程原 39 项配置、普通整数十级流水、OoO 执行/in-order commit、内存 latency10 与 SRAM 形状/容量保持。新增 80 位声明的关联状态，不插新流水边界；实际 FF 数量和面积只有综合后才能知道。

[冻结 manifest](F:/CPU2026CourseRuns/architecture_DM1_20261005/source_manifest.json) SHA256：`752cbc61415c193c4dd9a5a4b4aa009e7cd99bb0a387acb143e3763c1949725e`。[DK 备份](F:/CPU2026Candidates/pre_DM1_worktree_20261005/backup.json)、[对 DF1 的完整差异](F:/CPU2026CourseRuns/architecture_DM1_20261005/changes_vs_DF1.patch)、[源码身份与实际准备脚本 SHA](F:/CPU2026CourseRuns/architecture_DM1_20261005/implementation_review.json)独立保存。DL、DL1、DM 和 DM1 中间候选均未测量；最终采用的是 DM1，不能把中间名称当成已产生的性能结果。

## 已知测量与本批目标

最近的完整频率/IPC/面积测量属于 [DF1](E:/Verilog_cpu/reports/frequency_DF1_measurement_2026-10-05.md)：Fmax **294.337453291 MHz**、最小周期 **3.3974609375 ns**、六项 IPC **0.782372864215**、总面积含 SRAM **51,368.530674 μm²**。频率距 300 MHz 还需缩短 **0.0641276042 ns**；面积较课程基准高 10.9239%，IPC 低 20.1765%。±10% 与原 Tier3 尚未达标，本轮仍以频率为主，不用未知的新数值覆盖这些事实。

DF1 五条课程最差检查数据到达均为 3.3370 ns，沿 LSQ head→report→本地 cancel→RS wake→store 地址选择→base/imm→加法→LSQ 写入展开，五条路径均没有超过库最大电容的门。其原始 `source_path` 提供了本批依据；它只覆盖五条最差样本，不能据此称为全芯片所有路径的清单。

## 六项实际修改

| 组 | 已完成的结构 | 目的与代价 |
|---|---|---|
| DH | refill merge 先按 byte mask 资格，再由独立保留叶选择 8 位 payload | 处理原映射每 way 144 输入脚的最终资格扩散；增加计价的组合单元 |
| DI | LSQ 每行提前计算原 cancel，随原完整 report 一起选出 | 不再等待选中 ROB tag 后的年龄算术；报告 74→75 位，分组仍五个；正常 ROB authority 保留 |
| DJ | 环形 store 选择和 RS 选择直接携带 one-hot | 去掉索引编码、分发、再解码；保留旧环形最老顺序，legacy 重复匹配保留最低 RS 行优先 |
| DK | 共享 store 地址改八个 nibble 并行加法与三级 carry prefix | 保留精确 modulo-2^32 加法和一个共享 AGU；不复制十二个完整地址 adder |
| DL/DL1 | 分配时登记 LSQ→RS 槽号，按 RS 实际释放边沿失效；四行一组输入分发 | 地址探测的 16×12 完整 ROB tag 关联替换成短索引匹配；新增 16×(1+4)=80 位声明状态，ready 分发字段 216→12 位 |
| DM/DM1 | report 范围判断共享 widened endpoint，再和各行固定阈值比较 | 移除报告对逐行 age 减法后比较的串行依赖；没有删除范围检查、依赖 tail 关系或新增状态 |

原普通 completion 的完整 ROB valid/generation 查询、ROB 最终完整 tag 检查、共享 store 地址发布前的完整 ROB valid/generation 检查都保留。DG 删除普通完成 authority 的候选仍未采用。

## 直接关联的生命周期

RS 新增两个只读输出：已有 static allocation 的槽号，以及已有 valid_mem 释放的事件。`entry_release` 使用与 valid_mem 相同的优先级：reset；flush 时的对应 kill mask；普通周期的 `issue_valid && issue_ready && issue_slot==row`。没有改变 RS 分配、发射或恢复状态机。

关联模块仅在 `EARLY_STORE_ADDRESS==2 && RS_ALLOC_STATIC_WRITE!=0` 启用。每个 LSQ 行保存 valid 与 RS 槽号。其他模式维持原 tag 关联，独立 selector 默认 `LINKED_RS=0`，旧 standalone named-port 调用仍采用原行为。

| 事件 | 关联行为 | 防止的问题 |
|---|---|---|
| reset / 外部 flush | 全部 link valid 清零，index 不要求 reset | 旧任务不能从新初始化状态获得关联 |
| 普通 store 分配 | 同一 dispatch lane 的 LSQ alloc_fire 与 RS alloc_fire 均成立才建立有效 link，槽号来自真正 RS allocation_slots | 不把未分配或别的 lane 槽号当成 owner |
| 任何 LSQ 槽位分配 | 重写该行关联；load 或未与 RS 同时接受的行写 valid=0 | 旧 LSQ 行复用不能留下旧 RS link |
| RS 发射进入既有 issue FIFO | 在 RS valid 清除的同一边沿清除指向它的 link | FIFO 中旧 store 等待 ALU 时，已释放的 RS 行可被新任务复用，旧 link 不再读新操作数 |
| 部分分支恢复 | 禁止建立新 link；按真正 RS release 清除被杀行，保留未释放的旧 owner | 保留 branch 前的旧 store，抑制被取消的年轻任务 |
| 普通周期同时有新 LSQ 分配与旧 RS release | 新 LSQ 行身份的 capture 优先于旧 link release；旧 RS valid 行不会被 static allocator 在同边沿重新分配 | 避免用旧关联的释放事件清除新行身份 |
| 已提前发布地址 | pending 随原 LSQ 地址状态变为 false，link 不再使其重复参与 | 地址探测仍不使 store data ready、不完成指令、不授权内存写入 |

初始化后，每个有效 link 只指向同一次 dispatch 建立且尚未释放的 RS owner；static allocation 不选当前 valid 行，RS owner 释放与 link 失效同边沿发生。每个 LSQ allocation 都覆盖 link，使旧 LSQ generation 不能靠残留裸 RS 索引取得新值。新 selector 仍根据原 LSQ pending、RS base_ready 和原环形最老 policy 仲裁；base/imm/tag 的选择始终来自同一 one-hot grant，最终 ROB authority 和完整 LSQ tag 写入条件仍保留。

这是一份对已有分配/释放代码的人工生命周期推导，不是覆盖任意非可达输入状态的形式等价证明。linked 模式依赖 dispatch 的真实共同分配与唯一任务 ownership；legacy 模式继续定义任意重复 full-tag 输入的原优先级。新 link 写入/释放链可能成为新的慢路径，不能只依据删除比较数量预测 Fmax。

## 报告范围的代数与参数边界

原源码是 `entry_age=(row-head)&(LSQ_ENTRIES-1)`，赋值到 SLOT_WIDTH 位后再判断 `entry_age<occupancy`。由于队列要求 power-of-two，它的有效 modulo 是 **M=min(LSQ_ENTRIES,2^SLOT_WIDTH)**。令 `r=row mod M`、`h=head & (M-1)`、`n=occupancy`，使用足够宽、未回绕的 `e=h+n`：

| 条件 | 原 age | 等价范围判断 |
|---|---|---|
| r≥h | r−h | e>r |
| r<h | M+r−h | e>M+r |

sum 的宽度为 max(COUNT_WIDTH,SLOT_WIDTH)+1，当前是 6 位；结果分发到四组，每组最多四行。阈值是 elaboration 常量。空队列 n=0 时所有谓词为 false；n≥M 时所有 age<M 的行通过；边界相等仍不通过。M=1 时 h=r=0，判断为 n>0，保持单项队列。显式较宽或较窄 SLOT_WIDTH 保留原 mask 加截断的有效 modulo。

DM 初稿只按 SLOT_WIDTH 取 modulo；人工读回原 `entry_age` 定义发现还有队列 mask，遂形成 DM1 修正。**没有通过先运行 HDL 测试发现这一点。** 当前普通配置 M=16，修改不借助 `tail=head+occupancy` 这一未完整证明的状态关系。request/hazard/forwarding 等其他 age 消费者完全未改，所以不能宣称整个芯片十六个 age subtractor 都已消失；本改动只切断 report 的该依赖。

## 其余方向已作取舍

前一 [DK 报告](E:/Verilog_cpu/reports/frequency_batch_DK_pretest_2026-10-05.md)记录了文献与开源项目依据，本轮进一步落实其中两个原来保留的方向。对同一条已知慢路径，当前能在不增指令周期、不改容量/宏/课程口径的前提下直接落实的改造已汇集完成。

| 方向 | 当前结论 |
|---|---|
| 独立 memory 地址等待队列 / RS 分簇 | store→RS links 已去掉宽 tag 全表关联，同时保留共享十二行 RS 的容量和调度。进一步分簇需要 steering、跨簇 wake、容量利用和 replay 的取舍；现有五条路径不足以支持直接改这些职责 |
| RS 反向保存 LSQ 槽号 | 可用更少 index 状态，但每个 RS 行随后需查询 LSQ 身份/有效期；在 FF 数组上扩展十二份宽查询可能抵消匹配减少。此次采用 LSQ link，并按真正 RS release 失效 |
| load slow wake / report 新流水级 | 能切开反馈，但需要同步握手 owner 与 cancel，还新增 load-use 周期。先测六项不增指令周期的组合，若新锥仍穿越 load wake，再选择明确边界 |
| dependency pointer/matrix wake | 改变 rename/RS 依赖登记、释放、multi-successor 和 recovery；当前 source5 wake 后的宽 store 关联已移走。没有依据在十二行 RS 上加入更大矩阵来获取未证实收益 |
| 每行预计算地址 / 12 位立即数特化 | 前者复制算术，后者需各启用路径的立即数契约。此次通用共享 carry prefix 已改长进位，不混入格式假设或十二份 adders |
| 提前每个 tag/range 的全部资格 | 已完成 LSQ report row cancel 与 report bounds；其他资格属于正常 ROB/PRF 接受 authority，删除它们不属于等价 timing factoring |
| CSR/ISA/时钟边沿删改、缩容量、换库或放宽 STA | 不属于当前授权方向。容量、ISA、单时钟边沿、课程库与口径保持 |
| cache command FIFO、PRF SRAM、更多 MUL/DIV 段 | 本批覆盖的是已知 LSQ→wake→store AGU 锥和真实 refill 高负载。新的瓶颈需以新映射证据选择，不把已有架构段数作为必须继续增加的理由 |

这里没有声称全世界不存在其他方案；结论是经过当前证据与源契约评估，尚无另一个值得直接混入本批的可执行改造。继续只用旧五条路径推定修改后的主瓶颈，会变成猜测。六项完整组合已达到结构改变的测量时点，本报告先交付，再进入一次统一测量。

## 下一次统一原生后台测量

本报告写入并交付时尚未启动。下一目标轮测量同一 DM1 冻结身份，Windows 原生 PE 工具；只综合/STA 一次、CPU build 一次，原六项 perf 各一次。频率采用课程 period search，面积含 SRAM，IPC 按原 dynamic_instructions/cycles 的 GEOMEAN，latency10 不变。

复用该 exact CPU 执行已有短 `lsq_wrap_forward` 和 `recovery_reuse` 各一次。前者含等待 DIV 提供 store base 的场景、LSQ wrap 与 byte/half/word overlap；后者含保留旧任务、杀年轻 store 和恢复后再分配。它们是有限架构覆盖，不能宣称证明每种 link 内部状态。没有每改一项就测，没有重复编译 RTL，也没有自动重跑十九项全部 correctness。DF1 全套未跑，DD 原全套 16/19、pi/qsort/tak 一百万周期超时的事实继续保留。

测量在后台进行，期间继续阅读新产物和发展下一瓶颈方案。发现明确信息后再修正；不因状态或日志更新间隔重启同一批。若频率仍未达标，优先按新实际锥继续重构，并先报告下一组合。

课程框架 `54fc150ffc290f52aa024209ffb9a29d43856f6d`、cases `29f980727f7d99a1842a58f34091c7579ba3fe85`；Yosys0.63 `70a11c6bf0e8dd669f56c7da3587f78b405138e2`、ABC `8e401543d3ecf65e3a3631c7a271793a4d356cb0`、OpenSTA3.1.0 `f89887b59600cd3a2a10c3de31bda4235d904cdf`、Verilator5.020 `5c5314b39cd888f427807d626e1502cbf222c292` 保持。原 ASAP7 RVT TT、FakeRAM、约束和 scripts/synth.py / scripts/testcase.py / sim.cpp 保持；没有使用 WSL。

目标仍未完成：DM1 未测；最近可信 Fmax 仍为 DF1 的 294.337453291 MHz；面积、IPC 与完整正确性仍有既知缺口。不能以源级推导宣布 300 MHz 或 Tier3 已达成。
