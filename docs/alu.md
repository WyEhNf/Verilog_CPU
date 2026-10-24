# B-05 Integer ALU, Branch, and AGU

`rv32i_alu` accepts one INT reservation-station issue packet and produces one
registered execution result. The input immediate is a sign-extended 32-bit
value. Results are visible on the cycle after `issue_valid_i && issue_ready_o`
and remain stable until `exec_ready_i` is asserted.

The unit implements RV32I arithmetic, logical operations, comparisons, shifts,
LUI, AUIPC, conditional branches, JAL, and JALR. Shift amounts use only bits
4:0. JALR clears target bit zero. Load and store operations only calculate
`rs1 + immediate`; they return memory metadata and store data for the LSQ.

Branch results include the actual target, taken bit, next PC, and a redirect
request when the supplied prediction disagrees with the result. A pending
result is discarded by `flush_i`. When `live_tag_valid_i` is asserted, a
pending result is visible only if its complete ROB tag equals `live_tag_i`.
