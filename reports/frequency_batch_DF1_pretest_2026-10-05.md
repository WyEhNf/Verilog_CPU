# DF1：Dcache SRAM 命令与 LSQ 字节转发重构，测试前报告

DF1 已采用到 `E:/Verilog_cpu` 并冻结为 [architecture_DF1_20261005](F:/CPU2026CourseRuns/architecture_DF1_20261005/source_manifest.json)，冻结 manifest SHA256 为 `d4596d27b02aadb38412092006592954cf72f7114e705de44aeb5b8bad6113e9`。40 个活动输入与 157 个冻结输入已经核对文件身份；这不是 HDL 测试。目前没有启动 DF1 的 HDL 编译、lint、仿真、综合、STA 或形式验证。保存 [采用前 DD 备份](F:/CPU2026Candidates/pre_DF1_worktree_20261005/backup.json)。

普通整数流水仍为十级，所有 39 项课程参数、ROB64/PRF64/RS12/LSQ16、cache 容量及相联度保留，内存延迟仍为 10。DF1 对 DD 只改变 [Dcache](E:/Verilog_cpu/rtl/cache/rv32_dcache_nonblocking.v)和 [LSQ](E:/Verilog_cpu/rtl/backend/rv32_lsq.v) 两个 RTL 文件，继承此前 [DD 的完整 25 组方案](E:/Verilog_cpu/reports/frequency_batch_DD_pretest_2026-10-05.md)。

## 已有测量与本轮目的

DD 是 **273.943285 MHz / 3.650390625 ns、IPC 0.7823728642、面积 51,233.753154 μm²（含 SRAM）**。频率比旧 CD1 提高约 174.9%，仍需减少约 0.317057292 ns 才能达到 300 MHz。IPC 比课程基准低 20.1765%，面积高 10.6329%；目前没有达到用户此前 ±10% 条件或 Tier3。详见 [DD 测量报告](E:/Verilog_cpu/reports/frequency_DD_measurement_2026-10-05.md)。

DD 的根负载由旧版 victim-entry 的上千消费者下降后，新的最慢锥成为 `local_array_write → 重复字命令译码 → SRAM 地址`：96.36 fF/0.946 ns 的根门与被慢输入 slew 拖慢的后继门。DF1 直接重构这个锥的实际消费者，而非仅对命名相近的 tag 输入再加树。

## DE：每路缓存单独拥有命令，分发到字节 SRAM

由 [prepare_dcache_command_line.py](E:/Verilog_cpu/tools/prepare_dcache_command_line.py)生成独立 DE，然后被 DF/DF1 继承。

| 结构 | DD | DF1 |
|---|---|---|
| 数据命令与地址译码 | 2 ways × 4 个 32 位 word owner，各自重复译码 | 2 个 128 位 line owner，每个 way 一次译码 |
| raw refill/local/store/read/reset | 直接连八个 owner，控制在 owner 内展开成宽选择 | 先形成每 way 的 7 位控制包和地址字段视图 |
| 地址来源 | 嵌套 refill/local/store/deferred/input 选择 | 互斥 qualified grant 的并行 AND/OR 地址选择 |
| SRAM 地址/enable/write/full-mask | 字级控制直接挂四个宏 | 每 way 分发到 16 个字节宏，最终地址叶只驱动一个宏 |
| 128 位数据选择 | 每字重复译码后控制 32 位数据 | 最后 qualified refill/local grant 分发，每叶最多 16 位数据 |

源推导保持 `refill > local > store` 的全局优先级：若 refill 指向另一 way，不能让本 way 同拍接收 local/store。每 way 的 `writing`、地址、数据、mask 和 enable 与原四个 word owner 对应一致。deferred read 的地址优先于 input read，reset 只影响原 enable 责任，没有新增采样边沿或请求握手。

原课程 [FakeRAM 生成器](E:/Verilog_cpu/.deps/RISC-V-CPU-2026/scripts/fakeram.py)将 WIDTH32、granularity8 分成四个 DEPTH512×8 宏；四个 word 也是 16 个宏。DF1 直接用 16 个 WIDTH8、granularity8 wrapper，每个 way 的宏形状/数量和容量保持相同。宏面积、clock-to-Q 模型和约束没有更改。

全局 `we` 仍驱动该 way 的每个字节，mask 为零的字节仍由原 wrapper 的 `en & (~we | wmask)` 规则关闭 CE，不能变成一次读；写入和空闲输出无效的课程语义保留。仅减少重复地址逻辑并改变电气域，实际门面积需新映射确认。

## DF：每行局部转发查询与共享相对字节解码

由 [prepare_lsq_forward_windows.py](E:/Verilog_cpu/tools/prepare_lsq_forward_windows.py)生成，DF1 通过 [命名修正](E:/Verilog_cpu/tools/prepare_lsq_forward_window_names.py)将人工审阅发现的 SV 保留字 `matches` 改成 `byte_match_bits`。DF 的原始候选保留，没有因这个命名问题运行过编译或测试。

选中 load 的地址和 decoded byte mask 通过 36 位查询包分发到 16 行。每行读取其本地 packet，以免 selection FF 和 access-mask 的最终译码直接承担整个转发窗口的消费者。

原行内 overlap/data 函数各遍历四个 load bytes 与四个 store bytes，匹配 `(load_offset+b)==(store_offset+j)`。新的 `rv32_lsq_forward_window` 先求五位 `delta=load_offset-store_offset`，只解码 -3…+3 七种可能非空的字节窗口，再让每个输出 byte 局部选择四个 source bytes。七个 alignment 视图按输出字节分发，每个最终匹配叶驱动最多八个数据位和一个 mask 收集点，数据归并是二层 OR。

两个四位 offset 的真实差在 [-15,+15]，五位模 32 编码唯一。某个源字节 j 能覆盖输出字节 b，恰当且仅当 `delta=j-b`；j/b 都为 0…3，因此其他差值不会有匹配。每个输出字节最多一个有效源，OR 归并对应原覆盖写入顺序。load_mask/store_mask 资格保留；数据未匹配时归零。该推导不需要新增自然对齐假设。

store 的 valid/address-ready/data-ready、是否早于选中 load、同一 cache line、四个 byte 分别取最近旧 store 的 tournament 保持不变；未改未知地址阻塞、未决 store 数据阻塞、持有转发、请求取消、ROB/LSQ generation 检查、队列占用或完成/退役边沿。

## 风险与其余方向

DE 增加分发层而减少原真实负载，是否改善总路径要看新 STA，不能把 0.946 ns 当成必然全部可消除的收益。DF 的共享五位减法引入一段进位逻辑；相比重复比较/广播是否更短也必须测量。层次边界影响 ABC 的跨模块优化和面积，不保证面积降到此前 ±10% 以内。当前所有频率/面积/IPC 值都还未知。

基于当前五条最差检查与映射负载，可直接定位的两类新结构修改已经落地。本轮源审阅还记录了以下替代方向及触发条件：

| 方向 | 当前处置 |
|---|---|
| 移动 Dcache 命令寄存边界/独立 command FIFO | 会增加 refill/local-fill 或请求占用周期并涉及被接收事务的 owner；当前先用每 way 命令域重构消除真实超载，保留在该锥仍慢时采用 |
| 只对旧八个 word 模块增加输入树 | 可减少根负载，但保留重复译码和最终四宏地址负载；本轮已采用更完整的每 way command owner |
| SRAM 地址译码提前预计算/保留原串行地址 mux | 本轮选择互斥 grant 并行归并；若新的 shared address/grant 本身成为瓶颈，按新点的 slew/fanout 改拓扑 |
| 再复制整个 SRAM | 数据宏当前形状与容量固定，同端口命令分发已经能减轻引脚负载；复制不是当前最慢路径的必要操作 |
| LSQ load-byte/store-byte 常量地址比较预计算 | 是共享差值解码的替代拓扑；若新报告证明五位 delta 的串行进位主导，则换并行差值比较，不同时保留两套无用网络 |
| 全局 reset/domain、Icache 匿名高负载、剩余 ROB query | 已有负载与反向锥线索，但课程仅给五条最差检查，尚无明确新慢路径归属；不把某个匿名 net 或 source 行号当成唯一字段定位 |
| RS 分簇、metadata-only issue、PRF SRAM、更多执行段、Dadda/radix8 | 相关所有权、端口、旁路和容量取舍在 DD 报告中已展开；当前最慢锥是 cache 命令，不依该测量盲目增加相关指令周期 |

更多结构方案的取舍需要得知本轮之后新的最慢锥。此前十级和 25 组修改仍保留，未为了追求阶段数量再加流水级，也没有改变课程工具/库/宏/约束来提高数字。

## 下一轮统一测量范围，尚未启动

本报告先交给用户，再开始同批测量。主机是当前 Windows 原生环境，禁止 WSL。

| 项目 | 计划 |
|---|---|
| 课程综合/ABC/STA | 冻结 DF1 一次，固定 Yosys0.63/ABC8e401543/OpenSTA3.1.0、ASAP7 RVT TT 与原 clock/input/output/uncertainty/load；产物含宏面积 |
| CPU 编译与 IPC | Verilator5.020 一次 CPU build；原六项 perf 各一次，原 dynamic_instructions 和 latency10，几何平均原口径 |
| 有限功能覆盖 | 复用同批 exact executable，短 LSQ wrap/forward 与 recovery 程序各一次；不另外编译 RTL，也不逐项修改后测 |
| 十九项完整 correctness | DD 原有完整检查继续并保留失败；本轮不重复整套，以已有六项 perf 结果检查和两个有限程序检查改动范围。不能据此宣布所有 correctness 已通过 |
| 同期工作 | 测量后台运行，继续分析 owner/边界/下一瓶颈方案；只有新的明确失败或时序锥才追加对应修正，不因状态文件旧而重启同批 |

固定身份：课程框架 `54fc150ffc290f52aa024209ffb9a29d43856f6d`，testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`；Yosys commit `70a11c6bf0e8dd669f56c7da3587f78b405138e2`，ABC `8e401543d3ecf65e3a3631c7a271793a4d356cb0`，OpenSTA `f89887b59600cd3a2a10c3de31bda4235d904cdf`，Verilator `5c5314b39cd888f427807d626e1502cbf222c292`。调用原生 PE 可执行文件，仍使用原 `scripts/synth.py`、`scripts/testcase.py`、`sim.cpp`。Windows 原生 make/归档或时间符号适配只处理主机问题，不更改 CPU、模型和计量。
