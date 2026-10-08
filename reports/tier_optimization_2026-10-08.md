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

## 流水后端首轮 PPA 与字段分散候选

Tier1 inorder tagfix完整PPA耗时542.349秒，manifest SHA256 `90e3943a5c3cf455ce7ecd7fb54c87bedf7250b49ae6a9f64a7775a25cb5174f`，report SHA256 `418acc914a5bcffcaff69c0c2a904f1769969afc63144abe266bedd48e4aeecc`。面积 `9705.712986999559 μm²`、频率 `190.54707852623744 MHz`；组合 `4952.89889999956`、时序 `2487.348`、SRAM `2265.466086999998 μm²`。两项PPA门均失败，跳过构建、IPC及smoke，不宣称该新架构性能达标。相比小容量OoO，D256提供更大真实SRAM，后端逻辑较少仍不足消除面积与控制时序代价。

原最慢STA路径从decode head selection进入新后端的数据选择，NOR3驱动124个负载、延迟约0.783ns，随后NOR2驱动340个负载、单段延迟约2.502ns。这是实际映射路径证据，不是根据声明FF数推测的瓶颈。没有额外重跑STA。

顺序测量Tier2 direct修正版（冻结7283a8ef，manifest SHA256 `00e63550530ea549c441ea87e26caa5a1db44fff896ef3409f1663440f9b4cab`），完整PPA耗时1657.298秒：面积 `19434.734685013675 μm²`、频率 `347.5899524779362 MHz`；组合 `11102.509620013672`、时序 `4274.2728`、SRAM `4057.9522650000026 μm²`。report SHA256 `e3443ee2ca6292719aff5303d69a9fa4aa0fa146d78e50d027a3d05b8d03552d`。频率通过但面积高1434.735μm²，跳过构建、IPC与smoke；去掉D包并没有为D512提供足够面积。未改默认Tier3的D包、资源或fast-store。

字段分散源码提交 `dc2e3bf3`，仅修改可选流水后端：架构RF改原频率域array read与分组写索引/使能、每row 16bit word owner；RF初始化valid同样分布至两字。ROB完成旁路和按年龄最后匹配源改原event_select优先选择，每个选择叶驱动16bit数据，最年轻写者的ready仍控制发射，未变WAW/RAW策略。ALU/MDU launch、源使用屏蔽、store结果选择分散控制。ROB结果与store address用word owner写入，store data复用该row的value字段（store不写架构寄存器），省去4×32bit独立store-word状态。转发top已有的SHIFT_SHARED_BARREL给新ALU，不改变默认OoO实例。所有执行响应仍由原完整代际资格检查后写入对应row。

新配置 `configs/tier1_inorder_banked.json` 保留D256、ROB4、31×32架构RF及两个独立代际store槽，改I32/FQ2/WAITERS2，减少前端和等待槽以配合字段控制开销；不缩D-cache、word queue或总线line容量。新模块单独Yosys通用解析退出0；从dc2e3bf3冻结 `F:/CPU2026TierRuns/tier1_inorder_banked_20261008`，一次Verilator5.040原RTL lint退出0，无Error/LATCH/UNOPTFLAT。Tier2 direct PPA完成后顺序开始该候选完整PPA，尚无面积、频率或IPC结果。不把改动的逻辑等值或存储声明缩减当作性能证明。

## Banked inorder PPA 门通过

`F:/CPU2026TierRuns/tier1_inorder_banked_20261008` 完整PPA完成，耗时485.435秒，manifest SHA256 `e97090a69808c12c66018c544887293d5972bea1d215e007d3c83f4a4ddbc325`、report SHA256 `18db45e9ab6dbe58c0cea5daea37564348575ac368a6dc065d0aeb7ecdbe4d39`。面积 `8872.458987999691 μm²`、频率 `355.18557058619496 MHz`；组合 `4524.625979999693`、时序 `2254.3596`、SRAM `2093.473407999998 μm²`。相对上一冻结版面积少约833.254μm²、频率190.55→355.19MHz；这批改动产生实际显著提升，PPA门通过。

该候选只构建一次，33.438秒，exe SHA256 `b8e8aac177951da4a175fd94a513190ce97ad9decaf08c296e1a74b42aad1259`；开始一次六项官方perf，尚不宣称IPC达标。

未测的PHYS_TAG_IMPL切换思路在只读核对后排除：backend已hardcode RS_PHYSICAL_WAKEUP=1，`g_owned_producer_tags`要求PHYS_TAG_IMPL0且RS_PHYSICAL_WAKEUP0，当前标签数组实际不生成；切换不能省下假设的40×TAG_WIDTH寄存器或读mux。没有为这个无效思路新建配置或运行测试。

### Tier1 验收

同一banked冻结源码只跑一次六项官方perf（latency10、2.766秒），所有答案通过，几何平均 `0.6048281090215314`，达0.6000。perf log SHA256 `cf77fd40590d9c8463f30b7d8f4cc34697906a627f7afdebba54a637b6a2374c`。随后只选一个小正确性样本correctness_array_test1，0.442秒通过，log SHA256 `b76d8cbe59d8294b63e53253252aa72c785c9a7bb10a5a8f964de346447a9ac4`。不跑完整正确性套件、不重复perf。

| perf | 官方指令数 | 实测周期 | IPC |
|---|---:|---:|---:|
| median | 6961 | 10402 | 0.669198231 |
| multiply | 21722 | 24170 | 0.898717418 |
| qsort | 139900 | 235209 | 0.594790165 |
| rsort | 195719 | 451540 | 0.433447757 |
| towers | 5278 | 8984 | 0.587488869 |
| vvadd | 4524 | 8418 | 0.537419815 |

指令分子来自未修改课程metrics.json，周期与答案来自原sim.cpp等待真实AXI exit写响应，不是用RTL debug_instret外推或假定退出周期。Tier1三项门通过，canonical configs/tier1.json选择该参数，旧初始OoO配置另存configs/tier1_initial_ooo.json。验收记录reports/Tier1_verified_2026-10-08.json保存完整阶段记录与source_commit dc2e3bf3。默认Tier3 top资源保持原值，当前只有Tier1完成验收，Tier2和500MHz仍未完成。


## Tier2 producer-map / early-load 候选

独立模块 `rv32_inorder_lookup_backend` 由已验收Tier1流水后端派生，使用SERIAL_BACKEND=3，未修改Tier1的mode2模块或默认Tier3的mode0执行结构。每个架构寄存器保留最年轻在途写者的完整代际标签；分配覆盖旧写者，退休仅在完整标签仍相等时清除。操作数查询读取有效位和ROB槽索引，再从物理完成row读取值，避免随ROB窗口增长的年龄旋转数据矩阵。查询依赖生命周期保证该槽仍属最年轻在途写者；ALU、MDU、load响应仍逐一检查完整slot/generation，未缩短响应资格检查。

合法load用已有simm12地址单元在分配边沿直接送同步TAG查询，不再经过ALU的一周期地址寄存器。这个模式要求BE1、启用缓存、TAG_SRAM1及WORD_RESPONSE1。store缓冲仲裁独立于新load地址；load仍等待较老ROB store、未发送store、同line未完成store及MMIO。满store缓冲在旧head完成回收边沿允许新退休store补位，ACK和新row仍使用各自完整代际身份。

`configs/tier2_inorder_lookup.json` 使用FE2/BE1/ROB8、I128/MSHRI4、D1024/MSHRD4/WAITERS8、FQ8、word queue16、AXI response FIFO2和256项方向表。更大的真实SRAM与在途容量，以及load地址提前，是这次候选的主要变化；尚无IPC或频率结论。

第一份冻结 `F:/CPU2026TierRuns/tier2_inorder_lookup_20261008`（b1080e98）top级lint退出0但有UNOPTFLAT：提前load的request valid仍结构依赖ALU memory ready，并与MMIO仲裁形成组合反馈；store选取与load阻塞共用always块也产生不必要的地址依赖。未启动综合、构建或CPU测试。修正提交29db9777：fast-load模式不存在ALU held-load，因此显式切除ALU ready到issue_enable的依赖；把store选取与load阻塞拆为独立组合过程。

修正版冻结 `F:/CPU2026TierRuns/tier2_inorder_lookup_isolated_20261008`，一次top级原RTL lint退出0，无Error或UNOPTFLAT。接着只开始一次完整官方PPA，尚无结果。保留初次有警告快照，不覆盖；未运行完整正确性套件。


Tier2 lookup isolated完整PPA结束，628.212秒，manifest SHA256 `5cc5b4042aeadef56ef6e001c27b511f0aee71123c838157aeae93a64fa1d09b`，report SHA256 `59b8523ec0034bae304ed4aa5e4b8c871ec3ed0e90ee25c2e025e861f908811c`。面积 `21421.329662000047 μm²`、频率 `256.19214410808104 MHz`，组合 `9145.202940000045`、时序 `4348.3392`、SRAM `7927.787522000003 μm²`。面积与频率均失败，跳过build/perf/smoke；未替代Tier1或默认Tier3。

实际STA首路径从Dcache metadata状态经过cache响应资格、ROB load旁路、架构producer查询、提前AGU，再经过core的泛用MMIO谓词到状态FF，数据到达约3.84ns。64个Dcache metadata bank合计面积3054.59748μm²；更大容量与在途资源的总逻辑成本超过先前预算，不能把新结构当作已经节省面积。后续候选需同时减少实际缓存/等待槽成本，并切断load数据到仅用于store的MMIO控制路径；此次失败不追加CPU测试。


下一批源码62242541与配置 `configs/tier2_inorder_store_control.json` 使用独立lookup后端。仅在SERIAL_BACKEND3且DCACHE_REQUEST_PIPELINE0时，core采用后端直接输出的MMIO退出谓词：候选已提交store、非halt/error、地址精确0x80000000、size生成四字节mask。这个谓词与泛用接口的valid/store/address/mask四项条件等价，但不读取提前load地址或load request valid。若使用已寄存request接口，仍以保存后的原payload资格判断。mode0/1/2路径与原谓词不变，Tier1模块未修改。

资源调整为D512/MSHRD2/WAITERS4、FQ4、word queue8、AXI response FIFO0、128项方向表，保留FE2/BE1/ROB8/I128/MSHRI4与提前load。D容量少于上次未达标候选，不能据此宣称IPC提升；它仍比已验收Tier1的D256更大。收益仅以新冻结副本实测确认，不能替换默认Tier3或验收记录。

冻结 `F:/CPU2026TierRuns/tier2_inorder_store_control_20261008`，一次top静态lint退出0，无Error、LATCH或UNOPTFLAT。顺序开始一次完整PPA，尚无结果；此前失败候选没有构建或CPU测试。


Store-control候选完整PPA一次完成：面积14488.819021999865μm²，频率304.49003865596194MHz，614.882秒，组合6804.340199999864、时序3282.5412、SRAM4401.937622000003μm²。manifest SHA256 d31b1296a716fa53ccfbf2d1eb60476189f2e02792d7fce06d53f63d538de42b；report SHA2564193a63345e5254f00641dfc5814608ff68501e3bde8b7ffc465a95264b50e35。PPA门通过，构建一次34.503秒，exe SHA2565da03a7ec58651f30c61a411aa8391ddbd41fc91de5d7d8084b08fead726ad42。

只跑一次六项官方perf，latency10、3.209秒，答案全部通过，geomean0.657438969856524，低于0.845。因此不验收Tier2、不跑smoke，不把PPA通过当作完整达标。perf log SHA256d0a19664fcbe11fdd1e7d329a5205f6bddeaa809429d4a4dba1e215459fd0571。

| perf | 官方指令数 | 实测周期 | IPC |
|---|---:|---:|---:|
| perf_median | 6961 | 10279 | 0.677205954 |
| perf_multiply | 21722 | 24062 | 0.902751226 |
| perf_qsort | 139900 | 206252 | 0.678296453 |
| perf_rsort | 195719 | 384399 | 0.509155851 |
| perf_towers | 5278 | 7911 | 0.667172292 |
| perf_vvadd | 4524 | 7892 | 0.573238723 |

该结果表明提前load与D512仍不足以在单发射方案满足IPC。此前提出的独立双发射后端方案尚未实现，已因用户明确的统一参数化CPU要求撤销。后续单双发射必须来自同一套参数化后端，按宽度派生资源、依赖检查与退休逻辑；不能为每个发射宽度维护独立CPU或复制整套后端。


## 用户明确的架构约束（2026-10-08）

用户要求实现参数化CPU，而不是给每一种发射建立独立实现。Tier1/2/3最终应由同一套CPU源码及宽度、容量、流水参数配置得到；允许参数化generate裁剪资源，不能以选择独立专用后端替代宽度参数化。现有新增inorder/lookup模块属于历史实验，仍需收敛到统一设计，不因此宣称最终架构要求已完成。Tier1冻结副本的PPA、六项perf和单个小正确性样本证据保持有效，但只证明那个历史候选的数值门槛，不能作为重构后的统一实现达标证据。默认Tier3的已知良好版本仍保留，统一后的变化需按显著改动批次验证。


## 统一后端入口与共享 PRF 存储参数

提交c65acfe8移除core的独立serial/inorder/lookup generate选择，以及课程编译清单中的三个独立backend模块。当前core只实例化rv32_backend_joint；保留SERIAL_BACKEND=0的兼容参数，非0在准备阶段和RTL初始检查中拒绝。历史独立实验文件、Git冻结标签与记录继续保存，但不属于活动CPU编译。canonical Tier1回到同一后端的micro frontend参数，历史IPC0.427551，尚不达标；未沿用独立inorder的数字作统一验收。默认Tier3仍配置原OoO资源与原FF PRF。

共享PRF新增PRF_VALUE_SRAM=0/1，0保留FF row，1在同一row模块内使用真正的1RW同步sram_fakeram DEPTH1/WIDTH32。每个非零物理寄存器只拥有一个RAM word；闲置行每拍读，当前写行的输出在该拍无效。共享的上一拍写回流保存每lane物理ID、32bit value与valid，对刚写的row按原最高lane优先规则旁路；下一拍该row若不再写，就已恢复同步RAM读结果。连续写同row、不同row、同拍多lane同row均保留同一优先规则。current WB到读口的原组合旁路仍保留；ready仍是FF并保持write优先于alloc、reset清零、P0恒零。未以FF模拟替换课程RAM，也没有改变1RW同步时钟语义。

这项存储参数支持BE1/2/4，不复制CPU或后端。已有WORD_SIM的PHYS56纯word存储只在VALUE_SRAM0走；启用SRAM时，仿真与综合均使用同一RAM接口/上一拍写回资格逻辑。另把已有STORE_ALLOC_EARLY_ADDRESS从core hardcode2暴露为参数，默认2；可选1使用单个PRF读后simm12地址单元，保持共享LSQ、完整generation与RAM/store资格。

候选configs/tier1_shared_sram.json启用PRF SRAM、直接dispatch PIPELINE0/ELASTIC0、STORE_ALLOC_EARLY_ADDRESS1、D256与LSQ2，其他来自同一OoO micro frontend配置，FE1/BE1/ROB4/PRF36/RS2/I32。减少dispatch层级及PRF状态，为更大D-cache留空间；LSQ容量缩减的代价与频率不能仅凭状态数量判断。冻结F:/CPU2026TierRuns/tier1_shared_sram_20261008，top静态lint一次退出0，无Error/LATCH/UNOPTFLAT；接着顺序启动一次完整PPA，尚无达标证据。默认Tier3的PRF_VALUE_SRAM0、PIPELINE1、LSQ16等保持原值，未启用本候选参数。

只读审查另排除两个无效假设：现有CHECKPOINT_IMPL1已移除整份RAT快照存储；LSQ store payload已经是相对访问的32bit，而非128bit。未为重复删除这些已不存在的开销新增测试。


共享D256候选完整PPA一次结束，579.101秒：面积10034.566642999973μm²、频率382.660687593423MHz，组合5614.335179999973、时序2279.7288、SRAM2140.5026629999993μm²。真实PRF SRAM为35个1x32实例，合计47.029255μm²，未漏计；ready/上一拍写回与选择逻辑仍计标准单元。manifest SHA256892c2939e83c80f0a78920d7c3d6f2f865a8f5c7848f0eecd53a49a03be2ac08，report SHA25608625a54eea12b8a71f1d4bc5e309af923cc0fb6845f7e48bb6080dcbc8d748a。面积高1034.567μm²，因此不构建、不测IPC、不跑smoke；频率较历史小OoO候选提高，但配置有多项变化，不能把提高归因于单一PRF参数。

后续Tier1配置configs/tier1_shared_sram_d128.json仅把未通过面积门的D256改为D128；它仍大于canonical旧micro frontend的D64，保持共享后端、直接dispatch和PRF SRAM。缩减的SRAM与metadata足以构成有实际面积意义的批次，IPC并未证明，不能取代达标验收。另准备configs/tier2_shared_sram.json：同一CPU/后端BE2，ROB8/PRF38/RS3/LSQ4/I64/D512、PRF SRAM和单个PRF读后AGU、direct dispatch，资源与宽度均为参数，没有双发射专用模块；这个Tier2候选尚未冻结或测试。


从51c47bb9冻结F:/CPU2026TierRuns/tier1_shared_sram_d128_20261008；准备阶段完成参数几何和文件哈希校验。仅改变缓存容量，没有再重复全top lint；D256的top lint已通过，D128走同一已支持的power-of-two metadata/tag分支。顺序开始一次完整PPA，仍未构建或测IPC。


## 共享 D128 候选结果与有限 PRF 样本

冻结51c47bb9的D128候选完整PPA通过：8622.194454999893μm²、372.3636363636364MHz；组合5216.898959999893、时序2167.7544、SRAM1237.5410950000007μm²。manifest SHA256 438c64a449258681005c695d818bf0c815e873b3df00a7771ea4ce763f0766e6，report SHA256 7d95589ac8a17f8eed5e0ca824feaba6b7772abcbe4a132820206c74ab4c2c38。PPA只执行一次；3409.095秒包含主机长时间暂停，不是重复综合。构建一次35.401秒，exe SHA256 5eac3ef83a03ddaee26c3277236a0edb2115e02a213e37a42d22bfb78fb63e79。

一次六项官方perf，latency10，5.027秒，所有答案通过，IPC几何平均0.4327925169129822，未达0.6000。周期分别15962/35126/314629/579826/13116/11213；perf log SHA256 9015fa4feae77fde59bb21b805d391187f91982e4d6d48ddc3bdc5652ffa7db5。与旧micro frontend相比几何均值仅略增，并有towers等单项回退，因此不验收，不切canonical，不追加CPU smoke。完整记录见Tier1_shared_sram_d128_2026-10-08.json。

PRF SRAM仅做一次小型定向样本，BE2/PHYS36，与同一PRF的FF存储逐观察比较ready及ready数据；原生同步RAM、不使用WORD_SIM。首次98次观察的C++激励没有实际覆盖所声称的同row多lane及连续写；已纠正激励，保留原源码/日志，不重建RTL，只重编译并链接C++。修正后24组/114次观察通过，覆盖最高lane优先、连续同/异row写、当前/上一拍旁路、空闲同步读、alloc与WB碰撞、reset/P0/越界。F:/CPU2026TierRuns/prf_sram_smoke_20261008/smoke_cover.log SHA256 dd084d87457c5691391b6f84ac66f3748a45e87b68682beee4e3dc2e5a78aed1。这个有限样本不能替代CPU整体正确性证明；没有跑完整套件。

## 共享直接分配信用优化（待测）

新增DIRECT_DISPATCH_CURRENT_CREDITS=0/1，默认0保留原路径。1只允许DISPATCH_PIPELINE0/ELASTIC0：没有D包占用的预留槽，ROB/RS/LSQ的occupancy均来自寄存状态，因此可用min(BE_WIDTH,capacity-occupancy)直接界定本拍实际分配，不必等待另一拍credit寄存器。新路径不预借同拍释放，不读allocator fire/ready；trace_ready和rename使用同一三组饱和信用，所有RS需求仍按每条一槽保守计数。reset/flush信用为零，branch busy仍阻塞原rename入口，PRF可用池信用不变。不同BE宽度使用同一计算，不增加专用CPU或backend。默认Tier3的开关0及DISPATCH_PIPELINE1保持原信用和数据通路。

configs/tier1_shared_current_credits.json只在D128共享候选上启用此项，保留全部缓存及ROB/PRF/RS/LSQ容量，避免把容量调整与信用收益混淆。准备进行一次静态检查及完整PPA；尚无性能达标结论。


从8850991f冻结F:/CPU2026TierRuns/tier1_shared_current_credits_20261008，manifest SHA256 1388d100c5e6aaaf1d77b985b6067af8c348f1dcaaf9f89f65390d5f971c9873。一次原RTL静态lint退出0，无Error/LATCH/UNOPTFLAT，5.321秒，日志SHA256 311abc68ff297ad93c8f02e587ade993e93b2dd6eb0b75635ddb465733b4c2fe；存在常量宽度等warning，其中新信用布尔localparam的integer声明产生一条WIDTHEXPAND，不能声称零warning。完整PPA已启动，尚无面积/频率结果；没有构建或性能测试。默认Tier3未启用此参数，统一Tier1/Tier2及500MHz目标仍未完成。


## 共享信用优化的完整测量

冻结8850991f只进行一次完整PPA，496.836秒，面积8650.406754999887μm²，Fmax377.99926172019195MHz；组合5245.9860599998865、时序2166.8796、SRAM1237.5410950000007μm²。report SHA256 8440f80f1a95989e55750392f338f8adfb91670857e26511ceca838ea0e9f422。相对共享D128候选，面积增加28.2123μm²、频率提高5.6356MHz，不能表述为所有指标改善或已验收。

PPA门通过后构建一次41.377秒，exe SHA256 267449662812413acdd72eb3e0e43e5747b24e60fc9486a4a77ceadf014bddea；只跑一次六项perf，latency10，5.645秒，答案全部通过。IPC几何平均0.5068602348369285，较相同容量的共享D128提高17.1139%，六项周期全部下降，但仍未达0.6000；不切换canonical，不跑CPU smoke，不重复perf。perf log SHA256 14f4c1c21298f0e87d68dcf5acabe24c424bae3f0573f31acc1cce33656c7018。完整阶段记录在Tier1_shared_current_credits_2026-10-08.json。

| perf | 官方指令数 | 实测周期 | IPC |
|---|---:|---:|---:|
| median | 6961 | 13930 | 0.499712850 |
| multiply | 21722 | 25004 | 0.868741001 |
| qsort | 139900 | 276589 | 0.505804642 |
| rsort | 195719 | 546367 | 0.358218926 |
| towers | 5278 | 11227 | 0.470116683 |
| vvadd | 4524 | 9866 | 0.458544496 |

## 保留共享数据通路的窗口扩容（待测）

configs/tier1_shared_window8.json保留FE1/BE1、INT1/CDB1、D128/I32双路cache、RS2、FQ2、直接分配/当前信用及真实同步PRF SRAM，仅ROB4→8、PHYS36→40、LSQ2→4。前一个候选释放信用滞后已经消除但IPC不足；增加重命名可用目的寄存器、两倍ROB/内存窗口，让更多独立操作跨越load等待，同时没有新增单发射专用实现。不是用每个参数的历史单因素数值乘出预测结果；真实面积、频率和IPC仍须同一冻结配置验证。此次扩容只属于未验收候选，不改变默认Tier3资源、参数或canonical Tier1。顺带把信用活跃常量改为布尔localparam，修复新WIDTHEXPAND，逻辑取值/时序不变；先前冻结副本不修改、不重测。


从cdd8c1f6冻结F:/CPU2026TierRuns/tier1_shared_window8_20261008，manifest SHA256 b1af2e70e8552f150011730a8100aa62cd7bb6dd76abd30fcc96900f0efa9d29。一次原RTL静态lint退出0，无Error/LATCH/UNOPTFLAT，7.025秒，日志SHA256 9a024c69895a2aeacc4f0d41e84085fb4dcedc674498949b85967552c4f0fa3c。原有参数宽度等warning仍在，新信用localparam的WIDTHEXPAND已消失，未声称全部零warning。已顺序启动一次完整PPA，当前仍在运行；未开始构建、perf或CPU smoke。所有已测结果保留各自源码身份，不将旧数值用于扩容候选验收。


## 窗口扩容面积失败，未进行 CPU 测试

共享window8候选完整PPA耗时636.567秒，面积9619.738227000465μm²、频率391.13827349121465MHz；组合6008.155560000463、时序2368.6668、SRAM1242.9158670000008μm²。report SHA256 613046ec44443a92588ff8a290fd3604e953bc4eb35ac46a5fbf519dcda647ec，log SHA256 cf456d45282b506fe5a9ad330cc2c56ebc36fb673cd17a86f3587b1715b06cd4。面积超过9000，因此跳过构建/perf/smoke，未替代任何验收配置。阶段记录在Tier1_shared_window8_2026-10-08.json。不能把额外队列的容量收益当作实测IPC，不能乘历史单因素结果作达标推断。

## 共享预读操作数与 ready-load RS 信用（待测）

DIRECT_LOAD_RS_CREDIT默认0，1只适用于当前信用、direct nonelastic dispatch及已启用allocation-edge load address。每个读口用共享RAT的当前映射和原PRF读网络在资源分配前预读；与之前相同的ready/WB旁路/真实SRAM值不变。每lane检查所有更早原始lane的非零rd写者；有同bundle RAW时，保守要求RS槽，实际rename仍按最年轻在途写者分配物理ID，原依赖循环强制其ready为false，等待正确物理写回。没有RAW的接受lane，其preview源ID与实际rename源ID一致，读值/地址完全相同。未使用的源及x0预读P0。

ready且无RAW的load在trace_ready/rename两处都不消耗RS信用，仍必须有ROB、LSQ和目的物理寄存器容量。实际LSQ地址有效与原load_without_agu仍控制资源和完成；Verilator边沿断言检查实际被接受且免RS信用的load必须具有权威分配地址。预读只读取寄存RAT和原PRF ready，没有读取rename_valid/alloc_fire，避免把分配资格反馈到预读。普通路径和默认Tier3都保持开关0。BE1/2/4都使用同一循环和同一CPU/backend，未引入宽度专用实现。

下一候选configs/tier1_shared_load_window8.json沿用新ROB8/PRF40，但LSQ保留已测credit候选的2槽。启用预读信用，保留I32/D128总cache容量；I/D采用已支持的单way几何，省去第二way的查询/端口/替换控制，为较大ROB留面积。它的关联度变化可能影响冲突，不能预先声称IPC提高或全指标不回退；只在完整同源码门槛和非回退证据成立后才会验收。此配置仍为未测候选，不切canonical、不改变默认Tier3资源。尚未冻结或测试。


从114b4dc5冻结F:/CPU2026TierRuns/tier1_shared_load_window8_20261008，manifest SHA256 4f44d9655ca75492fd3ac7446b221a10720216f32c460d5e7cf23f2b5c8fc89c。一次原RTL静态lint退出0，无Error/LATCH/UNOPTFLAT，9.797秒，日志SHA256 0056315212cbae3e5d8da550cf3c65f740cc14a85df92cbdb04244dce2f44ec5；有既存参数宽度/未用信号warning，不宣称零warning。接着顺序启动一次完整PPA，尚无面积/频率/IPC结论。已准备configs/tier2_shared_load_credit.json：共享FE2/BE2、ROB8/PRF38/RS3/LSQ4/I64/D512的未测SRAM候选加相同当前信用及预读开关，不另建双发射模块；该Tier2配置还未冻结/测试，等待Tier1当前阶段结束。


## 预读 / 单way窗口候选未通过 IPC 门

114b4dc5冻结的共享load-window8完整PPA一次完成，815.690秒：面积8878.268245000081μm²，Fmax369.009009009009MHz；组合5470.47432000008、时序2175.6276、SRAM1232.1663250000004μm²。report SHA256 ace9200741789d9c06e64cd5e92548bb9cbb543e6151d21eb0f2ad13b364933b，log SHA256 6d4c98bab3d49c2a81128a6cba4f0f9a4d2d91870cb746592b0d078f7edd8638。与已测current-credit小窗口候选相比，面积多227.86149μm²、频率少8.99025MHz，不能称为全指标改善。

PPA门通过后构建一次65.619秒，exe SHA256 729ea70140f157f29f47883eb4ba2d992b42e662d308a739293a75df888ae30b；一次六项官方perf，latency10、7.319秒，答案与分配断言全部通过，geomean0.4947168434105929。比同D容量双way/ROB4/current-credit的0.506860下降2.3958%，未达0.6000，所以不验收，不跑smoke，不重复perf。perf log SHA256 c64fb9a2b84fbabb3625b3e7b1b0d684f8ed791f84ca46372831223bd1e1249d。完整记录在Tier1_shared_load_window8_2026-10-08.json。

| perf | 官方指令数 | 实测周期 | IPC |
|---|---:|---:|---:|
| median | 6961 | 14738 | 0.472316461 |
| multiply | 21722 | 25156 | 0.863491811 |
| qsort | 139900 | 276243 | 0.506438172 |
| rsort | 195719 | 586871 | 0.333495777 |
| towers | 5278 | 11160 | 0.472939068 |
| vvadd | 4524 | 10053 | 0.450014921 |

这一批有容量、关联度与控制多项变化，不能把结果归因于单一项；大ROB没有在当前组合产生显著性能提升，小LSQ包含已退休但未ACK的store，也不能仅凭ROB容量推定更多独立load在途。只读检查另发现，历史独立Tier1配置选择PREDICTOR_DIRECT_BRANCH_TARGET1（PC索引），共享小OoO候选仍使用2（带历史的索引/metadata）；不能将历史独立架构的IPC直接用于共享后端。后续需检查小表预测及前端吞吐，同时保留当前最好的共享数值候选0.506860，失败候选不替代canonical或默认Tier3。

同属目标1的双发射共享配置configs/tier2_shared_load_credit.json保留双way I64/D512、LSQ4、RS3，比刚测Tier1有更大的缓存和内存窗口，来自同一114b4dc5后端及相同信用/预读算法。此前没有对这一统一双发射配置测量；在Tier1本批结束后顺序冻结并测一次完整PPA，避免依据不同配置的IPC推断它必然成功或失败。默认Tier3参数仍为原值；Tier1/Tier2及500MHz均未验收完成。
