# ROB 与 D-cache 布局接入（2026-10-02）

目标是同一配置满足总面积（含全部 SRAM）≤36,000 µm²、授权六项 IPC 几何平均≥1.0985、全 SRAM 时序≥300 MHz。当前未达到 Tier3。用户本轮原始目标已逐字保存到 `docs/goal-objective_2026-10-02.md`，验收口径仍见 `docs/final_project_requirements.md`。

## 最新完整整机结果

本轮接入配置的编译、29项回归、完整综合、独立面积核价和全 SRAM 时序均已完成。以下三项来自同一配置；未将独立模块收益计入整机成绩。

| 指标 | 实测 | 目标 | 结果 |
|---|---:|---:|---|
| 六项 IPC 几何平均 | 1.1213155347 | ≥1.0985 | 达标，超出2.08% |
| 总面积（含全部 SRAM） | 54375.028734 µm² | ≤36000 µm² | 未达标，超出51.04% |
| 含 SRAM 的综合后 Fmax | 39.679156818 MHz | ≥300 MHz | 未达标 |

面积分解：组合34963.219080 µm²、时序11586.142800 µm²、37个SRAM宏7825.666854 µm²。独立核验状态为 VERIFIED，470939个叶实例全部计价，未映射内存为0，核验时当前输入变化为0。面积与时序对应相同网表 SHA256：`b23c92ef5b81a9d3851b2ea1ffebaf0ebe663f0bfabb6a76ffd8bcd5a5220bbe`。

最小时钟周期25.2021484375 ns；时序包含实际SRAM，遗漏内存边界为0。该频率是理想时钟、无互连寄生的综合后估计，尚非布局布线结果。相较接入前较好的 Cache更新模式0冻结整机，面积55385.539374→54375.028734 µm²（下降1.82%），频率32.261113386→39.679156818 MHz（提高22.99%），IPC不变。目标仍未完成。

完整证据位于下述整机目录的 `benchmark.json`、`basic.json`、`simulator.json`、`boundary.json`、`baseline_comparison.json`、`area/area_audit.json`、`area/independent_verification.json`、`area/full_timing_audit.json`。

## 本轮已接入的 RTL

ROB 分银行提交读取和分银行分配写入已从验证候选接入真实 CPU，参数为 `ROB_COMMIT_BANKED_READ`、`ROB_ALLOC_BANKED_WRITE`。包含先前证明过的紧凑指针推进及过程临时变量隔离。保留原状态、完整提交字段、generation 标签、分支恢复及容量小于发射宽度时的原路径。

D-cache 的同沿索引寄存器、银行内实时元数据查询已接入，参数为 `DCACHE_REGISTERED_INDEX`、`DCACHE_LOCAL_METADATA_QUERY`。元数据查询捕获地址而非有效/脏/LRU 值，因此等待期间仍观察实际更新。全部数据及标签 SRAM 保留，未新增请求流水拍。

四个选项默认均为 0，由 student_top → cpu_core → 实际后端/Cache 传递。本轮完成测量的候选显式开启四项，并保持原四发射、ROB64/PRF64/RS16/LSQ16、I128/D1024/2way、TAG1、Cache 控制2、共享 AGU2、RS metadata1、RAT1、AXI8/4/16、响应 FIFO2。

原工作树九个被替换文件已逐文件备份及 SHA256 固定到 `F:/CPU2026Integration/banked_layout_20261002/baseline`。未覆盖先前候选或冻结测量。旧、较早版本的大 ROB64 形式证明因新候选整机接入而明确取消，日志及取消原因保留；不记作通过。新候选已完成的八套小/边缘 ROB 整模块证明仍为其实际覆盖范围，不能称为 ROB64 或全 CPU 形式证明。

## 已完成检查

- 接入后的 48 组 ROB 协议全部通过：宽度1/2/4、容量4/8/32/64、控制寄存器开关、提交读取开关，银行分配显式为1，包含所有 head 旋转、逆序完成、背压、store、恢复和旧 generation 检查。证据：`F:/CPU2026Proofs/rob_banked_integration_protocol_20261002/report.json`。
- 接入后的 24 组 D-cache 定向协议通过，覆盖索引开关、更新模式0/1/2、元数据查询开关，以及真实1024行/2way/哈希/预取路径。证据：`F:/CPU2026Proofs/dcache_local_metadata_integrated_smoke_20261002/report.json`。此前同一候选的720组协议证据保留。
- 原生整机编译及随后29项 benchmark/basic/simulator/边界、完整面积、独立计价、全 SRAM 时序由 `tools/run_banked_layout_candidate.ps1` 串行执行，现已全部完成。全部29项已通过，逐项 cycles/instret/退出码与冻结基线完全相同；六项 IPC GEOMEAN=1.1213155347352615，周期合计372783、退休472599。整机面积/频率见本报告顶部。对照证据：整机目录下 `baseline_comparison.json`，明确记录六个改变的 RTL 来源，不称为同源码或全 CPU 形式等价。

整机任务目录：`F:/CPU2026Integration/r64p64rs16lsq16_robr1w1_dc2i1m1_20261002integrated1`。顶层日志位于 `F:/CPU2026Integration/banked_layout_20261002/integrated1.{stdout,stderr}.log`。所有新编译/综合临时文件和大输出使用 F 盘，避免 C/E 盘空间不足。

## 刚完成的接入前冻结整机对照

以下为当前改动之前的同一 RS metadata1/共享 AGU2 配置，只改变 `DCACHE_STATIC_UPDATES`。各自29项测试已经通过，六项 IPC 均为1.1213155347352615。不能把这些 PPA 移用到本轮接入后的 RTL。

| Cache 更新模式 | 组合 µm² | 时序 µm² | SRAM µm² | 总面积 µm² | 全 SRAM Fmax MHz |
|---|---:|---:|---:|---:|---:|
| 0 | 36128.277720 | 11431.594800 | 7825.666854 | 55385.539374 | 32.261113386 |
| 2 | 36826.747200 | 11431.594800 | 7825.666854 | 56084.008854 | 17.820782792 |

两套均使用原始五库、默认 ABC，实际37个 SRAM 宏完整计价和时序。模式0的独立冻结网表计价已核验；模式2原任务的完整报告已生成。两套路径分别为 `F:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_rsmeta1_standard_20261002rsmeta1dc0` 和 `F:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_rsmeta1_standard_20261002rsmeta1`。

这个对照显示仅引入银行化更新在整机上仍退化；本轮必须实测加入局部查询后的组合，不能把独立模块收益直接相加。

## 后续独立时序候选

对已完成的完整 D-cache 局部查询网表进行只读身份核验，全部69个功能模块、53309个叶单元和完整层级连接指纹一致。最差路径中 `_39068_/Y` 确实驱动64个银行的 `miss_valid_i`，该级延迟约8.08 ns；不是按 STA 编号猜测来源。证据：`F:/CPU2026Diagnostics/dcache_local_refill_identity_20261002/identity.json`。

独立候选 `F:/CPU2026Candidates/dcache_local_action_decode_20261002` 增加默认关闭的 `LOCAL_ACTION_DECODE`，把真实命令译码放在拥有状态的银行内部，保持原更新边沿、优先级和全部存储。24组初检及显式开关1的24组协议通过。实际独立 Cache 开关0/1完整PPA已完成：12723.483680→12752.716580µm²（+29.232900，+0.2298%），44.696639022→57.469974183MHz（+28.57784%），36个实际SRAM宏全计价和时序。新的720组显式模式1协议矩阵全部通过，完成816228次活动元数据查询核对。证据目录分别为 `F:/CPU2026Proofs/dcache_local_action_decode_explicit_20261002`、`F:/CPU2026Probes/dcache_local_action_actual_cache_20261002`。尚未接入当前 CPU；这些面积/频率是完整独立 Cache 的结果，不是整机成绩。

## RS 后续面积候选

对冻结 Cache0 整机的完整组合 DAG 做只读归属诊断：每个门只计一次，跨模块共有路径仍单列，并在触发器和 SRAM 处终止遍历。归属合计36128.277720µm²与独立核价严格相等。只流向RS状态的组合锥6004.845900µm²、LSQ3735.731340µm²、ROB3627.518580µm²、rename2643.572700µm²；这不是独立模块面积相加。证据：`F:/CPU2026Diagnostics/rsmeta1dc0_logic_owners_20261002/logic_ownership.json`。

据此在 `F:/CPU2026Candidates/rs_parallel_wakeup_20261002` 实现默认关闭的 `WAKE_MUX_IMPL`：共享tag比较、预译码优先级后以一热OR选择wake数据。尤其保留原先组合旁路采用最低lane、时序写入采用最高lane的行为，不能假设重复tag的数据永远相同而悄悄改变接口语义。没有新增状态、缩小队列或改变流水拍。

实际完整RS与原模块的无输入约束顺序等价已完成BE1/4项/1wake、BE2/4项/4wake、BE4/4项/10wake、BE4/16项/10wake四套，共18939个equiv点，包含实际16项配置的11469点。完整独立RS的PPA已完成：面积10001.559240→8266.947480 µm²（下降17.34%），频率76.807680768→84.265964450 MHz（提高9.71%）。此候选尚未接入整机，不能从整机面积直接扣减模块面积差或视作CPU形式证明。证明与完整独立RS综合分别在 `F:/CPU2026Proofs/rs_parallel_wakeup_formal_20261002`、`F:/CPU2026Probes/rs_parallel_wakeup_actual_20261002`。

## 重命名直接读取与批内转发候选

`F:/CPU2026Candidates/rename_read_bypass_20261002` 的 `RAT_READ_BYPASS` 使用原始RAT读取加更早已接受指令的直接转发，保留依赖、WAW旧物理寄存器、前缀背压、恢复及提交释放优先级，所有原状态和端口仍在。完整实际模块在BE1/PRF33、BE2/48、BE4/64、BE4/96四套均通过无输入假设顺序等价，共3231个equiv点。证据：`F:/CPU2026Proofs/rename_read_bypass_formal_20261002/report.json`。

实际完整独立BE4/PRF64模块的默认ABC/原库PPA：643.342500→613.992960µm²，251.597052→355.432142MHz；两个实际网表均完成独立完整层级/叶核价和源码核验，无实际SRAM。证据：`F:/CPU2026Probes/rename_read_bypass_actual_20261002`。这是模块结果，不是CPU达到300MHz；它的面积下降仅29.349540µm²，不能从前述“流向rename状态”的2643.572700µm²组合锥推断上千面积收益，因为后者包含外部恢复等驱动逻辑。当前尚未接入整机。
