# CD1 冻结后研究：下一次结构选择需要什么证据

本稿最初写于 [CD1 冻结批次](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)运行期间；CD1 已结束，结果为 99.65936739659368 MHz / IPC 0.7823728642153719 / 含 SRAM 面积 49851.29213392186 µm² / 正确性 16/19，没有仍在运行的 CD1 测试。随后源码迭代到 CU1，并准备 CV；所有后续批次均未启动新硬件测试。以下保留研究条件，并在发现源码假设不成立时明确纠正，不把源码规模变化记作频率收益。

## 资料提供的约束

BOOM v4 源码分别组织执行结果旁路、唤醒、PRF 写入和 ROB 完成：ALU 唤醒可来自快速唤醒接口，ROB 接收完成使用另外的分支过滤和寄存路径。这支持分开考虑消费者的数据可用性与提交身份，但不能直接复制其时序承诺：本设计有可变反压的 issue FIFO，提前唤醒必须保证操作数到达，不能仅以“已经发射”代替“结果可用”。[BOOM v4 core.scala](https://github.com/riscv-boom/riscv-boom/blob/master/src/main/scala/v4/exu/core.scala)

Palacharla 的原始研究将窗口唤醒/选择、旁路和寄存器文件作为复杂度与时钟的共同约束。分簇可以减少局部负载，同时需要处理负载均衡、指令导向和跨簇通信；把相关链的唤醒/选择拆成多个阶段会引入依赖气泡。其技术节点、机器宽度和模型与本课程 ASAP7 流程不同，文中的收益数字不能套用。[Complexity-Effective Superscalar Processors，原始论文](https://www.princeton.edu/~rblee/ELE572Papers/ComplexityEffectiveSuperscalar_palacharla.pdf)、[作者博士论文，第 2–3 章](https://jes.ece.wisc.edu/papers/subba.thesis.pdf)

## 后续方案与采用条件

| 新测量中实际最慢的结构 | 后续候选 | 必须先解决的问题 |
|---|---|---|
| RS wake→rank→operand select | 保持物理 wake，进一步局部调度或 INT/memory/MDU 分队列；若采用依赖链导向，不能只按指令类型硬分簇 | 12-row 总容量的均衡、每类 dispatch 保留、跨簇 RAW、最老 branch/load 调度；需证明新网络比现有 pair/rank 短 |
| producer ROB live/gen query→RS wake | 调整 producer 所有权边界；考虑在执行单元内部主动清除错误路径任务，减少完成阶段集中查询 | 每个 ALU/MDU/LSQ 的恢复取消、持有反压、generation 重用；MDU 仅 whole-core flush 的旧行为不能据此假定已安全取消 |
| D-stage PRF 读→RS allocation | 移动原 D 边界、采用 metadata-only RS 和专用读寄存器阶段 | 早期 store probe 额外读取、未写 PRF 的 held result、FIFO 任意停顿、read hazard/reissue；不能直接串 PRF 和 ALU，也不能无理由增加第十一级 |
| 前端 response→prediction→next PC | 预取或 lookahead 预测，重排现有入口/响应寄存边界 | response PC/epoch 精确对应、同拍接续、line 边界、恢复期间旧 response、不能重复使用先前 PC 的预测 |
| Icache/Dcache/AXI 行查询或控制 | 对实际超载的最终 mapped driver 重新分组；若确为 SRAM→逻辑→SRAM 跨级路径，再移现有缓存边界 | 读延迟、miss/MSHR/waiter 生命周期、load/store 排序、AXI ID、正常与 MMIO 两类事务，不修改课程 SRAM 或约束 |
| 仍由一个控制门驱动大量最终 mux | 将控制资格判断移到其局部消费者，或进一步减少依赖该控制的无效 payload | 以 pin 电容/输出 slew 和真实扇出确认，不能仅统计 RTL 引用；已有反相器分发是否保留及面积必须实测 |

当前不自动采用所有方向。先拿到 CD1 的路径、电容、slew、IPC 和含 SRAM 面积，选择影响最大且不会把问题移到相邻阶段的一项；没有新关键路径之前，不再无依据扩大 RTL 改动范围。

## 唤醒前集中存活查询：进一步源码推导

2026-10-04 冻结后逐段核对。当前直接唤醒已经绕过 CDB 仲裁，但仍经过 `producer_target_live_r`：每路 producer tag 查询 ROB 的 valid/generation，再检查恢复年龄，最后得到 RS wake valid。若 CD1 报告显示该查询是主要延迟，下一轮可以把执行任务的存活所有权移到执行单元内部，切断 `ROB query → wake → rank → operand route` 的前半段。这是待实现方案，未合入 CD1，也没有频率收益数字。

本地取消必须覆盖以下状态，而不是只给 MDU 输出端增加一个 kill 门：

| 当前源状态 | 源码证据 | 候选取消动作 |
|---|---|---|
| ALU 的单个保持结果 | backend 的 `alu_flush_r` 已按恢复年龄选择性清除；完整 tag 保留 | 核对每次 issue/held/recovery 同拍优先级；只有本地有效性足够严格才绕过 wake 的 ROB 查询 |
| MDU launch buffer | `pending_valid/tag/live`；当前只有 whole-core flush | 单独比较 pending tag，恢复边沿清除年轻请求，禁止同拍把它转移到执行单元 |
| Wallace MUL 的 s1、s2、out | 每段已有 valid/tag/live；恢复信息目前未接入 | 每段独立取消，取消优先于转移与补入；严格更老结果继续推进或保持 |
| DIV 的 busy/prepare/finish/result | 请求 tag 从接收直到结果保持都存在；当前只有 whole-core flush | 一次请求身份覆盖整个迭代和结果阶段；取消年轻请求，保留更老请求及有效结果 |
| MDU 完成仲裁及 inflight_count | mul 优先、div 反压；计数按 req_fire/completion_fire 增减 | 取消不能伪造完成握手；计数必须计入被取消的在途任务，或由各段真正占用状态导出 |
| LSQ load completion | LSQ 已有按恢复年龄截断；物理目的仍由 map 查询取得 | 先证明响应归属、被取消 waiter 和 slot 重用，不能把 ALU 的结论直接套到 load |

关键不变量是：被释放的物理编号重新分配前，旧任务已失去所有唤醒和写入资格；恢复当拍停止新分配，年轻消费者被取消，严格更老的消费者不可能依赖年轻 producer。最后一句依赖正确的 rename/回收及所有缓存响应归属，不能用程序顺序直觉代替实现证明。完成/PRF/ROB 的 generation 防护在候选早期应继续保留，先只拆开唤醒的资格路径。

香山公开设计把当拍选择与晚到取消分开计算，并用 issue 响应确认成功后才释放队列项；这提供了可借鉴的边界，但本设计采用非推测的结果唤醒和可变反压 issue FIFO，不能直接复制其提前唤醒协议。[IssueQueueEntries：Issue and Dequeue / Wakeup and Cancellation](https://docs.xiangshan.cc/projects/design/en/kunminghu-v2/backend/Schedule_And_Issue/IssueQueueEntries/)。如果把取消推迟到已选指令之后，必须在进入不可撤销的 store、MMIO、PRF 或提交前消除它，且不能在队列出队时遗失重试责任。

额外核对排除了一个无效提案：当前 RS 的 ready rank 已使用二叉 popcount，年龄顺序也已来自寄存 pair matrix；不能再次把“把线性 rank 求和改成平衡树”写作新优化。后续若 rank 本身成为瓶颈，应比较饱和计数/局部分组选择的实际层数与负载，而不是重复已完成的结构。

### Load 目的物理编号的边界选择

进一步检查 `load_phys_map_read` 及其写入者后纠正初步假设：它现在已经是 **LSQ_ENTRIES=16** 的 6-bit 表，按 `lsq_load_complete_lsq_tag` 查询，而不是 64-row ROB 物理表。因此仅把这个表搬到 LSQ 内部不会缩短查询，也不能宣称从 64→16 获益。

再次逐段读取 LSQ 后，**纠正此前“已有 completion buffer”的假设**：LSQ 没有独立的 load-completion 寄存缓冲，完成值保存在各行，report 是组合选择输出。因此不能声称在已有输出寄存边沿增加字段。

已准备 [CV 源码候选](F:/CPU2026Candidates/frequency_research_20261003/CV_lsq_parallel_report_destination/candidate.json)：将原 16×6=96 位分配表移入 LSQ，每行 report 附带同一行的目的编号，原 report 树并行选出 value/tag/phys，backend 删除第二次表读。没有新增寄存器或周期，当前 67→73 位的 report 仍为五个 16 位组。分配边沿、无 reset payload、原 highest-lane 写优先级保留；响应归属、full tag/generation、ready、错误和 recovery 防护不变。有效事务保持目的一致；无效 report 的新目的为零，不宣称无效 payload 逐位相等。详细推导见 [CV 实现报告](E:/Verilog_cpu/reports/frequency_batch_CV_implementation_2026-10-04.md)。没有频率/面积/IPC 或硬件正确性证据，不能承诺这项是全核关键路径。

## 现有报告读取准备

新增 [Windows 原生现成报告汇总工具](E:/Verilog_cpu/tools/summarize_course_frequency_native.py)。它只读取冻结清单、原课程报告和原 Liberty 文件，校验输入身份，把现有关键路径按到达时间排序，并记录单门延迟、电容、明确的 max_capacitance 和 slew。工具不包含 HDL/综合/STA/仿真调用；课程报告尚未生成时不会补跑测试。原课程导出的五条路径只是最慢样本，不能据此声称列出了所有端点。

输出的建议是待验证推断：负载超限优先追查最终驱动及消费者，正常负载则追查串行逻辑。2 ns 约束下的负裕量不能直接解释为未达 300 MHz，最终使用原课程最小周期搜索结果，包括 setup、pulse width 和 period 检查。当前工具尚未处理 CD1 数值结果，因为官方结果仍未产生。

## 固定映射流程对结构选择的影响

已对照课程 `scripts/synth.py` 和本次安装的 Yosys 精确 commit `70a11c6bf0e8dd669f56c7da3587f78b405138e2`。课程命令为 `abc -liberty ... -D 2000`，没有 `-constr` 和自定义 script。该版本按有无 constr 选择两个默认脚本；本次所用的默认库映射脚本不包含后置 `buffer/upsize/dnsize`，带 constr 的另一脚本才包含它们。[固定版本 abc.cc](https://raw.githubusercontent.com/YosysHQ/yosys/70a11c6bf0e8dd669f56c7da3587f78b405138e2/passes/techmap/abc.cc)。这不表示 ABC 完全不做门型/时序优化，但不能假设它会为最终巨大消费者网络补齐物理缓冲树。

同一版本的 flatten 实现尊重 cell 或 module 的 `keep_hierarchy`。[固定版本 flatten.cc](https://raw.githubusercontent.com/YosysHQ/yosys/70a11c6bf0e8dd669f56c7da3587f78b405138e2/passes/hierarchy/flatten.cc)。因此本批采用完整普通 RTL 反相模块边界，将控制分发落到最终少量消费者；原课程必须真实映射并计价这些门。是否发生意料外的优化、是否仍有末端超载，只能由本批 mapped netlist 和 STA 电容确认。保持课程工具、命令、SRAM 白名单、库和约束原样，不以修改评分流程补救 RTL。

## 结果解释

1. 编译成功只表示工具可以处理源码，不能证明 ISA 或协议正确；之前 pi/qsort/tak 超时仍需官方 suite 给出结果。
2. 若综合失败，必须区分普通 RTL 合规/映射错误和 Fmax 未达标，不能用 2 ns 约束声称 500 MHz。
3. 若大延迟由负载表外推主导，优先看最终消费者与驱动；若变成正常负载下的串行逻辑深度，才重新划分边界。
4. 若达到 300 MHz 但 IPC/面积仍不满足约束，保留频率成果，按同源码结果恢复吞吐或削减冗余。Tier3 与此前 ±10% 的比较均独立报告，不以其中一项代替另一项。
