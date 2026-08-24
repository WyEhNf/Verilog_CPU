# B-06 Multiply and Divide Units

`rv32m_multiplier` is a three-stage registered valid/ready pipeline. It
supports `MUL`, `MULH`, `MULHSU`, and `MULHU`, preserves the ROB tag and
physical destination, holds a completed result under backpressure, and clears
all stages on `flush_i`.

`rv32m_divider` accepts one request at a time and performs 32 restoring
division steps. It implements signed and unsigned quotient/remainder,
divide-by-zero, and the RV32 signed `INT_MIN / -1` overflow result. Its
request-ready signal stays low while the iteration is active. Both units
discard invalid or stale-tagged results before completion.
