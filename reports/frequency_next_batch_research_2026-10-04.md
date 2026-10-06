# L1 测量期间继续准备的优化

以下为独立源码候选，**没有编译、仿真、综合或 STA，没有并入正在测量的 L1，也不声称已提升频率**。主工作树/测试快照保持 L1；独立候选可按模块取舍，不要求将整个链一次采用。

**课程兼容性修正：**L1 后来被原课程 `fakeram.py` 拒绝外部 BUF 黑盒。这些候选继承同一缓冲器文件，以下库单元数量和毛面积只是历史源码估算，不能认为课程已经接受或完成计价。下一批先替换为完整普通 RTL 分发模块；不修改课程工具或绕过 SRAM 规则。

后续 S→AB 已完成上述机制替换、更多状态 ownership、并行分配及算术链拆分，并更新主工作树；均未启动硬件测量。[最新结构重构记录](E:/Verilog_cpu/reports/frequency_rtl_restructure_2026-10-04.md)。以下 M/N/O/P/Q/R 为其独立探索历史。

## M：寄存的物理寄存器候选池

[候选与 SHA](F:/CPU2026Candidates/frequency_research_20261003/M_registered_free_pool/candidate.json)。现有 rename 连续进行四次最低空闲编号选择，再进入同束 RAW/WAW 旁路、PRF 与 RS。M 在编号选择与 rename 使用之间加入四项候选池，保留编号和数量；不增加普通指令阶段。

参考 [BOOM v4 RenameFreeList](https://github.com/riscv-boom/riscv-boom/blob/master/src/main/scala/v4/exu/rename/rename-freelist.scala) 的候选寄存机制：本实现自行设计为密集池和本项目的增量恢复，不直接复制代码。BOOM 的 [SelectFirstN](https://github.com/riscv-boom/riscv-boom/blob/master/src/main/scala/v4/util/util.scala) 仍是级联选择，所以有用之处是把搜索隔离在保留项补充路径，而非仅模仿优先编码器写法。

协议与人工推理：

1. `free_count` 继续统计所有尚未分配的物理寄存器。原始位图 U 不含保留池 P，两者无交集；公开逻辑 free bitmap 为 `U | P`。
2. 本拍分配 A 项，只取寄存池前缀。余项移到前部；从原始 U 选出的不同编号补充空位，并从 U 清除这些补充项 B。补充和分配不改变互斥性质。
3. 提交归还的旧映射 C 写回 U。ISA/ROB 的原有所有权保证它们尚未在逻辑 free bitmap 中。可用总数满足 `F'=F-A+C`，保留动作不改变 F。
4. rename 的 ready/count 直接使用寄存池数量，不再叠加一个保守 credit 拍；池满且 U 充足时，消耗四项并补四项可以每拍持续。
5. recovery 输入采用当前完整逻辑 free bitmap 加 killed suffix 增量。清空保留池，把所有未分配的池项返还原始位图，再重新补充；不能只清 pool valid 而遗失编号。
6. reset/recovery 后有补充等待；池顺序可能不同于每拍全局最低编号选择。这是分配策略变化，正确性依赖唯一所有权，不依赖寄存器编号大小。

当前配置新增池 27 个寄存位，取消旧 3-bit PRF credit 后净约 24 位，写入缓冲 8 个。实际剪除与映射尚未计价。

## N：RAT 恢复的局部选择

[候选与 SHA](F:/CPU2026Candidates/frequency_research_20261003/N_grouped_rat_recovery/candidate.json)。新增独立内部 `IMPL=2`，保留原 0/1；课程顶层 39 项参数不变。没有新增恢复周期。

ROB 深度是 2 的幂。每行年龄、分支年龄均可用 SLOT_WIDTH 位减法得到模 ROB_ENTRIES 差，数值范围 0..N-1，与旧 compare/wrap 结果相同。占用量仍保留 COUNT_WIDTH，能表示满深度 N。

对每个架构寄存器，分别在八行组内及组间找 `first-any` 和 `first-upper`，完成两份物理编号值选择后才用 `upper_found` 选择结果。旧版把 `upper_found` 广播进全部 64 个优先输入；新版只选择最后 PAW 位值。最低命中必须同时满足“本组没有更低命中”和“更低组没有命中”，所以仍是原有最低槽位选择。选择高于 branch slot 的最低槽位、否则最低任意槽位，仍等于环形顺序的最老 killed writer。最后保留分支自己的新映射不变。

每行 killed/upper 输出经真实计价的库缓冲分配到 31 个架构寄存器比较，新增约 256 个 BUFx16f，毛面积 82.11456 µm²；并行选择额外逻辑成本须测量。

## O：保留池的查询负载

[候选与 SHA](F:/CPU2026Candidates/frequency_research_20261003/O_local_free_pool_queries/candidate.json)。新寄存边界仍可能产生大电气扇出：池编号与 valid 要参与 64 位逻辑 free bitmap 查询。O 为编号及 valid 的广播使用课程原库的实际驱动，避免把路径挪到一个高扇出的新 FF/弱比较输出上。当前配置增加 56 个 BUFx16f，毛面积 17.96256 µm²，不增加寄存位或周期。

## P：PRF 每行的最终写拥有者

[候选与 SHA](F:/CPU2026Candidates/frequency_research_20261003/P_local_prf_storage/candidate.json)。保留当前 PRF 读接口与同拍 WB bypass；新内部 `LOCAL_VALUE_ROWS` 选择每行的数据/ready 拥有者，未采用的旧存储只作为可选实现。

对每个非零物理寄存器，分别匹配 allocation 与 writeback 编号。写回选择先生成“最高编号有效匹配 lane”的 one-hot grant，再平衡合并 32-bit 值，最终 write enable 在本行包含 `!reset` 后通过真实驱动。数据寄存过程没有后置 reset/flush 控制；ready 位独立 reset，writeback 优先于 allocation，和旧 NBA 顺序相同。P0 硬连零/ready；非法编号不能匹配任何行，原 read/bypass 的边界规则保留。

写回数据、写回/分配地址与 valid 分为四个局部域；读地址也由真实驱动进入原有并行读选择。当前 64 项、四宽配置，缓冲源码毛计数约 1646 个（read96、write value640、write/alloc address240、valid40、row grants504、row enables126），毛面积 527.97096 µm²。不增加流水级或有效状态位；替代级联写选择的逻辑成本和旧私有数组剪除须在网表核实。

## Q：Icache 回应数据写入

[候选与 SHA](F:/CPU2026Candidates/frequency_research_20261003/Q_icache_response_data_owner/candidate.json)。128-bit 回应数据原先在统一 reset/回应状态过程里分别做 SRAM 保留和内存回应写入。Q 把这两条来源合成一个最终写拥有者，保持“活跃内存回应覆盖旧 SRAM 拷贝”的原 NBA 优先级，之后按四个 32-bit word 分配真实写/选择驱动。

promotion 优先于 MSHR 原有 demand；它们各自保持 epoch 合格条件，内存回应必须完成 valid/ready 握手。reset 禁止写入，valid/error/PC/epoch 仍归原过程所有；无效 data payload 不再要求为零。回压时 SRAM 数据转入保持寄存的行为保留。不新增状态位或周期，新增 10 个 BUFx16f，毛面积 3.2076 µm²。仍未编译或验证。

## R：取指空队列直达的权衡方案

[候选与 SHA](F:/CPU2026Candidates/frequency_research_20261003/R_icache_empty_bypass_tradeoff/candidate.json)。L1 已完成六项 perf，IPC 约 0.8005，下降约 18.3%，因此需要处理吞吐损失。官方 `perf_multiply/program.S` 是移位加法循环，没有 MUL/DIV，不能以 benchmark 名字误判为新乘法器导致退步。上层 MDU 源码本来支持同边沿补充请求，也不是单项串行完成后才接收下一项。

R 在两项 Icache 请求队列为空时允许当前请求直接做内部 lookup；公开输入 ready 仍只依赖寄存占用。内部 lookup 若不接受，请求在已承诺的空位中保存；旧 epoch 直接丢弃或从队列独立排空；同时出入队的环形顺序不变。理想 warm lookup 可免去新增请求存储一拍，但**会重新打开 predicted-PC→tag/array 的前向组合路径**。这是明确的频率/IPC 权衡，不是无代价的流水化。

保留为独立未测候选，增加 3 个真实缓冲、不新增 FF。要等 L1 的时序路径判断此反馈隔离是否足够、前向路径能否容纳在 3.333 ns；当前不采用，也不另外启动测试。更完整的 FTQ/提前 BTB 预测路线可保留双边界，但需要处理 MSHR 回应顺序、同 PC 多项请求、epoch 恢复和预测修正。

## 更大的替代路线

| 路线 | 可解决的问题 | 必须先厘清的协议/代价 |
|---|---|---|
| PRF 读取移到 issue 之后 | 将 rename/RAT/PRF/RS 数据写路径拆成独立周期，RS 可只保留物理源编号 | 修改当前 data-in-RS 协议；增加 operand-read 阶段；保证 recovery、同拍 WB 旁路及读口冲突 |
| Fast wakeup 与可变延迟 wakeup 分离 | 缩短固定延迟 ALU 的调度反馈 | 当前 RS 保存值，不能只提前置 ready 却没有正确操作数；必须定义 bypass/reservation/replay |
| 分簇 issue 与 PRF 银行 | 缩小选择和广播范围 | 银行冲突、跨簇依赖周期、写回端口与 IPC；不能直接把大型开源 CPU 的频率套用 |
| 取指多项请求窗口 | 抵消 Icache 新寄存入口对单项等待 frontend 的吞吐影响 | MSHR 回应可能乱序；需要 PC/epoch 身份与按程序顺序的行供给、分支重定向清理 |

这些路线继续做源码分析，是否采用取决于 L1 的新路径、IPC 与面积。频率仍为第一目标；必要代价明确计入。测试运行期间不修改其冻结源码，不为每个小候选启动测试。
