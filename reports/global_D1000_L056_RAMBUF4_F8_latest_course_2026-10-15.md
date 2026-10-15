# global_D1000_L056_RAMBUF4_F8 评估（2026-10-15）

采用官方框架 `302f0cf3cccdaa5de084a2120e0d950c663e4cf5` 的原始面积统计、STA、构建、RAM、模拟器驱动和 testcase 脚本，评估历史保存的准确综合网表。未修改当前工作树 CPU RTL，未重新运行默认综合流程来替换指定网表。

| 指标 | 本次实测 | Tier3 门槛 |
| --- | ---: | ---: |
| 总面积 | 32200.657838 μm² | ≤36,000 |
| IPC 几何平均 | 1.115262691835 | ≥1.0985 |
| STA 估计最高频率 | 489.016237 MHz | ≥300 |
| 最小周期 | 2.044921875 ns | 500 MHz 目标为 ≤2.0 ns |

该网表的三项实测数值满足 Tier3 阈值；500 MHz 目标未达到，差 10.983763 MHz。它使用自定义映射和综合后的缓冲树，因此这些结果属于保存网表的实验评估，不等于官方默认 RTL 综合流程的提交分数，也未替换当前正式配置。

## 版本与条件

- 基于冻结的 A109 CPU，源清单 SHA256：`33d1f29453657f5edd5ac5ee641e20cb0f1f991f567e1d10efc367c40aadd5ba`。
- 全局映射清除 RTL keep/keep_hierarchy；ABC 目标 1000 ps，驱动 BUFx2_ASAP7_75t_R，映射负载 0.56 fF。
- SRAM 输入增加 360 个 BUFx4_ASAP7_75t_R，树最大扇出 8；不改时钟，不增加流水级。
- STA 实际输出负载仍是官方 5 fF；输入/输出延迟 0.2 ns，时钟不确定度 0.05 ns，时钟与输入转换时间 0.05 ns，reset=0，理想时钟、无寄生参数。
- Liberty、工具二进制和指定网表均核验哈希；Windows 原生固定工具版本与前次当前默认配置评估相同。
- 网表 SHA256：`ce1ae01b92aabfac41adcddb6f6ef937c9212babe481403c38f1d824814edf6c`。
- 逻辑面积 24256.746000 μm²，其中时序 7451.838000、组合 16804.908000；SRAM 7943.911838 μm²，共 93 个宏。

## 直接门级仿真

本次 IPC 来自上述映射后网表的零延迟功能仿真，未借用 RTL 历史结果。标准单元行为由真实 Liberty 通过 Yosys read_liberty/write_verilog 生成；SRAM 宏桥接至未修改的最新官方 sram_fakeram。原始官方 sim.cpp/testcase.py，延迟 10、周期预算 1,000,000，未使用 WORD_SIM、PGO 或生成代码优化补丁。功能仿真不包含 SDF 延迟，频率由独立 STA 提供。

| 基准 | 动态指令数 | 周期 | IPC |
| --- | ---: | ---: | ---: |
| perf_median | 6961 | 7572 | 0.919307977 |
| perf_multiply | 21722 | 17490 | 1.241966838 |
| perf_qsort | 139900 | 143485 | 0.975014810 |
| perf_rsort | 195719 | 153155 | 1.277914531 |
| perf_towers | 5278 | 4739 | 1.113737075 |
| perf_vvadd | 4524 | 3725 | 1.214496644 |

六项基准答案全部通过；另仅运行一个小正确性点 correctness_array_test1，通过。未运行完整正确性回归或参数扫描。

构建辅助模块 cpu2026_pgo.py 在生成阶段、导入和编译前补入，并独立记录 SHA256 于 supplemental_inputs.json；PGO 始终关闭。原始冻结 manifest 与活跃构建保留，不重启测试。

完整原始证据：`F:/CPU2026CourseRuns/global_D1000_L056_RAMBUF4_F8_latest_302f0cf3_20261015`。机器可读报告：`global_D1000_L056_RAMBUF4_F8_latest_course_2026-10-15.json`。评估器：`tools/evaluate_saved_netlist_course.py`。
