# ER1 A109：Tier3与线程三项目标的已验证实现

同一课程固定工具链/配置/源/可执行文件实测IPC **1.115262691835**、总面积（含SRAM）**35891.672317998um²**、综合/STA估算Fmax **321.608040201MHz**。满足线程严格Fmax>300MHz、IPC>=1.1、总面积<=36000um²，并满足课程Tier3 IPC>=1.0985/频率>=300/面积<=36000。

| 指标 | 当前A109 | 线程目标 | 余量 |
|---|---:|---:|---:|
| 六perf IPC GEOMEAN | 1.115262692 | >=1.1 | 0.015262692 |
| 含SRAM面积/um² | 35891.672318 | <=36000 | 108.327682 |
| Fmax/MHz | 321.608040 | >300 | 21.608040 |

组合面积20348.956080、时序面积7598.804400、SRAM面积7943.911838um²，三者相加等于总面积。课程报告中93个SRAM实例逐项面积求和与该SRAM合计一致，无重复实例或漏计。频率按课程ASAP7RVT TT/FakeRAM、ideal clock/no parasitics、50ps uncertainty与最低周期搜索得到；最低周期3.109375000ns，尚不是布局布线后硅片频率。

六perf原答案全部通过，IPC分子使用课程metrics.json的dynamic_instructions，分母为同一个官方sim报告cycles，latency10：

原ER1六perf IPC已先行实测确认：0.763039790750，A109相对提高46.160489%。ER1原源码因Verilator保留标识符只做局部名字替换，反向替换后的文件逐字还原，其他源码与课程输入不变；原IPC及兼容审阅保持冻结，没有为本次报告重复运行。

| 程序 | 课程动态指令数 | 仿真周期 | IPC |
|---|---:|---:|---:|
| perf_median | 6961 | 7572 | 0.919307977 |
| perf_multiply | 21722 | 17490 | 1.241966838 |
| perf_qsort | 139900 | 143485 | 0.975014810 |
| perf_rsort | 195719 | 153155 | 1.277914531 |
| perf_towers | 5278 | 4739 | 1.113737075 |
| perf_vvadd | 4524 | 3725 | 1.214496644 |

随后复用同一CPU可执行文件，分两次完成19个不同的官方correctness程序，4/4既有冻结RV32IM边界程序通过。原集中运行返回1，18项PASS、Pi在10,000,000周期timeout；原失败日志和结果完整保留。Pi共享32轮M引擎仅必需迭代就需36,025,632周期，原预算不足。课程允许MAX_CYCLES配置，此后仅以48,000,000周期上限、相同latency10、原程序及原答案补测Pi，实际38853527周期退出并匹配112。没有重跑其余18项或四边界，不能表述成原10M单次19/19通过。六perf指标来自原测量，未放宽或重跑性能预算。

| 官方程序 | 实际周期 | 周期上限 | 结果来源 | 答案 |
|---|---:|---:|---|---|
| correctness_add_to_100 | 447 | 10000000 | original_closing | PASS |
| correctness_array_test1 | 433 | 10000000 | original_closing | PASS |
| correctness_array_test2 | 466 | 10000000 | original_closing | PASS |
| correctness_basicopt1 | 690965 | 10000000 | original_closing | PASS |
| correctness_bulgarian | 171539 | 10000000 | original_closing | PASS |
| correctness_expr | 414 | 10000000 | original_closing | PASS |
| correctness_gcd | 427 | 10000000 | original_closing | PASS |
| correctness_hanoi | 3348 | 10000000 | original_closing | PASS |
| correctness_lvalue2 | 210 | 10000000 | original_closing | PASS |
| correctness_magic | 363721 | 10000000 | original_closing | PASS |
| correctness_manyarguments | 215 | 10000000 | original_closing | PASS |
| correctness_multiarray | 1327 | 10000000 | original_closing | PASS |
| correctness_naive | 214 | 10000000 | original_closing | PASS |
| correctness_pi | 38853527 | 48000000 | pi_budget_followup | PASS |
| correctness_qsort | 887183 | 10000000 | original_closing | PASS |
| correctness_queens | 240708 | 10000000 | original_closing | PASS |
| correctness_statement_test | 1137 | 10000000 | original_closing | PASS |
| correctness_superloop | 342639 | 10000000 | original_closing | PASS |
| correctness_tak | 802145 | 10000000 | original_closing | PASS |

额外四项为arithmetic_edges_2、memory_low、memory_ram_top、control_alignment_0，期望与输入来自原已冻结独立解释器，含全部45类操作/8个M操作、除零/溢出、x0、自然对齐存取、RAM顶部和JALR边界；它们补齐官方程序缺少的DIVU/MULH/MULHSU/MULHU。这是有限程序/签名覆盖加源级审阅，没有宣称整CPU形式化完整ISA证明或任意参数组合都经过动态验证。

源级审阅确认：保留完整RV32IM译码和原ALU/MDU/LSQ实现；RS只对ready行排序，可越过未ready的较老指令；ROB只提交实际head的连续ready前缀；MMIO word store以地址80000000、WSTRB1111和原32位WDATA送至外部AXI，普通cache不吸收退出。Icache高地址前缀按way完整保留并参与命中，变化会失效旧行，Dcache保持完整地址tag。

关键参数通过实际模块与数组维度：FE4、BE2、INT_ISSUE_WIDTH2、ROB32、PRF56、RS8、LSQ16、Icache128行2路（每行16B）、Dcache1024行2路（每行16B）。支持范围/依赖见[本次参数与架构审阅](E:/Verilog_cpu/reports/ER1_A109_architecture_parameter_source_audit_2026-10-06.md)。已有[参数敏感度](E:/Verilog_cpu/reports/parameter_sensitivity.md)记载历史单参数IPC实验，包括ROB32→64、PRF64→96、RS深度和CDB宽度等；[架构探索](E:/Verilog_cpu/reports/architecture_exploration.md)记录相应取舍。这些旧源码/latency20/旧工具数据仅作历史探索，不用作当前latency10课程成绩，不混成A109指标。

A109整批将原恢复/LSQ身份和分配的晚选择拆为先计算候选、后选择事件/小字段，并把原单份ROBoccupancy分发到局部消费者；该组合实测频率比A94提高10.804020%，IPC逐项周期与A94相同，面积仅增加92.699640um²。A105整批曾退化到274.24MHz/36056.02um²，保留失败证据；不能从整批结果独立归因某个开关。A110先比较wake身份、A111并行加减已准备但没有测量，未混入或采用。

旧“九级算术流水”描述需要纠正：当前ALU四位chunk/prefix均是组合层，仍是原一周期结果寄存器，课程ISSUE_PIPELINE0未增加RS→ALU寄存级。本次达标通过组合路径与扇出重构得到，没有把算术组合层当作流水级。

已将20份改变的RTL及课程根目录头文件alias采用到E:/Verilog_cpu，41个主源文件逐字与本次已测源一致；原40源完整备份于F:\CPU2026Candidates\er1_before_a109_adoption_20261006。旧成功生成器/manager/proof/report/结果均保留，不编辑或重跑；原A109结果和closing证据只读，原manager的check核对原测量快照，当前主工作区另外逐项核对41源SHA。本次没有重复CPU构建、综合或六perf，采用后的41源SHA一致替代重复测试。

课程框架54fc150ffc290f52aa024209ffb9a29d43856f6d、testcases29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys0.63、固定ABC/OpenSTA3.1、Verilator5.020；整个测量与验证Windows native，无WSL。可执行文件SHA256：5a3ac16a6917157dd6d0dc2baa7f0b2c1bb7fe71baf504a2842edc3e09cdef42；source manifest SHA256：33d1f29453657f5edd5ac5ee641e20cb0f1f991f567e1d10efc367c40aadd5ba。原测量、两次运行合并的19个不同官方用例与四边界、架构审阅、当前41主源和备份证据由采用审阅绑定；采用后另行只读核对当前主源与原始证据，完成该核对才能宣布目标完成。
