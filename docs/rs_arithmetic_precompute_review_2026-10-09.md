# Shared RS arithmetic precompute

## Scope

RS_ARITHMETIC_PRECOMPUTE defaults to zero and passes through the same top/core/backend to the original parameterized RS/ALU. It requires RS_ISSUE_METADATA=1. Generic RS metadata[31:0] must contain the exact allocated immediate, with full opcode width. There is no separate CPU for any issue width.

Historical A109 timing has late selected-opcode SUB control before the 32-bit prefix/carry-select network. Row arithmetic can overlap original ready/rank arbitration. Current Tier3 PPA is independently running on frozen 049da02c without this option; its actual terminal paths must justify the next full PPA. This implementation/sample establishes no CPU timing improvement.

## Packet and edge argument

Each row chooses rhs=effective source2 for ADD/SUB, otherwise rhs=its immediate. Compute lhs-rhs for SUB, otherwise lhs+rhs modulo 2^32. Operands are the original saved/current-wakeup views; full tags, wake matching/duplicate priority and readiness are unchanged. The helper uses the original eight-nibble carry-select and 1/2/4 prefix equations with local bounded subtraction control. Its actual prefix implementation also runs under WORD_SIM.

Append that combinational word to the same original packet selected by the same ready candidates and age/rank grants. Accepted fresh allocation issue uses its original incoming lane operands/immediate/grants. The word never drives readiness, allocation or release. Original fields keep their positions in the lower packet; recovery qualification/cancel sidebands follow their same selected row. A simulation assertion compares every valid selected word against the same selected complete packet.

Direct issue adds no FF or cycle. ISSUE_PIPELINE=1 extends the existing packet by 32 bits and uses the original valid/ready/hold/reset/flush/recovery controller, saving the same operands/tag/word together. There is no new stage or separate authority. ALU capture/output/backpressure/recovery remain original. ADD/SUB consume register arithmetic; ADDI, LOAD/STORE address and JALR consume immediate arithmetic. PC-relative targets/results, shifts and comparisons remain original. Every valid ALU packet has an independent arithmetic reference assertion.

## Cost and gates

Enabled mode trades two adders per integer issue lane for one per RS row, plus incoming arithmetic when fresh issue needs it. Wider selectors, wake timing and other paths can offset that benefit. Default arithmetic equations remain original, but hierarchy/parameter additions may affect mapping; old metrics are not attributed to this source. No capacities, tag/generation widths, SRAM model, area exemption or timing exceptions change.

configs/tier3_shared_500_arithmetic_candidate.json pins 187 numeric parameters and adds only this option to the previous integration profile. Parameter guards pass. Require area <=35891.672317998215 and Fmax >=500 before one CPU build/perf. Then IPC >=1.1152626918348099, original instruction counts and each case cycle <=7572/17490/143485/153155/4739/3725 before one array1 smoke. Accepted freezes/canonical profiles are unchanged.

## One finite sample

One BE2/ROB8/PHYS40/RS4/LSQ4 pair uses arithmetic0/1 and identical completion mode2. Direct recovery uses direct issue; staged recovery uses the existing registered issue stage. Five arithmetic points use real renamed operands: a two-lane ADDI producer bundle immediately followed by wrapping ADD, borrowing SUB and negative ADDI. After reset another actual ADDI reacquires a nonzero base for wrapping SB/SH/SW addresses with original exact masks and real ACKs.

The original delayed LOAD/held completion, branch/young cancellation, reset/whole flush, full-tag row reuse, MUL0*0 and precise LOAD error remain. Public cycles/valid complete packets and ROB/allocator state match; all RS/ALU arithmetic assertions pass. Each recovery mode observes three captures/three previews/one apply; flush/reset cancel the other captures. This is not a whole CPU/all-width/configuration/timing proof. One run passed in 70.107403 seconds around 1us; exact frozen inputs/executable/build/simulation hashes are in reports/Tier_shared_RS_arithmetic_protocol_2026-10-09.json.
