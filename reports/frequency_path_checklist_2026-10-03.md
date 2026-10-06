# 2026-10-03 综合后路径检查清单

检查对象：已采用的 8 级组合参数配置，整机 Fmax **53.439 MHz**、最小周期 **18.712891 ns**。本次仅分析冻结网表，未修改 RTL。

已检查 **37,523 个有约束且存在可达时序路径的终点**，每个终点保留最差 setup 路径；归并为 **368 类终点字段**，其中 **35,662 条**在 300 MHz 下 setup slack 为负。字段归类不表示独立根因，同一控制链可影响多个字段。

按数据到达时间降序排序。寄存器路径耗时包含 clk→Q、组合逻辑及库负载效应，不含终点 setup/时钟不确定度；接口路径包含所设输入延迟。300 MHz 的 3.333333 ns 还要留 setup、0.05 ns uncertainty 及接口输出延迟。清单按原 2 ns SDC 的 slack 平移 1.333333 ns；已核对代表路径为同一上升沿单周期时钟。

这是完整终点最差路径清单，不是枚举所有组合逻辑路径。无路径/常量终点不在清单中。使用原 ASAP7 TT 库、全部 SRAM 与层级、原约束及 reset=0；check_setup 通过。频率仍是综合后理想时钟估计，不是布局布线结果。

[打开可搜索完整清单](E:/Verilog_cpu/reports/frequency_path_checklist_2026-10-03.html) · [37,523 条原始数值与逐条建议](F:/CPU2026Proofs/frequency_combined_paths_20261003/all_paths_with_advice.json) · [368 类详细门延迟](F:/CPU2026Proofs/frequency_combined_paths_20261003/families_with_advice.json)

| 类别编号 | 代表路径（RTL 起点 → 终点） | 耗时/ns | 修改建议 |
|---:|---|---:|---|
| 1 | `lsq.head_o [0]` → `lsq.addr_mem[12] [29]` | 18.647 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 2 | `recovery_rs_branch_slot [5]` → `rs.src2_value_mem[8] [11]` | 18.392 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将 RS 每行操作数写源选择与 kill/valid 分离，局部处理 allocation/wakeup；保留恢复时存活指令的同拍唤醒。 |
| 3 | `recovery_rs_branch_slot [5]` → `rs.src1_value_mem[8] [9]` | 18.392 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将 RS 每行操作数写源选择与 kill/valid 分离，局部处理 allocation/wakeup；保留恢复时存活指令的同拍唤醒。 |
| 4 | `lsq.head_o [0]` → `lsq.mask_mem[12] [2]` | 18.072 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 5 | `lsq.head_o [0]` → `lsq.addr_ready_mem[12]` | 18.027 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 6 | `recovery_rs_branch_slot [5]` → `rs.pc_mem[4] [12]` | 17.652 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 19 | `recovery_rs_branch_slot [5]` → `frontend.count_storage_reg [3]` | 17.500 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 31 | `recovery_rs_branch_slot [5]` → `decode.count [1]` | 17.410 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。 |
| 32 | `recovery_rs_branch_slot [5]` → `decode.g_slot[3].g_field[0].bank/data_o [0]` | 17.375 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。 |
| 38 | `recovery_rs_branch_slot [5]` → `lsq_phys_mem[2] [4]` | 16.875 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 40 | `recovery_rs_branch_slot [5]` → `rob.store_sent_mem[13]` | 16.377 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 45 | `icache.if_resp_pc_o [4]` → `icache.if_resp_error_o` | 16.112 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 48 | `icache.if_resp_pc_o [4]` → `icache.resp_data_reg [0]` | 15.873 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 65 | `recovery_rs_branch_slot [5]` → `prf.ready [45]` | 15.141 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将 ready 位和数据写端口分开，按物理寄存器行译码 allocate/writeback/reclaim，减少全局恢复信号直接负载。 |
| 66 | `recovery_rs_branch_slot [5]` → `rename.free_bitmap_state_o [41]` | 15.138 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 free bitmap/RAT 做分组恢复及并行计数，隔离恢复选择与正常重命名写使能，保留同拍回收/分配优先级。 |
| 82 | `lsq.head_o [0]` → `g_issue_pipeline[2].g_registered.pipe.data_o [112]` | 14.457 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 95 | `icache.if_resp_pc_o [4]` → `icache.data_array.lane_0/ce_in` | 14.100 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；分别局部生成 SRAM CE/WE/地址，区分 hit 与 refill；必要时寄存完整 SRAM 命令，但不能只延迟地址而错开控制。 |
| 103 | `icache.if_resp_pc_o [4]` → `icache.data_array.lane_0/addr_in[0]` | 13.429 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；分别局部生成 SRAM CE/WE/地址，区分 hit 与 refill；必要时寄存完整 SRAM 命令，但不能只延迟地址而错开控制。 |
| 104 | `recovery_rs_branch_slot [5]` → `core.instret [30]` | 13.389 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；用局部并行退休计数驱动窄增量加法，先修共享提交/恢复控制；退休计数仍须精确。 |
| 108 | `lsq.head_o [0]` → `predictor.g_bank[2].predictor.bht[31] [0]` | 12.988 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 124 | `lsq.head_o [0]` → `mdu.gen_divider.divider.resp_value_o [0]` | 11.154 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 150 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.genblk4.g_banked_updates.g_metadata[6].state_bank/dirty_o [8]` | 10.663 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 194 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[0].g_local_commands.g_word[0].port_bank/storage.lane_0/ce_in` | 9.284 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 278 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_0/addr_in[4]` | 5.660 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 311 | `mdu.gen_divider.divider.divisor_reg [0]` → `mdu.gen_divider.divider.unsigned_cache_q_reg [31]` | 3.476 | 缩短除法商/余数结果选择和符号修正逻辑；可把修正与缓存写入分开一拍，但需评估 DIV/REM 延迟对 IPC 的影响。 |
| 333 | `$\bus.write_addr$rdreg[0]$q [0]` → `wstrb[0]` | 2.769 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |

实测共享瓶颈：

- LSQ 最慢路径：`_477118_/Y` 的 NOR5 门约 4.890 ns，输出负载 253.4 fF、模块内接收引脚 599；另一门 `_380941_/Y` 约 2.471 ns。应先局部化真实行状态和写控制。
- 恢复路径：`_333051_/Y` 对应 `frontend.redirect_valid_i`，约 3.106 ns；`_361420_/Y` 对应译码缓冲 `flush_i`，约 5.118 ns、410.7 fF。恢复信号经过前端/译码后仍影响 RS，不能仅在 ALU 数据路径加级。
- Icache 路径已映射出 `frontend.if_req_pc_o` → `request_match_found` → `frontend.req_fire`，对应 RTL 的 `response_can_chain` 同周期再发请求。直接禁用该机制可能损失 IPC。
- Dcache 路径已映射出 `refill_array_write` → `static_request_action` → 元数据 bank，中央动作编码的一个门约 3.930 ns；局部元数据门另占约 2.949 ns。

建议先做 LSQ 行写控制、恢复信号局部分发，再处理前端/Icache 同周期链与 Dcache 动作分发。普通整数流水线已有 8 级，但这些跨级 ready/flush 控制仍可形成长路径。所有建议是待验证的修改方向，没有预先承诺频率收益。

固定基准保持不变：面积 46789.856634 µm²、IPC 1.1182750169703988。当前面积 46298.423154 µm²（−1.0503%）、IPC 1.0087820702582486（−9.7912%）；IPC 下限 1.0064475152733589，仅余约 0.2314% 相对下降空间。优先不增加周期的局部重构；新增阶段须复测面积和 IPC。

完整逐类降序清单：

| 类别 | 路径 | 耗时/ns | 终点数 | 修改建议 |
|---:|---|---:|---:|---|
| 1 | `lsq.head_o [0]` → `lsq.addr_mem[12] [29]` | 18.647 | 512 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 2 | `recovery_rs_branch_slot [5]` → `rs.src2_value_mem[8] [11]` | 18.392 | 384 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将 RS 每行操作数写源选择与 kill/valid 分离，局部处理 allocation/wakeup；保留恢复时存活指令的同拍唤醒。 |
| 3 | `recovery_rs_branch_slot [5]` → `rs.src1_value_mem[8] [9]` | 18.392 | 384 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将 RS 每行操作数写源选择与 kill/valid 分离，局部处理 allocation/wakeup；保留恢复时存活指令的同拍唤醒。 |
| 4 | `lsq.head_o [0]` → `lsq.mask_mem[12] [2]` | 18.072 | 48 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 5 | `lsq.head_o [0]` → `lsq.addr_ready_mem[12]` | 18.027 | 16 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 6 | `recovery_rs_branch_slot [5]` → `rs.pc_mem[4] [12]` | 17.652 | 384 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 7 | `recovery_rs_branch_slot [5]` → `rs.entry_metadata_o [285]` | 17.652 | 804 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 8 | `recovery_rs_branch_slot [5]` → `rs.op_mem[4] [4]` | 17.646 | 72 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 9 | `recovery_rs_branch_slot [5]` → `rs.entry_rob_tag_o [11]` | 17.627 | 180 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 10 | `recovery_rs_branch_slot [5]` → `rs.src1_tag_mem[0] [3]` | 17.617 | 180 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 11 | `recovery_rs_branch_slot [5]` → `rs.phys_rd_mem[0] [2]` | 17.616 | 72 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 12 | `recovery_rs_branch_slot [5]` → `rs.age_mem[0] [2]` | 17.607 | 96 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 13 | `recovery_rs_branch_slot [5]` → `rs.src1_ready_mem[0]` | 17.607 | 12 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 14 | `recovery_rs_branch_slot [5]` → `rs.src2_ready_mem[0]` | 17.598 | 12 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 15 | `recovery_rs_branch_slot [5]` → `rs.src2_tag_mem[4] [8]` | 17.555 | 180 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 16 | `recovery_rs_branch_slot [5]` → `lsq.rob_tag_mem[10] [16]` | 17.520 | 240 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 17 | `recovery_rs_branch_slot [5]` → `rs.valid_mem[8]` | 17.508 | 12 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 18 | `recovery_rs_branch_slot [5]` → `lsq.size_mem[10] [0]` | 17.501 | 32 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 19 | `recovery_rs_branch_slot [5]` → `frontend.count_storage_reg [3]` | 17.500 | 5 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 20 | `recovery_rs_branch_slot [5]` → `lsq.store_mem[10]` | 17.498 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 21 | `recovery_rs_branch_slot [5]` → `lsq.valid_mem[10]` | 17.488 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 22 | `recovery_rs_branch_slot [5]` → `lsq.forward_mask_mem[10] [0]` | 17.463 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；把 LSQ 地址、掩码、ready 状态改为每行独立写端口，静态译码分配/early-AGU/执行更新，并保持原同拍写优先级和 generation 校验。 |
| 23 | `recovery_rs_branch_slot [5]` → `lsq.forward_data_mem[10] [0]` | 17.463 | 512 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将前递/完成数据与有效位分开存储，逐行选择写源，避免全队列广播清零和宽数据写使能。 |
| 24 | `recovery_rs_branch_slot [5]` → `lsq.complete_value_mem[10] [10]` | 17.463 | 512 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将前递/完成数据与有效位分开存储，逐行选择写源，避免全队列广播清零和宽数据写使能。 |
| 25 | `recovery_rs_branch_slot [5]` → `lsq.unsigned_mem[10]` | 17.461 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 26 | `recovery_rs_branch_slot [5]` → `lsq.complete_error_mem[10]` | 17.456 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 27 | `recovery_rs_branch_slot [5]` → `lsq.data_mem[10] [30]` | 17.442 | 512 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 28 | `recovery_rs_branch_slot [5]` → `lsq.store_ack_error_mem[10]` | 17.436 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 29 | `recovery_rs_branch_slot [5]` → `lsq.retired_mem[10]` | 17.436 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 30 | `recovery_rs_branch_slot [5]` → `frontend.head_reg [3]` | 17.422 | 4 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 31 | `recovery_rs_branch_slot [5]` → `decode.count [1]` | 17.410 | 3 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。 |
| 32 | `recovery_rs_branch_slot [5]` → `decode.g_slot[3].g_field[0].bank/data_o [0]` | 17.375 | 768 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。 |
| 33 | `recovery_rs_branch_slot [5]` → `decode.tail [1]` | 17.362 | 2 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。 |
| 34 | `recovery_rs_branch_slot [5]` → `lsq.generation_mem[9] [3]` | 16.973 | 160 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 35 | `recovery_rs_branch_slot [5]` → `rs.target_live_mem[6]` | 16.951 | 12 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 36 | `recovery_rs_branch_slot [5]` → `lsq.generation_next_mem[9] [0]` | 16.936 | 160 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 37 | `recovery_rs_branch_slot [5]` → `lsq.load_mem[11]` | 16.904 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 38 | `recovery_rs_branch_slot [5]` → `lsq_phys_mem[2] [4]` | 16.875 | 96 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 39 | `recovery_rs_branch_slot [5]` → `lsq.data_ready_mem[10]` | 16.750 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 40 | `recovery_rs_branch_slot [5]` → `rob.store_sent_mem[13]` | 16.377 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 41 | `recovery_rs_branch_slot [5]` → `rob_to_lsq_mem[31] [10]` | 16.294 | 960 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 42 | `recovery_rs_branch_slot [5]` → `rob.ready_mem[37]` | 16.204 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 43 | `recovery_rs_branch_slot [5]` → `rob.valid_mem[3]` | 16.200 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 44 | `recovery_rs_branch_slot [5]` → `rob.store_wait_mem[3]` | 16.200 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 45 | `icache.if_resp_pc_o [4]` → `icache.if_resp_error_o` | 16.112 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 46 | `icache.if_resp_pc_o [4]` → `icache.if_resp_line_addr_o [0]` | 16.112 | 32 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 47 | `icache.if_resp_pc_o [4]` → `icache.if_resp_pc_o [25]` | 15.919 | 32 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 48 | `icache.if_resp_pc_o [4]` → `icache.resp_data_reg [0]` | 15.873 | 128 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 49 | `icache.if_resp_pc_o [4]` → `icache.resp_valid_reg` | 15.702 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 50 | `recovery_rs_branch_slot [5]` → `lsq.store_commit_mem[2]` | 15.457 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 51 | `recovery_rs_branch_slot [5]` → `lsq.complete_mem[10]` | 15.449 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 52 | `recovery_rs_branch_slot [5]` → `lsq.load_reported_mem[10]` | 15.448 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 53 | `recovery_rs_branch_slot [5]` → `lsq.request_sent_mem[10]` | 15.445 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 54 | `recovery_rs_branch_slot [5]` → `lsq.response_wait_mem[8]` | 15.422 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 55 | `recovery_rs_branch_slot [5]` → `lsq.store_ack_mem[8]` | 15.414 | 16 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 56 | `recovery_rs_branch_slot [5]` → `rob.generation_next_mem[47] [4]` | 15.290 | 512 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 57 | `recovery_rs_branch_slot [5]` → `rob.entry_generation_o [120]` | 15.241 | 512 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 58 | `recovery_rs_branch_slot [5]` → `rob.error_mem[47]` | 15.226 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 59 | `recovery_rs_branch_slot [5]` → `phys_tag_mem[45] [5]` | 15.216 | 960 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 60 | `recovery_rs_branch_slot [5]` → `rob.store_mem[15]` | 15.210 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 61 | `recovery_rs_branch_slot [5]` → `rob.entry_rd_o [75]` | 15.210 | 320 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 62 | `recovery_rs_branch_slot [5]` → `rob.entry_rd_we_o [15]` | 15.210 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 63 | `recovery_rs_branch_slot [5]` → `rob.entry_old_phys_o [90]` | 15.210 | 384 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 64 | `recovery_rs_branch_slot [5]` → `rob.entry_new_phys_o [90]` | 15.210 | 384 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 65 | `recovery_rs_branch_slot [5]` → `prf.ready [45]` | 15.141 | 63 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；将 ready 位和数据写端口分开，按物理寄存器行译码 allocate/writeback/reclaim，减少全局恢复信号直接负载。 |
| 66 | `recovery_rs_branch_slot [5]` → `rename.free_bitmap_state_o [41]` | 15.138 | 63 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 free bitmap/RAT 做分组恢复及并行计数，隔离恢复选择与正常重命名写使能，保留同拍回收/分配优先级。 |
| 67 | `recovery_rs_branch_slot [5]` → `rob.tail_o [5]` | 15.115 | 6 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 68 | `recovery_rs_branch_slot [5]` → `rob.halt_mem[7]` | 15.083 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 69 | `recovery_rs_branch_slot [5]` → `rob_mem_size_mem[44] [1]` | 15.003 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 70 | `recovery_rs_branch_slot [5]` → `load_error_mem[44]` | 14.997 | 64 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 71 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[3].g_owned.state_bank/demand_epoch_o [0]` | 14.956 | 32 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 72 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[3].g_owned.state_bank/pc_o [0]` | 14.951 | 256 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 73 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[0].g_owned.state_bank/prefetch_o` | 14.906 | 8 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 74 | `recovery_rs_branch_slot [5]` → `rs.age_counter [7]` | 14.875 | 8 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 75 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[3].g_owned.state_bank/line_o [27]` | 14.873 | 256 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 76 | `recovery_rs_branch_slot [5]` → `lsq.tail_o [3]` | 14.824 | 4 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；采用窄位宽入队/出队计数与并行 pop 判断，保持循环队列占用和回收语义。 |
| 77 | `recovery_rs_branch_slot [5]` → `lsq.occupancy_o [4]` | 14.815 | 5 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；采用窄位宽入队/出队计数与并行 pop 判断，保持循环队列占用和回收语义。 |
| 78 | `recovery_rs_branch_slot [5]` → `decode.head [1]` | 14.813 | 2 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；在已有环形译码缓冲上局部生成行写/头尾计数使能，缩短 recovery→ready→consume 链；如增加 credit/skid 缓冲，保持每拍接收能力。 |
| 79 | `recovery_rs_branch_slot [5]` → `rs.occupancy_o [2]` | 14.805 | 4 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 RS 行状态/元数据采用本地写使能，复用已有静态分配译码；只在语义需要时清有效位，避免 kill 广播控制全部宽字段。 |
| 80 | `recovery_rs_branch_slot [5]` → `rename.rat[4] [3]` | 14.761 | 186 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 free bitmap/RAT 做分组恢复及并行计数，隔离恢复选择与正常重命名写使能，保留同拍回收/分配优先级。 |
| 81 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[3].g_owned.state_bank/txn_epoch_o [0]` | 14.588 | 32 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 82 | `lsq.head_o [0]` → `g_issue_pipeline[2].g_registered.pipe.data_o [112]` | 14.457 | 736 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 83 | `recovery_rs_branch_slot [5]` → `rename.free_count_o [5]` | 14.452 | 7 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对 free bitmap/RAT 做分组恢复及并行计数，隔离恢复选择与正常重命名写使能，保留同拍回收/分配优先级。 |
| 84 | `icache.if_resp_pc_o [4]` → `icache.tag_mem[124] [0]` | 14.447 | 2816 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 85 | `lsq.head_o [0]` → `g_issue_pipeline[2].g_registered.pipe.occupied` | 14.432 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 86 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[3].g_owned.state_bank/sent_o` | 14.425 | 8 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 87 | `icache.if_resp_pc_o [4]` → `icache.lru_mem[14]` | 14.398 | 64 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 88 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[0].g_owned.state_bank/valid_o` | 14.250 | 8 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 89 | `icache.if_resp_pc_o [4]` → `icache.g_static_mshr.g_row[3].g_owned.state_bank/control_prefetch_o` | 14.244 | 8 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；已有 MSHR 行状态存储继续保留，把 request_fire/匹配/提升条件在各行局部解码，缩短中央仲裁到字段更新的路径。 |
| 90 | `icache.if_resp_pc_o [4]` → `icache.prefetch_tag [21]` | 14.210 | 22 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 91 | `lsq.head_o [0]` → `g_issue_pipeline[0].g_registered.pipe.saved_tag [0]` | 14.148 | 24 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 92 | `icache.if_resp_pc_o [4]` → `icache.prefetch_remaining [15]` | 14.131 | 32 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 93 | `icache.if_resp_pc_o [4]` → `icache.prefetch_next_line [0]` | 14.127 | 4 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 94 | `icache.if_resp_pc_o [4]` → `icache.if_resp_epoch_o [0]` | 14.108 | 4 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 95 | `icache.if_resp_pc_o [4]` → `icache.data_array.lane_0/ce_in` | 14.100 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；分别局部生成 SRAM CE/WE/地址，区分 hit 与 refill；必要时寄存完整 SRAM 命令，但不能只延迟地址而错开控制。 |
| 96 | `icache.if_resp_pc_o [4]` → `icache.valid_bits [65]` | 13.922 | 128 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 97 | `icache.if_resp_pc_o [4]` → `icache.prefetch_set [2]` | 13.884 | 6 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 98 | `icache.if_resp_pc_o [4]` → `icache.resp_from_sram` | 13.875 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 99 | `icache.if_resp_pc_o [4]` → `icache.prefetch_epoch [0]` | 13.861 | 4 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 100 | `icache.if_resp_pc_o [4]` → `icache.prefetch_active` | 13.829 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 101 | `recovery_rs_branch_slot [5]` → `rob.occupancy_o [5]` | 13.809 | 7 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 102 | `icache.if_resp_pc_o [4]` → `icache.prefetch_control_stream` | 13.683 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 103 | `icache.if_resp_pc_o [4]` → `icache.data_array.lane_0/addr_in[0]` | 13.429 | 7 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；分别局部生成 SRAM CE/WE/地址，区分 hit 与 refill；必要时寄存完整 SRAM 命令，但不能只延迟地址而错开控制。 |
| 104 | `recovery_rs_branch_slot [5]` → `core.instret [30]` | 13.389 | 32 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；用局部并行退休计数驱动窄增量加法，先修共享提交/恢复控制；退休计数仍须精确。 |
| 105 | `icache.if_resp_pc_o [4]` → `icache.last_demand_line [20]` | 13.346 | 28 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 106 | `icache.if_resp_pc_o [4]` → `frontend.req_pending_reg` | 13.101 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 107 | `icache.if_resp_pc_o [4]` → `icache.last_demand_valid` | 13.101 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；拆开响应槽可用、MSHR 匹配和响应字段写使能；优先同周期逻辑重构，插拍方案需验证不会引入逐行取指气泡。 |
| 108 | `lsq.head_o [0]` → `predictor.g_bank[2].predictor.bht[31] [0]` | 12.988 | 512 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 109 | `recovery_rs_branch_slot [5]` → `rob.head_o [5]` | 12.759 | 6 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 110 | `icache.if_resp_pc_o [4]` → `frontend.g_payload_row[0].g_banks.packet_bank/data_o [5]` | 12.560 | 1920 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 111 | `recovery_rs_branch_slot [5]` → `rob.error_o` | 12.499 | 1 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 112 | `recovery_rs_branch_slot [5]` → `rob.halted_o` | 12.499 | 1 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 113 | `recovery_rs_branch_slot [5]` → `perf_branch_pending_o` | 12.308 | 1 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 114 | `lsq.head_o [0]` → `g_alu[1].alu.exec_is_memory_o` | 12.024 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 115 | `lsq.head_o [0]` → `g_alu[1].alu.exec_mem_addr_o [0]` | 12.020 | 128 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 116 | `lsq.head_o [0]` → `predictor.g_bank[3].predictor.btb_tag[15] [23]` | 12.012 | 1536 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 117 | `lsq.head_o [0]` → `predictor.g_bank[3].predictor.btb_target[15] [31]` | 12.012 | 2048 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 118 | `lsq.head_o [0]` → `g_alu[1].alu.exec_is_load_o` | 11.749 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 119 | `lsq.head_o [0]` → `g_alu[1].alu.exec_is_store_o` | 11.671 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 120 | `lsq.head_o [0]` → `g_alu[1].alu.exec_store_data_o [13]` | 11.670 | 128 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 121 | `lsq.head_o [0]` → `predictor.g_bank[1].predictor.bht_trained[53]` | 11.422 | 256 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 122 | `lsq.head_o [0]` → `predictor.g_bank[2].predictor.btb_valid[5]` | 11.388 | 64 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 123 | `lsq.head_o [0]` → `predictor.g_bank[3].predictor.btb_kind[5] [0]` | 11.388 | 128 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 124 | `lsq.head_o [0]` → `mdu.gen_divider.divider.resp_value_o [0]` | 11.154 | 32 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 125 | `lsq.head_o [0]` → `mdu.gen_divider.divider.result_valid_reg` | 11.120 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 126 | `lsq.head_o [0]` → `g_alu[1].alu.exec_value_o [2]` | 11.116 | 128 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 127 | `lsq.head_o [0]` → `g_alu[1].alu.exec_rob_tag_o [5]` | 11.105 | 60 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 128 | `lsq.head_o [0]` → `$\rob_to_lsq_mem$rdreg[2]$q [2]` | 11.105 | 24 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；对该后端字段采用按槽位静态写译码，分开分配、完成和恢复选择，减少共享控制驱动的宽多路选择。 |
| 129 | `lsq.head_o [0]` → `g_alu[1].alu.exec_redirect_pc_o [21]` | 11.085 | 128 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 130 | `lsq.head_o [0]` → `g_alu[1].alu.exec_redirect_valid_o` | 11.068 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 131 | `lsq.head_o [0]` → `g_alu[2].alu.exec_rd_we_o` | 11.032 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 132 | `lsq.head_o [0]` → `g_alu[1].alu.exec_branch_target_o [13]` | 11.015 | 124 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 133 | `lsq.head_o [0]` → `g_alu[1].alu.exec_source_pc_o [5]` | 11.005 | 120 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 134 | `lsq.head_o [0]` → `g_alu[1].alu.exec_pred_kind_o [1]` | 11.005 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 135 | `lsq.head_o [0]` → `g_alu[1].alu.exec_phys_rd_o [3]` | 11.005 | 24 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 136 | `lsq.head_o [0]` → `mdu.gen_divider.divider.dividend_reg [15]` | 11.000 | 30 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 137 | `lsq.head_o [0]` → `mdu.pending_op [2]` | 10.979 | 6 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 138 | `lsq.head_o [0]` → `mdu.pending_src1 [0]` | 10.979 | 32 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 139 | `lsq.head_o [0]` → `mdu.pending_src2 [0]` | 10.979 | 32 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 140 | `lsq.head_o [0]` → `g_alu[0].alu.result_valid_reg` | 10.973 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 141 | `lsq.head_o [0]` → `mdu.pending_tag [0]` | 10.970 | 15 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 142 | `lsq.head_o [0]` → `g_alu[1].alu.exec_is_branch_o` | 10.969 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 143 | `lsq.head_o [0]` → `g_alu[0].alu.exec_branch_taken_o` | 10.915 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 144 | `lsq.head_o [0]` → `mdu.gen_divider.divider.remainder_shift [0]` | 10.908 | 33 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 145 | `lsq.head_o [0]` → `mdu.gen_divider.divider.quotient_reg [0]` | 10.894 | 31 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 146 | `lsq.head_o [0]` → `mdu.gen_divider.divider.remainder_shift_second [0]` | 10.894 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 147 | `lsq.head_o [0]` → `mdu.gen_divider.divider.step_reg [3]` | 10.884 | 6 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 148 | `lsq.head_o [0]` → `mdu.gen_divider.divider.busy_reg` | 10.837 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 149 | `lsq.head_o [0]` → `mdu.pending_phys [0]` | 10.672 | 6 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 150 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.genblk4.g_banked_updates.g_metadata[6].state_bank/dirty_o [8]` | 10.663 | 1024 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 151 | `lsq.head_o [0]` → `mdu.pending_live` | 10.646 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 152 | `lsq.head_o [0]` → `prf.value[8] [31]` | 10.630 | 2016 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；将 ready 位和数据写端口分开，按物理寄存器行译码 allocate/writeback/reclaim，减少全局恢复信号直接负载。 |
| 153 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.genblk4.g_banked_updates.g_metadata[6].state_bank/valid_o [15]` | 10.612 | 1024 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 154 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.genblk4.g_banked_updates.g_metadata[6].state_bank/lru_o [6]` | 10.606 | 512 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 155 | `lsq.head_o [0]` → `mdu.gen_divider.divider.sign_a_reg` | 10.434 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 156 | `lsq.head_o [0]` → `mdu.gen_divider.divider.result_live_reg` | 10.389 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 157 | `lsq.head_o [0]` → `mdu.gen_divider.divider.resp_rob_tag_o [0]` | 10.388 | 15 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 158 | `lsq.head_o [0]` → `mdu.gen_divider.divider.original_a_reg [0]` | 10.388 | 32 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 159 | `lsq.head_o [0]` → `mdu.gen_divider.divider.divisor_reg [0]` | 10.388 | 32 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 160 | `lsq.head_o [0]` → `mdu.gen_divider.divider.divide_zero_reg` | 10.388 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 161 | `lsq.head_o [0]` → `mdu.gen_divider.divider.sign_b_reg` | 10.382 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 162 | `lsq.head_o [0]` → `mdu.gen_divider.divider.original_b_reg [31]` | 10.376 | 31 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 163 | `lsq.head_o [0]` → `mdu.gen_divider.divider.want_remainder_reg` | 10.357 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 164 | `lsq.head_o [0]` → `mdu.gen_divider.divider.signed_overflow_reg` | 10.341 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 165 | `lsq.head_o [0]` → `mdu.gen_divider.divider.resp_phys_rd_o [0]` | 10.338 | 6 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 166 | `lsq.head_o [0]` → `rob.mmio_word_mem[59]` | 10.273 | 64 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 167 | `lsq.head_o [0]` → `$\lsq.complete_mem$rdreg[18]$q [1]` | 10.062 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；逐行生成分配、恢复、退休及响应更新条件，将该字段的写优先级局部化；不能提前释放未完成的 store。 |
| 168 | `lsq.head_o [0]` → `lsq.head_o [1]` | 10.062 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；采用窄位宽入队/出队计数与并行 pop 判断，保持循环队列占用和回收语义。 |
| 169 | `icache.if_resp_pc_o [4]` → `core.ras_stack[3] [6]` | 10.023 | 128 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 170 | `lsq.head_o [0]` → `mdu.pending_valid` | 9.998 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 171 | `lsq.head_o [0]` → `mdu.gen_divider.divider.signed_mode_reg` | 9.976 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 172 | `icache.if_resp_pc_o [4]` → `icache.data_array.lane_0/we_in` | 9.911 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；分别局部生成 SRAM CE/WE/地址，区分 hit 与 refill；必要时寄存完整 SRAM 命令，但不能只延迟地址而错开控制。 |
| 173 | `icache.if_resp_pc_o [4]` → `frontend.pc_reg [31]` | 9.786 | 32 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 174 | `icache.if_resp_pc_o [4]` → `bus.g_response_fifos.instruction.count [0]` | 9.765 | 2 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 175 | `icache.if_resp_pc_o [4]` → `core.ras_count [0]` | 9.736 | 3 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 176 | `icache.if_resp_pc_o [4]` → `$\bus.g_response_fifos.instruction.packets$rdreg[0]$q` | 9.702 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 177 | `icache.if_resp_pc_o [4]` → `bus.g_response_fifos.instruction.head` | 9.702 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 178 | `lsq.head_o [0]` → `mdu.gen_wallace_multiplier.multiplier.out_live` | 9.694 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 179 | `lsq.head_o [0]` → `mdu.gen_wallace_multiplier.multiplier.resp_rob_tag_o [0]` | 9.693 | 15 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 180 | `lsq.head_o [0]` → `mdu.gen_wallace_multiplier.multiplier.resp_phys_rd_o [0]` | 9.693 | 6 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 181 | `lsq.head_o [0]` → `mdu.gen_wallace_multiplier.multiplier.out_op [0]` | 9.693 | 6 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 182 | `icache.if_resp_pc_o [4]` → `core.ras_sp [1]` | 9.691 | 2 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；按预测器 bank/索引静态译码训练写使能，将恢复与普通训练分离；RAS 使用本地 push/pop/恢复优先级。 |
| 183 | `lsq.head_o [0]` → `mdu.gen_wallace_multiplier.multiplier.out_product [46]` | 9.690 | 64 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 184 | `lsq.head_o [0]` → `mdu.gen_wallace_multiplier.multiplier.out_valid` | 9.668 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；优先隔离完成队列反压到 MDU 结果保持/输入接收的控制链；仅当算术本体成为最慢段时再增加乘除流水级。 |
| 185 | `icache.if_resp_pc_o [4]` → `frontend.tail_reg [3]` | 9.655 | 4 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 186 | `icache.if_resp_pc_o [4]` → `core.g_cached_memory.memory_bridge.i_local_error` | 9.600 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 187 | `bus.g_response_fifos.data.count [1]` → `bus.g_response_fifos.instruction.packets[0] [168]` | 9.543 | 338 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 188 | `icache.if_resp_pc_o [4]` → `frontend.frozen_o` | 9.535 | 1 | 先处理响应 PC→前端 next-PC→Icache 请求匹配的同周期链，用预计算下一行/预测目标及独立请求缓冲隔离；将取指队列空间判断、出队计数和重定向计数更新解耦，用已有占用状态产生本地 credit；保持连续取指吞吐。 |
| 189 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_load` | 9.503 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 190 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_wdata [120]` | 9.474 | 128 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 191 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_mask [8]` | 9.412 | 16 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 192 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_addr [3]` | 9.299 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 193 | `lsq.head_o [0]` → `completion.direct_hold_tag[2] [14]` | 9.287 | 16 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；局部保存完成项并分离仲裁选择与消费许可，采用平衡仲裁和独立保持槽，切断跨功能单元的 ready 广播链。 |
| 194 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[0].g_local_commands.g_word[0].port_bank/storage.lane_0/ce_in` | 9.284 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 195 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[0].g_local_commands.g_word[0].port_bank/storage.lane_1/ce_in` | 9.284 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 196 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[0].g_local_commands.g_word[0].port_bank/storage.lane_2/ce_in` | 9.284 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 197 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[0].g_local_commands.g_word[0].port_bank/storage.lane_3/ce_in` | 9.284 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 198 | `lsq.head_o [0]` → `dcache.request_data_ready` | 9.244 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 199 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_data_from_sram` | 9.219 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 200 | `lsq.head_o [0]` → `bus.write_sent[0] [1]` | 9.211 | 12 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 201 | `lsq.head_o [0]` → `dcache.g_sram_tags.demand_tags.lane_1/ce_in` | 9.208 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 202 | `lsq.head_o [0]` → `dcache.g_sram_tags.nextline_tags.lane_1/ce_in` | 9.208 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 203 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.genblk4.g_banked_updates.g_mshr_data[3].state_bank/data_o [120]` | 9.202 | 512 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 204 | `lsq.head_o [0]` → `completion.direct_rr_reg [1]` | 9.154 | 3 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；局部保存完成项并分离仲裁选择与消费许可，采用平衡仲裁和独立保持槽，切断跨功能单元的 ready 广播链。 |
| 205 | `lsq.head_o [0]` → `completion.direct_hold_source[2] [0]` | 9.129 | 3 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；局部保存完成项并分离仲裁选择与消费许可，采用平衡仲裁和独立保持槽，切断跨功能单元的 ready 广播链。 |
| 206 | `lsq.head_o [0]` → `bus.write_received[0] [0]` | 9.114 | 12 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 207 | `lsq.head_o [0]` → `bus.write_error[0]` | 9.114 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 208 | `lsq.head_o [0]` → `dcache.request_tag [11]` | 9.088 | 19 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 209 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_valid` | 9.074 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 210 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_lsq [1]` | 9.070 | 15 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 211 | `lsq.head_o [0]` → `bus.write_mask[0] [3]` | 9.052 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 212 | `lsq.head_o [0]` → `bus.write_data[0] [8]` | 9.010 | 512 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 213 | `bus.g_response_fifos.data.count [1]` → `bus.g_response_fifos.data.packets[1] [9]` | 8.945 | 338 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 214 | `lsq.head_o [0]` → `completion.direct_hold_valid [2]` | 8.938 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；局部保存完成项并分离仲裁选择与消费许可，采用平衡仲裁和独立保持槽，切断跨功能单元的 ready 广播链。 |
| 215 | `lsq.head_o [0]` → `dcache.genblk4.g_banked_updates.g_metadata[58].state_bank/query_request_active` | 8.915 | 64 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 216 | `lsq.head_o [0]` → `dcache.genblk4.g_banked_updates.g_metadata[38].state_bank/query_prefetch_active` | 8.907 | 64 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 217 | `lsq.head_o [0]` → `dcache.genblk4.g_banked_updates.g_metadata[43].state_bank/query_request_row [2]` | 8.900 | 192 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 218 | `lsq.head_o [0]` → `dcache.genblk4.g_banked_updates.g_metadata[43].state_bank/query_prefetch_row [0]` | 8.898 | 192 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在元数据 bank 内就地产生动作条件，避免全局 static_request_action 编码→广播→再解码；将 refill、store-hit、miss 分开到行。 |
| 219 | `bus.g_response_fifos.data.count [1]` → `bus.g_response_fifos.data.tail` | 8.891 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 220 | `lsq.head_o [0]` → `dcache.request_index [0]` | 8.820 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 221 | `lsq.head_o [0]` → `dcache.prefetch_index [0]` | 8.820 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 222 | `lsq.head_o [0]` → `bus.write_addr[1] [31]` | 8.816 | 112 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 223 | `lsq.head_o [0]` → `bus.write_id[1] [6]` | 8.816 | 16 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 224 | `lsq.head_o [0]` → `bus.write_expected[1] [0]` | 8.816 | 12 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 225 | `lsq.head_o [0]` → `dcache.g_sram_tags.demand_tags.lane_0/ce_in` | 8.814 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 226 | `lsq.head_o [0]` → `dcache.g_sram_tags.nextline_tags.lane_0/ce_in` | 8.814 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 227 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_store` | 8.805 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 228 | `lsq.head_o [0]` → `dcache.request_line_addr [4]` | 8.805 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 229 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_size [0]` | 8.805 | 2 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 230 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_unsigned` | 8.767 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 231 | `lsq.head_o [0]` → `bus.write_valid [3]` | 8.754 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 232 | `lsq.head_o [0]` → `bus.read_valid [2]` | 8.671 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 233 | `lsq.head_o [0]` → `bus.read_error[7]` | 8.657 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 234 | `lsq.head_o [0]` → `bus.read_received[7] [0]` | 8.657 | 24 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 235 | `lsq.head_o [0]` → `bus.read_addr[6] [0]` | 8.649 | 256 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 236 | `lsq.head_o [0]` → `bus.read_id[6] [7]` | 8.649 | 64 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 237 | `lsq.head_o [0]` → `bus.read_sent[6] [0]` | 8.629 | 24 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 238 | `lsq.head_o [0]` → `bus.read_data_side[6]` | 8.628 | 8 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 239 | `lsq.head_o [0]` → `dcache.mshr_sent[2]` | 8.534 | 4 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 240 | `bus.g_response_fifos.data.count [1]` → `bus.g_response_fifos.instruction.tail` | 8.514 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 241 | `lsq.head_o [0]` → `core.g_cached_memory.memory_bridge.d_id [1]` | 8.507 | 3 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 242 | `lsq.head_o [0]` → `core.g_cached_memory.memory_bridge.d_line_addr [4]` | 8.485 | 28 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 243 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_victim_data[0] [113]` | 8.458 | 512 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 244 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_writeback[0]` | 8.453 | 4 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 245 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_victim_addr[0] [4]` | 8.415 | 112 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 246 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_rfo_offered[0]` | 8.403 | 4 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 247 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_victim_entry[0] [0]` | 8.402 | 40 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 248 | `lsq.head_o [0]` → `core.g_cached_memory.memory_bridge.i_line_addr [1]` | 8.328 | 32 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 249 | `lsq.head_o [0]` → `core.g_cached_memory.memory_bridge.i_id [0]` | 8.321 | 7 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 250 | `lsq.head_o [0]` → `dcache.send_locked_index [0]` | 8.239 | 3 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 251 | `lsq.head_o [0]` → `bus.prefer_d_request` | 8.187 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 252 | `lsq.head_o [0]` → `dcache.send_locked` | 8.177 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 253 | `lsq.head_o [0]` → `dcache.g_sram_tags.query_from_sram` | 8.146 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 254 | `lsq.head_o [0]` → `core.mmio_ack_lsq_tag [9]` | 8.091 | 15 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；局部保存 MMIO ack 与标签，分离 valid 消费和标签载荷更新；仍在合法写完成握手后产生退出副作用。 |
| 255 | `lsq.head_o [0]` → `core.mmio_ack_pending` | 8.027 | 1 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；局部保存 MMIO ack 与标签，分离 valid 消费和标签载荷更新；仍在合法写完成握手后产生退出副作用。 |
| 256 | `bus.g_response_fifos.data.count [1]` → `bus.g_response_fifos.data.count [0]` | 8.021 | 2 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 257 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_addr[1] [4]` | 7.677 | 128 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 258 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_lsq[1] [1]` | 7.666 | 60 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 259 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_size[1] [0]` | 7.666 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 260 | `bus.g_response_fifos.data.count [1]` → `bus.prefer_write_reply` | 7.599 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；用 FIFO 本地占用 credit 和独立请求/响应保持槽隔离缓存反压，按通道静态写入；保留 AXI 握手和错误响应语义。 |
| 261 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_prefetch[0]` | 7.532 | 4 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 262 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_unsigned[0]` | 7.522 | 4 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 263 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.resp_word_reg [31]` | 7.449 | 32 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 264 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_mask[1] [0]` | 7.446 | 64 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 265 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_store[1]` | 7.346 | 4 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 266 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_merge_delay[1] [4]` | 7.342 | 20 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 267 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.mshr_valid[0]` | 7.061 | 4 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 268 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.resp_line_reg [70]` | 6.665 | 128 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 269 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.resp_lsq_reg [4]` | 6.612 | 15 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 270 | `recovery_rs_branch_slot [5]` → `rob.epoch_reg [3]` | 6.155 | 4 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；逐 ROB 行预解码槽位/epoch 与更新源，局部合并完成、恢复和 store 握手；维持顺序提交及副作用抑制。 |
| 271 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_ready[6]` | 6.059 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 272 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_valid[6]` | 6.056 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 273 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.resp_line_valid_reg` | 6.038 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 274 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.resp_error_reg` | 6.034 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 275 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.resp_valid_reg` | 6.028 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 276 | `lsq.head_o [0]` → `dcache.g_sram_tags.nextline_tags.lane_0/addr_in[7]` | 6.016 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 277 | `lsq.head_o [0]` → `dcache.g_sram_tags.nextline_tags.lane_1/addr_in[7]` | 6.016 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 278 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_0/addr_in[4]` | 5.660 | 72 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 279 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_1/addr_in[4]` | 5.660 | 72 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 280 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_2/addr_in[4]` | 5.660 | 72 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 281 | `lsq.head_o [0]` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_3/addr_in[4]` | 5.660 | 72 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 282 | `lsq.head_o [0]` → `dcache.g_sram_tags.demand_tags.lane_0/addr_in[8]` | 5.617 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 283 | `lsq.head_o [0]` → `dcache.g_sram_tags.demand_tags.lane_1/addr_in[8]` | 5.617 | 9 | 先缩短 LSQ 头指针派生的资格判断与完成/就绪控制链，按行分摊控制负载；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 284 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.bank_hold [120]` | 5.491 | 256 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 285 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.demand_hold [27]` | 5.133 | 38 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 286 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.prefetch_hold [17]` | 4.833 | 38 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 287 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.demand_tags.lane_0/we_in` | 4.825 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 288 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.demand_tags.lane_1/we_in` | 4.825 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 289 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.nextline_tags.lane_0/we_in` | 4.825 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 290 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.nextline_tags.lane_1/we_in` | 4.825 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 291 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_0/wd_in[2]` | 4.788 | 64 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 292 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_1/wd_in[0]` | 4.788 | 64 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 293 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_2/wd_in[2]` | 4.788 | 64 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 294 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_3/wd_in[0]` | 4.788 | 64 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 295 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_line[7] [1]` | 4.673 | 1024 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 296 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_0/we_in` | 4.635 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 297 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_1/we_in` | 4.635 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 298 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_2/we_in` | 4.635 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 299 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.g_data_way[1].g_local_commands.g_word[0].port_bank/storage.lane_3/we_in` | 4.635 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 300 | `recovery_rs_branch_slot [5]` → `g_alu[3].alu.shift_remaining [4]` | 4.422 | 20 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 301 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_error[7]` | 4.270 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 302 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_mshr[3] [1]` | 3.903 | 16 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 303 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_lsq[3] [1]` | 3.903 | 120 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 304 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_unsigned[3]` | 3.903 | 8 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 305 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_addr[3] [0]` | 3.903 | 32 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 306 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.waiter_size[3] [0]` | 3.903 | 16 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；按 MSHR/waiter 行并行比较并局部写入，使用平衡选择树，分离回填数据写入和控制更新。 |
| 307 | `recovery_rs_branch_slot [5]` → `g_alu[0].alu.shift_busy` | 3.866 | 4 | 先局部化 recovery/redirect/flush 的有效性判断与分发，避免高负载全局控制串接到该终点；把 ALU 结果保持/消费与上游发射握手局部化；移位终点则缩短步数/结果选择逻辑，保持背压时结果稳定。 |
| 308 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.ack_lsq_reg [9]` | 3.708 | 15 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 309 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.ack_error_reg` | 3.624 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 310 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.ack_valid_reg` | 3.574 | 1 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；分离请求接收、回填和响应槽更新的控制，局部化寄存器写使能；必要时使用可保持请求的弹性缓冲切断反压链。 |
| 311 | `mdu.gen_divider.divider.divisor_reg [0]` → `mdu.gen_divider.divider.unsigned_cache_q_reg [31]` | 3.476 | 32 | 缩短除法商/余数结果选择和符号修正逻辑；可把修正与缓存写入分开一拍，但需评估 DIV/REM 延迟对 IPC 的影响。 |
| 312 | `mdu.gen_divider.divider.divisor_reg [0]` → `mdu.gen_divider.divider.signed_cache_q_reg [31]` | 3.471 | 32 | 缩短除法商/余数结果选择和符号修正逻辑；可把修正与缓存写入分开一拍，但需评估 DIV/REM 延迟对 IPC 的影响。 |
| 313 | `mdu.gen_divider.divider.divisor_reg [0]` → `mdu.gen_divider.divider.unsigned_cache_r_reg [31]` | 3.285 | 32 | 缩短除法商/余数结果选择和符号修正逻辑；可把修正与缓存写入分开一拍，但需评估 DIV/REM 延迟对 IPC 的影响。 |
| 314 | `mdu.gen_divider.divider.divisor_reg [0]` → `mdu.gen_divider.divider.signed_cache_r_reg [31]` | 3.281 | 32 | 缩短除法商/余数结果选择和符号修正逻辑；可把修正与缓存写入分开一拍，但需评估 DIV/REM 延迟对 IPC 的影响。 |
| 315 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.demand_tags.lane_0/wd_in[8]` | 3.259 | 19 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 316 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.demand_tags.lane_1/wd_in[8]` | 3.259 | 19 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 317 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.nextline_tags.lane_0/wd_in[8]` | 3.259 | 19 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 318 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `dcache.g_sram_tags.nextline_tags.lane_1/wd_in[8]` | 3.259 | 19 | 先将总线响应接收和 Dcache 请求/回填仲裁局部化，避免同拍响应反压控制扩散；在已有局部 SRAM 命令模块内分解 hit/refill/local-fill 选择，按 way/word 生成 CE/WE/地址/数据；新增命令寄存需同步所有字段和握手。 |
| 319 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.wq_count [4]` | 2.940 | 5 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 320 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.wq_slot[4] [0]` | 2.892 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 321 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.write_cursor [0]` | 2.873 | 2 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 322 | `g_alu[0].alu.result_valid_reg` → `recovery_rs_branch_slot [0]` | 2.861 | 6 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 323 | `g_alu[0].alu.result_valid_reg` → `$\rob.valid_mem$rdreg[0]$q [0]` | 2.861 | 6 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 324 | `g_alu[0].alu.result_valid_reg` → `branch_pending_tag [0]` | 2.859 | 9 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 325 | `g_alu[0].alu.result_valid_reg` → `branch_pending_value [0]` | 2.859 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 326 | `g_alu[0].alu.result_valid_reg` → `branch_pending_phys [0]` | 2.859 | 6 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 327 | `g_alu[0].alu.result_valid_reg` → `branch_pending_rd_we` | 2.859 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 328 | `g_alu[0].alu.result_valid_reg` → `branch_pending_pc [0]` | 2.859 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 329 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.wq_tail [3]` | 2.856 | 4 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 330 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.write_active` | 2.845 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 331 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.aw_done` | 2.818 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 332 | `$\bus.write_addr$rdreg[0]$q [0]` → `bus.w_done` | 2.818 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 333 | `$\bus.write_addr$rdreg[0]$q [0]` → `wstrb[0]` | 2.769 | 4 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 334 | `$\bus.write_addr$rdreg[0]$q [0]` → `wdata[10]` | 2.739 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 335 | `dcache.mshr_mask[0] [14]` → `core.g_cached_memory.memory_bridge.d_local_error` | 2.680 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 336 | `$\bus.write_addr$rdreg[0]$q [0]` → `awvalid` | 2.624 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 337 | `$\bus.write_addr$rdreg[0]$q [0]` → `wvalid` | 2.624 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 338 | `$\bus.write_addr$rdreg[0]$q [0]` → `awaddr[3]` | 2.463 | 30 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 339 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `$\bus.g_response_fifos.data.packets$rdreg[0]$q` | 1.508 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 340 | `$\bus.g_response_fifos.data.packets$rdreg[0]$q` → `bus.g_response_fifos.data.head` | 1.508 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 341 | `$\bus.read_addr$rdreg[0]$q [2]` → `araddr[31]` | 1.483 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 342 | `bus.rq_head [0]` → `bus.read_data[6] [96]` | 1.153 | 1024 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 343 | `$\bus.g_response_fifos.instruction.packets$rdreg[0]$q` → `icache.data_array.lane_0/wd_in[30]` | 1.099 | 128 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 344 | `$\bus.read_addr$rdreg[0]$q [2]` → `bus.read_active` | 1.003 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 345 | `$\bus.read_addr$rdreg[0]$q [2]` → `bus.read_cursor [2]` | 1.002 | 3 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 346 | `mdu.gen_divider.divider.busy_reg` → `mdu.gen_divider.divider.unsigned_cache_b_reg [0]` | 0.981 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 347 | `mdu.gen_divider.divider.busy_reg` → `mdu.gen_divider.divider.unsigned_cache_a_reg [0]` | 0.981 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 348 | `mdu.gen_divider.divider.busy_reg` → `mdu.gen_divider.divider.unsigned_cache_valid_reg` | 0.953 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 349 | `$\bus.read_addr$rdreg[0]$q [2]` → `bus.rq_word[11] [0]` | 0.938 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 350 | `core.cycles [0]` → `core.cycles [30]` | 0.838 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 351 | `mdu.gen_divider.divider.busy_reg` → `mdu.gen_divider.divider.signed_cache_b_reg [1]` | 0.837 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 352 | `mdu.gen_divider.divider.busy_reg` → `mdu.gen_divider.divider.signed_cache_a_reg [1]` | 0.837 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 353 | `mdu.gen_divider.divider.busy_reg` → `mdu.gen_divider.divider.signed_cache_valid_reg` | 0.582 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 354 | `bus.read_active` → `bus.rq_count [3]` | 0.564 | 5 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 355 | `bus.read_active` → `bus.rq_slot[12] [0]` | 0.505 | 48 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 356 | `bus.read_active` → `bus.rq_tail [3]` | 0.458 | 4 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 357 | `bvalid` → `bus.wq_head [3]` | 0.401 | 4 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 358 | `bus.write_active` → `$\bus.write_addr$rdreg[0]$q [1]` | 0.365 | 2 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 359 | `bus.write_active` → `bus.write_issue_slot [1]` | 0.365 | 2 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 360 | `bus.read_valid [1]` → `$\bus.read_addr$rdreg[0]$q [2]` | 0.359 | 3 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 361 | `bus.read_valid [1]` → `bus.read_issue_slot [2]` | 0.359 | 3 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 362 | `rvalid` → `bus.rq_head [0]` | 0.354 | 4 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 363 | `bus.read_active` → `arvalid` | 0.240 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 364 | `bus.rq_count [1]` → `rready` | 0.173 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 365 | `bus.wq_count [3]` → `bready` | 0.167 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 366 | `rob.error_o` → `debug_error` | 0.114 | 1 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 367 | `core.cycles [0]` → `debug_core_cycles[0]` | 0.110 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
| 368 | `core.instret [10]` → `debug_instret[10]` | 0.105 | 32 | 此终点的最差 setup 路径满足 300 MHz 周期预算；暂不改动，优化共享控制链后复查。 |
