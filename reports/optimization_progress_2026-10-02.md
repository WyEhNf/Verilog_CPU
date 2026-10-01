# 2026-10-02 优化进度与严格配置边界

**07:46最新完成证据**：新布局0/1的全部6/5/17/边界29项通过，严格机器对照逐项cycle/instret/退出码完全相同、当前SHA核验通过；当前六项IPC均为1.1213155347352615，开启版完整PPA已进入prepare。冻结的地址1/Cache控制0、2大窗口完整PPA均独立核价及全SRAM STA完成：总面积59205.207774/60175.215174µm²，频率27.09281405439729/15.632394473704297MHz，旧版六项IPC均1.0881243892617036、37宏全部计价/时序、遗漏边界0。控制分组在这组整机中面积和频率均退化，不选为优胜方案；新布局不能沿用这两套PPA。D-cache注册查询索引只在独立候选实现，12项真实Cache协议初检通过、360项在测，尚未接入主树或宣称提频。下面11项/仍运行等为此前时间记录。见[冻结PPA与计数修正](dcache_control_banks_integration_2026-10-02.md)。

**最新实测（2026-10-02）**：`RS_ISSUE_METADATA=0/1`实际接入后，两套同源码原生构建完成，benchmark6/basic5全部通过且11项机器对照逐项cycle/instret/退出码完全相同，当前SHA核验通过；六项计分IPC均为 **1.1213155347352615**，周期372783/退休472599。simulator17/边界仍在测，开启版随后执行完整PPA，尚无新布局面积/频率成绩。默认0、无新增执行拍，342组协议及8090次ALU对照通过。补充1024行Cache形式证明因资源优先级明确取消，四套小配置证明保留，未称全规模证明通过；正式完成门槛不变。见[实际接入与证据](rs_issue_metadata_2026-10-02.md)。以下运行中/当前SHA0等为各历史时刻，不拼接冻结PPA。

**共享AGU最新整机结果**：地址模式2已进入实际RS/LSQ/后端/CPU及两个filelist；162组后端回归、21组集成定向检查通过。新ROB64/PRF64/RS16/LSQ16、Cache控制2/地址2原生构建及benchmark6/basic5全部通过，计分IPC GEOMEAN **1.1213155347352615**、周期372783/退休472599、当前源码差异0；较接入前地址1冻结对照提升3.05031%。simulator17/边界尚待完成，原版总面积与全SRAM频率待测，不能宣布Tier3。旧Cache控制0/2 PPA已冻结接入前源码，不与新IPC配用。见[共享store AGU报告](shared_store_address_2026-10-02.md)。

**后续接入边界（2026-10-02）**：真实D-cache已新增可选模式2、两个CPU filelist已加入功能状态模块；180项三模式Cache协议通过。新ROB64模式0/2同源码整机各29项全部通过且逐项cycle/instret/退出码相同，IPC1.0881243892617036；两套完整PPA在测。四套小Cache完整控制器/SRAM引脚证明完成、实际1024行仍在运行，默认仍0。新大窗口只读诊断和36924次后续真实地址核验表明store基址/数据分阶段值得实际实现，但重叠/反事实计数不是已获得收益。下方“尚未接入CPU”和当前源码零差异PPA是接入前冻结时刻，不作为新RTL成绩。接入前ROB64两种主机编译29项也已逐项相同。详见[接入报告](dcache_control_banks_integration_2026-10-02.md)。

目标不变：同一最终配置总面积≤36,000µm²、六项benchmark IPC GEOMEAN≥1.0985、包含全部真实SRAM的频率≥300MHz；完整RV32IM/自然对齐访存、乱序执行、严格顺序提交、单共享32-bit AXI、外部256MiB RAM及20cycle/word、MMIO完整word写B握手退出。Pi冻结。**尚未达成Tier3**。

## 已完成的同源码RAT整机PPA

两套都为响应FIFO2、四发射ROB32/PRF48/RS8/LSQ8、early0、I128/D1024/2way/TAG1/预测1、CPL16、AXI8/4/16，仅改变RAT恢复实现；不是无-G覆盖默认配置。

| RAT_RECOVERY_IMPL | 组合 µm² | 时序 µm² | 全部SRAM µm² | 总面积 µm² | 六项IPC GEOMEAN | 全SRAM估计Fmax MHz |
|---|---:|---:|---:|---:|---:|---:|
| 0，原链式撤销 | 26987.011380 | 9932.187600 | 7825.666854 | 44744.865834 | 0.9562805856296562 | 27.438370846730976 |
| 1，并行最老被杀写者 | 25955.563860 | 9932.187600 | 7825.666854 | 43713.418314 | 0.9562805856296562 | 31.170096188968706 |

面积少1031.447520µm²，时序与SRAM面积不变。最小周期36.4453125→32.08203125ns；2ns约束slack -34.445271/-30.08185ns。原始五库/default ABC、实际叶实例373621/358565、实际SRAM37/37；未计价/未展开/遗漏存储时序边界0，两套独立Decimal `--require-current`均VERIFIED、输入差异0。两套29项cycle/instret/退出结果逐项相同。仅外部平台RAM不计，普通RTL数组及真实AXI适配器均计入。

网表SHA256分别`55fd838448e7674b24e93d27ef9036075ffeb91dd547be065c65c4f75ba27137`、`db974b15403bdb89a6c8bc33bffb495864680965e3388a9db6096c413f9d0e3a`。证据：`D:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r32p48rs8{,_rat1}_standard_20261002rat`。这是理想时钟/无布线寄生的综合后估计，不是PnR成绩。增加新选项之前的44,544.142974/28.182193477参考不再替代本次同源码对照。

首轮RAT0的prepared.il与RAT1映射输出在编译引发的磁盘压力期间损坏，分别明确终止于RTLIL解析错误与最终网表重读EOF。失败文件/标记/日志保留在`D:/CPU2026Diagnostics/rat0_truncated_prepare_20261002`、`rat1_truncated_mapping_20261002`，只恢复已确认失败阶段，保留成功elaboration/preparation。未把失败输出计为成绩，未因观察超时重启活任务，未删除源文件或改变框架/库。

## 新窗口性能对照

以下保持early1/RAT1及同一缓存/预测/总线参数，全部使用原官方20cycle共享内存：

| ROB/PRF/RS/LSQ | 六项周期合计 | 六项退休数 | 六项IPC GEOMEAN | 当前验证范围 |
|---|---:|---:|---:|---|
| 32/64/16/16 | 416444 | 472599 | 1.0324037635213024 | benchmark6/basic5/simulator17/边界1全部通过 |
| 64/64/16/16 | 396452 | 472599 | 1.0881243892617036 | benchmark6/basic5/simulator17/边界1全部通过 |
| 64/96/16/16 | 396081 | 472599 | 1.0886932595176315 | benchmark6/basic5/simulator17/边界1全部通过 |

ROB32→64只改一个硬件参数：median10637→10166、multiply12112→11871、qsort166404→161179、rsort217460→204069、towers5194不变、vvadd4637→3973。ROB64距IPC门槛约0.95%。再只增PRF64→96，IPC仅增约0.0523%，未选为最终优胜配置。**这三套大窗口没有对应完整面积/频率，不可拼接上面的43,713.42µm²或31.17MHz。**

报告前缀为`build/cpu2026/axi_response_fifo2_branch1_bus8w4q16_i128_r{32,64}p64rs16_lsq16_rat1_earlystore1_*_20261002windowearly{,_split}.json`；PRF96后缀`20261002prf96_split`。

原构建助手未改，新增`tools/build_course_verilator_split.ps1`明确`--output-groups 0`及模型C++ `-Os`，防止-j1默认重新合组大输出文件；官方驱动仍只增加一行只读退休观察。它是主机编译改动，不是硬件优化。ROB32普通-Os/低优化-O0全部29项、ROB64分文件-Os/低优化-O0的benchmark6/basic5共11项已逐项机器完全相同，证据`D:/CPU2026Proofs/windowearly_rob32_host_exact_20261002`、`windowearly_rob64_host_exact11_20261002`。ROB64低优化剩余simulator/边界仍在运行，不称已证明全部29项。

关闭合组并没有彻底解决单大函数的编译峰值：ROB64 Slow函数仍约17GB，PRF96热函数曾约19.5GB并使D盘降至约1.7GB。核验拟终止的PRF96编译进程时该函数已自行结束，实际未终止该任务，其后构建已完成。未通过缩小ROB/PRF或改变内存/计分来规避问题；后续大规模构建宜进一步细分生成函数。

## 剩余IPC瓶颈的直接观测

新`tools/observe_course_lsq_reasons.py`复用ROB32/PRF64/RS16/LSQ16/early1/RAT1已编译模型，低沿drive/eval后、memory.step/高沿前只读真实状态。每一活动周期重新计算并逐位断言真实eligibility叶节点及candidate完全一致，六项官方cycle/instret/结果不变。

| 程序 | 总周期 | LSQ非空无候选 | 其中同时有load等待返回 | 其中同时有load地址未ready | 其中同时有未知地址更老store阻塞load |
|---|---:|---:|---:|---:|---:|
| qsort | 166404 | 79517 | 32657 | 49711 | 9231 |
| rsort | 217460 | 109630 | 58524 | 61599 | 51855 |
| vvadd | 4637 | 2806 | 2693 | 212 | 57 |

类别重叠，不能相加作CPI归因，不能把所有“无候选”都当store地址问题。当前early1仅在rename基址已ready时提前发布地址，不是完整地址/数据分阶段AGU；rsort的后续基址就绪/未知store地址值得继续优化。vvadd更多仍在等待内存返回，窗口利用/并行访存需要同时考虑。证据`D:/CPU2026Diagnostics/windowearly_lsq_reasons_20261002/lsq_reasons_observation.json`。同模型Cache/内存流观测`axi_response_fifo2_windowearly_memory_flow_20261002`也完整通过六项身份检查；rsort入口背压34362周期、vvadd176周期，仍不是互斥CPI分解。

## 新真功能控制分组：尚未接入CPU

新增`rtl/cache/rv32_dcache_control_banks.v`，分别拥有valid/dirty/LRU状态与MSHR写数据状态，保留原写优先级、字节掩码与dirty无全局清零语义，不新增流水拍。使用真实有逻辑/状态的`keep_hierarchy`边界，不是标准单元空桩、whitebox冒名或导线别名；不代替真实Cache数据/标签SRAM。**尚未加入CPU filelist，当前整机没有启用它。**

10组16/64/1024行、ways1/2及合法16/32行分组、每组2000周期的四态状态对照全部通过，含写冲突、掩码和warm reset。原版SRAM检查、`synth -flatten`、默认ABC、原始五库及完整夹具SRAM STA全部通过，实际保留64个metadata组、4个MSHR数据组、4个真实16×8字节掩码宏；全部实际叶独立Decimal计价：

| 明确非CPU的隔离夹具 | 总面积 µm² | 最小周期 ns | 全夹具SRAM估计Fmax MHz |
|---|---:|---:|---:|
| 集中动态更新 | 2673.469864 | 6.484375 | 154.21686746987953 |
| 真功能局部分组 | 2943.958024 | 1.9404296875 | 515.3497735279316 |

夹具面积增加270.488160µm²，叶实例24949→29070；这是局部隔离试验，**绝不证明CPU达到300/500MHz，也不证明完整Cache协议或整机等价**。证据`D:/CPU2026Proofs/dcache_control_banks_course_20261002/report.json`。隔离状态顺序等价全部八组PROVEN，涵盖16/64/1024行、ways1/2及64行的16/32分组，合计10520个equiv、未证明0；1024行ways1/2分别3584/3072个。证明范围为任意输入下valid/dirty/LRU/MSHR-data状态与显式更新优先级参考一致，不冒称直接提取的完整Cache或整机证明。证据`D:/CPU2026Proofs/dcache_control_bank_state_equivalence_20261002/report.json`。

下一必要步骤是接入真实cache，完成所有原SRAM/哈希/预取/写回/背压/恢复协议验证和同源码开关整机29项对照，再做同配置完整面积/频率。面积、IPC和频率三项同时满足之前，目标保持未完成。
