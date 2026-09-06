`timescale 1ns/1ps
`include "rv32im_defs.vh"

// B-09 single-issue backend closure.  The input is a decoded instruction
// trace; the output is the only architectural observation point, CommitRecord.
// Rename, PRF, RS, ALU/MDU, completion, ROB and LSQ remain independent blocks
// connected by their frozen valid/ready/tag contracts.
module rv32_backend_joint #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer RS_ENTRIES = 8,
    parameter integer LSQ_ENTRIES = 8,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer CHECKPOINT_WIDTH = 1024
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,

    input  wire                         trace_valid_i,
    output wire                         trace_ready_o,
    input  wire [31:0]                  trace_pc_i,
    input  wire [31:0]                  trace_inst_i,
    input  wire [`RV32IM_OP_WIDTH-1:0]  trace_op_i,
    input  wire [31:0]                  trace_imm_i,
    input  wire [4:0]                   trace_rd_i,
    input  wire [4:0]                   trace_rs1_i,
    input  wire [4:0]                   trace_rs2_i,
    input  wire                         trace_rd_we_i,
    input  wire                         trace_rs1_used_i,
    input  wire                         trace_rs2_used_i,
    input  wire                         trace_is_load_i,
    input  wire                         trace_is_store_i,
    input  wire                         trace_is_branch_i,
    input  wire                         trace_is_halt_i,
    input  wire                         trace_is_error_i,
    input  wire [1:0]                   trace_mem_size_i,
    input  wire                         trace_mem_unsigned_i,
    input  wire [127:0]                 trace_store_data_i,
    input  wire                         trace_pred_taken_i,
    input  wire [31:0]                  trace_pred_target_i,
    input  wire [1:0]                   trace_pred_kind_i,

    output wire                         dcache_req_valid_o,
    input  wire                         dcache_req_ready_i,
    output wire                         dcache_req_is_load_o,
    output wire                         dcache_req_is_store_o,
    output wire [31:0]                  dcache_req_addr_o,
    output wire [1:0]                   dcache_req_size_o,
    output wire                         dcache_req_unsigned_o,
    output wire [15:0]                  dcache_req_mask_o,
    output wire [127:0]                 dcache_req_wdata_o,
    output wire [TAG_WIDTH-1:0]         dcache_req_rob_tag_o,
    output wire [TAG_WIDTH-1:0]         dcache_req_lsq_tag_o,
    input  wire                         dcache_resp_valid_i,
    output wire                         dcache_resp_ready_o,
    input  wire [TAG_WIDTH-1:0]         dcache_resp_lsq_tag_i,
    input  wire [31:0]                  dcache_resp_addr_i,
    input  wire [127:0]                 dcache_resp_line_data_i,
    input  wire [31:0]                  dcache_resp_word_data_i,
    input  wire                         dcache_resp_line_valid_i,
    input  wire                         dcache_resp_error_i,
    input  wire                         dcache_store_ack_valid_i,
    input  wire [TAG_WIDTH-1:0]         dcache_store_ack_lsq_tag_i,
    input  wire                         dcache_store_ack_error_i,

    input  wire                         commit_ready_i,
    output wire                         commit_valid_o,
    output wire [31:0]                  commit_pc_o,
    output wire [31:0]                  commit_inst_o,
    output wire [4:0]                   commit_rd_o,
    output wire                         commit_rd_we_o,
    output wire [31:0]                  commit_value_o,
    output wire                         commit_is_store_o,
    output wire [31:0]                  commit_store_addr_o,
    output wire [15:0]                  commit_store_mask_o,
    output wire [127:0]                 commit_store_data_o,
    output wire [TAG_WIDTH-1:0]         commit_tag_o,
    output wire                         redirect_valid_o,
    output wire [31:0]                  redirect_pc_o,
    output wire [3:0]                   redirect_epoch_o,
    output wire                         halted_o,
    output wire                         error_o,
    output wire [7:0]                   return_value_o,
    output wire                         branch_feedback_valid_o,
    output wire [31:0]                  branch_feedback_pc_o,
    output wire [1:0]                   branch_feedback_kind_o,
    output wire                         branch_feedback_taken_o,
    output wire [31:0]                  branch_feedback_target_o,
    output wire                         branch_feedback_pred_taken_o,
    output wire [31:0]                  branch_feedback_pred_target_o
);
    localparam integer PAW = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS);
    localparam integer ROB_SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES);
    localparam integer ROB_COUNT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES + 1);
    localparam integer LSQ_SLOT_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES);
    localparam integer FREE_SLOTS = PHYS_REGS - 1;
    localparam integer FREE_PTR_WIDTH = (FREE_SLOTS <= 1) ? 1 : $clog2(FREE_SLOTS);
    localparam integer FREE_COUNT_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS + 1);
    localparam integer CHECK_RAT_WIDTH = 32 * PAW;
    localparam integer CHECK_FREE_WIDTH = FREE_SLOTS * PAW;

    wire [BE_WIDTH-1:0] dec_valid = {{(BE_WIDTH-1){1'b0}}, trace_valid_i};
    wire [BE_WIDTH-1:0] dec_rd_we = {{(BE_WIDTH-1){1'b0}}, trace_rd_we_i};
    wire [BE_WIDTH-1:0] dec_rs1_used = {{(BE_WIDTH-1){1'b0}}, trace_rs1_used_i};
    wire [BE_WIDTH-1:0] dec_rs2_used = {{(BE_WIDTH-1){1'b0}}, trace_rs2_used_i};
    wire [BE_WIDTH-1:0] dec_rs_need = {{(BE_WIDTH-1){1'b0}}, trace_valid_i};
    wire [BE_WIDTH-1:0] dec_lsq_need = {{(BE_WIDTH-1){1'b0}}, trace_is_load_i | trace_is_store_i};
    wire [(BE_WIDTH*5)-1:0] dec_rd = {{(BE_WIDTH*5-5){1'b0}}, trace_rd_i};
    wire [(BE_WIDTH*5)-1:0] dec_rs1 = {{(BE_WIDTH*5-5){1'b0}}, trace_rs1_i};
    wire [(BE_WIDTH*5)-1:0] dec_rs2 = {{(BE_WIDTH*5-5){1'b0}}, trace_rs2_i};

    wire [BE_WIDTH-1:0] rename_valid;
    wire [BE_WIDTH-1:0] rename_rd_we;
    wire [(BE_WIDTH*5)-1:0] rename_rd;
    wire [(BE_WIDTH*PAW)-1:0] rename_old_phys, rename_new_phys;
    wire [(BE_WIDTH*PAW)-1:0] rename_rs1_phys, rename_rs2_phys;
    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] rename_count;
    wire [(32*PAW)-1:0] rat_state, rrat_state;
    wire [(FREE_SLOTS*PAW)-1:0] free_list_state;
    wire [FREE_PTR_WIDTH-1:0] free_head, free_tail;
    wire [FREE_COUNT_WIDTH-1:0] free_count;

    wire [BE_WIDTH-1:0] rob_alloc_valid;
    wire [BE_WIDTH-1:0] rob_alloc_fire;
    wire [(BE_WIDTH*TAG_WIDTH)-1:0] rob_alloc_tag;
    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] rob_alloc_count;
    wire rob_alloc_ready;
    wire [BE_WIDTH-1:0] rob_completion_valid;
    wire [(BE_WIDTH*TAG_WIDTH)-1:0] rob_completion_tag;
    wire [(BE_WIDTH*32)-1:0] rob_completion_value;
    wire [BE_WIDTH-1:0] rob_completion_done, rob_completion_error;
    wire [(BE_WIDTH*32)-1:0] rob_completion_store_addr;
    wire [(BE_WIDTH*16)-1:0] rob_completion_store_mask;
    wire [(BE_WIDTH*128)-1:0] rob_completion_store_data;
    wire [BE_WIDTH-1:0] rob_commit_valid, rob_commit_rd_we, rob_commit_is_store;
    wire [(BE_WIDTH*5)-1:0] rob_commit_rd;
    wire [(BE_WIDTH*32)-1:0] rob_commit_pc, rob_commit_inst, rob_commit_value;
    wire [(BE_WIDTH*32)-1:0] rob_commit_store_addr;
    wire [(BE_WIDTH*16)-1:0] rob_commit_store_mask;
    wire [(BE_WIDTH*128)-1:0] rob_commit_store_data;
    wire [(BE_WIDTH*TAG_WIDTH)-1:0] rob_commit_tag;
    wire rob_store_commit_valid, rob_store_commit_ready, rob_store_ack_valid;
    wire [TAG_WIDTH-1:0] rob_store_commit_tag, rob_store_ack_tag;
    wire [31:0] rob_store_commit_addr;
    wire [15:0] rob_store_commit_mask;
    wire [127:0] rob_store_commit_data;
    wire rob_recovery_accept, rob_redirect_valid, rob_checkpoint_restore_valid;
    wire [31:0] rob_redirect_pc;
    wire [3:0] rob_redirect_epoch;
    wire [CHECKPOINT_WIDTH-1:0] rob_checkpoint_restore;
    wire [ROB_SLOT_WIDTH-1:0] rob_head, rob_tail;
    wire [ROB_COUNT_WIDTH-1:0] rob_occupancy;
    wire [15:0] rob_free_count = (rob_occupancy < ROB_ENTRIES) ? ROB_ENTRIES - rob_occupancy : 16'd0;

    wire [(2*BE_WIDTH*PAW)-1:0] prf_read_phys;
    wire [(2*BE_WIDTH*32)-1:0] prf_read_data;
    wire [(2*BE_WIDTH)-1:0] prf_read_ready;
    wire [(BE_WIDTH*PAW)-1:0] prf_alloc_phys = rename_new_phys;
    wire [BE_WIDTH-1:0] prf_alloc_valid = rename_valid;
    wire [(BE_WIDTH*PAW)-1:0] prf_write_phys;
    wire [(BE_WIDTH*32)-1:0] prf_write_data;
    wire [BE_WIDTH-1:0] prf_write_valid;

    wire [BE_WIDTH-1:0] rs_alloc_valid;
    wire rs_alloc_ready;
    wire [BE_WIDTH-1:0] rs_alloc_fire;
    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] rs_alloc_count;
    wire [BE_WIDTH-1:0] rs_issue_valid;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] rs_issue_op;
    wire [BE_WIDTH*32-1:0] rs_issue_pc, rs_issue_src1, rs_issue_src2;
    wire [BE_WIDTH*TAG_WIDTH-1:0] rs_issue_tag;
    wire [BE_WIDTH*PAW-1:0] rs_issue_phys;
    wire [BE_WIDTH*128-1:0] rs_issue_store;
    wire [BE_WIDTH*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))-1:0] rs_issue_slot;
    wire [((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES + 1))-1:0] rs_occupancy;
    wire [15:0] rs_free_count = (rs_occupancy < RS_ENTRIES) ? RS_ENTRIES - rs_occupancy : 16'd0;
    wire [BE_WIDTH-1:0] rs_issue_ready;
    wire [BE_WIDTH-1:0] rs_wake_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] rs_wake_tag;
    wire [BE_WIDTH*32-1:0] rs_wake_value;
    wire [RS_ENTRIES-1:0] rs_entry_valid;
    wire [RS_ENTRIES*TAG_WIDTH-1:0] rs_entry_rob_tag;
    reg [RS_ENTRIES-1:0] rs_flush_kill_mask;

    wire alu_exec_valid, alu_exec_ready, alu_issue_ready, alu_exec_rd_we, alu_exec_is_branch;
    wire alu_exec_branch_taken, alu_exec_redirect_valid, alu_exec_is_memory;
    wire alu_exec_is_load, alu_exec_is_store, alu_exec_mem_unsigned;
    wire [31:0] alu_exec_value, alu_exec_branch_target, alu_exec_redirect_pc, alu_exec_mem_addr;
    wire [1:0] alu_exec_mem_size;
    wire [127:0] alu_exec_store_data;
    wire [PAW-1:0] alu_exec_phys;
    wire [TAG_WIDTH-1:0] alu_exec_tag;

    wire mdu_issue_valid, mdu_issue_ready, mdu_completion_valid, mdu_completion_ready, mdu_completion_rd_we;
    wire [31:0] mdu_completion_value;
    wire [TAG_WIDTH-1:0] mdu_completion_tag;
    wire [PAW-1:0] mdu_completion_phys;

    wire [BE_WIDTH-1:0] cdb_valid, cdb_rd_we, cdb_is_store, cdb_is_branch;
    wire [BE_WIDTH*TAG_WIDTH-1:0] cdb_tag;
    wire [BE_WIDTH*PAW-1:0] cdb_phys;
    wire [BE_WIDTH*32-1:0] cdb_value, cdb_addr, cdb_branch_target;
    wire [BE_WIDTH*128-1:0] cdb_store_data;
    wire [BE_WIDTH-1:0] cdb_branch_taken, cdb_redirect_valid, cdb_is_memory, cdb_is_load;
    wire [2:0] producer_valid, producer_ready;
    wire [3*TAG_WIDTH-1:0] producer_tag;
    wire [3*PAW-1:0] producer_phys;
    wire [3*32-1:0] producer_value, producer_addr, producer_branch_target;
    wire [3*128-1:0] producer_store_data;
    wire [2:0] producer_rd_we, producer_store, producer_branch, producer_taken, producer_redirect, producer_memory, producer_load;
    // The recovery cycle uses the ROB completion port for the resolving
    // branch.  Hold queued CDB work for one cycle so an older completion is
    // not popped without reaching the ROB.
    wire [BE_WIDTH-1:0] cdb_ready;
    wire [15:0] completion_entry_valid;
    wire [16*TAG_WIDTH-1:0] completion_entry_tag;
    wire [BE_WIDTH-1:0] prf_wb_valid, rob_wb_valid, wake_wb_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] prf_wb_tag, rob_wb_tag, wake_wb_tag;
    wire [BE_WIDTH*PAW-1:0] prf_wb_phys;
    wire [BE_WIDTH*32-1:0] prf_wb_value, rob_wb_value, wake_wb_value;

    wire [BE_WIDTH-1:0] lsq_alloc_valid;
    wire lsq_alloc_ready;
    wire [BE_WIDTH-1:0] lsq_alloc_fire;
    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] lsq_alloc_count;
    wire [BE_WIDTH*TAG_WIDTH-1:0] lsq_alloc_tag;
    wire [((LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES + 1))-1:0] lsq_occupancy;
    wire [15:0] lsq_free_count = (lsq_occupancy < LSQ_ENTRIES) ? LSQ_ENTRIES - lsq_occupancy : 16'd0;
    wire lsq_store_commit_ready, lsq_load_complete_valid, lsq_load_complete_ready;
    wire [TAG_WIDTH-1:0] lsq_load_complete_tag;
    wire [TAG_WIDTH-1:0] lsq_load_complete_lsq_tag;
    wire [31:0] lsq_load_complete_value;
    wire lsq_load_complete_error;
    wire lsq_store_ack_valid;
    wire [TAG_WIDTH-1:0] lsq_store_ack_lsq_tag;
    wire [TAG_WIDTH-1:0] lsq_store_ack_rob_tag;
    wire lsq_store_ack_error;
    wire lsq_addr_update_valid;
    wire [TAG_WIDTH-1:0] lsq_addr_update_tag;
    wire [31:0] lsq_addr_update;
    wire lsq_data_update_valid;
    wire [TAG_WIDTH-1:0] lsq_data_update_tag;

    reg [TAG_WIDTH-1:0] rob_to_lsq_mem [0:ROB_ENTRIES-1];
    reg [PAW-1:0] lsq_phys_mem [0:LSQ_ENTRIES-1];
    reg [PAW-1:0] rob_phys_mem [0:ROB_ENTRIES-1];
    reg [PAW-1:0] rob_old_phys_mem [0:ROB_ENTRIES-1];
    reg [4:0] rob_rd_mem [0:ROB_ENTRIES-1];
    reg rob_rd_we_mem [0:ROB_ENTRIES-1];
    reg [TAG_WIDTH-1:0] phys_tag_mem [0:PHYS_REGS-1];
    reg [31:0] rob_pc_mem [0:ROB_ENTRIES-1];
    reg load_error_mem [0:ROB_ENTRIES-1];
    reg [31:0] rob_imm_mem [0:ROB_ENTRIES-1];
    reg rob_pred_taken_mem [0:ROB_ENTRIES-1];
    reg [31:0] rob_pred_target_mem [0:ROB_ENTRIES-1];
    reg [1:0] rob_pred_kind_mem [0:ROB_ENTRIES-1];
    reg [1:0] rob_mem_size_mem [0:ROB_ENTRIES-1];
    reg rob_mem_unsigned_mem [0:ROB_ENTRIES-1];
    reg branch_pending;
    reg [TAG_WIDTH-1:0] branch_pending_tag;
    reg [31:0] branch_pending_value;
    reg [31:0] branch_pending_pc;
    reg [31:0] branch_pending_source_pc;
    reg [1:0] branch_pending_kind;
    reg branch_pending_taken;
    reg [31:0] branch_pending_target;
    reg branch_pending_pred_taken;
    reg [31:0] branch_pending_pred_target;
    assign cdb_ready = {BE_WIDTH{!branch_pending}};
    integer map_index;
    integer map_rob_slot;
    integer map_lsq_slot;
    integer map_phys_slot;
    integer producer_index;
    integer producer_count;
    integer alu_rank, mdu_rank, load_rank;
    integer completion_lane;
    integer completion_slot;
    integer recovery_map_index;
    integer recovery_slot_index;
    integer recovery_branch_slot;
    integer recovery_branch_age;
    integer recovery_slot_age;
    integer recovery_phys_index;
    integer recovery_free_index;
    integer recovery_rs_index;
    integer recovery_rs_rob_slot;
    integer recovery_rs_branch_slot;
    integer recovery_rs_age;
    integer recovery_rs_branch_age;
    integer recovery_completion_index;
    integer recovery_completion_rob_slot;
    integer recovery_completion_age;
    integer recovery_completion_branch_age;
    integer producer_recovery_index;
    integer producer_recovery_rob_slot;
    integer producer_recovery_age;
    integer producer_recovery_branch_age;
    reg [CHECK_RAT_WIDTH-1:0] recovery_rat_state;
    reg [CHECK_FREE_WIDTH-1:0] recovery_free_list_state;
    reg [PHYS_REGS-1:0] recovery_reserved;
    reg [FREE_PTR_WIDTH-1:0] recovery_free_tail;
    reg [FREE_COUNT_WIDTH-1:0] recovery_free_count;
    reg [15:0] completion_kill_mask;
    wire dispatch_valid;
    wire [TAG_WIDTH-1:0] rs_src1_tag = (rename_rs1_phys[PAW-1:0] < PHYS_REGS) ?
        phys_tag_mem[rename_rs1_phys[PAW-1:0]] : {TAG_WIDTH{1'b0}};
    wire [TAG_WIDTH-1:0] rs_src2_tag = (rename_rs2_phys[PAW-1:0] < PHYS_REGS) ?
        phys_tag_mem[rename_rs2_phys[PAW-1:0]] : {TAG_WIDTH{1'b0}};
    wire rs_src1_ready = (rename_rs1_phys[PAW-1:0] == 0) || prf_read_ready[0];
    wire rs_src2_ready = (rename_rs2_phys[PAW-1:0] == 0) || prf_read_ready[1];
    wire [31:0] rs_issue_imm = rob_imm_mem[rs_issue_tag[3 +: ROB_SLOT_WIDTH]];
    wire rs_issue_pred_taken = rob_pred_taken_mem[rs_issue_tag[3 +: ROB_SLOT_WIDTH]];
    wire [31:0] rs_issue_pred_target = rob_pred_target_mem[rs_issue_tag[3 +: ROB_SLOT_WIDTH]];
    wire [1:0] rs_issue_pred_kind = rob_pred_kind_mem[rs_issue_tag[3 +: ROB_SLOT_WIDTH]];
    wire [1:0] rs_issue_mem_size = rob_mem_size_mem[rs_issue_tag[3 +: ROB_SLOT_WIDTH]];
    wire rs_issue_mem_unsigned = rob_mem_unsigned_mem[rs_issue_tag[3 +: ROB_SLOT_WIDTH]];
    reg [CHECKPOINT_WIDTH-1:0] checkpoint_pack;
    reg [BE_WIDTH-1:0] rob_alloc_is_store, rob_alloc_is_branch, rob_alloc_is_halt, rob_alloc_is_error;
    reg [BE_WIDTH*32-1:0] rob_alloc_pc, rob_alloc_inst;
    reg [BE_WIDTH*5-1:0] rob_alloc_rd;
    reg [BE_WIDTH*PAW-1:0] rob_alloc_old_phys, rob_alloc_new_phys;
    reg [BE_WIDTH*CHECKPOINT_WIDTH-1:0] rob_alloc_checkpoint;
    reg [3*TAG_WIDTH-1:0] producer_tag_r;
    reg [3*PAW-1:0] producer_phys_r;
    reg [3*32-1:0] producer_value_r, producer_addr_r, producer_branch_target_r;
    reg [3*128-1:0] producer_store_data_r;
    reg [2:0] producer_valid_r, producer_rd_we_r, producer_store_r, producer_branch_r, producer_taken_r, producer_redirect_r, producer_memory_r, producer_load_r;
    reg [2:0] producer_target_live_r;
    wire [2:0] producer_ready_r;
    reg [BE_WIDTH-1:0] completion_valid_r, completion_done_r, completion_error_r;
    reg [BE_WIDTH*TAG_WIDTH-1:0] completion_tag_r;
    reg [BE_WIDTH*32-1:0] completion_value_r, completion_store_addr_r;
    reg [BE_WIDTH*16-1:0] completion_store_mask_r;
    reg [BE_WIDTH*128-1:0] completion_store_data_r;

    assign prf_read_phys = {{(2*BE_WIDTH*PAW-2*PAW){1'b0}}, rename_rs2_phys[PAW-1:0], rename_rs1_phys[PAW-1:0]};
    // Ready describes whether a trace could be accepted; it must not depend
    // on trace_valid, otherwise a producer cannot present its first item.
    assign trace_ready_o = !halted_o && !flush_i && !rob_recovery_accept &&
        (rob_occupancy < ROB_ENTRIES) && (rs_occupancy < RS_ENTRIES) &&
        ((!(trace_is_load_i || trace_is_store_i)) || (lsq_occupancy < LSQ_ENTRIES)) &&
        ((!trace_rd_we_i) || (trace_rd_i == 0) || (free_count != 0));
    assign dispatch_valid = trace_valid_i && trace_ready_o;
    assign rob_alloc_valid = { {(BE_WIDTH-1){1'b0}}, dispatch_valid };
    assign rs_alloc_valid = rob_alloc_valid;
    assign lsq_alloc_valid = { {(BE_WIDTH-1){1'b0}}, dispatch_valid && (trace_is_load_i || trace_is_store_i) };
    assign commit_valid_o = rob_commit_valid[0];
    assign commit_pc_o = rob_commit_pc[31:0];
    assign commit_inst_o = rob_commit_inst[31:0];
    assign commit_rd_o = rob_commit_rd[4:0];
    assign commit_rd_we_o = rob_commit_rd_we[0];
    assign commit_value_o = rob_commit_value[31:0];
    assign commit_is_store_o = rob_commit_is_store[0];
    assign commit_store_addr_o = rob_commit_store_addr[31:0];
    assign commit_store_mask_o = rob_commit_store_mask[15:0];
    assign commit_store_data_o = rob_commit_store_data[127:0];
    assign commit_tag_o = rob_commit_tag[TAG_WIDTH-1:0];
    assign redirect_valid_o = rob_redirect_valid;
    assign redirect_pc_o = rob_redirect_pc;
    assign redirect_epoch_o = rob_redirect_epoch;
    assign branch_feedback_valid_o = branch_pending && rob_recovery_accept;
    assign branch_feedback_pc_o = branch_pending_source_pc;
    assign branch_feedback_kind_o = branch_pending_kind;
    assign branch_feedback_taken_o = branch_pending_taken;
    assign branch_feedback_target_o = branch_pending_target;
    assign branch_feedback_pred_taken_o = branch_pending_pred_taken;
    assign branch_feedback_pred_target_o = branch_pending_pred_target;

    assign lsq_addr_update_valid = alu_exec_valid && alu_exec_is_memory;
    assign lsq_addr_update_tag = rob_to_lsq_mem[alu_exec_tag[3 +: ROB_SLOT_WIDTH]];
    assign lsq_addr_update = alu_exec_mem_addr;
    assign lsq_data_update_valid = alu_exec_valid && alu_exec_is_store;
    assign lsq_data_update_tag = rob_to_lsq_mem[alu_exec_tag[3 +: ROB_SLOT_WIDTH]];

    wire rs_issue_is_mdu =
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MUL) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MULH) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MULHSU) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MULHU) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_DIV) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_DIVU) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_REM) ||
        (rs_issue_op[0 +: `RV32IM_OP_WIDTH] == `RV32IM_OP_REMU);
    assign mdu_issue_valid = rs_issue_valid[0] && rs_issue_is_mdu;
    // Issue acceptance is independent from completion/CDB backpressure.  The
    // previous wiring reused alu_exec_ready for both directions, creating a
    // combinational loop through the reservation station's issue_valid path.
    assign rs_issue_ready = {{(BE_WIDTH-1){1'b0}}, (rs_issue_is_mdu ? mdu_issue_ready : alu_issue_ready)};
    assign mdu_completion_ready = mdu_rank < 3 ? producer_ready[mdu_rank] : 1'b0;
    assign lsq_load_complete_ready = load_rank < 3 ? producer_ready[load_rank] : 1'b0;

    assign rob_completion_valid = completion_valid_r;
    assign rob_completion_tag = completion_tag_r;
    assign rob_completion_value = completion_value_r;
    assign rob_completion_done = completion_done_r;
    assign rob_completion_error = completion_error_r;
    assign rob_completion_store_addr = completion_store_addr_r;
    assign rob_completion_store_mask = completion_store_mask_r;
    assign rob_completion_store_data = completion_store_data_r;

    // Rebuild recovery rename state from the mappings and ROB entries that
    // survive the branch.  Old physical mappings remain reserved until their
    // owning instruction commits, preventing duplicate free-list entries.
    always @* begin
        recovery_rat_state = rob_checkpoint_restore[CHECK_RAT_WIDTH-1:0];
        recovery_free_list_state = {CHECK_FREE_WIDTH{1'b0}};
        recovery_reserved = {PHYS_REGS{1'b0}};
        recovery_reserved[0] = 1'b1;
        recovery_branch_slot = branch_pending_tag[3 +: ROB_SLOT_WIDTH];
        if (rob_rd_we_mem[recovery_branch_slot] && (rob_rd_mem[recovery_branch_slot] != 0))
            recovery_rat_state[(rob_rd_mem[recovery_branch_slot]*PAW) +: PAW] =
                rob_phys_mem[recovery_branch_slot];
        for (recovery_map_index = 0; recovery_map_index < 32; recovery_map_index = recovery_map_index + 1) begin
            recovery_phys_index = recovery_rat_state[(recovery_map_index*PAW) +: PAW];
            if ((recovery_phys_index >= 0) && (recovery_phys_index < PHYS_REGS))
                recovery_reserved[recovery_phys_index] = 1'b1;
        end
        recovery_branch_age = recovery_branch_slot - rob_head;
        if (recovery_branch_age < 0) recovery_branch_age = recovery_branch_age + ROB_ENTRIES;
        for (recovery_slot_index = 0; recovery_slot_index < ROB_ENTRIES; recovery_slot_index = recovery_slot_index + 1) begin
            recovery_slot_age = recovery_slot_index - rob_head;
            if (recovery_slot_age < 0) recovery_slot_age = recovery_slot_age + ROB_ENTRIES;
            if ((recovery_slot_age <= recovery_branch_age) && (recovery_slot_age < rob_occupancy) &&
                rob_rd_we_mem[recovery_slot_index] &&
                (rob_old_phys_mem[recovery_slot_index] != 0) &&
                (rob_old_phys_mem[recovery_slot_index] < PHYS_REGS))
                recovery_reserved[rob_old_phys_mem[recovery_slot_index]] = 1'b1;
        end
        recovery_free_index = 0;
        for (recovery_phys_index = 1; recovery_phys_index < PHYS_REGS; recovery_phys_index = recovery_phys_index + 1) begin
            if (!recovery_reserved[recovery_phys_index]) begin
                recovery_free_list_state[(recovery_free_index*PAW) +: PAW] = recovery_phys_index[PAW-1:0];
                recovery_free_index = recovery_free_index + 1;
            end
        end
        recovery_free_count = recovery_free_index[FREE_COUNT_WIDTH-1:0];
        if (recovery_free_index >= FREE_SLOTS)
            recovery_free_tail = {FREE_PTR_WIDTH{1'b0}};
        else
            recovery_free_tail = recovery_free_index[FREE_PTR_WIDTH-1:0];
    end

    // External flushes clear the station.  A branch recovery clears only
    // entries younger than the resolving branch; older unresolved work still
    // belongs to the retained ROB prefix and must remain executable.
    always @* begin
        rs_flush_kill_mask = {RS_ENTRIES{1'b0}};
        recovery_rs_rob_slot = 0;
        recovery_rs_branch_slot = branch_pending_tag[3 +: ROB_SLOT_WIDTH];
        recovery_rs_age = 0;
        recovery_rs_branch_age = recovery_rs_branch_slot - rob_head;
        if (recovery_rs_branch_age < 0)
            recovery_rs_branch_age = recovery_rs_branch_age + ROB_ENTRIES;
        if (flush_i) begin
            rs_flush_kill_mask = {RS_ENTRIES{1'b1}};
        end else if (rob_recovery_accept) begin
            for (recovery_rs_index = 0; recovery_rs_index < RS_ENTRIES; recovery_rs_index = recovery_rs_index + 1) begin
                recovery_rs_rob_slot = rs_entry_rob_tag[(recovery_rs_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                recovery_rs_age = recovery_rs_rob_slot - rob_head;
                if (recovery_rs_age < 0) recovery_rs_age = recovery_rs_age + ROB_ENTRIES;
                if (rs_entry_valid[recovery_rs_index] &&
                    (!rs_entry_rob_tag[recovery_rs_index*TAG_WIDTH] ||
                     (recovery_rs_age > recovery_rs_branch_age) ||
                     (recovery_rs_age >= rob_occupancy)))
                    rs_flush_kill_mask[recovery_rs_index] = 1'b1;
            end
        end
    end

    // Completions may be queued out of program order.  Recovery invalidates
    // only entries younger than the resolving branch so retained work still
    // reaches the ROB while reclaimed physical registers cannot be poisoned
    // by wrong-path writeback.
    always @* begin
        completion_kill_mask = 16'b0;
        recovery_completion_rob_slot = 0;
        recovery_completion_age = 0;
        recovery_completion_branch_age = branch_pending_tag[3 +: ROB_SLOT_WIDTH] - rob_head;
        if (recovery_completion_branch_age < 0)
            recovery_completion_branch_age = recovery_completion_branch_age + ROB_ENTRIES;
        if (rob_recovery_accept) begin
            for (recovery_completion_index = 0; recovery_completion_index < 16;
                 recovery_completion_index = recovery_completion_index + 1) begin
                recovery_completion_rob_slot =
                    completion_entry_tag[(recovery_completion_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                recovery_completion_age = recovery_completion_rob_slot - rob_head;
                if (recovery_completion_age < 0)
                    recovery_completion_age = recovery_completion_age + ROB_ENTRIES;
                if (completion_entry_valid[recovery_completion_index] &&
                    (!completion_entry_tag[recovery_completion_index*TAG_WIDTH] ||
                     (recovery_completion_age > recovery_completion_branch_age) ||
                     (recovery_completion_age >= rob_occupancy)))
                    completion_kill_mask[recovery_completion_index] = 1'b1;
            end
        end
    end

    // Rename and PRF form the operand/producer boundary.
    rv32_rename_unit #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS)) rename (
        .clk_i(clk_i), .reset_i(reset_i), .rename_ready_i(!halted_o && !flush_i && !rob_recovery_accept),
        .decoded_valid_i(dec_valid), .decoded_rd_we_i(dec_rd_we), .decoded_rs1_used_i(dec_rs1_used), .decoded_rs2_used_i(dec_rs2_used),
        .decoded_rs_need_i(dec_rs_need), .decoded_lsq_need_i(dec_lsq_need), .decoded_rd_i(dec_rd), .decoded_rs1_i(dec_rs1), .decoded_rs2_i(dec_rs2),
        .rob_free_count_i(rob_free_count), .rs_free_count_i(rs_free_count), .lsq_free_count_i(lsq_free_count),
        .rename_valid_o(rename_valid), .rename_rd_we_o(rename_rd_we), .rename_rd_o(rename_rd), .rename_old_phys_o(rename_old_phys), .rename_new_phys_o(rename_new_phys),
        .rename_rs1_phys_o(rename_rs1_phys), .rename_rs2_phys_o(rename_rs2_phys), .rename_count_o(rename_count), .rat_state_o(rat_state), .rrat_state_o(rrat_state),
        .free_list_state_o(free_list_state), .free_head_o(free_head), .free_tail_o(free_tail), .free_count_o(free_count),
        .commit_valid_i(rob_commit_valid[0] && commit_ready_i), .commit_rd_we_i(rob_commit_rd_we), .commit_rd_i(rob_commit_rd),
        .commit_old_phys_i({{(BE_WIDTH*PAW-PAW){1'b0}}, rob_old_phys_mem[rob_commit_tag[3 +: ROB_SLOT_WIDTH]]}),
        .commit_new_phys_i({{(BE_WIDTH*PAW-PAW){1'b0}}, rob_phys_mem[rob_commit_tag[3 +: ROB_SLOT_WIDTH]]}),
        .restore_valid_i(rob_checkpoint_restore_valid), .restore_rat_i(recovery_rat_state),
        .restore_free_list_i(recovery_free_list_state), .restore_free_head_i({FREE_PTR_WIDTH{1'b0}}),
        .restore_free_tail_i(recovery_free_tail), .restore_free_count_i(recovery_free_count)
    );

    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS)) prf (
        .clk_i(clk_i), .reset_i(reset_i), .read_phys_i(prf_read_phys), .read_data_o(prf_read_data), .read_ready_o(prf_read_ready),
        .alloc_phys_i(prf_alloc_phys), .alloc_valid_i(prf_alloc_valid), .write_phys_i(prf_write_phys), .write_data_i(prf_write_data), .write_valid_i(prf_write_valid)
    );

    // Checkpoint state is captured at branch allocation and restored directly
    // into rename on recovery.
    always @* begin
        checkpoint_pack = {CHECKPOINT_WIDTH{1'b0}};
        checkpoint_pack[CHECK_RAT_WIDTH-1:0] = rat_state;
        checkpoint_pack[CHECK_RAT_WIDTH+CHECK_FREE_WIDTH-1:CHECK_RAT_WIDTH] = free_list_state;
        checkpoint_pack[CHECK_RAT_WIDTH+CHECK_FREE_WIDTH+FREE_PTR_WIDTH-1:CHECK_RAT_WIDTH+CHECK_FREE_WIDTH] = free_head;
        checkpoint_pack[CHECK_RAT_WIDTH+CHECK_FREE_WIDTH+2*FREE_PTR_WIDTH-1:CHECK_RAT_WIDTH+CHECK_FREE_WIDTH+FREE_PTR_WIDTH] = free_tail;
        checkpoint_pack[CHECK_RAT_WIDTH+CHECK_FREE_WIDTH+2*FREE_PTR_WIDTH+FREE_COUNT_WIDTH-1:CHECK_RAT_WIDTH+CHECK_FREE_WIDTH+2*FREE_PTR_WIDTH] = free_count;
        rob_alloc_checkpoint = {BE_WIDTH{checkpoint_pack}};
        rob_alloc_pc = { {(BE_WIDTH-1)*32{1'b0}}, trace_pc_i };
        rob_alloc_inst = { {(BE_WIDTH-1)*32{1'b0}}, trace_inst_i };
        rob_alloc_rd = { {(BE_WIDTH-1)*5{1'b0}}, trace_rd_i };
        rob_alloc_old_phys = { {(BE_WIDTH-1)*PAW{1'b0}}, rename_old_phys[PAW-1:0] };
        rob_alloc_new_phys = { {(BE_WIDTH-1)*PAW{1'b0}}, rename_new_phys[PAW-1:0] };
        rob_alloc_is_store = { {(BE_WIDTH-1){1'b0}}, trace_is_store_i };
        rob_alloc_is_branch = { {(BE_WIDTH-1){1'b0}}, trace_is_branch_i };
        rob_alloc_is_halt = { {(BE_WIDTH-1){1'b0}}, trace_is_halt_i };
        rob_alloc_is_error = { {(BE_WIDTH-1){1'b0}}, trace_is_error_i };
    end

    rv32_rob #(.BE_WIDTH(BE_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .PHYS_ADDR_WIDTH(PAW), .TAG_WIDTH(TAG_WIDTH), .CHECKPOINT_WIDTH(CHECKPOINT_WIDTH)) rob (
        .clk_i(clk_i), .reset_i(reset_i), .alloc_valid_i(rob_alloc_valid), .alloc_pc_i(rob_alloc_pc), .alloc_inst_i(rob_alloc_inst), .alloc_rd_i(rob_alloc_rd),
        .alloc_rd_we_i(rename_rd_we), .alloc_old_phys_i(rob_alloc_old_phys), .alloc_new_phys_i(rob_alloc_new_phys), .alloc_is_store_i(rob_alloc_is_store),
        .alloc_is_branch_i(rob_alloc_is_branch), .alloc_is_halt_i(rob_alloc_is_halt), .alloc_is_error_i(rob_alloc_is_error), .alloc_checkpoint_i(rob_alloc_checkpoint),
        .alloc_ready_o(rob_alloc_ready), .alloc_fire_o(rob_alloc_fire), .alloc_tag_o(rob_alloc_tag), .alloc_count_o(rob_alloc_count),
        .completion_valid_i(rob_completion_valid), .completion_tag_i(rob_completion_tag), .completion_value_i(rob_completion_value), .completion_done_i(rob_completion_done), .completion_error_i(rob_completion_error),
        .completion_store_addr_i(rob_completion_store_addr), .completion_store_mask_i(rob_completion_store_mask), .completion_store_data_i(rob_completion_store_data),
        .commit_ready_i(commit_ready_i), .commit_valid_o(rob_commit_valid), .commit_rd_we_o(rob_commit_rd_we), .commit_rd_o(rob_commit_rd), .commit_pc_o(rob_commit_pc), .commit_inst_o(rob_commit_inst), .commit_value_o(rob_commit_value), .commit_is_store_o(rob_commit_is_store),
        .commit_store_addr_o(rob_commit_store_addr), .commit_store_mask_o(rob_commit_store_mask), .commit_store_data_o(rob_commit_store_data), .commit_tag_o(rob_commit_tag),
        .store_commit_valid_o(rob_store_commit_valid), .store_commit_ready_i(rob_store_commit_ready), .store_commit_tag_o(rob_store_commit_tag), .store_commit_addr_o(rob_store_commit_addr), .store_commit_mask_o(rob_store_commit_mask), .store_commit_data_o(rob_store_commit_data), .store_ack_valid_i(rob_store_ack_valid), .store_ack_tag_i(rob_store_ack_tag), .store_ack_error_i(lsq_store_ack_error),
        .recovery_valid_i({ {(BE_WIDTH-1){1'b0}}, branch_pending }), .recovery_tag_i({ {(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, branch_pending_tag }), .recovery_pc_i({ {(BE_WIDTH-1)*32{1'b0}}, branch_pending_pc }),
        .recovery_accept_o(rob_recovery_accept), .redirect_valid_o(rob_redirect_valid), .redirect_pc_o(rob_redirect_pc), .redirect_epoch_o(rob_redirect_epoch), .checkpoint_restore_valid_o(rob_checkpoint_restore_valid), .checkpoint_restore_o(rob_checkpoint_restore), .halted_o(halted_o), .error_o(error_o), .return_value_o(return_value_o), .head_o(rob_head), .tail_o(rob_tail), .occupancy_o(rob_occupancy)
    );

    rv32_reservation_station #(.BE_WIDTH(BE_WIDTH), .ENTRIES(RS_ENTRIES), .TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW)) rs (
        .clk_i(clk_i), .reset_i(reset_i), .alloc_valid_i(rs_alloc_valid), .alloc_op_i({{(BE_WIDTH-1)*`RV32IM_OP_WIDTH{1'b0}}, trace_op_i}), .alloc_pc_i({{(BE_WIDTH-1)*32{1'b0}}, trace_pc_i}), .alloc_rob_tag_i(rob_alloc_tag), .alloc_target_live_i(rob_alloc_valid), .alloc_phys_rd_i(rename_new_phys),
        .alloc_src1_value_i({{(BE_WIDTH-1)*32{1'b0}}, prf_read_data[31:0]}), .alloc_src1_tag_i({{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, rs_src1_tag}), .alloc_src1_ready_i({{(BE_WIDTH-1){1'b0}}, rs_src1_ready}), .alloc_src2_value_i({{(BE_WIDTH-1)*32{1'b0}}, prf_read_data[63:32]}), .alloc_src2_tag_i({{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, rs_src2_tag}), .alloc_src2_ready_i({{(BE_WIDTH-1){1'b0}}, rs_src2_ready}), .alloc_store_data_i({{(BE_WIDTH-1)*128{1'b0}}, trace_store_data_i}), .alloc_ready_o(rs_alloc_ready), .alloc_fire_o(rs_alloc_fire), .alloc_count_o(rs_alloc_count),
        .wake_valid_i(rs_wake_valid), .wake_tag_i(rs_wake_tag), .wake_value_i(rs_wake_value), .issue_ready_i(rs_issue_ready), .issue_valid_o(rs_issue_valid), .issue_op_o(rs_issue_op), .issue_pc_o(rs_issue_pc), .issue_rob_tag_o(rs_issue_tag), .issue_phys_rd_o(rs_issue_phys), .issue_src1_value_o(rs_issue_src1), .issue_src2_value_o(rs_issue_src2), .issue_store_data_o(rs_issue_store), .issue_slot_o(rs_issue_slot), .flush_valid_i(flush_i || rob_recovery_accept), .flush_kill_mask_i(rs_flush_kill_mask), .entry_valid_o(rs_entry_valid), .entry_rob_tag_o(rs_entry_rob_tag), .occupancy_o(rs_occupancy)
    );

    rv32i_alu #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW)) alu (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i || rob_recovery_accept), .issue_valid_i(rs_issue_valid[0] && !mdu_issue_valid), .issue_ready_o(alu_issue_ready), .issue_op_i(rs_issue_op[0 +: `RV32IM_OP_WIDTH]), .issue_pc_i(rs_issue_pc[31:0]), .issue_imm_i(rs_issue_imm), .issue_src1_value_i(rs_issue_src1[31:0]), .issue_src2_value_i(rs_issue_src2[31:0]), .issue_store_data_i(rs_issue_store[127:0]), .issue_phys_rd_i(rs_issue_phys[PAW-1:0]), .issue_rob_tag_i(rs_issue_tag[TAG_WIDTH-1:0]), .issue_epoch_i(4'b0), .issue_target_live_i(rs_issue_valid[0]), .issue_pred_taken_i(rs_issue_pred_taken), .issue_pred_target_i(rs_issue_pred_target), .issue_pred_kind_i(rs_issue_pred_kind), .issue_mem_size_i(rs_issue_mem_size), .issue_mem_unsigned_i(rs_issue_mem_unsigned), .exec_valid_o(alu_exec_valid), .exec_ready_i(alu_exec_ready), .exec_value_o(alu_exec_value), .exec_phys_rd_o(alu_exec_phys), .exec_rob_tag_o(alu_exec_tag), .exec_epoch_o(), .exec_rd_we_o(alu_exec_rd_we), .exec_is_branch_o(alu_exec_is_branch), .exec_branch_taken_o(alu_exec_branch_taken), .exec_branch_target_o(alu_exec_branch_target), .exec_redirect_valid_o(alu_exec_redirect_valid), .exec_redirect_pc_o(alu_exec_redirect_pc), .exec_is_memory_o(alu_exec_is_memory), .exec_is_load_o(alu_exec_is_load), .exec_is_store_o(alu_exec_is_store), .exec_mem_addr_o(alu_exec_mem_addr), .exec_mem_size_o(alu_exec_mem_size), .exec_mem_unsigned_o(alu_exec_mem_unsigned), .exec_store_data_o(alu_exec_store_data), .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}})
    );

    rv32m_mdu_reservation_station #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW)) mdu (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i || rob_recovery_accept), .issue_valid_i(mdu_issue_valid), .issue_op_i(rs_issue_op[0 +: `RV32IM_OP_WIDTH]), .issue_src1_i(rs_issue_src1[31:0]), .issue_src2_i(rs_issue_src2[31:0]), .issue_rob_tag_i(rs_issue_tag[TAG_WIDTH-1:0]), .issue_phys_rd_i(rs_issue_phys[PAW-1:0]), .issue_target_live_i(1'b1), .issue_ready_o(mdu_issue_ready), .completion_valid_o(mdu_completion_valid), .completion_ready_i(mdu_completion_ready), .completion_value_o(mdu_completion_value), .completion_rob_tag_o(mdu_completion_tag), .completion_phys_rd_o(mdu_completion_phys), .completion_rd_we_o(mdu_completion_rd_we), .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}})
    );

    rv32_lsq #(.BE_WIDTH(BE_WIDTH), .LSQ_ENTRIES(LSQ_ENTRIES), .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH), .ROB_ENTRIES(ROB_ENTRIES)) lsq (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_valid_i(rob_recovery_accept), .recovery_tag_i(branch_pending_tag), .recovery_head_i(rob_head), .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1'b0}}, rob_occupancy}), .alloc_valid_i(lsq_alloc_valid), .alloc_ready_o(lsq_alloc_ready), .alloc_fire_o(lsq_alloc_fire), .alloc_count_o(lsq_alloc_count), .alloc_lsq_tag_o(lsq_alloc_tag), .alloc_is_load_i({{(BE_WIDTH-1){1'b0}}, trace_is_load_i}), .alloc_is_store_i({{(BE_WIDTH-1){1'b0}}, trace_is_store_i}), .alloc_rob_tag_i(rob_alloc_tag), .alloc_size_i({{(BE_WIDTH-1)*2{1'b0}}, trace_mem_size_i}), .alloc_unsigned_i({{(BE_WIDTH-1){1'b0}}, trace_mem_unsigned_i}), .alloc_addr_valid_i({BE_WIDTH{1'b0}}), .alloc_addr_i({BE_WIDTH*32{1'b0}}), .alloc_data_valid_i({{(BE_WIDTH-1){1'b0}}, trace_is_store_i}), .alloc_store_data_i({{(BE_WIDTH-1)*128{1'b0}}, trace_store_data_i}), .alloc_store_mask_i({BE_WIDTH*16{1'b0}}), .addr_update_valid_i({{(BE_WIDTH-1){1'b0}}, lsq_addr_update_valid}), .addr_update_tag_i({{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, lsq_addr_update_tag}), .addr_update_i({{(BE_WIDTH-1)*32{1'b0}}, lsq_addr_update}), .data_update_valid_i({{(BE_WIDTH-1){1'b0}}, lsq_data_update_valid}), .data_update_tag_i({{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, lsq_data_update_tag}), .data_update_i({{(BE_WIDTH-1)*128{1'b0}}, alu_exec_store_data}), .data_mask_update_i({BE_WIDTH*16{1'b0}}), .wakeup_valid_i({BE_WIDTH{1'b0}}), .wakeup_tag_i({BE_WIDTH*TAG_WIDTH{1'b0}}), .wakeup_value_i({BE_WIDTH*128{1'b0}}), .store_commit_valid_i(rob_store_commit_valid), .store_commit_ready_o(rob_store_commit_ready), .store_commit_rob_tag_i(rob_store_commit_tag), .dcache_req_valid_o(dcache_req_valid_o), .dcache_req_ready_i(dcache_req_ready_i), .dcache_req_is_load_o(dcache_req_is_load_o), .dcache_req_is_store_o(dcache_req_is_store_o), .dcache_req_addr_o(dcache_req_addr_o), .dcache_req_size_o(dcache_req_size_o), .dcache_req_unsigned_o(dcache_req_unsigned_o), .dcache_req_mask_o(dcache_req_mask_o), .dcache_req_wdata_o(dcache_req_wdata_o), .dcache_req_rob_tag_o(dcache_req_rob_tag_o), .dcache_req_lsq_tag_o(dcache_req_lsq_tag_o), .dcache_resp_valid_i(dcache_resp_valid_i), .dcache_resp_ready_o(dcache_resp_ready_o), .dcache_resp_lsq_tag_i(dcache_resp_lsq_tag_i), .dcache_resp_addr_i(dcache_resp_addr_i), .dcache_resp_line_data_i(dcache_resp_line_data_i), .dcache_resp_word_data_i(dcache_resp_word_data_i), .dcache_resp_line_valid_i(dcache_resp_line_valid_i), .dcache_resp_error_i(dcache_resp_error_i), .load_complete_valid_o(lsq_load_complete_valid), .load_complete_ready_i(lsq_load_complete_ready), .load_complete_rob_tag_o(lsq_load_complete_tag), .load_complete_lsq_tag_o(lsq_load_complete_lsq_tag), .load_complete_value_o(lsq_load_complete_value), .load_complete_error_o(lsq_load_complete_error), .dcache_store_ack_valid_i(dcache_store_ack_valid_i), .dcache_store_ack_lsq_tag_i(dcache_store_ack_lsq_tag_i), .dcache_store_ack_error_i(dcache_store_ack_error_i), .store_ack_valid_o(lsq_store_ack_valid), .store_ack_ready_i(1'b1), .store_ack_rob_tag_o(lsq_store_ack_rob_tag), .store_ack_lsq_tag_o(lsq_store_ack_lsq_tag), .store_ack_error_o(lsq_store_ack_error), .occupancy_o(lsq_occupancy), .head_o(), .tail_o()
    );

    // Compact the three completion candidates into the completion network's
    // required contiguous source prefix while preserving ALU > MDU > LSQ.
    always @* begin
        producer_valid_r = 3'b0; producer_target_live_r = 3'b0; producer_rd_we_r = 3'b0; producer_store_r = 3'b0; producer_branch_r = 3'b0; producer_taken_r = 3'b0; producer_redirect_r = 3'b0; producer_memory_r = 3'b0; producer_load_r = 3'b0;
        producer_tag_r = 0; producer_phys_r = 0; producer_value_r = 0; producer_addr_r = 0; producer_branch_target_r = 0; producer_store_data_r = 0;
        producer_count = 0; alu_rank = 3; mdu_rank = 3; load_rank = 3;
        if (alu_exec_valid && (!alu_exec_is_load || alu_exec_is_store)) begin
            alu_rank = producer_count; producer_valid_r[producer_count] = 1'b1; producer_target_live_r[producer_count] = 1'b1; producer_tag_r[producer_count*TAG_WIDTH +: TAG_WIDTH] = alu_exec_tag; producer_phys_r[producer_count*PAW +: PAW] = alu_exec_phys; producer_value_r[producer_count*32 +: 32] = alu_exec_value; producer_addr_r[producer_count*32 +: 32] = alu_exec_mem_addr; producer_branch_target_r[producer_count*32 +: 32] = alu_exec_branch_target; producer_store_data_r[producer_count*128 +: 128] = alu_exec_store_data; producer_rd_we_r[producer_count] = alu_exec_rd_we; producer_store_r[producer_count] = alu_exec_is_store; producer_branch_r[producer_count] = alu_exec_is_branch; producer_taken_r[producer_count] = alu_exec_branch_taken; producer_redirect_r[producer_count] = alu_exec_redirect_valid; producer_memory_r[producer_count] = alu_exec_is_memory; producer_count = producer_count + 1;
        end
        if (mdu_completion_valid) begin
            mdu_rank = producer_count; producer_valid_r[producer_count] = 1'b1; producer_target_live_r[producer_count] = 1'b1; producer_tag_r[producer_count*TAG_WIDTH +: TAG_WIDTH] = mdu_completion_tag; producer_phys_r[producer_count*PAW +: PAW] = mdu_completion_phys; producer_value_r[producer_count*32 +: 32] = mdu_completion_value; producer_rd_we_r[producer_count] = mdu_completion_rd_we; producer_count = producer_count + 1;
        end
        if (lsq_load_complete_valid) begin
            load_rank = producer_count; producer_valid_r[producer_count] = 1'b1; producer_target_live_r[producer_count] = 1'b1; producer_tag_r[producer_count*TAG_WIDTH +: TAG_WIDTH] = lsq_load_complete_tag; producer_phys_r[producer_count*PAW +: PAW] = lsq_phys_mem[lsq_load_complete_lsq_tag[3 +: LSQ_SLOT_WIDTH]]; producer_value_r[producer_count*32 +: 32] = lsq_load_complete_value; producer_rd_we_r[producer_count] = 1'b1; producer_load_r[producer_count] = 1'b1; producer_memory_r[producer_count] = 1'b1; producer_count = producer_count + 1;
        end
        producer_recovery_rob_slot = 0;
        producer_recovery_age = 0;
        producer_recovery_branch_age = branch_pending_tag[3 +: ROB_SLOT_WIDTH] - rob_head;
        if (producer_recovery_branch_age < 0)
            producer_recovery_branch_age = producer_recovery_branch_age + ROB_ENTRIES;
        if (rob_recovery_accept) begin
            for (producer_recovery_index = 0; producer_recovery_index < 3;
                 producer_recovery_index = producer_recovery_index + 1) begin
                producer_recovery_rob_slot =
                    producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                producer_recovery_age = producer_recovery_rob_slot - rob_head;
                if (producer_recovery_age < 0)
                    producer_recovery_age = producer_recovery_age + ROB_ENTRIES;
                if (producer_valid_r[producer_recovery_index] &&
                    (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                     (producer_recovery_age > producer_recovery_branch_age) ||
                     (producer_recovery_age >= rob_occupancy)))
                    producer_target_live_r[producer_recovery_index] = 1'b0;
            end
        end
    end
    assign producer_valid = producer_valid_r;
    assign producer_ready = producer_ready_r;
    assign producer_tag = producer_tag_r;
    assign producer_phys = producer_phys_r;
    assign producer_value = producer_value_r;
    assign producer_addr = producer_addr_r;
    assign producer_branch_target = producer_branch_target_r;
    assign producer_store_data = producer_store_data_r;
    assign producer_rd_we = producer_rd_we_r;
    assign producer_store = producer_store_r;
    assign producer_branch = producer_branch_r;
    assign producer_taken = producer_taken_r;
    assign producer_redirect = producer_redirect_r;
    assign producer_memory = producer_memory_r;
    assign producer_load = producer_load_r;
    assign alu_exec_ready = alu_exec_is_load ? 1'b1 : (alu_rank < 3 ? producer_ready[alu_rank] : 1'b0);

    rv32_completion_network #(.BE_WIDTH(BE_WIDTH), .SOURCES(3), .FIFO_DEPTH(16), .TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW)) completion (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .kill_valid_i(rob_recovery_accept), .kill_mask_i(completion_kill_mask), .producer_valid_i(producer_valid), .producer_ready_o(producer_ready_r), .producer_tag_i(producer_tag), .producer_phys_rd_i(producer_phys), .producer_value_i(producer_value), .producer_addr_i(producer_addr), .producer_branch_target_i(producer_branch_target), .producer_store_data_i(producer_store_data), .producer_rd_we_i(producer_rd_we), .producer_is_store_i(producer_store), .producer_is_branch_i(producer_branch), .producer_branch_taken_i(producer_taken), .producer_redirect_valid_i(producer_redirect), .producer_is_memory_i(producer_memory), .producer_is_load_i(producer_load), .producer_target_live_i(producer_target_live_r), .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}}), .cdb_valid_o(cdb_valid), .cdb_ready_i(cdb_ready), .cdb_tag_o(cdb_tag), .cdb_phys_rd_o(cdb_phys), .cdb_value_o(cdb_value), .cdb_addr_o(cdb_addr), .cdb_branch_target_o(cdb_branch_target), .cdb_store_data_o(cdb_store_data), .cdb_rd_we_o(cdb_rd_we), .cdb_is_store_o(cdb_is_store), .cdb_is_branch_o(cdb_is_branch), .cdb_branch_taken_o(cdb_branch_taken), .cdb_redirect_valid_o(cdb_redirect_valid), .cdb_is_memory_o(cdb_is_memory), .cdb_is_load_o(cdb_is_load), .prf_write_valid_o(prf_write_valid), .prf_write_tag_o(prf_wb_tag), .prf_write_phys_rd_o(prf_write_phys), .prf_write_value_o(prf_write_data), .rob_ready_valid_o(rob_wb_valid), .rob_ready_tag_o(rob_wb_tag), .rob_ready_value_o(rob_wb_value), .wakeup_valid_o(wake_wb_valid), .wakeup_tag_o(wake_wb_tag), .wakeup_value_o(wake_wb_value), .entry_valid_o(completion_entry_valid), .entry_tag_o(completion_entry_tag), .occupancy_o()
    );
    assign rs_wake_valid = wake_wb_valid;
    assign rs_wake_tag = wake_wb_tag;
    assign rs_wake_value = wake_wb_value;

    always @* begin
        completion_valid_r = rob_wb_valid;
        completion_tag_r = rob_wb_tag;
        completion_value_r = rob_wb_value;
        completion_done_r = rob_wb_valid;
        completion_error_r = {BE_WIDTH{1'b0}};
        completion_store_addr_r = cdb_addr;
        completion_store_mask_r = {BE_WIDTH*16{1'b0}};
        completion_store_data_r = cdb_store_data;
        for (completion_lane = 0; completion_lane < BE_WIDTH; completion_lane = completion_lane + 1) begin
            completion_slot = rob_wb_tag[(completion_lane*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
            if (rob_wb_valid[completion_lane] && (completion_slot < ROB_ENTRIES))
                completion_error_r[completion_lane] = load_error_mem[completion_slot];
        end
        if (branch_pending) begin
            completion_valid_r = {{(BE_WIDTH-1){1'b0}}, 1'b1};
            completion_tag_r = {{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, branch_pending_tag};
            completion_value_r = {{(BE_WIDTH-1)*32{1'b0}}, branch_pending_value};
            completion_done_r = {{(BE_WIDTH-1){1'b0}}, 1'b1};
            completion_error_r = {BE_WIDTH{1'b0}};
        end
    end

    assign rob_store_ack_valid = lsq_store_ack_valid;
    assign rob_store_ack_tag = lsq_store_ack_rob_tag;

    always @(posedge clk_i) begin
        if (reset_i) begin
            branch_pending <= 1'b0;
            branch_pending_tag <= 0;
            branch_pending_value <= 0;
            branch_pending_pc <= 0;
            branch_pending_source_pc <= 0;
            branch_pending_kind <= `RV32IM_PRED_NONE;
            branch_pending_taken <= 1'b0;
            branch_pending_target <= 0;
            branch_pending_pred_taken <= 1'b0;
            branch_pending_pred_target <= 0;
            for (map_index = 0; map_index < ROB_ENTRIES; map_index = map_index + 1) begin
                rob_to_lsq_mem[map_index] <= 0;
                rob_phys_mem[map_index] <= 0;
                rob_old_phys_mem[map_index] <= 0;
                rob_rd_mem[map_index] <= 0;
                rob_rd_we_mem[map_index] <= 1'b0;
                rob_pc_mem[map_index] <= 0;
            end
            for (map_index = 0; map_index < LSQ_ENTRIES; map_index = map_index + 1)
                lsq_phys_mem[map_index] <= 0;
            for (map_phys_slot = 0; map_phys_slot < PHYS_REGS; map_phys_slot = map_phys_slot + 1)
                phys_tag_mem[map_phys_slot] <= 0;
            for (map_index = 0; map_index < ROB_ENTRIES; map_index = map_index + 1)
                load_error_mem[map_index] <= 1'b0;
            for (map_index = 0; map_index < ROB_ENTRIES; map_index = map_index + 1) begin
                rob_imm_mem[map_index] <= 0;
                rob_pred_taken_mem[map_index] <= 1'b0;
                rob_pred_target_mem[map_index] <= 0;
                rob_pred_kind_mem[map_index] <= 0;
                rob_mem_size_mem[map_index] <= `RV32IM_MEM_WORD;
                rob_mem_unsigned_mem[map_index] <= 1'b0;
            end
        end else begin
            if (rob_recovery_accept && branch_pending) begin
                // The branch is retained in the ROB by recovery and will
                // commit on the following cycle; stop reissuing recovery.
                branch_pending <= 1'b0;
            end else if (!branch_pending && alu_exec_valid && alu_exec_redirect_valid) begin
                branch_pending <= 1'b1;
                branch_pending_tag <= alu_exec_tag;
                branch_pending_value <= alu_exec_value;
                branch_pending_pc <= alu_exec_redirect_pc;
                branch_pending_source_pc <= rob_pc_mem[alu_exec_tag[3 +: ROB_SLOT_WIDTH]];
                branch_pending_kind <= rob_pred_kind_mem[alu_exec_tag[3 +: ROB_SLOT_WIDTH]];
                branch_pending_taken <= alu_exec_branch_taken;
                branch_pending_target <= alu_exec_redirect_pc;
                branch_pending_pred_taken <= rob_pred_taken_mem[alu_exec_tag[3 +: ROB_SLOT_WIDTH]];
                branch_pending_pred_target <= rob_pred_target_mem[alu_exec_tag[3 +: ROB_SLOT_WIDTH]];
            end else if (branch_pending && commit_ready_i && rob_commit_valid[0] &&
                         (rob_commit_tag[TAG_WIDTH-1:0] == branch_pending_tag)) begin
                branch_pending <= 1'b0;
            end
            if (dispatch_valid && rob_alloc_fire[0]) begin
                map_rob_slot = rob_alloc_tag[3 +: ROB_SLOT_WIDTH];
                rob_phys_mem[map_rob_slot] <= rename_new_phys[PAW-1:0];
                rob_old_phys_mem[map_rob_slot] <= rename_old_phys[PAW-1:0];
                rob_rd_mem[map_rob_slot] <= rename_rd[4:0];
                rob_rd_we_mem[map_rob_slot] <= rename_rd_we[0];
                rob_pc_mem[map_rob_slot] <= trace_pc_i;
                load_error_mem[map_rob_slot] <= 1'b0;
                rob_imm_mem[map_rob_slot] <= trace_imm_i;
                rob_pred_taken_mem[map_rob_slot] <= trace_pred_taken_i;
                rob_pred_target_mem[map_rob_slot] <= trace_pred_target_i;
                rob_pred_kind_mem[map_rob_slot] <= trace_pred_kind_i;
                rob_mem_size_mem[map_rob_slot] <= trace_mem_size_i;
                rob_mem_unsigned_mem[map_rob_slot] <= trace_mem_unsigned_i;
                if (rename_rd_we[0] && (rename_new_phys[PAW-1:0] < PHYS_REGS))
                    phys_tag_mem[rename_new_phys[PAW-1:0]] <= rob_alloc_tag[TAG_WIDTH-1:0];
                if (trace_is_load_i || trace_is_store_i) begin
                    map_lsq_slot = lsq_alloc_tag[3 +: LSQ_SLOT_WIDTH];
                    rob_to_lsq_mem[map_rob_slot] <= lsq_alloc_tag[0 +: TAG_WIDTH];
                    lsq_phys_mem[map_lsq_slot] <= rename_new_phys[PAW-1:0];
                end
            end
            if (lsq_load_complete_valid && lsq_load_complete_ready && lsq_load_complete_error) begin
                map_rob_slot = lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH];
                if (map_rob_slot < ROB_ENTRIES)
                    load_error_mem[map_rob_slot] <= 1'b1;
            end
        end
    end
endmodule
