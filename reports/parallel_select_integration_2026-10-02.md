# 并行数据选择与局部命令译码接入

目标保持同一整机配置：含全部SRAM的面积≤36000 µm²、授权六项IPC几何平均≥1.0985、包含SRAM时序的频率≥300 MHz。目标尚未完成，状态汇报不代表停止优化。

## 已接入的改动

- `RS_WAKE_MUX_IMPL`：共享唤醒tag比较，以一热选择替代串联数据mux；保留组合旁路选择最先命中lane、时序写入选择最后命中lane的既有语义。
- `RAT_READ_BYPASS`：直接读取RAT并转发同批内更早已接受的写者，保留RAW/WAW、前缀背压、恢复和提交释放行为。
- `DCACHE_LOCAL_ACTION_DECODE`：在拥有元数据状态的bank内部译码实际请求命令，保留更新边沿、优先级和全部SRAM。

三个参数默认关闭，从student_top经cpu_core传入实际实例。测量脚本 `tools/run_parallel_select_candidate.ps1` 显式开启三项，保留此前四发射、ROB64/PRF64/RS16/LSQ16、I128/D1024两路、银行ROB读写、Cache更新模式2及局部查询等全部配置。

四份模块RTL与已验证独立候选逐字一致。修改前七份主树文件及SHA256备份于 `F:/CPU2026Integration/parallel_select_20261002/baseline`。

## 候选证据

RS完整模块的四组无输入假设顺序等价全部通过，共18939个equiv点，其中实际四发射/16项/10唤醒端口配置11469点。独立完整RS面积10001.559240→8266.947480 µm²，频率76.807680768→84.265964450 MHz；两份网表已独立核验完整叶实例、原始库价格、源码及网表指纹。证据：`F:/CPU2026Proofs/rs_parallel_wakeup_formal_20261002`、`F:/CPU2026Probes/rs_parallel_wakeup_actual_20261002`。

重命名完整模块四组无输入假设等价全部通过，共3231点；独立实际模块面积643.342500→613.992960 µm²，频率251.597052→355.432142 MHz。证据：`F:/CPU2026Proofs/rename_read_bypass_formal_20261002`、`F:/CPU2026Probes/rename_read_bypass_actual_20261002`。

Cache显式局部译码模式1的720组协议全部通过，包含816228次活动元数据查询核对；独立完整Cache面积12723.483680→12752.716580 µm²，频率44.696639022→57.469974183 MHz，36个实际SRAM全部计价和时序。证据：`F:/CPU2026Proofs/dcache_local_action_decode_full_20261002`、`F:/CPU2026Probes/dcache_local_action_actual_cache_20261002`。

这些是模块证据，未作为新CPU的面积、IPC或频率成绩，也不构成全CPU形式等价证明。

## 整机测量

新构建、29项回归、完整面积、独立核价和全SRAM时序已由同一脚本启动，输出目录为 `F:/CPU2026Integration/r64p64rs16lsq16_robr1w1_dc2i1m1_rswake1_ratread1_action1_20261002integrated2b`。原生编译及29项回归已完成，六项IPC几何平均1.1213155347352615；逐项周期、退休数、退出码与上一冻结构建完全一致。对照文件 `baseline_comparison.json` 记录七个源码变化、三个新增参数以及源码/模型/原驱动/程序映像指纹。完整综合已完成prepare、正在map，面积和频率尚未完成。日志和继续工作状态位于 `F:/CPU2026Integration/parallel_select_20261002`。

首次 `integrated2` 启动因Windows PowerShell模块环境无法解析Get-FileHash而失败，未进入RTL测评；失败目录保留。`integrated2b` 使用已验证可用的PowerShell7，未修改RTL、编译参数或评测语义来绕过该主机环境问题。

上版冻结整机的完整成绩为54375.028734 µm²、IPC1.1213155347352615、39.679156818 MHz，29项全部通过，37个SRAM宏全部计价。详见[上版接入报告](banked_layout_integration_2026-10-02.md)。新结果完成前保留此基线，不扣除或相加独立模块收益。

## 已定位路径及后续验证

上版完整网表经过69个功能模块、470939个叶实例及全层级连线指纹核验，最差路径起点是frontend.head_reg[0]，终点是RS第8项src2_value_mem[25]。路径中 `_629422_/Y` 的延迟约14.504 ns，直接扇出1504个引脚；下游组合路径最终只到达RS的src2数据、tag及ready状态。诊断证据：`F:/CPU2026Diagnostics/integrated1_critical_identity_20261002/identity.json`，工具为 `tools/audit_full_timing_identity.py`。这些是物理连接与状态归属，尚不能单独证明某一个RTL条件就是全部延迟的根因。

独立RS候选 `F:/CPU2026Candidates/rs_static_allocation_20261002` 增加默认关闭的 `ALLOC_STATIC_WRITE`。它保留原槽位搜索、同拍分配、最高lane写优先级和全部状态，预译码逐行写入归属后并行选择完整payload。四组完整模块形式等价均已完成，共23827个等价点；实际16项配置14477点全部证明，未证明点为零。完整独立RS开关0/1 PPA已完成并独立核验：面积8245.602360→7654.660380 µm²，频率95.835283107→116.575591985 MHz。证据分别在 `F:/CPU2026Proofs/rs_static_allocation_formal_20261002` 和 `F:/CPU2026Probes/rs_static_allocation_actual_20261002`，尚未接入CPU。

Icarus的SystemVerilog解析发现该原型中的内部标识符 `matches` 与保留字冲突。可接入副本 `F:/CPU2026Candidates/rs_static_allocation_sv_20261003` 仅将六处该标识符改为 `allocation_match_bits`；反向文本替换精确还原原候选，记录在 `identifier_repair.json`。新副本在四组参数下，各8000周期的全部19个输出端口四态对照全部通过，包括实际RS16配置；每拍边沿前后比较，不屏蔽invalid payload。总计32000周期，实际16项覆盖5902次分配、2518次发射、459次flush和614次冲突重复唤醒。证据：`F:/CPU2026Proofs/rs_static_allocation_differential_v3_20261003`。此前两个解析失败的记录保留；原型PPA不冒充改名副本或CPU的实测。

PRF候选 `F:/CPU2026Candidates/prf_parallel_read_20261002` 增加默认关闭的 `READ_MUX_IMPL`，以逐字译码和并行旁路选择替代读取数据串联mux，保留P0、越界地址和最高lane写旁路优先级。BE1/P33、BE2/P48、BE4/P64、BE4/P96四组完整模块无输入假设等价全部通过，共8679个equiv点。实际四发射PRF64完整模块开关0/1 PPA已完成并独立核验：面积3299.147820→2628.088740 µm²，频率241.680434270→627.835683630 MHz，物理叶36218→25969，无实际SRAM。这是约20.34%面积下降的模块结果，尚未接入CPU；组件超过300MHz不代表整机达标。证据：`F:/CPU2026Proofs/prf_parallel_read_formal_20261002`、`F:/CPU2026Probes/prf_parallel_read_actual_20261002`。

Cache局部替换路候选720组协议、135980次victim选择和816228次活动元数据对照已全部通过；但完整组件PPA开关0/1的面积12786.556760→12886.196480 µm²、频率62.241672745→55.208108691 MHz，两份各36个真实SRAM网表已独立核验。面积与频率均变差，不接入这一候选。详见[局部替换路实验](cache_local_victim_2026-10-03.md)。

同源码RS16→8单参数测试已启动，由 `tools/run_window_tradeoff_candidate.ps1` 运行全部29项；保持ROB64/PRF64/LSQ16及所有其它有效参数。初始等待队列仅在确认没有工作子进程后被重新调度，与当前PPA并行，证据在 `rs8_queue_reschedule_20261003.json`。RS8六项IPC为1.066078324，低于Tier3的1.0985，因此不选它为当前达标配置；完整29项回归继续完成。RS12对照已排在RS8之后，等待实际结果选择窗口。主树43个编译输入在当前PPA与RS8/RS12测试完成前保持冻结；尚未把缩窗的预期面积下降当作新成绩。

下一轮五文件接入已在 `F:/CPU2026Candidates/static_datapath_integration_20261003` 准备完成，并通过实际全部CPU源码、原参数加两个新开关的Icarus完整展开。两个组件文件与上述已验证候选字节一致；top/core/backend仅增加默认关闭参数 `RS_ALLOC_STATIC_WRITE`、`PRF_READ_MUX_IMPL` 并传入真实实例。`staging_manifest.json` 保存43个原输入及新输入SHA、五文件差异和编译证据；主树43个编译输入未变。此阶段不是CPU仿真或PPA；后续运行脚本 `tools/run_static_datapath_candidate.ps1` 已备好，尚未启动。

RS静态写原型的剩余关键路径已在完整73875叶物理连线同一性验证后解析：输入 `alloc_valid_i[0]` 到 `src1_ready_mem[14]`。最大级 `_115462_/Y` 延迟4.311ns、直接扇出248，组合遍历也只到248个首个状态边界，属于第14项的payload和ready等字段；前级 `_115443_/Y` 直接扇出280、到297个状态位。证据：`F:/CPU2026Diagnostics/rs_static_allocation_20261003/identity.json` 和 `allocation_fanout_endpoints.json`。说明本项宽payload的控制负载仍很大；这只是冻结网表观察，不宣称已消除整机瓶颈。

## 2026-10-03 后续证据

原版RS16完整证明和使用共享逻辑的完整证明均已通过，分别位于 `F:/CPU2026Proofs/rs_static_allocation_formal_20261002` 和 `F:/CPU2026Proofs/rs_static_allocation_short_actual16_20261003`。原版直接SAT证明14477点；共享逻辑流程先证明13085点，再通过一步归纳补齐1392个metadata/tag输出点。所有冻结输入SHA再次核验。

常量读取化简的独立完整证明也通过相同14477点。它读取完全相同的原始prepared模型，以 `opt_expr -keepdc; opt_clean` 折叠常量地址读取，保留242个原架构状态名及位宽、所有端口，没有输入假设；原版/候选cell数从178337/17099降至61501/10407，两个直连状态输出在两边都归一为同一状态别名。证据 `F:/CPU2026Proofs/rs_static_allocation_normalized_actual16_20261003`，不会改变测量RTL或面积/时序流程。首次前置检查错误地要求已被原模型别名化的occupancy_reg名称，随后改为其真实保留名occupancy_o；首次失败日志保留，没有删除任何状态或输出。

新的独立年龄比较缓存原型位于 `F:/CPU2026Candidates/rs_age_order_matrix_20261003`。默认关闭AGE_ORDER_MATRIX，启用需ALLOC_STATIC_WRITE=1；它保留全部原age_mem与age_counter，在分配边沿维护每对槽位的原无符号年龄比较结果（16项新增120个派生bit），包括计数回绕和相同年龄按槽号优先的语义，不新增执行拍。六组全19输出四态对照累计48000周期通过，实际四发射/RS16/AGE32包含在内；AGE2/AGE3另外覆盖297/166次数字回绕。完整模块等价与实际组件开关PPA正在执行，尚未接入CPU、没有收益结论。

RS12同源码全部29项与独立配置核验已完成：IPC1.1232643380242247，相比RS16提高0.1738%，六项369979周期/472599退休。RS12静态分配完整模块10380点也已证明，输入SHA再次核验。独立源码目录已经启动RS12＋静态分配＋PRF并行读的整机原生构建/29项测试；同一build的完整CPU PPA随后在相同独立目录执行，保持五份原库、defaultABC、全部真实SRAM及完整时序。这样可保留仍在综合的旧主树43个输入；将来采用独立实现必须逐字匹配其实际测量来源。详见[RS容量取舍](rs_window_tradeoffs_2026-10-03.md)。

2026-10-03 02:15更新：上述独立整机29项已全部通过，`tools/audit_static_datapath_integration.py` 独立确认全部周期、退休数、退出码与RS12基线完全一致；五个RTL变化及新增RS_ALLOC_STATIC_WRITE=1、PRF_READ_MUX_IMPL=1之外的有效参数均一致。核验记录 `F:/CPU2026Integration/parallel_select_20261002/staged_rs12_native_audit.json`。首次完整PPA仅因隔离目录缺少官方框架Git元数据而在RTL综合前失败；真实固定提交checkout修复后，43个编译输入和149个评测依赖哈希仍全部相同，失败记录保留。`area_v2` 已完成展开、正在prepare；主树旧整机map及年龄比较缓存实际16项证明也仍在运行。Tier3目标保持active，汇报不等于暂停或完成。
