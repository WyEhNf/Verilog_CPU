# A-03 一级指令 Cache

`rv32_icache` 是 1 KiB、直接映射、16-byte line 的指令 Cache，共 64 项。索引为地址 `PC[9:4]`，tag 为 `PC[31:10]`。CPU 端请求携带原始 PC 和 frontend epoch，响应返回完整 128-bit line、原始 PC、line 地址、epoch 和错误位。

命中路径固定经过 request、compare、response 三个寄存阶段。请求在上升沿 N 被接受且下游不反压时，命中响应在 N+3 才可见；没有组合数据旁路。流水充满后，已命中且无冲突的请求可以每周期接受一项。响应被反压时，完整 payload 保持稳定并停止前级流水。

首版只允许一个 miss。为防止已经接受的请求因随后发现 miss 而丢失，入口在流水非空时只接受当前阵列可确认命中的请求；接受 cold/conflict miss 后立即保留 miss 资源，直到三级查找确认、MSHR 发出 line 请求并消费 refill。refill 即使属于旧 epoch 也会写入 Cache，便于后续正确路径复用；只有返回 Fetch Queue 的响应按 `current_epoch_i` 过滤。

主存端使用 H-03 的 line ready/valid 协议，transaction ID 低位携带 epoch。line 地址或 ID 不匹配会产生确定的错误响应，不写阵列。事件输出分别标记 CPU request、三级 lookup hit/miss、成功 refill 和入口 stall，供 A-06 统计模块计数。

验证入口 `make a03` 使用真实 50-cycle 双端口主存模型，覆盖 cold refill、严格三周期连续命中、little-endian line、同 set 冲突替换、越界错误、事件计数、完整响应 payload 反压稳定、redirect 后旧 hit 丢弃，以及旧 epoch miss 只 refill 不交付。
