# ER1 A8 测量与独立后续候选

A8完整组合已在Windows原生课程工具链中一次调度。范围为一次综合/STA、一次CPU构建、六perf及十九correctness。
预期结构收益及风险详见ER1_A8_pretest_2026-10-05.md。源/课程脚本/程序157份仍与冻结manifest一致。
本记录时驱动进程95760存活，native CPU已进入C++编译，综合处于Yosys elaboration；IPC/面积/Fmax尚无新结果。
不能把ER1或EU旧结果当作A8结果，不能据构建开始宣称功能或目标完成。

背景工作已另存A9_unconnected_return_payload（未测试、未采用）：
课程student_top不连接cpu_core.return_value，官方结果通过AXI退出store的WDATA输出。
新增RETURN_VALUE_ENABLE默认1；只有课程调用显式设0且轻量模式启用时省去ROB store_data载荷。
实际store bytes仍由原LSQ data_mem和AXI路径保存、更新、发送；MMIO地址/mask检测、store admission/ack、halt时刻不变。
当前ROB32可进一步省1,024位存储，退休选择包65→33位；实际映射收益未知。
必须明确：该可选模式将未连接的内部return_value置零，因此不是cpu_core所有诊断接口全等价。
原模块默认保留返回值；完整退休模式也保留store_data owner。其证明范围是课程顶层AXI与debug输出的源码投影。
A9没有修改A8冻结源码或启动另一组测试，等待A8真实瓶颈/结果决定后续完整组合。

目标保持IPC≥1.1、Fmax>300MHz、含SRAM总面积≤36,000μm²及课程正确性要求；当前未达成。
下一步首先观测同一存活作业的结果，结合真实频率、面积分解与六项周期继续优化，避免中间版本/参数扫描。
