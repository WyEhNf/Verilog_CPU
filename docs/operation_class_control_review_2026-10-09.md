# 同一 CPU 内的操作类别控制

## 组合改动的实测原因

21175e7b Tier3 冻结版本测得 35146.444778 um2 / 357.541899 MHz，未达到 500MHz。最差路径为 2.737ns：待处理 ROB 槽位经恢复资格、LOAD 队首选择／唤醒及 RS 发射，到达供分支捕获消费的执行结果寄存器。另一条 2.720ns 路径从 branch_pending 出发，经前端重定向／请求控制和读取仲裁，到达 bus.write_lifecycle_tree bit15（写分配）及写生命周期寄存器。准确最终具名寄存器位尚未独立映射。以下两项改动消除 RTL 操作类别的重新汇合，不豁免 STA 路径，也不宣称未测频率。

## ALU 目标类别比较

ALU_PRED_TARGET_CLASS_COMPARE 在共享 top/core/backend 中默认为零，在既有 ALU 中成为 PRED_TARGET_CLASS_COMPARE。操作码译码使条件分支、JAL 和 JALR 互斥。原 calc_branch_target 对条件分支／JAL 选择 PC+immediate，对 JALR 选择 (source1+immediate)&~1。因此，在 JALR 类别下，它准确等于后者，不依赖前者目标逻辑锥。

紧凑模式中，原预测不匹配仅被 JALR 消费，因此启用模式直接比较按页重建的预测与 JALR 地址。完整模式将条件分支／JAL 预测与 PC+immediate 比较，将 JALR 预测与清除最低位的地址比较，并按类别限定。原重定向谓词不使用非分支目标不匹配，故该值变零。实际寄存分支目标输出、taken 结果、重定向 PC、元数据、算术、包捕获、ready／背压、取消及完整身份保留原行为。默认零模式保留原不匹配表达式。启用仿真每个非复位边沿断言原始 calc_redirect_valid 等于完整原重定向表达式，包含无效／未消费操作；不替换查询或标签证书。

一组有限 ALU 比较 0/1 配对在 compact0/1 两模式下检查九点：相等／不跳转分支、完整目标不匹配、JAL、页内／奇目标／页外 JALR、非分支 AUIPC 和 PC 回绕算术。比较完整有效结果包、ready/valid 周期、预期重定向及保持结果背压／消费。使用原前缀算术，不启用 WORD_SIM。一测试点故意提供错误直接分支预测，以验证与原 ALU 的代数相等，不宣称其是合法紧凑前端预测或端到端 CPU 测试。前端既有紧凑目标契约和页外方向处理不变。

## AXI 类别局部接收

AXI_CLASS_LOCAL_ADMISSION 在 student_top 中默认为零，选择同一 rv32_axi_lite_bridge 的 CLASS_LOCAL_ADMISSION。原公共 d_req_ready 为 !reset && (write ? write_free_found : (read_free_found && (!i_req_valid || prefer_d_request)))。真实写入下代入 write=1，准确得到独立于读取仲裁的 d_write_capacity_ready；真实读取下代入 write=0，准确得到读取容量／仲裁项。

启用模式用这两个类别限定表达式计算 take_d_write 和 take_d_read。全部公共 ready/valid、指令接收、容量、行分配、载荷、队列／字握手、响应 FIFO、计数器／错误及请求／回复偏好保留原逻辑和边沿。不增加推测所有权、额外状态，不忽略过期包。每拍（含复位周期）断言真实类别接收等于原公共 valid/ready 公式。默认零模式保留原公式。

一组原有限生产几何 READ8/WRITE4/WORD16/FIFO2/SRAM-payload1 配对比较 class0/1，读取计数器所有权固定 1。保留 12 次行读、六次写、AW/W 独立前进、响应背压／错误、字／FIFO 回绕及行复用。另要求实际在指令 valid 存在时接收写入，并比较全部公共有效包／周期、读写有效性和有效行计数／错误状态。这不是全部配置或整 CPU 证明。

## 验收门

192 参数 Tier3 配置将这两个标志与此前行内算术／比较、私有分支捕获和读取计数器所有权策略组合。保持 FE4/BE2/INT2/CDB2、ROB32/PHYS56/RS8/LSQ16、原缓存和 AXI 资源、寄存分派及寄存器 PRF。两策略不增加流水线／触发器，不收窄标签，适用于全部发射宽度使用的同一参数化 CPU。一次提交冻结及原完整核心结构静态检查先于一次官方 PPA。面积 <=35891.672317998215、Fmax>=500 后才构建 CPU／测试性能；原指令数、IPC>=1.1152626918348099 和周期 <=7572/17490/143485/153155/4739/3725 后，才执行一次 array1 冒烟测试。历史已验收冻结版本全部保留，新 CPU PPA／IPC 及最终验收仍待证明。
