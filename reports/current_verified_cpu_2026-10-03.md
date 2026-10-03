# 当前整机验证与优化进度

最新已采用版本：2026-10-03 的 8 级组合配置。以下新增状态覆盖本文后面的 11:44 历史快照；固定比较基准仍是合法 ADDI 修复版，没有滚动更换基准。

| 最新组合配置 | 实测 | 相对固定基准 |
| --- | ---: | ---: |
| 频率 | 53.439098 MHz | 300 MHz 目标尚未达到 |
| 总面积（包含 37 个 SRAM） | 46298.423154 µm² | −1.0503% |
| 六项 IPC 几何平均 | 1.0087820702582486 | −9.7912% |

53 项整机原生用例全部通过；最新配置和测量使用的 43 项源码输入一致。实际采用参数以[组合配置档案](E:/Verilog_cpu/build/cpu2026/verified_frequency_combined_profile_20261003.json)为准，并非所有可选流水参数的默认值都开启。完整结果见[整机测量](F:/CPU2026Integration/frequency_combined_v2_20261003/verified_cpu_result.json)，采用记录见[工作区同步记录](F:/CPU2026Candidates/frequency_combined_main_backup_20261003/adoption.json)。面积与 IPC 的 ±10% 约束通过，Tier 3 尚未达到。

本次已对同一冻结网表提取 37,523 个有约束且有可达路径的终点，每个终点保留最差 setup 路径；按耗时排序后归为 368 类终点字段。最慢路径是 LSQ 头指针到地址状态写入，18.646686 ns；分支恢复到 RS 操作数为 18.391958 ns，Icache 同周期请求链为 16.112240 ns。共有 35,662 条终点最差路径在 300 MHz 下不满足 setup。此次仅作时序诊断，没有修改 RTL。

详见[逐路径清单与修改建议](E:/Verilog_cpu/reports/frequency_path_checklist_2026-10-03.html)、[文字报告](E:/Verilog_cpu/reports/frequency_path_checklist_2026-10-03.md)及[检查记录](F:/CPU2026Proofs/frequency_combined_paths_20261003/report_audit.json)。频率是综合后理想时钟估计，无布局布线寄生。

## 11:44 历史快照（下文“当前主版本”指当时版本）

更新时间：2026-10-03T11:44:47+08:00（Asia/Shanghai）。目标继续执行，**Tier 3 尚未达到**；结果汇报不暂停目标。原始要求已保存为[目标文件](E:/Verilog_cpu/docs/goal-objective_2026-10-02.md)与[项目要求](E:/Verilog_cpu/docs/final_project_requirements.md)。

当前主版本保留已验证的 ADDI255 修复。合法 `ADDI a0,zero,255` 在缓存行末触发旧哨兵停顿的问题已修复；39组前端/预测器协议、原29项整机回归、新增8个指令位置用例，以及16个独立解释器给定期望值的RV32IM程序全部通过。有限测试不等于完整ISA证明。

| 同一主版本构建 | 实测 | Tier 3要求 | 结果 |
| --- | ---: | ---: | --- |
| 六项IPC几何平均 | 1.1182750169703988 | ≥1.0985 | 达标 |
| 总面积，包含全部37个SRAM | 46789.856634 µm² | ≤36000 µm² | 未达标 |
| 包含全部SRAM的频率 | 33.05144922858434 MHz | ≥300 MHz | 未达标 |

面积组成：组合28098.00738、时序10866.1824、SRAM7825.666854 µm²；共382390个物理叶子。周期30.255859375 ns。面积仍需下降约23.06%，频率需达到当前约9.08倍，不能称为三项都已接近标准。

[主版本参数档案](E:/Verilog_cpu/build/cpu2026/verified_legal_addi_profile_20261003.json)绑定全部43份编译输入。配置为ROB64、PRF64、RS12、LSQ16、FE4/BE4、整数发射4、CDB宽度4、COMPLETION_BYPASS=2；其他参数以档案为准。[完整整机结果](F:/CPU2026Integration/r64p64rs12lsq16_cdb2_legal_addi_fix_20261003/verified_cpu_result.json)的网表SHA256为 `9e201fa0ed4506dfd18035e10cba9cd5b0a9eb5d325ab2c6d4c06d084ff08948`。

计分程序为median、multiply、qsort、rsort、towers、vvadd；主版本周期分别10048、11969、161195、184298、4925、3951，共376386周期、472599条退休指令。Pi按既有授权冻结。测量沿用课程revision `54fc150ffc290f52aa024209ffb9a29d43856f6d`、五份原始ASAP7 RVT TT库、默认ABC、原FakeRAM验证器及模型。原sim.cpp只增加只读退休计数打印；256 MiB RAM、20 cycle/word、32位共享AXI4-Lite及MMIO B握手退出保持不变。频率是综合后理想时钟、无寄生估计，不是布局布线结果。

新完成的整机对比：

| 修复版候选 | 总面积/µm² | 六项IPC | 完整SRAM频率/MHz | 决定 |
| --- | ---: | ---: | ---: | --- |
| 当前主版本 | 46789.856634 | 1.1182750169703988 | 33.051449229 | 保留 |
| 仅I-cache pending-hit保护1→0 | 46717.248234 | 1.1182750169703988 | 32.376375364 | 省面积72.6084、频率下降2.042%，暂未采用 |
| 仅I-cache就绪逻辑简化 | 47271.740214 | 1.1182750169703988 | 35.132260610 | 面积/频率取舍，暂未采用 |
| 仅CDB宽度4→3 | 46187.629734 | 1.119368909148719 | 31.750953459 | 面积下降、频率退化，暂未采用 |
| CDB3 + 就绪逻辑 + 前端计数缩位 | 46390.029294 | 1.119368909148719 | 30.563514804 | 面积略降、频率退化，暂未采用 |
| 14个真实功能模块保留层级 | 58274.026914 | 1.1182750169703988 | 27.397993311 | 面积、频率均退化，排除 |

组合方案的原29项、新增8项以及16个独立解释器用例均通过。完整面积、IPC、时序绑定同一构建，153份结果输入哈希已再次复核。面积组成27706.05324 + 10858.3092 + 7825.666854 µm²，含378319个物理叶子、37个SRAM；周期32.71875 ns。[完整结果](F:/CPU2026Integration/r64p64rs12lsq16_cdb3width_fixed_ready_count_20261003/verified_cpu_result.json)和[复核记录](F:/CPU2026Integration/parallel_select_20261002/combined_cpu_result_recheck_20261003.json)已保存。网表SHA256为 `f9ec3d7a9c8fd8952023f98b9b399a4e02380b6a4c0e5570ad318a73ddf60530`。


仅关闭I-cache pending-hit保护的[完整整机结果](F:/CPU2026Integration/r64p64rs12lsq16_cdb2_fixed_icache_protect0_20261003/verified_cpu_result.json)包含380475个物理叶子、全部37个SRAM，网表SHA256为 `b5a391e18418f7db52a0898e213fb81674f5fff31fa1e5bad7bd991d61989d30`。面积组成为28025.39898 + 10866.1824 + 7825.666854 µm²，周期30.88671875 ns；相较主版本面积仅减少0.15518%，频率下降2.04249%，IPC不变，因此暂不采用。[153份输入复查](F:/CPU2026Integration/parallel_select_20261002/policy0_full_cpu_recheck_20261003.json)已完成。

I-cache并行标签比较完成了32组协议、88组策略/碰撞回放，以及6组完整控制器与全部7个SRAM原始引脚的等价证明，覆盖实际128行/2路/8 MSHR/E4配置、ready0/1及256行边界。没有输入假设；SRAM读数据是共享无限制输入，存储阵列内部不属于该形式证明。[形式证明](F:/CPU2026Proofs/icache_parallel_match_formal_20261003/report.json)保留所有原状态和输出。

| 实际128行I-cache，其他参数相同 | 总面积/µm² | 频率/MHz |
| --- | ---: | ---: |
| TAG_MATCH_PARALLEL=0 | 3672.584194 | 81.431411531 |
| TAG_MATCH_PARALLEL=1 | 4107.942994 | 224.070021882 |

[组件成对核验](F:/CPU2026Probes/icache_parallel_match_actual128_20261003/independent_component_verification.json)显示面积增加435.3588 µm²（11.8543%），频率提高175.1641%。这不是整机成绩，不能把各组件收益相加。

并行标签比较已通过默认关闭的参数适配接入隔离组合CPU，只改3份RTL，其余有效参数一致。首次整机启动因隔离目录缺少Verilator运行库失败，失败输出原样保留。已复制并逐一校验15392个工具文件，43份冻结输入和测量依赖未改变。[修复与重试记录](F:/CPU2026Integration/parallel_select_20261002/parallel_match_runtime_retry_20261003.json)绑定新任务70640；新目录为 `F:/CPU2026Integration/r64p64rs12lsq16_cdb3width_ready_count_parallelmatch_v2_20261003`，现已完成原29项、新增8项和16个独立解释器程序，共53项整机测试；独立核验确认周期、退休数与退出值逐项相同，IPC为1.119368909148719。全部1439份核验输入哈希已复查。完整整机PPA已在前序任务67788完成后开始，尚无并行标签比较CPU的新面积或频率结论。

单独CDB3的[完整整机结果](F:/CPU2026Integration/r64p64rs12lsq16_cdb3width_fixed_20261003/verified_cpu_result.json)现已完成，含37个SRAM、375798个物理叶子；网表SHA256为 `c0949f18aca14c140a809d14059fb80061f664675bd21d862348a52ef3ff2b5a`。面积组成27495.78048 + 10866.1824 + 7825.666854 µm²，周期31.4951171875 ns。相较主版本面积下降约1.29%，频率下降约3.93%，IPC略升；它在相同IPC下同时优于就绪逻辑与计数缩位组合，但仍未达到Tier3。153份整机输入已再次复核；连同RS组件及完整时序身份诊断，本次复核共182份独立输入，见[复核记录](F:/CPU2026Integration/parallel_select_20261002/cdb3_rsage_identity_recheck_20261003.json)。

任务67788现已完成仅关闭I-cache pending-hit保护方案的完整整机PPA；RS年龄8位的整机任务58696已完成全部53项测试和独立核验，六项IPC为1.1191945272026464。并行标签比较PPA70640已开始，RS年龄8位PPA等待70640。一项重排尝试在诊断任务已结束的身份检查处退出，尚未修改任何队列；随后已有计算启动，因此保留当前依赖顺序。主树尚未采用新的优化。

组合版本[完整时序身份诊断](F:/CPU2026Diagnostics/combined_ready_count_critical_identity_full_20261003/identity.json)对全部378319个叶子的层级连线进行一致性验证，定位最慢路径起点为I-cache `if_resp_pc_o[4]`、终点为 `if_resp_line_addr_o[4]`。路径上的OAI21、NAND2、NOR2节点扇出分别1039、738、502。一次更快的导出文件字节比较未通过，仅保留为失败诊断；上述身份结论来自随后完成的完整物理图一致性检查。

面积方向检查已对主版本实际37264个触发器逐一计价，恰好得到10866.1824 µm²；41个逻辑别名未定位，但对应物理单元仍全部计入。ROB store_addr_mem为2048个触发器、597.1968 µm²。这里按规范化信号名归类，某字段计数为零不代表它被剪除，可能由输出别名标识。[物理触发器核验](F:/CPU2026Diagnostics/fixed_cpu_sequential_ownership_20261003/report.json)只描述现有网表，不预报收益。

据此建立默认关闭的ROB MMIO预解码候选，在原完成写使能与优先级下同步保存“地址0x80000000且mask=0xf”判定位，保留全部原payload和输出。48组原协议与6组共48000周期、全部46个输出的差分测试通过。直接形式证明有35个点未证成，不能据此声明等价或认定RTL存在反例。补充纯观测的原比较结果别名后，七组小配置的完整证明已全部通过，共70672个证明点。最后一组汇总曾把新增观测别名误作原状态；独立收集器纠正分类后，复核了全部原状态、接口、证明脚本、日志及准备网表，未删减任何求解证明点。[差分报告](F:/CPU2026Proofs/rob_mmio_predecode_differential_v2_20261003/report.json)与[当前形式报告](F:/CPU2026Proofs/rob_mmio_predecode_formal_aliases_v2_20261003/verified_completion.json)均已保存；现已建立隔离CPU试验，尚无该试验的面积或频率结论。MMIO定向测试另通过24组配置、936个场景及84次真实退出，覆盖原版及候选关闭/开启；其中候选开启模式为312个场景、28次退出。测试检查所有16种写掩码、相邻/普通地址、重复完成优先级、首尾槽位、错误代际确认、背压与年轻提交抑制；把mask3错误视作完整字的负向变异被测试准确拒绝。实际ROB64、BE4、generation8、CHECKPOINT_WIDTH192、buffered1的bank1完整证明已完成29726个点，保留1216个原状态别名；[独立核验证书](F:/CPU2026Proofs/rob_mmio_predecode_actual64_bank1_verified_20261003/report.json)逐项检查完整31条求解命令、接口、状态、日志及观测别名可逆性。bank0由任务9984/求解器60812继续计算，未声称两组均完成。只替换了经核验未开始计算的旧等待器；[调度记录](F:/CPU2026Candidates/rob_mmio_predecode_v2_20261003/actual_guard6_reschedule_20261003.json)与旧输出均保留。

ROB预解码已通过默认关闭的参数接入隔离并行标签比较CPU，恰好修改ROB和三份参数适配文件，其余输入与参数保持一致。[整机试验](F:/CPU2026Integration/parallel_select_20261002/rob_mmio_parallel_match_cpu_launch_20261003.json)已完成原29项、8项ADDI边界及16项解释器用例，共53项全部通过，周期、退休数和退出值逐项相同。IPC为1.119368909148719；[独立核验](F:/CPU2026Integration/r64p64rs12lsq16_cdb3width_parallelmatch_robmmio1_20261003/independent_native_audit.json)的1836份输入已[再次复查](F:/CPU2026Integration/parallel_select_20261002/rob_mmio_native53_recheck_20261003.json)。完整PPA由新等待器41136接续，尚无该整机的面积或频率结果，也未采用到主树。

LSQ指针候选的8组纯函数SAT证明和12组原协议已完成。新增[函数替换核验](F:/CPU2026Proofs/lsq_function_congruence_20261003/report.json)确认函数无外部副作用，恢复原函数后外围RTL字节一致，拒绝6类负向变异。在容量1/2/4/8/16/32/64/128、默认SLOT_WIDTH、相同具名参数及二态语义下，可由函数等价推出整个模块状态转移和输出关系一致。单独的完整模块顺序求解仍在运行；不扩展到任意自定义宽度、四态语义或整机结论。

其他实验保留：

- LSQ16→8：同源码37项通过，但IPC降到0.99653885831981，排除，不启动PPA。
- PRF64→48：IPC1.097356845675659，低于阈值；RS16→8亦低于阈值。参数敏感性记录保留。
- 前端占用计数32→5位：9组完整等价证明共26767点通过；实际组件面积1493.06490→1484.52102、频率191.009→286.915 MHz，已纳入上述组合整机试验。
- RS payload banks：48000周期差分和较小形式证明通过，实际12/16项证明继续运行。组件面积5519.15694→5752.02870、频率90.188→124.242 MHz，尚无整机结果。
- RS AGE_WIDTH32→8：28组测试、48000次独立选择器对照、13次自然回绕通过；现有参数、RTL不变。回绕可能改变发射顺序，不能声明周期等价。实际RS12组件成对PPA已完成：32位面积5565.09852 µm²、频率93.507442243 MHz；8位面积5099.71950 µm²、频率120.258367587 MHz，即面积减少8.36%、频率提高28.61%。[完整组件核验](F:/CPU2026Probes/rs_age_width_actual12_20261003/independent_component_verification.json)按8→32排序，文中收益按32→8计算。仅通过三份默认32位的参数适配接入隔离整机，实际RS RTL字节不变；[整机启动记录](F:/CPU2026Integration/parallel_select_20261002/rs_age8_parallel_match_cpu_launch_20261003.json)对应58696，现已通过全部53项整机测试及[独立核验](F:/CPU2026Integration/r64p64rs12lsq16_cdb3width_parallelmatch_rsage8_20261003/independent_native_audit.json)：全部退休数和退出值相同，周期按仲裁变化重新实测，六项IPC为1.1191945272026464，仍达IPC门槛。1700份核验输入已复查；整机面积和频率待测。
- 原主版本和组合版本的16个补充RV32IM程序，每版本42592条退休指令与独立译码解释器相符；覆盖45类指令、除零、溢出、移位量截断、自然对齐内存、分支两方向及JALR边界。475份输入已核验，详见[双构建核验](F:/CPU2026Proofs/rv32im_native_edges_comparison_20261003.json)。这是有限签名/退休数验证，不是逐条RTL退休值比对或完整ISA证明。语义依据[RISC-V RV32I规范](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html)与[M扩展规范](https://docs.riscv.org/reference/isa/v20260120/unpriv/m-st-ext.html)。


新的I-cache MSHR固定槽位写入试验保留原有8种字段、42处赋值的8组写优先级、全部接口及原SRAM，无额外状态或周期；参数默认关闭。现已通过32组原SRAM协议和88组策略/碰撞回放，八组完整控制器/全部7个SRAM引脚等价证明已有7组通过，包括实际128行/8MSHR/E4以及256行/16MSHR配置，其余配置仍在求解。[验证进度](F:/CPU2026Proofs/icache_static_mshr_formal_20261003/report.json)不能当作八组均已完成；后续实际128行组件PPA等待现有整机队列，尚未接入CPU，也无面积或频率结论。

本次另对RS年龄整机核验与实际ROB证明证书共1714份独立输入完成[哈希复查](F:/CPU2026Integration/parallel_select_20261002/rsage_native_rob_actual_recheck_20261003.json)。主版本全部43份输入再次与采用档案一致。


在固定写入候选上另建立真实MSHR状态分组：每个槽位拥有原来的8种字段（E4时76位），直接复用原顺序过程，仅替换端口名和常量行号；替换可严格逆转。没有增加逻辑状态位或周期，SRAM接口不变，所有功能层级仍须完整计价和计入时序。此方案已通过[32组原SRAM协议](F:/CPU2026Proofs/icache_mshr_state_banks_protocol_20261003/report.json)及[88组回放](F:/CPU2026Proofs/icache_mshr_state_banks_replay_20261003/report.json)；完整证明等待前一候选八组完成，组件PPA尚未开始，尚未接入CPU。

新增[整数执行通道取舍试验](F:/CPU2026Integration/parallel_select_20261002/integer_width_tradeoff_launch_20261003.json)：以已完成53项验证的RS年龄8位版本为基线，保持全部43份源码、FE4/BE4、CDB3、窗口和缓存参数不变，只将INT_ISSUE_WIDTH由4改成2。先重新测53项及真实IPC；若2通道低于最终门槛，再测3通道，保留低IPC结果用于后续联合取舍。等待器经确认尚无编译子进程后，以4GB原生编译准入重新启动为66692；原同类单线程分文件构建报告Verilator分配572.824 MB，完整PPA仍保留原6GB门槛。两通道原生编译68008已开始，尚无该参数试验的成绩；[调度证据](F:/CPU2026Integration/parallel_select_20261002/integer_native4_reschedule_20261003.json)保留旧等待器身份和未开始输出。

三项尚未开始计算的等待器经过PID、创建时间、命令行、子进程及输出状态复核后重新排序，[调度记录](F:/CPU2026Integration/parallel_select_20261002/mshr_bank_priority_reschedule_20261003.json)保留完整证据。策略试验67788已完成；后续PPA顺序为并行标签70640、RS年龄58696、固定MSHR写入30540、真实MSHR分组68676、ROB预解码41136、整数通道66692。没有中断运行中的计算，也没有重跑已完成的原生或协议测试。

更早的实验、故障和调度记录保存在[此前报告快照](F:/CPU2026Integration/parallel_select_20261002/report_before_runtime_retry_20261003.md)。含ADDI255已知缺陷的旧CPU成绩不能作为修复版成绩。下一步继续完成活动候选的整机验证，并依据同一配置的完整面积、IPC和SRAM时序决定取舍。
