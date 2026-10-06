# A107：分配标签载荷先行，真实分配事件仍是唯一写入门槛

本轮以A106为父快照，再分离LSQ分配的预备完整身份与晚到接受事件。原A105继续单独测量；A106和A107均未启动测试，三项指标未知。当前原进程观察与冻结身份附于JSON记录，主E EU40源不变。

A99关键路径后段在实际分配票据valid处经过212ps NAND3和112ps INV，到d_rob_value_tree.signal_i[0]为2.982ns，再进入LSQ load状态写入链。这个别名是LSQ分配tag，不是ROB宽数据读取。A104已分布部分实际fire负载，但票据仍把晚fire编码进整个标签，又被独立实际write事件门控。

新私有alloc_payload_tag从既有planned sparse-lane slot和同一generation_next完整行调用原make_lsq_tag，先得到{fullGEN,slot,kind,valid1}。public alloc_lsq_tag/fire/count/ready原组合过程逐字保持；private载荷仅替换三个真实事件消费者：backend ROB-to-LSQ map、store RS link以及LSQ allocation-load selection。这三个消费者的原写入/选择条件均蕴含actual alloc_fire，未放宽资源/flush/recovery门槛。

原ALLOC_SLOT_PRESELECT契约是只要有任何真实fire，plan==fire。backend elastic d_admit以整个稀疏memory bundle需求<=当前free为门槛，因此admit时全部need同序fire，否则没有fire；plan=d_lsq_need，actualvalid=d_lsq_need&d_admit。对应实际lane的原slot与planned slot均为tail加之前fire/plan数量，回绕与截断相同；从相同GEN-next行使用原make函数得到逐bit相等的标签。不改变GEN0原组合行为，也不截断9位LSQGEN。空/未fire载荷可以不同，但原event_select遮罩或word_bank write门槛不观察它。

core/backend新flag默认0，course1；实际启用还要求原slot preselection的elastic+pipeline guard。LSQ自身flag与旧slotflag共同启用，否则private直接等于public旧tag。公开标签在flush期间的旧非零行为仍保持。LSQ所有payload行、metadata、回收、选择/响应/hold、GEN状态owners及helpers后缀逐字相同，原allocator过程也逐字相同；backend map/link事件及所有时序状态不改。

这种变换从载荷网络拿掉晚fire、稀疏槽位编码、GEN读取的串行依赖，真实接受只走原事件网络。活跃profile旧publictag的未使用查询可能被裁掉，但面积和频率以实际综合为准。新增FF/SRAM/流水边沿均0，现有窗口/ISA/OoO/顺序commit/MMIO/cache/预测规模保留。对BE1/2/4及旧LSQ合法power-of-two/entries1几何，实际fire始终受free_count限制，未分配的越界计划槽位不能制造事件。

目前A106提供恢复分类的算术链缩短，A107提供分配边界事件/载荷分离；两项为下一批源级方案，不借用A94或A105指标。暂不测试：等待A105原始终态与新路径再判断后续批次。新测试前先汇报；仅PPA>300MHz且含SRAM面积<=36000后测六perf，三项达标后复用同CPU集中19课程正确性+4既有冻结边界程序，并做参数/架构审阅。目标尚未完成，未采用。
