# EL1 后台期间的后续源码研究

EL1 已先向用户汇报完整范围，再启动一次 Windows 原生 timing-only 测量；没有启动 Verilator/IPC/功能程序。本文件不是新的测试计划，也不改变正在测量的源。

## EM：共享探测的正常 ROB 槽号先解码，条件备选

继续读 EL1 源码及 EF 保存路径。共享 probe 原 suffix 是选出完整 ROB tag 后，再解码其槽号查询正常 valid/full generation；EF 的旧路径确实经过这一后缀。当前 EL1 已切断前面的 LSQ wake 联系，新结果尚未说明这个后缀是否仍限制全局频率。

EM 把每行保存的 ROB slot 先解码成低/高银行掩码，随同原 full tag、LSQ tag、RS one-hot 按原 oldest/lowest 优先级选择。既有 bank-mask reader 查询相同 ROB 行；后端正常 valid、完整 generation、reset/flush/branch-busy 全部保留。零新增状态和周期，普通整数流水线仍为 10 级。当前 query 16 位、选择包 46→62 位；多出的选择负载和静态译码可能抵消收益，未测频率/面积。

没有 eligible 行时，新 mask 为零，内部 selected_live 会从原默认 ROB 行0改为零。但这个内部值只有 shared-valid 一个消费者，而该表达式已经被 selected=0 禁用；输出 address、tag 和其他选择 payload 保持原来。没有将 ROB 授权加入优先级筛选，因此 stale oldest 仍抑制 shared-valid，不改成选择后续行。

当前 RS_ISSUE_METADATA=1，immediate 已从 RS 选出。EM 不声称优化 ROB immediate 动态读；实际只处理正常 live 查询。通用默认参数为 0，原 packet/read 保留；零宽 high bank 单独处理。

已核对候选 41 个输入、69 个复合时钟块与 EL1 相同，原 store selector 的 eligible/upper/first 和 link lifecycle 文本相同，原后端完整 valid/generation guard 与所有地址加法文本相同。仅源码/二值关系检查，不是功能或形式等价测试。EL1 主输入40、冻结157及不可变测试前报告哈希仍一致。

候选：`F:/CPU2026Candidates/frequency_research_20261003/EM_shared_store_rob_query_predecode`。审查：`F:/CPU2026Proofs/EM_source_review_20261005/source_review.json`。没有采用 EM，没有单项测量。只有完成的 EL1 路径仍显示该 suffix 是主要瓶颈时，才考虑组合它；下一测量前仍需先汇报。

## EL1 完成：266.88 MHz，真实限制变成宽 MMIO 选择

EL1 单次 Windows 原生 timing-only 完成：266.875163 MHz、含 SRAM 49,613.040354 μm²；相对 EF 频率 -27.9646%、面积 +1.0100%，原面积基线 +7.1332%。没有 CPU 构建、IPC 或功能程序。不能把这次回归归因到某个单项改动；五条最慢路径现在都经过 enabled_words 别名所在的 165-load NOR4（1.1544 ns）及 47-load INV（0.7405 ns），原缓存四条不再是导出的最慢路径。

只读新映射 JSON，得到函数 result[0] 的公共别名与 165 个真实消费者。当前缓存常规 mask 只有 ffff/0000，退出请求 mask000f，所以 count 低位与 MMIO 请求条件等价。此别名不能被误当成仅属于 bridge 的计数输出；修改 bridge 计数或只给它增加分发不会解决 CPU 宽 mux 的最终消费者。

## EN1 与 EO1：已实现完整源码组合，尚未测试

EN1 保留 MMIO 的完整地址/mask/valid/store 检测和原 acknowledgement 时钟块；低32位数据仍精确来自原请求，上96位在 MMIO 下固定零，普通请求保留完整128位。17个控制域让每个数据叶最多服务16位。桥仍只给非零 mask 的 word 发 AW/W；退出请求只有第0 word 启用，所以被清零的上96位不改变任何 AXI 写或返回码。上位固定零还确保MMIO回压时整个请求稳定。此前 EN/EO 草稿保留，但采用此稳定的 EN1/EO1 分支。

EO1 复用 Dcache 已有完整 response metadata/data owners 和 resp_valid_reg，CPU 将新增默认1的 HIT_BYPASS 参数置0。接受 hit 后从已有寄存器返回，空响应槽的首次 hit 多一拍；普通整数流水线仍10级，零新增状态。保持原 request_fire/capture、响应槽回压、reset、store-ack bypass、miss/waiter 仲裁。已有 EF 第2–5条路径明确经过 response_output_tree.g_driver[0]，源码 bit0 就是 bypass_load_hit；这一修改切断整个 MSHR 仲裁→hit输出→LSQ选行/提取联系，而非只修一个门。

EL1→EN1→EO1 的41个候选输入、69个复合时钟块已核对，除两个 RTL 的组合式/参数外其余源相同。时钟文本相同不等于周期行为相同：HIT_BYPASS0有意改变首次hit返回时刻；IPC尚未知。审查：`F:/CPU2026Proofs/EO1_source_review_20261005/source_review.json`。当前主工作区仍是测得266.88MHz的EL1；没有新测量。

EM 的共享 ROB 查询预解码与逐行缓存响应分类思路仍分开保存：当前实际路径不支持混入前者，EO1 已将后者的已证跨模块关键消费者移到现有寄存器边界。暂未找到另一个依据充分、应继续混入这批的结构变换。最终冻结后先汇报，再只测整体频率/面积一次；不得测中间草稿或用 EF/EL1 指标替代 EO1 指标。

## EP：组合加入 LSQ 选择字段的写使能分组

EL1 路径末尾还经过 selection_write_tree 的地址写叶，服务32位 hold mux（64输入连接），延迟0.1189ns。EP 将原有全部选择 payload 的同拍写入移到已有 word-bank：宽度 SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72，当前110位、7组，每组最多16位。输入/输出字段顺序相同，完整 LSQ/ROB tag 保留，原 selection_valid/forwarding_hold_valid 的 reset/flush/recovery/kill/done 优先级完全相同。没有新状态或 LSQ 阶段；映射后的重复位是否合并仍待测。

完整组合现为 EL1→EN1→EO1→EP；相对 EL1 仅 LSQ/Dcache/CPU core 三文件变化。68个复合时钟块文本原样，一个时钟块仅移除旧 payload 写入后其余文本相同；word-bank 的单语句时钟写另行人工核对。继承 EO1 的17域 MMIO 与首次空槽 hit+1拍。审查：`F:/CPU2026Proofs/EP_source_review_20261005/source_review.json`。本次 source/hash/握手审查未调用任何 HDL/EDA；当前主工作区仍 EL1。下次只能冻结 EP 并先报告，再测完整19组组合一次，不能单测 EN1/EO1/EP 子项。
