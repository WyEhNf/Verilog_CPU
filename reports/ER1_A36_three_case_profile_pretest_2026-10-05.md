# A36三项低IPC程序定向采样前汇报

A36已实测IPC几何平均0.9918977910、总面积含SRAM35,686.138058μm²、Fmax297.24238026MHz，六perf答案全PASS。面积显著改善并达到门槛，IPC仍需约10.9%，有实际可观收益，值得定位剩余动态停顿；暂不重复19项正确性或所有中间候选测试。

本次仅对已测A36的median/qsort/towers三项低IPC程序各采样一次。复用已编译的Verilator5.020 CPU模型archive和runtime对象，只编译/链接一个旁路C++观察驱动；没有新的Verilog生成、RTL修改、CPU模型编译、综合或STA。原sim.cpp、sim.exe、模型archive和所有A36结果保持冻结。新增驱动等于官方sim.cpp仅增加root header、host-side只读计数和stderr JSON输出；反向删除这三处插入逐字恢复原驱动。不增加eval、tick、timeInc、内存步骤或CPU寄存器写入。

通过原官方oj_io准备相同stdin，latency10、MAX_CYCLES1,000,000、程序/答案/动态指令分子不变；逐项要求stdout退出答案与原课程一致，官方CPU2026 cycles必须与原A36三项完全相等。不同则不把采样作为同源码证据。不会把采样获得的三个IPC替代六项GEOMEAN。

现有ENABLE_CACHE_STATS=0，不能读取恒零的RTL统计寄存器。新增host计数在原posedge之前采样已eval的fetch/trace/RS/occupancy/branch pending/cache event信号，记录前端空、派发完全受阻、RS issue、ROB/RS/LSQ满及占用、branch pending及其与ready RS的重叠。读取现有predictor反馈正确率和最终debug值。只采样reset=0且core halted=0的周期，样本数与外部内存完成周期可能不同；各类停顿重叠，不能相加成总损失。

branch_pending_with_ready_rs只是“存在就绪条目”的上界，不证明它比恢复分支更老。I-cache事件来自原primary cache，不包含全部L0过滤命中。predictor反馈统计保留原同bank优先规则，不等于完整所有执行分支数量。这些边界将随结果记录。

所有采样在对话汇报本文件后开始，只用于决定下一项IPC架构改动。当前A38已独立完成指令SRAM offered-read和每宏命令分发源码，尚未测量；本采样不验证A37/A38，不采用或宣称目标完成。Windows原生，不使用WSL。
