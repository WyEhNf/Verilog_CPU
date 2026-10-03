`ifndef RV32IM_DEFS_VH
`define RV32IM_DEFS_VH

// H-00 project defaults.
`define RV32IM_FE_WIDTH_DEFAULT 1
`define RV32IM_BE_WIDTH_DEFAULT 1
`define RV32IM_PHYS_REGS_DEFAULT 64
`define RV32IM_ROB_ENTRIES_DEFAULT 32

// Shared scalar widths.
`define RV32IM_OP_WIDTH 6
`define RV32IM_CLASS_WIDTH 4
`define RV32IM_MEM_WIDTH 2
`define RV32IM_PRED_KIND_WIDTH 2
`define RV32IM_EPOCH_WIDTH 4
`define RV32IM_BYTE_MASK_WIDTH 16
`define RV32IM_ROB_GENERATION_WIDTH 8
`define RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT 6
`define RV32IM_ROB_SLOT_WIDTH_DEFAULT 5
`define RV32IM_ROB_TAG_WIDTH_DEFAULT 16

// RV32I/M operation identifiers.
`define RV32IM_OP_INVALID  6'd0
`define RV32IM_OP_LUI      6'd1
`define RV32IM_OP_AUIPC    6'd2
`define RV32IM_OP_JAL      6'd3
`define RV32IM_OP_JALR     6'd4
`define RV32IM_OP_BEQ      6'd5
`define RV32IM_OP_BNE      6'd6
`define RV32IM_OP_BLT      6'd7
`define RV32IM_OP_BGE      6'd8
`define RV32IM_OP_BLTU     6'd9
`define RV32IM_OP_BGEU     6'd10
`define RV32IM_OP_LB       6'd11
`define RV32IM_OP_LH       6'd12
`define RV32IM_OP_LW       6'd13
`define RV32IM_OP_LBU      6'd14
`define RV32IM_OP_LHU      6'd15
`define RV32IM_OP_SB       6'd16
`define RV32IM_OP_SH       6'd17
`define RV32IM_OP_SW       6'd18
`define RV32IM_OP_ADDI     6'd19
`define RV32IM_OP_SLTI     6'd20
`define RV32IM_OP_SLTIU    6'd21
`define RV32IM_OP_XORI     6'd22
`define RV32IM_OP_ORI      6'd23
`define RV32IM_OP_ANDI     6'd24
`define RV32IM_OP_SLLI     6'd25
`define RV32IM_OP_SRLI     6'd26
`define RV32IM_OP_SRAI     6'd27
`define RV32IM_OP_ADD      6'd28
`define RV32IM_OP_SUB      6'd29
`define RV32IM_OP_SLL      6'd30
`define RV32IM_OP_SLT      6'd31
`define RV32IM_OP_SLTU     6'd32
`define RV32IM_OP_XOR      6'd33
`define RV32IM_OP_SRL      6'd34
`define RV32IM_OP_SRA      6'd35
`define RV32IM_OP_OR       6'd36
`define RV32IM_OP_AND      6'd37
`define RV32IM_OP_MUL      6'd38
`define RV32IM_OP_MULH     6'd39
`define RV32IM_OP_MULHSU   6'd40
`define RV32IM_OP_MULHU    6'd41
`define RV32IM_OP_DIV      6'd42
`define RV32IM_OP_DIVU     6'd43
`define RV32IM_OP_REM      6'd44
`define RV32IM_OP_REMU     6'd45
`define RV32IM_OP_FENCE    6'd46
`define RV32IM_OP_ECALL    6'd47
`define RV32IM_OP_EBREAK   6'd48
`define RV32IM_OP_HALT     6'd49

// Instruction classes.
`define RV32IM_CLASS_INVALID 4'd0
`define RV32IM_CLASS_INT     4'd1
`define RV32IM_CLASS_LOAD    4'd2
`define RV32IM_CLASS_STORE   4'd3
`define RV32IM_CLASS_BRANCH  4'd4
`define RV32IM_CLASS_JUMP    4'd5
`define RV32IM_CLASS_MUL     4'd6
`define RV32IM_CLASS_DIV     4'd7
`define RV32IM_CLASS_SYSTEM  4'd8
`define RV32IM_CLASS_HALT    4'd9

// Memory width and prediction identifiers.
`define RV32IM_MEM_BYTE 2'd0
`define RV32IM_MEM_HALF 2'd1
`define RV32IM_MEM_WORD 2'd2
`define RV32IM_MEM_NONE 2'd3
`define RV32IM_PRED_NONE 2'd0
`define RV32IM_PRED_BRANCH 2'd1
`define RV32IM_PRED_JAL 2'd2
`define RV32IM_PRED_JALR 2'd3

// ROB tag layout: {generation, slot, kind, valid}.
`define RV32IM_ROB_TAG_VALID_LSB 0
`define RV32IM_ROB_TAG_KIND_LSB 1
`define RV32IM_ROB_TAG_SLOT_LSB 3
`define RV32IM_ROB_TAG_GENERATION_LSB 8
`define RV32IM_ROB_TAG_KIND_WIDTH 2
`define RV32IM_ROB_TAG_PACK(valid, kind, slot, generation) {generation, slot, kind, valid}
`define RV32IM_ROB_TAG_VALID(tag) tag[`RV32IM_ROB_TAG_VALID_LSB]
`define RV32IM_ROB_TAG_KIND(tag) tag[`RV32IM_ROB_TAG_KIND_LSB +: `RV32IM_ROB_TAG_KIND_WIDTH]
`define RV32IM_ROB_TAG_SLOT(tag) tag[`RV32IM_ROB_TAG_SLOT_LSB +: `RV32IM_ROB_SLOT_WIDTH_DEFAULT]
`define RV32IM_ROB_TAG_GENERATION(tag) tag[`RV32IM_ROB_TAG_GENERATION_LSB +: `RV32IM_ROB_GENERATION_WIDTH]

// Packet field widths and canonical packed field order.
// FetchPacket: {epoch, btb_hit, pred_kind, pred_target, pred_taken, inst, pc}.
`define RV32IM_FETCH_PACKET_WIDTH 104
`define RV32IM_FETCH_PACKET_PACK(pc, inst, pred_taken, pred_target, pred_kind, btb_hit, epoch) {epoch, btb_hit, pred_kind, pred_target, pred_taken, inst, pc}
// DecodedInst: {epoch, pred metadata, inst, pc, memory/control fields, immediate, sources, op/class}.
`define RV32IM_DECODED_INST_WIDTH 174
// RenamePacket: {epoch, prediction, memory/control fields, immediate, source values/tags, physical and logical registers, ROB tag, pc, inst, op/class}.
`define RV32IM_RENAME_PACKET_WIDTH 322
// IssuePacket: {epoch, memory/control fields, immediate, source values, physical rd, ROB tag, pc, op/class}.
`define RV32IM_ISSUE_PACKET_WIDTH 246
// ExecResult: {epoch, branch metadata, memory metadata, value, physical rd, ROB tag}.
`define RV32IM_EXEC_RESULT_WIDTH 134
// MemoryRequest: {valid, load/store, address, size/sign/mask, write data, ROB/LSQ tags}.
`define RV32IM_MEMORY_REQUEST_WIDTH 105
// MemoryResponse: {valid, error, line address, line data, transaction id, ROB/LSQ tags}.
`define RV32IM_MEMORY_RESPONSE_WIDTH 185
// CommitRecord: {valid, store metadata, writeback value, rd, rd_we, inst, pc}.
`define RV32IM_COMMIT_RECORD_WIDTH 117

// Same-cycle control priority. Higher values win; equal values are resolved by oldest tag.
`define RV32IM_PRIORITY_STORE_VISIBILITY 1
`define RV32IM_PRIORITY_COMMIT 2
`define RV32IM_PRIORITY_WRITEBACK 3
`define RV32IM_PRIORITY_REDIRECT 4
`define RV32IM_PRIORITY_FLUSH 5
`define RV32IM_PRIORITY_HALT_ERROR 6

// Packed-bus protocol rules used by all producers and consumers.
`define RV32IM_VALID_READY_FIRE(valid, ready) ((valid) && (ready))
`define RV32IM_VALID_READY_STABLE(valid, ready, old_payload, new_payload) (((valid) && !(ready)) ? ((old_payload) == (new_payload)) : 1'b1)

`endif
