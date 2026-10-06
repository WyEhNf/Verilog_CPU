# EF Windows 原生课程综合结果

EF 完整组合完成一次课程综合/STA：**370.477569 MHz**，最低周期 **2.69921875 ns**，含 SRAM 总面积 **49116.955854 μm²**。相对 EA，频率 **+12.8799%**、面积 **-0.3289%**。EF 主工作区仍对应本次冻结源；EG/EH 是独立未采用源码备选。

|指标|EF 实测|要求对应|
|---|---:|---|
|频率|370.477569 MHz|超过原 300 MHz 和程序测量前 350 MHz 工作判断值|
|组合面积|30226.818600 μm²|课程固定计价|
|时序面积|11064.470400 μm²|与 EA 相同；不等于源码声明计数|
|SRAM 面积|7825.666854 μm²|已计入总面积|
|总面积|49116.955854 μm²|原基线 +6.0619%，在 ±10% 内；仍高于 Tier3 的 36,000|
|IPC/功能|未测|IPC 下限 0.882115146585 和 Tier3 1.0985 均未证明；不能沿用 DM1 的 IPC|

## 当前限制路径

只分析课程已生成的五条路径，没有新增 STA，也没有枚举所有端点。端点私有映射名不能直接认定为某个公开字段。

|序号|起点|终点|到达时间 ns|
|---:|---|---|---:|
|1|`_619153_/QN`|`_616714_/D`|2.6398|
|2|`_620376_/QN`|`_620843_/D`|2.6327|
|3|`_620376_/QN`|`_621012_/D`|2.6327|
|4|`_620376_/QN`|`_621181_/D`|2.6327|
|5|`_620376_/QN`|`_621350_/D`|2.6327|

第一条的显式层级经过 LSQ report_bound、直接 report grant、RS wake port 5、entry 10 基址 ready、共享 store packet 选择、normal ROB live 查询，末段出现 LSQ mask owner 写控制。关键边界到达：LSQ grant 0.838 ns、RS wake-valid 1.078 ns、共享 probe base-ready 1.319 ns、store packet grant 1.768 ns、normal live 查询 index 1.902 ns、LSQ mask owner 写控制 2.548 ns。可优先让共享探测只读已有注册基址；普通发射旁路不必因此整体延后。EH 较广的快慢通知拆分也能断开这类联系，但对 load/MDU 直接依赖发射有一拍机会代价，暂留备选。

后四条经过 Dcache response_read、响应生命周期/输出选择、LSQ response_query 行号、查询到的 offset、response_extract。第二条的 LSQ 查询 index 在 1.820 ns、row select 在 1.901 ns、offset64 控制在 2.022 ns。最大单门 AOI221xp5 为 0.2913 ns，50 个负载、23.7029 fF；后段另一个 AOI21xp33 为 0.1909 ns、18 个负载。需要分别处理缓存响应选择负载与查询后串行提取，不能只针对第一条改完就宣称全局频率还会提升。

EF 的分配地址删除有实际时序收益，但可能延后 store 地址可用时刻。EG 并行地址备选保留原分配当拍行为；新面积和新频率尚未知。继续做源码结构工作；任何后续测量前先汇报完整组合。当前没有 Verilator CPU 构建、IPC 或功能程序，本次 timing-only 不证明完整正确性。

课程保持 Windows 原生固定 Yosys/ABC/OpenSTA、ASAP7 RVT TT/FakeRAM、2 ns 请求映射时钟、0.05 ns uncertainty、5 fF 输出负载、reset=0、无寄生。2 ns 下的负 slack 不代表 300 MHz 失败；以上频率来自原课程周期搜索。未使用 WSL。

## 原始证据

- 测量：`F:\CPU2026CourseRuns\architecture_EF_20261005\result\timing_only.json`
- 源码 manifest SHA256：`3e90b25b005f6e8fc5b2dd625e38603d349c2c2027b7eaecf3efd4093c0651f2`
- 工具 manifest SHA256：`c08263a362cd79513f17701b6328f8fb14d41a315539006d7b7dd71113ee3fb5`
- 官方 report SHA256：`43622417c4e7eb1ca1ca1ae892f1c20e68040b30dcc2c828c9f217990b0660a5`
- 标量摘要：`F:/CPU2026Proofs/EF_existing_reports_20261005/summary.json`
- 映射路径分析：`F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json`
