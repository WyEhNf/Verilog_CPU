# 面积缩减方案（Area Reduction Plan）

> 历史说明（2026-09-16）：本文记录早期探索，面积口径和部分优先级已经过时。
> 当前决策以 `area_optimization_strategy_2026-09-08.md`、`STATUS.md` 及
> `tools/audit_synth.py` 的 `INCOMPLETE` 判定为准。尤其不能把切换 Yosys 版本、删除
> Cache 或旧的 28,497 µm² 汇总直接当作已证实收益；P1–P8 已完成的结构优化也不能
> 重复计数。

目标：把单发射乱序核的面积从当前 **28,497 µm²** 压到"合理乱序"水平，并向
instructions.md 的 1500–2000 µm² 期望靠拢，然后再做"面积翻倍→性能≥1.3×"的 Pareto。

## 0. 现状与基线

- 配置：FE=BE=1，PHYS_REGS=64，ROB_ENTRIES=32，LSQ_ENTRIES=8，I-Cache 1 KiB /
  D-Cache 4 KiB（阵列黑盒，仅统计控制逻辑）。
- 实测分模块面积（µm²，`stat -liberty`，ASAP7 RVT TT）：

| 模块 | 面积 | 占比 |
|---:|---:|---:|
| backend_joint（胶水） | 9,530 | 33% |
| ROB（含 checkpoint） | 3,881 | 14% |
| LSQ（控制） | 6,781 | 24% |
| PRF | 2,257 | 8% |
| multiplier | 1,578 | 6% |
| dcache 控制 | 1,085 | 4% |
| cache_stats | 772 | 3% |
| alu | 594 | 2% |
| rs | 557 | 2% |
| icache 控制 / divider / rename / predictor / fetch / bridge / 其余 | ~2,500 | 9% |
| **合计** | **28,497** | 100% |

> 注意（实测修正）：`checkpoint_mem`（1024 位 × 32 项）在综合流程里**并未展开成
> 触发器**——`memory_dff`/`opt` 只把小块存储换成寄存器，1024 位宽的 checkpoint 仍作为
> `$mem` 黑盒保留，`stat -liberty` 里面积为 0。所以它**不在这 28.5k 里**，也不是"1/3"。
> 真正的面积几乎全是控制逻辑 + 宽总线 mux（见下）。

---

## 1. 方案总览（按收益/优先级排序，实测修正后）

| 优先级 | 措施 | 预估节省 | 风险 |
|:--:|---|---:|---:|
| P1 | 配置瘦身 ROB32→16 / PRF64→48 / LSQ8→4 | **-3~5k** | 低 |
| P2 | 修复映射口径（换 Yosys 0.64 恢复 &nf） | **-20~30%** | 低 |
| P3 | backend_joint / LSQ 组合逻辑收敛 | **-3~6k** | 中 |
| P4 | 首轮去 Cache（连主存）+ MDU 精简 | **-3~4k** | 中高 |
| P5 | 结构微调（单发射下 PRF/完成网络端口精简） | **-1~2k** | 中 |
| P0' | checkpoint 宽度 1024→192（已做，见 §2） | -0.17k（逻辑），但对未来 SRAM 省 ~5× | 低 |

**预期轨迹**：28.5k → P1 ~24k → P3 ~19k → P4 ~15k → P2 ~11k。
（1500–2000 是理论下界，现实可达 ~10–15k；先到"合理乱序"，再谈 Pareto。）

---

## 2. P0' — checkpoint 宽度收敛（已做，属"SRAM 口径"收益，非逻辑面积）

**实测结论（先纠正原估计）**：
- 原以为 checkpoint 是最大单项（~9.5k）。但实测：把 `CHECKPOINT_WIDTH` 从 1024 收到
  **192**（只留 RAT，恢复时 free list 从 RAT+幸存 ROB 项确定性重建），面积只从
  28,496 → **28,324 µm²**（-173）。因为 checkpoint 在本流程里本来就是 `$mem` 黑盒，
  从未展开成触发器，没进 `stat -liberty` 面积。
- 该改动**仍然正确且值得保留**：① 功能正确（17/17 回归 PASS，branch recovery 全对）；
  ② 源码更干净；③ 未来若把 checkpoint 做成 SRAM 宏或展开成触发器，位宽已缩 5.3×
  （32768→6144 bit），对应 SRAM/触发器面积省 ~5×。

**真实面积大头（需重点攻关）**：`backend_joint 9.5k + lsq 6.8k + rob 3.9k + prf 2.3k`，
全部是**完成压缩 / 恢复 / store 转发扫描 / 提交分配 / 旁路 mux** 这类组合逻辑 + 宽总线，
不是存储。见 P1/P3。

---

## 3. P1 — 配置瘦身

把基线从"豪华"压到"够用"：

| 参数 | 现在 | 目标 | 说明 |
|---|---|---|---|
| ROB_ENTRIES | 32 | 16 | 存储+比较逻辑面积随深度近似线性 |
| PHYS_REGS | 64 | 48 | RAT/free-list/PRF 端口全跟着缩 |
| LSQ_ENTRIES | 8 | 4 | store-forwarding 扫描面积随深度平方级涨 |

注意：会掉一点 IPC，但 instructions.md 的 Pareto 正是"从达标面积起翻倍"，所以**先小、再按 1.3×/翻倍 逐级放大**，这才是正确顺序。

---

## 4. P2 — 修复映射口径（去掉 map 兜底的虚高）

- 根因已定位：本机 Yosys 0.68 自带 ABC 无法把 ASAP7 NLDM liberty 转成可用门级库，
  `&nf` 崩溃，只得用 `map + 自制 genlib` 兜底，面积偏大。
- **换 Yosys 0.64**（VerCore 同款，已被公开验证能跑 ASAP7 全流程），恢复官方
  `&nf` 映射，面积会再收紧（估 20–30%）。
- 配套：把 `synth/synth.tcl`、`synth/synth_bb.tcl` 的 abc 行从
  `-genlib … map` 切回 `-liberty …`（默认 `&nf`），并保留 `liberty2genlib.py` 作为备选。

---

## 5. P3 — backend_joint 胶水收敛

9,530 µm² 的完成压缩 + 恢复 + 总线打包是第二大头，逐项审查：

- completion 三路（ALU/MDU/LSQ）压缩逻辑：确认没有多余的数据拷贝；
- 三套 recovery kill-mask（rs / completion / producer）：能否合并/共用扫描；
- checkpoint 打包（P0 后自然瘦）；128-bit store-data 宽 mux 是否必要全宽。

目标：胶水从 9.5k 压到 ~6k。

---

## 6. P4 — 首轮去 Cache + MDU/预测器精简（可选，冲刺用）

instructions.md 原始要求**没有强制 Cache**（Cache 是 plan.md 自己加的）。首轮面积
冲刺可以：

- **去掉 I/D-Cache**，核心直接接 50 周期主存模型：省 dcache 控制 1,085 + icache
  控制 275 + cache_stats 772 ≈ **-2.1k**，并删除 cache 一致性/MSHR 复杂度。
- **multiplier 换迭代/移位加**（像 divider 一样 ~238 µm²）：省 ~1.3k，代价是 MUL
  延迟变大（单发射可接受）。
- 分支预测器（186）首轮可保留（很小，收益有限）。

---

## 7. P5 — 结构微调（单发射）

- PRF：单发射只需 2 读 1 写，检查是否按 `2*BE_WIDTH` 端口多造了端口。
- completion FIFO / CDB 多 lane：BE=1 时很多 lane 逻辑可退化。
- 用 `opt -full` / `abc9` 之类再压一轮面积。

---

## 8. 验证与风险控制（每一步都要）

1. **每步 RTL 改动后**：Icarus 冒烟 + B-08 等单测 + Verilator 18/18 回归（周期数
   应不变，或已知的合理变化），尤其 P0/P4 要重点验 branch recovery 与访存正确性。
2. **面积口径统一**：固定 `stat -liberty` + 同一 ASAP7 lib/角 + 同一映射工具，避免
   不同口径互相打架。
3. **分步提交**：每个 P 一个 commit，便于回滚与归因。
4. **性能不回归到 1.3× 线以下**：瘦身每步记录 IPC，Pareto 验收从最终基线开始。

---

## 9. 一句话结论

先砍 **checkpoint（P0，-8k）**，再**缩配置（P1）**，同时**换 Yosys 0.64 修映射（P2）**，
就能把 28.5k 压到 ~10–15k 的"合理单发射乱序"水平；1500–2000 是理论下界，需再叠加
P3/P4/P5 才可能逼近。执行顺序 = P0 → P1 → P2 → P3 → (P4 冲刺) → Pareto 扩宽。
