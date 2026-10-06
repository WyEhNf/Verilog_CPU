# A105原终态与A109完整频率源批次

A105原监督PID96096已不存在，唯一timing阶段返回0，原源码/manifest/config/工具/报告身份已核对。Fmax274.236743439MHz，最小周期3.646484375ns，含SRAM总面积36056.018078μm²（组合20513.301840、时序7598.804400、SRAM7943.911838）。面积超标56.018078μm²，频率不足；按原PPA门槛未构建CPU、未仿真、IPC未知、19正确性未跑。

相对A99，频率-13.565393MHz、面积+140.259600μm²；相对最新完整A94，频率-16.012690MHz、面积+257.045400μm²。不能把A94IPC1.115262692写成A105IPC，也不能把整个批次退化单独归因于某一改动。

五条最慢路径从同一原ROB occupancy bit3起始，到达3.586/3.573/3.553/3.543/3.536ns。最长：原count FF QN177.6ps、33.77fF，INV170.6ps→execution_recovery_tree.signal_i[13]0.3482ns→recovery_preview0.484ns→后端recovery域0.615ns→LSQ/source3 direct payload physbit4(data[72])1.808ns→RS物理唤醒tag域1.916ns→RS entry2 second operand selector2.053ns→lane1 issue select2.427ns→ALU subtract control2.631ns→FF3.586ns。最大门OAI21_225574_529ps、43.73fF、slew1.1ns；另OAI21_229718_192ps、NAND2_223845_185ps。实际最小周期需要缩短超过313.151042ps才能严格>300MHz。

旧A99恢复至分配的路径不在当前五条里，不能宣称全部消失。新路径穿过恢复/完成载荷/同周期RS唤醒+发射/ALU，频率必须处理整个跨阶段组合链。原设计JSON中的execution recovery packet位13按W5 age+W5 head+6count+apply解包是countbit3，追溯原INV/FF绑定真实count，未用相似名字猜寄存器。529ps内部driver没有head_choice标签；将它与未分组的最终73bit报告mux联系是结构推断，而非精确RTL映射证据。

在原A105进行时已经冻结A106和A107：A106以共享端点和环形slot比较替代原W-bit unsigned age减法再比较，保持2^W回绕和所有rawcount；A107从原已知稀疏分配plan预选完整LSQ slot/GEN载荷，只在原actualfire消费者使用，分开载荷与晚接受事件。这两个旧关键链方向没有新测试。

A108在原HEAD_LOAD_PACKET_ACTIVE分支把最后73bit head/saved整包选择拆成5个<=16bit选择叶，由原真实控制树传同一bool；所有packet bits逐bit保持。新profile关闭可选A105每行完整GEN比较，恢复原9bit selected currentvalid/fullGEN read，保留代码与所有语义。此结构成本退出当前profile，净面积效果尚未知，不重跑旧A105或单个因素。

A109把同一原occupancy_reg分给ceil(ROB_ENTRIES/4)个恢复比较域及独立lane/public/query域。原count width/unsigned类型/全状态值不变，原count reset/recovery/commit/allocation赋值逐字保持，不复制寄存器、不增加边沿；每个消费者换成等值wire。目标是减轻关键链起点348.2ps大负载，与A108处理中段529ps控制负载配合。A106/A107防止此前链再次成为主瓶颈。新增FF/SRAM/流水边沿全0。

评估其余方向：新增恢复/CDB/issue寄存边界会改变同周期唤醒及分支等待，A94 IPC余量只有约1.37%，当前没有周期代价可控的证据；扩窗口/预测器没有当前性能瓶颈依据且面积紧；缩GEN/减少ISA/取消恢复检查违背要求；源前比较RS唤醒可再去掉CDB-tag选择后比较，但需新源身份/仲裁优先接口和更多比较，在处理明确529ps/348ps负载前没有更直接的净收益证据。ALU算术分段已有9级架构，当前大部分延迟出现在算术之前。此批优先保留周期行为，不能保证映射结果，不能宣称未来架构思路已被穷尽。

本轮未新增HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建。A106-A109源、生成器、审阅全部冻结，A10941文件候选SHA2b31e8b8dea04efc2a8680bb38765e55a1d2724bb01f33c7492300eb2cc9e128；主E40源未采用。下一步先对话报告完整批次和不确定性，再唯一一次原生Windows课程PPA，只有>300MHz且含SRAM面积<=36000才构建一次CPU测六perf。三项实测达标后复用同CPU，集中19课程正确性+4既有冻结边界程序及参数/架构审阅，完成前不采用、不标目标完成。
