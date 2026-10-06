# ER1 A36运行中与A37独立源码进度

目标仍是同一源码IPC几何平均≥1.1、Fmax>300MHz、含SRAM总面积≤36,000μm²，以及完整RV32IM/OoO执行/顺序退休/课程MMIO退出。目标未完成。

上一轮仅核对实测指标，未改权威源码，归类为无进展；本轮已重新确认A16R2/A21原测量终止，没有重启。A29–A33已有源码与本轮新增A34命名修复、A35就绪store分配数据、A36 D-cache word response已整合冻结，测试前已在对话汇报并落盘完整A36 pretest报告。

A36一次Windows原生课程测量现处运行中：原派发PID=92848，本记录生成时核对该PID仍存活，尚无result/failure。源码展开产物elaborated.json已生成（227,852,855字节），日志已明确启动综合与native perf。没有把展开通过当成CPU功能、综合或时序通过，没有重启或覆写任何测试。A36 IPC/面积/频率尚无最终结果。

A36快照157项源码/依赖文件，其中116项课程依赖字节与A16R2相同；snapshot SHA256=ded2e1ec852fd874016886ba98c75e69e0f3924fd0a8c2a7dcf15155abf13db0。测试前报告SHA256=e63982a07d2b3b387ceade8a44decf71e645161879fefab378d1381832e5a9de。主EU源码哈希仍不变。详细结构收益和验证范围见[ER1_A36_pretest_2026-10-05.md](ER1_A36_pretest_2026-10-05.md)。A36中间候选未逐个测试，本次不立即重跑19correctness或M单元。

本轮新增的旧网表证据：A21 mapped.v与design.json顶层全部235,684个私有cell的顺序类型对应，并核对关键后段5条端口连接在两种格式中一致。端点_430425_/D的DFF源码属性属于rv32m_mdu_iterative.v的原时钟状态过程；起点属于AXI reader过程。尚未定位MDU中的具体字段，不能冒称PRF/RS状态。最慢后段_338495_、_371714_、_372056_的门延迟分别为0.254/0.636/0.876ns，合计1.766ns，其输出负载53.16/53.52/43.08fF。证据只来自旧结果，没有启动新EDA分析。

在A36后台运行时独立完成A37源码：MDU原先一段时钟条件更新的载荷迁入按16位分发写控制的word owners，launch再分为4个owner控制及4个初值mode分支。phase/counter时钟过程等于原过程删除载荷赋值的投影；全部算术/ready-valid/恢复条件为原文本。载荷初始化、迭代、step31 finishing capture、finishing output的边沿和优先级不变，所有载荷仍不复位。无新增寄存位、流水边界或M运算拍数。MDU取消/完整tag/物理目的/输出背压仍保留。新增的分发反相器和event mux可能增加映射逻辑，实际面积/频率仍未知。

A37尚未启动任何HDL/EDA/CPU/单元测试，未采用；A36快照/manifest/manager/report未编辑。当前最新独立源码：F:\CPU2026Candidates\tier3_er1_20261005\A37_mdu_local_payload_owners，candidate SHA256=7fb716e252d610b9b9acbcaee8c4fb6965b0d87f65485216fa445a4d59290f57。不把A37结构估算同A16/A21指标混用。

下一步继续观察原A36派发句柄与实际产物，并分析新结果对应的IPC瓶颈、critical path与面积所有者。若A36显示相称收益且值得采用，再对同一冻结源码完成19项课程正确性及全部M、恢复、缓存/FQ背压/错误/region和BTB别名、自然对齐word response、partial-forward/store分配依赖等相关验证。A37仅在明确净收益依据及测试前报告后测量；不得每次源码改动重复完整测试。
