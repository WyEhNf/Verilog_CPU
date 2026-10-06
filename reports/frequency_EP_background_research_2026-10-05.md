# EP 后台期间源码研究与文档更正

当前只有EP的一次原生 timing-only在后台，未启动CPU构建或程序。主工作区及157个冻结输入、测试前报告hash均保持。未启动EQ测试。

## 请求保持来源更正

EO1原审查将当前MMIO请求保持归因到CPU可选skid级，这句话不准确。当前student_top `DCACHE_REQUEST_PIPELINE=0`，39项override无改写；backend显式LSQ `REQUEST_PIPELINE=1`。持续valid的store等待ready时，既有LSQ选择payload保持；store的selection_done在request_fire=0时为0，selection_input_fire不能覆盖仍live的selection。reset/恢复可按原规则撤销valid；MMIO上96位固定0。CPU额外skid只在参数1时存在。原审查/预测试报告保存原hash，使用这份补充纠正文字；EP RTL和测量行为不变。

## 条件备选 EQ：将事务分类移到原LSQ选择边沿之前

若EP的完成报告仍显示MMIO检测/请求mask资格是限制，再考虑EQ。新增一个与原110位选择payload同拍存储的分类位：`!pick_load && pick_addr==80000000 && pick_store_mask==f`。当前变111位仍7写叶、仅多1状态位，不加LSQ阶段/事务延迟。最后必须与原request_valid相与；原live/full generation/committed-store/flush/recovery/wait资格全部保留。CPU直接模式沿用该标志；可选CPU寄存模式将其与全部原packet一起捕获；串行backend用完整原predicate fallback。

二值代数理由：原退出条件是valid、store、地址80000000和输出line mask000f。valid0或load1均不能退出；地址80000000低offset=0，store mask左移后等于000f恰好要求原store_mask=f。因此可在已有LSQ选择边沿前计算分类，保留实时完整valid资格，而省去资格后store/mask门与32位地址比较。并不缓存权限，也不依赖“已退休tag永远live”等不正确假设。

该方案将比較移到更早的LSQ选择阶段，可能使早级更慢；EP已经分散MMIO负载后，也可能完全不需要此变化。仅实现为独立条件备选，不能据源码预测MHz或自动加入EP。69个复合时钟块文本保持，单语句word-bank载荷增加1位人工核对。没有HDL编译、仿真、STA/综合或形式测试。

## 开源资料支持的边界

[BOOM Physical Realization](https://docs.boom-core.org/en/latest/sections/physical-realization.html)说明关闭前端flow-through可缩短fetch到dispatch联系，寄存branch resolution以一拍误预测代价换周期，并强调组合乘法后补延迟寄存器仍需retiming；这里将“已有边沿前做分类”作为设计推断，不能用其1GHz数字预测课程ASAP7结果。

[BOOM LSU](https://docs.boom-core.org/en/latest/sections/load-store-unit.html)保留store地址/数据资格并在commit后顺序发出；其乐观load/冲突后重放需要完整记忆序恢复，本CPU没有理由只删冲突/ROB权限来缩短链。[Ibex LSU](https://ibex-core.readthedocs.io/en/latest/03_reference/load_store_unit.html)说明请求等待grant与返回数据/error必须对齐；用于核对握手设计原则，并未照搬其in-order流水级或假设协议相同。

当前预先保存EM、EH与新EQ均有明确采纳条件。先读取EP新最慢路径，再选有证据的源方案；不得重启正在运行的测量，也不得为这些备选单项测试。

- EQ候选：`F:\CPU2026Candidates\frequency_research_20261003\EQ_lsq_registered_mmio_classification`
- EQ manifest SHA256：`874ff8e9ef4ea386d6339d979dac1c50c7b039341bde93b994f8042169704f92`
- 源审查及更正：`F:\CPU2026Proofs\EQ_source_review_20261005\source_review.json`
- 原EP pretest SHA256：`7e1150fc84363720def8ed58021af2a360ff14760ac5911e507c9e7a40c196e4`
- 运行EP frozen SHA256：`2aaa5d09501f2d59dbdceb7a4d446c2312ba174dfb15f205f11457954e7a879c`

## 恢复位宽告警的既有展开接线证据

EP和EL1原综合日志都有recovery_saved_owner输入128→76、recovery_query_tree输入46→21告警。只读EL1映射，query第7–13位精确来自chosen_age低7位，第14–19位来自head视图，第20位来自preview视图，不能据告警字面推断head/preview被截掉。再只读正在运行EP已生成的elaborated.json：具体ROB参数slot6/count7，query signal_i恰为occupancy7+chosen_age低7+head6+preview1共21位；saved data_i恰为kill64+chosen_age低6+chosen_slot低6共76位。所有公共bit ID逐项一致。

此证据消除了“这两个字段包因告警而漏接”的具体怀疑，未重新调用Yosys或任何测试，不证明整个branch recovery/映射功能等价；原程序测试仍未运行。Dcache action包17位输入与16位接收字段的源码拼接中，多的一位是未使用高位padding，不是删除reset字段；暂不因告警盲改宽度。没有调整课程工具或冻结输入。

展开接线证据：`F:/CPU2026Proofs/EP_recovery_port_width_review_20261005.json`；映射查询input证据：`F:/CPU2026Proofs/EL1_recovery_cast_ports_20261005.json`。

## EP 测量完成，ER1 完整请求包选择已实现但未测

EP完成一次原生课程测量：361.071932MHz、2.76953125ns、总49,589.945634μm²含SRAM；相比EL1频率+35.2962%、面积-0.04655%，相对原面积+7.0833%。300MHz满足，略低于EF370.477569MHz。没有IPC/功能程序，不能宣布±10%IPC或Tier3完成。原始测量：`E:/Verilog_cpu/reports/frequency_EP_measurement_2026-10-05.md`。

五条新最慢路径都从LSQ addr_mem[7][3]经过老store/request资格和选择，到pick_payload_read.query_tree/行解码再到暂存输入。四门负载67/68、延迟0.3363/0.3228/0.3972/0.3042ns，合计1.3605ns。后两项的公共index别名也可能等于原choose决策，不是payload_reader独占；方案同时处理完整树节点的地址/年龄/slot等选择消费者。

ER1只改LSQ组合结构：每节点仍用原choose_left，slot/age/wrap/address/完整generation+ROBtag+storedata+mask/load/size/unsigned一同传递，当前108位、7个最多16位选择域。取消赢得slot后再查67位payload的串行读。二值树归纳证明每节点packet等于原read(该节点slot)，无候选时仍执行原invalid/invalid右分支；保持原默认槽，不额外指定row0。叶payload按原SLOT_WIDTH的slot赋值取数据，兼容显式slot宽度截断；单条目root直接是叶。

ER草稿与最终ER1保留，均未测；ER1相对EP仅LSQ组合逻辑变化，69个复合时钟块相同，零新增状态/LSQ周期，普通整数流水线10级，继承EP首次hit多一拍。当前主工作区及冻结157输入仍为实测EP。源审查：`F:/CPU2026Proofs/ER1_source_review_20261005/source_review.json`。面积/全局Fmax未知，不能用1.3605ns直接相减预测频率。

EQ与EM的限制不在新导出的最慢路径，继续分开。矩阵hazard寄存、乐观load重放、缩窗口/issue/PRF端口等仍有snapshot/失效/恢复和IPC成本；当前采用与原优先树严格对应的无新增边沿转置。完整ER1已经结束源审查；下一次必须冻结并先报告，再只测整体一次，不能单测节点或混入无证据备选。
