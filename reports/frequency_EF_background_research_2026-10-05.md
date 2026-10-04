# EF 后台测量期间：把 store 加法前移到 PRF 旁路选择之前

EF 已冻结并在 Windows 原生后台做一次 timing-only 测量。这里记录一个新条件方向，尚未创建新 candidate，也没有改 EF 的任何工作区或冻结源。不会据此启动第二个综合。

EA 的慢路径由 PRF 写回物理地址匹配/旁路控制，经选择出来的 32 位值，再走 allocation signed-12 加法器。EF 删去可选分配当拍地址，代价是地址可用时间更晚。可以另存一个保留该功能的方向：在 PRF 旁路控制尚未完成时，并行计算候选数据加 store offset，之后用相同旁路最高槽优先级选择完整地址。

令 `f(x)=x+sign_extend(offset12) mod 2^32`。对一个确定的原选择 `sel`，`f(mux(sel,x0,...,xn)) = mux(sel,f(x0),...,f(xn))`。它并不缩短 CDB 本身；它让地址加法与物理地址匹配/priority 控制重叠，避免完整加法串在旁路数据输出之后。能否提高全局频率仍未知。

具体接口计划是 PRF 加一个默认关闭的组合地址输出，只对每个分配槽的偶数读口实现。复用原 `stored_tree[1]`、`bypass_match`、写回 data 和最高槽优先级，不引入新的物理寄存器匹配，也不绕过 normal ROB valid/generation。输入为该槽的 12 位 decoder offset，候选为旧 PRF 数据与 BE_WIDTH 路原 PRF 写回数据。后端模式只有同时启用 parallel PRF read 和 signed-12 合同时才选新输出；通用/独立配置保留原接口行为。

P0/range 检查继续来自原 `legal` 和原匹配；原 read_ready、同 bundle RAW 清 ready、完整 tag、branch-link 写回最高槽、恢复和 CDB 回压都保留。只能在原 `rs_src1_ready` 下发布分配地址。不能为了提前计算而把任何 write candidate 当成已经有效，也不能在原输出之前保存未经当前 identity 检查的 ready 授权。

旧 PRF 值与每路写回值各一个加法器，当前四分配槽、四写回槽共 `4×(1+4)=20` 个；EA 原来四个，增加 16 个。只读取 EA 已完成的 `report.json/area/module_tree`：五个 `rv32_frequency_add_simm12` 实例各为 14.215500 μm²，其中 direct 13.515660、子树差额 0.699840，无 sequential 或 SRAM。因此按相同旧实例计价，纯新增加法器约 `16×14.2155=227.448 μm²`。EF 相对其已删除分配加法器的实现则需加入完整 20 个，粗估 284.310 μm²。

这些是旧映射规模估算，不能当成新面积。新选择器、查询和数据分发的缓冲、优化合并/裁剪，以及新 slew/load 都可能改变结果。原 EA 总面积 49,279.056294，原 +10% 上限 50,940.662839，余量 1,661.606545 μm²；这个方向从量级上值得做源码备选，不证明新总面积一定在范围内。

若 EF 实测获得明显频率余量，可以先实现该独立备选并比较结构，再考虑一次完整组合测量。它若成功，能够保留分配提前地址的周期，而不是支付 EF 的潜在 store-conflict 延迟。若 EF 新瓶颈已经转移，保留当前结果，不能将这里的局部推导冒充下一轮全局收益。当前没有该方向的 HDL、仿真、综合、STA 或 IPC 结果。

原面积证据：`F:/CPU2026CourseRuns/architecture_EA_20261005/result/synth/opt/report.json`。

冻结 EF：`F:/CPU2026CourseRuns/architecture_EF_20261005`。
