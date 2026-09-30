# 最新四发射配置完整面积审计

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
