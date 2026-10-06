# ER1 A8 实测与 A14 独立源码进度

A8六perf已完成：IPC几何平均 **0.76398585**。课程综合/STA已完成：
总面积 **37638.051294 μm²（含SRAM）**，Fmax **349.48805461 MHz**。
相对ER1，IPC +0.1240%，总面积 -24.1763%，频率 -5.9044%。
频率满足>300；面积还差1638.051294μm²，IPC还需提高43.9817%。目标未达成。

面积分解：组合24127.173540，时序9211.060800，SRAM4299.816954 μm²。
SRAM37个：32×256x8、4×256x20、1×128x128；本次实际宏形状/面积符合A2容量预算。

|程序|动态指令数|周期|IPC|
|---|---:|---:|---:|
|perf_median|6961|11592|0.60050035|
|perf_multiply|21722|31958|0.67970461|
|perf_qsort|139900|227401|0.61521277|
|perf_rsort|195719|244978|0.79892480|
|perf_towers|5278|5729|0.92127771|
|perf_vvadd|4524|4205|1.07586207|

median、multiply、qsort、towers减少周期；rsort和vvadd增加周期。
rsort的244978周期比ER1的184341增加32.894%；不能将整个变化唯一归因为D-cache缩容，ROB/PRF/RS容量与流水线也同时改变。
此次大幅面积收益没有转化为总体IPC收益，下一步必须解决供给和依赖延迟，并重新平衡逻辑带宽与缓存容量。

记录时驱动PID95760存活=True，十九项correctness已收到13通过/2失败，整套结束=False，最新用例=correctness_queens。
当前日志中pi/qsort可能达到默认1,000,000周期上限；尚不能将超时证明为功能错误或证明为仅限额问题。
官方metrics：pi3,117,658、qsort1,097,111、tak1,221,227条动态指令。输出仍必须通过。
课程固定提交README-EN.md明确给出MAX_CYCLES=5000000的自定义测试示例，config.mk也给出MAX_CYCLES=100000000注释示例。
后续统一验证将明确记录合理周期预算、保持latency10及原脚本/答案，不覆盖这次默认限额失败日志，不将其改写为通过。
参考：[官方固定提交说明](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/blob/54fc150ffc290f52aa024209ffb9a29d43856f6d/README-EN.md)。

独立后续候选已实现，均未测试/未采用，A8冻结源码完全未改：

|候选修改|具体结构变化|限制|
|---|---|---|
|A9—A11无用ROB/CDB载荷投影|移除无调用方消费者的载荷及其选择/广播通道，保留PRF架构写回值与实际LSQ/AXI store数据|不是所有诊断接口等价；映射收益未测|
|A12 16行指令缓冲|注册命中从两拍到一拍；未命中原Icache主体仅端口重命名；保留epoch、全PC身份及背压|新增声明2650位状态；命中比例、频率、面积未测|
|A13依赖型load地址直通选择|有效完整LSQ标签匹配的AGU load地址同拍进入原选择寄存器，省一拍；旧store未知地址/data仍阻塞|组合路径变长，需保持频率>300MHz|
|A14单一两路后端组合|FE4/BE2/INT2/CDB2、ROB32/PRF56/RS8/LSQ16、恢复ER1 Dcache1024行2路|PRF读端口8→4、ALU4→2，但退休峰值4→2；SRAM相对A8增加3525.8499μm²，必须由逻辑削减偿付|

A14只是一个具体结构tradeoff，不是参数扫描结果，也没有继承A8的任何IPC/频率/面积数字。
两路峰值2IPC高于1.1目标不等于实际能达标；继续源级面积压缩和瓶颈分析，再汇报下一次完整组合的收益依据和验证范围。
本记录没有启动新的CPU构建、仿真、综合、STA、定向测试或回归。仅读取既有结果并实现独立候选。

原始结果：F:\CPU2026CourseRuns\ER1_A8_tier3_20261005\result\ipc.json；F:\CPU2026CourseRuns\ER1_A8_tier3_20261005\result\synth\opt\report.json；F:\CPU2026CourseRuns\ER1_A8_tier3_20261005\result\correctness.log。
活动测量源码manifest SHA256：9d5d741c51f1703253e3ba78dfb76960690f4c571b1a26cecbafe0a3adae362e。
最新候选manifest SHA256：96fa8efe057c23aa80debb78b66df0cd8e03fe9541e97125a5c4077a09497a3e。
