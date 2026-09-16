# 参数化 RV32IM 乱序 CPU 面积与 P/A 优化方案

更新日期：2026-09-08（Asia/Shanghai）

## 1. 文档目标与结论

本文依据根目录 `STATUS.md`、`instructions.md`、`plan.md`、当前 RTL、历史综合日志和公开的一手资料制定。本文只提出方案，没有运行测试、仿真或综合，也没有修改 RTL。所有面积收益均是待实验确认的设计假设，不能与旧日志中的数字直接相加。

项目的硬目标是：实现可综合的 Verilog-2005 RV32IM 乱序核；前端宽度和后端宽度独立支持 1/2/4；物理寄存器和 ROB 容量参数化；使用 Yosys 与 ASAP7 衡量面积和性能；单发射乱序核希望落在 1500–2000 µm² 量级；面积约翻倍时性能至少提高 1.3 倍，并争取连续满足三次。

当前最重要的判断如下：

1. 现在的整机仍只消费 frontend lane 0，`FE_WIDTH/BE_WIDTH=2/4` 只能 elaboration，不能作为多发射性能点。
2. 历史的 28,497 µm² 和 15,634 µm² 都不是可信的完整顶层面积：一部分 INV/BUF 面积疑似放大 16 倍，同时大量 `$mem*`、MUX、NOT、BUF、ZERO 面积没有计入。因此既不能据此宣布距离目标很远，也不能据此宣布某项优化已经节省多少面积。
3. 当前最有把握的 RTL 热点不是 Cache 本身，而是后端恢复时的一周期 free-list 重建、LSQ 的重复全表扫描和 128-bit 数据搬运、completion 的重复动态压缩、ROB/joint 重复元数据，以及不利于 SRAM 推断的复位和多端口结构。
4. 面积目标应先通过“准确计量 + 单发射结构瘦身”建立，再扩展真正的 BE=2/4。宽度、功能单元数量和队列容量必须独立参数化，不能把 BE=4 等同于复制四套 LSU/MDU。
5. “面积翻倍、性能提高 1.3 倍”并不意味着 P/A 不下降。每一级的 P/A 可以降至前一级的 0.65。连续三次需要至少四个有效配置点，端点面积约为 8 倍，性能至少为 2.197 倍。

## 2. 当前项目状态与约束

### 2.1 已有能力

根据 `STATUS.md`，项目已有可工作的单发射推测乱序闭环，包括 fetch queue、Bimodal/BTB、I/D Cache、rename/RAT/RRAT/free list、PRF、ROB、整数 RS、MDU RS、ALU/branch、乘除法、completion network、LSQ、memory bridge 和 50-cycle 双端口内存模型。历史版本已经跑通过 JOIN-01 和 18 个外部程序镜像；当前工作区还出现了 `accumulate`、`vvadd`、`vmul`、`m_isa_smoke` 与 JOIN-03 runner，但这些变化晚于 STATUS 记录，不能把旧回归结果自动归给当前源码。

### 2.2 必须保持的功能边界

- 指令集为 RV32IM。CSR、FENCE、浮点和 V 扩展不属于首轮目标。
- 实际验收镜像要求 `LB/LBU/LW/SB/SW`；半字接口应保留，完整 RV32IM 声明前还需覆盖 `LH/LHU/SH`。
- 向量加法和向量乘法是标量 C 循环，不要求 RISC-V V 扩展。
- store 只能在 ROB/LSQ head 获准后对 Cache 可见；HALT/error 必须在 ROB head 精确提交。
- 分支恢复必须保留分支自身和所有更老指令，杀死严格年轻项；旧 generation 的 load/MDU 结果不得污染新指令。
- 前端与后端宽度 1/2/4、PHYS_REGS、ROB_ENTRIES 必须真正参数化。通过编译但只使用 lane 0 不算满足要求。

### 2.3 当前源码中的扩宽阻塞项

- `rtl/cpu_core.v:237–239` 只读取 `fetch_valid[0]`，并且只给 lane 0 `ready`。
- `rtl/cpu_core.v:108–112` 只为 lane 0 生成预测信息。
- `rtl/backend/rv32_backend_joint.v` 的 trace/commit 主路径仍是标量，若干 BE 总线只把 lane 0 接入有效数据。
- `rtl/rv32m_mdu_reservation_station.v` 实例化乘法器和除法器时没有透传 `TAG_WIDTH`、`PHYS_ADDR_WIDTH`；PHYS=96 时 7-bit 地址可能接入默认 6-bit 端口。
- 当前 joint 的默认 tag 为 16 bit，而 ROB=64 时按 `3 + clog2(ROB) + 8` 需要 17 bit。tag 宽度应从 ROB 参数全链路派生，不能把截断当成面积节省。
- `rtl/rv32_rob.v` 能从多条 recovery candidate 中选择最老 tag，但恢复 PC 仍固定取 lane 0。
- 分支恢复会全局 flush MDU，可能清除更老、仍应存活的 M 指令；如果该指令已从 RS 移除，就无法重发。扩宽前应改为依据完整 ROB tag 选择性丢弃年轻结果。

## 3. 先修复面积和性能计量

面积优化必须以一致、完整、可复现的账本为前提。旧数据只能用来定位热点，不能用于最终达标判断。

### 3.1 历史面积报告的三个问题

第一，本地 ASAP7 Liberty 与同版本 1x LEF 的部分单元面积不一致：

| 单元 | 本地 Liberty area | 官方同版本 1x LEF 尺寸 | LEF 几何面积 | 比率 |
| --- | ---: | ---: | ---: | ---: |
| INVx1 | 0.69984 | 0.162 × 0.27 | 0.04374 µm² | 16× |
| BUFx2 | 1.1664 | 0.27 × 0.27 | 0.07290 µm² | 16× |
| DFFHQNx1 | 0.2916 | 1.08 × 0.27 | 0.29160 µm² | 1× |
| NAND2xp33 | 0.05832 | 0.216 × 0.27 | 0.05832 µm² | 1× |

这说明不能把整个报告统一除以 16。可能是特定类别的数据来源或缩放不一致，最终必须逐 cell 校验 Liberty/LEF，并在重新映射前修正统一库口径。

第二，历史网表仍含大量未知面积硬件。`build/synth/fe1_be1_p48_r16_rs4_lsq4_mul/synth.log` 记录了 104 个 memories、66,110 memory bits、11,337 个 `$_MUX_`、8,379 个 `$_NOT_` 以及未知的 BUF/ZERO。顶层 15,634.39644 µm² 只是“已知 area 单元之和”。只把 8,366 个 INVx1 按 LEF 面积重算，会得到 10,145.46384 µm²，但这只是账面演算，不是完整面积，也不是新综合结果。

第三，旧 28,497 µm² 来自逐个 module 报告的直接求和，不是可达实例树的顶层总面积。已经被优化掉的模块可能仍在独立 module stat 中出现，例如 cache statistics。模块定义面积不能直接相加当作芯片面积。

### 3.2 建立三套面积账本

每个配置同时输出三张账，禁止混用：

1. `A_logic`：完整映射后的非 SRAM 标准单元面积，用于比较控制逻辑和 datapath 优化。
2. `A_total`：`A_logic + 实际 SRAM 宏 + bank/复制/仲裁/写掩码/适配器`，这是 P/A 评分的主面积。
3. `A_ff_reference`：把所有数组显式 `memory_map` 成触发器、译码器和读 mux 后的参考实现。它用于检查遗漏和给出寄存器实现参考，不应再称当前 blackbox flow 的“上界”。

所有 `$mem*` 必须进入 manifest，逐项列出实例、深度、宽度、端口、同步/异步读、写掩码、读写冲突语义、候选实现和面积。不能把 cache、PRF、checkpoint、ROB、RS 或 decoder ROM 一律当成免费 SRAM；多读多写端口可能要求复制、bank 或标准单元实现。

### 3.3 修复综合流程

- 锁定同一版 ASAP7 Liberty、LEF、PVT、Yosys/ABC 和脚本 hash。
- 先处理 DFF 合法化和寄存器映射，再做最后一轮组合逻辑 ABC。当前脚本先 ABC、后 `dfflibmap`，后者产生的 QN 反相器可能留下大量未映射 `$_NOT_`。
- 最终网表只允许白名单中的标准单元和已登记 SRAM 宏；存在任何 generic cell 或 unknown-area cell 时，结果标记为 `INCOMPLETE`。
- `tools/liberty2genlib.py` 中乘 10000 是 ABC 成本整数化，不是物理面积缩放；`stat -liberty` 结果不可再除以 10000。
- Yosys 版本切换只是 A/B 诊断实验。旧方案中的“换 0.64 必省 20–30%”没有证据，不能作为面积优化收益。
- 如果没有合适 SRAM 宏，主结果应明确为估计值，并给出宏来源、几何、端口复制与外围开销。ASAP7 dummy SRAM 不能冒充经过 DRC/LVS 的可制造宏。

### 3.4 建立真实性能口径

性能必须分两种口径：

- 固定频率周期性能：`Speedup_cycles = Cycles_baseline / Cycles_config`。
- 考虑时序后的执行时间性能：`Speedup_time = Cycles_baseline × Tclk_baseline / (Cycles_config × Tclk_config)`。

当前 genlib 给所有 PIN 人工相同的延迟参数，不能把 ABC delay 当真实 ps 或 fmax。需要使用统一输入驱动、输出负载、PVT 和时钟约束做 STA，并把 SRAM latency 纳入关键路径。testbench 的 10 ns 时钟只是仿真驱动，不是 ASAP7 fmax。

## 4. 优化优先级总览

| 优先级 | 措施 | 主要收益来源 | 风险 | 适用阶段 |
| --- | --- | --- | --- | --- |
| P0 | 修复综合与面积账本 | 消除漏计、错计与错误决策 | 低 | 立即 |
| P1 | 删除 joint 的 completion 动态压缩 | 宽 mux、rank mux、重复搬运 | 低至中 | 单发射 |
| P1 | 收窄 LSQ 内部数据到 32-bit/4-byte mask | 状态位数、转发 mux、比较扇出 | 中 | 单发射 |
| P1 | 合并 LSQ 重复扫描 | 比较器、选择器、组合路径 | 中 | 单发射 |
| P1 | free-list bitmap 或串行 rollback | 恢复 prefix/动态压缩网络 | 中 | 单发射 |
| P2 | ROB/joint 元数据单一所有权 | 重复状态、宽端口和 mux | 中 | 单发射 |
| P2 | completion payload 分路并缩 FIFO | 128-bit 无效载荷与深缓冲 | 中 | 单发射 |
| P2 | PRF/RS 复位、age 和存储组织收敛 | DFF、reset mux、年龄比较 | 中 | 单发射 |
| P2 | 前端与 Cache 去串行握手 | 在较小面积下提高性能 | 中 | 单发射/BE2 |
| P3 | MDU 三档参数化 | 乘法面积与 vmul 性能折中 | 中 | Pareto |
| P3 | 真正 BE2、共享 LSU/MDU | 性能提高而避免全复制 | 高 | 扩宽 |
| P4 | BE4 分簇调度、banked Cache/PRF | 控制宽度增长与布线 | 高 | 扩宽后期 |

## 5. 后端结构优化

### 5.1 固定 completion producer 位置

`rv32_backend_joint.v` 当前把 ALU、MDU、LSQ 三个候选动态压缩为连续前缀，搬运 tag、phys、value、address、branch target、128-bit store data 和大量 flag，再通过 `alu_rank/mdu_rank/load_rank` 反解 ready。`rv32_completion_network.v` 实际已经能跳过 valid=0 的 source，并只对 fire 的 source 分配 FIFO 槽。

建议固定：source0=ALU、source1=MDU、source2=LSQ，直接连接 payload 和 ready。保留 ALU>MDU>LSQ 的固定优先级，或改为小型 round-robin，但删除外部动态压缩和 rank mux。该改动范围集中，应作为第一个 RTL 面积实验。

需要检查：无效或 target-live=false 的 source 是否会阻塞后续 source；recovery 当拍的 kill 与 ready/fire 优先级；FIFO 满时 payload 保持。不能仅凭静态阅读宣称已经等价。

### 5.2 重构 free list 与分支恢复

当前 checkpoint 已从 1024 bit/ROB 项压到 `32 × PAW` 的 RAT 状态，这是已经实现的收益，不能再次计数。真正的热点是恢复时的一周期组合逻辑：扫描 RAT、扫描全部幸存 ROB old-phys、构造 `PHYS_REGS` 位 reserved、遍历全部物理寄存器，并用运行时 prefix index 把空闲号压成宽 free-list 总线。

建议比较三种实现：

**方案 A：空闲位图，推荐作为单发射默认。**

- free list 使用 `PHYS_REGS` 位 bitmap，分配用分组优先编码器。
- BE=1 每拍只分配一项；BE=2/4 时用分层 priority + mask，避免全宽排序网络。
- commit 直接置回 old_phys bit；rename 清除 new_phys bit。
- 恢复可结合 branch allocation bitmap，或通过年轻 ROB 项的 new_phys 集合归还。

**方案 B：串行 ROB rollback，推荐面积最小档。**

- 从 ROB tail 向分支逐条逆序撤销：`RAT[rd] = old_phys`，归还 `new_phys`。
- 每拍处理 1 或 2 条，恢复期间暂停 rename；更老 completion 可继续进入受控缓冲。
- 可以取消每个 ROB 项的 RAT checkpoint，代价是误预测恢复增加若干周期。
- 性能损失可用 `ΔCPI ≈ mispredicts/instruction × 新增平均 rollback 周期` 估算。

**方案 C：独立 branch checkpoint 池，推荐性能档。**

- 仅为未决分支保存 RAT 和 branch allocation list，checkpoint 数量参数化为 2/4/8。
- ROB 只保存 checkpoint ID，池满时仅阻塞新分支。
- PHYS64 时 4 份 RAT 原始数据为 `4 × 32 × 6 = 768 bit`，远少于对 ROB32 每项保存 RAT 的 6144 bit；但这只是原始位数，不是已证明的 µm² 收益。

三种实现都必须处理：分支自身 rd、同一逻辑寄存器多次重命名、恢复期间更老提交释放的寄存器、重复释放、P0 恒为零、commit 与 recovery 同拍的优先级。

### 5.3 LSQ 内部数据宽度收敛

当前每个 LSQ 项保存 128-bit store data、16-bit mask、128-bit forward data 和 16-bit forward mask，总计 288 bit/项，仅这部分 LSQ8 就有 2304 raw bits。RV32 一条 store 最多提供 32 bit 数据和 4 byte mask。

建议：

- LSQ 内只存原始 32-bit store value、size、byte offset 和 4-bit byte mask。
- load forward state只保存目标 word 的 32-bit data 与 4-bit covered mask。
- 仅在 D-Cache 16-byte line 接口处按 `addr[3:0]` 扩展为 128-bit payload 和 16-bit mask。
- 多个更老 store 对一个 load 的覆盖按字节合并，最近 store 优先；保留部分覆盖、符号扩展和未知老 store 阻塞。

若从 288 bit/项收至约 72 bit/项，LSQ8 原始状态减少约 1728 bit。实际面积还包括对齐、比较和接口转换，必须综合确认。跨 word/line、misaligned 与 halfword 的契约要在实现前明确，不能暗中假设所有访问天然对齐。

### 5.4 LSQ 只扫描一次

当前 LSQ 至少有三处相近的 forwarding 计算：为每个候选 load 扫描老 store、选中后再次生成转发、时序过程又生成一次 forward data/mask；tag update 与 response match 也对所有 slot 重复比较。

建议分成两级：

1. 资格级只计算每个 load 是否被未知地址/未就绪重叠 store 阻塞，以及是否可发请求，不搬运完整数据。
2. 对最终选中的一个 load 计算一次 `selected_fwd_data/mask/complete`，同时供 fully-forwarded completion 和 Cache response merge 使用。

tag 中包含 slot 时，先用 slot 直接索引，再比较 valid+generation，避免对每个条目全 tag CAM。LSQ4/8 可以保留并行候选资格逻辑；LSQ16 再考虑拆成两拍或 load/store queue 分离。旧方案中“LSQ 总是平方增长”的说法应限定为当前多个候选各扫全部 store 的实现，并非所有 LSQ 的必然复杂度。

### 5.5 ROB 与 joint 元数据只保留一份

joint 当前另建了按 ROB 深度的 `rob_to_lsq`、phys、old_phys、rd、rd_we、pc、load_error、imm、prediction metadata、mem metadata 等 side table；ROB 自身也保存 PC、inst、rd、old/new phys、result、store 数据和 checkpoint。

建议先画出字段所有权表，再决定唯一 owner：

- commit/recovery 必需的 PC、inst、rd、old/new phys 由 ROB 保存并提供窄 lookup/commit 端口。
- imm 和执行期预测信息随 RS/branch entry 保存，非分支不存 pred_target。
- store payload 由 LSQ 保存，ROB 只存 LSQ tag、done/ack/error；提交时由 LSQ 提供 store trace。
- load error 可并入 ROB result status，不在 joint 复制一表。
- CommitRecord 与调试字段保留在可综合接口中，但可用明确的 `ENABLE_PERF_COUNTERS/ENABLE_DEBUG_TRACE` 配置比较生产核与观测核，报告时不能混用面积。

必须在后续网表层确认哪些重复字段真正存活；源码重复声明不等于综合后一定重复。也不要把所有字段塞进一个超多端口大数组，因为端口 mux 可能抵消存储收益。

### 5.6 收窄 ROB、RS 和恢复运算

- completion/recovery 从 tag 提取 slot，先进行一次 valid+generation 校验，再共享 one-hot write enable；避免 BE×ROB 全 tag 匹配后分别更新每个字段。
- ROB/RS/LSQ 容量为 2 的幂时，指针 wrap 使用参数位宽的截断加法。free-list 容量不是 2 的幂时使用一次比较减法。
- 用明确位宽的环形 distance 替代 Verilog `integer` 年龄差。Yosys 可能会优化 integer，但显式位宽有利于控制综合结果。
- RS 当前每项有两份 32-bit operand、两份完整 tag 和 32-bit age。把 age 改为 ROB slot/generation 或较窄的环形序号；不能简单截短全局 counter 导致回绕乱序。
- 预计算一次 branch younger mask，供 RS、completion、producer、LSQ 使用；注意共享大扇出与局部复制之间的物理权衡。

### 5.7 PRF 和 RS 组织

当前 PRF 在 BE=1 已经是 2R1W，因此“把单发射 PRF 改成 2R1W”没有新增收益。优先做以下改动：

- 数据阵列与 ready scoreboard 分离；reset 只清 ready/valid 和 P0，不清所有 data bits，减少 reset mux/布线并改善 memory inference。
- PHYS48 与 PHYS64 的 PAW 都是 6，PHYS64→48 只减少条目，不减少地址/tag 位宽；容量收益应实测。
- 小 PRF 先比较标准单元局部写使能与实际 2R1W 宏/复制方案；异步多读口不能按单端口 SRAM 面积估算。
- BE=2/4 再探索 tag-only RS：RS 只存 phys tag/ready，issue 后读 PRF。它能减少 RS 数据存储和宽 wakeup，但会增加 PRF 读口、一级 latency、仲裁失败和重发，必须作为完整架构 A/B。
- 可在宽核中把 source wakeup 主总线改用 phys tag，ROB generation 校验集中在 completion 入口；仍需保证被复用的物理号不会被旧结果误唤醒。

### 5.8 completion FIFO 与数据平面分路

completion FIFO 当前深度固定 16，每项携带普通写回数据外，还携带 address、branch target、128-bit store data 和多种 flag。建议：

- 增加 `COMPLETION_DEPTH` 参数，BE1 探索 4/8/16，BE2 探索 8/16。
- 通用写回只保存 `tag + phys + 32-bit value + rd_we + error`。
- branch metadata 直接送 branch/ROB 小缓冲；store metadata 直接送 LSQ/ROB 小缓冲，不随每个 ALU/MUL/load 结果占 128 bit。
- 比较“小全局 FIFO”和“每 source 1–2 项 skid buffer + BE 宽仲裁”。后者更易控制多写口，但要避免 ALU 持续流量使 load/MDU 饥饿。
- 支持 dequeue 当拍回收空间给 enqueue，减小 FIFO 后不牺牲吞吐；明确同槽读写语义。

## 6. 执行单元优化

### 6.1 ALU/AGU 数据路径

当前 ALU 输出寄存器无条件保存 128-bit store data，普通 ALU 和 branch 也携带这条宽路径。建议把 ALU/branch result 与 AGU/store payload 分路：

- ALU/branch：value、target、taken、redirect、tag。
- AGU/load：address、size、unsigned、tag。
- AGU/store：address、32-bit rs2 value、4-bit mask、tag。

加法资源可在面积档中共享：PC+4、branch target、AGU address 和 integer ADD/SUB 通过分时或复用同一 32-bit adder，但要用 STA 检查 mux 是否把关键路径拉长。BE1 可先尝试 ALU 与 AGU 共享；BE2 性能档应至少保留一个独立 AGU，避免 load/store 与普通 ALU 互相阻塞。

移位器是另一个潜在热点。比较完整 barrel shifter 与每拍 1/2/4/8 bit 的迭代 shifter；但 RV32I 循环和地址代码中的 shift 频率需先统计。面积档可迭代，性能档保留单周期或两级 5-stage mux shifter。

### 6.2 乘法器三档设计

当前 `rv32m_multiplier.v` 是 32 行 magnitude partial products + CSA/Wallace reduction，再做符号绝对值和末端修正；它不是 plan 所写的 radix-4 Booth。建议把 MDU 实现独立参数化：

1. `MUL_IMPL=ITERATIVE`：radix-2 或 radix-4 shift-add，16/32 拍，最小面积。
2. `MUL_IMPL=17X17`：参考 Ibex fast multiplier，用 17×17 分解和 34-bit MAC，MUL 约 3 拍、MULH 约 4 拍，作为面积/性能中档。
3. `MUL_IMPL=BOOTH_TREE`：radix-4 Booth 约 16 个 partial products，CSA tree + final CPA，面向吞吐档。

必须用 vmul 和 M 指令 smoke 衡量。不能因为“单发射”就认定 32-cycle MUL 可接受；vmul 正是要求中的重要程序。MUL low 结果可利用低位不需要完整 64-bit 高半部分的剪枝，但 MULH/MULHSU/MULHU 仍要求完整高位路径，是否共享硬件由 workload 决定。

### 6.3 除法器

现有 32-step restoring divider 面积通常不是首要热点。可做低风险收敛：删除未使用状态，如经审计确认 `signed_mode_reg/original_b_reg` 不参与结果；异常路径在 request 时直接记录最终值并缩短活动周期；乘除法共享输入/输出缓冲和 MDU 内部 adder，但不能未经仲裁直接复用主 ALU。

MDU wrapper 应支持 pending 完成当拍被下游接受时，同时接收下一条 MDU 指令，避免一个无意义气泡。更老 MDU 在 branch recovery 时必须继续运行或保留可重发信息。

## 7. 前端、预测器与 Cache 优化

### 7.1 先提升现有小面积结构的有效吞吐

历史 `pi` 结果约 548,099,190 cycles / 101,560,724 instret，IPC≈0.185；basicopt1、superloop 等小工作集也约 0.17–0.19 IPC。这说明有系统性串行化，单纯缩队列会进一步损害 P/A。

前端 `req_pending_reg` 只允许一个 I-Cache request 在途；D-Cache `ready` 要求 pipeline empty 和 outputs free，使“三周期流水”实际上难以做到每拍接收。优化顺序：

- I-Cache hit 路径允许新请求逐拍进入，miss 时才由 MSHR 阻塞冲突 line。
- D-Cache hit pipeline 支持每拍一个请求，response 使用 skid buffer；miss 时只阻塞无法命中的请求。
- store hit ack 与 load response 分开，避免两个输出必须同时为空才接收新请求。
- 主存仍为单 outstanding 时，不必先实现复杂 non-blocking Cache；先消除 hit 路径的全流水 drain。

这些改动可能略增控制逻辑，但能显著提高小核性能，使随后缩小 ROB/RS/LSQ 更容易满足 P/A。

### 7.2 预测器

当前 64-entry bimodal + 16-entry BTB 本身不大，不建议为了面积首先删除。更值得做的是：

- 预测器 query 真正按 FE lane 或每个 fetch word bank 组织，不能只预测 lane 0。
- 统计 branch frequency、BTB hit、direction accuracy、JALR miss 和恢复代价。
- 面积档可保留小 bimodal/BTB；性能档增加 BTB entries 或小 RAS，并由 speedup/area 决定。
- 不应直接照搬 TAGE 等大核预测器。SonicBOOM 的小 uBTB 和 bank mapping 是启发，不是当前小核的默认答案。

### 7.3 Cache 容量与组织

直接删除 Cache 会让所有访问承担固定 50-cycle 主存延迟，可能严重破坏 P/A，因此仅作为面积下界消融，不作为首选交付方案。

建议参数化：I-Cache 0.5/1/2 KiB，D-Cache 1/2/4/8 KiB，line 固定 16 bytes；先扫容量再扫相联度。`pi` 的工作数据约 11.2 KiB，4 KiB direct-mapped 容量不足，扩大 D-Cache 可能用较小面积换较大性能。另一方面，短测试可能更受串行 hit pipeline 影响。

BE=2 后参考 SonicBOOM 使用偶/奇双 bank、每 bank 1R1W SRAM 支持不同 bank 的双请求；同 bank 冲突重放。不能把它当免费双口，因为地址 CAM、bank 仲裁和 replay 也占面积。BE=1 不需要提前承担这些结构。

### 7.4 性能计数器与测试环境

当前 cache stats 输出悬空，综合可能已把整个模块删除。最终性能计数器应有两种模式：

- `SYNTH_PROFILE=0`：生产面积配置，计数器不实例化。
- `SYNTH_PROFILE=1`：性能分析配置，导出计数器，面积单独报告。

必须采集：frontend empty/full stall、ROB/RS/LSQ/PRF 满、无 ready issue、FU busy、WB/FIFO 冲突、load 被未知 store 阻塞、store commit 等待、mispredict/rollback 周期、I/D hit/miss/writeback、各 lane issue/commit 利用率。测试环境的 memory model、monitor、trace checker 不进入 CPU 综合层次。

## 8. 真正的多发射扩展

### 8.1 宽度与资源数量解耦

建议新增独立参数：

- `FE_WIDTH`：1/2/4。
- `RENAME_WIDTH`、`DISPATCH_WIDTH`、`COMMIT_WIDTH`：默认等于 BE，但可独立实验。
- `INT_ISSUE_WIDTH`：1/2/4。
- `LSU_COUNT`：1/2。
- `MUL_COUNT`、`DIV_COUNT`：通常 1，只有数据证明需要才复制。
- `CDB_WIDTH/PRF_WRITE_PORTS`：1/2/4，可小于 producer 总数并用 completion buffer 吸收冲突。

BE=2 推荐首个真实扩宽点：2-way rename/dispatch/commit、2 个整数/branch issue、1 LSU、1 MUL、1 DIV、2 CDB/write ports。BE=4 可先做 4-way rename/commit、2 或 4 INT、2 LSU banks、1 MUL、1 DIV、2 或 3 write ports，而不是四倍复制所有结构。

### 8.2 同 bundle 依赖与资源分配

- rename lane i 必须看到本 bundle 更早 lane 的新映射，覆盖 RAW/WAW。
- free bitmap 需要一次选出连续有效前缀所需的 0–BE 个物理寄存器。
- ROB/RS/LSQ 分配只接受连续 valid prefix；资源不足时要么缩短接受前缀，要么整 bundle 停顿，规则需全链一致。
- 同拍多个 branch 的 checkpoint 分配、最老 mispredict 选择、恢复 PC lane 选择必须明确。
- commit `instret` 增加实际 valid commit lane 数，不再固定加 1。

### 8.3 BE4 的复杂度控制

宽发射的主要面积增长来自 rename bypass、wakeup/select、PRF 端口和 bypass network，而不是 ALU 本体。参考 Palacharla 的复杂度分析，BE4 可探索 2×2 调度簇：

- 两个小 RS，各自连接局部 ALU 和局部 bypass。
- 相关指令尽量分到同簇；跨簇结果增加一拍或走窄 crossbar。
- LSU/MDU 作为共享资源，通过窄仲裁连接。
- 比较复制少量 PRF/bank 与全连接多端口 PRF 的总面积。

这属于 BE2 正确后再做的高风险优化。依赖 FIFO、RegCache、operand collector 等大核技巧只有在实际 PRF/wakeup 成为热点时才引入。

## 9. 参数分配与 Pareto 配置

### 9.1 单发射容量候选

先围绕以下组合做非笛卡尔筛选：

| 档位 | FE/BE | PHYS | ROB | INT RS | LSQ | Completion | Checkpoint | MUL |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S0 面积下界 | 1/1 | 40或48 | 8或16 | 4 | 4 | 4 | rollback/2 | iterative |
| S1 推荐基线 | 1/1 | 48 | 16 | 4或8 | 4 | 8 | bitmap+4 | 17×17 |
| S2 深窗口 | 1/1 | 64 | 32 | 8 | 8 | 8或16 | bitmap+4/8 | 17×17或tree |

PHYS 必须至少 33；40/48 是否足够由 free-list stall 和 mispredict recovery 压力决定。容量不要同时全部翻倍：先做 ROB–PHYS 配对扫描，再固定二者扫描 RS/LSQ。

### 9.2 四个评分档位

三次“约翻倍”需要四个点。建议在面积口径修复后，从实际非支配点选择，而不是预先硬指定恰好 1/2/4 issue：

| 评分点 | 目标相对面积 | 最低相对性能 | 可能结构 |
| --- | ---: | ---: | --- |
| P0 | 1.0× | 1.000× | 紧凑 BE1 |
| P1 | 约 2.0× | ≥1.300× | BE1 深窗口/快 MDU/Cache 优化，或紧凑 BE2 |
| P2 | 约 4.0× | ≥1.690× | 真 BE2 + 合理容量 + 2-bank D$ |
| P3 | 约 8.0× | ≥2.197× | BE4/分簇 + 更强前端/内存 |

原要求没有定义“约翻倍”的容差。建议在首次正式测量前冻结为 `1.8× ≤ A_next/A_prev ≤ 2.2×`；性能按几何平均执行时间 speedup，所有配置使用同一程序权重。如课程评分另有明确口径，以课程口径覆盖此建议。

### 9.3 P/A 报告公式

对配置 i：

```text
Perf_i          = 1 / geometric_mean(runtime_i,b)
Speedup_i       = Perf_i / Perf_0
AreaNorm_i      = A_total_i / A_total_0
PAnorm_i        = Speedup_i / AreaNorm_i
StepSpeedup_i   = Perf_i / Perf_(i-1)
StepArea_i      = A_total_i / A_total_(i-1)
```

每一级要求 `StepArea≈2` 且 `StepSpeedup≥1.3`。同时报告 `PAnorm`，但不额外要求它不下降，因为该门槛本身允许效率降至 0.65。

## 10. 实验与报告设计

虽然本文不运行测试，但实施优化时应使用以下流程，避免面积数字失真。

### 10.1 单一配置源

建立 machine-readable config，统一驱动 RTL elaboration、testbench、综合和报告目录，至少包括：FE/BE、rename/commit/issue width、PHYS/ROB/RS/LSQ、checkpoint 数、completion depth、Cache 几何、FU 数量、MDU mode、profile/debug mode、RTL hash、tool/library hash、程序镜像 hash。

当前 testbench 硬编码 FE=BE=1、PHYS=48、ROB=16、RS=4、LSQ=4，而 Makefile 默认仍是 PHYS64/ROB32/RS8/LSQ8；这种不一致必须消除，否则性能点和面积点不是同一 CPU。

### 10.2 分阶段筛选

1. 流程阶段：固定一份 RTL，修复库、映射和面积账本，禁止把工具变化算成架构收益。
2. 结构阶段：固定 FE=BE=1，每次只改变 completion 接线、LSQ 宽度、recovery、metadata、MDU 中的一项。
3. 容量阶段：对 ROB–PHYS、RS、LSQ 做成对扫描，保留 Pareto 非支配点。
4. 扩宽阶段：真正完成多 lane 后扫描 FE×BE，再围绕每个宽度调容量和 FU 数量。
5. 最终阶段：四个评分点跑完整正确性、性能和 PPA 流程。

### 10.3 程序集

- 完整保留 18 个实际镜像，最终候选必须包含长程序 `pi`。
- JOIN-03 使用 accumulate、vvadd、vmul、m_isa_smoke，固定编译选项、checksum、objdump 与退休 M opcode 证据。
- 筛选期可使用覆盖相同压力的短程序，但不得把筛选子集冒充最终结果。
- 参考 C++ 模型只用于架构退休对拍；其 3-cycle memory 不能用于本 CPU 的性能 speedup。

### 10.4 每项优化的记录模板

```text
变更 ID / 源码 hash / 参数 / 工具与库 hash
功能状态：PASS/FAIL/NOT RUN
A_logic / SRAM / adapter / A_total / unknown cell count
STA: worst path / Tclk / fmax / constraint violations
各程序 cycles / instret / IPC / runtime / speedup
stall 与 occupancy 计数
相对上一点的 step area / step speedup / P/A
结论：保留、回退、仅用于面积档、仅用于性能档
```

## 11. 推荐实施顺序

### 阶段 A：先得到可信基线

1. 统一 Liberty/LEF 面积，逐 cell 检查 INV/BUF 异常。
2. 调整 dfflibmap/ABC 顺序，消除 generic MUX/NOT/BUF/ZERO。
3. 为所有 `$mem` 建立 manifest，并形成 `A_logic/A_total/A_ff_reference`。
4. 建立真实 STA 和单一配置清单。

退出条件：顶层无未知面积单元；面积、参数、性能对应同一源码和配置。

### 阶段 B：单发射低风险瘦身

1. completion producer 固定接线，删除动态压缩和 rank mux。
2. 显式派生 TAG/PAW，修复 MDU 参数透传和 recovery lane PC。
3. 收窄指针、age、slot 和 distance 计算。
4. PRF/各数组只 reset valid/ready，不 reset data。

退出条件：结构收益可以逐项归因，没有依赖旧日志估算。

### 阶段 C：单发射主要热点

1. LSQ 32-bit/4-mask 化并合并转发扫描。
2. 选择 free bitmap、rollback 或 checkpoint pool；建议 S0=rollback，S1/S2=bitmap+checkpoint pool。
3. ROB/joint metadata 单一所有权。
4. completion payload 分路并筛选 FIFO 深度。
5. 消除 I/D Cache hit pipeline 的全 drain 串行化。

退出条件：得到满足功能门的最小 `A_total` 单发射核，并记录各类 stall。

### 阶段 D：MDU 与容量 Pareto

1. 实现 iterative、17×17、Booth-tree 三档乘法器。
2. 扫 ROB–PHYS、RS、LSQ、completion、Cache 容量。
3. 用 vmul、pi、branch-heavy、memory-heavy 程序选非支配点。

退出条件：确定 P0 和可能的 P1，不预设 1500–2000 µm² 一定可达或不可达。

### 阶段 E：真正 BE2/BE4

1. 完成 packed multi-lane frontend/decode/rename/dispatch/commit。
2. BE2 使用共享 LSU/MUL/DIV 与 2 CDB，先闭正确性和 P/A。
3. 按数据决定 BE4 是否采用 2×2 分簇、banked D-Cache、PRF bank/复制。
4. 从所有非支配点选择 P0/P1/P2/P3，检查每级 1.3× 门槛。

## 12. 不推荐的捷径

- 不把删除 Cache 作为首选面积方案；50-cycle memory 下性能代价可能远大于面积收益。
- 不直接删除 store queue 或照搬 NoSQ。NoSQ 依赖 memory dependence prediction、speculative bypass、load replay 和验证结构，论文预测器规模对本项目 4–8 项 LSQ 可能得不偿失。
- 不把 CVA6 的“顺序发射、乱序完成”替代本项目要求的乱序 issue；可借鉴 transaction ID 和 scoreboard 接口。
- 不宣称换 Yosys 版本本身是硬件面积优化。
- 不按 raw bit 数直接换算 SRAM/触发器面积，不忽略端口和外围。
- 不为省 tag 位宽破坏 generation 保护、精确恢复和 PHYS/ROB 参数范围。
- 不让 BE4 机械复制四个 MUL、DIV、LSU 和全连接 bypass。
- 不把 profiling/testbench 硬件混入评分面积，也不把它优化掉后仍加到顶层。

## 13. 主要风险与控制

| 风险 | 可能后果 | 控制措施 |
| --- | --- | --- |
| rollback/free bitmap 错误释放 | 两条指令获得同一 phys，静默错误 | 明确 commit/recovery 优先级；完整 generation；分支自身映射保留 |
| LSQ 32-bit 化破坏部分覆盖 | LB/LW forwarding 错误 | byte mask 合并；最近 store 优先；跨界契约固定 |
| 减 PRF 端口但无 replay | 丢失已唤醒指令 | 仲裁失败必须 cancel/reissue 或缓冲 |
| completion FIFO 过小 | FU 反压、吞吐下降、死锁 | source skid；同拍 pop/push；公平仲裁 |
| 共享 adder/AGU | 关键路径变长或结构冲突 | 用 STA 和 stall 计数决策；性能档保留独立 AGU |
| 多发射 tag/PC lane 错配 | 错误恢复到 lane 0 | recovery tag、PC、checkpoint ID 成组传递 |
| 分支 flush 清更老 MDU | 指令永久丢失 | 完整 tag 选择性 kill；或保留重发记录 |
| SRAM 宏端口不匹配 | 面积低估或功能语义改变 | 把 bank/复制/replay/adapter 全计入 A_total |
| 工具变化混入 RTL 收益 | Pareto 结论无效 | 固定 flow 后再比较架构；工具 A/B 单独报告 |

## 14. 业界思路及适用边界

1. [BOOM Rename Stage](https://docs.boom-core.org/en/latest/sections/rename-stage.html)：RAT snapshot、committed map、branch allocation list 和 ROB unwind，为本项目 checkpoint pool/rollback/free bitmap 提供直接参考。
2. [BOOM Register Files and Bypass](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)：动态仲裁可以减少 RF 端口，但失败指令必须取消和重发；不能只砍端口。
3. [BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)：分离 issue queue、age ordering、fast/slow wakeup；支持本项目比较 data-less RS 与不搬移的年龄选择。
4. [Complexity-Effective Superscalar Processors](https://ftp.cs.wisc.edu/sohi/papers/1997/isca.complexity.pdf)：rename、wakeup/select、bypass 随宽度增长，是 BE4 分簇而非全连接复制的理论依据。
5. [SonicBOOM](https://carrv.github.io/2020/papers/CARRV2020_paper_15_Zhao.pdf)：双 bank 1R1W D-Cache、小 uBTB 等适合宽核；data-less RS 并不是本文特有贡献。
6. [香山昆明湖 V2 DataPath](https://docs.xiangshan.cc/projects/design/en/kunminghu-v2/backend/DataPath/DataPath/)：RF 端口仲裁、失败重发和 RegCache 可作为 BE4 后期选项，小 PRF 不应直接照搬。
7. [Ibex Multiplier/Divider](https://ibex-core.readthedocs.io/en/latest/03_reference/instruction_decode_execute.html)：slow/fast/single-cycle 三档，尤其 17×17 + 34-bit MAC 是本项目乘法中档的重要参考。
8. [CVA6 Issue Stage](https://cva6.readthedocs.io/en/latest/03_cva6_design/issue_stage.html)：借鉴窄 transaction ID 与结果定位；它是顺序发射，不能替代本项目 OoO issue。
9. [NoSQ 原论文](https://acg.cis.upenn.edu/papers/micro06_NoSQ.pdf)：说明删除 SQ 需要额外预测、重执行和验证机制，因此本项目优先减少重复扫描而非删除 SQ。
10. [Yosys Memory Handling](https://yosyshq.readthedocs.io/projects/yosys/en/latest/using_yosys/synthesis/memory.html)：`memory -nomap` 会保留 memory，`memory_map` 才展开为逻辑；未映射 memory 面积为零不代表硬件免费。
11. [ASAP7 1X/4X 说明](https://github.com/The-OpenROAD-Project/OpenROAD/discussions/2868)：4X 是线性尺寸缩放，面积涉及平方关系；本项目仍需逐 cell 核查，不能对总数盲目除 16。
12. [ASAP7 官方 1x LEF](https://github.com/The-OpenROAD-Project/asap7sc7p5t_27/blob/main/LEF/asap7sc7p5t_27_R_1x_201211.lef)：用于核对当前 Liberty 中 INV/BUF/DFF/逻辑门面积口径。

## 15. 最终建议

近期最优路线不是继续基于旧 28.5k 数字做百分比承诺，而是先把面积账本闭环，然后连续完成四项高价值改变：固定 completion source 接线、LSQ 32-bit 化并复用一次扫描、用 bitmap/rollback 替代一周期 free-list 压缩、合并 ROB/joint 元数据。并行改善 Cache hit 路径串行化和 MDU pop/push，使紧凑单发射核仍有足够性能。

之后以真正的 BE2 为主要性能扩展点，共享一个 LSU、MUL 和 DIV，避免功能单元随宽度机械复制。只有当 BE2 的统计证明 wakeup、PRF 或 D-Cache bank 冲突成为瓶颈时，再为 BE4 引入分簇调度、banked Cache 或 operand collection。最终用完整 `A_total` 与 STA 执行时间选出四个非支配点，验证三次约 2× 面积对应至少 1.3× 的逐级性能提升。
