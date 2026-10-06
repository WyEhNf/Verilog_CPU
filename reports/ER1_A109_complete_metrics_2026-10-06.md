# A109 同一次测量三项指标

原PID103132已结束，serial timing/performance均returncode0；冻结41候选源/157测量输入与课程工具检查保持，三项来自相同source manifest/config/CPU，不能与A110/A111源混用。

| 指标 | A109原课程Windows native实测 |
|---|---:|
| IPC（六perf GEOMEAN，latency10） | 1.115262691835 |
| 总面积（含SRAM） | 35891.672317998 um² |
| Fmax | 321.608040201 MHz |
| 最低周期 | 3.109375000 ns |

组合20348.956079998、时序7598.804400000、SRAM7943.911838000um²，总和与总面积一致。课程五份ASAP7RVTTT/FakeRAM、Yosys0.63/ABC/OpenSTA3.1/Verilator5.020固定版本，Windows native、原sim.cpp/testcase/metrics、latency10，ideal/no parasitics最低周期搜索。

相比A94，IPC变化0.000000%，频率变化10.804020%，总面积变化0.258945%。严格三项数值目标达到；六性能答案通过。完整19课程+4现有冻结边界CPU程序尚未运行，主E源尚未采用，目标还不能宣布完成。

原CPU SHA256：5a3ac16a6917157dd6d0dc2baa7f0b2c1bb7fe71baf504a2842edc3e09cdef42。保留原成功结果文件，不重新构建/综合/跑perf；达到数值目标后先在对话汇报，再集中同exe执行19+4，完成架构/参数审阅后采用。A110/A111未测，单独保留，不把它们称为已达标方案。
