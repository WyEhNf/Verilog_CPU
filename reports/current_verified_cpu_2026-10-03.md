# 2026-10-03 当前已核验整机与后续任务

截至2026-10-03 04:24（Asia/Shanghai），目标保持执行中，**Tier3尚未达到**。汇报进展不暂停或终止目标。原始要求见[目标文件](../docs/goal-objective_2026-10-02.md)；三项指标必须来自同一配置、同一构建，全部真实FakeRAM SRAM均计入面积和时序。

## 当前已采用的完整结果

主树43个编译输入已与经过验证的静态RS12/PRF并行读取源树逐字节一致。只采用了五个RTL文件，旧主树全部43个文件保存在 `F:/CPU2026Integration/parallel_select_20261002/pre_static_adoption_20261003`，并保留adoption.json。**测量参数由显式配置指定，不能把RTL默认开关当作本次测量配置**：使用 `build/cpu2026/verified_static_completion2_profile_20261003.json`，其中ROB64、PRF64、RS12、LSQ16、RS_ALLOC_STATIC_WRITE=1、PRF_READ_MUX_IMPL=1、COMPLETION_BYPASS=2。

| 同一配置的核验项 | 实测 | Tier3要求 | 状态 |
| --- | ---: | ---: | --- |
| 全部正确性测试 | 29/29通过 | 全部通过 | 通过 |
| 授权六项IPC几何平均 | 1.1182750169703988 | ≥1.0985 | 达标 |
| 总面积，包含37个SRAM | 46808.096214 µm² | ≤36000 µm² | 未达标 |
| 全SRAM时序频率 | 42.25817101353582 MHz | ≥300 MHz | 未达标 |

面积组成：组合28116.24696、时序10866.1824、SRAM7825.666854 µm²；实际物理叶子382777个。最小周期23.6640625ns，最终网表SHA256为 `3b3956f6db65df688d51f1ebe2e36234a5269d88e78a89f9d84144c63af19f44`。面积还需下降10808.096214µm²（当前值的23.09%），频率需提高至当前的7.10倍，不能称为已接近全部门槛。

六项median、multiply、qsort、rsort、towers、vvadd周期依次为10048、11969、161195、184298、4925、3951；合计376386周期、472599条退休指令。IPC采用六项各自IPC的几何平均，而非合计指令数除合计周期。Pi按先前授权冻结。

完整证据目录：`F:/CPU2026Integration/r64p64rs12lsq16_cdbmode2_static_datapath_20261003completion2`。其中 `verified_cpu_result.json` 由 `tools/collect_verified_course_cpu.py` 独立绑定29项测试、全部43个编译输入、驱动、程序映像、参数、原始库计价及所有时序输入哈希，状态VERIFIED。主树采用后又通过 `verify_course_axi_area.py --require-current`，当前输入差异为零。

流程保持原课程框架revision `54fc150ffc290f52aa024209ffb9a29d43856f6d`、五份原始ASAP7 RVT TT库、默认ABC、原FakeRAM验证器和模型。原sim.cpp仅增加只读退休计数打印，256MiB内存、20cycle/word、32位AXI4-Lite及MMIO B握手退出约定不变。频率是包含SRAM的综合后理想时钟、无寄生估计，不是布局布线后结果。

## 完整整机取舍

| 配置 | 29项 | 六项IPC | 含全部SRAM面积/µm² | 频率/MHz |
| --- | --- | ---: | ---: | ---: |
| integrated1 | 通过 | 1.1213155347352615 | 54375.028734 | 39.67915681791762 |
| integrated2b | 通过 | 1.1213155347352615 | 52307.482674 | 39.38916028772551 |
| RS12静态分配、PRF并行读取、completion0 | 通过 | 1.1232643380242247 | 49363.387014 | 32.57101052832469 |
| 同源completion2，当前采用 | 通过 | 1.1182750169703988 | 46808.096214 | 42.25817101353582 |

completion0→2使面积下降5.18%、频率提高29.74%、IPC下降0.44418%，IPC仍达标。各行均是自身完整测量，组件收益没有叠加为整机结果。

## 下一份整机与独立候选

- **ROB并行完成写入＋D-cache元数据64行分组**：隔离来源 `F:/CPU2026Candidates/rob_cache_integration_20261003`，其余参数以当前completion2为基线。新增显式参数ROB_COMPLETION_PARALLEL_WRITE=1、DCACHE_METADATA_GROUP_ROWS=64，共五个编译文件有变化。04:24实际Verilator/C++构建仍在运行，后续自动执行29项、逐项精确周期/退休/退出对照、同构建完整面积及全SRAM时序。输出 `F:/CPU2026Integration/r64p64rs12lsq16_cdb2_robcompletion1_cache64_20261003`；尚无新整机结果，未采用到主树。
- **ROB组件证据已完整**：48组协议、8组小容量/边界完整模块形式证明、6组共48000周期全46输出四态差分通过。实际完整ROB64组件面积10942.58160→9847.36116µm²（−10.01%），频率103.87502536→106.67777894MHz（+2.70%），独立核验VERIFIED。8组形式证明不等于实际ROB64完整形式证明。证据 `F:/CPU2026Probes/rob_parallel_completion_actual64_v3_20261003/independent_component_verification.json`。
- **Cache组件证据已完整**：720组协议、816228次检查通过；16→64行分组后，含全部36个SRAM的实际完整Cache面积12752.716580→12454.409780µm²，频率57.46997418→70.41188201MHz，独立核验VERIFIED。证据 `F:/CPU2026Probes/dcache_metadata_geometry_actual_20261003/independent_component_verification.json`。
- **关闭前端响应同拍链式请求已拒绝**：29项正确性通过，三处源码改动及单一参数切换独立核验通过，但IPC1.123264338→0.918541310（−18.23%），不满足Tier3 IPC，因此没有安排PPA。证据 `F:/CPU2026Integration/r64p64rs12lsq16_frontend_chain0_static_datapath_20261003/independent_native_audit.json`。
- **前端队列实际状态分组**：保留响应同拍链式请求和全部流水周期，以真实拥有状态的功能模块局部化写控制。6组协议和6组完整模块形式证明已通过（包含实际FE4/FQ16），04:24正在实际完整前端组件PPA。证据 `F:/CPU2026Proofs/frontend_payload_banks_20261003` 和 `F:/CPU2026Probes/frontend_payload_banks_actual16_20261003`；尚无面积/频率收益结论。
- **RS实际状态分组和年龄比较缓存**：前者全输出48000周期差分与前五组完整形式证明通过，实际12项证明仍运行；后者完整16项替代证明仍运行。原重复年龄证明因实际内存压力已明确暂缓并保留记录，目标未暂停。尚无采用或组件PPA收益结论。

## 当前时序与面积诊断

当前completion2的完整382777物理叶子及全部连接身份核验完成。关键路径起点I-cache `if_resp_pc_o[4]`，终点 `tag_mem[24][6]`；最大延迟门NAND2xp33约8.46ns、根模块扇出736，另两级扇出539与616。这确认了物理控制依赖和高负载，尚不能单凭门名断言精确RTL表达式。证据 `F:/CPU2026Diagnostics/completion2_critical_identity_20261003/identity.json`。

完整层级时序单元核价得到10866.1824µm²，与总面积证据一致。ROB的4953个触发器占1444.2948µm²、I-cache的3914个占1141.3224µm²、RS的3108个占906.2928µm²；这些是寄存器信号归属诊断，不能当作模块全部面积。后续继续针对实际控制负载和选择逻辑优化，并用同一整机结果决定采用。
