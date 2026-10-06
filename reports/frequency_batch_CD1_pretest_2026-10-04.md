# CD1 统一后台测试前汇报

本报告先于 CD1 测量启动落盘。CD1 只修复 CD 的内部保留字：27 处 matches 改为 row_match_mask，不改逻辑、状态、时序或端口。CD 首次编译失败，没有运行 perf/correctness；其综合树已停止，日志保留。当前工作树采用 CD1；本批 BV→CD 九项和此前 S→BU 的全部结构改动共同冻结于 [architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)，23 个实现文件、157 个课程输入，原工作树版本保留在 [备份](F:/CPU2026Candidates/pre_CD1_worktree_20261004/backup.json)。

已完成的主要变化是：保持十级，RS physical wake tag 17→7 位、wake source 10→6 路，移除 CDB 仲裁到 RS 的重复唤醒路径及 first/last 选择；frontend 宽包/PC/count/dispatch 查询缩短；预测器 BHT/BTB/RAS 行拥有原边沿状态，目标与跨 bank 路由按 16 位分组。之前已有恢复 preview/apply、dispatch/issue 边界、相对年龄、CSA 乘法器末级、并行除法准备、LSQ/cache/AXI 控制与宽数据重构。完整解释见 [实现记录](E:/Verilog_cpu/reports/frequency_rtl_restructure_2026-10-04.md)。

质变判断依据是跨级组合依赖被切断、唤醒身份和总线规模直接缩小、原高负载控制分散到最终消费者；没有数值证据保证已经达到 300 MHz。当前没有新的频率、IPC 或面积结果。统一测量用于确认这个完整候选的收益与合法性，不为每项改动运行测试。

## 一次测量的范围

- 只在 Windows 当前环境用固定课程版本；不用 WSL。框架 54fc150ffc290f52aa024209ffb9a29d43856f6d，测试库 29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys 0.63、ABC 8e40154、OpenSTA 3.1.0、Verilator 5.020，固定 ASAP7 库。
- 对同一冻结源码并行进行一次课程综合/STA 与一次原生 CPU 构建。综合使用原脚本 opt/2 ns 约束，最终频率取其 STA 最小周期，不将约束值当成实测频率。
- 构建后一次运行官方六项 perf，内存延迟 10，动态指令分子来自原 metrics.json，IPC 取精确几何平均；随后一次运行官方 19 项 correctness。
- 总面积按原课程 SRAM/FakeRAM 规则计入 SRAM。比较同规范基线的 Fmax、IPC、面积；频率优先，同时报告 ±10% 范围和 Tier3 的 36000 µm²/1.0985/300 MHz 是否达成。
- 后台隐藏窗口执行，冻结输入不再改动；运行期间继续整理优化方向，不重复启动测量。先完成本批验证，再根据实际最慢路径决定后续实现。

## 必须验证的风险

此前 L1 correctness 为 16/19，pi/qsort/tak 达到 million-cycle 上限；本批没有证据证明已修好。AM 的 redirect 仲裁修正和后续全部结构需共同验证。优先关注 warm reset、分支恢复后物理编号重用、持有生产者反压、同束 RAW、store/load 顺序、RAS overflow/pop、frontend line 边界与合法 ADDI。普通 RTL 层次控制分发是否通过原课程 SRAM 白名单、ABC 是否保留并改善负载也需实际综合。任何编译/映射失败都保留日志，不宣称有频率结果。

最后完整同规范基线为 Fmax 32.39788654411997 MHz、IPC 0.9801279406499007、总面积 46309.69349394434 µm²。L1 IPC 0.8004591469676289，综合被拒，没有 Fmax/面积；它们都不是 CD 的结果。
