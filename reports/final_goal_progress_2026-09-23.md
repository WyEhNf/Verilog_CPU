# 最终要求对齐进度（2026-09-23）

本页按 `docs/final_project_requirements.md` 的最终口径记录证据。历史记录将 CPU-2026 称为代理测试；2026-09-26 用户已确认按现有 benchmark 文件夹继续评测，当前 IPC 验收采用这六项的几何平均，不再等待 `testcases/perf_*`。完整 FakeRAM 面积及存储时序尚未验证，因此仍不能宣称 Tier 3 三项同时达标。下面历史记录中的“缺少官方 perf_*”不再是当前阻塞项。

## 已实现与直接验证

- RV32I 译码的旧 `0x0ff00513` 停机别名改为 `LEGACY_SENTINEL_HALT` 可选参数，硬件默认关闭，旧测试平台默认开启。最终模式中该编码仍是合法 `ADDI`。
- `LH/LHU/SH` 已加入译码；半字程序经完整 CPU 测试返回 0。RV32M 八条指令已有现有实现；完整官方正确性测试仍待运行。
- 32 位全字 `SW` 至 `0x80000000` 从缓存前旁路到外部数据总线，`WMASK=16'h000f`（低四字节 `WSTRB=4'hf`），数据来自完整 32 位存储值；ROB 等到该总线请求被接收并获得 LSQ 确认后才按程序顺序停机。使用包含旧停机编码的 `mmio_exit.c`，Icarus 和 20 周期 Verilator 分别验证返回 `0x12345678`；Verilator 结果为 59 周期、退休 14 条。
- CPU 外部 RAM 地址范围参数默认设为 256 MiB；桥接边界测试接受最后一个 16 字节行、拒绝 `0x10000000`。旧平台仍可选 1 MiB 以快速跑代理测试。
- I-cache 容量/路数可选，默认 64 行、2 路；非阻塞 D-cache 容量/路数可选，已测试 1 路及 2 路。两路 D-cache 的冲突命中、脏行替换与正确物理地址回写定向测试通过。

## 性能探索：本地六程序代理，20 周期统一 RAM

| 配置 | 汇总 IPC | 六程序几何平均 IPC | 备注 |
|---|---:|---:|---|
| P2，D-cache 128 行 1 路 | 0.626664 | 0.704744 | `build/cpu2026/assoc_base_0923/baseline.json` |
| P2，D-cache 128 行 2 路 | 0.691662 | 0.739550 | `build/cpu2026/assoc_0923/assoc2.json` |
| P2，D-cache 64 行 2 路 | 0.548699 | 0.689592 | 容量不足抵消相联度收益 |
| P4，D-cache 256 行 1 路 | 0.881805 | 0.961493 | `build/cpu2026/p4_0923/p4.json` |
| P4，D-cache 256 行 2 路 | 0.980719 | 1.043551 | `build/cpu2026/p4_0923/p4_assoc2.json` |
| P4，D-cache 512 行 2 路 | 1.094616 | 1.095518 | `build/cpu2026/p4_knobs_0923/p4_assoc2_d512.json` |
| P4，512 行 2 路，免快照恢复 | 1.094616 | 1.095518 | `build/cpu2026/p4_tier3_probe_0923/p4_d512_checkpoint1.json` |
| P4，512 行 2 路，ROB32 | 1.054213 | 1.055080 | 容量下降导致 IPC 回退 |
| P4，D-cache 1024 行 2 路 | 1.319377 | 1.164361 | `build/cpu2026/p4_tier3_probe_0923/p4_d1024.json`，尚未量面积 |
| P4，1024 行 2 路，免快照，ROB32/PRF64 | 1.266951 | 1.121807 | `build/cpu2026/p4_compact_0923/p4_d1024_cp1_r32p64.json`，当前紧凑候选 |
| P4，1024 行 2 路，免快照，ROB16/PRF64 | 1.107782 | 1.039450 | ROB16 容量不足 |
| P4，ROB32/PRF64，D-cache1024行2路，LSQ16，MMIO | 1.266865 | 1.121336 | 层级重命名＋并行 LSQ 行掩码，六项全过 |
| 上述配置仅 LSQ 缩为 8 | 1.262038 | 1.099197 | 仅高于 Tier 3 代理阈值 0.000697，余量极薄 |

P4 同容量改两路后，`rsort` 从 0.8793 提升到 1.0366，`vvadd` 从 0.8048 提升到 0.9771；继续扩大数据缓存至 1024 行则使 `rsort` 达到 1.668，但面积成本必须另算。RS16→RS32 的六程序几何平均仅从 1.043551 增至 1.046063，不是优先方向。I-cache 默认 64 行 2 路扩至 128 行只把 P2 汇总 IPC 从 0.626664 提到 0.626951，改 1 路则为 0.626404，短期不值得为了容量增加面积。

## 尚不能宣称 Tier 3

- 尚无提供的 `testcases/perf_*`、FakeRAM 面积模型、正式频率脚本，无法得到正式 GEOMEAN 或 SRAM/组合/时序/总面积四项分解。
- 1 KiB D-cache P2 的旧版完整 FF 面积为 36,627.526080 µm²，带缓冲近似 STA Fmax 255.57 MHz；这不是当前最终配置的面积或频率。
- 当前 P4、D-cache 256 行 2 路、完整 MMIO 设计以所有数组展开为触发器的 Yosys/ASAP7 标准单元面积为 **120,610.279800 µm²**（时序单元 36,192.5172；其余 84,417.7626）；见 `build/synth/p4_p96_r64_d256_assoc2_final_ff/area_audit.json`。其中 ROB 32,402.84、D-cache 28,988.54 µm²。该面积运行采用 D-cache `INDEX_HASH=0`，而代理 IPC 使用 `INDEX_HASH=1`；两者不是严格同配置，且 FF 全展开并非正式 FakeRAM 口径。
- 与代理 IPC 一致的 XOR 索引、512 行两路、免快照恢复配置完整 FF 面积为 **145,371.785400 µm²**（时序单元 43,173.4212；其余 102,198.3642），独立核对相符；见 `build/synth/p4_p96_r64_d512_assoc2_cp1_hash1_final_ff/area_audit.json`。其中 D-cache 57,484.65、ROB 20,171.79、backend_joint 22,639.24 µm²。与有快照的 ROB 模块相比，免快照使 ROB 省约 12,231 µm²，但其恢复逻辑使 backend_joint 增约 8,496 µm²，整机净收益有限。频率仍待复测。
- 目前紧凑候选 P4/ROB32/PRF64/D-cache1024行2路/免快照已通过三项基础程序、半字、RV32M 和 32 位 MMIO 退出的 Icarus 与 Verilator 本地测试；正式正确性程序集仍缺失。
- 同一紧凑架构的 **MMIO 退出** Verilator 可执行文件又通过六个 CPU-2026 代理程序，20 周期统一内存下汇总 IPC **1.266699**、逐程序几何平均 IPC **1.121144**；见 `build/cpu2026/final_mmio_p4_r32p64_d1024_report.json`。该可执行文件的外部测试 RAM 为 1 MiB、I/D outstanding 为 8/4、完成队列深度为 16、缓存统计关闭，因此不能与下面的黑盒面积直接拼成同配置得分。另一次完成队列深度 4、I/D outstanding 16/8、缓存统计开启的 MMIO 代理测试全部通过，但几何平均仅 **1.052915**；见 `build/cpu2026/area_matched_p4_r32p64_d1024_c4_mmio_report.json`。这说明完成队列深度不能随意缩到 4。
- 紧凑候选的最新 Yosys/ASAP7 黑盒综合得到 **28,803.256560 µm² 已知标准单元面积**，见 `build/synth/p4_r32p64_d1024_cp1_hash1_bb/area_audit.json`；Yosys 原始日志证明完成队列深度实际为 **16**，审计元数据已经对齐。审计状态明确为 `INCOMPLETE`：150 个层级存储实例未计价；清单有 132 个存储定义、188,592 bit 定义几何（实例化后物理总位数还须按层级计）。其中 D-cache `data_mem` 为 1024×128 bit，推断 2 读/4 写；`tag_mem` 为 1024×19 bit，推断 5 读/3 写。它们不能未经端口合法化就按普通单端口 SRAM 宏计价。相对 Tier 3 的 36,000 µm² 上限，已计价逻辑只留下 **7,196.743440 µm²** 给全部尚未计价的存储与其他成本，这不是面积通过证明。
- 又构建了与上述综合架构参数对齐的 MMIO Verilator 版本（测试 RAM 仍为 1 MiB），六个代理程序全部通过，汇总 IPC **1.266865**、几何平均 IPC **1.121336**；见 `build/cpu2026/synth_matched_p4_r32p64_d1024_c16_mmio_report.json`。完成队列深度 4 的对照结果显著较差，故当前候选固定深度 16。
- 当前紧凑候选的黑盒逻辑网表经过 16 扇出缓冲后，以 ASAP7 RVT TT NLDM、300 MHz 时钟（3333.33 ps、100 ps uncertainty）跑 OpenSTA；最差已实现标准单元路径周期 **8186.30 ps，Fmax 122.16 MHz**，起点在 `frontend` 触发器、终点在 `backend.rename` 触发器，见 `build/timing/p4_r32p64_d1024_cp1_hash1_bb/timing_300mhz_buf16.rpt`。该 STA 仍有 139 个无时序弧的通用存储边界，因此不能证明全芯片时序通过；但这条已经违例的标准单元路径足以证明当前映射未达到 300 MHz。
- 围绕该路径完成两版重命名空闲寄存器预选。先将候选预选与译码束解耦，逻辑面积 **28,815.401700 µm²**、缓冲后 Fmax **131.41 MHz**；再改为 8 位局部优先编码加组选择，面积 **28,785.060720 µm²**、Fmax **206.06 MHz**，六项 MMIO 代理 IPC 仍为 **1.121336**、周期数完全不变。最终层级搜索版已通过 BE1/2/4 的单元测试（含碎片化位图/部分槽不写寄存器）、五项基础程序和六项代理程序。证据分别在 `build/synth/p4_r32p64_d1024_cp1_hash1_hier_bb/area_audit.json`、`build/timing/p4_r32p64_d1024_cp1_hash1_hier_bb/timing_300mhz_buf16.rpt`、`build/cpu2026/rename_hier_p4_r32p64_d1024_c16_mmio_report.json`。新最差标准单元路径为 LSQ 触发器到 D-cache 触发器，周期 **4852.98 ps**，仍未过 300 MHz。
- 试开已有 D-cache 请求寄存级后，六项 MMIO 代理程序仍全部通过，但几何平均 IPC 从 **1.121336 降至 1.048190**；见 `build/cpu2026/rename_hier_pipe1_p4_r32p64_d1024_c16_mmio_report.json`。因此该现有非直通寄存级不能直接作为 Tier 3 时序修复方案；这次配置未做面积/STA，不能宣称它修好了时序。
- 对同一层级搜索网表测试 16/8/4 扇出上限的缓冲树，标准单元路径 Fmax 分别为 **206.06/224.64/210.58 MHz**。8 扇出树插入 86,784 个 BUFx8，按已表征的 0.17496 µm²/个计算仅缓冲器就 **15,183.72864 µm²**；与重导出平面逻辑 31,004.85114 µm² 相加为 **46,188.57978 µm²**，还未计任何存储。16 扇出版本的同口径亦为 **37,728.21402 µm²**。这是自制扇出修复流的实现成本，不是官方 FakeRAM/后端物理面积，但证明只靠这种大量缓冲既未过 300 MHz，也不具备当前面积余量。
- LSQ 将每项 load/store 的访问范围预先转为 16 字节行掩码，旧 store 危险改为并行 OR 归约后，LSQ16 配置的六项代理程序周期数不变，五项基础程序、LSQ BE1/2/4 单元测试和 LSQ 深度 1/2/4/8/16 的各 3000 次随机危险/转发对照通过。已计价逻辑面积降至 **27,907.475940 µm²**，扇出 16 的标准单元 Fmax 提至 **214.65 MHz**，但仍低于 300；见 `build/synth/p4_r32p64_d1024_cp1_hash1_lsqmask_bb/area_audit.json` 和 `build/timing/p4_r32p64_d1024_cp1_hash1_lsqmask_bb/timing_300mhz_buf16.rpt`。
- 同一 LSQ 行掩码架构改为 LSQ8 后，五项基础程序和六项代理程序通过，代理几何平均 **1.099197**。但 `rsort` 的 LSQ 满周期从 62 增到 56,141，`qsort` 从 244 增到 20,169；该性能余量不稳健。已计价逻辑面积 **26,151.548220 µm²**、扇出 16 的 Fmax **229.26 MHz**，关键路径转为 ROB→ALU；平面逻辑加手工缓冲约 **33,723.58 µm²**，仍未计 SRAM。见 `build/cpu2026/lsq8_mask_p4_r32p64_d1024_c16_mmio_report.json`、`build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_bb/area_audit.json`、`build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_bb/timing_300mhz_buf16.rpt`。因此 LSQ8 目前也没有正式面积/IPC/频率同时通过证据。
- 最新将执行结果的 RS 唤醒从完成 FIFO 的 `producer_ready` 背压链中解耦：生产者在握手前保持有效和值稳定，故可提前通知依赖者；恢复杀死的生产者仍由 `producer_target_live_r` 屏蔽。LSQ16 与 LSQ8 各六项 MMIO 代理程序全部通过，且每项周期数与修改前完全一致；五项基础程序与后端 BE1 单元测试通过（后端测试的乘法/负载碰撞不再依赖已不存在的乘法器内部流水级）。LSQ16 已计价逻辑面积由 **27,907.475940** 增为 **27,920.320920 µm²**，扇出 16 的 Fmax 仍为 **214.65 MHz**；LSQ8 已计价逻辑面积由 **26,151.548220** 增为 **26,168.038200 µm²**，Fmax 由 **229.26** 提至 **248.49 MHz**，新瓶颈也转为 LSQ→D-cache。证据见 `build/cpu2026/early_wake_p4_r32p64_d1024_c16_mmio_report.json`、`build/cpu2026/early_wake_lsq8_p4_r32p64_d1024_c16_mmio_report.json`、对应的 `build/synth/*earlywake_bb/area_audit.json` 和 `build/timing/*earlywake_bb/timing_300mhz_buf16.rpt`。两个时序网表均有 139 个未表征存储边界，不能视为全芯片时序收敛。
- 从 LSQ16 的最差路径映射追踪到 LSQ 输出的 `dcache_req_addr[4]`：请求候选与地址选择约在 2.0 ns 才完成，随后 D-cache 的索引、命中和接收判定又串行消耗约 2.6 ns。原有非直通请求寄存级会损失过多 IPC；下一轮需优先缩短 LSQ 地址选择和 D-cache 判定之间的组合串联，而非继续优化 ROB→RS→ALU 路径。
- 将 LSQ 请求地址随最老可发射候选的平衡选择树一并传递，省掉候选编号确定后的第二次动态数组读取，并使无效请求时地址不再受转发/恢复门控。LSQ8 五项基础程序、BE1/2/4 LSQ 单元测试、深度 1/2/4/8/16 各 3000 次随机危险/转发对照、六项 MMIO 代理程序均通过；六项代理周期数与前版逐项相同，几何平均 IPC **1.0991968369**。已计价逻辑面积从 **26,168.038200** 增至 **26,190.389340 µm²**，16 扇出缓冲下 Fmax 从 **248.49** 提至 **259.27 MHz**（周期 3856.98 ps），最差路径仍为 LSQ→D-cache，尚未达到 300 MHz。证据见 `build/cpu2026/pickaddr_lsq8_p4_r32p64_d1024_c16_mmio_report.json`、`build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_pickaddr_bb/area_audit.json`、`build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_pickaddr_bb/timing_300mhz_buf16.rpt`。标准单元 STA 仍有 139 个未表征存储边界，不能证明全芯片时序。
- 同一地址树下，LSQ16 的黑盒综合已完成：已计价逻辑面积 **27,993.308400 µm²**、150 个存储实例未计价；见 `build/synth/p4_r32p64_d1024_cp1_hash1_pickaddr_bb/area_audit.json`。该配置的代理 IPC 尚沿用修改地址树前的 **1.121336**，不能把两者当作严格同版本成绩；其 STA 亦未完成。
- 试将每个候选负载的旧存储覆盖并行计算并随候选树传递，LSQ BE1/2/4 单元测试、五种深度各 3000 次随机危险/转发对照、五项基础程序及六项代理程序均通过。该次代理 IPC **1.097703** 使用 I/D outstanding=8/4，而旧 **1.099197** 使用 16/8，不能归因于 RTL 改动；后续匹配参数对照已确认差异来自测试配置。已计价逻辑面积升至 **26,263.478880 µm²**，16 扇出缓冲 Fmax 仅从 **259.27** 增至约 **260.95 MHz**（最差 slack -500.8023 ps）。由于很小的时序收益和面积增加，该 RTL 实验已撤回，当前代码仍采用原转发掩码判定；实验记录保留在 `build/cpu2026/pickcover_lsq8_p4_r32p64_d1024_c16_mmio_report.json`、`build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_pickcover_bb/area_audit.json`、`build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_pickcover_bb/timing_300mhz_buf16.rpt`。
- 进一步保持原 LSQ8 RTL 不变，只将 `synth/synth_bb.tcl` 的 ABC 末端从面积导向 `map -a` 切为时序导向 `map`（显式设置 `ASAP7_ABC_DELAY_MAP=1`，默认仍是面积导向）。已计价逻辑面积由 **26,190.389340** 增为 **26,616.300300 µm²**；同样的 16 扇出缓冲及 ASAP7/OpenSTA 约束下，最差标准单元路径从 **3856.98** 缩到 **3590.14 ps**，Fmax 从 **259.27** 升为 **278.54 MHz**。见 `build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_pickaddr_delaymap_bb/area_audit.json` 和 `build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_pickaddr_delaymap_bb/timing_300mhz_buf16.rpt`。该局部 STA 仍有 139 个未表征存储边界，频率仍低于 300 MHz；并且新增映射面积压缩了未计价 SRAM 的剩余预算，不能据此宣称面积通过。代理 IPC 沿用相同 RTL 的 1.099197，不是从映射网表重新跑出的正式成绩。
- 对上述偏时序映射再把手工缓冲扇出上限从 16 收紧至 8，插入缓冲器从 **34,793** 增到 **79,538** 个，单按 BUFx8 的 **0.17496 µm²/个** 就约 **13,915.97 µm²**；局部 Fmax 反而从 **278.54** 降到 **276.66 MHz**。见 `build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_pickaddr_delaymap_bb/timing_300mhz_buf8.rpt`。因此继续靠全局加密这种手工缓冲既不改善频率也破坏面积预算。
- 对偏时序映射的最差路径进一步定位：由 ROB 状态经 RS 选择到 ALU 分支重定向寄存器。把 ALU 的 32 位比较拆成并行 4 位比较及高低组归并后，随机 3000 对输入 × 8 种分支/SLT 操作、既有 ALU 测试、同配置五项基础程序均通过；六项 MMIO 代理程序在 **I/D outstanding=16/8**、20 周期统一内存下逐项周期数与改前完全一致，几何平均 IPC **1.0991968369**。已计价逻辑面积从 **26,616.300300** 降至 **26,612.509500 µm²**，16 扇出局部 Fmax 从 **278.54** 提至 **288.96 MHz**（周期 3460.74 ps，slack -127.4072 ps），但仍未达到 300 MHz。证据见 `build/cpu2026/cmp4_i16d8_lsq8_p4_r32p64_d1024_c16_mmio_report.json`、`build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_delaymap_bb/area_audit.json`、`build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_delaymap_bb/timing_300mhz_buf16.rpt`。一次误用 I/D outstanding=8/4 的代理对照为 IPC **1.097703**，与 16/8 结果不能混用；该差异来自测试内存并发参数，不是已否决覆盖位或新比较器造成的退化。
- 在同一比较器架构下，将 ALU 的共享 32 位加减法改为 4 位组生成/传播及三级前缀进位；随机 **3000 对输入 × 11 种分支/SLT/加减操作**、既有 ALU 单元测试、五项基础程序全部通过。严格匹配 **I/D outstanding=16/8** 的六项 MMIO 代理程序亦全部通过，逐项周期数与修改前完全相同，几何平均 IPC **1.0991968369**；见 `build/cpu2026/cmp4_fastadd_i16d8_lsq8_p4_r32p64_d1024_c16_mmio_report.json`。已计价标准单元逻辑面积 **26,611.226460 µm²**；16 扇出缓冲的局部 ASAP7/OpenSTA 最差 slack **+46.1726 ps**、等效最小周期 **3287.16 ps / Fmax 304.21 MHz**，首次满足 300 MHz 的**已表征逻辑路径**约束。证据为 `build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_fastadd_delaymap_bb/area_audit.json`、`build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_fastadd_delaymap_bb/timing_300mhz_buf16.rpt`。**尚不能宣称官方 Tier 3**：150 个存储实例未计价、139 个存储时序边界未表征；本地缺少 FakeRAM 模型和官方 `testcases/perf_*`，代理 IPC 余量仅约 0.000697。
- 使用 `tools/test_simulator_mmio.ps1` 将旧 CPU 仿真程序源码按 RV32IM 重新编译为 32 位 MMIO 退出版本，并用宿主机包装程序取得完整有符号返回值（同时核对其低 8 位与旧清单一致）。按先前要求暂不运行 `pi`；其余 **17/17** 程序在当前 Verilator 配置、20 周期统一内存、I/D outstanding=16/8 下通过，包含 `qsort`、`queens`、`superloop`、`tak` 等长程序。`expr` 的完整返回值为 **-198**、`naive` 为 **350**，若直接把旧清单低 8 位的 58/94 当作完整 MMIO 返回值会误判。此回归覆盖源码重编译版本，不等同于原 `.data` 二进制或尚未获得的正式正确性评测。
- 用现有 `third_party/asap7/sram_0p0` 单端口 SRAM LIB 做了**仅供决策的乐观装箱情景**：已知逻辑 26,611.23 µm² 留给存储的 Tier 3 预算是 **9,388.77 µm²**；仅 D-cache data/tag、I-cache data 三块数组在忽略端口、适配器、冲突与时序时的最低宏面积合计约 **7,132.30 µm²**。若其余 **28,344 bit** 另按库中最佳位密度理想计价，情景存储面积约 **8,130.25 µm²**，只留约 **1,258.52 µm²** 给端口复制/适配/对齐浪费。D-cache data 是 2 读/4 写、tag 是 5 读/3 写，而该库宏仅有单地址读写接口；该情景**不是可实现映射，也不是严格数学下界或 FakeRAM 评分面积**（还忽略了跨数组装箱）。复现命令：`python tools/estimate_local_sram_floor.py build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_fastadd_delaymap_bb/area_audit.json`。
- 试在同一 RTL/参数下关闭 `ENABLE_CACHE_STATS`，偏时序 Yosys 综合已计价逻辑面积仅从 **26,611.226460** 变为 **26,610.920280 µm²**，节省 **0.306180 µm²**，见 `build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_fastadd_nostats_delaymap_bb/area_audit.json`。统计模块虽在层级日志中有约 495 µm² 的模块面积，但作为无外部观察用途的实例已被优化，不能将它误计为可再节省的 495 µm²。由于节省几乎为零，该变体未单独跑 IPC/STA，当前已验证的同配置三指标仍以上述统计开启版本为准。
- 将同一 P4/ROB32/PRF64/RS16/LSQ8/D-cache1024×2/I-cache64×2/完成队列16 配置的外部 RAM 从先前显式指定的 1 MiB 修正为最终要求的 **256 MiB**。`rv32_memory_bridge_256m_tb` 验证最后一条 16 字节 RAM 行有效、越界地址不转发；`tools/test_ram_256m.ps1` 构建并运行 `tests/programs/ram_256m_last_word.c`，在 Verilator 20 周期模型下写 `0x0ffffffc`，用两条同组缓存行逼出脏写回，再从外部 RAM 重新读入，完整 32 位 MMIO 返回 **598**，trace 可见对 `0x0ffffff0` 的写回且 `d_wb=1`。六项 CPU-2026 MMIO 代理程序重新编译/运行后全部通过，逐项周期数与原 1 MiB 运行完全一致，几何平均 IPC **1.0991968369**；报告 `build/cpu2026/cmp4_fastadd_i16d8_lsq8_p4_r32p64_d1024_c16_mmio_ram256m_report.json`。相同 256 MiB 参数的 Yosys+ASAP7 偏时序黑盒综合已计价逻辑面积 **26,614.754820 µm²**，比 1 MiB 增 **3.528360 µm²**，仍有 **150** 个存储实例未计价；见 `build/synth/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_fastadd_delaymap_ram256m_bb/area_audit.json`。正式 FakeRAM 总面积、官方 `perf_*` 和存储时序仍待验证。
- 同一 256 MiB 参数的平面逻辑重新导出并以 ASAP7 RVT TT 跑局部 OpenSTA；OpenSTA 2.0.17 的脚本改用其支持的 `-group_count` 和 `report_worst_slack`。16 扇出缓冲下最差已表征路径 slack **+46.1726 ps**，按 300 MHz 周期及 100 ps uncertainty 折算最小周期 **3287.1607 ps / Fmax 304.2139 MHz**，与旧 1 MiB 参数的最差逻辑路径到 4 位小数相同；`build/timing/p4_r32p64_lsq8_d1024_cp1_hash1_cmp4_fastadd_delaymap_ram256m_bb/timing_300mhz_buf16.rpt`。仍有 **139** 个无时序弧的存储边界，不能视为全芯片 300 MHz 证明。已知逻辑后剩余 Tier 3 存储/其他面积预算为 **9,385.245180 µm²**。
- **不能直接拼接上面 26,614.75 µm² 与 304.21 MHz 当作同一实际网表的面积/频率成绩。** STA 导出流程将 Yosys 产生的存储端口外围逻辑重新映射，导出网表已有 **28,221.485400 µm²** 已知标准单元面积；为得到上述局部时序又插入 **34,822** 个 BUFx8，按 ASAP7 Liberty **0.17496 µm²/个** 即 **6,092.457120 µm²**。因此该手工缓冲的**已知逻辑加缓冲面积约 34,313.942520 µm²**，离 36,000 上限仅 **1,686.057480 µm²**，仍未包括任何 FakeRAM、其他存储成本或物理实现开销。导出面积见同目录 `sta_logic_area.log`，缓冲数量见 `memory_boundaries.json`；这不是官方面积算法，但说明当前自制时序修复流不能作为 Tier 3 同时达标的证明。
- 官方 Tier 3 要求同一最终配置同时满足总面积 ≤36,000 µm²、`perf_*` 几何平均 IPC ≥1.0985、频率 ≥300 MHz；目前三项均未获得正式通过证据。
- 现有 CPU 测试平台虽然让 I/D 请求共享同一存储数组，但接口有独立请求队列；评测器端口与带宽应在取得官方文件后逐项对齐。

## 下一步

1. 针对当前紧凑候选完成正式面积计价；全 FF 面积不是 FakeRAM 计价。重点解决数据缓存和 ROB 的存储实现、端口合法性及组合逻辑成本。
2. 当前 LSQ8 在 16/8 内存并发模型下的代理 IPC 仅比 Tier 3 下限高约 0.000697；经过偏时序映射、分组比较和前缀进位，局部已表征逻辑路径过 300 MHz，但未表征的缓存/队列 SRAM 时序仍待正式模型验证。下一步优先获得/接入合法 FakeRAM 宏、存储时序和官方测试，并扩大 IPC 余量；现有非直通 D-cache 请求寄存级会显著降低 IPC，不可直接采用。
3. 用用户确认的 `CPU-2026-Benchmark` 六项及现有正确性程序集复测 32 位 MMIO 退出、所有指令和 256 MiB 地址空间（pi 仍冻结），冻结同一配置后提交参数敏感度与架构探索报告。

## 2026-09-26：测试集确认与缓冲成本优化

用户确认继续使用 benchmark 文件夹，保留 Tier 3 面积/频率门槛。256 MiB 当前配置的六项已全部通过，几何平均 IPC **1.0991968369**，高于 1.0985 约 **0.000697**；汇总 IPC 1.262038 不用于该门槛判断。当前仍待完成的是包括存储的面积与时序证据。

收到确认后，重新编译并运行六项 benchmark，结果再次全部通过，逐项周期数与前次相同；新报告 `build/cpu2026/benchmark_confirmed_20260926_report.json`。测试配置为 20 周期、共享 RAM、I/D outstanding=16/8、256 MiB、MMIO 返回码 0。评测器内存配置校验与计数器解析的 5 项单元测试通过。

在同一平面逻辑 JSON 上比较数据扇出缓冲，所有面积均包含显式缓冲，但不含 139 个未计价存储边界；频率仅为已表征标准单元路径的预布局估计。

| 缓冲策略 | 缓冲器数 | 已知逻辑加缓冲 µm² | 局部 Fmax MHz |
|---|---:|---:|---:|
| 全局 16 | 34,822 | 34,313.94252 | 304.21 |
| 全局 32 | 14,643 | 30,783.42468 | 255.75 |
| 全局 64 | 6,239 | 29,313.06084 | 203.32 |
| 全局 64 + 关键路径 16，第三轮 | 6,589 | 29,374.29684 | 251.80 |
| 全局 64 + 关键路径 8，第四轮 | 7,203 | 29,481.72228 | 259.81 |
| 全局 64 + 关键路径 4，第五轮 | 9,915 | 29,956.21380 | 259.63 |
| 全局 64 + 关键路径 8 + 32 位内总线扩展 | 8,708 | 29,745.03708 | 277.89 |
| 上述关键路径累计，第七轮 | 8,909 | 29,780.20404 | 287.60 |
| 上述关键路径累计，第九轮 | 9,700 | 29,918.59740 | 299.15 |
| 上述关键路径累计，第十轮 | 9,738 | 29,925.24588 | 301.64 |

前几轮定向缓冲降低了成本但未过 300 MHz；继续累计关键路径后，第十轮已过局部标准单元路径的 300 MHz 约束，见下文。`tools/audit_sta_area.py` 现可显式输出未完成的局部面积审计：总面积和 SRAM 仍为 null，默认完整验收模式继续拒绝未计价存储。`tools/test_sta_flow.py` 的 7 项测试通过；`make b05 a06` 通过，新增 ALU 随机比较/加减与 256 MiB 桥接边界测试纳入对应单元目标。

后续定向实验发现，单个位修复后，关键路径会转移到相似总线位；因此 `tools/yosys_json_to_sta_verilog.py` 增加可选 `--critical-bus-width`，仅从原始关键位一次扩展到限定宽度的总线，禁止递归别名扩张，默认关闭。新增边界/非递归测试后共 **8/8** STA 流测试通过。32 位内总线扩展版本 slack **-265.2072 ps**，局部 Fmax **277.89 MHz**，相对全局 16 节省已知标准单元面积约 **4,568.91 µm²**，但还差 300 MHz 且未计 SRAM，不能报成同时达标。相关结果位于同一 `fanout_sweep` 下的 `targeted64_8_v4`、`targeted64_4_v5`、`targeted64_8_bus32` 目录。

`tools/test_simulator_mmio.ps1` 的镜像地址限制改为默认 **256 MiB**（可参数化），显式核对完整 32 位返回并输出结构化报告。当前 256 MiB Verilator 可执行文件重新通过除 pi 外的 **17/17** 源码重编译仿真程序，20 周期统一 RAM、I/D outstanding=16/8；`pi_included=false`，报告 `build/cpu2026/simulator_mmio_ram256m_20260926_report.json`。其中 `expr` 的无符号返回 4294967098 对应有符号 -198，`naive` 为 350。这是源码重编译回归，不替代原始二进制覆盖或冻结的 pi 测试。

## 2026-09-26：低成本局部时序收敛与缓存端口合并

同一平面 JSON 的 `targeted64_8_bus32_v10` 已得到最差 slack **+18.0891 ps**、TNS/WNS 为 0，局部等效 Fmax **301.6369 MHz**。确切已计价逻辑加缓冲面积 **29,925.24588 µm²**：组合含缓冲 **27,167.29308**、时序 **2,757.95280**，其中显式缓冲 **1,703.76048**（9,738 个）。相对全局 16 的 34,313.94252，节省 **4,388.69664 µm²**。面积与频率对应同一缓冲网表，但仍有 **139 个未计价、未表征存储边界**；36,000 的剩余预算 **6,074.75412 µm²**。本轮未改 RTL，IPC 沿用已复测的同 RTL 配置 1.0991968369，不能宣称完成 SRAM 面积/全芯片时序验收。

缓存端口诊断通过 Yosys `memory_share` 合并同地址回填写入，1024 行两路 XOR D-cache：数据 **2R4W → 2R2W**，标签 **5R3W → 5R1W**；实际 store-hit 与回填写入可并发，不能继续当成单写端口。诊断前后 JSON 为 `build/dcache_ports_before.json`、`build/dcache_ports_after.json`。`synth/synth_bb.tcl` 加入可选 `ASAP7_CACHE_MEMORY_SHARE=1`，仅选择 `*/data_mem`、`*/tag_mem`，默认关闭，不处理 ROB/RS/LSQ 多写数组；记录合并前后 manifest。面积审计配置增加 `--cache-memory-share` 标记，避免与旧网表混用。

`tools/test_cache_memory_share.ps1` 对合并后发射的固定参数 Verilog 网表进行仿真，四种 16 行、1/2 路、hash=0/1 配置全部通过；每项核对端口数、容量、宽度、读端口不变，并运行 500 次掩码随机写读、脏行回写地址/数据检查及 1024 字全量回读。综合后内部函数被消除，原内部函数直接调用仅在 RTL 模式保留，外部脏回写检查两种模式均保留。原 RTL 的 8 组 hash/容量/prefetch 回归也通过。这不是完整 CPU 综合后等价性或单端口 SRAM 合法化证明。

当前使用相同 P4/ROB32/PRF64/RS16/LSQ8、256 MiB 参数正在跑开启 cache sharing 的偏时序综合：`build/synth/p4_r32p64_lsq8_d1024_ram256m_cache_share_bb`。在其面积/时序完成前，不能沿用旧网表的 301.64 MHz 当作该合并版本成绩。

第一次综合进程虽退出 0，但调用的 `-l synth.log` 与 Tcl 内部 `tee -o synth.log` 同名，使日志被两次写入而混杂，面积审计明确拒绝（找不到最后层级区段的顶层面积）；该次不作为面积证据。已用独立 `yosys_run.log` 重跑，Tcl 的 `synth.log` 只保留计价 stat。后续应审计新 stat 和合并后 manifest，再单独导出/跑时序；旧定向缓冲的报告索引不能直接套用新 JSON。

## 2026-09-26：单数据读口与合并范围校验

整机端口合并重跑已完成，历史宽选择器实验已计价逻辑 **26,783.022600 µm²**，比未合并版本增加 **168.267780 µm²**。但逐数组核对发现 `*/data_mem` 同时选择了 LSQ：写端口从 132 合并为 12；此前“未处理 LSQ”描述不正确。该次存储几何未变，但不能当作缓存限定实验；其 `area_audit.json` 已标记 **INVALID_SCOPE**，不计为当前候选的面积/时序成绩。当前选择器已改为带缓存模块名称后缀的四个精确模式。

`tools/audit_synth.py` 在 `--cache-memory-share=1` 时自动核对 `memory_manifest_before_share.il`：内存身份、几何不得改变，非缓存数组读写端口不得改变，缓存合并不得增加端口或降至零。新增 2 项单元测试通过；历史宽选择器 manifest 被该校验明确拒绝，能复现上述 LSQ 范围错误。

RTL 将命中读取与 miss 牺牲行快照共用一个 `request_data_line`，一次请求只能走其中一个分支；store-hit 与 refill 写入继续并发，不串行化。D-cache 数据数组变为 **1R**，再开启缓存限定的回写合并后为 **1R2W**。RTL 文件 SHA256 从 `D67D9046A6C65F14F1A67F8D4D54108C39D96EFB0F49C4665F6FC2CC3EDE1003` 更新为 `89F7124E6106A40FFFFCEAAEE1E9A05EBD9C7099C0BDABC1B808DF25EA3FF890`；前一份端口合并面积与 301.64 MHz 定向缓冲属于旧 RTL，不能拼到新版本。

新 Verilator 可执行文件 `build/vlt/dcache_1r_p4_r32p64_lsq8_ram256m/cpu_core_image_vlt.exe` 构建完成，六项 benchmark 全过，周期数/退休数逐项与旧版相同，几何平均 **1.0991968369**；报告 `build/cpu2026/dcache_1r_ram256m_report.json`。单读口版通过 4 种综合后缓存网表随机/脏回写测试（显式断言 RD_PORTS=1）、原 8 组缓存 RTL 回归、256 MiB 末地址脏回写测试以及除 pi 外 **17/17** 仿真源码回归；对应报告 `build/cpu2026/simulator_mmio_dcache1r_ram256m_report.json`。

新整机缓存限定综合正在独立目录 `build/synth/p4_r32p64_lsq8_ram256m_dcache1r_cache_share_scoped_bb` 运行；在其完整计价与新网表 STA 完成之前，不报告新 RTL 的面积/频率通过。`tools/test_final_basic.ps1` 新增 `-Executable` 模式，可把五项基础/半字/M-extension 程序用于同一个已冻结 Verilator 可执行文件，并要求完整 PASS 标志；硬件大小选项仅用于其 Icarus 构建模式。

已用该 `-Executable` 模式在单读口版验证 **5/5**：vmul、vvadd、accumulate、halfword_smoke、m_isa_smoke 均通过。加上六项 benchmark、17 项仿真源码程序与末 RAM 地址回写，当前单读口修改已有整机正确性与 IPC 对照证据；pi 仍按用户要求冻结，所有存储完整计价/时序仍未完成。

## 2026-09-26：单读口版面积/时序复测与精确导出

缓存限定、单数据读口版的完整综合已经结束，范围校验通过，只合并 D-cache data/tag 的写端口，非缓存数组端口未改。已知标准单元面积 **26,593.147260 µm²**，比旧未合并双读口版的 26,614.754820 少 **21.607560 µm²**。仍有 150 个存储实例未计价，合计为空；报告 `build/synth/p4_r32p64_lsq8_ram256m_dcache1r_cache_share_scoped_bb/area_audit.json`。配置 IPC 仍以单读口版六项复测的 **1.0991968369** 为证。

兼容行为 Verilog 重读路径导出后，未缓冲标准单元面积为 **28,173.094380 µm²**。同一新 JSON 的缓冲/时序结果如下；均非全芯片时序，仍有 139 个未表征存储边界。

| 缓冲策略 | 已知逻辑加缓冲 µm² | 最差 slack ps | 局部 Fmax MHz |
|---|---:|---:|---:|
| 全局 16 | 34,235.10846 | +46.1726 | 304.21 |
| 全局 64 | 29,259.42102 | -1828.7374 | 193.72 |
| 定向 8、128 位内总线、第一轮 | 29,746.85958 | -938.2446 | 234.11 |
| 定向 8、128 位内总线、第二轮 | 29,980.43118 | -359.1139 | 270.82 |

上述逻辑加缓冲计价与对应频率属于同一新网表。不能把 26,593.15 与 304.21 直接拼成实现面积/频率；全局 16 留给存储的预算只有 **1,764.89154 µm²**。

展开的兼容路径 manifest 有 **139 个逻辑存储实例、197,440 bit**，不是此前定义几何的 132 定义、187,064 bit；也不是合法映射后的 SRAM 宏数量/面积。`tools/estimate_local_sram_floor.py` 增加 `--boundary-manifest` 与显式同版本 `--logic-area-um2`，重复实例均计入，未知几何/计数不符拒绝；新增 2 项测试通过。用全局 16 的 known logic 计价、忽略端口适配等成本的本地 SRAM 情景为 **8,495.572815 µm²**（top3=7,132.302720，其余 38,720 bit 理想密度计价），不再沿用定义几何算出的 8,130.25；它仍不是严格下界或 FakeRAM 验收成绩。

发现兼容导出重读行为数组会重建外围逻辑，已知面积比源综合多 **1,579.947120 µm²**。`synth/synth_bb.tcl` 新增保存 `cpu_core_mapped.il`，`synth/export_sta_json.tcl` 优先读取该已映射 RTLIL，并不再次重建/ABC 映射；缺少该文件时保留兼容路径。`tools/test_exact_sta_export.py` 通过：小型实际 Yosys 网表的单元类型计数与存储参数在精确导出前后相同，兼容路径仍可用。真实 CPU 正在 `build/synth/p4_dcache1r_scoped_exact_ram256m_bb` 重新生成精确源；尚未证明真实整机精确导出的面积一致或频率，存储端口合法化/适配成本亦不能由这项导出修复豁免。

公开 [FakeRAM2.0](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/tools/FakeRAM2.0) 提供模型生成工具，旧 [示例配置](https://raw.githubusercontent.com/The-OpenROAD-Project/FakeRAM2.0/main/example_input_file.cfg) 明确标记示例参数不真实。已向用户确认能否采用公开生成器加本地 ASAP7 参数的披露估算口径，或必须使用课程指定配置；未将该示例的面积/时序假设当作成绩。本地 ASAP7 sram_0p0 也不能未经多端口合法化就当作所需 SRAM。初始盘点还发现 BTB tag/target 的每项同步清零产生很多写端口；利用 valid 位屏蔽未初始化内容可能是下一步存储合法化方向，目前未改 RTL 或宣称收益。

## 2026-09-26：精确 CPU 网表与定向缓冲复测完成

`p4_dcache1r_scoped_exact_ram256m_bb` 源综合完成，已知层级逻辑 26,593.147260 µm²；从映射 RTLIL 精确导出、flatten/opt_clean 后为 25,189.647300 µm²（时序 2,743.081200）。层级清理会移除未观察逻辑，差额不是 RTL 面积优化收益，也不能把 toy 的导出一致性当作完整 CPU 形式等价。

同一个精确 JSON：全局 fanout16 已计价逻辑含缓冲 30,858.351300，最差 slack +46.1726ps；全局64为 25,958.946420、-1773.7205ps。定向8/总线128的 v1/v2/v3/v4 依次为 26,433.088020/-938.2446ps、26,666.309700/-356.9176ps、26,704.276020/-3.1257ps、**26,730.520020/+31.3933ps**。v4 TNS/WNS=0，局部 Fmax **302.8523MHz**；组合含缓冲 23,987.438820、时序 2,743.081200，显式缓冲 1,540.872720（8,807 个）。面积与局部时序对应同一网表，尚有139个未计价、未表征存储边界，不能宣布完整频率或总面积通过。

精确 manifest 重新计数也是139逻辑存储实例、197,440bit。本地理想 SRAM 情景为8,495.572815µm²，与v4相加为35,226.092835，但忽略多端口/适配/时序，既非FakeRAM成绩也非严格下界；正式总面积继续为null。IPC沿用同RTL冻结可执行文件的六项复测1.0991968369，pi仍冻结。

导出工具新增 `--skip-maps`，同一JSON多轮扫描可省略重复TSV，不修改默认行为、网表或manifest；新增对照测试通过。`test_sta_flow.py`现9/9通过，`test_exact_sta_export.py`1/1通过。E盘仅余约0.09GB，本轮未删除用户测试或历史文件，未开启新大型整机编译。新报告草稿 `reports/current_candidate_2026-09-26.md` 汇总当前参数、逐项性能、同版本面积/时序和7组历史单变量敏感度，明确区分估算与验收。

## 2026-09-26：BTB payload 单写口实现与整机复测

完成BTB tag/target/kind仅valid复位屏蔽的payload去复位，并合并互斥的branch/JALR更新。整机清单三数组均 **1R66W→1R1W**、ABITS32→6，位容量不变；四份预测器共12个payload实例确认1R1W。valid仍1R65W，BHT全表reset仍保留，不宣称完整SRAM合法化。RTL SHA256 `2079F3DDBA5FBCA0F5B211D48BFFFE806D7D836858785B93EA7638597FE5F62E`。

`make a02`通过热复位/并发反馈/64项未知payload屏蔽/前后向冷分支/再分配测试。新`test_predictor_payload.py`2/2通过实际Yosys端口验证和4000周期独立随机参考模型。新整机C盘模型通过6/6benchmark、5/5基础半字M、17/17仿真源码（排除pi）、末RAM字地址回写。六项及17项周期/退休数/返回值逐项不变，IPC几何平均1.0991968369；报告`build/cpu2026/btb1w_ram256m_report.json`、`simulator_mmio_btb1w_ram256m_report.json`。二进制/源码配置哈希清单已保存`build/vlt/btb1w_p4_r32p64_lsq8_ram256m`，复制文件哈希一致。构建脚本新增输入前后哈希一致性检查和冻结manifest，实际PowerShell5.1构建验证通过。

新源综合C盘`cpu_btb1w_synth_20260926`完成，已知层级逻辑 **26,571.568860**（减少21.578400），精确flatten后 **25,170.168420**。同一新JSON重新定向缓冲v4：已计价逻辑含缓冲 **26,667.476100 µm²**，组合含缓冲23,924.394900、时序2,743.081200、缓冲1,497.307680（8,558个），最差slack **+57.1951ps**、TNS/WNS=0，局部Fmax **305.2374MHz**。相对前一候选定向v4少63.043920，包含重新选择缓冲，不能全归因RTL。证据副本保存`build/timing/btb1w_p4_r32p64_lsq8_ram256m_proof`；完整大网表仍在C盘临时生成目录，E盘不足未删除用户文件。

139逻辑存储实例/197,440bit不变；正式总面积/SRAM仍null，完整存储时序未验证。本地理想情景8495.572815与新逻辑相加35163.048915仅作算术情景，不是FakeRAM验收。分析取指查询发现每个有效PC均来自同一16byte行、低两位word index互异，完整四份预测表可探索四bank共享总容量；尚未实现。剩余valid/BHT复位端口、PRF8R4W、缓存和ROB/FQ的高端口数组仍需合法化。最新报告草稿明确区分前一冻结版与本轮工作树，未宣称Tier3完成。

仅删除本轮新建C盘`cpu_btb1w_20260926`目录的两份 `.gch` 预编译缓存，共261,117,798bytes（约249MiB）；删除前确认具体路径、同一目录及编译进程已结束，不递归删除。缓存可用构建脚本重建；未删除源码、可执行文件、网表、报告或用户历史文件。冻结可执行文件再次核对manifest SHA256一致。最终端口/随机参考2项、缓存合并审计2项、STA流程9项均再次通过。
