# DT：完成仲裁与操作数旁路重构，测试前报告

本批已在主工作树实现并冻结，**没有启动 HDL 编译、lint、仿真、综合、STA 或形式验证**。DM1 的 302.154028 MHz 是上一版本的已测结果；DT 的频率、面积和 IPC 均未知。下面先交付实现、依据、代价和后续测量范围。

## 现有数据指向什么

课程工具链下 DM1：最低周期 3.3095703125 ns，Fmax 302.154028 MHz，含 SRAM 面积 51,130.672554 μm²，IPC 0.782372864。相对原课程基准，面积 +10.410302%、IPC −20.176455%，原 ±10% 条件和 Tier3 尚未满足。原六项 perf 的返回值通过，两个短程序共 176 项检查通过；全十九项 correctness 没有在 DM1 上运行。

本轮只读取已经生成的报告，没有重新调用 STA。现有五条最差样本的精确 arrival 都是 3.2491 ns；链条经过 LSQ report、正常 ROB 资格查询、完成仲裁、PRF 写回旁路和分配侧算术。已命名边界如下，均为同一路径上的累计时间：

| 边界 | 累计 ns | 本批处理 |
|---|---:|---|
| report_bound_tree 输入 bit4 | 0.3185 | 保留已测 DM1 的队列边界改法 |
| report row10 选择分发 | 0.7724 | 保留报文选择和完整标签 |
| completion source5 ROB 查询输入 | 1.0214 | 保留正常 ROB 权限来源 |
| ROB live read 第63行选择 | 1.1420 | 保留 valid/完整 generation 检查 |
| completion lane2/source1 payload 选择 | 1.7280 | 对迟到的 LSQ 资格预计算两种仲裁；拆出单 bit 写使能 |
| PRF write_address_tree bit16 | 1.9668 | 旁路比较移到每个 producer，提前与仲裁并行 |
| PRF read port6 bypass_choice 输入 | 2.1490 | 合并 CDB/PRF 的串行旁路数据选择 |
| PRF read port6 bypass 分发叶 | 2.2384 | 保留读端口最终选择，缩短其前方控制链 |
| endpoint D | 3.2491 | 缩短分配 store 的地址加法 |

末段有连续 MAJ/MAJI 算术门，与分配 store 地址加法相符。自动编号端点仍没有公开 RTL 别名，因此不把它描述成所有端点归属均已证明。约 −1.309 ns 的旧 slack 针对原 2 ns/500 MHz 请求，不能当作 300 MHz 下的违例。证据保存在[现成路径解析](F:/CPU2026Proofs/DM1_mapped_paths_20261005/saved_path_analysis.json)和[已测 DM1 报告](E:/Verilog_cpu/reports/frequency_DM1_measurement_2026-10-05.md)。

## 五项组合实现

| 顺序/候选 | 已实现的改动 | 目的与代价 |
|---|---|---|
| DP | 分配 store 使用专门的 signed-12 地址加法器 | 低12位三个4-bit carry-select 块；高20位只需 −1/0/+1 的并行前缀，不让低位进位穿过完整32位加法 |
| DQ | 每个 producer 的物理目的寄存器先与八个读查询比较，再按原完成 grants 选命中位 | 把“等仲裁选地址，再比较”变成并行计算；比较数量增加，保留实际写有效、P0、越界和最高端口优先级 |
| DR | 同时计算 LSQ 完成可参与/不可参与两种原仲裁结果；完整资格最后选结果 | 迟到的资格信号不必从头穿过排名/空闲 lane 计算；增加一份组合仲裁，完整标签、轮转、held-source 和握手保持 |
| DS | 先决定最高命中的实际写端口，再直接从该端口的 producer 路由操作数 | 合并 CDB 值选择与 PRF 旁路值选择；广播/组合路由成本可能增加，正常 PRF 状态写入仍走原端口 |
| DT | 实际 PRF 写使能由原 grants 和 producer 可写属性直接生成 | 不等待宽 metadata payload 回读写使能 bit；原 reset/flush、store 禁写、正常 ROB 资格仍约束写入 |

组合源码涉及五个 RTL 文件：[backend](E:/Verilog_cpu/rtl/backend/rv32_backend_joint.v:269)、[completion](E:/Verilog_cpu/rtl/backend/rv32_completion_network.v:162)、[PRF](E:/Verilog_cpu/rtl/rv32_physical_register_file.v:149)、[组合函数](E:/Verilog_cpu/rtl/common/rv32_asap7_fanout.v:514)、[CPU 接入](E:/Verilog_cpu/rtl/cpu_core.v:882)。

新增声明状态 **0 bit**；普通整数主流水线仍为 **10 级**。BE=4、CDB=3、producer=6、读端口=8、PRF/ROB=64、LSQ=16、RS=12、ROB generation=8、完整 ROB tag=17 bit；原39项课程配置保持。新的 CPU 内部使能只选择组合实现，standalone 默认保留旧接口行为。无新增 load-use、branch recovery、issue 或完成等待拍数；这表达设计意图，尚不等于已测 IPC 不变。

## 源码层面必须成立的条件

1. 地址算术：令 base=4096H+L，12-bit immediate 的无符号值为 U、符号位为 s，则结果低位是 L+U mod4096，高位是 H+carry12−s mod2²⁰。高位增加时低于该 bit 的原位全1才翻转，减少时全0才翻转。独立 standalone backend 默认仍用完整32位加法。CPU 的 store 解码器确实提供 S-type 符号扩展12位偏移；这一合同也符合[RISC-V RV32I 规范的 Load/Store 定义](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html)。未 ready 的分配地址 payload 可能改变，但地址就绪位仍清零，普通 AGU 路径随后写入正确地址。
2. 仲裁：对任意二值输入，F(e,x)=e?F(1,x):F(0,x)。两个副本使用原始排名方程、完整 producer/held tag 和相同轮转状态；最终 e 仍含原 normal ROB valid/generation 检查。没有以 LSQ 存活假设替代正常 ROB 权限，也没有采用 DG 的删除资格检查方案。
3. 旁路：每个 lane 的原 one-hot grant 选中哪个 producer，就选该 producer 的比较位。DS 用**实际 backend PRF write-valid**约束 lane hit，按原最高写端口规则决定获胜 lane，再选它的 producer 值。DT 的实际 write-valid 等于 !reset&&!flush&&OR(grant&&producer_rd_we&&!producer_is_store)，与原 direct 模式 cdb_valid&&cdb_rd_we 相同。
4. JAL/JALR：branch link 覆盖最后一个活动写端口时，同时覆盖比较和数据。即使 link 不命中当前读查询，也必须屏蔽该端口被覆盖的普通完成结果；匹配的低端口仍能提供值。这个边界已经明确编码，不能只覆盖数据而继续用普通完成的匹配位。
5. held-source、轮转更新、producer ready、CDB payload、reset/flush 和 completion FIFO 的原时序更新块保持。query-dependent 旁路命中不存入 held packet，每周期重新计算。

[源码审查记录](F:/CPU2026Proofs/DT_source_review_20261005/source_review.json)核对了候选文件 digest、原 grant 方程文本与 completion 时序块文本；这是文件/源码审查和手工代数推导，**不是 HDL 语法、完整功能/参数等价、面积或时序证明**。没有借此填入 PASS 或预测 MHz。

## 进一步方向与本批取舍

| 方向 | 当前判断 |
|---|---|
| 专门缩短地址进位、比较提前、仲裁迟到事件分解、旁路路由合并、局部写使能 | 已合并到 DT；不是逐个修改后逐个跑测试 |
| 取消同周期 PRF 旁路或将 LSQ 完成再寄存一拍 | 能直接切路径，但增加依赖等待；当前 IPC 已明显低于约束，不在本批增加这种延迟 |
| full ROB generation 在每个查询/每个行前并行比较，再归约单 bit | 可以移走动态表读后的比较，但会把少量查询扩大到多行比较并增加查询扇出；目前不能给出受控面积/负载依据，保留完整正常检查 |
| producer 直接旁路到 RS | DM1 已有直接 wake，普通 ALU 已能在接收结果同一边沿接受下一条；不重复实现已存在的吞吐能力 |
| DN 的 registered store probe、DO1 的额外 store 地址 packet | 未采用未测试；对应旧共享 store AGU 锥，新最差样本已经迁移，packet 还增加99 bit和一拍 |
| 减 issue/CDB/窗口/缓存容量或加更多流水寄存器 | 可减负载/逻辑，但有实际吞吐、延迟和状态代价；不以缩参数或加级替代本批关键依赖重构 |
| 升级更多 buffers、盲目复制查询和旁路 | 新数据未显示当前五条样本有超 max-cap 的门；仅凭旧家族不能继续任意加缓冲 |
| 更广的 cache、divider、乘法内部重构 | 不在目前五条最差样本中；保留研究方向，待本批路径迁移证据支持再实施 |

本批把目前数据明确支持、且可不增加指令周期的五项改法做成了完整组合。我没有发现还应立即合入的另一项同类改法。无法证明已经穷尽所有 CPU 设计；更大方案仍有明确代价，而新的关键路径只能由之后的一次整批测量确定。唤醒/选择/旁路反馈的复杂度问题可参照[Palacharla、Jouppi、Smith，ISCA 1997](https://ftp.cs.wisc.edu/sohi/papers/1997/isca.complexity.pdf)，[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)也区分固定结果快唤醒与可变延迟结果的慢唤醒。它们帮助判断结构，不能直接替代本工程的 MHz 或 IPC 数据。

## 测量范围：交付本报告之后再开始

**本次汇报时仍未开测。**后续第一阶段只对 DT 冻结源码调用一次原课程 synth.py：原生 Windows、固定 Yosys/ABC/OpenSTA 和 ASAP7 RVT TT/FakeRAM，原2 ns请求与原频率搜索约束；测 Fmax 和含 SRAM 面积。没有 CPU simulator build，没有 IPC/功能程序。主工作树和上一已测 DM1 均已备份，不测 DP/DQ/DR/DS 中间候选，不重跑 DN/DO1。

只有第一阶段显示值得继续验证的明显收益，才进入 Verilator/程序阶段。当前建议把 **约350 MHz（比 DM1 高约15.8%）**作为“明显提频”的工作判据，同时审查总面积；这不是已获得的结果，也不改变原 Tier3/±10%要求。没有明显收益就根据新路径继续实现，保持 IPC/功能程序挂起。

若进入第二阶段，复用第一阶段相同 source/config/tool/library identity 的综合报告，不重新综合；仅 build 一次 exact CPU，原六项 perf 各一次，复用已有的两个内存/恢复短程序，覆盖有限场景。完整十九项 correctness 留待真实收益确认、准备正式采用时完成，不将短程序当作完整证明，也不自动改动一百万周期上限或删除已有超时。两阶段均在后台；运行期间继续读现成数据与研究源码，不对另一工作树版本填入这个结果。

已将原生测量包装器加入 `--timing-only` 和 `--reuse-synth` 阶段模式；只是源码编辑，没有调用它。原课程 scripts、sim.cpp、库、工具版本、latency=10 和 perf 指标口径未修改。所有原有默认测量行为保留。

候选链 `DM1 → DP → DQ → DR → DS → DT` 的原始源码与补丁均保留。DT 原始候选 manifest SHA256：`0f302044a6dacc78d5ea17799e5ac8ac4cb855de8d666544000b9960c9ca3734`；完整五文件变化见[相对已测 DM1 的补丁](F:/CPU2026Candidates/frequency_research_20261003/DT_completion_local_prf_enable/changes_vs_measured_DM1.patch)。冻结运行目录为 `F:/CPU2026CourseRuns/architecture_DT_20261005`，40项活动输入/157项冻结输入，尚无新的测量输出。上一工作树完整身份备份于 `F:/CPU2026Candidates/pre_DT_worktree_20261005/backup.json`。
