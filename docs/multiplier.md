# RV32M Wallace 树乘法器

`rtl/rv32m_multiplier.v` 是三级、可反压的 RV32M 乘法流水线，支持
`MUL/MULH/MULHSU/MULHU`。实现中没有使用 Verilog 行为级乘法运算符。

## 数据通路

第一级先根据指令类型确定两个操作数的符号属性，将负数转成 32 位绝对值，再生成
32 行、每行 64 位的移位部分积。部分积通过三输入两输出的 carry-save compressor
（3:2 CSA）逐层归约：

```text
32 -> 22 -> 15 -> 10 | pipeline register
10 -> 7 -> 5 -> 4 -> 3 -> 2 | pipeline register
2 -> final carry-propagate adder -> sign correction/result select
```

CSA 的 sum 为 `a ^ b ^ c`，carry 为三组按位进位多数函数再左移一位。只有最后两行
才执行一次 64 位进位传播加法。最终积按有符号组合做二补码修正；`MUL` 选择低 32 位，
三个高位乘法选择高 32 位。

## 流水和恢复

每一级保存 valid、操作类型、ROB generation tag、物理目的寄存器和 live 位。输出在
`resp_ready_i=0` 时保持稳定，反压逐级传播到 `req_ready_o`。外部 reset/flush 清空全部级。
分支恢复不再无条件清空共享 MDU：严格老于恢复分支的长延迟乘法必须继续完成；后端以
ROB slot+generation 的 live 校验接受老结果并丢弃已 squash 的年轻结果。

## 验证

`tb/unit/rv32m_units_tb.v` 覆盖边界值，并对 128 组伪随机操作数逐一检查四种乘法模式，
参考值由 testbench 的 64 位算术计算。`tests/programs/vmul.c` 经
`riscv-none-elf-gcc -march=rv32im` 编译，runner 会在反汇编中断言真实 `mul` 助记符存在，
再由 `make join03/join04/join05` 分别运行单、双、四发射及参数矩阵。
