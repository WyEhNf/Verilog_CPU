# Tier1/Tier2 与 Tier3 500 MHz 优化接续

起点：`88e460d38afbef4f74a7a30d1ced437d194d0937`，工作分支 `codex/tier-optimization`。本轮保留主树全部 Tier3 RTL，独立候选不能自动替代默认配置。用户原有未跟踪研究资料未改动。

## 接受门槛与工作顺序

| 配置 | 含 SRAM 最大面积 μm² | 六项 IPC 几何平均下限 | 频率下限 MHz | 累计分 |
|---|---:|---:|---:|---:|
| Tier1 | 9000 | 0.6000 | 300 | 90 |
| Tier2 | 18000 | 0.8450 | 300 | 95 |
| Tier3 | 36000 | 1.0985 | 300 | 100 |

先完成前两档，再完成默认测试配置的 500 MHz。目标3之前，接受的默认 Tier3 新版本还必须逐项不低于前一个接受版本的 IPC/频率、不增加面积。500 MHz 与其它门槛全部通过后，保留项目最终版本；IPC 1.5、1 GHz 及取消面积上限的进一步探索采用独立版本。

不按逐个编辑运行测试。先完成有明显结构/资源收益的候选批次，完整综合/STA 后判断是否继续一次六项 IPC；仅偶尔复用同一可执行文件检查一个小 correctness 程序，不自动运行完整正确性或参数扫描。一次失败的面积/时序门不会触发该候选的 CPU 构建或 IPC。

## 起点证据

历史冻结 A109：IPC `1.1152626918348099`、含 SRAM 面积 `35891.672317998215 μm²`、频率 `321.60804020100505 MHz`。原完整报告及失败候选保持只读。面积余量 `108.327682001785 μm²`；500 MHz 要把 `3.109375 ns` 最小周期降至 `2 ns`。这些是旧冻结硬件测量，不冒称为最新 warning-cleanup 源码的新 PPA。

已有最新提交的独立 baseline：`F:/CPU2026Sensitivity/88e460d3_20261008/results/baseline.json`。六官方 perf 答案通过，逐项周期与 A109 一致。当前主树与该 baseline 的 108 份 RTL/filelist/课程脚本/根头文件核对：107 份逐字一致，根 `rv32im_defs.vh` 只有 CRLF/LF 差异，规范化换行后逐字一致。baseline manifest SHA256：`f8115c05d2a41eb3ec4085b17c31b587a6abecb4aecb95e69fd90429b9806cd9`。本轮没有重跑 baseline。

同源码单参数已有记录：仅整数发射宽度 2→1 时 IPC `0.8949448224722484`；ROB32→16 为 `1.022329440536504`；Dcache1024→512 为 `1.0375680096302817`。只用这些记录指导减面积候选，不能相乘推算联合配置 IPC，不能借用默认配置面积/频率。

## 第一批独立候选

配置见 `configs/tier1.json`、`configs/tier2.json`。Tier1：FE1/BE1/issue1/CDB1、ROB8/PRF36/RS4/LSQ4、I64/D128、较小 MSHR/队列、双模方向预测。Tier2：FE2/BE2/issue2/CDB2、ROB16/PRF40/RS4/LSQ8、I128/D256、较小 MSHR/队列，保留混合方向预测。缓存仍是16字节行、两路，外部 RAM 仍256 MiB、原 AXI、latency10。

保留原乱序 backend、rename、ROB 连续有序提交、完整 RV32IM；没有选择顺序串行 backend。所有变化只在独立副本中替换顶层对应参数默认数字，其余 RTL 不改。两套配置均尚未获得全部三项指标，因此尚未宣布完成 Tier1/Tier2。

首轮 Tier1 课程综合输出 `F:/CPU2026TierRuns/tier1_compact_20261008`，manifest SHA256 `c7c109f1fe0f6b7afa0421d033323d4ea336b53fb9652ae152890c4579fb7bf6`。展开在 `rv32_branch_predictor.v:63` 拒绝不支持的8项 compact BTB；耗时501.13秒，未到综合映射、STA、面积报告或仿真阶段。原失败结果保持不动。准备配置时漏读16/32/64合法值是本轮配置错误，不是硬件指标回退。已改为最小合法16项，并在冻结工具里增加前置几何校验；没有改 RTL 的合法性检查。

修正后的唯一 Tier1 候选为 `F:/CPU2026TierRuns/tier1_compact_btb16_20261008`。继续使用原生 Windows Yosys0.63/固定 ABC/OpenSTA3.1/五份 ASAP7 RVT TT 与全部实际 FakeRAM；2 ns 映射目标，实际 Fmax 按原课程最低周期搜索。只有完整 PPA 通过才继续该候选的构建、六项 IPC 和一个小 correctness。

Tier2 副本 `F:/CPU2026TierRuns/tier2_compact_20261008` 的第一次完整综合/STA 已成功完成（784.990 秒），但面积门未通过：含 SRAM 面积 `19886.021862009184 μm²`，频率 `337.95379537953795 MHz`，超过面积上限 `1886.021862009184 μm²`。组合逻辑 `12285.06426000918`、时序逻辑 `4983.444`、SRAM `2617.513602000002 μm²`。manifest SHA256 `f6cad3acb2e780c9453f3fe862439d5d3ec7a29a63ac6143e115e384310bfbbe`，report SHA256 `acdd84e751b0b2c400e630a5a556a0ca6d0e6af81bcc88a3c8b36e5b5a2469a4`。未构建或运行 IPC/正确性，原结果保留。`tools/run_tier_candidate.py` 显式分阶段运行、拒绝覆盖已有阶段和源码，记录工具/库/源码/可执行文件身份；构建使用原官方 simulator 与原生 Verilator5.040，Windows time-zero host shim 保持原驱动不变。构建入口现在强制完整 PPA 通过，并核对报告身份。

修正后的 Tier1 完整综合/STA 已成功完成（649.658 秒），但面积门未通过：含 SRAM 面积 `12288.756519002882 μm²`，频率 `347.4720054292501 MHz`，最小周期 `2.8779296875 ns`。面积由组合逻辑 `7389.7272000028825`、时序逻辑 `3536.5248`、75个 SRAM 实例 `1362.5045189999983 μm²` 组成。manifest SHA256 `e1bec6a8eb8906ca17f459c482fa96938585f127dd9dd7ca44eaf4764de5a874`，report SHA256 `3aa0e358dae80b0ccc6f1e60d65c5984f92b3501e55349011e1d5804dac5c1e1`。超过面积上限 `3288.756519002882 μm²`，因此跳过该候选 CPU 构建、IPC 与 smoke；原结果保留。

只读网表检查发现 18,089 个显式控制反相器，合计约 `791.213 μm²`；此外 `keep` 控制消费者可能保留本可删除的上游状态/逻辑。展开前的 RS 大量 legacy 寄存器已被映射删除，不能把展开寄存器总数当作实际双份存储，更不能据此宣称面积收益。

## 500 MHz 路径依据

只读核对原 A109 完整网表及原五条最慢路径，未新增 STA。最慢路径数据到达约 `3.049 ns`：分支捕获 tag→ROB live/generation 查询→recovery→LSQ head/saved 身份选择→RS 物理唤醒/ready→lane1 issue payload→SUB 控制与算术→结果寄存器。另有 LSQ forwarding/request owner 至 selection payload 的约3 ns链。

因此，只改变时钟约束或独立 ALU 加法器不足以保证500 MHz。后续优先考察把身份比较/恢复资格与晚事件选择并行化，并同时处理 LSQ forwarding/request 的控制链；新增 issue 寄存级需要真实 IPC 改善补偿，不能带着 IPC 回退采用。之前准备的 A110/A111 没有完整测量，不继承 A109 数字，也没有直接覆盖主树。

## 小容量预测表源候选

在修正后的 Tier1 原综合进程 PID80820 仍存活时，完成独立的可选源码改进：顶层 `PREDICTOR_BHT_INDEX_BITS`、banked/scalar predictor 的 `BHT_INDEX_BITS` 支持6/7/8位索引（总64/128/256项，再按FE bank划分），默认8。原8位 prediction-time training metadata 保留；查询及反馈在各自 bank 消费完全相同的低索引位。双模表同步收窄；64项 chooser 与原混合预测 metadata 契约保留。历史长度必须适配实际 bank 位宽，冻结工具提前检查该条件。

默认8位下，原表项数256、索引宽8-bank、原PC切片[9:2+bank]及query/training切片[7:bank]完全还原。小表只改变预测资源/aliasing，执行阶段依旧检查原完整目标并恢复错误预测，ISA/ROB/AXI/时钟边沿无变化。单发射关闭hybrid时256→64项减少576个counter/trained状态位及相应更新/查询逻辑；尚未换算为面积或IPC收益。

该源码仅做审阅与 `git diff --check`，未开始第二轮HDL/形式/CPU仿真/综合/STA；没有改变当前正在测量的冻结源、工具或结果。初始Tier1/Tier2配置仍用256项，待原完整面积结果判断是否需要小表再组成下一批。源候选不是已验收的Tier3新硬件版本；历史 A109 的 PPA 不外推给新增参数后的当前源码。

## 面向紧凑配置的控制树策略

新增 `RV32IM_COMPACT_CONTROL_DEFAULT`（根和 RTL 头文件均默认0）与控制树 `COMPACT_CONTROL` 参数。默认0生成原显式反相树；可选1直接分发同值信号，由原课程综合器决定共享、扇出及删去未使用控制的上游逻辑。两种策略的组合值和时钟边沿一致，不改变队列、恢复或缓存协议。原仿真 `CPU2026_WORD_SIM` 的同值分发分支保持不变。面积与高扇出时序代价仍需实际 PPA 判断。

`configs/tier1_area_control.json` 保留首轮有效 Tier1 的队列/缓存容量，同时选择64项方向表和控制策略1，组成一次结构候选。冻结副本 `F:/CPU2026TierRuns/tier1_area_control_20261008` 来自提交 `69aa79abc04f43db32c8880bb67ef890c0893eda`，在Tier2首轮结束后顺序测量。完整综合/STA耗时604.033秒：含SRAM面积 `10281.746618999337 μm²`，频率 `130.9462915601023 MHz`，最小周期 `7.63671875 ns`。组合逻辑 `5576.339699999338`、时序逻辑 `3342.9024`、SRAM `1362.5045189999983 μm²`。manifest SHA256 `8e42449408bccddc1bce7e9238400d748f71237a349fa741ae7d266d5aef6b15`，report SHA256 `c0bbec9bf197f039f331c9ff77046858884ad5fec7d5429b55a2c1d503bfb029`。

面积下降 `2007.009900003545 μm²`（约16.3%）仍不足，而且频率显著不达标。最慢路径实际到达约7.571ns，多个门的负载107/122/126/211，单段延迟约0.5~1.2ns；显式控制缓冲确有必要。此候选拒绝采用，跳过构建、IPC、smoke，默认Tier3仍为策略0。没有把此PPA移植为默认CPU指标。

`configs/tier2_area_control.json` 保留首轮Tier2原全部队列/缓存/256项混合预测器，仅启用控制策略1。由于Tier1已经确认该全局策略严重恶化时序，不启动这个相同方向的Tier2实验。

## Micro OoO 候选

全局取消缓冲失败后，micro候选恢复原显式缓冲，保留rename/ROB/LSQ完整代际身份与原时钟边沿，集中缩减状态/仲裁规模：ROB8→4、RS4→2、D128→64、Dcache等待槽8→2、间接BTB16→4，继续64项方向表；AXI响应从双槽FIFO切到源码原有的单槽保留响应模式（深度参数0），读/写line容量仍2。I64/MSHRI2/MSHRD2、PRF36、LSQ4、FQ4/CPL4保持。配置 `configs/tier1_micro_ooo.json`，PPA结果见下；容量降低对IPC的影响不能由面积推算。

为该候选暴露 `DCACHE_WAITERS`，顶层/core均默认8并转发至原Dcache `WAITER_ENTRIES`；等待槽仅改变背压容量，旧路响应仍由原完整LSQ代际过滤。间接BTB扩展支持4/8项，原PC索引与8位折叠身份算法已按容量参数化，不改查询/训练配对或执行完整目标检查；每bank至少2行以防零宽索引，默认16项无变化。冻结前额外校验两侧非阻塞MSHR范围、合法总线line/word容量及响应模式。没有启用不支持的FIFO深度1或写line容量1，也没有以固定4KiB且会映射大寄存器阵列的旧阻塞Dcache替代当前FakeRAM配置。

Tier1 micro副本 `F:/CPU2026TierRuns/tier1_micro_ooo_20261008` 基于 `1dde728c`，manifest SHA256 `15c4fe0e49ccb79753a44e8abadffbfaacf7d05a2193918eaf25055679aa95a2`。完整综合/STA已完成，耗时691.522秒：含SRAM面积 `9278.840886999424 μm²`、频率 `347.35413839891453 MHz`。组合 `5601.825539999425`、时序 `2771.3664`、SRAM `905.648946999999 μm²`；report SHA256 `f9fe70a9481c289b8e29d1d7f7edf30c63e23040ecc7b8fc71e174e76cbccafe`。面积距上限仍差 `278.840886999424 μm²`，因此跳过构建、IPC和正确性。相比首轮有效单发射配置，面积减少约24.5%、频率约347MHz保持达标，但仍不宣称Tier1完成。

Tier2对应资源候选 `configs/tier2_micro_ooo.json`：保留ROB16/RS4/LSQ8和256项混合方向表，把间接BTB16→4、等待槽8→4、D256→128、PRF40→38（仍6个额外物理寄存器），响应FIFO改原单槽模式0。副本 `F:/CPU2026TierRuns/tier2_micro_ooo_20261008` 基于 `32154ce5`，manifest SHA256 `148d2e31dd2031f847ec97fc20d8d90d992194738e7546ebf0e7062d459b929d`。完整PPA耗时792.011秒，含SRAM面积 `17669.810534011292 μm²`、频率 `358.041958041958 MHz`、最小周期 `2.79296875 ns`；组合 `11407.464900011293`、时序 `4547.7936`、SRAM `1714.5520339999985 μm²`。report SHA256 `7e6c7315462f78775493d4c4c2d4e08dcc6243c23646fec4590b189be46e90d5`，PPA门通过。

该候选只构建一次（72.058秒），可执行文件SHA256 `415d289d1c5ef8b17b5734ddb4daba2e2f1180b7d512f6cf4959cf942a8b651e`；随后只跑一次六项官方perf（latency10、11.806秒），答案均通过，IPC几何平均 `0.7288260646252578`，低于0.845，不验收Tier2，不新增smoke。

| perf | 动态指令 | 周期 | IPC |
|---|---:|---:|---:|
| median | 6961 | 10642 | 0.654106371 |
| multiply | 21722 | 17953 | 1.209937058 |
| qsort | 139900 | 201187 | 0.695372961 |
| rsort | 195719 | 414579 | 0.472090965 |
| towers | 5278 | 5314 | 0.993225442 |
| vvadd | 4524 | 7789 | 0.580819104 |

与已存在的同源baseline相比，multiply仅慢约2.6%，rsort/vvadd明显受限；数据缓存容量是优先恢复方向，而不能为了面积继续一味缩小它。下批 `configs/tier2_balanced_memory.json` 在micro配置上恢复D256/PRF40，改I64/RS3/128项混合方向表，保持ROB16/LSQ8/FQ8及全部显式缓冲。RS已有的平衡rank/allocation树支持任意>=BE的行数，3行使用4叶树的一条常量填充叶；不是把非法槽当有效行。新配置尚未测量，不借用已有各单参数结果相乘预测联合IPC。默认Tier3仍未缩减上述资源。

Tier1下一批 `configs/tier1_micro_frontend.json` 在micro配置上把I64→32、FQ4→2，保留16行真实SRAM loop filter与原8项AXI word metadata queue，以免256MiB RAM latency10下额外限制总线在途字数。副本 `F:/CPU2026TierRuns/tier1_micro_frontend_20261008` 在Tier2 micro perf结束后顺序测量，manifest SHA256 `fee2f781954881455f35bd8f50c31ef42df7c2dc650e555633ead487895fb833`。完整PPA耗时577.328秒，含SRAM面积 `8641.614987999217 μm²`、频率 `352.9817304377801 MHz`、最小周期 `2.8330078125 ns`；组合 `5299.013519999216`、时序 `2608.9452`、SRAM `733.6562680000002 μm²`。report SHA256 `f42b6e2a26130ebab2e89b0669e89f83a767811117b8b7a58bd9be5ae4d56012`，PPA通过。

该Tier1只构建一次（42.372秒），可执行文件SHA256 `fbb36f44fd5b6b3de6aaa546f8eff62eb3df87b3405af843dba5aca8197d3d5b`，只跑一次六项官方perf（7.155秒，latency10），答案全通过，几何平均 `0.4275510094072113`，未达0.6000。因此未验收Tier1、不增加smoke，也不继续缩小关键容量。

| perf | 动态指令 | 周期 | IPC |
|---|---:|---:|---:|
| median | 6961 | 15997 | 0.435144090 |
| multiply | 21722 | 35848 | 0.605947333 |
| qsort | 139900 | 338907 | 0.412797611 |
| rsort | 195719 | 740634 | 0.264258730 |
| towers | 5278 | 9782 | 0.539562462 |
| vvadd | 4524 | 11494 | 0.393596659 |

这个结果改变后续方向：仅靠缩容量的单发射乱序候选仍不能同时达成三项门槛，需要减少后端流水/控制成本，为缓存与在途指令留出空间。已排除无效的completion depth缩减思路：当前 `COMPLETION_BYPASS=2` 已不存completion FIFO，改变深度不会提供期望的面积收益，因此不为它单独测试。Tier2 balanced副本 `F:/CPU2026TierRuns/tier2_balanced_memory_20261008` 在本次Tier1 perf结束后开始完整PPA，目前没有完整指标。

额外暴露已有 backend 的 `DISPATCH_PIPELINE` 到core/top，默认1还原此前hardcoded1，未启用直接分发。可选0必须同时关闭`DISPATCH_ELASTIC`，由冻结前校验拒绝矛盾组合。它只开放已有direct dispatch分支供后续容量与周期优化；这条分支也会关闭依赖弹性D包的fast-store shortcut，因此不能宣称性能自动改善。尚无直接分发候选测试，不改当前在测副本；默认Tier3保留原D pipeline和fast-store实现。

## Tier2 balanced PPA 与 Tier1 流水单发射候选

Tier2 balanced冻结源来自 `326142d4`，manifest SHA256 `420774aa713ef8ce634570bb9c3f6332a115dc5c375f171886d573abf2831c53`。完整PPA耗时815.657秒，面积 `17146.600825013506 μm²`、频率 `353.5911602209945 MHz`，组合 `10673.449380013504`、时序 `4199.6232`、SRAM `2273.528244999998 μm²`。report SHA256 `595fe7a028be42400368896a8af5243bd8150946bda883bfbed124e407724dba`。面积与频率门通过，一次构建67.696秒，可执行文件SHA256 `5cbdab2341af3a31002a3bda6fadff19b4d456b806c9b80b6205e9fa03d02181`；开始一次官方六项perf。

针对Tier1容量缩减后的IPC不足，新增 `rtl/backend/rv32_inorder_backend.v`，仅 `SERIAL_BACKEND=2` 启用；原0乱序及1串行后端保留。单发射按序读架构RF、发射与退休，4项完成队列允许独立ALU在旧load/MDU未完成时前进。每个源扫描按年龄排序的在途写者，最年轻匹配写者决定ready/value，覆盖WAW与RAW；ALU/MDU/load响应以完整valid/slot/generation身份匹配并旁路。分支结果在下一条分配前解决，重定向同边沿禁止分配，不取消更老load/MDU；因此没有已发射的更年轻工作需要回滚。

两项已提交store缓冲保留地址、原32位word、size及独立generation，接收ack后才回收，不依赖已复用的ROB身份。load等更老未提交store，且不能越过未发送store、同16B line的未完成store或MMIO；不同line普通load可以在旧store发送后继续。MMIO只在store缓冲最老行发送，halt等待缓冲排空；store字节mask与128位payload按原cache接口展开。该结构复用原ALU与32步共享迭代MDU，无ISA、FakeRAM或AXI时钟边沿替换。

冻结 `F:/CPU2026TierRuns/tier1_inorder_memory_20261008` 时修改尚在暂存区，manifest base为398bc837但每文件实际SHA均记录；保留该首份快照。第一次lint调用因PowerShell把未引用的 `-I.` 拆分而未进入HDL检查，修正为Python参数数组后lint退出0，但发现分支反馈经过alu_fire/cache-ready与frontend/predictor/epoch形成组合循环告警。分支不可能是load，故分支feedback/redirect直接使用已完整验证的alu_live与branch位，移除冗余内存ready依赖。没有对首份快照综合或CPU测试。

修正源码提交 `6125aff4` 后冻结 `F:/CPU2026TierRuns/tier1_inorder_memory_branchfix_20261008`，一次Verilator5.040原RTL lint退出0，无UNOPTFLAT、LATCH或Error。仍保留未使用执行输出和原参数宽度类告警；静态lint不代替功能验证。新profile用I64/FQ4/D256/MSHRD2/WAITERS4，FE1/BE1/ROB4；64项方向表、4项间接BTB与direct-target模式1，原OOO indexed-history模式2拒绝用于此后端。保留原前端response bypass/local PC/redirect request及Dcache word response，以避免串行模式1的禁用条件限制流水吞吐；默认0与原1的这些条件值保持相同。当前尚未综合、构建或测IPC。

Tier2 balanced随后只跑一次六项官方perf（11.793秒，latency10），答案全部通过，IPC几何平均 `0.770462340024059`，仍低于0.845。log SHA256 `95d756f686699e079a337e58bc79505e3dfd496566ad486cdf79c541a2f0bc07`。不验收Tier2、不新增smoke；没有把独立Dcache容量因素结果相乘作为该组合的达标证据。

| perf | 动态指令 | 周期 | IPC |
|---|---:|---:|---:|
| median | 6961 | 8777 | 0.793095591 |
| multiply | 21722 | 19135 | 1.135197282 |
| qsort | 139900 | 190952 | 0.732644853 |
| rsort | 195719 | 356183 | 0.549490009 |
| towers | 5278 | 5601 | 0.942331726 |
| vvadd | 4524 | 7387 | 0.612427237 |

该候选比D128 micro的geomean提高约5.7%，仍不足达标；剩余面积余量约853μm²，不能仅凭余量宣称D512可达。Tier1 inorder branchfix副本在这次perf完成后顺序开始完整PPA，保留默认Tier3原资源与执行路径。

下一项Tier2结构候选 `configs/tier2_direct_memory.json` 保留balanced的ROB16/PRF40/RS3/LSQ8、I64及128项方向表，改用已经存在的直接dispatch分支（PIPELINE0/ELASTIC0），移除两row×两lane、每lane约160bit+tag的D包及其选择/恢复逻辑，为D256→512留出面积。已有32bit零store字段及compact target等会被优化，不能直接把700个声明bit都换算为实际面积。该分支关闭依赖弹性D包的fast-store资格，因此store吞吐与ready/PRF链频率仍可能受损；不把状态减少或周期提前宣称为实测收益。未缩减ROB/物理寄存器/LSQ，也不全局取消控制缓冲。候选尚未综合或CPU测试，默认Tier3的PIPELINE1/ELASTIC1与D1024不变。

### 通用综合解析的默认标签修复

Tier1 branchfix完整综合在通用read_verilog阶段退出（233.964秒，manifest SHA256 `f17821ff64d01be295ed7e9d31a7b7f7a16c53eb371fdae0b573411f63dc92d2`，log SHA256 `3eaa58b0e05d1bd470e2da1a9002da27ba5a45a75ad653c5e74bd4776da658e9`），没有网表、面积或频率指标。新模块默认ROB4仍借用原ROB32标签默认16，触发其TAG_WIDTH==SW+11检查；top覆盖13是正确的，因此先前top级Verilator静态检查未发现这个通用默认实例问题。提交 `7283a8ef` 把新模块默认标签改为 `11+$clog2(ROB_ENTRIES)`，不改变top覆写的实际13位标签。

一次单模块Yosys read_verilog检查在缺少运行时PATH的直接shell调用中未加载工具（退出-1073741515，不是HDL错误）；配置与原runner相同的runtime/build PATH后，静态read_verilog退出0，只保留正常的数组到寄存器展开提示。未改变官方综合脚本或规避参数检查。

从7283a8ef冻结修正版 `F:/CPU2026TierRuns/tier1_inorder_memory_tagfix_20261008`，顺序重新开始完整PPA。旧branchfix结果原样保留，不重跑或覆盖它。先前未测的Tier2 direct副本也含错误模块默认值，因此不对其启动综合；从修正版另冻 `F:/CPU2026TierRuns/tier2_direct_memory_tagfix_20261008` 等待Tier1结束。默认Tier3所有架构参数与分支仍为原值；解析修复也确保新增但不使用的模块不会令默认课程综合提前退出。
