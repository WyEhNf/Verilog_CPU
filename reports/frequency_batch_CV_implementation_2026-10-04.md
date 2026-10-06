# CV：LSQ 结果与物理目的并行选择，尚未测试

CV 继承 [CU1 七组实现](E:/Verilog_cpu/reports/frequency_batch_CU1_implementation_2026-10-04.md)，新增 LSQ 结果选择与目的物理寄存器选择的融合。准备候选为 [CV](F:/CPU2026Candidates/frequency_research_20261003/CV_lsq_parallel_report_destination/candidate.json)，冻结输入为 [architecture_CV_20261004](F:/CPU2026CourseRuns/architecture_CV_20261004/source_manifest.json)。采用前的 CU1 工作树完整备份在 [pre_CV](F:/CPU2026Candidates/pre_CV_worktree_20261004/backup.json)。

**没有启动新的 HDL 编译、lint、仿真、综合、STA 或形式验证。CV 的频率、IPC、面积与正确性均未知。** 普通整数流水仍为十级，课程版本、39 项参数、容量和内存延迟 10 保持此前配置。源码身份核对只确认文件，不能证明功能、语法、面积或时序。

## 串行依赖的消除

原 LSQ 从 16 个完成行中选出 value、完整 ROB tag 和 LSQ tag；backend 随后解出 LSQ slot，再读取 `lsq_phys_mem[16][6]`，最后构成 producer 的目的编号。两个行选择串联。

CV 把原 16×6=96 位、无 reset 的分配 payload 移到 LSQ。report 的每行拼接增加六位物理目的，原有 report 选择同时选出 value/tag/phys。backend 删除旧表和第二次读取，直接消费 LSQ 的新输出。当前 report 宽度由 67 变成 73 位，16 位分组数量仍为五。数据选择树增加六位，串行的第二次表读取消失；这只是结构推导，没有延迟或频率收益的测量。

先前研究稿误认为存在独立的 load-completion 寄存缓冲。源码实际上将完成值保存在各 LSQ 行，再组合选出报告。此次没有新增所谓 completion buffer，也没有增加六位报告寄存器；96 位存储移位、没有复制。旧表本来就是 16 行，不能声称从 64 行缩成 16 行。

## 人工边沿与身份核对

- 原 map 写入资格是 `d_valid & lsq_alloc_fire & !reset`。CPU 中 `lsq_alloc_valid=d_valid & (is_load|is_store)`，所以 `lsq_alloc_fire` 必然蕴含 `d_valid`。搬迁后的资格为 `lsq_alloc_fire & !reset`，有效 CPU 分配边沿相同。
- 地址仍使用完整 `alloc_lsq_tag` 的 slot slice，物理值仍来自同一 D-stage `d_new_phys`；相同行多 lane 匹配仍保留原最高 lane 优先级。
- LSQ 原组合 alloc-fire 未单独排除 recovery；旧 backend map 也未排除。本次保留这一资格，没有套用 LSQ 的正常 payload 写入条件而悄悄改变边沿。
- 原 report 的低 67 位位置完全保留，新物理编号追加在高位；完整 tag/generation、完成错误、报告年龄选择、ready、recovery、retire 均保留。后端所有 ROB valid/generation 与恢复年龄防护仍在。
- 没有有效 report 时，新目的输出为零；旧 backend 对零 LSQ tag 的无条件查询可能返回 slot0 的旧 payload。因此只主张有效事务的目的、数据和身份一致，不主张无效 payload 位逐位相等。
- 现有两个独立 LSQ fixture 使用命名端口，新输入尚未连接；它们原有输出不依赖新物理编号。未来若运行这些 fixture，应明确新端口，不能把缺失端口警告当作功能通过证据。

## 当前指标与剩余工作

最近实际测过的 CD1 仍为 99.65936739659368 MHz、IPC 0.7823728642153719、含 SRAM 面积 49851.29213392186 µm²、正确性 16/19。这些数字属于 CD1，不属于 CV。CV 相对 CU1 修改两个 RTL 文件，相对 CD1 修改九个 RTL 文件。

继续检查执行单元本地恢复取消、producer 的 ROB 存活查询到 RS 唤醒的串行段、metadata-only RS 和已有匿名 mapped driver 的真正输入。剩余方向必须给出保留、采用或暂缓的源码理由，不能在本轮未测试时把猜测记为收益。测试前先汇报最终冻结版本、完整改动、风险和一次统一 Windows 原生课程测试范围。
