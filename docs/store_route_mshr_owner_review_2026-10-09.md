# 保存 STORE 路由与 MSHR 数据所有者候选

e776571f 静态源／保存状态候选以 9069.333895 um2 / 290.496454 MHz 未通过 Tier1 两项 PPA 门，已拒绝，未构建 CPU／运行性能／冒烟测试。最长路径回到数据缓存响应／完成、ROB 查询、LSQ 选择／LOAD 转发覆盖、限定 MMIO 分发及总线读取生命周期寄存器。较好实测 8af905db 仍为候选参考：8973.514135 um2 / 294.930876 MHz，但其频率也未达门槛。

新 configs/tier1_shared_store_route_owner.json 从该较好新鲜数据配置开始，保持 DECODE_STATIC_HALT_CLASS=0，组合 LSQ_SAVED_CANDIDATE_STATE_QUERY=1 和 MMIO_STORE_ADMISSION_ROUTE=1。早期单独 STORE 路由试验失败，是因为新最差路径在等待状态查询前经过新鲜可见槽位／candidate-found 多路选择器；保存状态索引删除该依赖。两策略组合旨在从仅 STORE 的限定路由移除 LOAD 转发覆盖，同时避免早先晚到候选状态索引路径。测量组合之前不假定映射改善。

STORE 分类包含既有保存选择、STORE 类别、准确地址 80000000、相对掩码 f，以及真实存在的更老 STORE。新鲜 LOAD 请求要求无现存 STORE，并覆盖旧等待状态数据。通用请求完整转发覆盖只能抑制 LOAD，因此 candidate_found AND NOT candidate_wait AND saved_MMIO_class 等于原有效性限定 MMIO 路由。candidate_found 为真时，保存状态读取同一旧选中槽位。原完整 GEN／标签、选择存活、flush/recovery、准确 MMIO 载荷、ACK 及 AXI 边沿保留。既有生产断言将因式分解路由及候选状态与原查询比较。显式范围见此前两项策略审阅和有限 LSQ 样例；它们不证明此组合整 CPU。

DCACHE_MSHR_DATA_NO_CLEAR=1 仅抑制既有分组 MSHR 载荷所有者中无所有权数据的清除，以降低面积。每个 STORE 在合并或发布字节前取得完整初始化；复位／预取仍清除生命周期权限，抑制冲突低优先级写入。全部 128 数据位、掩码、被替换载荷、完整身份和边沿保留。消费者及冲突细节见 docs/mshr_unowned_clear_review_2026-10-09.md。有限 PREFETCH=1 缓存配对样例是此候选唯一新协议样例，不加入布尔恒等测试或广泛正确性套件。

全部宽度仍使用同一参数化 cpu_core/rv32_backend_joint/cache。正式配置和默认值不变。CPU 构建／性能测试前，候选须通过一次原结构静态检查及一次冻结官方 PPA。要求面积 <=9000、频率 >=300、IPC >=0.6000，且相对 c2a09eaa（12249/23982/231173/455096/7515/9007）无逐项周期回退；之后才执行一次 correctness_array_test1 冒烟测试。早期 Tier2/Tier3 指标不证明新源码，各冻结版本继续单独保留。

## 最终实测结果

366f4726 冻结版本完成一次官方 PPA：8960.946175 um2 / 284.2865074958356 MHz。面积通过，频率失败且相对 8af905db 回退，故未构建 CPU／运行性能／冒烟测试。最长路径现终止于字节转发后的分阶段 LOAD 结果捕获，而非限定 MMIO 分发。映射终点 _115579_/QN 为 _001611_，其反相器驱动 complete_value_mem[3][16]，别名已在 mapped.v 核对。最低周期 3.517578125 ns，到达时间 3.4696 ns。注意力因而转向两层嵌套结果／阶段载荷选择器；成功移除旧关键路由不等于整体频率改善。
