# DM1 后台测量期间的进一步架构实现

DM1 测试前报告已先交付。北京时间 2026-10-05 03:31:21 启动一批 Windows 原生课程测量，driver PID 69172，冻结 manifest SHA256 为 `752cbc61415c193c4dd9a5a4b4aa009e7cd99bb0a387acb143e3763c1949725e`。原六项 perf、一次 CPU build 与课程综合/STA 在同一身份下运行，两个既有内存/恢复短程序复用该 CPU。没有另起候选测量，没有使用 WSL。

03:38:01 的 [直接进程观察](F:/CPU2026CourseRuns/architecture_DM1_20261005/measurement_observation.json)确认 driver 存活，当时 build、IPC、综合报告和有限程序均未完成。该文件随后可能更新，最新阶段以文件及实际进程为准。当前 [主版本](E:/Verilog_cpu/build/cpu2026/active_frequency_implementation_20261004.json)仍是 DM1；下列候选只写入独立目录，不改变这批输入。

## 进一步发现

[RS 源码](E:/Verilog_cpu/rtl/backend/rv32_reservation_station.v:148)导出的 base ready/value 使用 `src1_ready_effective` 与 `src1_value_effective`，包含本周期 wake。DM1 虽然移除了 store 的宽 tag 全表关联，但组合拓扑仍允许 load report→wake→store grant→base/imm→AGU→LSQ。普通 issue 已有后续寄存边界；提前地址探测绕过了这个边界。这是可选微架构快路的拓扑问题，不是再加一个全局整数流水级就能完整描述的问题。

[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)区分 ALU 的 fast wake 与 loads 等操作的 slow wake。[BOOM LSU](https://docs.boom-core.org/en/latest/sections/load-store-unit.html)允许 store 地址和数据分开就绪，保留尚未执行的部分，同时保持有序提交后再写内存。它们支持把唤醒、调度和地址发布职责分开考虑；下面两项按本项目的握手、tag 与恢复实现，没有照搬 BOOM 的 bypass 或 replay 契约。

## 已写入的两个替代候选

两者都从 DM1 派生，彼此是替代关系，不叠加。DO1 在 DO 初稿上继续修正了连续探测的选择。未编译、lint、仿真、综合、STA 或形式验证；源码推导不构成性能或正确性证明。

| 候选 | 切断方式 | 当前配置新增声明状态 | 主要代价 |
|---|---|---:|---|
| [DN](F:/CPU2026Candidates/frequency_research_20261003/DN_store_registered_probe/changes_vs_DM1.patch) | 提前地址探测只读 RS 已保存的 ready/value；普通 issue 仍使用同周期 wake | 0 位 | 若 base 在 wake 同周期就发射并释放 RS，提前探测不再抓到该任务，需要正常 ALU 地址更新 |
| [DO1](F:/CPU2026Candidates/frequency_research_20261003/DO1_store_address_inflight/changes_vs_DM1.patch) | 保存选中的 `{完整 ROB tag, 完整 LSQ tag, base, imm}`，下一周期才进入共享 AGU；选择时排除暂存任务的完整 LSQ tag | 98 位 payload + 1 位 valid | 提前地址发布增加一周期；新增寄存器、写控制和排除比较要综合计价 |

DN 新参数 `REGISTERED_BASE_PROBE` 默认 0；后端仅在已有 `STORE_RS_LINKS` 条件启用。ready 和 value 必须一起改为保存值，避免跨周期混配。`ready_candidates`、普通 issue payload、wake capture、RS release、issue FIFO 和所有正常 ALU 更新未改。若 store 仍等数据而未发射，下一周期会读到保存的 base；若已发射，原 [ALU→LSQ 地址/数据更新](E:/Verilog_cpu/rtl/backend/rv32_backend_joint.v:871)仍执行。这能改变年轻 load 被未知 store 地址阻塞的时长，所以不能声称 IPC 一定不变。

DO1 仅在 `STORE_RS_LINKS` 启用一组 packet 暂存；其他 EARLY_STORE_ADDRESS=2 调用维持原直接连接。98 位 packet 沿用现有每 16 位分散写控制的 bank。流水不是阻塞队列：每周期接收一个选中探测，旧 packet 当周期发布，新 packet 在边沿替换。DO 初稿会因 LSQ pending 尚未在边沿清除而重复选择上一 packet，降低有效任务吞吐；人工周期推导后，DO1 以保存的完整 LSQ tag 排除该 owner，四行一组分发，仍具备每周期选择不同 store 的结构能力，实际吞吐未测量。没有占用或释放第二个 RS 发射槽，没有重复执行 store data，也没有增加全局整数流水级。

DO1 的发布必须查询 **保存的完整 ROB tag** 的 valid/generation；不能对当前新选择的 tag 做检查后发布旧 packet。LSQ 则继续用保存的完整 LSQ tag 匹配行及 generation。`selected_slot` 仍属于输入任务，仅用于无 inline metadata 的立即数读取；输出 ROB authority 使用独立 `probe_slot`，保持两端任务身份一致。

| DO1 场景 | 处理 |
|---|---|
| 同边沿 RS 发射、link 释放 | packet 已保存完整 tag 与操作数，后续无需再读释放后的 RS 行 |
| 同一 store 的 pending 尚未清除 | 当前有效 packet 的完整 LSQ owner 被排除；下一任务仍按原 circular policy 选择 |
| 正常 ALU 更新与探测同时到达 | 原 LSQ 更新优先级保留；二者针对同一任务计算同一架构地址 |
| LSQ/ROB 槽位复用 | 发布使用完整 tag/generation，不只保存裸槽号 |
| reset / 外部 flush / branch busy | 立即抑制发布与 capture，并在边沿清 valid；payload 无需 reset |
| 恢复取消年轻 store | branch busy 在 ROB 取消/回收前抑制发布；stage valid 清零。正常 ALU 与已有恢复逻辑继续负责幸存 store |

这些只是对当前源码的人工生命周期审阅。DO1 的 capture、in-flight 排除、ROB 查询或普通 wake→issue 链都可能成为新最慢路径；DN 的地址发布延迟也可能更大。若旧 packet 的 ROB authority 不通过，排除只延迟那一个 LSQ owner 一周期，没有持久置位、删除任务或授权内存写入。没有把删除旧长锥转换成未经测量的 MHz 数字。

## 结果出来后的选择条件

先读 DM1 的实际映射路径。如果已达到 300 MHz，先保留已测版本，并处理已知 IPC、面积和完整正确性缺口；不因为候选已经写好就自动再测。若仍未达标且主要锥仍穿越 wake→store AGU，DN 提供低状态开销的切断，DO1 提供保留唤醒周期任务的明确寄存边界；根据新锥和地址发布需求选其中一个继续组合。若最慢路径已迁移到别处，就围绕新锥发展实现，不启动 DN/DO1 的参数扫描。

03:47:03 已有直接进程观察确认 DM1 driver 仍存活，原生 CPU build 完成，两个有限程序各运行一次并全部通过：96 项/1015 周期与 80 项/1228 周期，均与 DF1 相同。[结果](F:/CPU2026CourseRuns/architecture_DM1_20261005/directed_cases/results.json)属于 DM1 冻结身份，CPU executable SHA256 `40878a37b02717c012fb468440c8349187f527434e932a7c516ebdfb531c9fcd`。当时六项 IPC 和综合报告尚未完成，频率仍未知。

任何下一批测量前都先更新实际实现报告。当前这两个替代候选的准备不启动新测量、不重启正在运行的 DM1、不覆盖预先交付的测试前报告。最近可信频率仍是 DF1 的 294.337453291 MHz；DM1 与两个候选尚无频率结果。原 Tier3 与 ±10% 约束仍有已知缺口，目标未完成。

更新：DM1 随后完成，Fmax **302.154027737 MHz**、IPC **0.782372864215**、面积含 SRAM **51,130.672554 μm²**。[完整结果报告](E:/Verilog_cpu/reports/frequency_DM1_measurement_2026-10-05.md)记录身份核对与尚未满足的要求。新最慢样本经完成仲裁与 PRF 旁路进入分配，旧 RS 共享 AGU 未出现在五条最差样本中；因此 DN/DO1 的启用条件未发生，仍未采用、未测。以上等待记录属于测量期间的历史状态。
