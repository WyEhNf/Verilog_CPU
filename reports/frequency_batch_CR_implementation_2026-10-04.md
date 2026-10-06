# CR：当前未测试的频率优化实现

主工作树采用 **CR**，在 [CN 的九组修改](E:/Verilog_cpu/reports/frequency_batch_CN_implementation_2026-10-04.md)上增加 DIV、ROB、MDU 与 Icache 四组修改。冻结输入 [architecture_CR_20261004](F:/CPU2026CourseRuns/architecture_CR_20261004/source_manifest.json)共 157 个文件；CN 工作树原件保存在 [pre_CR](F:/CPU2026Candidates/pre_CR_worktree_20261004/backup.json)。中间 CO、CP、CQ 候选及逐份 patch 均保留。

**没有启动新 HDL 编译、lint、仿真、综合、STA 或形式验证。CR 的频率、面积、IPC 和正确性全部未知。** 当前仅做源代码准备、人工语义推导、既有网表/报告/库阅读、源码身份校核。十级普通整数流水、容量、39 项课程参数、工具链和 SRAM 保持此前配置；这四组没有增加功能寄存位或额外周期。相对 CN 修改四个 RTL 文件，相对已测 CD1 共七个 RTL 文件有后续修改。

## 本轮增加的四组

| 候选 | 实施位置 | 结构变化 | 保留的行为 |
|---|---|---|---|
| CO | `rtl/rv32m_divider.v` | 请求、归一化、迭代、结果和两份商余数缓存使用互斥命令、16 位事件选择和寄存器写入域；odd/digit/borrow/sign/normalization 控制按实际消费者分组 | 原 radix-4、三个并行试减、3D 准备边沿、所有 scalar 状态、fast/bypass/finish 边沿、reset/flush 清零、ready/live-tag 和特殊值优先级 |
| CP | `rtl/backend/rv32_rob.v` | head/选中年龄/occupancy/preview 按四行分发，失效掩码与回收共用逐行区间判断；76 位恢复描述符局部写入；恢复 lane live/generation 和选中目的载荷静态读取 | 原最老优先及 lane 同龄顺序、完整 generation、preview/hold/apply、未复位 descriptor payload、valid 清除优先级、提交与 slot 身份 |
| CQ | `rtl/backend/rv32m_mdu_reservation_station.v` | 94 位原 launch payload 改为局部 reset/capture 写入；56 位完成载荷按 16 位选择 MUL/DIV 来源 | 原一项 launch buffer、同拍消费/补充、pending valid 先清再置、inflight count、MUL 优先、所有 MUL_IMPL 参数行为及响应握手 |
| CR | `rtl/cache/rv32_icache_nonblocking.v` | 四个返回字分别计算 JAL 目标；response address 先分发至四份算术；字位移在 signed22 位范围中计算；小宽度 grant 后做 16 位目标选择 | 最早前向出行 JAL，否则最早出行 JAL；原 unsigned forward 比较含 wrap、cache/MSHR 存在检查、预取策略、MSHR 复用和同一个响应边沿 |

以上宽度按当前 ROB64、TAG17、PHYS6、OP6 计算。CO 原载荷寄存位为 `119+32+65+32+128+128=504`，原 34 位 3D 寄存器仍在；CQ 为 `6+64+17+6+1=94`；CP 为 `64+2*6=76`。它们只是同一状态的写入电路重排。这个数量说明没有主动增加状态，不等于已综合测得面积不变。

## 人工语义推导与边界

DIV 的命令来自原嵌套条件：clear；非 clear 且 idle 接收；busy/prepare 的小幅值旁路或归一化；busy/非 prepare/finish；其余迭代。clear 与全部有效写入互斥。结果仍在旧寄存器采样边沿产生；consume/discard 清 valid 后，同边沿新结果置 valid 的原优先级保留。所有原清零 payload 在 reset/flush 时仍写零，不能以“无效就可忽略”为理由删掉。原 request 的 DIV/REM overflow 判断与已保存状态中只对 DIV 置 overflow 的差别亦保留。

ROB 的选中年龄在无匹配时为 `ROB_ENTRIES+1`。分发使用 COUNT_WIDTH，保留 64-entry 下的 65 哨兵；不能只截成六位。只有保存 slot/age 时才按原赋值截成 SLOT_WIDTH。保存条件包含非 reset、非 apply、hold、preview、非 saved-valid，与原 if/else 的同边沿条件相同。descriptor 与 reclaim 共享的谓词均为旧 `valid && age>chosen_age && age<occupancy`，reclaim 额外要求 preview 和 rd_we。

原 Icache 扫描首先保存最早出行目标，直到遇到第一个前向目标；此后不再替换。因此 parallel grant 先判断是否有前向候选，再选择这一类中最早的字，与旧顺序一致。令 J-immediate 为 I、字位移 d 为 0/4/8/12，原目标 `(base+d)+I` 与 `base+(I+d)` 在 32 位模加法下相等。I 的范围为 −1048576 至 1048574，I+d 在 signed22 位内；此后符号扩展到 32 位。PC 的 unsigned 比较仍使用 `base+d`，没有把 wrap 情况错误替换成 immediate 的正负判断。

这些是**人工源码推导，尚无 HDL 编译、等价性或功能测试证据**。面积、门数量、实际扇出、slew、Fmax 和 IPC 的新结果均不能从这些推导宣称。

## 已有负载证据与本轮覆盖

[CD1 详细名义负载](F:/CPU2026Proofs/CD1_existing_mapped_loads_detail_20261004/loads.json)与[连接追查](F:/CPU2026Proofs/CD1_existing_mapped_loads_detail_20261004/remaining_source_traces.json)均来自现成映射文件。名义 Liberty 输入电容不是新版本 STA 延迟。

| 旧 CD1 记录索引（从零计） | 已有驱动/负载 | 对应措施与定位限制 |
|---|---|---|
| 39、40 | DIV 控制，164/161 个脚，71.96/71.53 fF | CO 去掉嵌套状态命令直接控制整组载荷的结构；源范围已定位至 DIV，单个匿名 FF 的具体状态名称尚未完全反推 |
| 61、62 | DIV 接收，110/142 个脚，59.93/57.19 fF | CO 的 request payload ownership，CQ 的 launch payload；scalar handshake 仍保留 |
| 43 | MDU/issue，148 个脚，70.71 fF | CQ 局部接收写入；不能仅由一个 alias 指定全部负载属于 launch |
| 60 | ROB descriptor 捕获，138 个脚，60.85 fF | CP 在最终捕获资格之后分发，原恢复边沿未移 |
| 42、73、91 | ROB FF/恢复年龄资格，约 47.61–70.91 fF | CP 分发年龄边界并共享 interval；具体 FF 身份仍有未知部分，不声称每个脚已经修复 |
| 74 及同族 | memory-bridge/Icache 输入，140 个脚，50.46 fF | CR 对返回地址的四份算术/比较先分发。其 error-tree leaf0 上游表明至少有 address 字段，不能笼统写成 inst sign；其余同族位仍需继续追查 |

## 当前测量身份和剩余工作

最近一次测量是 **CD1**：Fmax **99.65936739659368 MHz**；IPC **0.7823728642153719**；含 SRAM 总面积 **49851.29213392186 µm²**；正确性 **16/19**，pi/qsort/tak 超时。它尚未达 300 MHz；IPC 超出先前 −10% 范围；总面积也高于 Tier3。不能将这些数字标成 CR，或说本轮已经保证三项指标。

本轮改变的是有负载证据的结构，没有继续盲加流水。接下来仍有可行动的检查：Dcache SRAM tag 写资格的剩余消费者；未完全定位的 Icache/address 字段；MUL partial-product 的 operand/control fanout；ROB reclaim destination decode 的局部消费者。更大的 metadata-only RS、producer-local cancellation、load phys 同边沿 capture 和 frontend lookahead 方向仍见 [CM 完整研究](E:/Verilog_cpu/reports/frequency_batch_CM_implementation_2026-10-04.md)，未实施部分不能写成已完成。

仍遵守先完成修改、测试前汇报的要求。只有当前有依据的可落地修改完成，再报告统一冻结版本、未解决事项与课程测试范围，才启动一次 Windows 原生后台测量；当前不启动。

## 原始资料

[RISC-V RV32I 官方规范](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)给出 JAL 的 signed、2-byte offset 和 ±1 MiB 范围，支持上面的即时数边界推导。[BOOM instruction-fetch 文档](https://docs.boom-core.org/en/latest/sections/instruction-fetch-stage.html)讨论 fetch packet、PC/预测元数据和阶段中的预译码；[NLP 文档](https://docs.boom-core.org/en/latest/sections/branch-prediction/nl-predictor.html)说明需要在一批取指中识别控制流位置。这些提供更大前端设计的参照；CR 的精确预取优先级仍按本项目源码推导，并不是直接采用 BOOM 的 BTB 或声称得到其时序结果。
