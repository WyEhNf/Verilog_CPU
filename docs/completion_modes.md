# 完成通路模式

`COMPLETION_BYPASS` 由 student_top/cpu_core/backend 传到完成网络的 `BYPASS` 参数。默认值仍为 0。

| 模式 | 架构 | CDB 能力 |
|---|---|---|
| 0 | 完成 FIFO，功能单元握手后结果进入 FIFO | 参数化 CDB_WIDTH |
| 1 | 旧最小面积直接旁路，固定来源优先级 | 仅通道 0，不能当作四路旁路 |
| 2 | 无完成 FIFO 的公平多路直接完成 | CDB_WIDTH=1/2/4，且不超过 BE_WIDTH |

模式 2 依赖已有功能单元在有效且未就绪期间保持结果。网络只锁定每个背压通道的来源编号与完整 ROB 标记，不再保存宽载荷副本；全部已锁来源预留后才能仲裁其它通道，避免重复消费同一来源。轮转仅在真实握手后推进，选择不依赖就绪信号。

代际失效或被恢复逻辑取消的结果由 `producer_target_live_i` 取消并独立消费；全局复位／冲刷抑制握手且清除来源锁。`live_tag_valid_i` 启用时还要求完整标记一致。模式 2 的 FIFO 条目有效位、标记与占用数恒为 0，因此 FIFO 专用取消掩码不代表来源取消掩码；调用者须提供逐来源的存活过滤。待处理分支预留最后一条有效 CDB 通道，其它通道仍可独立握手。

即时 LSQ 加载结果必须把本次错误标志同拍送到 ROB，不能只读取当拍尚未更新的 load_error_mem。后端已针对模式 2 按完整标记匹配传递即时错误，包含恢复时的通道重映射。

验证命令：

```powershell
& tools/test_completion_direct.ps1
python tools/test_completion_equivalence.py --baseline D:/CPU2026AreaAudits/rob_parallel_tagbanks_i128_r32p48rs8_standard_20261001/source_snapshot/rtl/backend/rv32_completion_network.v --outdir D:/CPU2026Proofs/completion_legacy_modes_20261001
```

第一项运行 24 组直接网络测试和 12 组后端模式／宽度／存储退休整合测试；第二项对模式 0/1 进行完整顺序等价证明，不将改变延迟与仲裁的新模式 2 伪称逐周期等价。

模式 2 目前仍是面积探索候选，不是默认选定的性能优化。最新同资源严格 IPC 与 LSQ 容量对照见 `reports/direct_completion_2026-10-01.md`；完整面积和全 SRAM 频率必须独立测量，不沿用模式 0 结果。
