# A69 集中测量结果与 A72 修复方向

A69 原始串行作业已正常结束。课程标准 Windows 原生工具、库、六项程序和冻结源码均绑定复核；没有重跑测试。

| 指标 | A55R2 | A69 |
|---|---:|---:|
| 六项 IPC 几何平均 | 1.01714182 | 1.05184611 |
| 综合与 STA 估算频率 / MHz | 306.86245 | 229.69942 |
| 总面积（含 SRAM）/ μm² | 35480.53090 | 35673.35140 |

A69 IPC 提高 3.412%，总面积增加 192.820 μm²；频率下降 25.146%，不能采用。频率和面积满足目标的已测综合最优记录仍是 A55R2。A69 IPC 距 1.1 尚需提高 4.578%。

六项性能程序均通过；完整19项正确性、RV32IM/恢复/参数专项覆盖仍未完成。没有将候选写入主实现。

| 程序 | A55R2 周期 | A69 周期 | A69 IPC | IPC 变化 |
|---|---:|---:|---:|---:|
| perf_median | 8307 | 7969 | 0.873510 | +4.241% |
| perf_multiply | 18338 | 17494 | 1.241683 | +4.825% |
| perf_qsort | 162351 | 147323 | 0.949614 | +10.201% |
| perf_rsort | 161852 | 161812 | 1.209546 | +0.025% |
| perf_towers | 5662 | 5589 | 0.944355 | +1.306% |
| perf_vvadd | 3939 | 3930 | 1.151145 | +0.229% |

新 STA 的五条最慢路径共享主要通路，最长数据到达4.293 ns：pending recovery tag → ROB full-GEN qualification → MDU cancellation/ordinary completion live-ready → redirect-dependent ICache response → predictor query → RAS。2 ns映射约束下报告负裕量，目标300 MHz仍需实际路径缩短；没有加入 false-path。

独立源码工作：A70 在有效直接恢复边沿计算准确的下一周期 ROB 信用；A71 允许当前单报告端口上报的第二项已完成加载同时参与两项前缀回收；A72 将分支捕获中的通用 ALU ready 按现有 valid+redirect+!pending 条件展开为等价的重定向优先规则。A72 保留实际 ALU 消费规则与全部有效性/代数检查，删除完成网络 ready 对捕获逻辑的结构依赖。

A70–A72 均未运行 HDL/仿真/综合/STA；未证明频率已恢复，收益也未测得。三项修改不增加声明的 FF/SRAM/流水边沿，但新增或改写组合门的映射成本与剩余路径仍待评估。

- [A69 结果](F:/CPU2026CourseRuns/ER1_A69_tier3_20261006/result/result.json)
- [A69 IPC](F:/CPU2026CourseRuns/ER1_A69_tier3_20261006/result/ipc.json)
- [A69 时序路径](F:/CPU2026CourseRuns/ER1_A69_tier3_20261006/result/synth/opt/critical_paths.json)
- [A72 源码审查](F:/CPU2026Candidates/tier3_er1_20261005/A72_source_review.json)

后续先继续检查恢复到前端的剩余依赖，再汇报并安排有充分依据的下一次集中测量。
