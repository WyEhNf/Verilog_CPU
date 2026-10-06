# 完成通路模式

`COMPLETION_BYPASS`由student_top/cpu_core/backend传到完成网络的`BYPASS`参数。默认值仍为0。

| 模式 | 架构 | CDB能力 |
|---|---|---|
| 0 | 完成FIFO，功能单元握手后结果进入FIFO | 参数化CDB_WIDTH |
| 1 | 旧最小面积直接旁路，固定来源优先级 | 仅lane0，不能当作四路旁路 |
| 2 | 无完成FIFO的公平多路直接完成 | CDB_WIDTH=1/2/4，且不超过BE_WIDTH |

模式2依赖已有功能单元在valid且未ready期间保持结果。网络只锁每个背压lane的来源编号与完整ROB tag，不再保存宽payload副本；全部已锁来源预留后才能仲裁其它lane，避免重复消费同一来源。轮转仅在真实握手后推进，选择不依赖ready。

generation-stale/recovery-killed结果由`producer_target_live_i`取消并独立消费；全局reset/flush抑制握手且清除来源锁。`live_tag_valid_i`启用时还要求完整tag一致。模式2的FIFO entry_valid/tag与occupancy恒为0，因此FIFO专用kill_mask不代表来源kill-mask；调用者须提供逐来源live过滤。branch_pending预留最后有效CDB lane，其它lane仍可独立握手。

即时LSQ load结果必须把本次错误标志同拍送到ROB，不能只读取当拍尚未更新的load_error_mem。backend已针对模式2按完整tag匹配传递即时错误，包含恢复时的lane重映射。

验证命令：

```powershell
& tools/test_completion_direct.ps1
python tools/test_completion_equivalence.py --baseline D:/CPU2026AreaAudits/rob_parallel_tagbanks_i128_r32p48rs8_standard_20261001/source_snapshot/rtl/backend/rv32_completion_network.v --outdir D:/CPU2026Proofs/completion_legacy_modes_20261001
```

第一项运行24组直接网络测试和12组backend模式/宽度/store-retire整合测试；第二项对模式0/1进行完整顺序等价证明，不将改变延迟与仲裁的新模式2伪称逐周期等价。

模式2目前仍是面积探索候选，不是默认选定的性能优化。最新同资源严格IPC与LSQ容量对照见 `reports/direct_completion_2026-10-01.md`；完整面积和全SRAM频率必须独立测量，不沿用模式0结果。
