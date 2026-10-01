# RS/ALU指令信息布局优化（2026-10-02）

目标仍为同一最终配置：总面积≤36,000µm²、六项benchmark IPC GEOMEAN≥1.0985、全SRAM频率≥300MHz；完整RV32IM、自然对齐访存、乱序执行与严格顺序提交。Pi冻结。**Tier3尚未达成。**

## 已实际接入的可选实现

`RS_ISSUE_METADATA=0/1`已进入实际RS、ALU、后端、cpu_core和课程student_top；默认0保留原布局，不新增执行拍数、CDB端口或外部访存通道。原有filelist已包含这些模块，无需加入额外存储库或空桩。

| 信息 | 开关0 | 开关1 |
|---|---|---|
| 32-bit立即数、预测taken/target/kind、访存size/unsigned | 按完整ROB容量存储，issue时索引读取 | 每个RS条目携带70-bit原始信息，同原issue选择/唤醒/flush所有权 |
| 分支源PC及预测信息 | 从后端ROB辅助数组读取 | 在原ALU结果接受沿携带67-bit信息，背压/迭代移位时保持 |
| 共享store AGU立即数 | 一个ROB立即数读口 | 与被选完整ROB标签匹配的RS条目，按选择器同样的最低槽优先级读取 |
| CDB store-mask所需访存size | ROB辅助表 | 仍保留，未错误提前释放 |
| ROB提交PC/指令/值、恢复及预测历史metadata | 原路径 | 原路径，严格顺序提交不变 |

所有字段保留原始32-bit值，不依赖缩窄立即数或非ISA输入假设。ALU新增携带状态只在原结果真正接受的边沿更新，保留stale-result取消优先于新issue的边界；不开启时新增输出恒0。RS metadata不参与ready、年龄、分配或出队控制。

在ROB64/RS16/4个ALU的原始存储容量模型中，后端不再需要的六类辅助字段合计100×64=6400位，新增RS信息70×16=1120位和ALU信息67×4=268位，净少5012位。**这是原始容量差，不是综合FF数量、总面积或可直接计分的面积收益**：常量传播、共享逻辑、动态读/写选择及新选择信号负载都须由整机原版流程实际确认。

代价是RS条目更宽、原issue选择增加70-bit负载，以及ALU结果多携带67-bit状态；可能降低某些路径的扇出和MUX层数，也可能增加另一些选择网负载。不能只凭存储位数宣布面积或频率优化成功。

## 已完成的验证

先在`F:/CPU2026Candidates/rs_issue_metadata_20261002`独立候选中实现，避免打断此前共享AGU的当前源码29项回归和PPA冻结。通过后用apply_patch接入主工作树，并核验全部六个改动文件与测试候选SHA逐字节相同。

- 6组初步定向检查全部通过：BE1/2/4×布局0/1，RAT1、预测metadata1、共享地址2与延迟基址场景。`F:/CPU2026Proofs/rs_issue_metadata_smoke_v1_20261002/report.json`。
- 342组协议全部通过：原162组后端矩阵×布局0/1，加18组BE1/2/4×地址0/1/2×布局0/1共享地址定向检查。覆盖checkpoint0/1、RAT0/1、完成0/2、posted store0/1及预测metadata0/1。`F:/CPU2026Proofs/rs_issue_metadata_full_v1_20261002/report.json`。
- 新完整generation标签对照表从实际dispatch捕获PC和70-bit字段，逐项检查issue、分支反馈及保留的恢复分支；不是拿实现内部旧ROB数组作参考。此矩阵主要为lane0刺激，不能替代原生多lane回归。
- ALU原输出与布局关闭版逐周期完全对比：SHIFT_IMPL0/1分别4045次检查（合计8090次），包含最大长度移位、结果背压、完整tag失效与同拍新issue优先级、flush，随后各4000确定性随机周期；接受包分别2549/2265个。`F:/CPU2026Proofs/alu_forward_metadata_v1_20261002/report.json`。这不是整CPU形式证明。

## 当前同源码原生对照与PPA

两套固定四发射、ROB64/PRF64/RS16/LSQ16、RAT1、地址2、Cache控制2、I128/D1024/2way/TAG1、预测1、CPL16、AXI8/4/16/FIFO2，只改变`RS_ISSUE_METADATA`。均使用原官方256MiB/20cycle/FIFO16/B握手退出以及同一C++-Os、Verilator-fno-dfg主机选项：

- 关闭版：`F:/CPU2026Builds/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_20261002rsmeta0`。
- 开启版：`F:/CPU2026Builds/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_rsmeta1_20261002rsmeta1`。
- 开启版PPA目标：`F:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_rsmeta1_standard_20261002rsmeta1`。

两套原生构建和benchmark6/basic5/simulator17/256MiB边界1全部完成。只改变`RS_ISSUE_METADATA 0→1`的机器对照已完成全部29项：硬件/清单/头文件/构建助手/官方driver来源一致且当前SHA核验通过，逐项cycle/instret/退出码完全相同。完整证据：`F:/CPU2026Proofs/rs_issue_metadata_native_exact29_20261002/report.json`；此前11项证据另行保留。这是这29项程序的严格对照，不是整CPU形式证明。

两套当前源码六项计分IPC GEOMEAN均为 **1.1213155347352615**，总周期372783、退休472599；六项周期分别10166/11871/157540/184317/4929/3960。开启版原库/default ABC总面积已经完成elaborate并进入prepare，随后独立当前源码零差异核验和全SRAM STA；**新布局总面积和频率尚无结果**。此前共享AGU版29项及PPA为接入前冻结来源，不能拿旧PPA替代新布局结果。

此前共享AGU/Cache控制0/2的原版PPA均在独立源快照中继续运行，不重启活任务；完成后按冻结来源核验并跑全SRAM时序。`--require-current`因本轮六个RTL文件变化失败时，保留其版本差异，另做不要求当前树的冻结核验，而不是忽略差异宣称当前达标。最终候选仍须三项同配置且当前源码差异0。

为PPA留出提交内存，在确认精确PID/父进程/脚本后显式结束了占约8.9GiB的补充1024行Cache等价证明（当时主机剩余提交容量约6.2GiB）。其四个已完成小配置、源快照和部分日志均保留，1024行案例**未完成、不宣称证明通过**；不是因观察超时重启，也不是CPU反例。正式总面积、六项IPC、全SRAM时序与RV32IM正确性门槛不缩小。
