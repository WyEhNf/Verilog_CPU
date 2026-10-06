# CN：当前未测试的频率优化实现

当前主工作树采用 **CN**，157-file 输入保存在 [architecture_CN_20261004](F:/CPU2026CourseRuns/architecture_CN_20261004/source_manifest.json)。**尚未启动新编译、综合、STA、仿真或形式验证**。CN 包含 [CM 的八组修改和完整研究清单](E:/Verilog_cpu/reports/frequency_batch_CM_implementation_2026-10-04.md)，再增加下述第九组。全部相对 CD1 的 RTL 修改仍只涉及四个文件；课程版本、39 项参数、SRAM、容量、十级流水和功能寄存位数保持此前设计。

## 第九组：LSQ 到 Dcache 的宽请求数据路径

旧 CD1 名义电容排序第 52 项的 AND4 驱动 151 个输入脚、66.29 fF。它在 flatten 后带有 `bus.write_lifecycle_tree.signal_i[0]` 和 `enabled_words(...)[0]` 的名字，但沿原网表输入连接追查，它的上游是 LSQ 的请求选择、恢复资格和已选状态。[只读追查记录](F:/CPU2026Proofs/CD1_existing_mapped_loads_detail_20261004/remaining_source_traces.json)。这个名字不能单独作为“AXI count 计算慢”的证据。

原 LSQ 在同一个组合分支里用请求资格选择 128 位零/forward/store 数据，还分别把两份 32 位源数据左移到 128 位 cache line。CN 保留原来的 `dcache_req_valid`、request_fire、mask、tag、size、ready 与恢复条件，但重新组织数据路径：

1. 用两个 16 位选择域在 forward/store 的 **32 位 access-relative 数据**之间选择。
2. 共用一份 32→128 位 byte insertion。四段中间宽度为 40、56、88、128 位；amount leaf 最多控制 16 位。
3. 在移位之后，用八个 16 位有效性域生成原来的零/数据输出。晚到的 request-valid 不经过四段移位。

按源码推导，对全部 0–15 byte offset 保留原来 `{96'b0,word} << (offset*8)` 的截断语义。有效 load/store 分支的数据源不变；无效输出仍为零。没有新增寄存器或接口延迟，也没有把数据依赖放入 ready 条件。这些是人工结构推导，未经过 HDL 编译或等价性测试。

## 测量身份与未完成项

**CN 的 Fmax、IPC、面积和正确性全部未知**。最近一次已测源码为 CD1：99.65936739659368 MHz、IPC 0.7823728642153719、含 SRAM 面积 49851.29213392186 µm²、正确性 16/19；pi/qsort/tak 超时。活动状态文件保留 `last_observed_measurement`，当前指标置空，避免将旧结果误标为 CN。

CM→CN 的原工作树备份在 [pre_CN](F:/CPU2026Candidates/pre_CN_worktree_20261004/backup.json)，此前 CD1→CL→CM 的备份及冻结输入也都保留。

剩余只读追查已把若干匿名高负载驱动定位到 DIV 的请求/迭代资格、MDU 接收、ROB 恢复，以及 memory-bridge/Icache 输入字段。仍需区分共享控制与数据位的多消费者，不能见到高电容就复制整个 payload，或依据一个别名修改错误模块。更大的 RS/PRF/唤醒/前端架构方向仍列在 CM 报告中，不能声称已经穷尽。

**当前不启动测试。** 继续排查这些已发现的节点、完成有依据的源码修改后，先向用户报告具体冻结版本、结构变化、未解决问题和统一测试范围，再按授权在 Windows 原生环境后台执行课程流程。
