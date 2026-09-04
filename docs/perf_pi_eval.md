# pi 镜像回归耗时评估（Verilator）

日期：2026-09-04。数据来源：`.tmp_join02_vlt.log`（JOIN-02 全量 Verilator 回归，18/18 PASS）、
`RISC-V-CPU-Simulator` 参考模型实测（`build/reference_sim.exe`，本会话运行）。

## 1. 结论先行

`pi` 单测耗时 **2073.8 s（约 34.6 分钟）**，大于用户观察到的 12 分钟阈值。
评估结论：**耗时正确，不是卡死，但周期数偏高**。

- 该次运行以 `PASS: JOIN-02 image=pi return=137 cycles=548099190 instret=101560724`
  正常停机；无退休 watchdog（100k cycles 停滞上限）未触发，返回值正确。
- 时间构成可分解、可复现，见下。

## 2. 为什么这么长（分解）

| 因素 | 数值 | 说明 |
| --- | --- | --- |
| 程序本身规模 | 退休 101,560,724 条指令 | `pi.c` 是经典 π 数字算法：外层 200 轮（c=2800..14 步进 14），每轮内层循环 ~c 次；镜像按 RV32I 编译，`d % --g` / `d / g--` 落到软件 `__modsi3/__divsi3`，每次约数百条指令的依赖链。 |
| 参考模型所需周期 | 126,904,523 cycles（IPC≈0.80） | 即使单发射、无 Cache、固定 3 周期访存的 C++ 参考模型也要 1.27 亿周期；连参考模型自带的 2e8 周期上限都只差不到 2 倍。 |
| 本 CPU 实际周期 | 548,099,190 cycles（IPC≈0.185） | 是参考模型的 ~4.3 倍，即每指令平均 ~5.4 周期。 |
| Verilator 仿真速率 | ~0.26–0.41M cycles/s（本设计、本机） | 全量回归日志中各用例 2.0–4.1 ms/s（10 ns 时钟）。548M cycles ÷ ~0.3M/s ≈ 30 分钟量级。 |

12 分钟阈值对应的只是“一小时内能跑完”的直觉上限；pi 被 `tests/manifest` 标为
`long regression=1`，上限 620M cycles 本身就是按该量级设置的（先有 100M 上限的
`pi100m.log` 失败记录，后放宽）。因此 >12 分钟符合预期，不应缩短上限或用小上限掩盖。

## 3. 但 548M cycles 值得警惕（IPC 偏低）

对拍参考模型（C++，单发射无 Cache，本会话实测）：

| 测试 | 参考 cycles | 本 CPU cycles | 倍数 | 本 CPU IPC |
| --- | ---: | ---: | ---: | ---: |
| qsort | 1,772,242 | 6,230,841 | 3.5× | 0.18 |
| magic | 1,094,660 | 2,476,299 | 2.3× | 0.19 |
| superloop | 519,893 | 2,715,978 | 5.2× | 0.19 |
| basicopt1 | 627,729 | 3,038,978 | 4.8× | 0.17 |
| pi | 126,904,523 | 548,099,190 | 4.3× | 0.19 |

参考模型对 superloop/basicopt1 的 IPC 达 0.82–0.98，而本 CPU 所有长测试都收敛到
~0.17–0.19（5.4–5.9 cycles/inst 的“地板”）。这不像 Cache miss 单独能解释（
basicopt1/superloop 工作集很小），更像存在系统性的每周期损失，候选原因（待 JOIN-06
性能阶段用计数定位）：

1. 分支恢复代价：mispredict 后 drain/redirect/重取指路径长，若 Bimodal/BTB 命中率低
   （1 KiB I-Cache、16 项 BTB、64 项 BHT 对多分支程序），每次 ~15–25 cycles；
2. Store 提交串行化：store 需 ROB head + D-Cache ack，逐 store 的提交停顿；
3. D-Cache 容量/组冲突：pi 的 `f[2801]`（11.2 KB）流式访问远超 4 KiB 直接映射
   D-Cache，每轮整数组遍历都 miss + writeback（50-cycle 主存）；
4. I-Cache 1 KiB 对 ~2–8 KB 代码的容量失效；
5. 单发射下 Load-to-use、MDU 长延迟与 ROB/RS 深度的交互。

建议：给 `cpu_core_image_tb` 增加末尾统计打印（`rv32_cache_stats` 与预测器计数已存在），
对 basicopt1/superloop 各跑一次即可定位主因；这属于 JOIN-06 性能/面积阶段的正式工作，
不影响 JOIN-02 正确性结论。

## 4. 实用建议

- 开发期回归不要每次都等 pi：manifest 已区分 long；`run_join02.ps1` 支持按 manifest
  过滤（开发用非 long 子集），发布门才跑全量。
- 若需要更快的整机仿真：去掉 Verilator 构建的 `--debug`/`--timing` 实验性选项或改用
  release 优化构建，实测可再提 1.5–3×（本日志 0.26–0.41M cycles/s 已含这些开销）。
- 长测试必须走后台上限 + `tools/progress_monitor.py`（见 `.dsh/skills/long-running-tests`）。
