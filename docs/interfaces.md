# H-01/S-01 接口契约

本文件冻结 H-01/S-01 的公共接口规则。所有后续 RTL 单元只引用 `rtl/rv32im_defs.vh` 中的定义，不在各自模块中重新声明同名操作码、tag 或优先级。

## 参数和位宽

默认配置为 `FE_WIDTH=1`、`BE_WIDTH=1`、`PHYS_REGS=64`、`ROB_ENTRIES=32`。默认物理寄存器地址宽度为 6 位，ROB slot 宽度为 5 位，ROB generation 宽度为 8 位，完整 ROB tag 宽度为 16 位。

ROB tag 的 packed 顺序为 `{generation, slot, kind, valid}`。只有 `valid=1` 且 `kind`、`slot`、`generation` 同时相等时，tag 比较才成功；slot 相同但 generation 不同的旧完成结果必须丢弃。

## Packed bus 字段顺序

所有跨模块 bundle 使用 packed bus，不使用端口 unpacked array。当前冻结的字段顺序如下，左侧为高位字段：

| Bundle | Packed 顺序 |
| --- | --- |
| `FetchPacket` | `epoch, btb_hit, pred_kind, pred_target, pred_taken, inst, pc` |
| `DecodedInst` | 由 epoch、预测信息、原始指令/PC、控制字段、立即数和寄存器字段组成 |
| `RenamePacket` | 由 epoch、预测/访存字段、立即数、源操作数、物理/逻辑寄存器、ROB tag、PC/指令和 op/class 组成 |
| `IssuePacket` | 由 epoch、访存/控制字段、立即数、源值、物理目标、ROB tag、PC 和 op/class 组成 |
| `ExecResult` | epoch、分支结果、访存信息、结果值、物理目标和 ROB tag |
| `MemoryRequest` | valid、load/store、地址、size/sign/mask、写数据、ROB tag 和 LSQ tag |
| `MemoryResponse` | valid/error、line 地址、128-bit line data、transaction ID、ROB tag 和 LSQ tag |
| `CommitRecord` | valid、store 元数据、写回值、rd/rd_we、原始指令和 PC |

未使用 lane 的 `valid` 必须为 0。多 lane bundle 只能存在连续的有效前缀，不能出现 lane 0 无效而后续 lane 有效。

## Valid/ready

传输只在时钟上升沿前 `valid && ready` 时发生。当 `valid=1 && ready=0` 时，发送方必须保持完整 payload 和 tag 不变；接收方不得消费或产生副作用。flush 优先清除年轻 speculative 项，旧响应在写状态前必须通过 tag/epoch live 检查。

## 同周期优先级

公共优先级从高到低为：HALT/error freeze、flush、redirect、writeback、commit、store visibility。相同优先级的多个请求由最老的有效 ROB tag 决定。该顺序用于后续 frontend、ROB、completion 和 cache 连接，不能由单个模块临时改写。
