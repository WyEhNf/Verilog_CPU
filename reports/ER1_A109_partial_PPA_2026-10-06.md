# A109：频率和含SRAM面积达到目标，IPC尚待原运行

原课程Windows native测量PID103132的综合/STA阶段returncode0，冻结manifest/工具/源/配置检查保持。只读取同一个原结果，不重启或额外测量。

| 指标 | 原A109实测 |
|---|---:|
| Fmax | 321.608040201 MHz |
| 最低周期 | 3.109375000 ns |
| 总面积（含SRAM） | 35891.672317998 um² |
| 组合面积 | 20348.956079998 um² |
| 时序面积 | 7598.804400000 um² |
| SRAM面积 | 7943.911838000 um² |
| IPC | 尚未完成，不能继承A94 |

相比A94，频率提高10.8040%，总面积增加92.699640um²（0.2589%）。含SRAM面积余量108.327682um²。相比A105整批，频率增加47.371297MHz，面积减少164.345760um²。不能把整批改善归因于其中单一修改。

课程报告使用2ns映射/报告时钟、50ps uncertainty、ideal clock/no parasitics；Fmax来自minimum-period搜索，2ns下负slack不等于300MHz未达标。原频率已超过300MHz，时序/面积通过后原manager自动按预汇报计划继续一次CPU构建和六perf，IPC/答案仍未完成。

新top5到达为3.049, 3.034, 3.030, 3.021, 3.018ns，前3条为branch_capture_tag→recovery_preview→LSQ headchoice→原rawproducer物理身份→RS唤醒/发射→ALU SUB/算术，后2条为LSQ forwarding/request→MMIO请求资格→dcache ready→selection payload写入。原completion data名称是rawproducer共享别名，不代表串行CDB仲裁。ALU仍为一周期结果寄存器，分块prefix是组合层，不是新增流水级。

A110/A111作为独立源候选继续保留，均未测/未采用；当前不派发它们。若原A109六perf答案通过且IPC>=1.1，再先汇报，复用完全相同exe/source/config执行19官方与4现有冻结边界程序，再完成关键参数/架构源审阅与主源采用。目标尚未完成。
