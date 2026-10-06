# 条件分支方向与BTB目标解耦实验

**后续源码与统计口径更正（2026-10-01）**：工作树随后新增可选模式2的索引随指令携带/投机历史恢复，见 `reports/indexed_history_predictor_2026-10-01.md`。本报告的模式1完整面积/频率属于此前冻结快照，不能称为后续工作树零差异PPA。下面预测事件的准确含义是 **ALU接受的分支解析反馈**，不是ROB退休；旧模式反馈也没有模式2新增的完整ROB代际有效性过滤。历史“提交训练/提交预测错误”表述错误，本文更正，不改变原始cycle、instret或IPC数据。

**同一完整网表时序已完成**：最小周期45.986328125 ns、全部SRAM参与/遗漏0，OpenSTA3.1/原版ns-fF约束、理想时钟/无寄生估计Fmax **21.745593544277 MHz**、2 ns目标setup slack -43.986233 ns。完整成绩 **45,918.264234 µm² / IPC0.9567514009772996 / 21.745593544277 MHz**，与上述网表/冻结源码/参数严格配对。相对旧预测器FIFO候选面积更大、频率更低、IPC仅小升，所以保持源码默认新预测器开关0，未将该模式作为已达标或明显优越的最终选择。后文“频率运行中”记录先前状态，以此为准。

**当前源码完整面积已完成（09:43）**：四发射新预测器1/FIFO0/store接收0、TAG1/I128/ROB32/PRF48/RS8/LSQ8/D1024、AXI16/8/64。组合27,506.059380、时序10,586.538000、全部37个实际SRAM宏7,825.666854，总面积 **45,918.264234 µm²**；381,567个计价叶实例、未计价/未展开0、最终check0、独立--require-current VERIFIED、当前输入差异0。相对旧FIFO/旧预测器面积45,793.940574增加124.323660 µm²，不能宣称面积减少；IPC小升0.0981434563%。全SRAM STA尚在运行，网表SHA `3c06b92b4503b67241796a2d53ca95fdd42109eaf188fa7a554c08b0dd383e1b`，证据 `D:/CPU2026AreaAudits/direct_branch_fifo_tagbanks_i128_r32p48rs8_standard_20261001`。后文主候选“面积运行中”为当时历史状态，以此为准；小AXI队列面积仍独立运行。

新增 `PREDICTOR_DIRECT_BRANCH_TARGET=0`，经student_top/cpu_core/banked predictor传到各bank的 `DIRECT_BRANCH_TARGET`。默认0保留旧模式。

模式1让条件分支目标始终来自真实取到的RV32指令 `PC+decoded B-immediate`。每个BHT行增加trained位，冷行保留BTFNT；经过解析反馈训练的行直接使用原2-bit饱和计数器方向，不再要求条件分支命中BTB。条件分支不分配BTB，BTB留给JALR；JAL、JALR最低位清零、valid/tag防护和解析反馈训练规则不变。本节模式1仍是256行bimodal/64行BTB，而非gshare；后续模式2另行记录。FE1/2/4的bank使用不同PC低位，表容量没有按lane复制。

## 验证

一键功能复现 `& tools/test_direct_branch_predictor.ps1`，完整旧模式等价另用 `python tools/test_predictor_legacy_equivalence.py --baseline D:/CPU2026AreaAudits/rob_parallel_tagbanks_i128_r32p48rs8_standard_20261001/source_snapshot/rtl/predictor/rv32_branch_predictor.v --outdir D:/CPU2026Proofs/NEW_PREDICTOR_PROOF`。

- `rv32_direct_branch_predictor_tb` 的BANK_BITS0/1/2全部通过：冷前向/后向、训练后方向独立BTB、错误反馈target不能覆盖指令target、条件分支与JALR碰撞、训练后的后向不跳、条件分支不挤掉间接目标、JAL与无效查询、warm reset和invalid payload X注入。
- 扩展原bank路由TB，模式0/1×FE1/2/4共6组，每组4000周期与各lane完整独立表参考逐输出/计数对照，全部通过，含行尾无效lane与PC溢出边界。
- `tools/test_predictor_legacy_equivalence.py` 对两份完整冻结模块，旧模式0×BANK_BITS0/1/2的完整顺序等价全部PROVEN、未证明0。证据 `D:/CPU2026Proofs/predictor_legacy_20261001`，含输入/脚本/日志指纹和源码快照。新模式改变预测行为，不声明逐周期等价。
- `make a02 lint unit matrix b08 b09`通过，日志 `build/direct_branch_legacy_regression_20261001.log`。
- 官方AXI整机构建 `D:/CPU2026Builds/direct_branch_fifo_tagbanks_i128_r32p48rs8_20261001`，新模式1、FIFO完成0/store接收0，TAG1/I128/PRF48/RS8，四发射ROB32/LSQ8/D1024；benchmark6/6、basic5/5、simulator17/17及256MiB边界全部通过，pi冻结。

## 严格IPC与只读诊断

| benchmark | 原模式周期 | 新模式周期 | 退休数 | 原/新解析反馈预测错误事件 |
|---|---:|---:|---:|---:|
| median | 10906 | 10906 | 7062 | 490 / 490 |
| multiply | 12170 | 12170 | 27637 | 105 / 105 |
| qsort | 169012 | 168995 | 139606 | 10350 / 10330 |
| rsort | 224250 | 224169 | 289966 | 2093 / 2086 |
| towers | 5731 | 5700 | 3803 | 72 / 71 |
| vvadd | 6185 | 6185 | 4525 | 2 / 2 |

六项总周期428125、退休472599，IPC GEOMEAN **0.9567514009772996**，相对0.9558133327368818仅 **+0.0981434563%**。累计IPC1.1038808759不是评分用几何平均，不能宣布达到Tier3的1.0985。

预测事件来自 `tools/observe_course_perf.py --branch-stats`：只在原版最终top.final()之后读已有RTL计数器，链接冻结模型对象而非改RTL/运行时行为，逐项cycle/ret/result与严格原报告精确相同。该数是ALU接受的解析反馈prediction_count-correct_count，可能包含错误路径事件，不是退休分支统计；预测正确要求方向相同且taken目标一致。qsort新模式35689/46019，约77.6%，仍有10330次解析反馈预测错误，不能声称解决IPC瓶颈。计数类别存在重叠，不相加归因。

原始诊断在 `D:/CPU2026Tests/direct_branch_20261001/perf_{baseline,branch}/perf_observation.json`，均保留新helper快照和输入/对象/驱动/可执行文件指纹。旧counter-only诊断仍是其当时版本，不因helper扩展就重写其历史数据。

各suite报告 `build/cpu2026/direct_branch_fifo_tagbanks_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001.json`；新模式完整默认ABC面积正在 `D:/CPU2026AreaAudits/direct_branch_fifo_tagbanks_i128_r32p48rs8_standard_20261001` 对不可变完整输入快照综合。面积/全SRAM频率未完成，不用旧FIFO或模式2数字替代。Tier3尚未达标。

## 单参数请求寄存级对照：未选用

同一源码和上述参数，仅 `DCACHE_REQUEST_PIPELINE=1`，冻结构建 `D:/CPU2026Builds/direct_branch_dreqpipe_fifo_tagbanks_i128_r32p48rs8_20261001`。benchmark6/6、basic5/5、simulator17/17及256MiB边界通过；已有非fall-through弹性stage保留分支恢复边沿已接收的store/幸存load，不把请求丢弃来换统计改善。

六项周期11331/12283/179401/233294/5883/6375，退休数逐项与上表相同，总周期448567/退休472599，IPC GEOMEAN **0.9240009563430192**，较无请求stage的0.9567514009772996下降 **3.42308823%**，故不选用。没有该变体的完整面积或频率；不能因为寄存了请求就声称全CPU已提频，更不能借用另两份网表Fmax。各suite报告 `build/cpu2026/direct_branch_dreqpipe_fifo_tagbanks_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001.json`。

## AXI队列联合容量候选：待面积核验

**后续完成结果**：该冻结候选完整默认ABC及独立原库Decimal VERIFIED：组合26,851.883940＋时序9,831.294000＋全部实际SRAM7,825.666854＝**44,508.844794 µm²**；370772计价叶实例/37宏，未计价/未展开0，最终check0。同网表全SRAM STA Fmax **26.01890436019921 MHz**、38.43359375 ns、2 ns目标slack -36.433144 ns；网表SHA `e99a4cce0d6b982e2d6cd12a359d6d9b7a835a0e5b4086d6a924dde1ba412b50`。面积较本报告大AXI基线减少 **1,409.419440 µm²**，其中组合654.175440、时序755.244000，SRAM不变；IPC仅降0.0492097892%。这属于当时模式1快照，与后续历史预测器源码有6个RTL差异，不冒称当前模式2的PPA。

`tools/audit_sequential_ownership.py` 的同网表寄存器归属诊断显示AXI适配器FF-only面积758.743200（2602 FF），大队列1513.404000（5190 FF）；这不是整个适配器面积，不能将诊断中的各模块FF面积当成模块组合+时序总面积。

在同一当前源码、同一新预测器/FIFO/store接收0/无D-request级基线上，仅联合覆盖READ_LINES16→8、WRITE_LINES8→4、WORD_QUEUE64→16，核心/Cache/MSHR/内存平台不变。平台共享AXI FIFO仍16、20cycle/word，256MiB RAM未改；这是CPU内部适配器容量扫描，不是增加外部带宽或更换评分模型。

冻结构建 `D:/CPU2026Builds/direct_branch_bus8w4q16_fifo_tagbanks_i128_r32p48rs8_20261001`，6/5/17/边界全部通过，pi冻结；六项周期10929/12173/169057/224174/5692/6195，退休逐项不变，总周期428220/退休472599，IPC GEOMEAN **0.9562805856296562**，相对大队列0.9567514009772996仅下降 **0.0492097892%**。因联合改变三个队列参数，不能把结果拆成单项收益或宣布容量收益已经相加验证。

正式完整面积开始运行于 `D:/CPU2026AreaAudits/direct_branch_bus8w4q16_fifo_tagbanks_i128_r32p48rs8_standard_20261001`，所有输入已按冻结构建核验并复制快照。未完成前不宣称面积减少，不用当前大队列或模式2结果估算；Fmax也必须同一新网表完整STA。报告 `build/cpu2026/direct_branch_bus8w4q16_fifo_tagbanks_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001.json`。
