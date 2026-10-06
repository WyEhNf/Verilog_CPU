# ER1 基线 IPC 与已测 PPA

ER1逻辑基线：**IPC 0.76303979、Fmax 371.41820820MHz、含SRAM面积 49638.890694 μm²**。

IPC来自Windows原生Verilator5.020、六个官方perf（latency10、原metrics动态指令数、GEOMEAN），官方答案全部通过。
构建只做LSQ局部matches信号的四行/五处标识符兼容重命名；反向字节替换与原文件相同，其他冻结文件逐一hash一致。
频率和面积引用原ER1冻结综合结果，未对标识符副本再次综合；不会声称原源码和副本的SHA相同。不存在EU数据混入。

|程序|动态指令数|周期|IPC|
|---|---:|---:|---:|
|perf_median|6961|12597|0.55259189|
|perf_multiply|21722|32844|0.66136890|
|perf_qsort|139900|265597|0.52673788|
|perf_rsort|195719|184341|1.06172257|
|perf_towers|5278|6053|0.87196432|
|perf_vvadd|4524|4085|1.10746634|
|GEOMEAN|||0.76303979|

新目标要求IPC≥1.1、总面积≤36000、Fmax>300。
IPC还需提高 **44.1602%**；面积需削减 **13638.890694 μm²（27.4762%）**。
当前仅频率满足。六项perf答案通过不是19项正确性全套通过；最终目标和全套功能未证明。

证据：IPC F:\CPU2026CourseRuns\ER1_native_identifier_compat_20261005\result\ipc.json；兼容身份 F:\CPU2026CourseRuns\ER1_native_identifier_compat_20261005\compatibility_identity.json；构建 F:\CPU2026CourseRuns\ER1_native_identifier_compat_20261005\native_build\build_identity.json。
原ER1 timing-only F:\CPU2026CourseRuns\architecture_ER1_20261005\result\timing_only.json；工具manifest F:\CPU2026CourseTools\win54fc150\toolchain_manifest.json。
IPC报告SHA256 `7716a2f74ad9610b9f335c0b8189d9ae20dc2d00b6b163b475d68c5c7618348f`；原综合reportSHA256 `a7f6017c1f5cd4e960c0d6798ddb57026c1fc5f415c082a29a2880f385d1e1af`。

没有新增综合/STA、额外定向测试或回归。原保留字失败构建日志保留。
下一候选为ER1派生A3：ready load提前LSQ地址、原D-cache命中旁路、ROB32/PRF56/RS8/D512。
A3已源码审查，未采用、未测。现阶段继续改善完整组合，不据SRC容量估算宣称已达面积或IPC门槛。
