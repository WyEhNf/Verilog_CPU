# EU 完整组合测试前范围

先完成全部源码实现与审查，再整体冻结、在对话汇报，最后做唯一一次后台课程timing-only。ET、ES、EU均未分项测试；本报告生成时没有新的CPU构建、程序、综合或STA。

参考ER1：**371.418208 MHz**，最低周期2.6923828125ns，含SRAM面积**49,638.890694 μm²**；比EP频率+2.8654%、原面积+7.18899%。频率已超过300，IPC/功能未知，完整Tier3未达。本批EU未测，不能继承ER1指标。

## 两个结构变化

1. 把分配store地址加法移动到生产者一侧，早于完整完成网络source仲裁。每个当前allocation offset分别与各producer值并行加signed12，通过原direct mask选出相同source的结果；保留原zero CDB默认、CDB_WIDTH-1的branch-link覆盖与最高匹配PRF write lane优先级。offset仍是当前分配查询，不跨新边沿；原full live/tag/generation/held-source/ready/recovery许可全部保留。普通stored PRF fallback与关闭新选项的原adder分支不变。原raw value通过组合树向各adder分发，限制新增直接负担。
2. 完整LSQ packet通过环形两类/组内组间前缀winner、分组mask和平衡OR选择。power-of-two行按原(wrap,physical row)规则，空候选仍取最后原叶，payload仍按原slot-width截断索引。N1及非2的幂保留原树。它针对曾测到的请求仲裁结构，并作为第一条链缩短后的备选限制；不声称仍是ER1导出的最慢路径。

累计22组，相对ER1四个RTL文件变化；69个复合时钟块文本相同，零新增声明状态/事务周期，普通整数流水线仍10级。当前BE4/CDB3/producer6，allocation加法器20→32（24producer、4link、4stored），净增12；新source query24位、派生bus512位。继承既有cache first empty-slot load-hit多一拍，其IPC代价仍未知。

ER1新的五条限制路径均2.6319ns，第一条85个门段，经LSQ report/full ROB live/direct completion/PRF value/addition。原请求选择不再出现在导出top5；最大单门0.1349ns，当前应处理跨模块串行联系。不能将现有adder延迟直接从总周期减掉后预测频率。

## 源码审查及边界

EU三个ET文件逐字对应原源码变换，LSQ与ES审查版本SHA相同；原rank/held-source/源选择、branch-link路由及全部时钟块保留。二值推导覆盖同源算术、空源/额外BE lane默认、分支覆盖、offset即时变化、PRF bus索引与最高匹配write、通用关闭分支和ES优先级/默认/参数。候选输入41、当前主源40、既有ER1冻结157 SHA核对。

这是源码审查，不是HDL编译/形式/全核正确性证明。unknown四态行为可能差异；原direct mask合法初始化/one-hot约束继续依赖原实现，没有新授予。更多adder、mask/OR/default及分发控制会增加逻辑面积，也可能暴露其他路径。当前距离原面积+10%上限只余约1,301.77μm²，不能保证映射增量。保留ER1与所有中间候选及原结果，若回退有完整身份依据。

注册load report、全面慢wake延后等会增加依赖周期；ROBlive提前到每LSQ行则增加全generation查询复制。缩窗口/端口/cache、乐观load replay、删掉存活/提交许可均未加入。此批所有有依据的实现和审查已完成，没有更多当前应加入的改动；新路径出来后仍可能需要下一结构方案。

## 唯一下一测量

先在对话汇报最终冻结报告，再对完整EU做一次后台Windows原生Yosys/课程ABC/OpenSTA周期搜索和含SRAM面积计价。无CPU、IPC、correctness、形式或中间候选测试。后台期间继续收集源码方向，保持主/冻结身份。

framework `54fc150ffc290f52aa024209ffb9a29d43856f6d`、testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`；原Yosys0.63/课程ABC/OpenSTA3.1/Verilator5.020、ASAP7 RVT TT/FakeRAM、39项override、queue/issue/cache配置、2ns映射/uncertainty/IO/负载预算与计价不变，禁止WSL。以课程最低可行周期给Fmax，不拿2ns负slack判断300失败。

原面积上限50,940.662839μm²，IPC下限0.882115146585；最终Tier3为area≤36,000含SRAM、IPC≥1.0985、Fmax≥300。频率是当前主目标。足够收益且面积允许后，必要IPC/功能阶段仍须先汇报，只构建一次、6perf+19correctness并复用同一综合身份；目前该阶段工具保持未执行。350MHz只是昂贵程序阶段的工作门槛，不替代原目标。

完整源码研究：`E:/Verilog_cpu/reports/frequency_EU_source_research_2026-10-05.md`。

原ER1结果：`E:/Verilog_cpu/reports/frequency_ER1_measurement_2026-10-05.md`。

源审查：`F:/CPU2026Proofs/EU_source_review_20261005/source_review.json`与`final_scope_review.json`。
