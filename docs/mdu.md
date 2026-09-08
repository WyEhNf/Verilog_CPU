# B-06 Multiply and Divide Units

`rv32m_multiplier` is a three-stage registered valid/ready pipeline. It
supports `MUL`, `MULH`, `MULHSU`, and `MULHU`, preserves the ROB tag and
physical destination, and holds a completed result under backpressure. Its
datapath uses 32 explicit partial-product rows, repeated 3:2 carry-save
compressors, a Wallace reduction tree, and one final carry-propagate adder;
see `docs/multiplier.md` for the complete structure.

`rv32m_divider` accepts one request at a time and performs 32 restoring
division steps. It implements signed and unsigned quotient/remainder,
divide-by-zero, and the RV32 signed `INT_MIN / -1` overflow result. Its
request-ready signal stays low while the iteration is active. Both units
discard invalid or stale-tagged results before completion.

The MDU wrapper propagates both `TAG_WIDTH` and `PHYS_ADDR_WIDTH` into the
multiplier/divider, including the ROB=64 / PHYS_REGS=96 configuration. A
branch recovery does not globally flush the shared long-latency unit: older
work drains normally and ROB generation validation discards squashed work.
