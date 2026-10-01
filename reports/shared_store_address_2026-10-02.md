# 共享store AGU接入与验证（2026-10-02）

目标仍为同一最终配置：总面积≤36,000µm²、六项benchmark IPC GEOMEAN≥1.0985、全SRAM频率≥300MHz；完整RV32IM、自然对齐访存、真正OoO与严格顺序提交。Pi冻结。**Tier3尚未达成。**

**后续源码边界**：RS/ALU metadata可选布局已接入实际CPU，默认0；342组协议和8090次ALU逐周期检查通过，开关0/1同源码整机对照在构建。本文共享AGU原生29项已全部通过，IPC1.1213155347352615；测试结束时源码差异0，之后成为接入新布局前冻结基线，不能冒称新布局已获该IPC或PPA。见[新布局状态](rs_issue_metadata_2026-10-02.md)。

## 实际接入

| EARLY_STORE_ADDRESS | 提前发布地址时机 | store数据/完成/写授权 |
|---|---|---|
| 0（源码默认） | 原ALU执行 | 原路径 |
| 1 | rename时基址已ready | 原ALU与ROB路径 |
| 2 | 模式1，加上RS中基址后来就绪时的共享AGU | 原ALU与ROB路径 |

模式2已进入实际RS、LSQ、后端、CPU参数检查和两个filelist，不是隔离原型。RS只读输出现有基址有效值及完整标签CDB当拍旁路，不新增操作数存储或CDB。选择器将LSQ中未知地址store与RS完整ROB标签匹配，按LSQ循环年龄选择最老可计算者，使用**一个共享32-bit加法器和一个ROB立即数读口**，每拍最多发布一个地址。

结果只更新完整LSQ generation标签匹配的有效store；load、旧标签、已知地址、已发请求/完成条目不接收。reset/flush/恢复边沿暂停；普通ALU同拍更新有优先级。地址发布补齐访问相对byte/half/word掩码，但不置data-ready、不出队RS、不完成ROB、不授权内存写。不相交load可前进，重叠load仍等真实store数据。

实际Cache数据/标签SRAM、单共享AXI4-Lite32、官方256MiB统一RAM、20cycle/word、FIFO16与MMIO完整word写B握手退出均不变，没有修改原库或面积计分。

## 完成的验证

- 最终当前版本162组后端协议全通过：BE1/2/4、快照/链式/并行RAT恢复、地址模式0/1/2、完成0/2、posted store及预测metadata开关。`F:/CPU2026Proofs/shared_store_address_backend_matrix_v2_20261002/report.json`。更早的162组也通过并保留，最终v2使用追加定向TB、CPU模式2参数检查后的相同RTL。
- 21组集成定向检查全通过：12组LSQ（BE1/2/4×probe0/1×admission0/1）及9组后端（BE1/2/4×地址模式0/1/2）。`F:/CPU2026Proofs/shared_store_address_directed_v4_20261002/report.json`。
- LSQ检查同一行内不相交load放行、重叠load等待与真实数据转发、byte/half/word掩码、无提前写授权、旧generation、普通ALU同拍优先级、恢复暂停/较老保留/较年轻杀除与重新分配标签、load不可被此端口更新。
- 后端用真实延迟load唤醒store基址，独立长DIV提供数据。模式2在原ALU前发布正确地址、放行不相交load；模式0/1没有该提前效果。首次发布保留RS条目，之后允许正常ALU issue，并核对严格顺序提交和最终值。刺激主要为lane0，不能代替原生多lane回归或整机形式证明。

失败证据保留：首次选择器编译用了SV保留字`matches`，修正为`rs_matches`。定向v1对模式0原有分配data-ready语义作了错误假设；v2/v3将正常ALU issue误判为提前地址出队，详细失败是地址0x84正确、commit=0、ALU store有效、RS已出队。v4核对完整标签对应的合法ALU执行边界后通过，没有改CPU来迎合断言。

选择器2000随机输入/几何加任意输入组合SAT已证明1/1、4/4、8/8三种LSQ/RS几何（8/8为143068变量、412249子句，SAT SUCCESS），16/16、32/16仍随原活动任务运行：`F:/CPU2026Proofs/shared_store_address_selector_v2_20261002`。不是整机证明，首轮失败目录保留。

probe关闭时相对接入前真实冻结LSQ的完整原有端口/状态顺序等价在`F:/CPU2026Proofs/shared_store_address_disabled_lsq_equivalence_20261002`运行（BE1/2/4、LSQ8/ROB32/G8）。只排除新增只读/禁用probe端口，probe参数固定0；不宣称启用模式逐周期等价。

## 新原生配置与验收边界

明确候选：四发射、ROB64/PRF64/RS16/LSQ16、RAT1、地址模式2、I128/D1024/2way/TAG1、预测1、CPL16、AXI8/4/16、响应FIFO2、Cache控制分组2。-Os/-fno-dfg原生构建和benchmark6/basic5/simulator17/边界1共29项已全部通过，测试结束时源码差异0。独立原版default ABC、原始五套ASAP7库、全部实际FakeRAM计价与全SRAMSTA链已启动；随后RS/ALU新布局接入使本配置成为冻结基线。

- 完整29项构建：`F:/CPU2026Builds/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_20261002sharedagu_os_nodfg`。
- 活动PPA：`F:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_standard_20261002sharedagu_os_nodfg`。
- 官方驱动仍只增加一行只读退休输出，不改内存/周期计分。完整29项主机使用C++`-Os`、Verilator`-fno-dfg`；另一个-O0构建已有benchmark/basic共11项并完成机器逐项计数相同。硬件与原版Yosys/ABC流程不改。
- **六项benchmark IPC GEOMEAN=1.1213155347352615**，超过1.0985门槛约2.07697%；总周期372783、退休472599，报告为`build/cpu2026/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_benchmark_20261002sharedagu_nodfg.json`。官方256MiB/20cycle/FIFO16/B握手退出，评测结束时当前源码差异0。汇总IPC=1.2677589911557126不是计分使用的GEOMEAN。
- -Os/-fno-dfg的benchmark6/basic5/simulator17/边界1四份`..._20261002sharedagu_os_nodfg.json`均为COMPLETE、共29项全部passed，测试结束时各源码差异0。basic包含半字与完整M扩展smoke，边界为256MiB最后一个合法word；Pi仍未运行。
- -O0/-Os同硬件的11项benchmark/basic机器核对全相同：`F:/CPU2026Proofs/shared_store_address_host_o0_os_exact11_20261002/report.json`。-O0重复链在其simulator qsort中按已完成同硬件完整29项证据显式结束，wrapper记录exit1属于本次主动结束，不是CPU功能失败；保留已完成11项、部分12项simulator输出及全部日志，未启动它的重复PPA。
- **新地址模式总面积与全SRAM频率尚未完成，Tier3仍未达成。** 接入前Cache控制0/2各29项完全一致、IPC1.0881243892617036，是冻结对照，不与新模式拼接PPA。

六项程序对接入前相同窗口、地址模式1/Cache控制2的冻结对照（全部退休数保持不变）：

| 程序 | 地址1周期 | 地址2周期 | 周期减少 | 地址2 IPC |
|---|---:|---:|---:|---:|
| median | 10166 | 10166 | 0% | 0.694668503 |
| multiply | 11871 | 11871 | 0% | 2.328110521 |
| qsort | 161179 | 157540 | 2.25774% | 0.886162245 |
| rsort | 204069 | 184317 | 9.67908% | 1.573191838 |
| towers | 5194 | 4929 | 5.10204% | 0.771556097 |
| vvadd | 3973 | 3960 | 0.32721% | 1.142676768 |

六项GEOMEAN从1.0881243892617036提升约3.05031%，总周期396452→372783。对照跨共享AGU接入前后源码版本，不能称仅-G参数变化的同源码原生对照；模式0/1/2已用当前RTL完成162组协议和21组定向检查，当前源码地址1的完整原生逐项对照仍未重跑。新增共享AGU的比较/选择/加法器及可能延长的组合路径是面积和频率代价，须等整机PPA检验。

较早Cache控制0/2两套大窗口PPA已冻结接入前RTL，本轮后端/CPU/filelist修改使它们不再是当前源码零差异成绩。仍核验其冻结输入、完整计价/时序，保留`--require-current`差异边界，绝不混用不同版本的三项结果。最终选定配置须另获当前源码零差异且三项同时达标证据。此前小窗口43,713.418314µm²/31.170096189MHz和局部Cache夹具515.35MHz均不能替代新整机结果。

## 已确认的主机编译失败与恢复

首轮`20261002sharedagu`的原生`-Os`编译在476个对象之后明确失败：`cc1plus.exe: out of memory allocating 65536 bytes`，目标为6,592,118字节的`Vstudent_top___024root__471.cpp`；不是观察超时或RTL功能失败。失败目录和构建日志保留，不算通过。Windows页文件在D/E增长，各盘可用空间约256MiB；未修改系统页文件、关闭用户程序或删除数据。

因此分文件builder新增显式`ModelOptimization=-Os/-O0`参数（默认仍-Os），在新鲜`_o0`目录用相同完整硬件、-j1重新构建。只降低主机C++优化强度与编译峰值，不缩小ROB/PRF/RS/LSQ，不修改官方20周期内存或IPC计分，不改变原库/default ABC。新增`build_inputs.json`在编译前保存参数、驱动和全部源码哈希，`PREPARED`仅是尝试记录，只有完成并核对哈希后的`build_manifest.json`才可用于成绩。

第二轮`_o0`仍在同一生成函数明确内存不足，失败目录/日志保留，不算完成。实际C++文件显示巨大函数来自DFG对并行RAT组合逻辑的聚合；单降GCC优化不足。[Verilator官方参数文档](https://verilator.org/guide/latest/exe_verilator.html#cmdoption-fno-dfg)说明`-fno-dfg`关闭其DFG组合优化。本地5.051的该选项lint通过，在新鲜`_nodfg`目录执行同硬件构建后，最大C++文件从6,592,118字节降至2,032,400字节，1197个对象已编译完成并链接。新增`DisableDfg`仅为主机选项，默认关闭；全部实参与43个输入哈希记录在完成manifest，当前差异0。六benchmark与五basic已通过，尚须完成simulator17/边界才能宣称全部29项通过；不把生成文件变小当硬件面积优化。

相同完整硬件在新鲜`..._20261002sharedagu_os_nodfg`目录的C++`-Os`、`-fno-dfg`构建已成功，Verilator墙钟671.723s（build648.551s），43个输入与-O0构建相同、官方观察驱动相同，11项机器逐项计数相同，后续全部29项通过。PPA另由独立链使用此完成manifest启动。此前-Os失败是开启DFG的6.59MB函数；不把主机仿真加速算CPU频率或IPC收益。

## 冻结小窗口网表的寄存器面积归属诊断

独立读取此前已完整核验的小窗口RAT1网表、prepared身份和原库计价，得到`F:/CPU2026Diagnostics/rat1_small_frozen_sequential_ownership_20261002sharedagu/sequential_ownership.json`（COMPLETE；网表SHA256 `db974b15403bdb89a6c8bc33bffb495864680965e3388a9db6096c413f9d0e3a`）。所有实际时序单元面积9932.1876µm²；其中D-cache控制状态5498个FF/1603.2168µm²、I-cache3914个FF/1141.3224µm²、后端直属4454个FF/1298.7864µm²、ROB2486个FF/724.9176µm²、AXI桥2262个FF/659.5992µm²。Cache两者合计2744.5392µm²，不含其数据/标签SRAM和相关组合逻辑；不能仅用删除Cache控制寄存器的假设填补该冻结总面积43713.418314相对36000的差距。

这是冻结版本的寄存器归属诊断，不是按模块相加的总面积或当前大窗口PPA；相关组合逻辑、完整新网表关键路径和同配置计分仍须真正映射/STA后检查，不将这些归属数等同于可直接省掉的面积。
