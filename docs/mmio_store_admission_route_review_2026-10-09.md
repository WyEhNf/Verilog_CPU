# 新鲜 RS 时序改动后的 MMIO STORE 准入因式分解

本审阅现已实现为默认关闭的 `MMIO_STORE_ADMISSION_ROUTE` 策略，新 CPU PPA／IPC 未测量。冻结版本 `8af905db` 测得 8973.514135 um² / 294.930876 MHz，因频率门失败，未构建 CPU／运行性能／冒烟测试，不替换正式配置。新最差路径从数据缓存保存 SRAM 查询控制出发，经 LSQ 响应查询、加载报告元数据选择、完成及 ROB 查询逻辑，进入 LSQ 可见选择及字节转发覆盖，再经请求所有者有效性 → MMIO 退出分发 → 总线读取生命周期。到达时间 3.331 ns，最低周期 3.390625 ns。所报告五条最长路径均有此共同源，取代此前最差新鲜 RS 分配／SUB 路径，因此禁用 HALT 审阅不再是下一时序优先项。

当前保存 MMIO 类别为 `SAVED_REQUEST_QUERY && any_present_store && !existing_selection_packet.load && existing_selection_packet.address==0x80000000 && existing_selection_packet.relative_mask==0xf`。`any_present_store` 在提供新鲜分配 LOAD 时抑制无效过期 STORE 类别。新鲜请求要求没有现存存储，且 selected_load=1。因此保存 MMIO 类别为真会排除新鲜 LOAD，并意味着旧选择包是 STORE。此类别包含准确既有地址／掩码谓词，不仅是地址前缀或操作码类别。

保存查询模式中，原所有者有效性为 `!flush && !recovery && (fresh_without_forward || (found && !wait && (!query_load || query_incomplete_forward)))`，既有 query_load 来自同一旧选择包。对保存 MMIO 类别，query_load=0、fresh_without_forward=0，所选源必为旧包，所以准确限定退出请求可化为 `!flush && !recovery && candidate_found && !candidate_wait && saved_mmio_class`。候选选择和 wait 已携带原事务所有权／存活检查。可从仅 STORE 的路由中消除 LOAD 转发覆盖，不改握手、状态边沿、标签宽度或加载转发行为。

一种可能默认关闭的策略是共享 LSQ／后端新增限定 MMIO valid 输出，按上述因式分解式计算。核心仅在保存 LSQ 查询／类别启用且 DCACHE_REQUEST_PIPELINE=0 时使用它。请求寄存器必须使用自己接收并保存的所有者，不得用上游 LSQ 类别控制其输出，因此首版策略应拒绝请求流水线。仿真所有周期（含过期无效包）比较该信号与 `dcache_req_valid && saved_mmio_class`，核心再与原准确有效／存储／地址／行掩码谓词比较。保留完整 ACK 捕获、普通缓存流量及 AXI 请求语义。不使用原始 MMIO 类别直接路由总线。

实现前检查 candidate_wait、旧／新鲜包所有权、选择存活、直接旁路保护及恢复行为。可小幅扩展既有保存路由配对样例，覆盖保持 STORE、过期 STORE 类别加新鲜 LOAD、完整／部分转发 LOAD 及行 generation 复用。这是后续有限样例，不要求整套正确性。仅组合独立论证过的时序／面积改动，静态检查一次，再完整 PPA 一次。CPU 性能仍须先通过两个 PPA 门，随后既满足 c2a09eaa 逐项周期参考，也满足 IPC >=0.6000。

未用 HALT 源保护和 MSHR 载荷清除审阅仍未实现。此冻结面积余量 26.485865 um²，因此新增控制复制必须实测，不预测该因式分解的映射面积。全部宽度保留同一参数化 CPU、共享后端和 LSQ。

## 实现与有限样例

共享 LSQ 现按上述准确表达式输出 `dcache_req_mmio_valid_o`，共享后端仅透传该线。核心在 `MMIO_STORE_ADMISSION_ROUTE=1` 时选择它，顶层公开同一参数、默认零。核心及候选运行器拒绝无保存查询／类别或存在 CPU 请求流水线时启用。既有通用请求所有者、普通 LOAD 请求、字节转发、完整标签／generation 字段、状态转换、ACK 寄存器和 AXI 主存桥不变。每个下游 MMIO 消费者使用与此前相同的最终限定路由。

保存查询模式下，每个非复位仿真边沿，LSQ 将新因式分解输出与 `dcache_req_valid_o && dcache_req_mmio_class_o` 比较，含无效过期包及恢复。核心既有始终启用的保存路由断言，将最终所选路由与原准确有效／存储／地址／行掩码表达式比较。类别仍含 `any_present_store`，从不是仅凭原始地址的路由。

检查确认 candidate_wait 是所选行既有 response_wait 位；流水化 LSQ 的 candidate_found 是 selection_live OR 直接选择旁路，非流水化时为原 pick-valid。selection_live 和原直接旁路中的完整 generation／存活／sent／complete／wait 检查保留。新鲜分配请求要求没有候选及现存 STORE，且必须为 LOAD。ready 撤销后，保持 STORE 票据保留原包。单独无效过期票据不能使 candidate_found 为真。

一组 BE2/LSQ4 有限配对样例通过，两 DUT 都使用保存查询和分阶段数据所有者，夹具分别消费通用 valid／类别路由和新因式分解输出。比较公共 valid/ready 派生握手、周期、有效完整请求／加载载荷及准确新旧 MMIO 谓词。覆盖既有定向新鲜／保持 LOAD、部分／完整转发、延迟存储数据、满行复用及过期响应、保持 MMIO STORE／ACK、队列排空后过期 STORE 接新鲜 LOAD，以及恢复保护。仅为测试满行复用使用 RELEASE_CREDITS=2，生产 Tier1 保持 RELEASE_CREDITS=0。不实例化 cpu_core 或 AXI 总线，不宣称整 CPU 证明。证据：`reports/Tier_shared_LSQ_mmio_admission_protocol_2026-10-09.json`。

候选 `configs/tier1_shared_mmio_admission.json` 仅在已测新鲜数据配置上增加此路由策略。HALT／源查询及 MSHR 清除审阅仍未实现。准确源码满足全部面积／频率／IPC 要求且无逐项性能回退之前，不替换正式配置。

db75467c 策略测量一次后被拒绝：9032.621455 um² / 244.858919 MHz，两项均回退。未构建 CPU／运行性能／冒烟测试。下一配置明确关闭此策略，针对新实测源／状态查询路径。最终证据：`reports/Tier1_shared_mmio_admission_2026-10-09.json`。
