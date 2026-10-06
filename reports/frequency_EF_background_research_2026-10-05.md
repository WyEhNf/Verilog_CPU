# EF 后台测量期间：把 store 加法前移到 PRF 旁路选择之前

EF 已完成一次 Windows 原生 timing-only 测量，370.477569 MHz、含 SRAM 49,116.955854 μm²；IPC/功能未测。这里记录一个条件方向及其后续源码实现。独立 EG 备选已创建并完成源码关系审查，未采用、未测量。EF 工作区与冻结源保持一致，不据此启动第二个综合。

EA 的慢路径由 PRF 写回物理地址匹配/旁路控制，经选择出来的 32 位值，再走 allocation signed-12 加法器。EF 删去可选分配当拍地址，代价是地址可用时间更晚。可以另存一个保留该功能的方向：在 PRF 旁路控制尚未完成时，并行计算候选数据加 store offset，之后用相同旁路最高槽优先级选择完整地址。

令 `f(x)=x+sign_extend(offset12) mod 2^32`。对一个确定的原选择 `sel`，`f(mux(sel,x0,...,xn)) = mux(sel,f(x0),...,f(xn))`。它并不缩短 CDB 本身；它让地址加法与物理地址匹配/priority 控制重叠，避免完整加法串在旁路数据输出之后。能否提高全局频率仍未知。

具体接口计划是 PRF 加一个默认关闭的组合地址输出，只对每个分配槽的偶数读口实现。复用原 `stored_tree[1]`、`bypass_match`、写回 data 和最高槽优先级，不引入新的物理寄存器匹配，也不绕过 normal ROB valid/generation。输入为该槽的 12 位 decoder offset，候选为旧 PRF 数据与 BE_WIDTH 路原 PRF 写回数据。后端模式只有同时启用 parallel PRF read 和 signed-12 合同时才选新输出；通用/独立配置保留原接口行为。

P0/range 检查继续来自原 `legal` 和原匹配；原 read_ready、同 bundle RAW 清 ready、完整 tag、branch-link 写回最高槽、恢复和 CDB 回压都保留。只能在原 `rs_src1_ready` 下发布分配地址。不能为了提前计算而把任何 write candidate 当成已经有效，也不能在原输出之前保存未经当前 identity 检查的 ready 授权。

旧 PRF 值与每路写回值各一个加法器，当前四分配槽、四写回槽共 `4×(1+4)=20` 个；EA 原来四个，增加 16 个。只读取 EA 已完成的 `report.json/area/module_tree`：五个 `rv32_frequency_add_simm12` 实例各为 14.215500 μm²，其中 direct 13.515660、子树差额 0.699840，无 sequential 或 SRAM。因此按相同旧实例计价，纯新增加法器约 `16×14.2155=227.448 μm²`。EF 相对其已删除分配加法器的实现则需加入完整 20 个，粗估 284.310 μm²。

这些是旧映射规模估算，不能当成新面积。新选择器、查询和数据分发的缓冲、优化合并/裁剪，以及新 slew/load 都可能改变结果。原 EA 总面积 49,279.056294，原 +10% 上限 50,940.662839，余量 1,661.606545 μm²；这个方向从量级上值得做源码备选，不证明新总面积一定在范围内。

EG 已先作为独立备选实现并比较源码结构。应先结合 EF 的实际频率、面积与限制路径，再决定后续完整组合；任何新测量前先汇报。它若成功，能够保留分配提前地址的周期，而不是支付 EF 的潜在 store-conflict 延迟。若 EF 新瓶颈已经转移，保留当前结果，不能将这里的局部推导冒充下一轮全局收益。当前没有该方向的 HDL、仿真、综合、STA 或 IPC 结果。

原面积证据：`F:/CPU2026CourseRuns/architecture_EA_20261005/result/synth/opt/report.json`。

冻结 EF：`F:/CPU2026CourseRuns/architecture_EF_20261005`。

## EG 已实现，源码审查结果

EG 位于 `F:/CPU2026Candidates/frequency_research_20261003/EG_prf_parallel_store_address`，仅 PRF、backend joint、CPU core 三个 RTL 与 EF 不同。新模式 2 在 PRF 内并行算旧存储值和各写回值的地址，之后复用原旁路匹配和最高槽优先级。模式 0 保留 EF，模式 1 保留原后加法器；不支持 parallel/signed-12 合同时回到原实现。

核对候选 41 个源、主工作区 40 个源及冻结 EF 157 个源的哈希。69 个 begin/end 时钟块文本与 EF 相同；原 PRF 存储读树、旁路比较、数据/ready 输出、legacy 读写后缀，以及后端 ready/同批依赖段均保持原文本。普通整数流水线仍为 10 级，零新增状态。此项仅源码关系审查，不是 HDL、功能、等价或时序测试。

当前课程顶层明确 `BE_WIDTH=4`、`PRF_READ_MUX_IMPL=1`；通用宏默认宽度为 1，不能用宏默认代替实际测量配置。新分配加法器共 20 个；未声称全局频率收益或面积达标。EF 的实测结果只能属于 EF。

源码审查：`F:/CPU2026Proofs/EG_source_review_20261005/source_review.json`。候选 manifest SHA256：`1a47868a051181e90ab7f53da4cf286f799267ba14076965c2196e24c80853ab`。

## EH 与 EI：两种通知/共享探测边界备选

EH 将 RS 当拍旁路分为低编号四个 ALU 快速端口与 MDU/LSQ 慢端口。慢端口仍按原式写入现有行寄存器；同拍发射的 readiness 和数据都只来自快速分区。原 first-grant 向量分区后 OR 合并，保留原顺序写值；没有新状态。它可能增加 load/MDU 直接依赖的一次发射等待，IPC 未知。默认 SAME_CYCLE_WAKE_PORTS=WAKE_WIDTH 保留通用行为。

EI 是更窄的平行备选，继承 EG 并行分配地址。只有共享 store 基址探测读取已有 src1 ready/value 寄存器，普通 issue 的所有 wake、优先级、操作数和选择文本保持原样。EF 第一条慢路径明确经过当前拍 LSQ wake -> shared probe，因此 EI 有直接路径依据。新醒来的共享基址可能晚于 EF 可用，正常 ALU 地址更新仍可先完成；不声称 IPC 已保住。

两者各核对 41 个候选输入、69 个 begin/end 时钟块；EF 主源 40 个、冻结输入 157 个保持原哈希。两者均未采用、未运行 HDL/仿真/综合/STA，不能使用 EF 的 370.48 MHz 作为其测量值。

BOOM 将 ALU 快速通知与 load/variable-latency 慢通知分开：[Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)。这里的 EH 仍用现有已有效的 ALU held-result 通知，没有提前预告未来结果，亦未引入 speculative issue/replay。EI 则只对共享 store 探测作窄范围边界调整。

EH 审查：`F:/CPU2026Proofs/EH_source_review_20261005/source_review.json`。EI 审查：`F:/CPU2026Proofs/EI_source_review_20261005/source_review.json`。

## EJ：响应行直接选择与字节偏移预解码，已实现

EJ 继承 EI。响应匹配继续用原 `dcache_resp_valid && tag_matches_slot && response_wait`，保留原 valid/generation 权限；payload 直接按相同最高匹配行优先级选择，不再经过 `response_slot` 编码后解码。无匹配时选择原默认行 0，即使出现多个匹配也保留原最后行优先级。原 response_match/slot/fire 控制段保持原文本。

每行保存的 4 位地址偏移在行选择前变为 16 位 one-hot 组合码；当前 query 从 60 位变为 72 位，零新增状态。原 line extractor 的四个串行 byte-offset 路由改为同一偏移的固定 32 位 byte-window 选择，越过 128 位行末的部分填零。按位等同 `low32(line >> (8*offset))`，不依赖自然对齐假设。原 line-valid 选择、转发合并、LB/LH 符号扩展/无符号扩展、LW、恢复过滤和写入事件均保持原文本。

新增选择器及宽查询可能改变负载、面积和全局频率。EJ 没有任何编译、仿真、综合、STA 或 IPC 结果；源码审查只核对 41 个输入、69 个时钟块及以上二值关系。没有用当前 EF 370.48 MHz 作为 EJ 结果。

EJ 审查：`F:/CPU2026Proofs/EJ_source_review_20261005/source_review.json`。先继续定位 EF 缓存响应的 50 负载慢门，再明确最终组合，测试前另行汇报；当前不启动任何新测试。

## EK：返回完整身份的四行比较域，已实现

只读取 EF 已生成的 design.json，按公开输入端口、库 cell 类型、STA 实际负载数及相邻 INV 拓扑交叉匹配 Verilog 与 JSON 私有门名。0.1909 ns 的 AOI21 输出有 18 个直接输入连接，其中 16 个为 XNOR2；其选择输入来自低 LSQ response-tag 输出分组。具体私有 tag 位未命名，不能仅凭后缀认定字段。EK 针对接收端全 tag 比较的可见宽负载，让每个返回 tag/valid 位通过四行域再比较；不删除 generation、有效位或 response_wait 条件。

原 scalar 响应行遍历和 EJ direct query 复用相同的每行 match；返回匹配函数保持原文本。当前四个域，每叶至多四行比较；零新增状态/周期。额外分发深度可能抵消负载收益，未声称已提升新频率。

另一个 0.2913 ns、50 负载 AOI221 及其 INV 已与 JSON 精确对应；它们从 response_read 的第 0/2 行低包分组取输入，输出没有公开别名。只凭此不能确定完整字段/布尔含义，不能声称已被 EK 消除。查询其三个私有输入的直接 INV 别名没有找到结果；保留这个未决项，不根据猜测改缓存状态权限。

EK 审查：`F:/CPU2026Proofs/EK_source_review_20261005/source_review.json`。门及负载对应：`F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json`。输入极性补查：`F:/CPU2026Proofs/EF_selected_field_polarity_20261005/summary.json`。没有执行新的综合、STA、仿真或程序。

目前主工作区仍为实测 EF。EG/EH/EI/EJ/EK 均只是独立备选或源码组合，不能使用 EF 的实测指标。后续先处理上述剩余控制负载与最终组合取舍，再提供测试前完整汇报；不分别测量中间候选。

## EL1：地址先比较再选择，最终组合源码审查

继续只读 EF 保存的 JSON。此前查询极性方向未得到别名，不据此认定字段；这次追溯四个所选寄存器的 D 输入，各锥均到达 MSHR lifecycle 的 dirty_victim 第 14 位。与源码中 writeback <= dirty_victim 的状态更新相符，形成 writeback 字段的强数据流推断；仍不是私有网形式等价证明。

EL1 继承 EG→EI→EJ→EK，只改 Dcache：每行将返回地址与完整 victim 地址及低四位清零的 demand 地址分别比较，以该行 writeback 选择匹配结果，再按返回 ID 选择一位 Boolean。原 response_found 的范围、valid、sent 条件及所有消费者/时钟块保留。当前 4 MSHR，因此源码包含 8 个 32 位比较，新增输入负载及面积未知。这样去掉晚到的选后 writeback 驱动 32 位地址 mux 再比较的串行联系，不声称已消除整个 50-load 门或测得收益。

最终源码链 EF→EG→EI→EJ→EK→EL1 共核对 41 个候选输入；69 个复合时钟块与 EF 相同，普通整数流水线 10 级、零新增状态。更广的慢 wake、额外 probe/响应流水级、减少端口和推测 wake 逐项取舍，采用能对应当前实际路径的窄边界与选择前并行方案。本批暂未找到另一个依据充分、值得继续混入的结构变换；并不排除未来新瓶颈下的方案。

源码审查及对实测 EF 的完整 diff：`F:/CPU2026Proofs/EL1_source_review_20261005/`。失败的 EL 准备目录（原锚点格式不匹配）保留，无 manifest、未采用、未测试；EL1 使用原完整地址对齐表达式。当前主工作区仍是实测 EF。最终冻结后先向用户完整汇报，再只对整体测一次课程频率/面积，不分别测 EG/EI/EJ/EK/EL1 中间改动。
