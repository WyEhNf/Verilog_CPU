# B-06 乘法与除法单元

`MUL_IMPL=0` 选择 `rv32m_multiplier`，即三级寄存的 valid/ready 流水线。它支持 `MUL`、`MULH`、`MULHSU` 和 `MULHU`，保留 ROB 标签和物理目的寄存器，在背压下保持已完成结果。数据路径使用 32 行显式部分积、多级 3:2 进位保留压缩器、Wallace 归约树，以及最后一级进位传播加法器；完整结构见 `docs/multiplier.md`。

`MUL_IMPL=1` 选择 `rv32m_multiplier_radix4`，即保持相同外部协议的紧凑 16 次迭代 radix-4 移位加法实现。共享单元忙时，MDU 保留站保存后续乘除任务。面积优先的单发射配置可使用紧凑实现，乘法吞吐优先的宽配置保留 Wallace 实现。

`rv32m_divider` 每次接受一个请求，执行 32 步恢复余数除法。它实现有符号和无符号商与余数、除零，以及 RV32 有符号 `INT_MIN / -1` 溢出结果。迭代进行时，请求就绪信号保持为低。两个单元在发布完成结果前都会丢弃无效或标签过期的结果。

MDU 包装模块向乘法器和除法器同时传递 `TAG_WIDTH` 与 `PHYS_ADDR_WIDTH`，包括 ROB=64 / PHYS_REGS=96 配置。分支恢复不会全局清空共享长延迟单元：更老任务正常排空，被清除任务的结果由 ROB generation 校验丢弃。
