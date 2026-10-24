# A-04 取指前端

`rv32_fetch_frontend` 负责取指 PC、前端 epoch 和可参数化的取指队列。它每次接收一个来自指令缓存的行响应，最多输出 `FE_WIDTH` 个 `FetchPacket` 条目，且有效条目必须组成连续前缀。包字段沿用 `rv32im_defs.vh` 中冻结的顺序：`{epoch, btb_hit, pred_kind, pred_target, pred_taken, inst, pc}`。

预测元数据随指令缓存响应逐条提供，使前端可独立测试，同时允许在集成边界接入 A-02 预测器。遇到第一条预测跳转指令时，截断当前指令束，并将其目标作为下一取指 PC。缓存行尾部只输出该行中剩余的字。

`redirect_valid_i` 的优先级高于普通队列活动：清除旧 epoch 的已排队包，安装给定的 PC 和 epoch，并允许丢弃过期响应。`stop_i`、`error_i`、HALT 指令（`0x0ff00513`）及错误响应会冻结新的取指请求。有效通道未就绪时，队列输出载荷保持稳定；出队仅消费连续的就绪前缀。

验证入口 `make a04` 对 `FE_WIDTH=1/2/4` 运行 Icarus 单元测试，再执行 Verilator 静态检查和 Yosys 层次、过程及存储检查。
