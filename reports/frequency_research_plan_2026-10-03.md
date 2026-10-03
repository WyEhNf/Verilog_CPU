# 频率优化研究与测试前汇报

**本轮没有启动仿真、编译、lint、综合、STA 或形式测试。** 已读取旧报告、网表、RTL 和课程原始 Liberty，查阅论文及 BOOM、香山、Ibex 的一手资料，并准备三份有补丁和源码清单的候选。所有候选状态均为 `PREPARED_UNTESTED_NOT_ADOPTED`。下一步测试前以本报告向用户交付研究、改动与取舍；此报告不宣布优化成功。

## 1. 当前结论和依据

优先级应当是：**减少恢复广播的电气负载 → 将宽数据存储与有效性控制分开 → 打断恢复与下游握手的组合传播 → 缩短调度、旁路和算术内部路径。** 当前普通整数路径已加过 decode、issue 寄存边界，但恢复信号仍跨越这些边界影响同周期 `valid/ready/write_enable`。继续只增加数据寄存器，不能解决这种控制传播。

唯一当前课程标准基线：Windows 原生、课程固定版本、原始六项 perf、内存延迟 10。

| 指标 | 已测基线 | 目标 |
|---|---:|---:|
| 课程估算 Fmax | 32.3978865441 MHz | ≥300 MHz |
| 最小周期 | 30.8662109375 ns | ≤3.3333333333 ns |
| IPC 几何平均 | 0.98012794065 | Tier3 ≥1.0985 |
| 总面积 | 46309.6934939443 µm² | Tier3 ≤36000 |
| SRAM | 7825.666854 µm²，37 个宏 | 全部计入 |

冻结基线：[源码清单](F:/CPU2026CourseRuns/current_adopted_20261003/source_manifest.json)、[测量结果](F:/CPU2026CourseRuns/current_adopted_20261003/result/result.json)、[课程标准复测报告](E:/Verilog_cpu/reports/course_standard_retest_2026-10-03.md)。候选复制的是已经物化 39 项采用参数的冻结源码，避免误用主树顶层的旧默认参数。

### 当前最慢路径的延迟来源

课程现成报告有 **5 条**最慢路径，都从 `_610980_/QN` 出发，分别到 `_637263_`、`_637267_`、`_637268_`、`_637280_`、`_637286_` 的 D，文本报告到达时间均为 **30.7973 ns**。它们共用同一重定向/清空控制瓶颈；不能当成五个独立瓶颈。没有为了补齐全芯片路径而重新运行 STA。

| 顺位 | 单元/网络 | 单段延迟 ns | 扇出 | 负载 fF | 处理方向 |
|---:|---|---:|---:|---:|---|
| 1 | NAND3 `_362281_`，decode `flush_i` | 9.4477 | 794 | 410.6031 | 清空只控制元数据；显式分配局部控制负载 |
| 2 | NOR3 `_333444_`，`redirect_valid_i` | 7.4105 | 1383 | 640.6143 | 在 ROB 恢复源和真实消费者间建立缓冲分支 |
| 3 | INV `_333445_`，反向 redirect | 6.5727 | 123 | 58.0252 | 改善上游过渡时间，在各分支局部取反 |
| 4 | NAND2 `_417536_` | 1.1502 | 191 | 92.9560 | 控制译码与宽状态写入分离；局部写选择 |
| 5 | NOR2 `_429170_` | 0.8232 | 126 | 53.0159 | 降低局部写/保持门控负载 |
| 6 | NOR2 `_362282_` | 0.7431 | 4 | 1.5514 | 主要受极差输入过渡时间影响，先修上游 |
| 7 | NOR2 `_429169_` | 0.5515 | 8 | 3.7561 | 同上；不能只按扇出判断慢门 |
| 8 | NOR2 `_417527_` | 0.4918 | 103 | 41.6546 | 局部控制分支与译码 |
| 9 | NOR2 `_417193_` | 0.4717 | 103 | 43.1161 | 局部控制分支与译码 |

前三段是**串联、相互影响**的延迟，合计 23.4309 ns，占 30.7973 ns 的约 76.1%。不能把三项改善当成独立收益相乘，也不能直接用减法预测新频率。纯加减剩余约 7.37 ns 只是分解现有报告；改善上游 slew 后下游延迟也会变化，且全芯片最慢路径可能转移。

[本轮只读解析结果](E:/Verilog_cpu/reports/frequency_research_20261003/saved_path_analysis.json)保留报告 SHA、路径单元、原始网络与实例连接。根模块直接连线计数不包含保留层次内部的负载，扇出结论使用现成 STA 文本中的完整数值。当前数字并未通过旧工具的信号命名映射推断寄存器原名。

### 为什么这是一个结构性问题

直接读取课程五库得到：

| 真实库单元 | 最大输出负载 fF | 本路径实际负载 fF | 超载比例 |
|---|---:|---:|---:|
| NOR3xp33 | 23.04 | 640.6143 | 27.80 倍 |
| NAND3xp33 | 23.04 | 410.6031 | 17.82 倍 |
| INVx1 | 46.08 | 58.0252 | 1.26 倍 |

这些单元的第一组延迟表输入过渡时间范围为 **5–320 ps**。NOR3 输出 slew 已达 **15870.4 ps**，进入 INV 时约为该范围上界的 49.6 倍；INV 输出 2894.7 ps，再进入 NAND3 也远超范围。课程 OpenSTA 数字仍是当前评测结果，但这里涉及远超表格范围的时序估算。关键工程任务是让控制网回到合理负载和过渡范围，而非用工艺节点或流水线级数解释频率。

本项目固定 Yosys 源码显示：没有 `-constr` 的默认 ABC 库脚本包含 `&nf`，**没有显式 `buffer; upsize; dnsize` 后处理**；带 `-constr` 的另一脚本才包含这些命令。这不等于 ABC 完全不会选驱动规格，而是不能假定课程流程会自动修复所有高扇出网。课程本次实际命令是 `abc ... -D 2000`，未使用 `-constr`。依据：[固定源码](https://raw.githubusercontent.com/YosysHQ/yosys/70a11c6bf0e8dd669f56c7da3587f78b405138e2/passes/techmap/abc.cc)。

原始模型为理想时钟、没有布线寄生；因此摆放、CTS 和时钟偏斜不能直接解释或修复这份课程报告中的数据控制负载。OpenROAD 的 resizer 文档也将缓冲插入用于修复 slew、capacitance、fanout，帮助确认处理方向；本轮没有运行 OpenROAD，也没有改课程脚本来获取分数。[OpenROAD 官方源文档](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/rsz/README.md)

## 2. 已准备的三个具体候选

主树与已经测量的快照未被候选替换。三个候选是逐项累积的独立源码目录，可以查看相对测量基线的补丁。

### A：有效性失效与 payload 写入解耦

[候选目录清单](F:/CPU2026Candidates/frequency_research_20261003/A_payload_acceptance_decoupling/candidate.json) · [补丁](F:/CPU2026Candidates/frequency_research_20261003/A_payload_acceptance_decoupling/review.patch)

修改 `cpu_core.v` 和 `rv32_fetch_frontend.v`：

- Fetch payload 使用响应有效、epoch/行地址匹配、队列容量形成存储写入条件，去掉存储写入对外部 `if_resp_ready_o` 的依赖。真正响应接收、队列计数、PC 和请求状态仍遵守 redirect 优先级。
- Decode 从未加 invalidate 的消费前缀计算存储容量与 `storage_push`。公开的 `valid/ready` 仍受 invalidate 门控；计数/head/tail 在 reset/flush 边沿清零。
- 移除这些队列 payload FF 上的 reset/flush 保持选择。失效边沿允许写入将被丢弃的数据；队列控制拥有有效性。

此前 v7 已尝试删除显式 payload `!flush`，但 `push=valid & ready`、`resp_fire=valid & ready` 的 `ready` 仍包含清空控制，不能据此认定依赖已经解除。A 处理的是这层间接依赖。不过 decode 的 `ready_i` 来自后端，仍可能含恢复逻辑，因此 A **不是**整个 CPU 恢复链已完全解耦的证明。

静态推理：普通周期的公开握手和写入与原行为一致；失效边沿 count/head/tail 清空，存储内容不可作为有效指令观察；恢复后每个有效条目必须先完整写入。payload 失去“无效时一定为零”的保证，调试接口或旧测试若依赖该保证，需要与架构有效性区分。A 没有计划增加指令或恢复延迟，也没有新 SRAM。

### B：在恢复源与局部消费者间加入真实、计价的缓冲分支

[候选目录清单](F:/CPU2026Candidates/frequency_research_20261003/B_priced_control_domains/candidate.json) · [补丁](F:/CPU2026Candidates/frequency_research_20261003/B_priced_control_domains/review.patch)

B 包含 A，并在五个文件中准备了以下改动：

- ROB 的恢复选择结果驱动缓冲树；恢复接受、前端重定向、RAT 恢复、头指针/分配、reclaim、提交/时序更新分别消费分支。
- 后端的分配、RAT、RS kill、completion kill、issue/ALU、LSQ、producer/completion、分支状态更新消费八个不同分支。
- 顶层前端、预测器、decode 分别连接重定向分支；decode 的公开有效性和元数据更新再分开。
- Fetch 队列的 granted 写选择、decode 字段的 selected 写选择在实际 payload 字段旁使用局部缓冲。

复用已有 `BUFx16f_ASAP7_75t_R` 的仿真视图与综合声明，单元功能、输入负载、延迟和面积来自课程原始 Liberty。缓冲是组合单元，**不增加周期**。这里不是复制 `assign`、给信号改名或依赖重复 RTL 表达式保留下来；每个分支有明确的真实库单元和消费者。后续仍须确认综合产物保留拓扑、所有叶单元按真实库计价，并检查分支实际负载。

当前四宽、FQ16、decode 194-bit/7 字段的配置，在保留所有准备的缓冲实例时，静态结构数为：

| 位置 | BUFx16f 个数 |
|---|---:|
| ROB | 7 |
| Backend | 9 |
| Top redirect | 4 |
| Decode invalidate | 3 |
| Decode payload selected 与本地写使能 | 280 |
| Fetch payload granted 与本地写使能 | 160 |
| 合计 | **463** |

该库单元单价 **0.32076 µm²**，所以新增缓冲的毛面积为 **148.51188 µm²，约基线总面积 0.32%**。这不是候选总面积实测：A 会删除部分逻辑，ABC 也可能改变其他逻辑映射。BUFx16f 的最大输出负载为 737.28 fF、输入负载为 2.34187 fF；例如八分支树的根只直接驱动约 18.735 fF 的分支输入，原弱恢复门直接看见的是根输入。分支自身的负载仍须在后续报告中确认，不能仅凭强驱动规格保证所有 slew 合格。

### C：乘法器内部真正分级，并将符号修正融入压缩树

[候选目录清单](F:/CPU2026Candidates/frequency_research_20261003/C_split_signed_multiplier/candidate.json) · [补丁](F:/CPU2026Candidates/frequency_research_20261003/C_split_signed_multiplier/review.patch)

C 包含 B，另修改 `rv32m_multiplier.v`：

1. 对原始无符号操作数生成 32 个部分积，用 carry-save 项补偿 signed high-half，删除树前取绝对值和树后整体取负的串行加法。
2. 第一阶段：36 个项压缩为 24、16、11、8 项，寄存 8 项和操作/tag/PRF 元数据。
3. 第二阶段：8→6→4→3→2 项，再做最终 carry-propagate 加法并选低/高字，结果寄存。
4. 两个阶段各有有效位和保持/转移条件，支持输出反压下保持数据；flush 清有效位；结果携带原 ROB tag。保留四种合法 MUL 操作与默认零输出选择。新增部分项和结果写使能使用局部缓冲分支，避免一个弱控制门重新直接驱动 512 个保持 mux；C 比 B 再增加 13 个缓冲，毛面积约 4.17 µm²。

符号公式（模 2⁶⁴）：`P = U - (negative_A ? B : 0)·2³² - (negative_B ? A : 0)·2³²`。其中 `negative_A` 仅对 MULH/MULHSU 生效，`negative_B` 仅对 MULH 生效；MUL 的低 32 位直接取 U，MULHU 不修正。每个减项用 `{~operand, 32'b0}` 和 `1<<32` 两个 carry-save 项表达，不另放串行减法器。

**乘法延迟由 1 拍变为 2 拍；无反压时启动间隔仍为 1 拍。** C 可能降低依赖链 IPC，不像 A/B 只改变组合实现。第一阶段新增原始状态为 512-bit 部分项加元数据；同时最终输出由 64-bit product/op 改为 32-bit value。净寄存位数在未优化前为 `482 + TAG_WIDTH + PHYS_ADDR_WIDTH`，当前配置需按实际 tag 宽度计价；常量零位等可能被优化，不能把该计数当成综合面积。

当前默认 `MUL_IMPL=0` 确实用到此乘法器；外层 MDU 已有多条在途乘法和带 tag 的 completion。新增深度仍须在后续功能检查中确认与反压、失效结果、完成仲裁一致。BOOM 文档明确指出，组合乘法后面只补延迟寄存器，还需要 retiming 才能缩短组合路径；C 是在压缩树内部插入真实边界。[BOOM Physical Realization](https://docs.boom-core.org/en/latest/sections/physical-realization.html)

## 3. 架构层面的下一批改动：快速重定向、分阶段恢复

A/B 处理超载，但没有消除所有跨阶段握手逻辑。若目标是 300 MHz，需要把恢复变为有时序边界的事务，而非一条组合广播线。

BOOM 的机制是尽早发送 PC redirect，而把在途指令 kill 广播延后一拍，以缩短关键路径；它用 branch mask 标识受影响指令。[BOOM Execute Pipeline](https://docs.boom-core.org/en/latest/sections/execution-stages.html) 香山源代码则能看到 oldest redirect 的寄存、分阶段 redirect，以及 pending redirect 状态。[香山 RedirectGenerator](https://github.com/OpenXiangShan/XiangShan/blob/master/src/main/scala/xiangshan/backend/ctrlblock/RedirectGenerator.scala)、[CtrlBlock](https://github.com/OpenXiangShan/XiangShan/blob/master/src/main/scala/xiangshan/backend/CtrlBlock.scala)。这里借鉴的是机制，未直接移植其完整代码或频率数字。

针对本 CPU 的具体设计草案：

| 时刻/边界 | 要做的事 | 必须保留的规则 |
|---|---|---|
| 分支执行结果 → branch pending | 保存 target/tag，并尽可能在该边界预验证 ROB generation、存活性 | 不能使用已被更老恢复杀死的分支；同周期冲突按年龄处理 |
| 经过验证的 redirect → 前端 | 更新 PC/epoch，失效尚未分配 ROB 的 fetch/decode 指令 | 前端旧响应按请求身份丢弃；不能误收新 epoch 请求对应的旧响应 |
| Recovery descriptor → 各后端域 | 寄存 branch tag、ROB 头视图、保留边界/kill mask，再在域内执行 | 保留更老指令；不能全清 RS/LSQ/MDU；提交/MMIO 只能来自合法 ROB 前缀 |
| Rename recovery | 使用分支 checkpoint 或分阶段 RAT 恢复，恢复期间用局部状态阻止新分配 | 已提交 store 保持；free list 不重复释放；晚到旧 completion 不能污染已重用 PRF |
| Recovery finish | 正确路径重新获得分配 credit | 上述元数据与 generation 更新完成后才释放 credit |

**不能简单把 `flush_i` 寄存一拍**：当前 decode 输出没有按当前 epoch 在后端入口过滤，上一拍残留的指令可能在恢复后的下一拍被错误分配。全局 epoch 也不能直接杀死后端所有旧 epoch 指令，因为更老指令应保留。预分配队列的 epoch 和已分配 uop 的 ROB generation/年龄/branch mask 必须分开使用。

优先保留现有八级普通整数路径，先对恢复通路单独分级。只有调度/读操作数或 cache 路径仍无法满足预算时，再把普通路径扩成 9–10 级，避免每次恢复、每条 ALU 依赖都无条件增加延迟。

## 4. 完整候选清单：40 项，不重复宣称已有功能是新优化

P0 有当前课程路径直接证据；P1 有 RTL/历史路径和架构依据；P2 为替代路线，是否实施取决于后续真正瓶颈。表中的面积/IPC 是方向性判断，未填造出的 MHz 或提升百分比。

| # | 优先级 | 具体方案 | 当前状态/证据 | 主要代价或限制 |
|---:|---|---|---|---|
| 1 | P0 | Fetch payload 写入脱离 redirect-qualified ready | A 已准备；修复 v7 的间接依赖遗漏 | 只允许失效数据被覆盖，不改变接收协议 |
| 2 | P0 | Decode storage_push 与公开握手解耦 | A 已准备 | 后端 ready 的间接恢复依赖仍存在 |
| 3 | P0 | 删除无效队列 payload reset/flush mux | A 已准备；有效性由元数据拥有 | 无效 payload 不再保证零 |
| 4 | P0 | ROB recovery_found 源缓冲与消费者分支 | B 已准备；1383 扇出主因 | 真库单元必须保留并完整计价 |
| 5 | P0 | Backend 恢复域分为 allocation/RAT/RS/completion/issue/LSQ 等 | B 已准备 | 需确认每个分支负载；语义不延迟 |
| 6 | P0 | Frontend/predictor/decode 重定向分支隔离 | B 已准备 | 同周期逻辑，不等于控制流水化 |
| 7 | P0 | Decode invalidate 的有效位与元数据分支 | B 已准备；794 扇出主因 | 仍需处理下游 ready/分配链 |
| 8 | P0 | 宽字段 selected/granted 与写使能的局部驱动 | B 已准备 | 463 个新增缓冲毛面积已计算 |
| 9 | P1 | 快速 PC redirect 与寄存 kill 事务分开 | 具体时序草案见上节；BOOM/香山依据 | 必须处理恢复期间的错误分配 |
| 10 | P1 | 未分配队列用 epoch 失效替代广播宽数据控制 | 部分 epoch 已有；新增入口过滤/握手设计待做 | epoch 回卷与长期在途请求不可混淆 |
| 11 | P1 | 在 branch_pending 边界预验证 ROB tag/generation | 当前恢复前有约 1.96 ns 控制逻辑 | 预验证结果不能因更老恢复/条目重用过期 |
| 12 | P1 | RAT checkpoint 只存实际在途分支，采用 4/8 个银行 | 当前 CHECKPOINT_IMPL=1 用 ROB 信息恢复，并非该方案 | 需要 branch allocation list 和 checkpoint 容量管理 |
| 13 | P1 | branch mask 在 RS/执行/completion 中局部 kill | BOOM 方法；替代集中年龄广播 | 每个 uop 增加掩码，分支 tag 重用必须安全 |
| 14 | P1 | 捕获 recovery metadata，再分阶段恢复 RAT/reclaim | 可以缩短恢复组合路径，避开全并行大网 | 暂停 rename 若干拍；不得影响保留指令执行 |
| 15 | P1 | RAT oldest-killed-writer 按 ROB 银行平衡选择 | 当前并行恢复已存在；改进其选择/读负载 | 不再回退到 ROB64 深度串行 undo mux |
| 16 | P1 | 注册局部分配 credit，分离 ROB/PRF/RS/LSQ 容量链 | 当前 trace_ready 汇合多个资源 | 必须预留回程周期容量，防溢出和 credit 泄漏 |
| 17 | P1 | 两项 skid/保留槽阻断反向 ready 传播 | 现有单项 issue 边界不能自动保证 ready 已寄存 | 容量补偿；recovery 后 credit 重建 |
| 18 | P1 | RS12 分成两个 6 项局部调度域、保留四发射总能力 | 论文支持局部 wakeup/select；不是直接缩 RS | 分派平衡和跨域依赖会影响 IPC |
| 19 | P1 | fast tag wakeup 与实际 value forwarding 分离 | 当前快速旁路还可能贯通调度选择 | 可变延迟 load/div 不可提前假定已就绪 |
| 20 | P1 | 每执行域局部 bypass，跨域值经过寄存边界 | 历史 RS operand 路径很慢 | 跨域依赖增加延迟；不能复制整个 PRF 逃避代价 |
| 21 | P1 | RS 年龄选择使用平衡 tournament/ROB 相对年龄 | 检查级联选择与 8-bit age 的行为 | wrap、等龄、issue port 能力与选择优先级一致 |
| 22 | P1 | PRF 分银行局部读选择及局部 bypass 合并 | 当前 one-hot read 已采用；改的是传播范围 | 读端口冲突需要调度保证或重放 |
| 23 | P1 | Completion 固定来源的分组仲裁与 ready 回传 | 固定 producer 位置当前已有，非新增功能 | 保留 CDB3 带宽、优先级与持有语义 |
| 24 | P1 | ROB completion/commit 端口在真实银行内译码和门控 | 当前 alloc/commit banking 已有，继续降低共享负载 | 仅改层次/复制状态的旧尝试不够 |
| 25 | P1 | LSQ 候选选择树与局部 head/age 比较 | 历史 LSQ 是最慢家族 | 不牺牲 load/store 年龄与依赖检查 |
| 26 | P1 | LSQ address/data/valid 各自拥有局部写事务 | v11 曾局部化但整体退化，需重构依赖而非照搬 | 同周期多写优先级、recovery 与已提交 store |
| 27 | P1 | LSQ 请求决策与 payload 发出分阶段 | 分离“选谁”和“读数据/发送” | 增加 load latency；store admission/ack 仍精确 |
| 28 | P2 | Cache tag 查询和 hit/way/data 选择真正分级 | SRAM/metadata 相关历史路径 | load-use 与取指延迟，需要吞吐补偿 |
| 29 | P2 | Way prediction 加校验/重放，避免所有 way 串联选择 | 替代路线，尚无命中预测率数据 | 不能以未校验的预测 way 数据完成指令 |
| 30 | P1 | Icache response acceptance 与下一请求地址生成分开 | 当前 response_can_chain 能串到新 PC 请求 | 去掉链式启动会损 IPC，宜用预备请求/credit |
| 31 | P1 | SRAM refill/写事务在每银行形成局部地址和 enable | 当前 local SRAM command 已采用，进一步缩控制消费者 | 必须是真正持有事务，不是给控制信号改名 |
| 32 | P2 | 全部热路径计数器定宽、指针局部 predecode/一热点 | Frontend 定宽和 one-hot 读已采用；审查剩余 LSQ/RS/counters | 编译时常量取模可能已消除，避免无收益重复 |
| 33 | P1 | 直接 signed correction 融入乘法 carry-save tree | C 已准备 | 四种 MUL 的符号/高字语义必须一致 |
| 34 | P1 | 乘法压缩树内插寄存器，保持启动间隔一拍 | C 已准备；补寄存器不等于切树 | 依赖 MUL 延迟 +1；新增部分项状态 |
| 35 | P2 | Radix-4 Booth/Dadda 减少部分积并重新平衡内部边界 | 原有 radix4 是替代实现，不能仅开开关宣布收益 | 符号扩展/校正项；看真实工具映射 |
| 36 | P1 | Divider leading-zero 使用分组/树式优先选择 | 当前函数是 found-one 循环；入口串取绝对值/比较 | 先检查映射，工具可能已平衡部分逻辑 |
| 37 | P2 | 除法两次迭代的 compare/subtract 融合或 speculative remainder | 当前一拍做两次迭代，算术链长 | 一拍改一步会增周期；radix4 也需精确商校正 |
| 38 | P1 | Branch target PC+imm 在更早边界预计算，决定与目标并行 | 当前 ALU 有共享 adder 和独立比较；应缩其输入 mux 链 | JALR 仍需要源值；保持清 bit0 与正确 PC |
| 39 | P2 | Barrel shift 分组中间级，独立跟踪多周期有效性 | 普通整数路径替代方案 | 移位依赖延迟增加，可能影响排序程序 |
| 40 | P2 | 32/64-bit 加法器前缀/分块 carry-select 与 CSA 融合 | 当前 ALU 已有 fast_add_sub；重点是未改的 CPA/除法 | 更大并行前缀负载与面积；不会自动优于 Yosys 映射 |

论文的 wakeup/select 与 operand bypass 复杂度分析说明：宽发射 OoO 的频率限制常由调度与旁路决定，切开相关反馈会增加依赖发射间隔；因此本方案选择局部化与快 tag 路径后再分级，不承诺简单加级保住 IPC。[Palacharla、Jouppi、Smith，ISCA 1997](https://www.eecs.harvard.edu/cs146-246/isca.complexity.pdf)。BOOM 的 fast/slow wakeup 区分可参考其[Issue Unit 文档](https://docs.boom-core.org/en/latest/sections/issue-units.html)。

Checkpoint/free list 的设计参考 [BOOM Rename](https://docs.boom-core.org/en/latest/sections/rename-stage.html)：branch allocation list 需要记录分支后的分配，单纯恢复 free-list snapshot 可能遗漏释放后再分配的寄存器。信用/反压设计参考 [Carloni 2015](https://sld.cs.columbia.edu/pubs/carloni_pieee15.pdf)，本项目需按实际反馈和容量分析吞吐，不能把“多加一个 FIFO”当成无成本提频。独立 branch target ALU 机制参考 [Ibex Pipeline](https://ibex-core.readthedocs.io/en/latest/03_reference/pipeline_details.html)，不把 Ibex 的两级顺序核整体替换本课程要求的 OoO 核。

本轮覆盖控制负载、恢复、rename/credit、调度/旁路、LSQ/cache、算术六类可行方向，已形成当前证据支持的候选集。仍可能从新的网表瓶颈产生新方案；“永远不再有新想法”无法作为可证明的工程条件。本轮不会以此为理由提前测试，也不会宣称已经穷尽所有 CPU 设计。

## 5. 用旧数据安排优先级，不混用频率结果

旧工具曾导出 368 个路径家族。各域最慢到达时间如下，只用于确认需要覆盖的结构，**不是当前课程标准测量值**：

| 家族/域 | 历史到达 ns |
|---|---:|
| LSQ address payload | 18.6467 |
| RS operand payload | 18.3920 |
| Frontend occupancy | 17.5004 |
| Decode occupancy | 17.4098 |
| Backend LSQ physical destination | 16.8752 |
| ROB store state | 16.3771 |
| Icache response state | 16.1122 |
| PRF ready | 15.1409 |
| Rename free bitmap | 15.1375 |
| MDU divider response | 11.1545 |
| Dcache metadata | 10.6635 |

[历史家族摘要](E:/Verilog_cpu/reports/frequency_research_20261003/historical_family_summary.json)。v7/v11 的旧工具整机估算约 36.96/36.91 MHz，低于旧采用版本约 53.44 MHz；这说明仅去 mux、加层次、复制局部控制没有产生预期总体收益。不能把这些值与新课程基线 32.40 MHz 直接配对宣布进步。本轮未采用 v7/v11/v12，也未重跑它们。

## 6. 面积、IPC 与 300 MHz 的约束

频率是本阶段主任务。A/B 不计划增加流水线或恢复周期；B 的已知新增缓冲毛面积约 148.5 µm²。C 和架构恢复分级有明确周期代价，单独作为候选，不能未经测量合并为“最优”。更宽 issue、更大 PRF、复制全量读端口不是默认办法。

为评估新增延迟，用同口径基线计算：若额外周期为 ΔC，则 `IPC_new/IPC_old = 1/(1+ΔC/C)`；要避免 IPC 下降超过 10%，需 `ΔC/C ≤ 1/9 ≈ 11.11%`。例如某类事件每千指令 r 次、增加 k 拍且完全不能隐藏，估计额外 CPI 为 `r·k/1000`。这只是对延迟代价的预算，不是 OoO 重调度后的 IPC 保证。当前缺少同口径的完整动态误预测、MUL 依赖和 cache 重放统计，不凭静态指令比例伪造这种数据。

当前同口径总面积的 +10% 参考值约 50940.66 µm²，IPC 的 -10% 参考值约 0.882115；这用于本报告的成本估计，**不重新定义用户早先跨版本比较的已约定基线**。Tier3 本身仍要求面积 ≤36000、IPC ≥1.0985，不能因提频容许范围而宣称最终目标完成。

300 MHz 的预算应落到每个真实寄存边界，留出 clock-to-Q、setup、0.05 ns uncertainty 等开销；组合逻辑可先按约 2.7–3.0 ns 的设计预算规划。每条路径必须包含 SRAM 边界和实际负载；这个预算是设计目标，没有被候选结果证明。

## 7. 测试前的建议顺序与尚未证明之处

本轮交付的是这份报告及 A/B/C 三份可审阅源码，**测试仍未开始**。优先建议 B（已经包含 A）处理当前最有直接证据的广播超载；C 作为乘法长链候选。架构恢复分级是下一批改动的主线，前述失效和保留规则必须先具体落实。

后续若进入验证，先明确最终要测的候选和本批改动，保持 Windows 原生、同一固定课程工具与同一配置。先做一次必要的整机综合/时序/总面积，判断瓶颈是否真的转移、有无显著增益；不要每改一处就启动一次 55 分钟整机作业，也不做模块/参数的铺开测试。达到值得验证的频率增益后，再运行最小必要的官方功能/IPC 检查，最终采用前完成课程要求的正确性确认。候选 A 只在需要归因 B 的结果时使用，不默认三份全部跑。

尚未证明：候选能通过编译与完整功能检查、缓冲拓扑的最终映射与分支 slew、实际 Fmax/总面积、C 的 IPC 代价，以及改动后是否出现新的 cache/LSQ/调度瓶颈。这些都不能由静态分析或开源项目的频率代替。

准备脚本：[prepare_frequency_research_candidates.py](E:/Verilog_cpu/tools/prepare_frequency_research_candidates.py)，仅写源码、补丁和清单，不包含测试工具调用；[只读报告解析脚本](E:/Verilog_cpu/tools/analyze_saved_frequency_paths.py)。
