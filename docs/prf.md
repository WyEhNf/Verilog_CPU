# 物理寄存器文件（B-01）

`rv32_physical_register_file` 保存物理寄存器的 32 位值和 ready 状态。它不保存
ROB 或生产者关系；RAT、ROB tag 和提交恢复逻辑负责决定哪个值仍然可达。

## 接口

模块参数为 `BE_WIDTH`、`PHYS_REGS` 和可选的 `PHYS_ADDR_WIDTH`。读端口数量固定为
`2*BE_WIDTH`，写端口数量为 `BE_WIDTH`。所有总线按 lane 顺序平铺：第 n 个端口位于
`n*width` 起始的 part-select。

- `read_phys_i`：读物理寄存器号。
- `read_data_o` / `read_ready_o`：组合读出的值和 ready 状态。
- `alloc_phys_i`、`alloc_valid_i`：rename 分配端口，在时钟沿把新物理目的寄存器置为未 ready。
- `write_phys_i`、`write_data_i`、`write_valid_i`：CDB 写回端口，在时钟上升沿生效。

同一周期多个写端口写入同一地址时，编号较大的 lane 优先。P0 永远输出零且 ready，
写入 P0 被丢弃。非二幂 `PHYS_REGS` 的编码地址若超出数组范围则读出零/未 ready，写入
被忽略。复位把所有值清零，只将 P0 置为 ready；其它寄存器保持未 ready。

组合读路径对当前有效写端口做显式旁路，因此同周期 RAW 可见；寄存器数组仍只在时钟
沿更新。同一物理号同时被 allocation 清 ready 和 CDB 写回时，写回优先。flush 不回滚
已写入的 PRF 值。

验证命令：`make b01`，覆盖 `BE_WIDTH=1/2/4` 以及 `PHYS_REGS=48/64/96`。
