# DD 统一批次测试前汇报

**汇报时尚未启动任何新 HDL/EDA/仿真测试。** 已采用 DD，源码冻结到 [architecture_DD_20261005](F:/CPU2026CourseRuns/architecture_DD_20261005/source_manifest.json)，40 个活动输入与 157 个冻结输入的 SHA 由 [活动记录](E:/Verilog_cpu/build/cpu2026/active_frequency_implementation_20261004.json)核对。完整新增方程、位宽、所有权、反压和恢复推导见 [DD 实现报告](E:/Verilog_cpu/reports/frequency_batch_DD_implementation_2026-10-05.md)。旧快照保留，当前指标均为未知。

本轮已完成有旧路径证据或可直接从现有源码推导的结构重排。下面列出全部采用的方向，以及需要新瓶颈证据或架构前提才能实施的方向。这不等于声称未来不可能再有方案：下一步需要看到这份已大幅改变的电路实际怎样被课程 ABC 映射，才能判断剩余路径的主次。

## 旧证据与这次要解决的主问题

最近真正测过的是 **CD1**，Windows 原生课程固定版本。Fmax **99.65936739659368 MHz**、最小周期 **10.0341796875 ns**；IPC GEOMEAN **0.7823728642153719**；含 SRAM 总面积 **49851.29213392186 µm²**；正确性 **16/19**，pi/qsort/tak 达到原 1000000 周期上限。旧完整同规范基线为 32.39788654411997 MHz / IPC 0.9801279406499007 / 46309.69349394434 µm²。

CD1 相对该基线频率 +207.61%，面积 +7.65%，IPC −20.18%。面积在此前 ±10% 范围，IPC 已超出，不能称三项已可控。频率距离 300 MHz 仍远，最终 Tier3 的面积 ≤36000 和 IPC ≥1.0985 也未达成。DD 没有测量数字，不能把上述旧数字标到新源码。

旧课程最慢五条样本为 9.9780、9.9670、9.9650、9.9430、9.9420 ns 到达时间。共同 AOI31xp33 输出驱动 **1255 个实际输入脚、572.3894 fF**，门延迟 **6.6391 ns**，下一 INV 延迟 **2.4430 ns**，两段约占第一条路径 91%。按 packet 位回溯为 Dcache `prefetch_victim_entry[0]`。本轮优先改最终控制/索引的实际消费者，而不是只继续给外围插寄存器。

证据来自 [现成课程结果汇总](F:/CPU2026Proofs/CD1_existing_reports_20261004/summary.md)与 [现成映射负载目录](F:/CPU2026Proofs/CD1_existing_mapped_loads_detail_20261004/loads.json)。后者名义 Liberty 电容排序不是所有端点的 STA 延迟排名。课程原报告只给五条最慢样本，不能虚构其余路径耗时；高负载清单也不是逐条 timing closure 证明。

## 已采用的全部结构方向

相对实测 CD1，改动十三个 RTL 文件；这些文件内的累计研究/实现可分为下面 25 组，部分后续方案替换前组的算术结构，不能把各组预计收益相加。

| 组 | 最终实现中的作用 |
|---|---|
| CF | Dcache 最终 action/entry/query/acceptance 分发到 metadata owner；避免一条最终输入仍直驱全体 bank |
| CG | Dcache 128 位 line→32 位 waiter 数据提取按有界组组织 |
| CH | Icache tag/LRU/response 的实际控制消费者分组 |
| CI | LSQ head 查询分发、静态行读，减少大表动态读取与广播 |
| CJ | LSQ response 元数据打包，完整返回身份保留 |
| CK | LSQ selection 的状态和 payload 静态读取，替换反复动态索引 |
| CL | LSQ 恢复保留数/尾部定位使用平衡树；尾部年龄选择后续由 DC 化简 |
| CM | Dcache refill/store 宽数据按八个 16 位控制组写入 |
| CN | LSQ 请求数据先在 32 位源间选择再插入 128 位 line，最终 valid 放在移位之后分组 |
| CO | DIV prepare/iterate/finish/cache 等写入使能分发，保留已有 radix4 的并行三种 trial |
| CP | ROB 恢复描述符、查询、静态行访问与回收控制分组 |
| CQ | MDU launch 元数据与完成 payload 分组选择/写入 |
| CR | Icache 四个 JAL target 并行计算，再选择目标；原预测顺序不改 |
| CS | MUL 真正的部分积消费者与写入组分发；旧部分积算法由 DA 替换，16 位写入与 metadata owner 保留 |
| CT | Dcache tag SRAM 的 demand/nextline/way 端口分组；按课程 lane 规则保持原宏形状/数量与读写行为 |
| CU/CU1 | ROB physical reclaim 的 high/low 预译码，避免 eligible 直接参与所有目的编号比较；保留去重与计数 |
| CV | LSQ 完成值/tag/物理目的一起选择，删除报告后的第二次目的表读；同一 96 位表移入 LSQ |
| CW | RS 直接产生 rank0–3 的精确计数谓词，保留年龄矩阵、ready、issue policy 和更宽 fallback |
| CX/CX1 | 完整 ALU/MDU task owner 本地恢复取消，覆盖 held、shift、pending、MUL 各段、DIV 最后一拍；MDU busy 来自实际占用 |
| CY | ALU/MDU 结果到达后的 wake 资格依靠本地有效任务，避免串行 ROB 查询；完成仍查完整 ROB 身份 |
| CZ | ALU 加法与 MUL 最终 CPA 的进位选择尾部 |
| DA | 17 个 Booth digit 加补偿行，CSA 三层/三层，S1 少声明 128 位 |
| DB | load report 同行 unretired 与本地恢复年龄，去掉 load wake 的 ROB 表读取；正常完成防护保留 |
| DC | LSQ oldest/youngest tournament 以一位环形 wrap key 代替每层完整年龄比较 |
| DD | LSQ 固定行间依赖顺序按常量位置化简为 wrap 逻辑，前递目标使用 circular slot key；控制分组 |

这批没有新增加普通流水级或固定返回周期；仍为十级普通整数流水。39 项课程顶层设置和容量/内存延迟 10 保留。功能状态没有主动增加，MUL S1 少声明 128 位，但实际标准单元面积、常量剪枝、分发门数量和被推导出的 FF 必须由课程结果判断。不能用“未加 FF”保证总面积 ±10%。

## 其余方向的处置

| 方向 | 目前结论与下一步触发条件 |
|---|---|
| RS/执行分簇、依赖 FIFO steering | 可以缩短跨全窗口广播，但需要完整的 dispatch steering、容量再平衡、跨簇结果传输和冲突处理；会改变现有一拍 RAW 与 IPC。先看 CY/DB 去掉查询后的真正 wake/select 路径。若仍是主瓶颈，采用两簇并明确同簇/跨簇旁路和容量策略，不能只把 12 项队列机械切半 |
| metadata-only RS + 发射后 PRF 读 | 当前 RS issue 已选择缓存操作数；改为先选物理编号再查 64 行 PRF，会把大读表串在晚到选择之后。独立 PRF stage 还涉及 issue FIFO 持有任务的晚绑定、store probe 和旁路。需要替换既有阶段并定义所有权，不是零成本删 RS 值寄存器 |
| wake/select 再加一拍 | 会增加相关指令间隔；IPC 旧版已退步 20.18%。当前先去串行查表、改排名与环形选择。若新报告确认为 select 段瓶颈，再移动已有边界并计算/处理旁路及依赖等待，而非直接变成十一、十二级 |
| issue 时预测完成/推测唤醒 | issue FIFO/MDU/完成网络均可受反压；没有固定完成拍。当前消费者发射时已捕获值，不能只提前置 ready。需要保留未成功消费者、重放或 late binding/credit。当前采用结果已实际到达后的非推测 wake |
| PRF 换 SRAM | 课程 FakeRAM 是同步单端口，写入同拍读无效；多路写/读需要复制、bank collision 处理、最新值表或旁路。当前无法把 FF 表直接替换而保持现有端口和发射语义。若新报告确认 PRF 仍主导，先设计 bank/复制与冲突重试，再评价 SRAM 含面积 |
| 分离 load/store queue、保存 store dependency mask | 可把依赖年龄移到分配阶段，但新增 mask 状态/清除广播，或改变统一 16 项队列的容量共享及队列间序号。DD 已在不加 mask 的前提下化简固定位置年龄关系；只有新瓶颈仍在 LSU 时再选这一架构方向 |
| radix8 Booth | 需要 ±3A 的预计算加法或额外表示/行；省一层压缩不等于首段一定更短。DA 当前已三层/三层。若实测 Booth 编码/首段压缩仍长，比较列级 Dadda/4:2 压缩或另配表示；不默认再加宽算术到首段 |
| 列级 Dadda/不同 prefix 拓扑 | 是可保留的次级候选，但当前 CSA 已三/三层、进位尾部已选择化；无新报告不能知道哪一层、负载或拓扑还主导。新报告若指向 CSA/CPA，再按实际列高度与 fanout 选择稀疏前缀/Dadda，而不是循环改名称 |
| DIV 更高 radix | 减少迭代次数主要影响延迟/吞吐；更多候选余数会增加每拍比较/选择的宽度。现有 radix4 已并行 D/2D/3D，CO 又处理写入广播。只有新结果指向该段，再重平衡其 prepare/iterate/finish 边界 |
| 再给 MUL 插一拍 | DA 已减少行数并在原三阶段内平衡；没有新证据不增加返回周期和状态。若仍是时序瓶颈，按实际路径分割，而非因乘法器存在就假定其为全核瓶颈 |
| 前端 lookahead / 移 cache 边界 | 已有注册请求、epoch、取消和响应缓存。改变边界需要处理 response/epoch/请求复用责任与分支惩罚；CR 已并行 JAL target，cache 也已分发。新报告若指向该段，再以现有握手 owner 为界拆分 |
| 缩小 ROB/RS/PRF/cache | 不属于保留当前容量的本轮频率优化，会直接改变 IPC；后续必须做的参数敏感性阶段再分析，当前不靠缩容量伪装结构增益 |
| 三个匿名 mapped FF 高负载 | 已有旧 FF 源 process 范围但没有精确字段归属。42/91 来自 ROB always，53 来自 word-bank always；别名与下游不能证明源字段。旧电路已经改变，需新可识别网表/路径再定位，不盲改 head/tail 等猜测字段 |
| 外部 BUF 黑盒、改 ABC/STA 约束 | L1 曾被课程白名单拒绝。采用普通功能 RTL 分发并按原课程映射/计价；不修改白名单、库、ideal-clock 或评分约束 |

采用的优先级有文献和实现依据：[Palacharla/Jouppi/Smith 的 ISCA 1997 原作者资料](https://ftp.cs.wisc.edu/sohi/talks/1997/isca.complexity.pdf)分析 wakeup/select/bypass 随窗口/发射规模增长，并讨论依赖 steering 和分簇的代价。其工艺和实验数字不能用来预测本 CPU 的 MHz。[BOOM issue 文档](https://docs.boom-core.org/en/latest/sections/issue-units.html)说明快/慢唤醒及推测 issue 的重试责任；[BOOM LSU 文档](https://docs.boom-core.org/en/latest/sections/load-store-unit.html)展示 load 的 store dependency mask 和未知/重叠 store 的处理。本项目保留原非推测 memory 规则，DD 的 wrap 化简由本设计队列顺序推导，并非复制 BOOM 频率结果。

## 一次统一测试的拟定范围

测试启动前先在会话汇报此文档、冻结身份、所有主要改动和风险。此文档本身不启动测试，也不需要新建 WSL 环境或改课程工具。

1. 对这一份冻结输入做一次 Windows 原生构建及课程综合/STA，原驱动可并行推进 CPU 构建与综合，不逐组跑回归，不启动参数 sweep。
2. 用同一生成的课程 CPU 跑六项原 perf，保持内存延迟 10、官方 dynamic_instructions 分子和 GEOMEAN；跑一次 19 项原 correctness。旧三个超时仍按原上限检查，不擅自加大周期预算。
3. 新算术/所有权不能只靠 perf 名称推断覆盖：`perf_multiply` 实际是软件乘法。只补少量 RV32M 符号/高半边界和恢复、受反压、迟到 load、目的复用的定向场景；不逐项跑长随机、全参数或形式回归。具体 fixture 必须使用冻结源码及同一固定 Verilator，结果与全核课程数值分开。
4. 首次映射后只读取现成结果，检查最大路径是否还为高电容广播、分发是否实际保留、SRAM 宏与总面积、当前正确性及 IPC。原 STA 只给五条路径时，明确样本限制，不把 nominal fanout 排名写成全路径耗时。
5. 仅在构建失败、新功能失败或新最慢路径提供证据时追加修正/诊断；旧输入与失败日志保留，新修正另冻身份。不是每次修改重复一套大测试。

主驱动：[run_course_standard_windows.py](E:/Verilog_cpu/tools/run_course_standard_windows.py)。冻结配置：[course_windows_config.json](F:/CPU2026CourseRuns/architecture_DD_20261005/course_windows_config.json)。未来的 `--clock-period 2.0` 只是原 ABC 请求目标，不是 500 MHz 的实测结论；频率来自原 STA 最小周期，300 MHz 对应 3.3333 ns 上限。

## 固定课程环境与最大风险

框架 `54fc150ffc290f52aa024209ffb9a29d43856f6d`，testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`；Yosys 0.63 `70a11c6bf0e8dd669f56c7da3587f78b405138e2`；ABC `8e401543d3ecf65e3a3631c7a271793a4d356cb0`；OpenSTA 3.1.0 `f89887b59600cd3a2a10c3de31bda4235d904cdf`；Verilator 5.020 `5c5314b39cd888f427807d626e1502cbf222c292`。Windows 二进制与五份 ASAP7 RVT TT 库身份见 [工具清单](F:/CPU2026CourseTools/win54fc150/toolchain_manifest.json)。原课程源码、仿真输入输出约定、FakeRAM 计价、ideal clock 和 STA 约束均沿用。

最需要验证的是新 wake 对 ROB/物理目的生命周期的依赖、恢复/完成同拍、多个 MUL 段同拍取消/替换、DIV 最后一拍取消、Booth 符号/补偿、LSQ head 回绕及每字节前递。实际 ABC 可能消除、重新组合或把成本移到其他路径。所有新优化的 MHz 增益、正确性、面积 ±10% 和 IPC 控制范围都未证明。

到此已有依据、可在原边沿/容量内直接落实的方向已合入；剩余方案已写出其前提和触发条件。下一份映射应决定下一轮主次，不能再用旧 CD1 路径替新电路臆测时序。
