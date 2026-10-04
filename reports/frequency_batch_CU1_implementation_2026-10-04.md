# CU1：当前未测试的频率优化实现

主工作树采用 **CU1**，冻结输入为 [architecture_CU1_20261004](F:/CPU2026CourseRuns/architecture_CU1_20261004/source_manifest.json)，共 157 个文件。此次在 [CR 四组实现](E:/Verilog_cpu/reports/frequency_batch_CR_implementation_2026-10-04.md)上加入 MUL 实际消费者分组、Dcache tag SRAM 端口分组、ROB 回收目的预译码三组修改，共继承 CN 之后的七组实现。相对 CN 修改六个 RTL 文件，相对已测 CD1 修改八个 RTL 文件。CR 工作树备份在 [pre_CU1](F:/CPU2026Candidates/pre_CU1_worktree_20261004/backup.json)；CS、CT、CU、CU1 源码候选均保留。

**尚未启动任何新 HDL 编译、lint、仿真、综合、STA 或形式验证。所有新性能与正确性指标未知。** 普通整数流水仍是十级，没有新增功能状态、流水周期或恢复周期；39 项参数、课程工具版本、内存延迟 10 和存储容量保持此前配置。源码身份校核只核对文件，不构成逻辑正确性或时序验证。

## 新增三组

| 组 | 原结构与问题 | 已实现的变化 | 边沿、行为和代价边界 |
|---|---|---|---|
| CS：MUL 消费者 | 32 个部分积共享 multiplicand；每个 multiplier bit 选择整份 32 位；CSA 写入 leaf 仍管 32 位 | multiplicand 分为四个八行域；每个 multiplier bit 分两个 16 位域；signed correction 分组；S1/S2 数据、metadata、输出均按 16 位写入或选择 | modulo64 乘法、CSA/CPA、原全部寄存位、valid/ready/live/discard 不变。保留原 data 可在 reset edge 覆写、metadata/output 在 reset/flush 保持的差别。未额外拆 CPA 或加级 |
| CT：Dcache tag 端口 | 已有网表 `tag_array_write` 驱动 120 脚，61.944211 fF，超过其 NOR2 23.04 fF nominal limit；tag ports/地址 mux 等共用它 | local/refill 的 entry/tag 选择按 16 位分发；hold forwarding 按 way 分发 metadata；demand/nextline tag SRAM 按已有 way 单独实例化，write、enable、地址选择、data 分别分发 | 每个 way 仍使用原全局 write mode，即使 wmask=0；不会在另一 way 写时变成 read。读边沿、write/idle rdata 无效语义、消费者 hold、mask/entry 优先级不变 |
| CU/CU1：ROB reclaim | 每行 eligible 与物理编号参加每个非零目的寄存器匹配；直接 flat cross-product 存在控制广播 | 当前六位物理编号按 high3/low3 预译码；eligible 只先参与八个 high code，再与八个 low code 交叉。功能 inversion 边界保留每个 code 的局部消费者 | 完整 eligible、非零目的、所有行 OR、重复目的去重和原 balanced bit count 不变。CU1 额外保证 PHYS_ADDR_WIDTH=1 没有零宽度 slice/cast；当前 PHYS64 逻辑不变 |

CS 和 CU 是从当前源码消费者数量得出的结构改法，**没有实测证明它们是全核最慢路径**；CT 的 120-pin/61.94 fF 数字来自旧 CD1 现成映射记录，也不是 CU1 的新测量。[旧负载与直接 sink 记录](F:/CPU2026Proofs/CD1_existing_mapped_loads_detail_20261004/loads.json)第 58 项（从零计）包含 demand/nextline tag 地址选择。不能把这个 nominal load 换算成新 Fmax。

## tag SRAM 宏规则的源码依据

读取课程固定版本的 [fakeram.py](F:/CPU2026CourseRuns/architecture_CD1_20261004/source/.deps/RISC-V-CPU-2026/scripts/fakeram.py:73)可见：宏名字和 lane area 使用 `DEPTH × WRITE_GRANULARITY`；`lanes=WIDTH/WRITE_GRANULARITY`；每个 mask lane 单独实例化宏。原每个 `512×38, granularity19` wrapper 对应两个 `512×19` 宏，新每个 way 的 `512×19, granularity19` 对应一个，因此两个查询副本合计仍为四个 `512×19`，存储位数和规则估算 SRAM 面积相同。

同一源文件生成 `ce_in = en & (~we | wmask[lane])`、`we_in=we`。拆 way 后逐 lane 输入保持这些表达式的原值。课程 [sram_fakeram.sv](F:/CPU2026CourseRuns/architecture_CD1_20261004/source/.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv:31)在 write/idle edge 将 rdata 置无效，read edge 才读 words；新实例保持原全局 we，不能让未命中 mask 的 way 误读。该结论来自源码推导；**尚未实际 elaborate/map CU1，真实宏计数、标准单元面积与 STA 仍待统一测量**。

## 本轮七组人工保留性核对

DIV、ROB descriptor/query、MDU launch/completion、Icache JAL 并行选择的条件和宽度推导见 [CR 报告](E:/Verilog_cpu/reports/frequency_batch_CR_implementation_2026-10-04.md)。新三组进一步保留：

- MUL 原 `req_src2[row] ? ({32'b0,A} << row) : 0` 改为先对 A 的两个 halfword mask，再零扩展/常量移位；仍得到同一 64 位部分积。signed correction 仍为 `{~operand,0}` 和 bit32 加一。
- MUL 30 位 S1/S2 metadata 和 24 位 output metadata 保留原 reset/flush 排除条件；原 S1/S2 data 的 unreset 覆写路径不加这个条件。原 opcode case 的 MUL 低半、MULH/MULHSU/MULHU 高半、其他零值保留。
- Dcache tag selection packet 为 `{entry,tag}`，以完整 slice 路由，不缩短 entry。每个 way 的 wmask、tag data slice 和 rdata slice 对应原拼接顺序；read address 与 write address 保持原选择。
- ROB `eligible && destination==phys` 分解为 `eligible && high==phys_high && low==phys_low`。phys0 强制零；编号超出 PHYS_REGS 不会命中；再跨所有行 OR，因此原 distinct-destination 数量和重复处理不变。

以上均为人工推导，没有语法、等价性或功能测试证据。新增组合门会影响总面积；没有额外状态或 SRAM 位并不能证明面积 ±10%。

## 指标身份与继续工作

活动身份 [active_frequency_implementation_20261004.json](E:/Verilog_cpu/build/cpu2026/active_frequency_implementation_20261004.json)的 CU1 当前指标置空、tests_started=false。最近测过的 CD1 为 **99.65936739659368 MHz / IPC 0.7823728642153719 / 含 SRAM 面积 49851.29213392186 µm² / correctness 16/19**。300 MHz、此前 IPC/面积控制要求及最终 Tier3 均未被新证据证明。

剩余工作仍包括完全定位已有网表的匿名输入字段、检查 producer/ROB 存活资格到 wake/issue 的串行段，以及评估 metadata-only RS 和 load destination capture 等较大方向。源码审阅应说明采用或暂缓每项方向的依据，不重复实施已经存在的并行 DIV、CSA→CPA 分拍或 balanced RS rank。没有依据时不能把“更深流水”当作默认答案。

当前不启动测试。完成仍可落地的方案后，先报告具体冻结版本、变化、未解决问题和统一课程测试范围，再按授权在 Windows 原生环境后台运行。
