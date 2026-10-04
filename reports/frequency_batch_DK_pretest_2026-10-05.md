# DK：LSQ 唤醒到 store 地址的结构重排，测试前报告

主工作树 `E:/Verilog_cpu` 已采用 **DK_store_address_prefix**，组合 DH、DI、DJ、DK 四项修改。相对实测 DF1 仅修改五个 RTL 文件；40 个活动源码与 157 个课程冻结输入已保存并核对。**本批尚未运行 HDL 编译、lint、仿真、综合、STA 或形式验证，频率、IPC、面积与功能结果均未知。** 本报告先交付，测试仍未启动。

[冻结输入](F:/CPU2026CourseRuns/architecture_DK_20261005/source_manifest.json) SHA256：`21fd42b7d1471948a252f5d955c191f194510b11f945d88b0a7051821c11de9f`。DF1 源码与旧活动身份保存到 [备份](F:/CPU2026Candidates/pre_DK_worktree_20261005/backup.json)。完整差异为 [changes_vs_DF1.patch](F:/CPU2026CourseRuns/architecture_DK_20261005/changes_vs_DF1.patch)，[源码身份记录](F:/CPU2026CourseRuns/architecture_DK_20261005/implementation_review.json)同时记录实际四个准备脚本的 SHA256。

## 根据现有数据选择修改

最近已经完成的 [DF1 结果](E:/Verilog_cpu/reports/frequency_DF1_measurement_2026-10-05.md)是 **294.337453 MHz / 3.3974609375 ns**，对 DD 提升 7.4447%，IPC 仍为 0.7823728642，含 SRAM 面积为 51,368.530674 μm²。达到 300 MHz 还需缩短 0.0641276042 ns。这里的数值不能写成 DK 的数值。

DF1 五条最差检查集中在 LSQ report → 取消资格 → RS wake → 提前 store 地址这一长组合链，各路径无超载门。此次重点是减少串行依赖；同时修正现有映射负载清单证实的 refill merge 最终控制扩散。没有因阶段总数不足而再插一级，也没有削减 OoO、队列容量或指令支持。

| 修改 | 当前实现 | 预期作用与代价 |
|---|---|---|
| DH，字节 merge 资格 | 每字节先计算 `response_store && response_mask[byte]`，再经过独立保留叶选 8 位数据 | raw command 只到 16 个字节资格；最终资格只选 8 位。增加真实组合单元；不是当前五条最差路径的直接收益保证 |
| DI，LSQ report 取消资格 | 各 LSQ 行使用同一恢复 snapshot 和原 helper 并行计算 cancel；cancel 随 tag/value/phys/unretired 同一报告选出 | 移除选中 ROB tag 后的减法与范围/分支年龄比较。复制 16 份短资格计算与 descriptor 分发；没有新增功能状态 |
| DJ，store/RS one-hot 选择 | 环形 LSQ 选择直接生成 one-hot grant；每行最低 RS 匹配也以 one-hot 随包选出 | 去掉 LSQ 选中 index 再比较、RS index 编码/选择/分发/再解码。保留完整 tag 比较和两种优先级；组合包 38→46 位，16 位分组仍 3 个 |
| DK，共享地址加法 | 八个 4 位加法块预计算 carry=0/1 两种 nibble；三级 carry prefix 决定各块进位 | 替换旧共享 AGU 的长进位链，保持完整 modulo-2^32 加法。仅替换一个共享 adder，实际面积/映射深度待测 |

## 人工语义审阅

DI 不改变 report valid、最老 load 选择、reported 状态、ready/ack 或退休顺序。对每行标签 t 定义原资格 `C(t)=apply && (!t[0] || age>=occupancy || age>branch_age)`，其中 age、字段宽度和 modulo 算法均来自原 `rv32_execution_recovery_cancel`，`KILL_BRANCH=0`。原实现是 report_valid 与 `C(selected_tag)`；新实现以同一 one-hot report selection 选择各行 `C(row_tag)`，没有报告时为 0。cancel 与所有原字段使用同一选择树，所以不会把一行取消结果配给另一行的值。使用的是 backend 原来的 execution recovery packet，而不是把不同 LSQ kill 规则误当成同一个条件。

恢复 packet 当前为 20 位，含 apply、7 位 occupancy、6 位 head、6 位 branch-relative-age；报告 74→75 位，选择叶仍五个。新增接口默认 `LOCAL_REPORT_CANCEL=0`，旧 named-port 单元实例保持该模式；backend 根据原 `LOCAL_EXEC_RECOVERY` 启用。取消计算位于保留组合 hierarchy 内，输出没有新增寄存器。普通 completion 的完整 ROB valid/generation 查询、ROB 最终完整 tag 检查及 PRF 正常接受资格均保留。

DJ 的 eligible 条件仍是 pending store 且存在 ready RS 完整 tag 匹配。若有 `row>=head` 的 eligible，grant 选这些行中最低物理行；否则选全部 eligible 中最低行，这与原环形最老规则相同。每行 RS grant 使用 `match[j] && !OR(match[0:j-1])`，保留存在重复匹配时最低 RS 行的确定性。最后选出的 RS one-hot 同时驱动 base 与 immediate 选择；没有候选时所有 grant 为 0，选出包及 base 为 0。新的选择不 dequeue RS、不产生 completion、不使 store data ready，也不授权内存写入。

DK 的块 G 是两操作数该 nibble 的 carry-out，P 是该 nibble 所有位 XOR 的 AND。prefix 的 G/P 组合公式为 `G=G_hi || (P_hi && G_lo)`、`P=P_hi && P_lo`；三级覆盖八个 nibble，各块输入 carry 取其前一块的累计 G。sum1 为四位 sum0+1，最高溢出按原 32 位加法舍弃。没有使用“上位立即数必定如何”的额外数据假设。

DH 保留 refill/local/store/read 命令优先级、每 way address、原 SRAM CE/WE/wmask 规则以及被 mask 的字节不能意外读出这一课程契约。宏形状、数量与容量均未修改。保留边界内的逻辑和 inverter 是计价的真实综合单元，不是黑盒、假 buffer 或面积豁免。

以上是源码与代数推导，**不是 HDL 语法检查、形式证明或测量结果**。没有增加 `always @(posedge ...)`、功能寄存器、指令周期或握手边界；十级普通整数流水与原 39 项参数一致。综合优化仍可能改变 gate 数、结构和路径主次，不能保证三项新数值与旧版相同，更不能预报具体 MHz。

## 文献、开源项目与保留方向

[Palacharla/Jouppi/Smith，ISCA 1997](https://ftp.cs.wisc.edu/sohi/papers/1997/isca.complexity.pdf)分析 wakeup/select 与 bypass 的复杂度，并讨论拆分这类反馈链对连续依赖指令发射的影响。这支持优先减少实际反馈链中的串行选择；其旧工艺实验数值不能换算成本 CPU 的 ASAP7 MHz。这里的目标推导来自本机 DF1 STA。

[BOOM issue 文档](https://docs.boom-core.org/en/latest/sections/issue-units.html)区分 ALU fast wakeup 与 load/可变延迟的 slow wakeup，并说明 speculative issue 需要失败后的 kill/retry；[biRISC-V issue 源码](https://github.com/ultraembedded/biriscv/blob/master/src/core/biriscv_issue.v)有独立 load/mul bypass 配置。由这些项目得到的本 CPU 备选方向，是只拆较慢 load wake 或提前发资格并配套 replay，而不是用开源核心的频率替代自身计量。biRISC-V 的 in-order 架构也不满足本项目要求，不能整体替换。

| 备选方向 | 本轮取舍及继续条件 |
|---|---|
| DG 删除普通完成的 ROB 存活查询 | 已准备独立源候选，未采用。它不直接缩短 DF1 早期 wake 慢锥；PRF 没有独立 generation，删除资格还需要更完整的 pending/held/recovery 生命周期依据 |
| load report 增加一级或仅延后 load wake | 可切开 report→wake，但新增 load-use 延迟，须同步 valid/tag/phys/value/cancel 及接受 owner。先完成本批无新增周期的重排；若新最慢锥仍穿过 load report，再评估代价 |
| RS 分簇或 memory 专用地址等待队列 | 可减少 store 地址的全 LSQ×RS 匹配；涉及 steering、容量利用、分簇旁路、分支恢复和 bank 阻塞。当前重排保持任意现有 RS 行可用，容量不减 |
| dispatch 时登记 store→RS 槽位映射 | 可去掉 16×12 tag 匹配；需定义 RS 释放/重分配后 owner、回收清除和 store data 未准备时的生命周期，不能只记裸槽号。属于上述专用队列方向的较小实现 |
| 每个 RS 行预计算 base+imm 或进位资料 | 会把加法移到选择前，但复制 12 份算术。此次保留一个共享 adder；新数据若仍指向选中操作数后的加法，再比较复制的面积代价 |
| 12 位 store immediate 特化加法 | 可利用符号扩展结构预计算高位增/减结果；需对所有启用路径确认 immediate 契约。目前使用通用 32 位精确加法，不混入额外格式假设 |
| report membership 使用 head/tail 环形区间 | 可能减少逐行 age 减法。已检查恢复会按 retained count 更新 occupancy 并按 first-killed 更新 tail；暂不靠尚未完整证明的 head/tail/occupancy 关系删除现有范围资格。若该段仍慢，可用纯算术等价改写保留 guard |
| load 合格行直接广播到 RS、物理依赖矩阵/pointer wake | 可移除 report winner→wake 的依赖；会扩大 wake 端口或新增 successor/reuse 管理。当前只有十二行 RS，先压缩已定位的资格和选择链 |
| 继续全局插 buffer 或优化 reset | 当前五条路径无超载，reset 在 STA 中固定 0；只对 DH 这种真实最终消费者超载落地，不依据全局 net 名义排名推断临界性 |
| SRAM command FIFO、更多 MUL/DIV 段、PRF SRAM、缩小容量 | 前序报告已有展开。当前这条路径无需改宏端口或增加这些单元的延迟；后续只按实际新锥选择 |

仍有这些依赖映射和架构契约的方向可继续推演，不能宣称不存在任何其他优化方案。本轮先汇报已落地的四项修改，不因此自动开始测试。下一次测试前，会再次明确已经完成的组合版本和范围。

## 后续统一测量范围，当前未启动

若后续研究决定测量 DK，则仅在当前 Windows 原生主机执行一批冻结源码的课程 Yosys/ABC/OpenSTA 与一次 Verilator CPU 构建，六项原 perf 各一次；面积包括 SRAM。复用同一 CPU 执行短 LSQ wrap/forward 与 recovery/reuse 程序，各一次，覆盖本批改动，不逐项编译或每次编辑重测。十九项整套不自动重复；已有 DD 超时状态保持，有限通过不能代替完整正确性。

课程框架 `54fc150ffc290f52aa024209ffb9a29d43856f6d`，testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`；Yosys0.63 `70a11c6bf0e8dd669f56c7da3587f78b405138e2`、ABC `8e401543d3ecf65e3a3631c7a271793a4d356cb0`、OpenSTA3.1.0 `f89887b59600cd3a2a10c3de31bda4235d904cdf`、Verilator5.020 `5c5314b39cd888f427807d626e1502cbf222c292` 保持。原 ASAP7 RVT TT 库、FakeRAM、ideal clock、slew/uncertainty/I/O/load 约束、原 scripts/synth.py / scripts/testcase.py / sim.cpp 和内存 latency10 保持。没有使用 WSL，也没有改变约束来制造频率数字。

活动记录的 DK 当前 Fmax/IPC/area 为 null、tests_started=false；DF1 的 294.337453 MHz 已移入其独立历史记录。300 MHz、±10% 与 Tier3 均不能据未测源码宣布达成。
