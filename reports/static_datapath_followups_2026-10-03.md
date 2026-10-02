# RS12静态数据通路后续实验

目标仍为同一整机同时达到含全部SRAM总面积不超过36000µm²、授权六项IPC几何平均不低于1.0985、全SRAM频率不低于300MHz。当前尚未完成。主树保持原测量版本，独立整机的编译输入继续冻结供COMPLETION_BYPASS=2测量；以下独立模块原型均未接入CPU。

## 已完成的整机测量

| 同一配置的完整结果 | 全29项回归 | 六项IPC几何平均 | 总面积，含37个SRAM / µm² | 全SRAM频率 / MHz |
| --- | --- | --- | --- | --- |
| integrated1基线 | 通过 | 1.1213155347352615 | 54375.028734 | 39.67915681791762 |
| integrated2b并行选择 | 通过，周期相同 | 1.1213155347352615 | 52307.482674 | 39.38916028772551 |
| staged1 RS12、静态分配和PRF并行读 | 通过，周期与RS12基线相同 | 1.1232643380242247 | 49363.387014 | 32.57101052832469 |

三者面积均为原始五份ASAP7库的实际叶子面积加全部真实FakeRAM SRAM。频率包含所有SRAM边界，使用原始课程约束、理想时钟和无寄生模型，不是布局布线后频率。面积有所改善，频率仍远低于300MHz；staged1的面积收益伴随频率下降，不构成全面改善或Tier3达标。

staged1面积组成：组合30259.21536、时序11278.5048、SRAM7825.666854 µm²；410771个实际叶子，37个SRAM；最终网表SHA256为 `a5dd66eec1f4c6e752531b15cb624cf11cd3f5d4bfb434e3d9aee2653281db92`。面积已独立核验且43个当前编译输入无变化。首次时序因独立目录缺少OpenSTA可执行文件而失败，保留原日志；复制原OpenSTA 3.1.0的完全相同二进制并核验43个编译文件与149个测量依赖的并集189个文件无变化后，仅补跑已完成网表的完整时序。修复记录 `F:/CPU2026Candidates/static_datapath_integration_20261003/opensta_runtime_repair.json`，结果目录 `F:/CPU2026Integration/r64p64rs12lsq16_static_datapath_20261003staged1/area_v2`，最小周期30.7021484375ns。

staged1关键路径的实际物理连接与状态身份核对已完成，目录 `F:/CPU2026Diagnostics/staged_static_rs12_critical_identity_20261003`。重读的完整410771个叶子、69个功能模块的全部连接与原网表一致。起点寄存器在prepared模型中的信号别名为 `core.g_ooo_backend.backend.recovery_rs_branch_slot[5]`（RTL来源为branch_pending_tag的slot位），终点为 `core.g_cached_memory.g_nonblocking_icache.icache.if_resp_pc_o[28]`。`_411221_/Y` 驱动737个根模块输入负载，单门延迟约12.57ns；前级 `_407585_/Y` 和 `_405848_/Y` 分别驱动706、551个负载。

依赖追踪 `control_cones.json` 在真实寄存器、SRAM和功能层级端口处停止，不把层级端口当作零延迟组合穿越。三个门的下游分别到达3921、3921、8665个边界单元。第一门的下游包括I-cache响应/有效位、前端及后端的状态；这是物理组合依赖范围，不是某个RTL模块的独占面积或精确逻辑表达式归因。

## 整机直接完成模式

基线是独立目录 `F:/CPU2026Candidates/static_datapath_integration_20261003` 中已通过29项回归的ROB64/PRF64/RS12/LSQ16、静态RS分配及PRF并行读整机。只改变COMPLETION_BYPASS从默认0到2，其余RTL、参数、原驱动、程序映像与20cycle/word、256MiB内存约定不变。

全部29项回归已通过。IPC几何平均1.1232643380242247→1.1182750169703988，下降0.44418049%，仍超过1.0985；总周期369979→376386，退休472599不变。`tools/compare_course_source_tradeoff.py` 已核验全部29项，确认有效参数只有COMPLETION_BYPASS从0到2、43个编译来源完全相同、全部退出码和退休数相同；周期允许随本次结构改变而变化。审计输入哈希已再次验证，报告 `single_parameter_audit.json` 的SHA256为 `4352e5687b9afbb3184274e2ab24a1ef96fb63065e617d38bdd5dddb989270de`。同一构建的完整面积及全SRAM时序已于02:59启动，展开完成，正在综合准备阶段。不能使用以前小窗口直接完成模式的面积代替本次结果。

输出：`F:/CPU2026Integration/r64p64rs12lsq16_cdbmode2_static_datapath_20261003completion2`。新显式来源核验器已在既有RS16→12的29项完整结果上验证，记录 `F:/CPU2026Integration/parallel_select_20261002/explicit_source_auditor_rs12_validation.json`。

## Cache元数据分组大小

独立候选 `F:/CPU2026Candidates/dcache_metadata_geometry_20261003` 增加默认16的METADATA_GROUP_ROWS，仅改变STATIC_UPDATES=2的真实元数据状态分组，实际每组行数取该参数与CACHE_LINES的较小值。原元数据bank逻辑和实际数据/标签SRAM不变，模式0/1不变。实际完整Cache对照设定16→64行，其它参数固定。

24组冒烟与720组完整协议测试已全部通过，完整矩阵包含816228次活动查询索引及live metadata比较；原始四态SRAM、dirty/refill/hold/flush等检查全部保留。两份测试台额外断言参数确实传入实际Cache，以及真实bank行数和数量正确。完整输入哈希已独立重算核验，报告SHA256为 `f3d1dde7014a5ca584661d3f8180f55400fbf418b2b061bb0ee562c810a70994`。

协议证据：`F:/CPU2026Proofs/dcache_metadata_geometry_full_20261003`。完整组件PPA已在 `F:/CPU2026Probes/dcache_metadata_geometry_actual_20261003` 完成并独立核验，使用原五库/defaultABC、计入两者全部36个真实SRAM。16行分组为12752.716580µm²、57.46997418341004MHz；64行分组为12454.409780µm²、70.41188200508836MHz。组件面积减少298.306800µm²（2.3392%），频率提高22.5194%。证据 `independent_component_verification.json` 包含全部原始库价、物理叶子、层级及全SRAM时序核验；这些是完整Cache组件结果，尚无采用该参数的整机结果。

此前确认原队列仅在等待且没有工作子进程后，独立组件的内存余量改为6GB继续执行，完整CPU仍保持8GB；协议测试未重跑，RTL和测量流程未变，记录在候选的 `ppa_queue_reschedule.json`。

## RS实际数据寄存器分组

上一静态分配原型的关键路径显示，单项分配控制仍直接驱动248个负载。独立候选 `F:/CPU2026Candidates/rs_payload_banks_20261003` 增加默认关闭的ALLOC_PAYLOAD_BANKS，以实际拥有寄存器状态和局部lane选择的模块承载op、PC、ROB tag、物理目的号、两个源tag、store data、metadata及age；每组最多32位。保留原操作数唤醒、ready、valid、目标live和发射顺序，不增加执行拍。没有使用缓冲占位模块或替换真实SRAM。

候选基于已经验证的静态分配版本9dbf90f1，未混入年龄比较缓存。六组全19输出、每拍边沿前后四态比较共48000周期通过，包含实际四发射16项及短age回绕；不屏蔽invalid payload。报告SHA256为 `4ac0543862cf087ae8dad875a65821d2a25c2a5d2ba5282f7970e54b0d72ac70`，证据 `F:/CPU2026Proofs/rs_payload_banks_differential_20261003`。

完整模块等价流程正在执行七组配置，包含实际12项和16项。初版验证脚本提前重命名层级根模块，第二版hierarchy参数设置触发Yosys模块重名断言；改用项目既有chparam→hierarchy→rename-top顺序后正常展开。第三版opt_clean-purge清除了公共状态别名，剩余84点无法证明；第四版用普通opt_clean保留这些别名，第一组完整5315点已全部证明，前五组已通过、实际12项正在执行。各失败目录保留，候选RTL在此期间没有改变；没有删除等价义务或增加输入假设。

当前证明目录：`F:/CPU2026Proofs/rs_payload_banks_formal_v4_20261003`。所有证明通过后测量实际RS12的开关0/1完整组件PPA，再独立核价和核验时序。尚无CPU或组件PPA收益结论。

## 年龄比较缓存证明

原完整RS16证明于02:59因实际内存不足而明确暂缓，其约4.45GB内存用于已经通过回归的整机PPA；前五组证明及全部日志保留，未把尚未完成的实际16项证明标为通过。核验进程归属后停止原证明的三个自有进程，记录 `F:/CPU2026Integration/parallel_select_20261002/rs_age_original_proof_deferred_20261003.json`。这不是用户目标的暂停，原队列的后续PPA也尚未启动。

另一独立完整证明仍在运行：只为gold现有的120个年龄比较信号添加与gate派生状态相匹配的名字；删除所加名字后，模型JSON与原prepared模型完全一致，所有cell、连接、端口、状态和原名字不变。它继续证明完整模块及全部等价点，未增加输入假设；当前尚未完成。证据目录 `F:/CPU2026Proofs/rs_age_matrix_aliases_actual16_20261003`。不能把这项证明方法实验当作RTL优化收益。

## ROB完成写入并行选择

独立候选 `F:/CPU2026Candidates/rob_parallel_completion_v3_20261003` 基于原ROB SHA256 `3361098140ceadd09a2af9495fa05f866c7a51f2907513591fc0d083f3ec147f`，增加默认关闭的COMPLETION_PARALLEL_WRITE。按真实行解码存活代际和完成tag，最高匹配lane提供100位结果数据，所有匹配lane的异常标志仍累积。分支恢复保留范围、store ack、提交清除和重新分配的原写入优先级保持不变，不增加执行拍。

当前候选SHA256 `b53248f75ae46efc4b0d14f1d3ab7089213eb5ce46708997caf0aa603bdc783e`。48组原完整协议检查已通过，8组小容量/边界完整ROB等价证明正在运行；后者不等于实际ROB64的完整形式证明。六组全46输出端口、每拍边沿前后四态比较共48000周期通过，包含三种实际ROB64配置、重复完成tag、低优先lane异常、过时代际、分支恢复及两位代际回绕。实际ROB64每组都有超过4800次提交、400次重复tag事件；证据 `F:/CPU2026Proofs/rob_parallel_completion_differential_v4_20261003`。待全部证明通过及内存余量允许后测量实际完整ROB64组件，尚无收益结论，未接入CPU。

失败与修复均保留：首版准备目录因基线复制时换行字节不同而未通过身份断言。v2虽然48组协议和前六组形式证明通过，但无掩码差分在四发射ROB8第4105拍发现commit_valid不一致，因此终止其后续队列。诊断 `rob_parallel_completion_differential_20261003/diagnose_sensitivity.log` 显示第4104拍原版实时tag匹配为1，候选组合匹配仍为0；原因是连续赋值中的函数通过隐式内部状态读取行valid/generation，Icarus未按这些隐式依赖更新。v3显式引用两项状态后消除该差异。第一轮v3实际ROB64跑完8000周期无差异，但随机分配空洞使提交/重复tag覆盖不足，因此保留该失败并改进激励：每128拍前3/4采用合法连续分配，末1/4继续任意输入组合，比较项和覆盖下限均未减少。

## 前端响应同拍链式请求权衡

独立整机来源 `F:/CPU2026Candidates/frontend_chain_tradeoff_20261003` 仅在frontend、cpu_core、student_top三个文件增加默认开启的FRONTEND_RESPONSE_CHAINING参数，关闭时等待已经注册的下一PC再发起请求。依据是已验证的恢复控制→前端响应/预测→I-cache关键路径；该实验用于测量切断响应到请求的同拍依赖所付出的IPC代价，不预先声称频率提高。

其余43个编译输入中的40个文件及基线参数保持与staged1完全相同，RS12/静态分配/PRF并行读仍开启，COMPLETION_BYPASS保持0。未混入Cache64行分组、RS payload bank或ROB完成写入原型。正在使用原驱动和原内存约定构建并执行29项完整原生测试，输出 `F:/CPU2026Integration/r64p64rs12lsq16_frontend_chain0_static_datapath_20261003`。当前尚无IPC和整机PPA结论。
