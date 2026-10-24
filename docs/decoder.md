# A-01 RV32IM 译码器

`rv32im_decoder` 是单 lane、纯组合译码器。多发射前端为每个有效 lane 各实例化一份，输出字段直接对应后端 trace/rename 接口：操作码、类别、逻辑寄存器、源使用标志、写回标志、立即数、访存属性和控制流属性。

立即数按 RISC-V 的 I/S/B/U/J 格式在译码器内重排并符号扩展。JALR 额外输出 `jalr_clear_lsb_o`，提示执行单元对最终目标地址清零 bit 0。移位立即数只接受 RV32 合法的 `funct7`，R 型只接受标准整数或 `funct7=0000001` 的 M 扩展编码。

首轮访存范围为 `LB/LBU/LW/SB/SW`。`mem_base_mask_o` 是尚未按地址低位移动的 word 内基础 mask：byte 为 `0001`，word 为 `1111`；地址相关移动由 AGU/LSQ 完成。`LH/LHU/SH` 保留操作码定义，但当前显式返回非法，避免与 byte/word 路径混淆。

CSR、ECALL、EBREAK 和 FENCE 当前均非法。项目结束标记 `0x0ff00513` 在机器码上与 `ADDI a0,zero,255` 重叠，因此译码器以完整机器码优先识别为 `HALT`，并清除普通 ADDI 的寄存器写回副作用。任何非法编码都输出 `legal=0`、`OP_INVALID/CLASS_INVALID`，同时清零所有副作用控制。

验证入口为 `make a01`，覆盖所有 RV32I 算术类别、六类分支、JAL/JALR、八个 M 扩展操作、立即数重排、支持的 byte/word 访存、HALT 优先级和保留编码。
