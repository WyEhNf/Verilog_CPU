# ER1 基线 IPC 测量前汇报

新目标：以 ER1 为基础，频率保持 >300 MHz，IPC≥1.1，含 SRAM 总面积≤36,000 μm²。

ER1 已测 Fmax 371.41820820 MHz、总面积 49638.890694 μm²。
当前必须确认 ER1 自身 IPC。仅构建一次原生 Verilator 5.020 CPU，运行六个课程性能基准：perf_median, perf_multiply, perf_qsort, perf_rsort, perf_towers, perf_vvadd。
复用该冻结版本的综合和 STA，命令使用 --reuse-synth，不再次综合、不运行额外定向测试或 19 程序回归。
本次性能基准仍检查官方答案；全套正确性尚未验证，不据此宣布功能或最终目标完成。

latency=10；分子为原 metrics.json dynamic_instructions，IPC 为六个程序的 GEOMEAN。
所有 RTL、官方脚本、程序、工具、计价和约束保持同一冻结身份；不使用 WSL。
独立后台运行，不修改当前 EU 主源码或其结果。后续优化候选独立保存，确认有可观结构收益后才统一测量。

冻结 manifest SHA256：9206002e2e07824ffd8a4db5a65be70c59f644d5fe87d1052456fbe602e34612。
原官方综合 report SHA256：a7f6017c1f5cd4e960c0d6798ddb57026c1fc5f415c082a29a2880f385d1e1af。
本报告生成时 CPU 构建和程序测量尚未开始；对话汇报后才调度。
