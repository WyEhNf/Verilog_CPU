# CM 频率优化实现与剩余方向

当前工作树已采用 **CM**，冻结输入为 [architecture_CM_20261004](F:/CPU2026CourseRuns/architecture_CM_20261004/source_manifest.json)，157 个文件；**没有启动编译、仿真、综合、STA 或形式验证**。相对已测 CD1，本批只改四个 RTL 文件：Dcache nonblocking、Icache nonblocking、LSQ 和普通 RTL 分发/选择模块。冻结工具列出的 23 个实现文件包含此前已完成的 CD1 改动，不表示此次又改了 23 个文件。

CD1 与中间候选均保留。工作树从 CD1 到 CL 的备份为 [pre_CL](F:/CPU2026Candidates/pre_CL_worktree_20261004/backup.json)，CL 到 CM 为 [pre_CM](F:/CPU2026Candidates/pre_CM_worktree_20261004/backup.json)。新工作树的频率、IPC、面积和正确性均为未知，下面的测量属于旧 CD1。

## 已有实测结论

CD1 官方 Fmax **99.65936739659368 MHz**，最小周期 **10.0341796875 ns**；含 SRAM 总面积 **49851.29213392186 µm²**；六项 perf 的 IPC GEOMEAN **0.7823728642153719**。相对同工具、同内存延迟的基线，频率 +207.6107%、面积 +7.64764%、IPC −20.17646%。仍未达到 300 MHz，IPC 已超出此前 ±10% 范围，总面积和 IPC 也未达到 Tier3。

CD1 官方正确性已结束：**16/19**，pi、qsort、tak 在原课程 `cycles=1000000` 上限超时。原驱动生成 [failure.json](F:/CPU2026CourseRuns/architecture_CD1_20261004/result/failure.json)，状态 INCOMPLETE。没有提高周期上限或追加诊断仿真，不能仅凭超时断言是运行变慢或死锁。

最慢五条路径都经过 Dcache metadata 的共享 way 控制。共同的 AOI31xp33 输出驱动 1255 个输入脚，STA 电容 572.3894 fF、单门延迟 6.6391 ns、输出 slew 14.3106 ns；随后 INV 的延迟又达到 2.4430 ns，两段约占 9.9780 ns 最慢到达时间的 91%。这属于驱动负载及后续 slew 的问题，继续增加流水级不能直接消除它。

## 本批已实现的八组修改

| 增量候选 | 实现 | 时序/状态约束 |
|---|---|---|
| CF，继承 CE | Dcache metadata 的最终 action、way、refill/local entry、查询地址与 acceptance 分发到 64 个现有 owner；当前 packet 从 95 位缩为 52 位 | LOCAL_QUERY 模式只传 miss/prefetch/hit 的 way bit；refill/local full entry、捕获的 full set 保留；旧查询模式仍传完整字段 |
| CG | 五个 load 提取器用 88→56→40→32 位的四段组合字节选择，每个 amount leaf 最多控制 16 位；hit/deferred 的输出和捕获复用结果 | 不增加寄存级；保留完整 128 位逻辑右移与行末零填充、byte/half 符号/零扩展及 default word 行为 |
| CG | waiter 的 response-store 整行选择拆为八组 16 位 leaf | response/local/allocate 的原写入优先级、waiter 生命周期与原边沿保留 |
| CH | Icache tag 用原 refill 边沿的静态 row owner；entry/tag 每四行一组、LRU set/way 每四 set 一组；公开 128 位 response 选择分成八组 | tag FF 数、数据 SRAM、tag 初始化与 valid 暴露关系、refill 高于 hit 的 LRU 优先级保留 |
| CI | LSQ head 的年龄/ack/pop 查询按 row 分发；head 的六个状态字段用静态并行读 | head/tail/occupancy、环形年龄和恢复规则未改 |
| CJ | LSQ cache response 用当前 60 位 packet 查询同一 row，返回身份逐 row 分发；line 提取和 line-valid mux 控制分组 | 完整 generation 匹配、低地址 nibble、forward mask/bytes、ROB tag、size/unsigned 归属及恢复优先级保留 |
| CK | LSQ 已选指令状态、picked payload 和 candidate flags 分别静态读取，消除多个数组之间共享的宽译码 | 原 full tag/generation/live 检查保留；REQUEST_PIPELINE=0 的旧模式字段也保留 |
| CL、CM | CL 将 LSQ recovery 的边界分发到 row，并用四层合并替换 16 项条件整数累加/首个 kill 扫描；CM 将全局 Dcache refill/local/store 数据选择拆为八组 | keep 只计 live 且在 occupancy 内的 row；保护 committed store/retired load，选择按 LSQ 年龄最早的 kill，无 kill 时 tail 回退原值；Dcache byte mask 与 refill>local>request 优先级保留 |

全批没有新增功能寄存位、缓存容量或流水级，普通整数路径仍为此前十级。以上是源码设计与人工推导，**不是实测等价性、面积或频率证明**。分发树会增加真实组合门，原课程必须映射并计入面积，不能假定面积变化一定在 ±10% 内。当前尚无新的 IPC/正确性结果，不能宣称原来的三个超时已解决。

## 现成网表的负载追查

只读工具分析旧 CD1 的 `design.json`、课程 Liberty 与已有路径，没有启动硬件工具。[详细负载记录](F:/CPU2026Proofs/CD1_existing_mapped_loads_detail_20261004/loads.json)枚举 top 的 414473 个 driven-net 记录，按已知名义输入电容保留前 100 项。子模块输入递归展开；不覆盖所有内部 owner 驱动或所有外部穿透负载。名义电容和 STA 的方向相关电容不同，不应把两者混称实测路径电容。

| 旧 CD1 节点 | 输入脚数 | 名义电容 fF | 本批对应措施 |
|---|---:|---:|---|
| request_victim_entry[0] | 1286 | 650.14 | CF 去除直接到 64 metadata bank 的共享输入负载 |
| prefetch_victim_entry[0] | 1255 | 574.43 | CF；同一个驱动在 STA 中为 572.3894 fF |
| request_hit_entry[0] | 418 | 207.97 | CF；原有 SRAM command 和其他少量消费者仍存在 |
| query_response_mshr_store | 460 | 207.12 | CF metadata 分发，CG waiter 整行选择，CM 全局 refill merge 分组 |
| static_request_action[3] | 336 | 173.57 | CF 先分发最终 action，再在 metadata owner 内译码 |
| 隐藏 INV 的 reset 反相 | 375 | 164.85 | 课程 STA reset case 为 0；未当成工作状态关键路径，也未据此扩大复位改动 |
| 隐藏 DFF 的 Dcache query-input 地址字段 | 367 | 156.10 | CG 将 load byte-offset 消费者控制负载分组 |
| refill_array_write | 286 | 143.53 | CF、CM；保留原事务与资格判断 |
| waiter store_event，两个域 | 每域 257 | 每域 94.77 | CG 每个 waiter 的数据 mux 拆成八组 |
| 隐藏 Icache response 源选择 DFF | 257 | 95.69 | CH 公开 response-line 选择分组 |
| LSQ 隐藏 head 译码节点 | 约 154–170 | 约 65.79–75.55 | CI 静态 head packet 和逐 row 查询 |
| LSQ 隐藏 selection 查询组合节点 | 150 | 80.23 | CK 静态 selected/picked/candidate 查询 |
| LSQ recovery_head 输入，两个位 | 58、61 | 53.35、52.56 | CL owner-local recovery boundary |

隐藏网名通过已有 mapped 输入连接及保留的 source/hierarchy 信息追查；不能仅凭其中一个 alias 判定功能。部分匿名节点仍未完全确定，不能声称已逐条修复全芯片的每一条路径。

## 更大架构方向与采用条件

| 方向 | 可能收益与代价 | 当前判断 |
|---|---|---|
| 继续分发最终消费者控制；选择 leaf 大小而非只复制上层信号 | 直接减少过载与下游 slew；增加组合门与分发层数 | 本批主线，已覆盖最大的已定位负载；仍需核对 AXI、MDU 和匿名节点 |
| metadata-only RS，移动已有 dispatch/read 边界到 issue 后 | 减少 RS operand 状态与写入/读取负载，缩短 rename/dispatch；增加 PRF 端口/旁路责任 | 候选架构仍可发展；必须处理 held producer、early-store probe、资源保留及反压，不能无理由增加第十一级 |
| 将 producer 存活资格放到执行单元内部 | 移除 ROB query→wake 前向串行段 | 先覆盖 MDU pending/MUL 各段/DIV/result 的选择性取消与 slot/phys 重用；保留 completion generation 防护 |
| 在原 load completion 边沿保存目的物理编号 | 让结果 value/tag/phys 同时进入唤醒，移除后置 16-row 查询 | 表当前已是 16×6，不是 64-row；必须保证旧响应不能取到新事务的目的编号 |
| RS 类型分队列、簇内唤醒与 operand routing | 缩小局部广播/选择 | 需要同时解决 12-row 总容量均衡、跨簇依赖和 dispatch credit；硬按类型划分可能恶化 IPC |
| ready rank 饱和计数或分组选择 | 只保留前四名所需排名，可能缩短排序 | 当前已经是 pair matrix 和二叉 popcount，不能重复宣称线性排名已改平衡；饱和逻辑未必更快 |
| 算术结构：prefix/carry-select、移位控制、MDU 最终资格分组 | 缩短正常负载下的长 carry/控制链 | DIV 的 D/2D/3D 已并行，MUL CSA→CPA 已分拍；不能重复算作新方案；需明确实际剩余路径 |
| frontend lookahead predictor 与提前 tag/index 查询 | 缩短 response→prediction→next-PC | 必须绑定 PC/epoch，解决 line 边界与 branch recovery，不能使用前一请求的预测 |
| 精确 branch 快速反馈和 issue FIFO 同拍容量恢复 | 改善加深流水后的依赖/分支损失 | 主要用于恢复 IPC；频率优先，不能以长 ready/flush 反馈重新破坏已切断的路径 |
| 更小缓存/ROB/RS 或复用 payload | 减小负载、面积及读写复杂度 | 会改变 IPC 和容量；仍要参数化及敏感性分析；现阶段优先保留容量定位结构问题 |
| 改课程 ABC script、库、时序约束或用外部 BUF stub | 数字会改变，但失去同标准比较 | 不作为本任务的实现方向；课程流程和 SRAM 白名单固定 |

上述方向尚能继续研究，**本记录不宣称已经想尽一切办法，也不启动下一轮测试**。继续源代码推导和匿名驱动追查；只有完成当前可实行修改、没有新的可落地改法时，先向用户提交统一测试前汇报，再在 Windows 原生环境后台测量同一冻结版本。

## 原始资料与推断边界

固定 OpenSTA commit 的 [TableModel.cc](https://raw.githubusercontent.com/The-OpenROAD-Project/OpenSTA/f89887b59600cd3a2a10c3de31bda4235d904cdf/liberty/TableModel.cc)用输入 slew 与 load 查门延迟/输出 slew；超出表轴上端时仍选最后两个点计算。这支持“过载会同时恶化驱动与后继门”的解释；本次具体瓶颈来自已有 STA 数值，不能把名义电容清单直接换算成 CM 的 Fmax。

[BOOM pipeline 文档](https://docs.boom-core.org/en/latest/sections/intro-overview/boom-pipeline.html)区分概念阶段、实际合并阶段和异步提交。本设计下一步重排边界应以真实寄存器和握手为依据；不能将 FIFO 两个存储槽当作两级流水，或把 MDU 内部级数叠加到全核固定级数。[此前原始论文、BOOM/香山及固定 ABC 实现的完整研究](E:/Verilog_cpu/reports/frequency_postfreeze_research_2026-10-04.md)继续有效。
