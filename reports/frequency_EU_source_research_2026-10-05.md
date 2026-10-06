# ER1 新关键路径与 EU 完整源码候选

ER1的唯一课程原生timing-only完成：371.418208MHz，周期2.6923828125ns，含SRAM总面积49,638.890694μm²；相对EP频率+2.8654%、面积+0.09870%，原面积基线+7.18899%，在±10%内。IPC和功能未测，Tier3面积未到。所有当前数值只属于ER1；EU、ET和ES都未测、未采用。

五条导出路径均2.6319ns，沿LSQ报告边界→完成行选择/ROB query→完整存活确认→direct CDB源仲裁→分支链接值覆盖→PRF旁路store地址加法→LSQ分配写入。第一条有85个门段；公开检查点为report_bound 0.3241ns、完成ROB query 1.0247ns、live_read/value_o 1.2479ns、direct payload选择控制1.6602ns、PRF write_data别名1.9601ns、simm12 sum[30] 2.4265ns，最后2.6319ns。无需把private门名硬认成某寄存字段。

原请求pick_payload_read及g_pick没有出现在新的五条导出限制路径里。不能因此断言全网表其他请求路径没有限制；课程只导出了五条。最大单门0.1349ns/17loads，不再是原先多个67/68负载门吞掉一半周期的模式。当前重点是多模块串行逻辑，而非继续盲目加缓冲。

## ET：在仲裁前计算各生产者的分配地址

旧EG已把PRF存储读与各WB lane加法并行，但WB lane的value仍须等待LSQ报告资格、完整ROBlive、CDB source仲裁和branch-link覆盖。ET更早计算各producer_value与当前分配offset之和，通过原direct payload源mask选相同source的sum；不新增CDB授权、不移除ROB/generation/recovery许可，也不增加寄存边界。

Completion只导出原选源mask及原reset/flush资格，held-source/tag、rank、cursor、ready和payload旧逻辑保留。Backend按分配lane与producer并行加signed12，再用该mask合并地址。无源时用zero+相同signed12，保留原零CDB默认值。branch_pending&&branch_pending_rd_we在原CDB_WIDTH-1 lane选择同一branch link加法结果；不是按当前偶合的BE_WIDTH-2硬编码。PRF按(a*BE_WIDTH+w)*32取得对应地址，原最高匹配写优先级、P0/越界和stored fallback保留。

这些offset是当前分配查询输入；在CDB held期间可改变，派生地址同步使用当前offset，原分配fire在原边沿捕获。没有将offset拼进跨拍producer事务。producer与link base通过既有组合control tree向各分配lane分发，避免原raw value直接多出四个adder的输入负担；缓冲有实际面积和延迟。

当前4分配lane/6producer/3CDB：旧allocation simm12为20个（4 stored+16 WB）；新32个（24 producer+4 link+4 stored），净增12。来源query24位、纯组合派生bus512位。关闭parallel store address或非direct completion时，原PRF WB adder分支保留；独立PRF新选项默认0。

## EU：完整组合

EU在ET基础上合入已审查ES环形前缀/one-hot packet选择，累计22组。ES是之前实际限制路径的结构备选，用于防止当前链缩短后再次受到旧请求仲裁串行层限制；不声称它仍是ER1导出的top5。ES与ET各自保留，均不单独测试。相对ER1仅四个RTL文件变化，69个复合时钟块文本相同，零新增声明状态/事务周期，普通整数流水线10级不变。原cache首次空槽load-hit回复多一拍仍继承，IPC成本未知。

完整源码变换、字段/二值选择/默认值/当前offset/branch link/参数推导与输入SHA核对单独保存，不是HDL/形式/全核功能证明。四态unknown可能差异；新增源算术、掩码/OR、缺省路径和控制分发可能提高面积，旧非导出路径可能成为新限制。不能减去现有adder耗时后直接预测MHz。面积上限50,940.662839仅剩约1,301.77μm²余量，实际是否可控只能由最终整批计价决定。

本轮尚未启动CPU构建、程序或新的综合/STA。程序工作流工具保持未执行。待整批范围确定、身份冻结并在对话汇报具体测试前报告后，才对完整候选做一次后台原生timing-only。无分项/中间候选测试；期间继续源研究。后续必要IPC/功能阶段仍先汇报、仅在频率收益与面积允许时进行并复用同一时序报告。

当前完整报告：`E:/Verilog_cpu/reports/frequency_ER1_measurement_2026-10-05.md`。

候选：`F:/CPU2026Candidates/frequency_research_20261003/EU_prefix_pick_and_prearbitration_store_addresses`。

源审查：`F:/CPU2026Proofs/EU_source_review_20261005/source_review.json`。
