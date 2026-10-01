# 最新四发射配置完整面积审计

**2026-10-02 07:46最新严格边界**：当前RS/ALU布局0/1全部29项通过且机器逐项cycle/instret/退出码相同、当前SHA核验通过，六项IPC均1.1213155347352615；开启版原版完整PPA已进入prepare，尚无新布局面积或频率。接入前地址1/Cache控制0、2冻结大窗口的完整核价与全SRAM时序均完成，分别 **59205.207774µm²/1.0881243892617036/27.09281405439729MHz** 与 **60175.215174µm²/同IPC/15.632394473704297MHz**，均有37实际SRAM、未计价/未展开/遗漏时序边界0，不能配用当前IPC。Yosys层级计数差异已通过逐模块/逐类型/逐实例递归严格核验修正，没有修改网表、库、映射命令或面积系数；详见[完整证据](dcache_control_banks_integration_2026-10-02.md)。Tier3仍未达成，下方运行中为历史时刻。

**最新源码边界**：RS/ALU metadata布局已作为默认关闭选项实际接入，342组协议和8090次ALU检查通过；新同源码开关0/1原生构建及benchmark6/basic5全部完成，11项严格机器对照逐项cycle/instret/退出码相同、当前SHA核验通过，两套六项IPC均为 **1.1213155347352615**。simulator17/边界仍在测，开启版随后执行完整PPA；新布局总面积/全SRAM频率仍无结果，不推算下降或宣布Tier3。共享AGU旧版活动PPA冻结于本次接入之前，不能替代新布局结果。见[新布局报告](rs_issue_metadata_2026-10-02.md)。

**最新后端源码边界**：共享store AGU作为地址模式2已接入，162组后端回归和21组定向检查通过；新大窗口地址2/Cache控制2的benchmark6/basic5通过，计分IPC GEOMEAN **1.1213155347352615**、当前源码差异0。simulator17/边界尚待完成，当前版本总面积/全SRAM频率尚未完成。下方Cache控制0/2审计冻结于接入之前，不与新IPC配用，最终仍需同配置当前源码零差异三项达标；Tier3尚未达成。见[共享store AGU报告](shared_store_address_2026-10-02.md)。

**最新源码边界（2026-10-02控制分组接入）**：D-cache新增默认关闭的模式2，功能状态模块已加入两个CPU清单，180项Cache协议通过。ROB64模式0/2各29项全部通过且逐项周期/退休/退出码相同、IPC1.0881243892617036；四套小Cache控制器/SRAM引脚等价完成、实际1024行仍在运行，两套原版总面积和全SRAMSTA仍在测。下面43,713.418314µm²/31.170096189MHz等均为接入前冻结版本，不是当前工作树零差异或ROB64的PPA。详见[接入报告](dcache_control_banks_integration_2026-10-02.md)，不把夹具或不同窗口结果拼成Tier3成绩。

## 2026-10-02 本轮完成结果

同源码RAT0/1、响应FIFO2、ROB32/PRF48/RS8/LSQ8/early0完整PPA均已恢复并独立VERIFIED、当前输入差异0。RAT0组合26987.011380＋时序9932.187600＋SRAM7825.666854＝**44744.865834µm² / IPC0.9562805856296562 / 全SRAM27.438370846730976MHz**；RAT1组合25955.563860＋相同时序/SRAM＝**43713.418314µm² / 同IPC / 全SRAM31.170096188968706MHz**。37实际宏全部计价/时序、未计价/未展开/遗漏边界0，29项cycle/instret/退出结果逐项相同。并行恢复少1031.447520µm²，仍未达36000/1.0985/300MHz。首轮中间输出明确损坏失败，保留文件后仅恢复失败阶段，不计失败输出或超时重启活任务。

另两套early1/RAT1/PRF64/RS16/LSQ16、ROB32/64的新整机各29项全部通过，六项IPC **1.0324037635213024 / 1.0881243892617036**；没有对应完整面积/频率，不与上面的ROB32/PRF48 PPA配用。仅PRF96的六项IPC **1.0886932595176315**，只增约0.0523%，其29项回归也已全部通过。新只读LSQ诊断每一活动周期与真实eligible逐位一致、六项正式计数完全不变，区分等待返回、load地址未ready及未知更老store地址，不把重叠计数相加为CPI。

真功能缓存状态分组候选尚未列入CPU filelist；10组2000周期状态对照及原版完整夹具流程通过，明确非CPU夹具总面积2673.469864→2943.958024µm²、全夹具SRAM频率154.216867→515.349774MHz。隔离状态顺序证明8组全部PROVEN、包含1024行ways1/2，合计10520个equiv、未证明0；不称整机提频或全Cache等价。完整参数表、SHA、严格配置边界、证据与下一验收步骤见[本轮优化进度](optimization_progress_2026-10-02.md)。以下为历史时刻记录；pi冻结，最终目标保持完整未完成。

## 2026-10-02 01:05：响应FIFO完整PPA、瓶颈实测和新后端选项

上一轮同一冻结源码、只改变`AXI_RESPONSE_FIFO_DEPTH=0/2`的默认ABC完整审计已完成。两套独立Decimal核算`VERIFIED`，核验时工作区输入差异0，全部37个实际SRAM宏计价且纳入STA，未计价/未展开/遗漏存储时序边界0；不包含外部256MiB平台RAM。此后接入RAT/提前store地址选项及文件清单，因此下表是**修改前冻结参考**，不是新后端RTL的当前PPA。

| 响应FIFO深度 | 组合 µm² | 时序 µm² | SRAM µm² | 总面积 µm² | 六项IPC GEOMEAN | 全SRAM估计Fmax MHz |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 26961.190200 | 9831.002400 | 7825.666854 | 44617.859454 | 0.9562805856296562 | 25.370397899013923 |
| 2 | 26786.288520 | 9932.187600 | 7825.666854 | 44544.142974 | 0.9562805856296562 | 28.182193477363423 |

深度2顺序面积增加101.185200，组合减少174.901680，总计减73.716480µm²，估计频率提高11.08298%，29项返回值/周期/退休数逐项相同。最小周期39.416015625→35.4833984375ns，2ns约束slack为-37.415051/-33.483009ns。叶实例373526/371664，网表SHA256分别`d1d27d360afd40b749f659496d5355b83704ef6e17f768a4acff85928d082c48`、`ebe0a9510debf8eb2155ca5ec66958748ed334bd58a57d58a2ee9b9a0ba09296`。证据`D:/CPU2026AreaAudits/axi_response_fifo{0,2}_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001r2`。这是理想时钟/无寄生的综合后估计，不是布局布线成绩，更未达到300MHz。

新模式2最差路径已通过全图net-alias/cell-pin/top-port身份恒等检查，起点`_734688_`为真实FIFO读寄存器`$\\bus.g_response_fifos.data.packets$rdreg[0]$q`，终点`_717455_`为D-cache `mshr_wdata[2][96]`。NOR `_469122_`有2034输入pin负载，延迟10.8026ns，后级NAND因坏输入边沿延迟8.2909ns；首个下游顺序边界2843个，主要为1020个dirty位、513个valid位以及多个MSHR写数据/受害行字段。另一个上游NOR有930负载、5.2329ns延迟。它不是RAT恢复路径；控制隔离后瓶颈仍在D-cache返回/请求仲裁和元数据/MSHR更新。依赖图不证明每条路径逻辑敏化，未设false path或改库。诊断`D:/CPU2026Diagnostics/axi_response_fifo2_timing_20261002`。

性能容量对照均已完成原20cycle共享AXI下29项整机回归：

| ROB/PRF/RS/LSQ | 六项IPC GEOMEAN | 相对上一行变化 |
|---|---:|---:|
| 32/48/8/8 | 0.9562805856296562 | 基线 |
| 32/48/8/16 | 0.9609030920251813 | +0.48338% |
| 32/64/8/16 | 0.9609202386848219 | +0.00178% |
| 32/48/16/16 | 0.9682381863757763 | 对32/48/8/16仅RS增大，+0.76335% |

表末不是对前一行的单参数对照。大窗口实验尚无对应面积/频率，不能拼接上面的PPA。只看队列满计数会误判：RS16/LSQ16下vvadd的LSQ满和RS满都为0，ROB满却4254/6159周期，而周期只比基线少36。

`tools/observe_course_memory_flow.py`复用已编译模型，只在原驱动低沿eval之后、memory.step/高沿之前读取信号，六项cycle/instret/返回值与各自官方报告完全一致。基线vvadd 6195周期中，Cache入口背压90周期（1.45%），LSQ非空无候选4451周期（71.85%）；RS16/LSQ16下为90/4414周期。rsort有36014入口背压周期，其中23220周期同时存在未完成tag查询；qsort多数入口背压伴随data写端口。分类重叠，不能相加作CPI归因。证据`D:/CPU2026Diagnostics/axi_response_fifo2_memory_flow_v2_20261002`及`axi_response_fifo2_rs16_memory_flow_20261002`。第一轮诊断仅因把reset五拍误加到官方cycle而未完成，修正计数断言后在新v2目录重跑；官方驱动本来就不计reset周期，未改计分。预测器count/correct数实际是被接受的**解析反馈**，不是退休分支全集；下文历史“提交预测正确率”的表述不采用。

当前RTL新增默认0的`RAT_RECOVERY_IMPL`和`EARLY_STORE_ADDRESS`。前者将已证明的并行最老被杀写者选择接入实际ROB/RAT端口，保留分支自身目的映射，CHECKPOINT_IMPL0仍走快照。原八组字面后端组合证明完成；将SV保留字`matches`改为局部`writer_matches`后，当前模块与原已证明快照的八组结构/组合等价又完成（29771个equiv，未证明0）。这不是CPU接线或整机顺序证明。

提前store地址仅在rename基址已ready时登记`base+imm`，同bundle依赖基址保持未ready；store数据直到原ALU执行更新才声明ready，避免错误转发占位数据。不提前完成store、不改变ROB顺序或MMIO B握手。基址未ready仍等待原AGU，不冒称已实现完整地址/数据拆分。新源码RAT0/1、early0的29项cycle/instret/返回值与彼此、旧基线完全相同；early1的29项也全通过，六项IPC为**0.981536642367891（+2.64107%）**，vvadd6195→5482周期（IPC提升13.0062%）。108组后端协议矩阵通过，含BE1/2/4、快照/链式恢复、RAT/early开关、完成0/2、posted store和预测metadata；单元刺激按lane0，实际多lane另由整机测试覆盖。额外长DIV数据/同址与异址load/byte-half/未ready基址/同bundle依赖/被杀store程序三套均返回0（284/284/279周期，53退休），不计入六项成绩。

新RAT0/1同源码完整原版PPA正在`D:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r32p48rs8{,_rat1}_standard_20261002rat`运行；未报RAT面积/提频收益。ROB32/64、PRF64/RS16/LSQ16、RAT1/early1的同源码性能对照另已启动，不先报结果。证明`D:/CPU2026Proofs/{rat_recovery_sv_alias,recovery_store_address_protocol}_20261002`；原字面证明`build/rat_parallel_recovery_literal_20261001/report.json`。三项目标仍为同一最终配置36000µm²/1.0985/300MHz，尚未达到；pi冻结。以下“运行中/当前源码”是对应时刻历史记录。

## 2026-10-01 23:55：完整缓存对照与 AXI 响应时序隔离

上一轮缓存静态更新的两套整机审计已完成，独立 Decimal 核算核对实际叶实例、原始库、冻结源码和仿真可执行文件。以下是新增 AXI 选项之前的冻结成绩，不能混用为新响应 FIFO 的面积或频率：

| DCACHE_STATIC_UPDATES | 组合 µm² | 时序 µm² | 实际 SRAM µm² | 合计 µm² | 六项 IPC GEOMEAN | 全 SRAM Fmax MHz |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 26780.106600 | 9830.710800 | 7825.666854 | 44436.484254 | 0.9562805856296562 | 24.0127567770378 |
| 1 | 26320.909500 | 9831.002400 | 7825.666854 | 43977.578754 | 0.9562805856296562 | 22.78999376836108 |

叶实例370228/364670，实际宏均37个，未计价/未展开/遗漏时序存储边界0。核验时各冻结输入与工作区差异0；此后桥/top两处RTL已改变，因此现在本表仅作冻结参考。静态更新面积减458.905500µm²（1.0327%），频率降5.0921%，IPC不变，仍默认关闭。两套29项整机返回值、cycle、instret逐项相同。缓存88项协议、五组控制器及全部实际SRAM端口顺序等价、六组ROB控制分组顺序等价均已完成；不是整机或SRAM储体内部实现证明。

目录 `D:/CPU2026AreaAudits/dcache_static_updates{0,1}_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001`。网表 SHA256 分别 `f7f2abb9bcef9b30b201a37d256887865a6b22458c79ca9af169932fa2ab11a1`、`4da1412d3122a2b0814b25c6f98f97338bbc5c971428eb52656aaefdaf876444`。

最新模式0最差路径通过全部net-alias/cell-pin/top-port指纹恒等核对后，起点为ROB `head_o[0]`，终点为 `bus.d_resp_addr[0]`。两组OAI/NAND四级延迟合计29.3634ns，约占41.5745ns数据到达时间70.6%；NAND负载738/671，起点FF负载1116。最终NAND首个下游状态为345个AXI响应/相关FF，非RAT恢复数据。证据 `build/dcache_static_updates0_timing_identity_20261001/{identity,sequential_ownership}.json`、`cone391481/control_cone.json`；物理依赖不等于每条路径都逻辑敏化，未设false path或改库。

新增默认0的 `AXI_RESPONSE_FIFO_DEPTH`，传入桥 `RESPONSE_FIFO_DEPTH`。0保留旧单响应寄存器同拍替换；非零合法2次幂启用I/D各一真实169-bit响应FIFO，只用寄存器count决定接收信用，不组合依赖消费者ready、不做fall-through。非满支持同拍push/pop；满队列需下一拍释放信用；空队列首响应无额外流水拍。它是响应流水队列，不以FF替代缓存SRAM或外部RAM。单一32-bit AXI、官方20cycle/word、AW/W/B配对和MMIO B握手退出不变。

新深度0/2两套四发射ROB32/PRF48/RS8/LSQ8/I128/D1024/TAG1/预测1/CPL16/AXI8/4/16，benchmark6/basic5/simulator17/边界1全部通过。29项返回值、cycle、instret逐项机器相同，源差异0，IPC仍0.9562805856296562，pi冻结。15组169-bit FIFO/完整AXI协议通过，含2/4/8深度、3000步、满空/并发/背压/带未完成响应复位/阻塞I时D前进/错误/掩码/MMIO。深度0桥对本表实际冻结原桥在2/2/4、8/4/16、16/8/64三种几何的完整顺序等价PROVEN（1516/3082/5758个equiv，未证明0）。深度2/4/8结构检查：接收信用初级输入只有reset并止于真实FF，payload无初级输入并止于真实FF；不称其为新旧FIFO逐周期等价。

新完整原版opt/default ABC和全SRAM PPA正在测量：`D:/CPU2026AreaAudits/axi_response_fifo{0,2}_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001r2`。未完成前不沿用本表、不宣称提频。测试 `build/cpu2026/axi_response_fifo{0,2}_branch1_bus8w4q16_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001r2.json`；协议 `build/axi_response_fifo_protocol_20261001/report.json`；证明/结构检查 `D:/CPU2026Proofs/axi_response_fifo_legacy_20261001/report.json`。

仅结束时读取原RTL计数器、复用新模式2已编译模型的诊断已完成，逐程序核对官方cycle/instret/返回值完全不变。LSQ满周期比例median21.37%、rsort22.47%、towers34.93%、vvadd70.54%，对应ROB满比例0.46%/15.23%/0%/0.61%；qsort提交预测正确率77.55%、median81.54%。类别重叠，不能加总为CPI分解。证据 `build/axi_response_fifo2_perf_20261001/perf_observation.json`。仅LSQ8→16的同源码性能敏感度实验已启动，尚未报收益。RAT并行恢复仍未接入CPU。最终目标保持同配置36,000µm²/IPC1.0985/300MHz，尚未完成。

## 2026-10-01 19:00：D-cache静态更新实验的新源码边界

根据下文18:31实际关键路径归属，当前工作区新增默认关闭的`DCACHE_STATIC_UPDATES=0/1`，由课程top传递至cache的`STATIC_UPDATES`。开启时，保留原时钟沿、请求/返回仲裁、缓存容量/相联度/真实SRAM及MSHR/预取语义，只把valid/dirty元数据、LRU及MSHR写数据的动态写选择改为静态行/字节写使能。元数据以16行分组+低位one-hot解码，保留**不同地址限定的真实逻辑函数**边界，不复制导线别名、不声明标准单元或SRAM空桩。MSHR写按字节使能，保持store覆盖、预取/需求优先级，以及refill>local fill>prefetch/miss>store-hit的原非阻塞写优先级；dirty原无复位行为不改变。

88组新旧开关协议矩阵已COMPLETE/PASS（24组SRAM协议＋64组哈希/预取），涵盖TAG0/1、ways1/2、16/64行、hash0/1、prefetch0/1、合并窗口0/16/32及官方四态SRAM的byte/half、warm reset、背压、flush、脏行写回/等待者复用等。证据 `build/dcache_static_updates_protocol_v2_20261001/report.json`。第一轮全部88例已通过，但汇总脚本误将计划数写成152而退出失败；修正计数后在新冻结目录重跑88例全部通过，不将第一轮报为COMPLETE，也未改RTL以迎合测试。

同一新源码、显式四发射ROB32/PRF48/RS8/LSQ8/I128/D1024/TAG1/预测1/CPL16/AXI8/4/16/ROB分组0的新对照已启动。两套六项benchmark和五项basic通过，逐项打印cycle/instret/返回值相同，六项IPC **0.9562805856296562**；simulator17/边界、完整原版面积和全SRAM STA尚在运行。不能据此断言面积或频率提升。Pi冻结。下面44,293.585674/25.437201907790143MHz属于增加这一选项之前的冻结版本，与当前RTL有cache/cpu_core/student_top三处源码差异；不能再称当前源码零差异面积。

构建 `D:/CPU2026Builds/dcache_static_updates{0,1}_branch1_bus8w4q16_i128_r32p48rs8_20261001`；PPA `D:/CPU2026AreaAudits/dcache_static_updates{0,1}_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001`。新顺序证明仅在证明设计中暴露真实SRAM的所有输入pin并比较，同时将对应rdata设为共有自由输入，证明控制状态和全部访问端口一致；原官方存储体另由四态回归覆盖，未修改CPU综合/面积流程、不声明储体空桩，不把此证明称为SRAM内部实现证明。小几何证明正在运行，尚无最终完整证明报告。三项Tier3保持未完成。

## 2026-10-01 18:19：当前源码两组完整整机 PPA 已完成

**当前合规基线总面积为 44,293.585674 µm²**。同一源码显式覆盖四发射ROB32/PRF48/RS8/LSQ8、I128/2way、D1024/2way/hash1/TAG1、条件预测模式1、FIFO完成0/深度16、AXI8/4/16；`ASAP7_FANOUT_BUFFERS=0`，新`ROB_CONTROL_REGISTER_BANKS`分别为0/1。不是无参数覆盖的源码默认配置。两组均使用原官方SRAM检查、原始ASAP7 r28 RVT TT五库、完整展开及默认ABC，无非法空桩或改库。

| 同一源码整机对照 | 分组0（保留） | 分组1（不选用） |
|---|---:|---:|
| 组合标准单元 µm² | 26,636.624820 | 27,093.153780 |
| 时序标准单元 µm² | 9,831.294000 | 9,996.631200 |
| 标准单元逻辑小计 µm² | 36,467.918820 | 37,089.784980 |
| 全部实际片上SRAM µm² | 7,825.666854 | 7,825.666854 |
| **完整总面积 µm²** | **44,293.585674** | **44,915.451834** |
| 六项benchmark IPC GEOMEAN | 0.9562805856296562 | 0.9562805856296562 |
| 全SRAM估计Fmax MHz | 25.437201907790143 | 21.658664523361324 |
| 最小周期 ns | 39.3125 | 46.1708984375 |
| 2ns约束最差setup slack ns | -37.312469 | -44.169952 |
| 实际计价叶实例 / SRAM宏 | 368,489 / 37 | 373,555 / 37 |

两组独立Decimal计价均`VERIFIED`，各54个冻结输入与当前工作区差异0，未计价叶实例/未展开存储/遗漏存储时序边界均0，最终映射网表重读check通过。仅排除外部256MiB平台RAM；PRF、ROB、RS和预测器等普通RTL数组完全计入标准单元。37个实际SRAM仍为1×128×128指令数据687.970714、32×512×8数据数据5503.765696、4×512×19标签1633.930444，合计7825.666854 µm²，实际bank、mask分块和副本均计入。

两套独立新构建的benchmark6/6、basic5/5、simulator17/17、256MiB边界1/1全部通过。18:19再次机器比对全部29项，逐项名称/状态/期望值/返回值/周期/退休数完全一致；六项总周期428220、退休472599，计分使用GEOMEAN 0.9562805856296562，而非aggregate 1.103635981504834。pi冻结。36组ROB/后端协议矩阵通过；新分组0/1的六组完整顺序等价仍在证明，不将仿真全通过冒称完整形式证明已完成。

结论：真实整机分组1增加 **621.866160 µm²**，其中567个额外FF增加165.337200、组合增加456.528960，IPC不变且估计频率下降；独立夹具收益没有传播成整机收益，**默认分组0继续保留**。分组0相对16:25旧源码快照44,490.415674减少196.830000 µm²，但这是关闭新选项时RTL改写/映射后的结果，不是启用分组的收益。当前面积仍超36,000目标8293.585674 µm²，IPC低于1.0985、频率低于300MHz，最终目标未完成。

两组PPA目录 `D:/CPU2026AreaAudits/rob_register_banks{0,1}_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001`；构建 `D:/CPU2026Builds/rob_register_banks{0,1}_branch1_bus8w4q16_i128_r32p48rs8_20261001`；四套报告 `build/cpu2026/rob_register_banks{0,1}_branch1_bus8w4q16_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001.json`。分组0面积/时序共同网表SHA256 `233134fdc11009a1402e41b8a97083b645c466accd9bb7b6d91058d40df717a5`，分组1为`9d0486b54285af0d296409f6451e5912a4fdb80c2bdb037862b08d30645bfb55`。OpenSTA3.1、原始ns/fF约束、理想时钟/无寄生，**频率是综合后估计，不是布局布线实测**。

本节覆盖下文“运行中”和“当前源码”的历史状态。新的STA仍显示组合控制门高扇出（基线关键NOR输出2312个输入pin，分组1关键NOR输出2756个），正在通过完整物理连接核对打印名与原始寄存器身份，不凭源码猜测归属，也不将夹具频率当作CPU成绩。

### 18:31：当前基线关键路径归属已核实

`tools/audit_timing_identity.py` 从完整冻结`design.json`重新导出普通名和原始名，并将原评分网表与重新导出的网表分别按真实库读回；对**全电路**命名net别名等价类、每个物理cell的每个pin和顶层端口做指纹比较，物理连接完全一致，368489个叶实例一一匹配。STA打印名不能按编号猜测原始FF身份。本轮重新导出不改变评分网表或成绩，诊断目录 `build/rob_control_banks0_timing_identity_20261001`。

打印起点`_729277_`对应真实FF`$auto$ff.cc:337:slice$670680`，通过prepared同名FF及真实输出反相器追踪，实际寄存器是 **`core.g_cached_memory.memory_bridge.d_local_error`**；终点`_709414_`对应`$auto$ff.cc:337:slice$575967`，实际为 **`core.g_cached_memory.g_nonblocking_dcache.dcache.mshr_wdata[3][0]`**。因此，**本条整机最差路径不是猜测的RAT恢复路径**。FF归属统计只统计实际计价FF，不冒称模块总面积。

关键NOR`_466295_`输出实际2312个输入pin负载，电容1034.5548fF、slew20.1374ns、该级延迟15.7720ns；其后NAND`_481493_`仅31个负载却因坏输入边沿又耗时7.9370ns。两级约23.709ns，约占39.2444ns数据到达时间的60.4%。起点FF本身只有73个pin负载，而不是此前head最大1152扇出路径。没有删掉这条路径、置为false path或改变库/约束。

进一步从这一实际NOR遍历组合连接直到第一个顺序边界，2758个下游FF全部位于D-cache，主要包含1024个dirty位、693个valid位、四组各128位的MSHR写数据及其它MSHR字段。上游边界主要为当前valid/dirty/LRU、标签同步查询保持值和内存返回/错误状态；这些是物理依赖，不表示每个依赖对每种输入都被敏化。证据 `identity.json`、`sequential_ownership.json`、`control_cone.json` 及原`timing.rpt`，分析工具 `tools/audit_control_cone.py`。下一优先方向据此转向 **D-cache返回/请求仲裁与元数据/MSHR更新之间的宽组合控制扇出**；尚未做新RTL改动或宣称优化收益。RAT恢复结构另有面积优化潜力，但不能拿它解释本条已核实的最差时序路径。

## 2026-10-01 17:33：新纯 RTL 控制寄存器分组的源码边界

当前工作区新增 `ROB_CONTROL_REGISTER_BANKS=0/1`，默认0。开启时，将ROB当前head的下一状态在**原来的同一时钟沿**分别写入5组内部head副本、6组后端控制域副本，以及BE×4组当前head的one-hot读选择寄存器；每个提交lane/约50-bit packet分组具有独立的真实控制FF。恢复时head保持，背压与提交前缀计数不变，不额外增加流水拍。使用普通RTL和保留顺序单元的`keep`属性，不声明新标准单元空桩、不修改官方框架或原库，所有新增FF应按实际映射计价。

此修改之后，下面16:25的 **44,490.415674 µm² / IPC0.9562805856296562 / 25.320837763655696 MHz** 属于修改前冻结版本，不再是当前源码零差异成绩。当前同一源码的开关0/1完整对照已经启动，不能把夹具频率或旧面积当作新结果。真实AXI/20cycle下，两套新构建已完成六项benchmark与五项basic，逐项周期/退休/返回值相同，六项IPC均为 **0.9562805856296562**；simulator17项及256 MiB边界尚在运行，pi冻结。36组ROB/后端协议矩阵全部通过，范围BE1/2/4、ROB8/32、FIFO/直接完成0/2、posted store0/1、预测metadata0/1；完整顺序等价仍在证明BE4/ROB32，不冒称已完成全部六组。

### 官方完整流程夹具：纯 RTL 方案通过，两种显式单元方案拒绝

`tools/test_fanout_course_flow.py` 在导入Liberty之前调用**原始**`prepare_memories`，包含真实16×32/8bit掩码SRAM、4个实际16×8宏；随后使用原始五库、默认ABC、完整网表重读check与独立Decimal计价。所有输入先复制并核验到`source_snapshot`。原空桩方案在RAM检查被拒绝；非空whitebox功能描述虽通过RAM检查，但原`read_liberty`因同名标准单元重定义而失败，均未改动官方命令或检查，也未用作CPU成绩。负例证据分别为 `build/fanout_course_blackbox_negative_20261001/report.json`、`build/fanout_course_whitebox_rejected_20261001/failure.json`。

纯RTL分组夹具 `build/registered_fanout_course_v3_20261001/report.json` 两组均完成原版SRAM检查/映射/计价/完整SRAM时序、1000随机周期功能一致。实际物理DFF数1025→1040，最大真实控制FF输出扇出2049→129；没有仅保留导线别名而合并控制FF。总面积 **515.075824→520.105924 µm²**（+5.030100），估计频率 **238.6390118853414→2255.506607929515 MHz**，最小周期4.1904296875→0.443359375 ns。这是明确标记`not_a_cpu_result=true`的夹具，**不证明CPU达到300MHz或Tier3**。扇出按真实DFF输出计数，解析保留的正相Q别名经过原库INV返回DFFHQN的真实反相输出，避免把闲置别名的0扇出误报为物理FF扇出；v2的旧`maximum_control_q_fanout`字段不采用。

当前原版完整CPU流程：构建 `D:/CPU2026Builds/rob_register_banks{0,1}_branch1_bus8w4q16_i128_r32p48rs8_20261001`；完整PPA目录 `D:/CPU2026AreaAudits/rob_register_banks{0,1}_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001`。矩阵证据 `build/rob_control_banks_protocol_20261001/report.json`，顺序证明冻结目录 `build/rob_control_banks_equivalence_20261001`。三项最终Tier3要求仍未达到，目标保持未完成。

## 2026-10-01 16:25：最新工作区合规配置完整面积已核验

**整机总面积 44,490.415674 µm²**。对应当前工作区、显式参数覆盖的四发射 ROB32/PRF48/RS8/LSQ8，I-cache 2 KiB/2way、D-cache 16 KiB/2way/hash1，TAG_SRAM1、条件分支模式1、FIFO完成0/深度16、AXI队列8/4/16，`ASAP7_FANOUT_BUFFERS=0`。不是无参数覆盖的源码默认配置，也不是开启显式物理缓冲树的实验配置。

| 当前同一配置组成 | 独立 Decimal 面积 µm² |
|---|---:|
| 组合标准单元 | 26,833.454820 |
| 时序标准单元 | 9,831.294000 |
| 标准单元逻辑小计 | 36,664.748820 |
| 全部实际片上 SRAM | 7,825.666854 |
| **整机总面积** | **44,490.415674** |

原始 ASAP7 r28 RVT TT 五库、全局展开/默认 ABC，370,554 个实际计价叶实例；未计价叶实例0、未展开存储0，最终网表重读 check0。独立 `tools/verify_course_axi_area.py --require-current` **VERIFIED**，53 个冻结输入与当前工作区差异0。构建、可执行文件、原观察驱动、RTL/头文件、官方流程/原库、最终统计和网表均核验。按最终实际叶实例数量乘原始 Liberty `area`，用 Decimal 独立累加；包括实际 AXI 适配器、PRF/ROB/RS/预测器等普通 RTL 数组，只排除外部256 MiB平台RAM。没有将逻辑黑盒当作零面积。

37 个实际 SRAM 宏直接从展开后的设计确认：1×128×128 指令数据 **687.970714**，32×512×8 数据缓存数据 **5,503.765696**，4×512×19 标签 **1,633.930444**，合计 **7,825.666854 µm²**。官方系数 `0.0419904 µm²/bit`、逐物理宏保留6位小数；字节写掩码分块、两路bank和标签读副本均按实际实例计入。

同一构建的正式六项 benchmark IPC GEOMEAN **0.9562805856296562**，周期428220/退休472599；benchmark6/6、basic5/5、simulator17/17、256 MiB边界1/1通过，pi冻结。同一最终网表全 SRAM STA 已完成：最小周期 **39.4931640625 ns**，估计 Fmax **25.320837763655696 MHz**，全部37宏参与、遗漏存储边界0，2 ns目标 setup slack **-37.492420 ns**。OpenSTA3.1、原版ns/fF约束、理想时钟/无寄生，是综合后估计，不是布局布线实测或500 MHz成绩。

与此前相同资源/模式1/小AXI配置44,508.844794相比，只减少 **18.429120 µm²（0.0414055%）**，IPC逐项不变，频率从26.01890436019921降至25.320837763655696 MHz；不能宣称整机提频成功。当前面积超36,000目标 **8,490.415674 µm²**，IPC与频率也未达到1.0985/300 MHz，最终目标未完成。本节覆盖下面各历史章节的“当前源码零差异”边界；更早PPA仍只属于各自冻结版本。

证据目录 `D:/CPU2026AreaAudits/asap7_fanout0_branch1_bus8w4q16_i128_r32p48rs8_standard_20261001`，同一面积/时序网表 SHA256 `1ffdf190e081e1cdb042f30ba1d42310c56ef3469fd080e9850c9781d1ba2c25`；构建 `D:/CPU2026Builds/asap7_fanout0_branch1_bus8w4q16_i128_r32p48rs8_20261001`。关键文件为 `area_audit.json`、`independent_verification.json`、`run_manifest.json`、`map.done.json`、`stat.json`、`mapped.v`、`full_timing_audit.json` 和 `timing.rpt`。

### 显式缓冲树实验不构成有效整机面积成绩

`ASAP7_FANOUT_BUFFERS=1` 的原官方 `scripts/fakeram.py:prepare_memories` 在展开后拒绝 `BUFx16f_ASAP7_75t_R` 空桩，报 `unsupported external module ...; only sram_fakeram has a RAM library implementation`；因此该配置没有完整官方面积或整机频率结果。没有绕过/修改官方检查，也没有把这些节点按零面积处理；源码默认开关仍0。本节总面积明确来自合法的开关0配置。

独立1024路高扇出夹具确实用原库计入17个缓冲单元，总面积493.081020→494.611920 µm²、估计频率238.861675→2884.507042 MHz，但它直接读取Liberty、**未经过官方 `prepare_memories` 检查，不是CPU成绩**，不能代替整机的44,490.415674/25.320838。夹具报告 `D:/CPU2026Tests/asap7_fanout_verified_20261001/report.json` 明确标记 `not_a_cpu_result=true`。整机开关0/1仿真的四套回归均完成，逐项返回值/周期/退休数机器比对完全相同；这些证明功能一致，不证明该开关1符合综合评测规则。36组ROB/后端协议测试通过。16:33确认完整ROB顺序等价六组全部PROVEN，共58,782个等价节点、未证明0，采用原库真实buffer函数，范围为BE1/2/4×ROB8/32、PHYS48/GEN8/CHECKPOINT_IMPL1/STORE_BUFFERED_RETIRE1；冻结证据 `D:/CPU2026Proofs/asap7_fanout_20261001/report.json`。这是开关0/1的功能等价证明，不是官方综合合法性证明，也不是更早60组ROB/三组LSQ广泛证明的完成记录。

另外已完成 D-cache缩至512/256行且完成FIFO深度16→4的联合实验，两组各6/5/17/边界通过，但六项IPC分别 **0.8208912588940499 / 0.7705675281357258**，明显低于基线；两项参数同时改变，不能拆成单参数收益。这两组使用开关1，未得到合规完整面积，不从容量公式推算整机面积，也不作为最终优胜配置。

## 2026-10-01 10:48：最新源码6位历史预测器完整面积已完成

工作树 `PREDICTOR_DIRECT_BRANCH_TARGET=2 / PREDICTOR_HISTORY_BITS=6`，查询索引随指令保存、投机历史恢复及完整代际反馈过滤；严格IPC **0.9460486608833834**，6/5/17/边界通过、pi冻结。最新源码/显式-G四发射ROB32/PRF48/RS8/LSQ8、I-cache2KiB/2way、D-cache16KiB/2way/hash1、TAG_SRAM1、FIFO完成0、store同拍接收0、D请求寄存级0、AXI16/8/64的完整默认ABC已经完成；这是实验候选，不是无参数覆盖的源码默认配置。

| 同一最新配置组成 | 独立Decimal面积 µm² |
|---|---:|
| 组合标准单元 | 27,934.536420 |
| 时序标准单元 | 10,758.873600 |
| 全部实际片上SRAM | 7,825.666854 |
| **整机总面积** | **46,519.076874** |

逻辑小计 **38,693.410020 µm²**。实际计价389542个叶实例、37个真实SRAM宏，未计价叶实例/未展开存储0、最终网表重读check0。`tools/verify_course_axi_area.py --require-current` **VERIFIED，当前输入差异0**：52个冻结输入、构建/原驱动/可执行文件、原始ASAP7 r28 RVT TT五库、脚本、统计与最终网表均核验；按实际最终叶实例数量乘未经改写的原库area，用Decimal独立累加。包括真实AXI适配器与所有普通RTL寄存器数组；只排除外部256MiB平台RAM。

SRAM明细：1×128×128指令数据687.970714＋32×512×8数据缓存数据5503.765696＋4×512×19两份标签阵列1633.930444＝7825.666854 µm²；写mask分块和实际副本均已计入。相比此前同核心资源模式1/大AXI快照45,918.264234，增加 **600.812640 µm²**，不是新的面积压缩。面积超Tier3上限 **10,519.076874 µm²**，IPC也未达1.0985。

证据 `D:/CPU2026AreaAudits/indexed_history6_fifo_tagbanks_i128_r32p48rs8_standard_20261001`，共同最终网表SHA `cfa551ee56f699ac65553e42134c1822ae01467e3b7c6b49c304986a361eec7f`，构建 `D:/CPU2026Builds/indexed_history6_fifo_tagbanks_i128_r32p48rs8_20261001`。同网表全SRAM STA已完成：最小周期 **39.1201171875 ns**、估计Fmax **25.562295613969397 MHz**，全部37宏参与/遗漏存储边界0，2ns目标setup slack **-37.119282 ns**；OpenSTA3.1/原始ns-fF约束/理想时钟/无寄生，是综合后估计，不是布局布线实测。完整配对 **46,519.076874 µm² / IPC0.9460486608833834 / 25.562295613969397 MHz**，三项均未达到Tier3。2ns综合目标不是500MHz实测成绩。下面数字属于各自历史快照，不能冒称本轮最新源码面积。

最新完成的较早模式1/小AXI8/4/16快照已独立VERIFIED并完成同网表全SRAM STA：组合 **26,851.883940**＋时序 **9,831.294000**＋SRAM **7,825.666854**＝**44,508.844794 µm²**；370772计价叶实例/37宏，未计价/未展开0。同构建IPC **0.9562805856296562**，Fmax **26.01890436019921 MHz**（38.43359375 ns，2 ns目标slack -36.433144 ns，原版约束、理想时钟/无寄生）。证据 `D:/CPU2026AreaAudits/direct_branch_bus8w4q16_fifo_tagbanks_i128_r32p48rs8_standard_20261001`，网表SHA `e99a4cce0d6b982e2d6cd12a359d6d9b7a835a0e5b4086d6a924dde1ba412b50`。与当前工作树6个RTL文件不同，不是新模式2面积/频率。

同模式1大AXI16/8/64相比，小队列总面积减少 **1,409.419440 µm²**，但联合改变三项参数，不能拆成单参数收益；面积仍超36,000 **8,508.844794 µm²**。两版本均未达Tier3。预测计数术语另已更正：来自ALU接受的解析反馈，不是退休分支准确率，见 `reports/indexed_history_predictor_2026-10-01.md`。

## 2026-10-01 09:43：当前源码新预测器/FIFO候选面积完成

同一网表完整STA随后已完成：**21.745593544277 MHz**，最小周期45.986328125 ns，全部37个SRAM宏参与、遗漏存储边界0，2 ns目标slack -43.986233 ns。完整配对 **45,918.264234 µm² / IPC0.9567514009772996 / 21.745593544277 MHz**，仍未达Tier3。理想时钟/无寄生综合后估计，不是布局布线实测。以下“STA运行中”是完成之前状态，由本段覆盖。

**当前源码零差异独立核验**：`direct_branch_fifo_tagbanks_i128_r32p48rs8_20261001`，四发射ROB32/PRF48/RS8/LSQ8、I-cache2KiB/2way、D-cache16KiB/2way/hash1、TAG_SRAM1；PREDICTOR_DIRECT_BRANCH_TARGET1、COMPLETION_BYPASS0、LSQ_STORE_ADMISSION_BYPASS0、DCACHE_REQUEST_PIPELINE0，AXI READ_LINES16/WRITE_LINES8/WORD_QUEUE64。这是显式-G候选，不是无覆盖默认配置。

| 当前同一冻结候选组成 | 独立Decimal面积 µm² |
|---|---:|
| 组合标准单元 | 27,506.059380 |
| 时序标准单元 | 10,586.538000 |
| 全部实际片上SRAM | 7,825.666854 |
| **整机总面积** | **45,918.264234** |

标准单元逻辑小计38,092.597380，实际计价381,567个叶实例、37个真实SRAM宏，未计价/未展开0、最终网表重读check0。原始ASAP7 r28 RVT TT/全局默认ABC，`tools/verify_course_axi_area.py --require-current` VERIFIED，changed_current_inputs为空；仿真构建/可执行文件/原驱动/RTL与头文件/原库/映射脚本/最终网表与统计均指纹核验。所有普通RTL数组作为标准单元计入，仅外部256MiB平台RAM不计入。

同一构建IPC GEOMEAN **0.9567514009772996**、总周期428125/退休472599，6/5/17/边界全部通过，pi冻结。与上一FIFO/旧预测器45,793.940574/0.9558133327368818相比，**面积增加124.323660 µm²**，IPC仅提高0.0981434563%；不宣称新的面积优化。面积仍超Tier3上限 **9,918.264234 µm²**，且IPC低于1.0985。全部SRAM参与的同一网表STA正在运行，未完成前不借用旧频率。

共同网表SHA `3c06b92b4503b67241796a2d53ca95fdd42109eaf188fa7a554c08b0dd383e1b`，证据 `D:/CPU2026AreaAudits/direct_branch_fifo_tagbanks_i128_r32p48rs8_standard_20261001`。进一步小AXI队列8/4/16候选已6/5/17/边界通过、IPC0.9562805856296562，其面积另在direct_branch_bus8w4q16目录运行，不把本表当作小队列的面积。下面模式2与旧FIFO数字保留为各自冻结版本。

## 2026-10-01 09:12：直接完成模式2完整面积完成

该同一完整网表STA随后完成：**22.538683335901 MHz**，最小周期44.3681640625 ns，全部37个SRAM宏参与/遗漏边界0，2 ns目标slack -42.368080 ns。完整配对为 **43,883.319054 µm² / IPC0.946078833733971 / 22.538683335901 MHz**，非当前后续预测器源码PPA，三项Tier3均未达标。下段“频率运行中”为完成之前记录，以本段为准。

冻结构建 `direct_cdb_precise_tagbanks_i128_r32p48rs8_20261001`，四发射ROB32/PRF48/RS8/LSQ8、TAG1/I128/D1024、COMPLETION_BYPASS2。组合25,952.545800＋时序10,105.106400＋全部实际片上SRAM7,825.666854＝**43,883.319054 µm²**。默认ABC/原始ASAP7 r28 RVT TT、360,511个实际计价叶实例/37个真实宏，未计价/未展开0、最终check0；独立Decimal VERIFIED。同比模式0减少4.1722147%，但同一构建IPC **0.946078833733971**低于模式0；全SRAM频率正在独立运行，不能沿用旧27.9255 MHz。

网表SHA `92afe77a20cc9748af84beb9454ca105cb949fc0fcaf506b007f2159deea0158`，证据 `D:/CPU2026AreaAudits/direct_cdb_precise_tagbanks_i128_r32p48rs8_standard_20261001`。该面积属于早于LSQ接收/预测器改动的冻结模式2快照，核验当前有6个源码差异，未冒称当前源码零差异面积。

当前另已验证新预测器条件目标模式1/FIFO0/store接收0，同资源IPC **0.9567514009772996**（仅+0.098143%），6/5/17/边界全部通过，完整面积正在 `D:/CPU2026AreaAudits/direct_branch_fifo_tagbanks_i128_r32p48rs8_standard_20261001`。LSQ store同拍接收模式1单独试验IPC0.9434785396017451，未选用。以上三种配置严格分开，源码默认新开关均0，pi冻结。详见 `reports/direct_branch_target_2026-10-01.md`、`reports/store_admission_2026-10-01.md`。下面旧FIFO与“直接面积运行中”保留为历史记录，以本节为准。

**后续源码/参数边界：直接完成实验**。工作树在下面冻结FIFO结果之后新增 `COMPLETION_BYPASS=2` 的1/2/4路直接完成网络及即时load-error传递，源码默认模式仍0。36组网络/整合测试、12组模式0/1完整顺序等价、lint/unit/matrix及真实AXI6/5/17/边界通过。新模式2同资源IPC0.946078833733971，单参数LSQ16实验0.949231678649818，均未超过旧FIFO版；未将它们设为默认。新完整面积正在 `D:/CPU2026AreaAudits/direct_cdb_precise_tagbanks_i128_r32p48rs8_standard_20261001` 运行，当前已完成面积45,793.940574只属于下面明确冻结FIFO版本，不是新模式2或LSQ16面积。证据与计数诊断见 `reports/direct_completion_2026-10-01.md`；不得跨源码/模式拼接成绩。

## 2026-10-01：最新ROB并行读口版本完整PPA已完成

当前工作树四发射候选：ROB32/PRF48/RS8/LSQ8，I-cache 2 KiB/2way、D-cache 16 KiB/2way/hash1、DCACHE_TAG_SRAM=1、store合并16；包括最新ROB并行提交读口、one-hot前端、store ACK/tag-query重叠和实际共享AXI适配器。这是显式参数覆盖候选，不是无覆盖默认PRF64/RS16配置。

| 当前版本组成 | 独立Decimal面积 µm² |
|---|---:|
| 组合标准单元 | 27,455.218920 |
| 时序标准单元 | 10,513.054800 |
| 全部片上FakeRAM SRAM | 7,825.666854 |
| **整机总面积** | **45,793.940574** |

原始ASAP7 r28 RVT TT、全局展开/默认ABC；382,493个实际计价叶实例、37个实际SRAM宏，未计价/未展开0、最终网表重读check0。重新运行独立计价工具 `--require-current` 得到VERIFIED，当前源码输入差异0。SRAM按实际写掩码lane和副本计价：I-cache 687.970714、D-cache数据5,503.765696、标签1,633.930444 µm²；仅外部256 MiB仿真RAM不计入，普通RTL数组全部展开并计入标准单元。

同一构建六项benchmark IPC GEOMEAN **0.9558133327368818**，benchmark6/6、basic5/5、simulator17/17及256MiB脏回写边界通过，pi冻结。同一完整网表、全部SRAM参与的STA：最小周期 **35.8095703125 ns**，估计Fmax **27.925495650277 MHz**，2 ns目标下setup slack **-33.808636 ns**，遗漏存储边界0；理想时钟/无寄生综合后估计，不是布局布线实测，也不是500 MHz成绩。

相较上一冻结store管线版本：面积45,928.134894→45,793.940574，减少 **134.194320 µm²（0.292183%）**；频率23.560269654649→27.925495650277 MHz（+18.527912%）；各benchmark周期与退休数精确不变。面积仍超Tier3的36,000上限 **9,793.940574 µm²**，IPC与频率也尚未达标。

面积/时序共同网表SHA256 `713d6245c0eb94162af54cffe85b13acd7ce392a36a960705b134e40e56ccf03`。完整证据 `D:/CPU2026AreaAudits/rob_parallel_tagbanks_i128_r32p48rs8_standard_20261001`，正式构建 `D:/CPU2026Builds/rob_parallel_tagbanks_i128_r32p48rs8_20261001`。当前实际ROB配置完整顺序等价证明12,083/12,083通过；60组参数矩阵仍运行，不冒称全矩阵完成。以下07:35和更早状态按历史记录保留，由本节的完成结果覆盖。

**后续源码边界（07:35）**：工作树又实现ROB各提交lane并行head+lane/共享one-hot packet读取，保留宽度与窗口；新6/5/17/边界回归及lint/unit/matrix通过，六项周期精确不变。下面45,928.134894 µm²/0.9558133327368818/23.560269654649 MHz仅属于ROB修改前的明确冻结构建，现在相对工作树只有ROB文件不同。新完整默认ABC在 `D:/CPU2026AreaAudits/rob_parallel_tagbanks_i128_r32p48rs8_standard_20261001` 实际运行，详细证明状态及失败诊断见 `reports/rob_parallel_read_2026-10-01.md`。不得把旧PPA冒称新ROB结果。

另一份较早one-hot/PRF64/RS16/**旧store管线、旧ROB**冻结审计现已完成：组合32,298.067980、时序11,170.904400、SRAM7,825.666854，总面积 **51,294.639234 µm²**，443,383个计价叶实例、37个宏、未计价/未展开0、最终check0、独立VERIFIED。同构建IPC0.9596478218888492；同一完整网表频率 **25.104192203972 MHz**，最小周期39.833984375 ns，全部SRAM参与。证据 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_standard_20261001`，网表SHA `3e894a6c02d1b17b5e23acd01f5fe052fb7873dfb588c0b02b0562835505598f`。与同参数旧前端51,314.351394相比仅减少19.712160 µm²；以下“PRF64/RS16仍运行”以此完成状态为准，它不能配用新store管线的0.963610821。

## 2026-10-01 07:01：当前store管线版本的总面积已经完整计价

**当前工作树实际四发射候选（不是无参数覆盖默认配置）**：ROB32/PRF48/RS8/LSQ8；I-cache128行×16 B/2way（2 KiB），D-cache1024行×16 B/2way/hash1（16 KiB）；DCACHE_TAG_SRAM=1、store合并16。包含one-hot前端和最新store同边沿ACK、tag查询/data-write重叠，保留实际共享AXI适配器。

| 当前同一冻结版本的组成 | 独立Decimal面积 µm² |
|---|---:|
| 组合标准单元 | 27,589.413240 |
| 时序标准单元 | 10,513.054800 |
| 全部实际片上FakeRAM SRAM | 7,825.666854 |
| **整机总面积** | **45,928.134894** |

默认ABC、原始ASAP7 r28 RVT TT、全局memory_map/flatten，383,242个实际计价叶实例、37个SRAM宏，未计价叶实例/未展开存储均0，最终网表重读check0。`tools/verify_course_axi_area.py --require-current` **VERIFIED**，changed_current_inputs为空；仿真冻结输入/可执行文件/观察驱动、源码/库/脚本/最终统计与网表SHA均核验，原始Liberty实际叶实例数量用Decimal独立累加。没有零面积逻辑黑盒，不混用旧网表。

SRAM包括I-cache数据1×128x128（687.970714）、D-cache数据32×512x8（5,503.765696）及两份标签阵列4×512x19（1,633.930444），逐写掩码lane/实际副本计价，总计7,825.666854 µm²；外部256 MiB仿真RAM不计入，其它普通RTL数组已作为标准单元计入。

当前同一构建的正式六项IPC GEOMEAN **0.9558133327368818**；总周期428254、退休472599，benchmark6/6、basic5/5、simulator17/17和256MiB脏回写边界通过，pi冻结。不能把PRF64/RS16的0.963610821与本配置面积配对。07:03该同一网表的完整SRAM时序已完成：最小周期 **42.4443359375 ns**、频率 **23.560269654649 MHz**、2 ns目标下最差setup slack -40.443760 ns，全部SRAM参与、遗漏存储边界0；不是旧cache频率，2 ns目标不是500 MHz实测成绩。

网表SHA256 `d05ef13c3376d670d08be9b5e3b004d14ea80b843bfd6545be17d2d2925add9f`，面积与完整时序SHA相同。证据 `D:/CPU2026AreaAudits/store_query_overlap_tagbanks_i128_r32p48rs8_standard_20261001` 的area_audit.json、independent_verification.json、run_manifest.json、map.done.json、stat.json、mapped.v、full_timing_audit.json及timing.rpt；同一冻结构建 `D:/CPU2026Builds/store_query_overlap_tagbanks_i128_r32p48rs8_20261001`。完整映射耗时1004.117846秒。

对比仅旧store管线、其余参数相同的one-hot/PRF48/RS8版本：45,947.628354→45,928.134894 µm²，减少 **19.493460 µm²（0.042425%）**；组合减20.076660、时序增0.583200，SRAM不变。面积仍超36,000上限 **9,928.134894 µm²（27.578152%）**，逻辑本身38,102.468040 µm²也超过36,000；面积尚未达标。下方06:36和更早章节为对应冻结历史记录，不再作为当前版本成绩。

## 2026-10-01 06:36：one-hot前端 + PRF48/RS8的完整PPA已完成

这是**旧store管线**冻结构建的完整结果，不含工作树后来新增的store ACK旁路和tag/data-write重叠。参数：四发射、ROB32/PRF48/RS8/LSQ8、I-cache128行/2way、D-cache1024行/2way/hash1、DCACHE_TAG_SRAM=1、store合并16；包含实际AXI适配器。

| 同一冻结版本的组成 | 面积 µm² |
|---|---:|
| 组合标准单元 | 27,609.489900 |
| 时序标准单元 | 10,512.471600 |
| 全部实际FakeRAM SRAM | 7,825.666854 |
| **整机总面积** | **45,947.628354** |

默认ABC/原始ASAP7 r28 RVT TT，全局展开；383,537个计价叶实例、37个SRAM宏，未计价/未展开均0，最终网表重读check0。原始Liberty与实际实例独立Decimal计价 **VERIFIED**。同一冻结构建六项IPC GEOMEAN **0.9519069653774248**，6/5/17/边界回归全部通过，pi冻结。全部真实SRAM参与的完整STA：最小周期 **44.7958984375 ns**，频率 **22.323472346363 MHz**，遗漏存储边界0；2 ns映射目标不是500 MHz成绩。

网表SHA256 `abff6777f1fbc7e20f6151be53271aff0517def973ac2895ab2598ecd5b4cfcc`。证据目录 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_r32p48rs8_standard_20261001`：area_audit.json、independent_verification.json、full_timing_audit.json、timing.rpt；冻结构建 `D:/CPU2026Builds/frontend_onehot_tagbanks_i128_r32p48rs8_20261001`。

与同参数旧动态索引前端的46,154.839314 µm²相比，清单参数完全相同、仅frontend源码SHA不同；完整CPU总面积实际减少 **207.210960 µm²（0.448947%）**，时序单元/SRAM面积不变，IPC逐项周期/退休数不变。完整频率反而从24.993288降至22.323472 MHz，不能把孤立前端的9.01%面积改善或250.43 MHz当作整机结果。面积仍超36,000上限 **9,947.628354 µm²**。

按这份实际组成，标准单元逻辑本身38,121.961500 µm²已超过36,000，即使不合法地把SRAM漏计也不能通过。保持时序单元与SRAM规模时，组合逻辑预算仅17,661.861546 µm²，需要组合部分再压缩36.029743%，等价于总面积降低21.649928%。这只是冻结配置的预算计算，不是已经取得的优化成果；不能靠缓存容量局部削减宣称整机达标。

**当前工作树边界**：核验发现相对这份冻结输入只有 `rtl/cache/rv32_dcache_nonblocking.v` 改变。因此最新store管线的PRF48/RS8实测IPC **0.9558133327368818** 不能和本节旧cache面积/频率拼接。最新组合的完整计价正在 `D:/CPU2026AreaAudits/store_query_overlap_tagbanks_i128_r32p48rs8_standard_20261001` 运行，完成后须再次独立复核；PRF64/RS16 one-hot旧cache版本也另行运行。以下旧章节的运行状态按各自记录时间保留，以本节为准。

后续源码边界（2026-10-01）：工作树又新增TAG1 store ACK旁路和tag/data-write重叠，完整四套整机回归、四态协议及随机hash矩阵通过，PRF64/RS16最新IPC0.9636108214058166。下面面积/频率仅属于各自明确冻结版本，不能当成本轮新cache管线结果；新PRF48/RS8组合构建→回归→独立默认ABC计价已启动，具体证据见 `reports/dcache_store_query_pipeline_2026-10-01.md`。

## 2026-10-01 05:52：三份冻结配置的完整PPA已完成；后续读口重构另行计价

无参数覆盖I64配置已完成默认ABC，总面积 **59,445.084949 µm²**。组成：组合37,356.671880、时序16,240.662000、SRAM5,847.751069；526,969个实际叶实例、17个SRAM宏，未计价/未展开均0，网表重读check0。独立VERIFIED。网表SHA256 `2fa3bf53013ddb112821103ac9ab7cb9e29c6276fba2286176a1d7216da9410e`，映射耗时9115.708400秒。

以下三行均来自各自同一冻结构建及完整默认ABC网表，时序包含全部真实SRAM、遗漏存储边界0，原版课程ns/fF约束。2 ns只作为映射/检查目标，实际频率为完整STA结果，不是500 MHz：

| 冻结配置（取指读口重构之前） | 完整面积 µm² | 六项IPC GEOMEAN | 完整频率 MHz |
|---|---:|---:|---:|
| I64、普通标签、无参数覆盖 | 59,445.084949 | 0.982501248101083 | 17.228325790333 |
| I128、普通标签 | 60,619.503366 | 1.001507321478700 | 14.720680831488 |
| I128、同步标签SRAM/并行数据bank | 51,314.351394 | 0.959647821888849 | 25.615369221533 |

证据：对应D盘审计目录中的 `area_audit.json`、`independent_verification.json`、`full_timing_audit.json`、`timing.rpt`；默认配置另完成冻结源码下的新6/5/17/边界回归，`build/cpu2026/latest_defaults_frozen_*_20261001.json`；普通标签I128同样另完成新6/5/17/边界回归，`build/cpu2026/tagff_i128_frozen_*_20261001.json`。pi冻结。

**当前版本边界**：完整时序定位到取指队列 `head_reg[0]` 的3398扇出后，工作树已将该队列读口改成共享one-hot解码/掩码归并。以上三份冻结面积与频率因此不再冒称本次读口重构后的结果。新版本通过14组完整顺序等价证明及6/5/17/边界回归，benchmark各项周期与退休数精确不变；新整机默认ABC审计在 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_standard_20261001`，尚待完成。孤立前端面积/时序诊断见 `reports/frontend_onehot_2026-10-01.md`，不能替代整机成绩。

另一缩参实验现已完整计价：重构前TAG1/I128、PRF48/RS8保留ROB32，通过6/5/17/边界，IPC **0.9519069653774248**；默认ABC总面积 **46,154.839314 µm²**（组合27,816.700860、时序10,512.471600、SRAM7,825.666854），389,527个计价叶实例、37个实际宏，未计价/未展开0、最终check0，独立VERIFIED。网表SHA256 `84ddeb5594233720511f83cdc7164262b6a645fe4396e33c7803aa239ccf94f3`；完整频率 **24.993287935369 MHz**、最小周期40.0107421875 ns，全部SRAM与路径包含。相比同源码TAG1/I128的PRF64/RS16，总面积实际降低5,159.512080 µm²（10.054716%），IPC降低0.806635%；仍超36,000上限10,154.839314 µm²。

证据 `D:/CPU2026AreaAudits/tagbanks_i128_r32p48rs8_standard_20261001`，对应同一冻结构建 `D:/CPU2026Builds/tagbanks_i128_r32p48rs8_20261001`。它不含后续one-hot前端读口；工作树相对快照的唯一RTL差异仍为该前端文件。不能从46,154.839314减去孤立前端收益来宣布新的整机面积。组合这两项改动的新构建 `D:/CPU2026Builds/frontend_onehot_tagbanks_i128_r32p48rs8_20261001` 已编译并通过6/5/17/边界回归，六项周期/退休数精确不变、IPC0.9519069653774248；新完整计价在 `D:/CPU2026AreaAudits/frontend_onehot_tagbanks_i128_r32p48rs8_standard_20261001` 实际运行中，结果须独立等待。全部候选仍未同时满足36,000 µm²/1.0985/300 MHz，目标保持未完成。

05:24曾对两份I128面积执行 `--require-current`并通过；之后新增的唯一RTL修改是取指读口。因此后来核验会明确报告该文件差异，不能绕过或把旧网表当作当前源码。

## 2026-10-01 本轮冻结源码审计（取指读口重构前；三份配置均已完成）

本轮面积冻结源码已加入16周期store合并、waiter复用保护，以及可选的同步标签SRAM/按way并行数据bank/单拍load-hit旁路。此前历史面积不能代替该源码重新综合的结果。

本轮冻结时与工作树逐项SHA256匹配的实际AXI `student_top`：四发射、ROB32/PRF64/RS16/LSQ8、D-cache1024×16 B（16 KiB/2way/hash1）、store合并窗口16。主报告采用无参数覆盖的源码默认I-cache64×16 B（1 KiB/2way）、普通标签；另外独立计算两份I-cache128×16 B（2 KiB/2way）候选：

| 候选 | DCACHE_TAG_SRAM | 本轮默认ABC完整面积状态 | 输出目录 |
|---|---:|---|---|
| **冻结默认、I64、无参数覆盖** | 0 | **COMPLETE / VERIFIED，59,445.084949 µm²** | `D:/CPU2026AreaAudits/latest_defaults_standard_20261001` |
| 普通标签、I128基线 | 0 | **COMPLETE / VERIFIED，60,619.503366 µm²** | `D:/CPU2026AreaAudits/latest_tagff_i128_standard_20261001` |
| 标签SRAM、并行数据bank | 1 | **COMPLETE / VERIFIED，51,314.351394 µm²** | `D:/CPU2026AreaAudits/latest_tagbanks_i128_standard_20261001` |

三份均使用课程原版ASAP7 r28 RVT TT五份Liberty、框架SRAM生成器/计价函数、全局flatten、默认ABC及2 ns目标周期。2 ns只是映射目标，不代表已验证500 MHz。全部实际片上SRAM（包括副本）计价；所有普通RTL数组memory_map并计入标准单元；外部256 MiB仿真RAM不计入。I128候选显式覆盖ICACHE_LINES=128；不将候选数值冒称无参数覆盖默认配置。

最新标签SRAM版完整6/5/17/边界测试通过（pi冻结），IPC GEOMEAN 0.959647821888849；同源码普通标签I128基线IPC为1.0015073214787。标签迁移尚有性能代价，不能称为已选定性能优化或Tier3达标。

独立复核工具 `tools/verify_course_axi_area.py` 从原始Liberty单元面积及最终叶实例数量以Decimal重新计价，验证源码快照、仿真冻结输入、库、统计与网表SHA256。`--require-current` 要求与工作树对应；若旧报告对应不同源码会拒绝，不允许以旧面积代替最新面积。

### 最新标签SRAM/并行bank版：默认ABC完整结果已完成

| 组成 | 原始Liberty独立Decimal计价 µm² |
|---|---:|
| 组合标准单元（含常量驱动） | 32,317.488540 |
| 时序标准单元 | 11,171.196000 |
| 片上FakeRAM SRAM | 7,825.666854 |
| **整机总面积** | **51,314.351394** |

这份结果是本轮当前源码的实际AXI `student_top` 全局flatten/default ABC网表，不复用已映射核心、不保留零面积逻辑黑盒。COMPLETE、独立VERIFIED，`--require-current`通过；445,507个计价叶实例、37个实际SRAM宏，未计价与未展开存储均0，最终网表重读check0个问题。全部组成来自同一网表SHA256 `43e98c148b9a8f08ea540fc9bb41c263a27e13d33f6abcd07e5c86b3621e7839`。

输出 `D:/CPU2026AreaAudits/latest_tagbanks_i128_standard_20261001/area_audit.json`、`independent_verification.json`、`run_manifest.json`、`map.done.json`。默认映射阶段实际4666.358381秒，不以经典映射替代。面积比36,000 µm²上限高15,314.351394 µm²，尚未达标；2 ns是映射目标，后续另以同网表完成包含全部SRAM的完整时序核验25.615369221533 MHz，见顶部PPA表。

注意：这份候选显式开启DCACHE_TAG_SRAM=1并设置ICACHE_LINES=128；源码无覆盖默认仍是TAG_SRAM=0、ICACHE_LINES=64。无覆盖冻结默认配置已独立完成59,445.084949 µm²，不把本节候选数字当成默认配置面积。

### 同源码普通标签I128对照：默认ABC完整结果已完成

| 组成 | 原始Liberty独立Decimal计价 µm² |
|---|---:|
| 组合标准单元（含常量驱动） | 37,767.200940 |
| 时序标准单元 | 16,660.566000 |
| 片上FakeRAM SRAM | 6,191.736426 |
| **整机总面积** | **60,619.503366** |

COMPLETE、独立VERIFIED，`--require-current`通过；533,979个计价叶实例、17个SRAM宏，未计价与未展开存储均0，最终网表重读check0个问题。网表SHA256 `48dca61b9d09289775f54623c822a8592973133ca35f7b02d4cd3bd3a331c4d8`。输出 `D:/CPU2026AreaAudits/latest_tagff_i128_standard_20261001/area_audit.json`、`independent_verification.json`、`run_manifest.json`。

两份I128候选相同源码、相同默认ABC/2 ns目标周期、相同I/D容量和其它顶层参数，仅DCACHE_TAG_SRAM不同。开启标签SRAM/并行bank版，组合面积减少5,449.712400、时序面积减少5,489.370000、SRAM面积增加1,633.930428 µm²，**总面积减少9,305.151972 µm²，约15.35%**。这次对照没有跨源码、跨缓存容量或跨ABC映射方式混算；对应IPC从1.0015073214787降到0.959647821888849，面积下降不代表性能同步提升。

### 最新标签SRAM/并行bank版：完整经典映射交叉对照已完成

这份结果对应本轮最新冻结源码，**是classic-area完整映射，不是默认ABC正式成绩**：

| 组成 | 原始Liberty独立Decimal计价 µm² |
|---|---:|
| 组合标准单元（含常量驱动） | 36,611.721360 |
| 时序标准单元 | 11,171.487600 |
| 片上FakeRAM SRAM | 7,825.666854 |
| **整机总面积** | **55,608.875814** |

COMPLETE / 独立VERIFIED：539,302个计价叶实例，37个SRAM宏，未计价叶实例0、未展开存储0，最终网表重读check0个问题。`--require-current`通过，输入与当前工作树完全匹配。网表SHA256 `06ede3e61874d271992c0fbf28811a5f5f34932696e6b601804a4e2a40d5ca5b`。

SRAM实际实例分解：I-cache数据1×128x128，687.970714 µm²；D-cache数据32×512x8，5,503.765696 µm²；D-cache两份标签存储共4×512x19，1,633.930444 µm²。按原框架逐写掩码lane生成并独立舍入，不能改为整个容量一次舍入，也不能漏掉标签副本。

输出 `D:/CPU2026AreaAudits/latest_tagbanks_i128_classic_20261001/area_audit.json`、`independent_verification.json`、`run_manifest.json`。展开/准备复用本轮默认流程同一源码、参数、库及哈希核验的结果，ABC经典映射重新执行，没有复用任何已映射逻辑网表。经典结果比36,000 µm²上限高19,608.875814 µm²，面积未达标。该候选默认ABC现已完成51,314.351394 µm²，无参数覆盖I64亦已完成59,445.084949 µm²，见顶部；后续one-hot读口新版本另行运行。

## 已完成的较新历史版本：store合并16，经典ABC

| 旧冻结版本 | 组合 µm² | 时序 µm² | 实际SRAM µm² | 整机总面积 µm² |
|---|---:|---:|---:|---:|
| I64、普通标签、store合并16 | 43,050.409740 | 16,241.245200 | 5,847.751069 | **65,139.406009** |
| I128、普通标签、store合并16 | 43,719.413040 | 16,661.149200 | 6,191.736426 | **66,572.298666** |

两份COMPLETE，未计价叶实例与未展开存储均0，分别650,240/660,573个计价叶实例，17个SRAM宏。原始Liberty独立计价复核VERIFIED。网表SHA256分别 `8dad64cf436bc3a6427bac370d3c5f6bf5f6c86cc01592ebdad2dd7767056a13`、`5825c725476ae686e2c12715b7faf4c0c0c5e08f972fdbb9c89c931ae06e0d2d`。这两份是加入可选标签SRAM重构之前的源码，且使用classic-area映射，不是本轮默认ABC正式数值。

证据：`build/synth/course_axi_storemerge16_fixed_classic_20261001/area_audit.json`（原路径为指向D盘的目录junction），以及 `C:/Users/admin/AppData/Local/CPU2026AreaAudits/course_axi_storemerge16_i128_classic_20261001/area_audit.json`。完整历史产物保留；移动归档没有删除证据。

## 已完成的旧版默认ABC：I/D-cache数据SRAM，未加入store合并

此前运行中的默认ABC已COMPLETE，总面积 **60,029.670049 µm²** =组合37,952.046180 +时序16,229.872800 +SRAM5,847.751069。536,591个计价叶实例，17个SRAM宏，未计价/未展开均0，原始Liberty独立复核VERIFIED。网表SHA256 `2c3caa5f9eecef838516f5fcd61f38d3439d794ac16a1a4fc3efdeb1c373bab2`。目标周期为10/3 ns。证据 `build/synth/course_axi_idata_sram_p4_opt_20261001/area_audit.json`、`independent_verification.json`。

该结果属于I64、加入store合并之前的冻结源码，与当前源码不一致，不能称为最新成果，也不能从它和经典ABC的差值推导RTL面积优化收益。

## 历史对照：I/D-cache 数据 SRAM，经典ABC完整面积

当时冻结的四发射 `student_top`（包含实际 AXI4-Lite 适配器）已完成全局flatten与完整计价。**经典ABC面积映射结果为64,740.978349 µm²**。该数值是store合并/标签SRAM重构之前的历史源码，且脚本为classic-area，不能当成本轮最新默认ABC面积。

| 历史I/D SRAM版本，经典ABC映射 | 面积 µm² |
|---|---:|
| 组合标准单元，含常量驱动 | 42,662.771279554 |
| 时序标准单元 | 16,230.456000000 |
| 实际 FakeRAM SRAM 宏 | 5,847.751069000 |
| **整机总面积，独立 Decimal 累加** | **64,740.978349000** |

I-cache 数据为 1 个 `fakeram_asap7_64x128` 宏；D-cache 数据为 16 个 `fakeram_asap7_1024x8` 宏。每个宏面积 343.985357 µm²，17 个宏合计 5,847.751069 µm²。其它普通 RTL 数组（包括标签、预测器和乱序状态）按实际映射标准单元计入，不作零面积排除。外部 256 MiB 仿真内存不计入。

审计 `COMPLETE`：643,612 个计价叶实例，未计价叶实例 0，未展开存储 0；课程原版计价函数、Yosys 递归统计与独立 Decimal 累加一致。最终网表重读检查 0 个问题。网表 SHA256 为 `2f28fec23014bd61ac0142615383a1fdfe67277ea3863a0bac08617fca126a68`，冻结仿真输入在当时逐项匹配，后续源码已改变。经典映射面积超出 Tier 3 的 36,000 µm² 上限 28,740.978349 µm²，不能据此声称达标。

历史配置：FE/BE/整数发射/CDB 均为 4；ROB32、PRF64、RS16、LSQ8；I-cache 64×16 B、2way，D-cache 1024×16 B、2way/hash1；I/D MSHR8/4；AXI READ_LINES16、WRITE_LINES8、WORD_QUEUE64。参数无 `-G` 覆盖。该历史版本正式 AXI 的六项 benchmark IPC GEOMEAN 为 0.980736877；本节没有该网表的完整频率结果。

证据：

- 已完成经典映射：`build/synth/course_axi_idata_sram_p4_classic_v2_20261001/area_audit.json`，以及同目录 `run_manifest.json`、`map.done.json`、`stat.json`、`design.json`、`mapped.v`、`map.log`。
- 同一旧冻结版本默认映射目录：`build/synth/course_axi_idata_sram_p4_opt_20261001/`，现已完成60,029.670049 µm²。此运行校验并复用同一冻结候选的 elaboration/prepare（全局 memory_map 与 dfflibmap），重新执行默认 ABC，不复用经典映射后的逻辑网表；复用来源及 SHA256 记录在清单和阶段标记中。

默认映射命令：

```powershell
python tools/run_course_axi_area.py --build-manifest build/vlt/course_axi_idata_sram_p4_20260930/build_manifest.json --outdir build/synth/course_axi_idata_sram_p4_opt_20261001 --reuse-prepared-run build/synth/course_axi_idata_sram_p4_classic_v2_20261001
```

## 上一版默认全局 opt：D-cache SRAM、I-cache 数据仍为 FF

此前等待中的全局综合已经完成，不再使用下面分层结果作为默认综合数值。上一版默认 ABC 总面积为 **62,953.004372 µm²**：组合 38,830.870259579、时序 18,618.368400000、SRAM 5,503.765712000 µm²。554,944 个计价叶实例，未计价/未展开均为 0。同一完整网表的频率为 8.108054608 MHz、最小周期 123.334147135 ns；包含 SRAM 时序，不沿用局部路径的 305 MHz。网表 SHA256 `29a6c7b386da1ab8ce335372ac02a6fefc1ef7a0af6d8f89d3e9d77d17587391`。

证据 `build/synth/course_axi_p4_opt_20260930/area_audit.json`、`full_timing_audit.json`，以及归档的 `source_snapshot/`。这份旧配置与最新 I-cache SRAM 配置不同；也不能把默认 ABC 与经典 ABC 的面积差直接当作 RTL 优化收益或回退。

## 历史成果：SRAM D-cache + 实际 AXI student_top，保留核心边界

2026-09-30，完整保留核心边界的整机综合网表已计价并通过审计。**总面积为 65,968.760732 µm²**，包含 CPU 核心、新增 AXI4-Lite 适配器及全部片上存储。外部 256 MiB 仿真 RAM 不计入。

| 项目 | 面积 µm² |
|---|---:|
| 组合标准单元，含常量驱动 | 41,016.149820 |
| 时序标准单元 | 19,448.845200 |
| 实际 FakeRAM SRAM 宏 | 5,503.765712 |
| **整机总面积** | **65,968.760732** |

不重叠的模块分解：CPU 核心 62,994.367832 µm²，AXI 适配器 2,974.392900 µm²；顶层只有接线，不额外产生单元。核心的组合/时序/SRAM分别为 39,608.523720 / 17,882.078400 / 5,503.765712 µm²；AXI 的组合/时序分别为 1,407.626100 / 1,566.766800 µm²。

D-cache 数据存储为框架实际生成的 16 个 `fakeram_asap7_1024x8` 宏，单宏 343.985357 µm²，总计 131,072 bit（16 KiB）。标签、预测器、PRF、ROB、RS、LSQ、MSHR、AXI 待读写 line 与 word 队列等其它数组均作为实际标准单元计入，没有根据数组用途自行免计面积。

审计结果 `COMPLETE`：583,462 个计价叶实例，其中核心 558,342、AXI 25,120；未计价叶实例 0，未展开存储 0。课程原版 `scripts/synth_report.py:area_report`、独立 Decimal 累加（65,968.760732）及 Yosys 递归统计（65,968.760732）一致。最终网表重新读入并通过 `hierarchy -check`、`check -assert -mapped`，0 个问题。

Tier 3 上限 36,000 µm²，本结果超出 **29,968.760732 µm²**，面积要求尚未达成。

### 方法与结果边界

这份结果是**完整的保留边界网表面积，不是默认全局 flatten 优化结果**。已完成的核心使用课程 `opt` 展平和标准 ABC 映射；本轮从当前完整 `student_top` 的真实 elaboration 中保留顶层接线和 AXI 模块，仅复用哈希匹配的已映射核心。全部核心参数和端口方向/位宽逐项核对，再对 AXI 进行实际 memory_map、标准 ABC 映射、常量驱动映射，并链接出完整可检查网表。没有把 CPU 核心作为零面积黑盒，没有以估算值替代 AXI 综合，没有进行跨核心/AXI 边界的全局优化。ASAP7 r28 RVT TT 五份原始库、框架 FakeRAM 模型与核心原综合一致。

实际配置：四发射；ROB32、PRF64、RS16、LSQ8；I-cache 1 KiB/2way，D-cache 16 KiB/2way/hash1；I/D MSHR8/4；AXI READ_LINES16、WRITE_LINES8、WORD_QUEUE64。采用 `build/vlt/course_axi_p4_r32p64_ctx/build_manifest.json` 冻结的实际 AXI 顶层源码默认参数，无 `-G` 覆盖。可执行文件 SHA256 `87085f66d726ad482f2b6da7ceff629553cd0f93610679da8a8f027456a4fb03`。

证据目录 `build/synth/course_axi_p4_hier_20260930/`：

- `area_audit.json`：课程总面积、完整模块树、16 个 SRAM 实例、独立累加、所有叶单元数量。
- `run_manifest.json`：全部源码和库哈希、复用核心/当前 elaboration 的哈希、真实参数和映射边界。
- `stat.json`、`design.json`、`mapped.v`：同一完整整机网表的统计、结构和 Verilog。
- `map.ys`、`map.log`：实际综合、计价和最终网表重读检查。

重现命令：

```powershell
python tools/run_course_axi_hier_area.py --full-run build/synth/course_axi_p4_opt_20260930 --core-run build/synth/dcache_sram_p4_course_opt_20260930 --outdir build/synth/course_axi_p4_hier_recheck
```

当时同时启动了实际 AXI `student_top` 的独立全局 `opt`/标准 ABC 重新综合，目录 `build/synth/course_axi_p4_opt_20260930/`。该运行现已完成，结果见上文上一版默认全局 opt；没有复用已映射核心，不能将本节分层表冒称为其结果。pi 保持冻结。

后续完整时序核验已完成：同一分层整机网表为6.650574MHz，最小周期150.362956ns，原版课程约束、全部SRAM路径包含、遗漏存储边界0。报告 `build/synth/course_axi_p4_hier_20260930/full_timing_audit.json` 与面积报告具有相同网表SHA256 `145e0cc1fa2e574a1279379594bd4603ab14fb4b62a86fb8c3a68ae8db78e4c6`。该网表的实际配置在官方AXI内存下六项IPC GEOMEAN为0.982319982，三项Tier3要求均未达到。分层时序不替代已完成的全局opt网表结果。

## 历史参考：SRAM 迁移前的全 FF 核心

版本边界更新：下表是SRAM迁移前、2026-09-30已核验的全FF参考网表面积。后续工作树已实际迁移D-cache数据阵列；新版IPC和迁移证据见 `reports/dcache_sram_integration_2026-09-30.md`。新版总面积必须等待新的完整课程综合，不能沿用本表或以容量公式代换。

2026-09-30，当前 `cpu_core`，外部256MiB仿真主存不计入。

| 项目 | 面积 µm² |
|---|---:|
| 组合标准单元，含常量驱动 | 90,802.198800 |
| 时序标准单元 | 57,367.634400 |
| FakeRAM SRAM | 0.000000 |
| **总面积** | **148,169.833200** |

该历史版本RTL没有实际实例化 `sram_fakeram`，SRAM宏实例数为0。所有普通RTL数组，包括Cache数据/标签、预测表、PRF、ROB、RS、LSQ、队列和MSHR，均完整映射到标准单元，成本已计入组合与时序项。没有按零面积存储黑盒保留。

审计状态COMPLETE；叶实例1,436,411，未计价叶实例0，未展开存储0。课程原版 `scripts/synth_report.py:area_report` 的递归结果、独立Decimal叶单元累加和Yosys统计一致，浮点舍入差低于0.00001µm²。

Tier3上限36,000µm²，当前超出112,169.833200µm²，约为上限4.12倍，目标未达成。

## 组成

以下为顶层直接子模块的包含式面积，各行之间不重叠；后端一行已包含其RS/ROB/PRF等子模块。

| 模块 | 面积 µm² |
|---|---:|
| D-cache | 93,770.147339 |
| 乱序后端 | 42,742.290600 |
| I-cache | 6,429.721680 |
| 分bank预测器 | 2,894.815260 |
| 取指前端 | 1,937.944440 |
| 内存桥接 | 78.017580 |
| 四份译码器合计 | 63.510480 |
| 顶层自身逻辑 | 253.385820 |

D-cache映射包含156,259个触发器，时序面积45,565.124400µm²；其余为读出选择、写控制及其它组合电路。需实际接入合法同步1RW宏后重新计算，不能用容量乘系数替换当前实现的成本。

## 配置、方法与边界

FE/BE/整数发射/CDB宽度4；ROB32、PRF64、RS16、LSQ8；取指/完成队列深度16；D-cache1024条16-byte line、2way、hash=1（16KiB）；I-cache64条line、2way（1KiB）；I/D MSHR8/4；CheckpointImpl=1；MulImpl/ShiftImpl/PhysTagImpl=0；GenerationWidth=8；StoreBufferedRetire默认1；DcacheRequestPipeline=0。与最近通过六项benchmark的bankedpred配置相同，RTL/TB源码哈希逐项核对无差异。本轮未修改RTL、未运行pi。

框架commit `54fc150ffc290f52aa024209ffb9a29d43856f6d`。标准单元库使用框架Dockerfile指定ASAP7 r28 commit `f970bd3c3292b79ae4d022a3ec80533534614066`：AO/OA/SIMPLE 211120、INVBUF 220122、SEQ 220123，RVT TT五份原始Liberty；没有使用旧版过滤/归一化库。全部库和RTL哈希记录在运行清单。

Yosys本地版本0.68+120。逐模块完整memory_map并进行经典ABC面积映射，保留层级、按实际实例计价；跳过可选SAT端口优化，保留原写优先级。默认ABC优化在RS上耗时过长后改用 `+strash;scorr;dc2;dretime;strash;map -a`，准备阶段复用、映射阶段重新计算，旧运行清单保留。结果对应本次完整综合网表，**不是框架默认flattened opt模式的数值，也不是最小面积下界**。

按课程流程加入TIEHI/TIELO后增加11,198个叶实例、489.800520µm²；加入前独立总面积147,680.032680µm²，加入后为上表发布值。未增加布局留白、CTS或布线寄生。本轮没有完整时序分析，不沿用原305.19MHz的局部时序结论。

## 证据

目录 `build/synth/bankedpred_p4_r32p64_lsq8_course_r28_full_20260930/`：

- `run_manifest.json`：参数、全部输入/库哈希、映射选项。
- `area_audit.json`、`independent_area_audit.json`：加入常量单元前的完整计价、独立核验。
- `course_area_audit.json`：课程函数结果、模块树、独立累加、最终总面积、框架与网表哈希。
- `course_stat.json`、`course_design.json`、`course_mapped.v`：最终计价对应的统计、结构和网表。
- `course_area.ys`、`course_area.log`：汇总命令与日志。
- `mapped_*.il`、`map_*.ys`、`map_*.log`：全部20个模块的展开/映射证据。

已核对最终网表SHA256、综合输入SHA256以及最近冻结仿真源码SHA256，全部匹配。后续优化需接入框架SRAM并重测正确性、IPC、完整面积与频率。
