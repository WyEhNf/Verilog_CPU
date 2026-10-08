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

Tier2 副本 `F:/CPU2026TierRuns/tier2_compact_20261008` 已冻结，尚未开始综合、仿真、正确性或 IPC。`tools/run_tier_candidate.py` 显式分阶段运行、拒绝覆盖已有阶段和源码，记录工具/库/源码/可执行文件身份；构建使用原官方 simulator 与原生 Verilator5.040，Windows time-zero host shim 保持原驱动不变。

## 500 MHz 路径依据

只读核对原 A109 完整网表及原五条最慢路径，未新增 STA。最慢路径数据到达约 `3.049 ns`：分支捕获 tag→ROB live/generation 查询→recovery→LSQ head/saved 身份选择→RS 物理唤醒/ready→lane1 issue payload→SUB 控制与算术→结果寄存器。另有 LSQ forwarding/request owner 至 selection payload 的约3 ns链。

因此，只改变时钟约束或独立 ALU 加法器不足以保证500 MHz。后续优先考察把身份比较/恢复资格与晚事件选择并行化，并同时处理 LSQ forwarding/request 的控制链；新增 issue 寄存级需要真实 IPC 改善补偿，不能带着 IPC 回退采用。之前准备的 A110/A111 没有完整测量，不继承 A109 数字，也没有直接覆盖主树。

## 小容量预测表源候选

在修正后的 Tier1 原综合进程 PID80820 仍存活时，完成独立的可选源码改进：顶层 `PREDICTOR_BHT_INDEX_BITS`、banked/scalar predictor 的 `BHT_INDEX_BITS` 支持6/7/8位索引（总64/128/256项，再按FE bank划分），默认8。原8位 prediction-time training metadata 保留；查询及反馈在各自 bank 消费完全相同的低索引位。双模表同步收窄；64项 chooser 与原混合预测 metadata 契约保留。历史长度必须适配实际 bank 位宽，冻结工具提前检查该条件。

默认8位下，原表项数256、索引宽8-bank、原PC切片[9:2+bank]及query/training切片[7:bank]完全还原。小表只改变预测资源/aliasing，执行阶段依旧检查原完整目标并恢复错误预测，ISA/ROB/AXI/时钟边沿无变化。单发射关闭hybrid时256→64项减少576个counter/trained状态位及相应更新/查询逻辑；尚未换算为面积或IPC收益。

该源码仅做审阅与 `git diff --check`，未开始第二轮HDL/形式/CPU仿真/综合/STA；没有改变当前正在测量的冻结源、工具或结果。初始Tier1/Tier2配置仍用256项，待原完整面积结果判断是否需要小表再组成下一批。源候选不是已验收的Tier3新硬件版本；历史 A109 的 PPA 不外推给新增参数后的当前源码。
