# A92展开失败与A93/A94新源码

A92集中任务原PID97984已不存在，监督记录SERIAL_TIMING_FAILED，只有timing阶段返回1；尚未生成PPA、timing-only或IPC结果。错误来自原冻结synth.log：

`F:\\CPU2026CourseRuns\\ER1_A92_tier3_20261006\\source\\rtl\\backend\\rv32_lsq.v:1215: ERROR: Failed to detect width for parameter \HEAD_LOAD_PACKET_ACTIVE!`

原因是我新增A91常量HEAD_LOAD_PACKET_ACTIVE被更早的REPORT_IDENTITY_WIDTH宽度表达式引用，课程Yosys前端无法展开该前向常量依赖。这不是频率测量值，也不是工具/库版本不匹配。旧A92源码157文件、配置、管理器、审阅/准备脚本、预报与日志保持冻结，未修改或重启；记录绑定原PID/rc1/日志哈希。

A93独立新增数据WB快存储覆盖：基址仍须原保存ready且没有匹配WB，继续使用保存地址类别；数据ready允许原保存ready OR 合法匹配WB-ready，实际LSQ数据仍原PRF最高WB优先级。只拓宽当前数据就绪控制，不把WB data值恢复到地址加法/类别。原严格条件R&&!W蕴含新R||W；同输入下原快机会保留，整体IPC和映射时序未知。原explicit-data非零、MMIO/未就绪基址等保持RS路径，真实分配与顺序存储副作用/全GEN不变。

A94修正展开声明顺序：把原完整HEAD_STORE_ACK_ACTIVE→HEAD_LOAD_IDENTITY_ACTIVE→HEAD_LOAD_PACKET_ACTIVE声明块前移到REPORT_IDENTITY_WIDTH/SAVED_IDENTITY_QUERY_LSB之前；同时将PARALLEL_STORE_ADDRESS前移到新FAST_STORE_SAVED_ACTIVE之前，处理扫描发现的同类常量依赖。所有被移动声明表达式逐字不变，没有改变字段、参数值、算法、状态或握手。不是新增性能优化，也尚未确认重新编译通过。

当前待测源码A94，A93/A94无额外HDL/lint/形式/仿真/综合/STA/单元作业。主E EU40源码与原快照相同，工作在F盘，不用WSL。最新完整测量仍A83：IPC1.074413717/Fmax244.683393MHz/含SRAM35647.034498μm²，六项性能答案通过，19正确性未跑；不能借给新源码。目标严格>300MHz/IPC≥1.1/含SRAM≤36000μm²与完整RV32IM/OoO/顺序提交/MMIO/参数化仍未达成。

下一步用成功A83的冻结依赖/工具作参考，准备独立新运行表征整个修正后的批次；先在对话报告，再开始，保留旧失败任务。不增加逐改测试或自动重试旧PID。数值明确改善并采用前仍需完整19正确性及M/恢复/全GEN/MMIO/参数覆盖。
