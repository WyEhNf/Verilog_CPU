# 静态哨兵类别与保存候选状态查询

## 实测动机与候选边界

db75467c MMIO STORE 准入路由候选以 9032.621455 um² / 244.858919 MHz 两门失败，已拒绝，未构建 CPU／运行性能／冒烟测试。最长路径为指令缓存 → 后端架构源 RS1 → RAT/PRF → 新鲜 LSQ 请求 → 候选状态查询 → 转发准入 → 保存选择载荷写入。RS1[4] 在 2.100 ns 到达，其中 NAND2 延迟 0.548 ns，后级反相器延迟 0.414 ns。源字段别名已在 mapped.v 核对。这是真实映射时序证据，不是预测收益。

新配置 `configs/tier1_shared_static_source_query.json` 从实测较好的 `8af905db` 新鲜数据配置（8973.514135 um² / 294.930876 MHz）派生，明确禁用失败的 MMIO_STORE_ADMISSION_ROUTE，同时保留既有保存类别路由。它增加同一共享 CPU／后端／LSQ 的两项默认关闭策略，不引入按宽度分离 CPU 或新流水边沿。目前不宣称新面积、频率或 IPC。

## 静态停机类别译码：DECODE_STATIC_HALT_CLASS

启用时，is_halt_trace 由参数 LEGACY_SENTINEL_HALT 限定。旧参数非零时，所有位及原 HALT 行为仍采用原操作码比较；为零时，源／操作码 HALT 选择器恒假。共享译码 RTL 仅在旧参数及准确哨兵字覆盖下赋予 HALT，其他合法／非法指令字不能产生 HALT。译码队列写入这些包，占用行／输入旁路有效性保留此不变量。无效过期队列数据的源／操作码选择可以不同，但 trace 有效性仍为必要条件，故不能产生分派。原队列 valid、接收及失效逻辑不变。

核心仿真断言：此策略启用且哨兵参数为零时，每个有效下游译码包都非 HALT。保留旧哨兵启用行为，禁用模式中哨兵字是普通 ADDI。不引入基准指令白名单，不收窄操作码／标签。详细不变量审阅见 `docs/disabled_halt_source_query_review_2026-10-09.md`。对该静态不变量，不需额外译码器／整 CPU 正确性扫描；结构静态检查及后续受门控 CPU 性能／冒烟测试使用生产断言。

## LSQ 保存候选状态查询：LSQ_SAVED_CANDIDATE_STATE_QUERY

启用时，既有 4 位候选状态读取器直接索引 existing_selection_packet 的槽位，而非 candidate_found ? visible selected_slot : 0，要求 LSQ_SAVED_REQUEST_QUERY。包仍是原保持／直接旧选择，保留完整原所有权／标签／GEN 检查，不改存储位。

candidate_found 为真时，新鲜分配请求为假：新鲜请求要求 !selection_valid 和 !pick_valid，而流水化 LSQ 的 candidate_found 是 selection_live OR selection_direct_bypass。因此可见选择等于旧包，新旧查询槽位／状态相同。非流水化 LSQ 不能提供新鲜请求，也有同一性质。candidate_found 为假时，metadata_forward 和受限定 MMIO STORE-valid 已为假。通用准入只有提供新鲜请求时才可能为真，而该分支已将 wait_i 覆盖为零。因此任意旧行查询数据无所有权，不能影响真实准入、转发、元数据写入或握手。已检查 candidate_wait/load/sent/complete 的全部使用。

仿真并行读取原查询，在每个非复位且 candidate_found 的边沿比较四字段。原完整选择 generation／存活检查、完整标签和转发数据／掩码保留。此改动从状态查询索引路径移除不必要的新鲜请求／可见包及 candidate_found 限定，不推测接收，不削弱身份检查。

一组 BE2/LSQ4 配对有限样例在策略 0/1 下通过，覆盖新鲜／保持请求、部分／完整转发、延迟存储数据、保持结果、满行加载出队／存储复用及过期响应、MMIO 保持／过期／新鲜加载类别及恢复保护。比较有效公共请求和完成包、握手、周期／占用及原查询断言。两 DUT 均使用保存查询／分阶段所有者及相同通用 valid 限定路由。RELEASE_CREDITS=2 仅为复用夹具，生产 Tier1 为 0。不实例化 cpu_core，不宣称测试了静态 HALT CPU 策略。证据：`reports/Tier_shared_LSQ_saved_state_protocol_2026-10-09.json`。

## 评估

冻结一次、原结构静态检查一次、完整官方 PPA 一次。面积 <=9000、频率 >=300 两门通过后，构建一次并运行六项官方性能程序。要求 IPC >=0.6000，且相对 c2a09eaa（12249/23982/231173/455096/7515/9007）周期不回退；全部验收门通过后执行 correctness_array_test1 一次。历史已验收 Tier2/Tier3 保留准确冻结版本，默认值不变，不由未验收候选替换正式配置。

## 最终结果

e776571f 完成一次完整官方 PPA，测得 9069.333895 um2 / 290.49645390070924 MHz，两门失败。相对 8af905db，面积 +95.819760 um2、频率 -4.434422 MHz。未构建 CPU／运行性能／冒烟测试，IPC 未测量，不替换已验收配置。新最差路径回到数据缓存元数据、LSQ 响应／完成、ROB 存活查询、LSQ 选择／转发准入、限定 MMIO 退出分发及总线读取生命周期。最低周期 3.4423828125 ns，最差到达时间 3.3826 ns。失败组合策略不作为新档位验收。
