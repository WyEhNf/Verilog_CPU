`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parameterized out-of-order backend closure.  The decoded input and
// CommitRecord output are contiguous BE_WIDTH-wide bundles.
// Rename, PRF, RS, ALU/MDU, completion, ROB and LSQ remain independent blocks
// connected by their frozen valid/ready/tag contracts.
module rv32_backend_joint #(
    parameter integer ISSUE_PIPELINE = 0,
    // Execution registers need selective cancellation even when RS issues
    // directly. Default retains the standalone configuration relation.
    parameter integer LOCAL_EXEC_RECOVERY = (ISSUE_PIPELINE!=0),
    parameter integer DISPATCH_PIPELINE = 0,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer RS_ENTRIES = 8,
    parameter integer LSQ_ENTRIES = 8,
    parameter integer LSQ_STORE_ADMISSION_BYPASS = 0,
    // 0: ordinary AGU; 1: allocate ready address and retain AGU;
    // 2 or above: skip redundant RS/AGU work only for a qualified ready load.
    parameter integer EARLY_LOAD_ADDRESS = 0,
    parameter integer LOAD_COMPLETION_BYPASS = 0,
    parameter integer LOAD_WAKE_BYPASS = 0,
    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,
    parameter integer LSQ_RECLAIM_WIDTH = 1,
    parameter integer LSQ_SECOND_REPORT_RECLAIM = 0,
    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 0,
    parameter integer LSQ_PICK_LOCAL_VALIDITY = 0,
    parameter integer LSQ_FORWARD_ONEHOT = 0,
    parameter integer LSQ_PICK_ONEHOT = 0,
    parameter integer EARLY_FRONT_REDIRECT = 0,
    // Capture knows valid+redirect+!pending. Use the exact corresponding
    // redirect-ready priority, independently of ordinary completion ready.
    parameter integer BRANCH_CAPTURE_REDIRECT_READY = 0,
    parameter integer BRANCH_CAPTURE_PHASE_VALID = 0,
    // The branch result remains captured. Apply its full qualified recovery
    // on the next edge, using the original direct ROB recovery implementation.
    parameter integer RECOVERY_DIRECT_APPLY = 0,
    // Only the fully qualified direct apply can advertise its post-edge ROB
    // capacity. Ordinary allocation credits keep their original conservative rule.
    parameter integer RECOVERY_ROB_CREDIT = 0,
    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 0,
    parameter integer RECOVERY_APPLY_OLDER_ISSUE = 0,
    parameter integer RS_ROW_RECOVERY_QUALIFICATION = 0,
    parameter integer RS_ROW_LIVE_MEMBERSHIP = 0,
    parameter integer RS_PREDECODE_ISSUE_CANCEL = 0,
    parameter integer DISPATCH_ELASTIC = 0,
    parameter integer DISPATCH_FULL_REPLACE = 0,
    parameter integer EARLY_STORE_ADDRESS = 0,
    parameter integer RS_ISSUE_METADATA = 0,
    parameter integer RS_WAKE_MUX_IMPL = 0,
    parameter integer RS_AGE_WIDTH = 32,
    parameter integer RS_ALLOC_STATIC_WRITE = 0,
    parameter integer PRF_READ_MUX_IMPL = 0,
    parameter integer RAT_READ_BYPASS = 0,
    parameter integer RENAME_RETAIN_FREE_POOL = 0,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    parameter integer ROB_COMMIT_BANKED_READ = 0,
    parameter integer LIGHT_RETIRE_PAYLOAD = 0,
    parameter integer ROB_LEGACY_HALT_PAYLOAD = 1,
    parameter integer ROB_RETURN_VALUE_ENABLE = 1,
    parameter integer ROB_MMIO_PREDECODE = 0,
    parameter integer ROB_ALLOC_BANKED_WRITE = 0,
    parameter integer ROB_UNIQUE_RECLAIM_COUNT = 0,
    parameter integer PREDICTOR_META = 0,
    parameter integer COMPACT_PRED_TARGET = 0,
    parameter integer INT_ISSUE_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer CDB_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer MUL_IMPL = 0,
    parameter integer SHIFT_IMPL = 0,
    parameter integer SHIFT_SHARED_BARREL = 0,
    parameter integer RS_PHYSICAL_WAKEUP = 0,
    parameter integer PHYS_TAG_IMPL = 0,
    parameter integer CHECKPOINT_IMPL = 0,
    parameter integer RAT_RECOVERY_IMPL = 0,
    parameter integer RAT_SUFFIX_BRANCH_MAPPING = 0,
    parameter integer STORE_BUFFERED_RETIRE = 1,
    parameter integer COMPLETION_BYPASS = 0,
    parameter integer COMPLETION_DEPTH = (BE_WIDTH <= 1) ? 4 :
                                         ((BE_WIDTH == 2) ? 8 : 16),
    parameter integer TAG_WIDTH = 1 + 2 +
        ((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) +
        `RV32IM_ROB_GENERATION_WIDTH,
    // Default preserves unrestricted standalone trace immediates. The CPU
    // enables this for its decoder's signed twelve-bit store displacement.
    parameter integer STORE_ALLOC_IMM12 = 0,
    // Independent control of the opportunistic allocation-edge address.
    // Ordinary AGU and EARLY_STORE_ADDRESS=2 shared probing remain available.
    // 0 removes the optional allocation-edge address, 1 uses the original
    // post-read adder, 2 selects parallel PRF address candidates when supported.
    parameter integer STORE_ALLOC_EARLY_ADDRESS = 1,
    parameter integer STORE_ALLOC_EARLY_DATA = 0,
    // One already-ready RAM store may complete from its actual LSQ allocation.
    // The original RS/ALU path remains for other stores and unsupported profiles.
    parameter integer FAST_STORE_COMPLETE = 0,
    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,
    parameter integer FAST_STORE_ADDRESS_PREDECODE = 0,
    parameter integer LSQ_ROB_QUERY_PREDECODE = 0,
    parameter integer LSQ_RESPONSE_QUERY_PREDECODE = 0
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,

    input  wire [BE_WIDTH-1:0]          trace_valid_i,
    output wire [BE_WIDTH-1:0]          trace_ready_o,
    input  wire [BE_WIDTH*32-1:0]       trace_pc_i,
    input  wire [BE_WIDTH*32-1:0]       trace_inst_i,
    input  wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] trace_op_i,
    input  wire [BE_WIDTH*32-1:0]       trace_imm_i,
    input  wire [BE_WIDTH*5-1:0]        trace_rd_i,
    input  wire [BE_WIDTH*5-1:0]        trace_rs1_i,
    input  wire [BE_WIDTH*5-1:0]        trace_rs2_i,
    input  wire [BE_WIDTH-1:0]          trace_rd_we_i,
    input  wire [BE_WIDTH-1:0]          trace_rs1_used_i,
    input  wire [BE_WIDTH-1:0]          trace_rs2_used_i,
    input  wire [BE_WIDTH-1:0]          trace_is_load_i,
    input  wire [BE_WIDTH-1:0]          trace_is_store_i,
    input  wire [BE_WIDTH-1:0]          trace_is_branch_i,
    input  wire [BE_WIDTH-1:0]          trace_is_halt_i,
    input  wire [BE_WIDTH-1:0]          trace_is_error_i,
    input  wire [BE_WIDTH*2-1:0]        trace_mem_size_i,
    input  wire [BE_WIDTH-1:0]          trace_mem_unsigned_i,
    input  wire [BE_WIDTH*128-1:0]      trace_store_data_i,
    input  wire [BE_WIDTH-1:0]          trace_pred_taken_i,
    input  wire [BE_WIDTH*32-1:0]       trace_pred_target_i,
    input  wire [BE_WIDTH*2-1:0]        trace_pred_kind_i,
    input  wire [BE_WIDTH*16-1:0]       trace_pred_metadata_i,

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
    output wire [BE_WIDTH-1:0]          commit_valid_o,
    output wire [BE_WIDTH*32-1:0]       commit_pc_o,
    output wire [BE_WIDTH*32-1:0]       commit_inst_o,
    output wire [BE_WIDTH*5-1:0]        commit_rd_o,
    output wire [BE_WIDTH-1:0]          commit_rd_we_o,
    output wire [BE_WIDTH*32-1:0]       commit_value_o,
    output wire [BE_WIDTH-1:0]          commit_is_store_o,
    output wire [BE_WIDTH*32-1:0]       commit_store_addr_o,
    output wire [BE_WIDTH*16-1:0]       commit_store_mask_o,
    output wire [BE_WIDTH*128-1:0]      commit_store_data_o,
    output wire [BE_WIDTH*TAG_WIDTH-1:0] commit_tag_o,
    output wire                         redirect_valid_o,
    output wire [31:0]                  redirect_pc_o,
    output wire [3:0]                   redirect_epoch_o,
    output wire                         halted_o,
    output wire                         error_o,
    output wire [31:0]                  return_value_o,
    output wire                         branch_feedback_valid_o,
    output wire [31:0]                  branch_feedback_pc_o,
    output wire [1:0]                   branch_feedback_kind_o,
    output wire                         branch_feedback_taken_o,
    output wire [31:0]                  branch_feedback_target_o,
    output wire                         branch_feedback_pred_taken_o,
    output wire [31:0]                  branch_feedback_pred_target_o,
    output wire [15:0]                  branch_feedback_metadata_o,
    // Per-lane accepted resolution: {pc,kind,taken,target,pred_taken,pred_target}.
    output wire [BE_WIDTH-1:0]          branch_feedback_lane_valid_o,
    output wire [BE_WIDTH*100-1:0]      branch_feedback_lane_packets_o,
    output wire [BE_WIDTH*16-1:0]       branch_feedback_lane_metadata_o,
    output wire [7:0]                   branch_recovery_history_o,
    output wire [15:0]                  perf_rob_occupancy_o,
    output wire [15:0]                  perf_rs_occupancy_o,
    output wire [15:0]                  perf_lsq_occupancy_o,
    output wire [BE_WIDTH-1:0]          perf_issue_valid_o,
    output wire                         perf_branch_pending_o,
    output wire                         perf_mdu_busy_o
);
    localparam integer PAW = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS);
    localparam integer ROB_SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES);
    localparam integer ROB_COUNT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES + 1);
    localparam integer ROB_GENERATION_WIDTH = TAG_WIDTH - ROB_SLOT_WIDTH - 3;
    localparam integer LSQ_SLOT_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES);
    localparam integer FREE_COUNT_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS + 1);
    localparam integer CHECK_RAT_WIDTH = 32 * PAW;
    // The checkpoint only needs the speculative RAT snapshot: the free bitmap is
    // deterministically rebuilt on recovery from the RAT + surviving ROB old
    // physical mappings (see the recovery block below).  Keeping the free state
    // in every checkpoint was pure dead storage (1024 -> 192 bits per entry).
    localparam integer CHECKPOINT_WIDTH = CHECK_RAT_WIDTH;
    localparam integer PRODUCERS = BE_WIDTH + 2;
    localparam integer MDU_SOURCE = BE_WIDTH;
    localparam integer LSQ_SOURCE = BE_WIDTH + 1;

    wire [BE_WIDTH-1:0] dec_valid = trace_valid_i & trace_ready_o;
    wire [BE_WIDTH-1:0] dec_rd_we = trace_rd_we_i;
    wire [BE_WIDTH-1:0] dec_rs1_used = trace_rs1_used_i;
    wire [BE_WIDTH-1:0] dec_rs2_used = trace_rs2_used_i;
    wire [BE_WIDTH-1:0] dec_rs_need = trace_valid_i;
    wire [BE_WIDTH-1:0] dec_lsq_need = trace_is_load_i | trace_is_store_i;
    wire [(BE_WIDTH*5)-1:0] dec_rd = trace_rd_i;
    wire [(BE_WIDTH*5)-1:0] dec_rs1 = trace_rs1_i;
    wire [(BE_WIDTH*5)-1:0] dec_rs2 = trace_rs2_i;

    wire [BE_WIDTH-1:0] rename_valid;
    wire [BE_WIDTH-1:0] rename_rd_we;
    wire [(BE_WIDTH*5)-1:0] rename_rd;
    wire [(BE_WIDTH*PAW)-1:0] rename_old_phys, rename_new_phys;
    wire [(BE_WIDTH*PAW)-1:0] rename_rs1_phys, rename_rs2_phys;
    // R owns ROB/destination allocation; D owns operand reads and queues.
    localparam integer DISPATCH_PAYLOAD_WIDTH=32 + `RV32IM_OP_WIDTH + 32 + 1 + 1 + 2 + 1 + 32 + 1 + 32 + 2 + PAW + PAW + PAW;
    wire [BE_WIDTH-1:0] d_valid;
    wire dispatch_packet_ready,d_admit;
    wire [BE_WIDTH*TAG_WIDTH-1:0] d_tag;
    wire [15:0] d_reserved_rs,d_reserved_lsq;
    wire [BE_WIDTH*DISPATCH_PAYLOAD_WIDTH-1:0] d_payload_in,d_payload_out;
    wire [BE_WIDTH*32-1:0] d_pc;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] d_op;
    wire [BE_WIDTH*32-1:0] d_imm;
    wire [BE_WIDTH*1-1:0] d_is_load;
    wire [BE_WIDTH*1-1:0] d_is_store;
    wire [BE_WIDTH*2-1:0] d_mem_size;
    wire [BE_WIDTH*1-1:0] d_mem_unsigned;
    wire [BE_WIDTH*32-1:0] d_store_data;
    wire [BE_WIDTH*1-1:0] d_pred_taken;
    wire [BE_WIDTH*32-1:0] d_pred_target;
    wire [BE_WIDTH*2-1:0] d_pred_kind;
    wire [BE_WIDTH*PAW-1:0] d_new_phys;
    wire [BE_WIDTH*PAW-1:0] d_src1_phys;
    wire [BE_WIDTH*PAW-1:0] d_src2_phys;

    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] rename_count;
    wire [(32*PAW)-1:0] rat_state, rrat_state;
    wire [PHYS_REGS-1:0] free_bitmap_state;
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
    wire [(BE_WIDTH*4)-1:0] rob_completion_store_mask;
    wire [(BE_WIDTH*32)-1:0] rob_completion_store_data;
    wire [BE_WIDTH-1:0] rob_commit_valid, rob_commit_rd_we, rob_commit_is_store;
    wire [(BE_WIDTH*5)-1:0] rob_commit_rd;
    wire [(BE_WIDTH*32)-1:0] rob_commit_pc, rob_commit_inst, rob_commit_value;
    wire [(BE_WIDTH*32)-1:0] rob_commit_store_addr;
    wire [(BE_WIDTH*16)-1:0] rob_commit_store_mask;
    wire [(BE_WIDTH*128)-1:0] rob_commit_store_data;
    wire [(BE_WIDTH*TAG_WIDTH)-1:0] rob_commit_tag;
    wire [(BE_WIDTH*PAW)-1:0] commit_old_phys, commit_new_phys;
    wire rob_store_commit_valid, rob_store_commit_ready, rob_store_ack_valid;
    wire [TAG_WIDTH-1:0] rob_store_commit_tag, rob_store_ack_tag;
    wire [31:0] rob_store_commit_addr;
    wire [15:0] rob_store_commit_mask;
    wire [127:0] rob_store_commit_data;
    wire rob_recovery_accept_source, rob_redirect_valid, rob_checkpoint_restore_valid;
    wire [7:0] recovery_domains;
    rv32_frequency_control_tree #(.LEAVES(8)) recovery_tree (
        .signal_i(rob_recovery_accept_source),.views_o(recovery_domains));
    wire [31:0] rob_redirect_pc;
    wire [3:0] rob_redirect_epoch;
    wire [CHECKPOINT_WIDTH-1:0] rob_checkpoint_restore;
    wire rob_recovery_rd_we;
    wire [4:0] rob_recovery_rd;
    wire [PAW-1:0] rob_recovery_new_phys;
    wire [PHYS_REGS-1:0] rob_recovery_reclaim_bitmap;
    wire [FREE_COUNT_WIDTH-1:0] rob_recovery_reclaim_count;
    wire [ROB_SLOT_WIDTH-1:0] rob_head, rob_head_source, rob_tail;
    wire [6*ROB_SLOT_WIDTH-1:0] rob_head_views;
    wire [6*ROB_SLOT_WIDTH-1:0] rob_registered_head_views;
    assign rob_head = rob_head_views[3*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
    generate
        if (ROB_CONTROL_REGISTER_BANKS != 0) begin : g_registered_heads
            assign rob_head_views = rob_registered_head_views;
        end else if (ASAP7_FANOUT_BUFFERS != 0) begin : g_head_fanout
            rv32_asap7_fanout #(.WIDTH(ROB_SLOT_WIDTH), .LEAVES(6), .ENABLED(1)) tree(
                .signal_i(rob_head_source), .replicas_o(rob_head_views));
        end else begin : g_head_wires
            rv32_frequency_control_tree #(.WIDTH(ROB_SLOT_WIDTH),.LEAVES(6)) tree (
                .signal_i(rob_head_source),.views_o(rob_head_views));
        end
    endgenerate
    wire [ROB_COUNT_WIDTH-1:0] rob_occupancy;
    wire [ROB_ENTRIES-1:0] rob_entry_valid;
    wire [ROB_ENTRIES*ROB_GENERATION_WIDTH-1:0] rob_entry_generation;
    wire [ROB_ENTRIES*PAW-1:0] rob_entry_new_phys;
    wire [ROB_ENTRIES-1:0] rob_entry_rd_we;
    wire [ROB_ENTRIES*5-1:0] rob_entry_rd;
    wire [ROB_ENTRIES*PAW-1:0] rob_entry_old_phys;
    wire [15:0] rob_free_count = (rob_occupancy < ROB_ENTRIES) ? ROB_ENTRIES - rob_occupancy : 16'd0;

    wire [(2*BE_WIDTH*PAW)-1:0] prf_read_phys;
    wire [(2*BE_WIDTH*32)-1:0] prf_read_data;
    wire [(2*BE_WIDTH)-1:0] prf_read_ready;
    wire [(BE_WIDTH*PAW)-1:0] prf_alloc_phys = rename_new_phys;
    wire [BE_WIDTH-1:0] prf_alloc_valid = rename_valid;
    wire [(BE_WIDTH*PAW)-1:0] prf_write_phys;
    wire [(BE_WIDTH*32)-1:0] prf_write_data;
    wire [BE_WIDTH-1:0] prf_write_valid;
    wire [(BE_WIDTH*PAW)-1:0] completion_prf_write_phys;
    wire [(BE_WIDTH*32)-1:0] completion_prf_write_data;
    wire [BE_WIDTH-1:0] completion_prf_write_valid;
    wire [BE_WIDTH-1:0] completion_live_load_error;

    wire [BE_WIDTH-1:0] rs_alloc_valid;
    wire rs_alloc_ready;
    wire [BE_WIDTH-1:0] rs_alloc_fire;
    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] rs_alloc_count;
    wire [BE_WIDTH-1:0] rs_issue_valid;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] rs_issue_op;
    wire [BE_WIDTH*32-1:0] rs_issue_pc, rs_issue_src1, rs_issue_src2;
    wire [BE_WIDTH*TAG_WIDTH-1:0] rs_issue_tag;
    wire [BE_WIDTH*PAW-1:0] rs_issue_phys;
    wire [BE_WIDTH*32-1:0] rs_issue_store;
    wire [BE_WIDTH*32-1:0] trace_store_data_relative;
    wire [BE_WIDTH*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))-1:0] rs_issue_slot;
    wire [((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES + 1))-1:0] rs_occupancy;
    wire [15:0] rs_free_count = (rs_occupancy < RS_ENTRIES) ? RS_ENTRIES - rs_occupancy : 16'd0;
    wire [BE_WIDTH-1:0] rs_issue_ready;
    wire [BE_WIDTH-1:0] rs_issue_allowed;
    localparam integer RS_ROW_QUALIFICATION_ACTIVE=(RS_ROW_RECOVERY_QUALIFICATION!=0) &&
        (LOCAL_EXEC_RECOVERY!=0) && (ISSUE_PIPELINE==0);
    localparam integer RS_ROW_LIVE_MEMBERSHIP_ACTIVE=(RS_ROW_LIVE_MEMBERSHIP!=0) &&
        RS_ROW_QUALIFICATION_ACTIVE && (RECOVERY_APPLY_OLDER_ISSUE!=0);
    localparam integer RS_ISSUE_CANCEL_PREDECODE_ACTIVE=(RS_PREDECODE_ISSUE_CANCEL!=0) &&
        RS_ROW_QUALIFICATION_ACTIVE && (RECOVERY_APPLY_OLDER_ISSUE!=0);
    wire [RS_ENTRIES-1:0] rs_entry_issue_cancel;
    wire [BE_WIDTH-1:0] raw_rs_issue_cancel;
    wire mdu_issue_cancel;
    wire [RS_ENTRIES-1:0] rs_entry_current_live_match;
    wire [RS_ENTRIES-1:0] rs_entry_recovery_qualified;
    wire [BE_WIDTH-1:0] raw_rs_issue_recovery_qualified;
    // In direct completion modes every CDB packet is a view of a
    // still-valid held producer. That producer already broadcasts to RS.
    localparam integer RS_DIRECT_WAKE=(RS_PHYSICAL_WAKEUP!=0) &&
        ((COMPLETION_BYPASS==1) || (COMPLETION_BYPASS==2));
    localparam integer RS_BASE_WAKE_WIDTH=RS_DIRECT_WAKE?PRODUCERS:BE_WIDTH+PRODUCERS;
    localparam integer RS_LOAD_RETURN_WAKE=(LOAD_WAKE_BYPASS!=0) && RS_DIRECT_WAKE && (LOCAL_EXEC_RECOVERY!=0);
    localparam integer RS_WAKE_WIDTH=RS_BASE_WAKE_WIDTH+RS_LOAD_RETURN_WAKE;
    wire [RS_BASE_WAKE_WIDTH-1:0] rs_base_wake_valid;
    wire [RS_BASE_WAKE_WIDTH*32-1:0] rs_base_wake_value;
    wire lsq_return_wake_valid;
    wire [TAG_WIDTH-1:0] lsq_return_wake_tag;
    wire [PAW-1:0] lsq_return_wake_phys;
    wire [31:0] lsq_return_wake_value;
    wire [RS_WAKE_WIDTH-1:0] rs_wake_valid;
    wire [RS_WAKE_WIDTH*RS_SOURCE_TAG_WIDTH-1:0] rs_wake_tag;
    wire [RS_WAKE_WIDTH*32-1:0] rs_wake_value;
    wire [RS_ENTRIES-1:0] rs_entry_valid;
    wire [RS_ENTRIES*TAG_WIDTH-1:0] rs_entry_rob_tag;
    wire [RS_ENTRIES-1:0] rs_entry_base_ready;
    localparam integer STORE_RS_LINKS=(EARLY_STORE_ADDRESS==2) && (RS_ALLOC_STATIC_WRITE!=0);
    localparam integer STORE_RS_SW=(RS_ENTRIES<=1)?1:$clog2(RS_ENTRIES);
    wire [BE_WIDTH*STORE_RS_SW-1:0] rs_alloc_slot;
    wire [RS_ENTRIES-1:0] rs_entry_release;
    wire [LSQ_ENTRIES-1:0] store_rs_link_valid;
    wire [LSQ_ENTRIES*STORE_RS_SW-1:0] store_rs_link_slot;
    wire [RS_ENTRIES*32-1:0] rs_entry_base_value;
    localparam integer RS_METADATA_WIDTH = (RS_ISSUE_METADATA != 0) ? 70 : 1;
    wire [BE_WIDTH*RS_METADATA_WIDTH-1:0] rs_alloc_metadata, rs_issue_metadata;
    wire [RS_ENTRIES*RS_METADATA_WIDTH-1:0] rs_entry_metadata;
    reg [RS_ENTRIES-1:0] rs_flush_kill_mask;
    reg [RS_ENTRIES-1:0] rs_preview_kill_mask;

    wire [BE_WIDTH-1:0] alu_exec_valid, alu_exec_ready, alu_issue_ready;
    wire [BE_WIDTH-1:0] alu_exec_saved_valid;
    wire [BE_WIDTH-1:0] alu_exec_rd_we, alu_exec_is_branch;
    wire [BE_WIDTH-1:0] alu_exec_branch_taken, alu_exec_redirect_valid, alu_exec_is_memory;
    wire [BE_WIDTH-1:0] alu_exec_is_load, alu_exec_is_store, alu_exec_mem_unsigned;
    wire [BE_WIDTH*32-1:0] alu_exec_value, alu_exec_branch_target, alu_exec_redirect_pc, alu_exec_mem_addr;
    wire [BE_WIDTH*2-1:0] alu_exec_mem_size;
    wire [BE_WIDTH*32-1:0] alu_exec_store_data;
    wire [BE_WIDTH*32-1:0] alu_exec_source_pc, alu_exec_pred_target;
    wire [BE_WIDTH-1:0] alu_exec_pred_taken;
    wire [BE_WIDTH*2-1:0] alu_exec_pred_kind;
    wire [BE_WIDTH*PAW-1:0] alu_exec_phys;
    wire [BE_WIDTH*TAG_WIDTH-1:0] alu_exec_tag;
    wire [BE_WIDTH-1:0] rs_issue_is_mdu;
    wire [BE_WIDTH-1:0] mdu_select;
    wire [`RV32IM_OP_WIDTH-1:0] mdu_issue_op;
    wire [31:0] mdu_issue_src1, mdu_issue_src2;
    wire [TAG_WIDTH-1:0] mdu_issue_tag;
    wire [PAW-1:0] mdu_issue_phys;

    wire mdu_issue_valid, mdu_issue_ready, mdu_completion_valid, mdu_completion_ready, mdu_completion_rd_we;
    wire mdu_busy;
    wire [31:0] mdu_completion_value;
    wire [TAG_WIDTH-1:0] mdu_completion_tag;
    wire [PAW-1:0] mdu_completion_phys;

    wire [BE_WIDTH-1:0] cdb_valid, cdb_rd_we, cdb_is_store, cdb_is_branch;
    wire [BE_WIDTH*TAG_WIDTH-1:0] cdb_tag;
    wire [BE_WIDTH*PAW-1:0] cdb_phys;
    wire [BE_WIDTH*32-1:0] cdb_value, cdb_addr, cdb_branch_target;
    wire [BE_WIDTH*32-1:0] cdb_store_data;
    wire [BE_WIDTH-1:0] cdb_branch_taken, cdb_redirect_valid, cdb_is_memory, cdb_is_load;
    wire [PRODUCERS-1:0] producer_valid, producer_ready;
    wire [PRODUCERS*TAG_WIDTH-1:0] producer_tag;
    wire [PRODUCERS*PAW-1:0] producer_phys;
    wire [PRODUCERS*32-1:0] producer_value, producer_addr, producer_branch_target;
    wire [PRODUCERS*32-1:0] producer_store_data;
    wire [PRODUCERS-1:0] producer_rd_we, producer_store, producer_branch, producer_taken, producer_redirect, producer_memory, producer_load;
    // The recovery cycle uses the ROB completion port for the resolving
    // branch.  Hold queued CDB work for one cycle so an older completion is
    // not popped without reaching the ROB.
    wire [BE_WIDTH-1:0] cdb_ready;
    wire [COMPLETION_DEPTH-1:0] completion_entry_valid;
    wire [COMPLETION_DEPTH*TAG_WIDTH-1:0] completion_entry_tag;
    wire [BE_WIDTH-1:0] prf_wb_valid, rob_wb_valid, wake_wb_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] prf_wb_tag, rob_wb_tag, wake_wb_tag;
    wire [BE_WIDTH*PAW-1:0] prf_wb_phys;
    wire [BE_WIDTH*32-1:0] prf_wb_value, rob_wb_value, wake_wb_value;

    wire [BE_WIDTH-1:0] lsq_alloc_valid;
    wire lsq_alloc_ready;
    wire [BE_WIDTH-1:0] lsq_alloc_fire;
    wire [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] lsq_alloc_count;
    wire [BE_WIDTH*TAG_WIDTH-1:0] lsq_alloc_tag;
    wire [BE_WIDTH-1:0] lsq_alloc_addr_valid;
    wire [BE_WIDTH*32-1:0] lsq_alloc_addr;
    localparam integer ALLOC_STORE_DATA_ACTIVE=(STORE_ALLOC_EARLY_DATA!=0) && (EARLY_STORE_ADDRESS!=0);
    // D owns renamed physical sources. A ready src2 value is authoritative
    // even before this store reaches RS issue. Unknown sources retain the
    // original execution update and never advertise allocation data ready.
    wire [BE_WIDTH-1:0] lsq_alloc_data_valid = ALLOC_STORE_DATA_ACTIVE ?
        (d_is_store & d_valid & rs_src2_ready) : ((EARLY_STORE_ADDRESS != 0) ?
        {BE_WIDTH{1'b0}} : (d_is_store & d_valid));
    wire [BE_WIDTH*32-1:0] lsq_alloc_store_data;
    generate for(genvar store_data_lane=0;store_data_lane<BE_WIDTH;store_data_lane=store_data_lane+1) begin:g_alloc_store_data
        assign lsq_alloc_store_data[store_data_lane*32 +: 32]=ALLOC_STORE_DATA_ACTIVE ?
            rs_src2_value[store_data_lane*32 +: 32] : d_store_data[store_data_lane*32 +: 32];
    end endgenerate
    wire [((LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES + 1))-1:0] lsq_occupancy;
    wire [((LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES))-1:0] lsq_head;
    wire [LSQ_ENTRIES-1:0] lsq_store_addr_pending;
    wire [LSQ_ENTRIES*TAG_WIDTH-1:0] lsq_store_addr_rob_tag, lsq_store_addr_lsq_tag;
    wire shared_store_addr_valid;
    wire [TAG_WIDTH-1:0] shared_store_addr_tag;
    wire [31:0] shared_store_addr;
    wire [15:0] lsq_free_count = (lsq_occupancy < LSQ_ENTRIES) ? LSQ_ENTRIES - lsq_occupancy : 16'd0;
    wire lsq_store_commit_ready, lsq_load_complete_valid, lsq_load_complete_ready;
    wire [TAG_WIDTH-1:0] lsq_load_complete_tag;
    localparam integer LSQ_ROB_LOW_BITS=(ROB_SLOT_WIDTH+1)/2;
    localparam integer LSQ_ROB_HIGH_BITS=ROB_SLOT_WIDTH-LSQ_ROB_LOW_BITS;
    localparam integer LSQ_ROB_QUERY_WIDTH=(1<<LSQ_ROB_LOW_BITS)+(1<<LSQ_ROB_HIGH_BITS);
    wire [LSQ_ROB_QUERY_WIDTH-1:0] lsq_load_complete_rob_query;
    wire [TAG_WIDTH-1:0] lsq_load_complete_lsq_tag;
    wire [31:0] lsq_load_complete_value;
    wire [PAW-1:0] lsq_load_complete_phys;
    wire lsq_load_complete_unretired;
    wire lsq_load_complete_cancel;
    wire lsq_load_complete_error;
    wire lsq_store_ack_valid;
    wire [TAG_WIDTH-1:0] lsq_store_ack_lsq_tag;
    wire [TAG_WIDTH-1:0] lsq_store_ack_rob_tag;
    wire lsq_store_ack_error;
    wire [BE_WIDTH-1:0] lsq_addr_update_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] lsq_addr_update_tag;
    wire [BE_WIDTH*32-1:0] lsq_addr_update;
    wire [BE_WIDTH-1:0] lsq_data_update_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] lsq_data_update_tag;

    wire [TAG_WIDTH-1:0] rob_to_lsq_mem [0:ROB_ENTRIES-1];

    localparam integer ROB_MAP_READ_DOMAINS=(ROB_ENTRIES+3)/4;
    localparam integer ROB_MAP_READ_LEAVES=1<<$clog2(ROB_ENTRIES);
    localparam integer ROB_MAP_READ_WORDS=(TAG_WIDTH+15)/16;
    wire [BE_WIDTH*ROB_SLOT_WIDTH-1:0] rob_map_query;
    wire [ROB_MAP_READ_DOMAINS*BE_WIDTH*ROB_SLOT_WIDTH-1:0] rob_map_query_views;
    wire [BE_WIDTH*TAG_WIDTH-1:0] alu_lsq_map_read;
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*ROB_SLOT_WIDTH),.LEAVES(ROB_MAP_READ_DOMAINS)) rob_map_query_tree (
        .signal_i(rob_map_query),.views_o(rob_map_query_views));
    genvar map_query_lane,map_query_row,map_query_word,map_query_node;
    generate
        for(map_query_lane=0;map_query_lane<BE_WIDTH;map_query_lane=map_query_lane+1) begin:g_rob_map_read
            wire [TAG_WIDTH-1:0] reads [1:2*ROB_MAP_READ_LEAVES-1];
            assign rob_map_query[map_query_lane*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]=
                alu_exec_tag[map_query_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            assign alu_lsq_map_read[map_query_lane*TAG_WIDTH +: TAG_WIDTH]=reads[1];
            for(map_query_row=0;map_query_row<ROB_MAP_READ_LEAVES;map_query_row=map_query_row+1) begin:g_row
                if(map_query_row<ROB_ENTRIES) begin:g_present
                    wire [ROB_MAP_READ_WORDS-1:0] selects;
                    wire hit=rob_map_query_views[((map_query_row/4)*BE_WIDTH+map_query_lane)*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_query_row;
                    rv32_frequency_control_tree #(.LEAVES(ROB_MAP_READ_WORDS)) select_tree (
                        .signal_i(hit),.views_o(selects));
                    for(map_query_word=0;map_query_word<ROB_MAP_READ_WORDS;map_query_word=map_query_word+1) begin:g_word
                        localparam integer LOW=map_query_word*16;
                        localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
                        assign reads[ROB_MAP_READ_LEAVES+map_query_row][LOW +: BITS]=
                            {BITS{selects[map_query_word]}} & rob_to_lsq_mem[map_query_row][LOW +: BITS];
                    end
                end else begin:g_padding
                    assign reads[ROB_MAP_READ_LEAVES+map_query_row]=0;
                end
            end
            for(map_query_node=1;map_query_node<ROB_MAP_READ_LEAVES;map_query_node=map_query_node+1) begin:g_reduce
                assign reads[map_query_node]=reads[2*map_query_node] | reads[2*map_query_node+1];
            end
        end
    endgenerate

    wire [TAG_WIDTH-1:0] phys_tag_mem [0:PHYS_REGS-1];

    localparam integer TAG_READ_PORTS=2*BE_WIDTH;
    localparam integer TAG_ROWS=(PHYS_REGS<=1)?1:(1<<$clog2(PHYS_REGS));
    wire [TAG_READ_PORTS*PAW-1:0] tag_read_queries;
    wire [TAG_READ_PORTS*TAG_WIDTH-1:0] tag_read_values;
    wire [4*TAG_READ_PORTS*PAW-1:0] tag_query_views;
    wire [4*BE_WIDTH*PAW-1:0] tag_write_address_views;
    wire [4*BE_WIDTH*TAG_WIDTH-1:0] tag_write_value_views;
    wire [4*BE_WIDTH-1:0] tag_write_valid_views;
    wire [PHYS_REGS-1:0] tag_reset_views;
    genvar tag_lane,tag_row,tag_port,tag_node;
    generate
        for(tag_lane=0;tag_lane<BE_WIDTH;tag_lane=tag_lane+1) begin:g_tag_query
            assign tag_read_queries[(2*tag_lane)*PAW +: PAW]=d_src1_phys[tag_lane*PAW +: PAW];
            assign tag_read_queries[(2*tag_lane+1)*PAW +: PAW]=d_src2_phys[tag_lane*PAW +: PAW];
        end
        if(PHYS_TAG_IMPL==0 && RS_PHYSICAL_WAKEUP==0) begin:g_owned_producer_tags
            rv32_frequency_control_tree #(.WIDTH(TAG_READ_PORTS*PAW),.LEAVES(4)) query_tree (
                .signal_i(tag_read_queries),.views_o(tag_query_views));
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PAW),.LEAVES(4)) address_tree (
                .signal_i(rename_new_phys),.views_o(tag_write_address_views));
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*TAG_WIDTH),.LEAVES(4)) value_tree (
                .signal_i(rob_alloc_tag),.views_o(tag_write_value_views));
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) valid_tree (
                .signal_i(dispatch_valid & rob_alloc_fire & rename_rd_we),.views_o(tag_write_valid_views));
            rv32_frequency_control_tree #(.LEAVES(PHYS_REGS)) reset_tree (
                .signal_i(reset_i),.views_o(tag_reset_views));
            for(tag_row=0;tag_row<PHYS_REGS;tag_row=tag_row+1) begin:g_row
                localparam integer DOMAIN=(tag_row*4)/PHYS_REGS;
                wire [BE_WIDTH-1:0] row_match_mask;
                for(tag_lane=0;tag_lane<BE_WIDTH;tag_lane=tag_lane+1) begin:g_match
                    assign row_match_mask[tag_lane]=tag_write_valid_views[DOMAIN*BE_WIDTH+tag_lane] &&
                        tag_write_address_views[(DOMAIN*BE_WIDTH+tag_lane)*PAW +: PAW]==tag_row;
                end
                rv32_producer_tag_row #(.LANES(BE_WIDTH),.TAG_WIDTH(TAG_WIDTH)) owner (
                    .clk_i(clk_i),.reset_i(tag_reset_views[tag_row]),.match_i(row_match_mask),
                    .tag_i(tag_write_value_views[DOMAIN*BE_WIDTH*TAG_WIDTH +: BE_WIDTH*TAG_WIDTH]),
                    .tag_o(phys_tag_mem[tag_row]));
            end
            for(tag_port=0;tag_port<TAG_READ_PORTS;tag_port=tag_port+1) begin:g_read
                wire [TAG_WIDTH-1:0] tree [1:2*TAG_ROWS-1];
                for(tag_row=0;tag_row<TAG_ROWS;tag_row=tag_row+1) begin:g_select
                    if(tag_row<PHYS_REGS) begin:g_present
                        localparam integer DOMAIN=(tag_row*4)/PHYS_REGS;
                        wire selected=tag_query_views[(DOMAIN*TAG_READ_PORTS+tag_port)*PAW +: PAW]==tag_row;
                        wire local_selected;
                        rv32_frequency_control_tree #(.LEAVES(1)) select_tree (
                            .signal_i(selected),.views_o(local_selected));
                        assign tree[TAG_ROWS+tag_row]={TAG_WIDTH{local_selected}} & phys_tag_mem[tag_row];
                    end else begin:g_padding
                        assign tree[TAG_ROWS+tag_row]=0;
                    end
                end
                for(tag_node=1;tag_node<TAG_ROWS;tag_node=tag_node+1) begin:g_or
                    assign tree[tag_node]=tree[2*tag_node] | tree[2*tag_node+1];
                end
                assign tag_read_values[tag_port*TAG_WIDTH +: TAG_WIDTH]=tree[1];
            end
        end else begin:g_rob_search_producer_tags
            assign tag_read_values=0;
            for(tag_row=0;tag_row<PHYS_REGS;tag_row=tag_row+1) begin:g_unused
                assign phys_tag_mem[tag_row]=0;
            end
        end
    endgenerate

    wire [31:0] rob_pc_mem [0:ROB_ENTRIES-1];
    wire load_error_mem [0:ROB_ENTRIES-1];
    wire [31:0] rob_imm_mem [0:ROB_ENTRIES-1];
    // Mode 1 probes only at allocation; mode 2 also follows existing RS
    // base wakeups with a single shared adder and ROB immediate read port.
    // Store data, execution completion and in-order commit remain unchanged.
    generate if(STORE_RS_LINKS!=0) begin:g_store_rs_links
        rv32_store_rs_links #(.BE_WIDTH(BE_WIDTH),.LSQ_ENTRIES(LSQ_ENTRIES),
            .RS_ENTRIES(RS_ENTRIES),.TAG_WIDTH(TAG_WIDTH)) owner (
            .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),
            .recovery_i(recovery_domains[4] || recovery_domains[5]),
            .lsq_alloc_fire_i(lsq_alloc_fire),.rs_alloc_fire_i(rs_alloc_fire),
            .alloc_is_store_i(d_is_store),.alloc_lsq_tag_i(lsq_alloc_tag),
            .alloc_rs_slot_i(rs_alloc_slot),.rs_release_i(rs_entry_release),
            .link_valid_o(store_rs_link_valid),.link_rs_slot_o(store_rs_link_slot));
    end else begin:g_no_store_rs_links
        assign store_rs_link_valid=0;
        assign store_rs_link_slot=0;
    end endgenerate
    generate if (EARLY_STORE_ADDRESS == 2) begin : g_shared_store_address
        wire selected;
        wire [TAG_WIDTH-1:0] selected_rob_tag;
        wire [31:0] selected_base;
        wire [31:0] selected_imm;
        wire [RS_ENTRIES-1:0] selected_rs;
        wire [ROB_SLOT_WIDTH-1:0] selected_slot = selected_rob_tag[3 +: ROB_SLOT_WIDTH];
        wire [ROB_LIVE_WIDTH-1:0] selected_live;
        rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
            .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
            .rows_i(rob_live_rows),.index_i(selected_slot),.value_o(selected_live));
        rv32_store_address_select #(.LSQ_ENTRIES(LSQ_ENTRIES), .RS_ENTRIES(RS_ENTRIES),
            .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH),.LINKED_RS(STORE_RS_LINKS)) selector (
            .link_valid_i(store_rs_link_valid),.link_rs_slot_i(store_rs_link_slot),
            .head_i(lsq_head), .pending_i(lsq_store_addr_pending),
            .lsq_tag_i(lsq_store_addr_lsq_tag), .store_rob_tag_i(lsq_store_addr_rob_tag),
            .base_ready_i(rs_entry_base_ready), .rs_rob_tag_i(rs_entry_rob_tag),
            .base_value_i(rs_entry_base_value), .valid_o(selected),
            .lsq_tag_o(shared_store_addr_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)
        );
        assign shared_store_addr_valid = selected && !reset_i && !flush_i &&
            !branch_busy_domains[0] && selected_rob_tag[0] && selected_live[ROB_GENERATION_WIDTH] &&
            (selected_rob_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==
             selected_live[0 +: ROB_GENERATION_WIDTH]);
        if (RS_ISSUE_METADATA != 0) begin : g_inline_imm
            wire [RS_ENTRIES*32-1:0] immediate_rows;
            genvar meta_slot;
            for(meta_slot=0;meta_slot<RS_ENTRIES;meta_slot=meta_slot+1) begin:g_immediate_row
                assign immediate_rows[meta_slot*32 +: 32]=rs_entry_metadata[meta_slot*RS_METADATA_WIDTH +: 32];
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RS_ENTRIES),.PRIORITY(0)) immediate_selector (
                .events_i(selected_rs),.values_i(immediate_rows),.write_o(),.value_o(selected_imm));
        end else begin : g_rob_imm
            assign selected_imm = rob_imm_mem[selected_slot];
        end
        if(STORE_ALLOC_IMM12!=0) begin:g_decoder_store_offset
            // The CPU enables this signed-12-bit contract for all decoded
            // stores, including the shared probe. Standalone trace backends
            // retain full-width arithmetic with the default-disabled option.
            rv32_frequency_add_simm12 address_adder (
                .base_i(selected_base),.immediate_i(selected_imm[11:0]),
                .sum_o(shared_store_addr));
        end else begin:g_generic_store_offset
            rv32_frequency_add32_select address_adder (
                .lhs_i(selected_base),.rhs_i(selected_imm),.sum_o(shared_store_addr));
        end
    end else begin : g_no_shared_store_address
        assign shared_store_addr_valid = 1'b0;
        assign shared_store_addr_tag = {TAG_WIDTH{1'b0}};
        assign shared_store_addr = 32'b0;
    end endgenerate
    initial begin
        if ((DISPATCH_ELASTIC!=0 && DISPATCH_ELASTIC!=1) ||
            (DISPATCH_ELASTIC!=0 && DISPATCH_PIPELINE==0)) begin
            $display("ERROR: DISPATCH_ELASTIC must be 0 or 1; elastic mode requires DISPATCH_PIPELINE");
            $finish;
        end
        if (RS_ISSUE_METADATA != 0 && RS_ISSUE_METADATA != 1) begin
            $display("ERROR: RS_ISSUE_METADATA must be 0 or 1");
            $finish;
        end
        if (EARLY_STORE_ADDRESS < 0 || EARLY_STORE_ADDRESS > 2) begin
            $display("ERROR: EARLY_STORE_ADDRESS must be 0, 1 or 2");
            $finish;
        end
    end
    wire rob_pred_taken_mem [0:ROB_ENTRIES-1];
    wire [31:0] rob_pred_target_mem [0:ROB_ENTRIES-1];
    wire [1:0] rob_pred_kind_mem [0:ROB_ENTRIES-1];
    wire [1:0] rob_mem_size_mem [0:ROB_ENTRIES-1];
    wire rob_mem_unsigned_mem [0:ROB_ENTRIES-1];

    // Raw registered producer tags form the query independently of the
    // producer qualification process. Never feed that process's result
    // back through an asynchronous table read into its own live predicate.
    localparam integer ROB_LIVE_WIDTH=ROB_GENERATION_WIDTH+1;
    wire [ROB_ENTRIES*ROB_LIVE_WIDTH-1:0] rob_live_rows;
    wire [ROB_ENTRIES*3-1:0] rob_completion_state_rows;
    wire [PRODUCERS*TAG_WIDTH-1:0] producer_query_tags={
        lsq_load_complete_tag,mdu_completion_tag,alu_exec_tag};
    wire [PRODUCERS*ROB_LIVE_WIDTH-1:0] producer_live_reads;
    wire [BE_WIDTH*3-1:0] completion_state_reads;
    genvar status_row,status_source,status_lane;
    generate
        for(status_row=0;status_row<ROB_ENTRIES;status_row=status_row+1) begin:g_rob_status_row
            assign rob_live_rows[status_row*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]={
                rob_entry_valid[status_row],
                rob_entry_generation[status_row*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH]};
            assign rob_completion_state_rows[status_row*3 +: 3]={
                load_error_mem[status_row],rob_mem_size_mem[status_row]};
        end
        for(status_source=0;status_source<PRODUCERS;status_source=status_source+1) begin:g_producer_live_read
            if(LSQ_ROB_QUERY_PREDECODE!=0 && status_source==LSQ_SOURCE) begin:g_predecoded_load
                rv32_frequency_array_read_bank_masks #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),.query_i(lsq_load_complete_rob_query),
                    .value_o(producer_live_reads[status_source*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]));
            end else begin:g_original_status_query
                rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),
                    .index_i(producer_query_tags[status_source*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                    .value_o(producer_live_reads[status_source*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]));
            end
        end
        for(status_lane=0;status_lane<BE_WIDTH;status_lane=status_lane+1) begin:g_completion_state_read
            rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) state_read (
                .rows_i(rob_completion_state_rows),
                .index_i(rob_wb_tag[status_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                .value_o(completion_state_reads[status_lane*3 +: 3]));
        end
    endgenerate

    // The accepted live branch can redirect fetch on its capture edge.
    // Backend preview/capture/apply and its sole epoch increment stay staged.
    localparam integer BRANCH_CAPTURE_WIDTH=TAG_WIDTH+PAW+65;
    wire [BE_WIDTH-1:0] branch_capture_match,branch_capture_grant;
    wire [BE_WIDTH*BRANCH_CAPTURE_WIDTH-1:0] branch_capture_values;
    wire branch_capture_write;
    wire [BRANCH_CAPTURE_WIDTH-1:0] branch_capture_next,branch_capture_saved;
    reg branch_pending;
    localparam integer RECOVERY_DIRECT_ACTIVE=(RECOVERY_DIRECT_APPLY!=0) &&
        (EARLY_FRONT_REDIRECT!=0) && (LOCAL_EXEC_RECOVERY!=0) &&
        (CHECKPOINT_IMPL!=0) && (RAT_RECOVERY_IMPL!=0);
    wire recovery_descriptor_valid;
    wire [CHECK_RAT_WIDTH-1:0] recovery_descriptor_rat;
    wire [PHYS_REGS-1:0] recovery_descriptor_reclaim;
    wire [FREE_COUNT_WIDTH-1:0] recovery_descriptor_reclaim_count;
    wire [ROB_SLOT_WIDTH-1:0] recovery_descriptor_head;
    wire [ROB_COUNT_WIDTH-1:0] recovery_descriptor_occupancy;
    wire [RS_ENTRIES-1:0] recovery_descriptor_rs_kill;
    wire rob_recovery_preview;
    // Preview remains the same qualified branch event. In direct mode
    // it is also the apply edge; no descriptor-valid feedback drives preview.
    wire recovery_preview_fire = branch_pending && rob_recovery_preview &&
        ((RECOVERY_DIRECT_ACTIVE!=0) || !recovery_descriptor_valid) && !flush_i;
    wire [3:0] branch_busy_domains;
    wire [3:0] recovery_capture_domains;
    rv32_frequency_control_tree #(.LEAVES(4)) branch_busy_tree (
        .signal_i(branch_pending),.views_o(branch_busy_domains));
    rv32_frequency_control_tree #(.LEAVES(4)) recovery_capture_tree (
        .signal_i(recovery_preview_fire),.views_o(recovery_capture_domains));
    wire [6*ROB_SLOT_WIDTH-1:0] recovery_head_views;
    rv32_frequency_control_tree #(.WIDTH(ROB_SLOT_WIDTH),.LEAVES(6)) recovery_head_tree (
        .signal_i(recovery_descriptor_head),.views_o(recovery_head_views));
    wire [TAG_WIDTH-1:0] branch_pending_tag;
    // Registered descriptors still need electrical separation at their
    // consumers. These are priced course-library cells, without new cycles.
    wire [8*TAG_WIDTH-1:0] recovery_tag_views;
    rv32_frequency_control_tree #(.WIDTH(TAG_WIDTH),.LEAVES(8)) recovery_tag_tree (
        .signal_i(branch_pending_tag),.views_o(recovery_tag_views));
    // Recovery guards are independent from the optional issue queue.
    // Core callers retain them for held ALU/MDU/LSQ results in direct mode.
    localparam integer EXEC_RECOVERY_WIDTH=1+2*ROB_SLOT_WIDTH+ROB_COUNT_WIDTH;
    wire [ROB_SLOT_WIDTH-1:0] execution_branch_age=
        branch_pending_tag[3 +: ROB_SLOT_WIDTH]-recovery_descriptor_head;
    wire [(BE_WIDTH+2)*EXEC_RECOVERY_WIDTH-1:0] execution_recovery_views;
    rv32_frequency_control_tree #(.WIDTH(EXEC_RECOVERY_WIDTH),.LEAVES(BE_WIDTH+2)) execution_recovery_tree (
        .signal_i({recovery_domains[6],recovery_descriptor_occupancy,recovery_descriptor_head,execution_branch_age}),
        .views_o(execution_recovery_views));
    wire [31:0] branch_pending_value;
    wire [PAW-1:0] branch_pending_phys;
    wire branch_pending_rd_we;
    wire [31:0] branch_pending_pc;
    wire branch_feedback_valid_r;
    wire [31:0] branch_feedback_pc_r;
    wire [1:0] branch_feedback_kind_r;
    wire branch_feedback_taken_r;
    wire [31:0] branch_feedback_target_r;
    wire branch_feedback_pred_taken_r;
    wire [31:0] branch_feedback_pred_target_r;
    reg [BE_WIDTH-1:0] cdb_ready_r;
    wire [ROB_SLOT_WIDTH-1:0] branch_feedback_slot;
    integer ready_lane;
    integer source_lane;
    integer source_rob_slot;
    integer checkpoint_lane;
    integer dependency_lane;
    integer alu_ready_lane;
    integer redirect_ready_found;
    integer ready_rob_used;
    integer ready_rs_used;
    integer ready_lsq_used;
    integer ready_phys_used;
    integer producer_index;
    integer cdb_ready_lane;
    integer recovery_rs_index;
    integer recovery_rs_rob_slot;
    integer recovery_rs_branch_slot;
    reg [ROB_SLOT_WIDTH-1:0] recovery_rs_age;
    reg [ROB_SLOT_WIDTH-1:0] recovery_rs_branch_age;
    integer recovery_completion_index;
    integer recovery_completion_rob_slot;
    reg [ROB_SLOT_WIDTH-1:0] recovery_completion_age;
    reg [ROB_SLOT_WIDTH-1:0] recovery_completion_branch_age;
    integer producer_recovery_index;
    integer producer_recovery_rob_slot;
    reg [ROB_SLOT_WIDTH-1:0] producer_recovery_age;
    reg [ROB_SLOT_WIDTH-1:0] producer_recovery_branch_age;
    integer alu_recovery_lane;
    integer alu_recovery_slot;
    reg [ROB_SLOT_WIDTH-1:0] alu_recovery_age;
    reg [ROB_SLOT_WIDTH-1:0] alu_recovery_branch_age;
    integer recovery_rat_age;
    integer recovery_rat_slot;
    reg [ROB_SLOT_WIDTH-1:0] recovery_rat_branch_age;
    reg [CHECK_RAT_WIDTH-1:0] recovery_rat_state;
    reg [PHYS_REGS-1:0] recovery_free_bitmap;
    reg [FREE_COUNT_WIDTH-1:0] recovery_free_count;
    reg [COMPLETION_DEPTH-1:0] completion_kill_mask;
    wire [BE_WIDTH-1:0] dispatch_valid = rename_valid;
    reg [BE_WIDTH*TAG_WIDTH-1:0] rs_src1_tag, rs_src2_tag;

    // ROB tags still guard producer ownership before wake_valid. RS source
    // identity is physical-register identity while that allocation is live.
    // P0/out-of-range source IDs never claim a wake dependency.
    localparam integer RS_SOURCE_TAG_WIDTH=RS_PHYSICAL_WAKEUP?(PAW+1):TAG_WIDTH;
    wire [BE_WIDTH*RS_SOURCE_TAG_WIDTH-1:0] rs_source1_identity,rs_source2_identity;
    genvar source_identity_lane;
    generate if(RS_PHYSICAL_WAKEUP!=0) begin:g_physical_source_identity
        for(source_identity_lane=0;source_identity_lane<BE_WIDTH;source_identity_lane=source_identity_lane+1) begin:g_lane
            wire [PAW-1:0] phys1=d_src1_phys[source_identity_lane*PAW +: PAW];
            wire [PAW-1:0] phys2=d_src2_phys[source_identity_lane*PAW +: PAW];
            assign rs_source1_identity[source_identity_lane*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]={phys1,(phys1!=0 && phys1<PHYS_REGS)};
            assign rs_source2_identity[source_identity_lane*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]={phys2,(phys2!=0 && phys2<PHYS_REGS)};
        end
    end else begin:g_rob_source_identity
        assign rs_source1_identity=rs_src1_tag;
        assign rs_source2_identity=rs_src2_tag;
    end endgenerate

    reg [BE_WIDTH-1:0] rs_src1_ready, rs_src2_ready;
    reg [BE_WIDTH*32-1:0] rs_src1_value, rs_src2_value;
    wire [BE_WIDTH*32-1:0] rs_issue_imm;
    wire [BE_WIDTH-1:0] rs_issue_pred_taken;
    wire [BE_WIDTH*32-1:0] rs_issue_pred_target;
    wire [BE_WIDTH*2-1:0] rs_issue_pred_kind;
    wire [BE_WIDTH*2-1:0] rs_issue_mem_size;
    wire [BE_WIDTH-1:0] rs_issue_mem_unsigned;
    reg [CHECK_RAT_WIDTH-1:0] checkpoint_rat_work;
    reg [BE_WIDTH-1:0] rob_alloc_is_store, rob_alloc_is_branch, rob_alloc_is_halt, rob_alloc_is_error;
    reg [BE_WIDTH*32-1:0] rob_alloc_pc, rob_alloc_inst;
    reg [BE_WIDTH*5-1:0] rob_alloc_rd;
    reg [BE_WIDTH*PAW-1:0] rob_alloc_old_phys, rob_alloc_new_phys;
    reg [BE_WIDTH*CHECKPOINT_WIDTH-1:0] rob_alloc_checkpoint;
    reg [PRODUCERS*TAG_WIDTH-1:0] producer_tag_r;
    reg [PRODUCERS*PAW-1:0] producer_phys_r;
    reg [PRODUCERS*32-1:0] producer_value_r, producer_addr_r, producer_branch_target_r;
    reg [PRODUCERS*32-1:0] producer_store_data_r;
    reg [PRODUCERS-1:0] producer_valid_r, producer_rd_we_r, producer_store_r, producer_branch_r, producer_taken_r, producer_redirect_r, producer_memory_r, producer_load_r;
    reg [PRODUCERS-1:0] producer_target_live_r;
    wire [PRODUCERS-1:0] producer_ready_r;
    reg [BE_WIDTH-1:0] alu_exec_ready_r;
    reg [BE_WIDTH-1:0] alu_flush_r;
    reg [BE_WIDTH-1:0] trace_ready_r;
    localparam integer CREDIT_WIDTH=(BE_WIDTH<=1)?1:$clog2(BE_WIDTH+1);
    reg [CREDIT_WIDTH-1:0] rob_credit, rs_credit, lsq_credit;
    // A registered reservoir count is already a ready boundary. Do not add
    // another conservative lag that would halve full-width allocation.
    wire [CREDIT_WIDTH-1:0] phys_credit;
    reg [CREDIT_WIDTH-1:0] used_rob_credit, used_rs_credit, used_lsq_credit, used_phys_credit;
    integer credit_lane;
    wire [CREDIT_WIDTH-1:0] recovery_rob_credit;
    generate if(RECOVERY_ROB_CREDIT!=0 && RECOVERY_DIRECT_ACTIVE!=0) begin:g_recovery_rob_credit
        // Qualified apply holds head, blocks rename/commit, and leaves the
        // prefix through the pending branch: free'=ROB_ENTRIES-1-branch_age.
        // Decode only the small saturated credit classes, avoiding a late
        // free-count subtract/compare on the recovery qualification path.
        wire [BE_WIDTH-1:0] credit_events;
        wire [BE_WIDTH*CREDIT_WIDTH-1:0] credit_values;
        genvar credit_class;
        for(credit_class=1;credit_class<=BE_WIDTH;credit_class=credit_class+1) begin:g_class
            localparam integer AGE_BOUND=ROB_ENTRIES-1-credit_class;
            if(credit_class>ROB_ENTRIES-1) begin:g_impossible
                assign credit_events[credit_class-1]=1'b0;
            end else if(credit_class==BE_WIDTH) begin:g_saturated
                assign credit_events[credit_class-1]=
                    execution_branch_age<=ROB_SLOT_WIDTH'(AGE_BOUND);
            end else begin:g_exact
                assign credit_events[credit_class-1]=
                    execution_branch_age==ROB_SLOT_WIDTH'(AGE_BOUND);
            end
            assign credit_values[(credit_class-1)*CREDIT_WIDTH +: CREDIT_WIDTH]=CREDIT_WIDTH'(credit_class);
        end
        rv32_frequency_event_select #(.WIDTH(CREDIT_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) select_credit (
            .events_i(credit_events),.values_i(credit_values),.write_o(),.value_o(recovery_rob_credit));
    end else begin:g_original_recovery_credit
        assign recovery_rob_credit=0;
    end endgenerate
    function [CREDIT_WIDTH-1:0] bounded_credit;
        input [15:0] available;
        input [CREDIT_WIDTH-1:0] consumed;
        reg [15:0] remaining;
        begin
            remaining=(available>=consumed)?available-consumed:16'b0;
            bounded_credit=(remaining>=BE_WIDTH)?BE_WIDTH:remaining;
        end
    endfunction
    function [CREDIT_WIDTH-1:0] reserved_credit;
        input [15:0] available,reserved;
        input [CREDIT_WIDTH-1:0] newly_reserved;
        reg [15:0] unreserved;
        begin
            unreserved=(available>=reserved)?available-reserved:16'b0;
            reserved_credit=bounded_credit(unreserved,newly_reserved);
        end
    endfunction
    // At the next edge actual free slots F' = F - accepted + releases.
    // Advertise min(BE_WIDTH,F-accepted), omitting this edge's releases.
    // Thus registered credits never promise more than actual capacity.
    always @* begin
        used_rob_credit=0; used_rs_credit=0; used_lsq_credit=0; used_phys_credit=0;
        for(credit_lane=0;credit_lane<BE_WIDTH;credit_lane=credit_lane+1) begin
            if(dispatch_valid[credit_lane]) begin
                used_rob_credit=used_rob_credit+1'b1;
                used_rs_credit=used_rs_credit+1'b1;
                if(trace_is_load_i[credit_lane] || trace_is_store_i[credit_lane])
                    used_lsq_credit=used_lsq_credit+1'b1;
                if(rename_rd_we[credit_lane]) used_phys_credit=used_phys_credit+1'b1;
            end
        end
    end
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            rob_credit<=0;rs_credit<=0;lsq_credit<=0;
        end else begin
            if(RECOVERY_ROB_CREDIT!=0 && RECOVERY_DIRECT_ACTIVE!=0 && recovery_domains[7])
                rob_credit<=recovery_rob_credit;
            else rob_credit<=bounded_credit(rob_free_count,used_rob_credit);
            rs_credit<=reserved_credit(rs_free_count,d_reserved_rs,used_rs_credit);
            lsq_credit<=reserved_credit(lsq_free_count,d_reserved_lsq,used_lsq_credit);
        end
    end
    wire [BE_WIDTH-1:0] completion_valid_r, completion_done_r, completion_error_r;
    wire [BE_WIDTH*TAG_WIDTH-1:0] completion_tag_r;
    wire [BE_WIDTH*32-1:0] completion_value_r, completion_store_addr_r;
    wire [BE_WIDTH*4-1:0] completion_store_mask_r;
    wire [BE_WIDTH*32-1:0] completion_store_data_r;

    // Recovery consumes one ROB completion lane. Keep the remaining CDB
    // bandwidth live as a contiguous prefix instead of freezing the whole
    // completion network until the redirect is accepted.
    always @* begin
        cdb_ready_r = {BE_WIDTH{1'b1}};
        if (branch_pending) begin
            for (cdb_ready_lane = 0; cdb_ready_lane < BE_WIDTH;
                 cdb_ready_lane = cdb_ready_lane + 1)
                cdb_ready_r[cdb_ready_lane] =
                    (cdb_ready_lane < (CDB_WIDTH - 1));
        end
    end
    assign cdb_ready = cdb_ready_r;

    genvar io_lane,link_word;
    generate
        for (io_lane = 0; io_lane < BE_WIDTH; io_lane = io_lane + 1) begin : g_backend_lane_io
            // Direct completion can reach the ROB on the SAME edge that
            // captures the LSQ error in load_error_mem. Carry this result's
            // precise error alongside its value rather than reading the old
            // flag. Full-tag qualification protects recycled ROB slots.
            assign completion_live_load_error[io_lane] =
                (COMPLETION_BYPASS == 2) && cdb_is_load[io_lane] &&
                lsq_load_complete_valid && lsq_load_complete_error &&
                (cdb_tag[io_lane*TAG_WIDTH +: TAG_WIDTH] == lsq_load_complete_tag);
            // The public trace interface retains its legacy line-sized field,
            // while the backend stores only the access-relative low word.
            assign trace_store_data_relative[io_lane*32 +: 32] =
                trace_store_data_i[io_lane*128 +: 32];
            // An allocation may advertise an address only when this
            // optional path is enabled. Disabled payload is constant as well,
            // so an unused PRF -> adder -> LSQ write cone can be removed.
            if(STORE_ALLOC_EARLY_ADDRESS!=0) begin:g_alloc_address_enabled
                assign lsq_alloc_addr_valid[io_lane] = (EARLY_STORE_ADDRESS != 0) &&
                    d_valid[io_lane] && (d_is_store[io_lane] ||
                        ((EARLY_LOAD_ADDRESS != 0) && d_is_load[io_lane])) && rs_src1_ready[io_lane];
                if(STORE_ALLOC_EARLY_ADDRESS==2 && STORE_ALLOC_IMM12!=0 && PRF_READ_MUX_IMPL!=0) begin:g_parallel_prf_address
                    assign lsq_alloc_addr[io_lane*32 +: 32]=prf_store_address[io_lane*32 +: 32];
                end else if(STORE_ALLOC_IMM12!=0) begin:g_store_alloc_simm12
                    // Ready loads may use the same allocation address when enabled.
                    // Ordinary AGU issue and full-tag LSQ updates remain active.
                    rv32_frequency_add_simm12 address_adder (
                        .base_i(rs_src1_value[io_lane*32 +: 32]),
                        .immediate_i(d_imm[io_lane*32 +: 12]),
                        .sum_o(lsq_alloc_addr[io_lane*32 +: 32]));
                end else begin:g_store_alloc_generic
                    assign lsq_alloc_addr[io_lane*32 +: 32] =
                        rs_src1_value[io_lane*32 +: 32] + d_imm[io_lane*32 +: 32];
                end
            end else begin:g_shared_or_ordinary_address
                assign lsq_alloc_addr_valid[io_lane]=1'b0;
                assign lsq_alloc_addr[io_lane*32 +: 32]=32'b0;
            end
            assign prf_read_phys[(2*io_lane)*PAW +: PAW] =
                d_src1_phys[io_lane*PAW +: PAW];
            assign prf_read_phys[(2*io_lane+1)*PAW +: PAW] =
                d_src2_phys[io_lane*PAW +: PAW];
            if (RS_ISSUE_METADATA != 0) begin : g_inline_metadata
                // {unsigned, size, prediction kind, target, taken, immediate}
                assign rs_alloc_metadata[io_lane*RS_METADATA_WIDTH +: RS_METADATA_WIDTH] =
                    {d_mem_unsigned[io_lane], d_mem_size[io_lane*2 +: 2],
                     d_pred_kind[io_lane*2 +: 2], d_pred_target[io_lane*32 +: 32],
                     d_pred_taken[io_lane], d_imm[io_lane*32 +: 32]};
                assign rs_issue_imm[io_lane*32 +: 32] = rs_issue_metadata[io_lane*RS_METADATA_WIDTH +: 32];
                assign rs_issue_pred_taken[io_lane] = rs_issue_metadata[io_lane*RS_METADATA_WIDTH+32];
                assign rs_issue_pred_target[io_lane*32 +: 32] = rs_issue_metadata[io_lane*RS_METADATA_WIDTH+33 +: 32];
                assign rs_issue_pred_kind[io_lane*2 +: 2] = rs_issue_metadata[io_lane*RS_METADATA_WIDTH+65 +: 2];
                assign rs_issue_mem_size[io_lane*2 +: 2] = rs_issue_metadata[io_lane*RS_METADATA_WIDTH+67 +: 2];
                assign rs_issue_mem_unsigned[io_lane] = rs_issue_metadata[io_lane*RS_METADATA_WIDTH+69];
            end else begin : g_rob_metadata
                assign rs_alloc_metadata[io_lane*RS_METADATA_WIDTH +: RS_METADATA_WIDTH] = {RS_METADATA_WIDTH{1'b0}};
                assign rs_issue_imm[io_lane*32 +: 32] = rob_imm_mem[rs_issue_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]];
                assign rs_issue_pred_taken[io_lane] = rob_pred_taken_mem[rs_issue_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]];
                assign rs_issue_pred_target[io_lane*32 +: 32] = rob_pred_target_mem[rs_issue_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]];
                assign rs_issue_pred_kind[io_lane*2 +: 2] = rob_pred_kind_mem[rs_issue_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]];
                assign rs_issue_mem_size[io_lane*2 +: 2] = rob_mem_size_mem[rs_issue_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]];
                assign rs_issue_mem_unsigned[io_lane] = rob_mem_unsigned_mem[rs_issue_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]];
            end
            assign rs_issue_is_mdu[io_lane] =
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MUL) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MULH) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MULHSU) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_MULHU) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_DIV) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_DIVU) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_REM) ||
                (rs_issue_op[io_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_REMU);
            if(RS_ROW_QUALIFICATION_ACTIVE!=0) begin:g_row_qualified_issue
                assign rs_issue_allowed[io_lane]=!branch_busy_domains[0] ||
                    raw_rs_issue_recovery_qualified[io_lane];
            end else begin:g_original_issue_qualification
            // Preview uses the live head. Apply uses the captured recovery
            // packet, and can issue only a retained row with the exact current
            // ROB generation. The RS now releases accepted retained rows on
            // that edge, so they cannot be issued again after recovery.
            wire [ROB_SLOT_WIDTH-1:0] issue_age=
                rs_issue_tag[io_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]-rob_head;
            wire [ROB_SLOT_WIDTH-1:0] pending_age=
                recovery_tag_views[3 +: ROB_SLOT_WIDTH]-rob_head;
            wire older_preview=(RECOVERY_PREVIEW_OLDER_ISSUE!=0) &&
                (LOCAL_EXEC_RECOVERY!=0) && (ISSUE_PIPELINE==0) &&
                branch_pending && rob_recovery_preview && !recovery_descriptor_valid &&
                !reset_i && !flush_i && rs_issue_valid[io_lane] &&
                rs_issue_tag[io_lane*TAG_WIDTH] && issue_age<pending_age &&
                issue_age<rob_occupancy;
            wire older_apply;
            if(RECOVERY_APPLY_ISSUE_ACTIVE!=0) begin:g_apply_issue
                wire [ROB_LIVE_WIDTH-1:0] issue_live;
                wire issue_cancel;
                rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),
                    .index_i(rs_issue_tag[io_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                    .value_o(issue_live));
                rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
                    .ENABLED(1),.KILL_BRANCH(1)) age_guard (
                    .packet_i(execution_recovery_views[io_lane*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
                    .active_i(rs_issue_valid[io_lane]),
                    .tag_i(rs_issue_tag[io_lane*TAG_WIDTH +: TAG_WIDTH]),.cancel_o(issue_cancel));
                assign older_apply=branch_pending && recovery_descriptor_valid && recovery_domains[4] &&
                    !reset_i && !flush_i && rs_issue_valid[io_lane] && rs_issue_tag[io_lane*TAG_WIDTH] &&
                    issue_live[ROB_GENERATION_WIDTH] &&
                    rs_issue_tag[io_lane*TAG_WIDTH+3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
                        issue_live[0 +: ROB_GENERATION_WIDTH] && !issue_cancel;
            end else begin:g_apply_issue_disabled
                assign older_apply=1'b0;
            end
            assign rs_issue_allowed[io_lane]=!branch_busy_domains[0] || older_preview || older_apply;
            end
            assign rs_issue_ready[io_lane] = rs_issue_allowed[io_lane] &&
                (rs_issue_is_mdu[io_lane] ?
                 (mdu_select[io_lane] && mdu_issue_ready) :
                 ((io_lane < INT_ISSUE_WIDTH) ? alu_issue_ready[io_lane] : 1'b0));
            assign lsq_addr_update_valid[io_lane] =
                alu_exec_valid[io_lane] && alu_exec_is_memory[io_lane];
            assign lsq_addr_update_tag[io_lane*TAG_WIDTH +: TAG_WIDTH] =
                alu_lsq_map_read[io_lane*TAG_WIDTH +: TAG_WIDTH];
            assign lsq_addr_update[io_lane*32 +: 32] =
                alu_exec_mem_addr[io_lane*32 +: 32];
            assign lsq_data_update_valid[io_lane] =
                alu_exec_valid[io_lane] && alu_exec_is_store[io_lane];
            assign lsq_data_update_tag[io_lane*TAG_WIDTH +: TAG_WIDTH] =
                alu_lsq_map_read[io_lane*TAG_WIDTH +: TAG_WIDTH];
            // Recovery reserves CDB slot CDB_WIDTH-1 for its direct ROB
            // completion.  Reuse the corresponding idle PRF write slot so a
            // redirecting JAL/JALR also publishes its link value.  An ordinary
            // completion in this lane remains queued by cdb_ready.
            if(io_lane==CDB_WIDTH-1) begin:g_branch_link_route
                localparam integer PHYS_WORDS=(PAW+15)/16;
                wire [PHYS_WORDS+2:0] link_views;
                rv32_frequency_control_tree #(.LEAVES(PHYS_WORDS+3)) link_tree (
                    .signal_i(branch_pending && branch_pending_rd_we),.views_o(link_views));
                assign prf_write_valid[io_lane]=link_views[PHYS_WORDS+2] || completion_prf_write_valid[io_lane];
                for(link_word=0;link_word<PHYS_WORDS;link_word=link_word+1) begin:g_phys_word
                    localparam integer LOW=link_word*16;
                    localparam integer BITS=(PAW-LOW>=16)?16:PAW-LOW;
                    assign prf_write_phys[io_lane*PAW+LOW +: BITS]=link_views[link_word]?
                        branch_pending_phys[LOW +: BITS]:completion_prf_write_phys[io_lane*PAW+LOW +: BITS];
                end
                for(link_word=0;link_word<2;link_word=link_word+1) begin:g_value_word
                    assign prf_write_data[io_lane*32+link_word*16 +: 16]=link_views[PHYS_WORDS+link_word]?
                        branch_pending_value[link_word*16 +: 16]:completion_prf_write_data[io_lane*32+link_word*16 +: 16];
                end
            end else begin:g_normal_link_route
                assign prf_write_valid[io_lane]=completion_prf_write_valid[io_lane];
                assign prf_write_phys[io_lane*PAW +: PAW]=completion_prf_write_phys[io_lane*PAW +: PAW];
                assign prf_write_data[io_lane*32 +: 32]=completion_prf_write_data[io_lane*32 +: 32];
            end
        end
    endgenerate

    // Ready is a contiguous, resource-qualified prefix and remains meaningful
    // before valid is asserted. Rename performs the identical acceptance check
    // using the actual valid prefix.
    always @* begin
        trace_ready_r = {BE_WIDTH{1'b0}};
        ready_rob_used = 0;
        ready_rs_used = 0;
        ready_lsq_used = 0;
        ready_phys_used = 0;
        for (ready_lane = 0; ready_lane < BE_WIDTH; ready_lane = ready_lane + 1) begin
            ready_rob_used = ready_rob_used + 1;
            ready_rs_used = ready_rs_used + 1;
            if (trace_is_load_i[ready_lane] || trace_is_store_i[ready_lane])
                ready_lsq_used = ready_lsq_used + 1;
            if (trace_rd_we_i[ready_lane] &&
                (trace_rd_i[ready_lane*5 +: 5] != 0))
                ready_phys_used = ready_phys_used + 1;
            if (!halted_o && !flush_i && !branch_busy_domains[0] && dispatch_packet_ready &&
                (ready_rob_used <= rob_credit) &&
                ((DISPATCH_ELASTIC!=0) || (ready_rs_used <= rs_credit)) &&
                ((DISPATCH_ELASTIC!=0) || (ready_lsq_used <= lsq_credit)) &&
                (ready_phys_used <= phys_credit))
                trace_ready_r[ready_lane] = 1'b1;
        end
    end
    assign trace_ready_o = trace_ready_r;
    assign rob_alloc_valid = dispatch_valid;
    genvar dispatch_lane;
    generate
        for(dispatch_lane=0;dispatch_lane<BE_WIDTH;dispatch_lane=dispatch_lane+1) begin:g_dispatch_fields
            assign d_payload_in[dispatch_lane*DISPATCH_PAYLOAD_WIDTH +: DISPATCH_PAYLOAD_WIDTH]={
                trace_pc_i[dispatch_lane*32 +: 32],
                trace_op_i[dispatch_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH],
                trace_imm_i[dispatch_lane*32 +: 32],
                trace_is_load_i[dispatch_lane],
                trace_is_store_i[dispatch_lane],
                trace_mem_size_i[dispatch_lane*2 +: 2],
                trace_mem_unsigned_i[dispatch_lane],
                trace_store_data_relative[dispatch_lane*32 +: 32],
                trace_pred_taken_i[dispatch_lane],
                trace_pred_target_i[dispatch_lane*32 +: 32],
                trace_pred_kind_i[dispatch_lane*2 +: 2],
                rename_new_phys[dispatch_lane*PAW +: PAW],
                rename_rs1_phys[dispatch_lane*PAW +: PAW],
                rename_rs2_phys[dispatch_lane*PAW +: PAW]};
            assign {d_pc[dispatch_lane*32 +: 32],
                d_op[dispatch_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH],
                d_imm[dispatch_lane*32 +: 32],
                d_is_load[dispatch_lane],
                d_is_store[dispatch_lane],
                d_mem_size[dispatch_lane*2 +: 2],
                d_mem_unsigned[dispatch_lane],
                d_store_data[dispatch_lane*32 +: 32],
                d_pred_taken[dispatch_lane],
                d_pred_target[dispatch_lane*32 +: 32],
                d_pred_kind[dispatch_lane*2 +: 2],
                d_new_phys[dispatch_lane*PAW +: PAW],
                d_src1_phys[dispatch_lane*PAW +: PAW],
                d_src2_phys[dispatch_lane*PAW +: PAW]}=d_payload_out[dispatch_lane*DISPATCH_PAYLOAD_WIDTH +: DISPATCH_PAYLOAD_WIDTH];
        end
        if(DISPATCH_PIPELINE!=0 && DISPATCH_ELASTIC!=0) begin:g_elastic_dispatch
            rv32_elastic_dispatch_packet #(.FULL_REPLACE(DISPATCH_FULL_REPLACE),.LANES(BE_WIDTH),.PAYLOAD_WIDTH(DISPATCH_PAYLOAD_WIDTH),
                .TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES)) packet (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.hold_i(branch_busy_domains[3]),
                .recovery_i(recovery_domains[7]),
                .recovery_head_i(recovery_head_views[0 +: ROB_SLOT_WIDTH]),
                .recovery_tag_i(recovery_tag_views[0 +: TAG_WIDTH]),
                .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1'b0}},recovery_descriptor_occupancy}),
                .rob_valid_i(rob_entry_valid),.rob_generation_i(rob_entry_generation),
                .valid_i(dispatch_valid & rob_alloc_fire),.tag_i(rob_alloc_tag),.data_i(d_payload_in),
                .ready_o(dispatch_packet_ready),.valid_o(d_valid),.tag_o(d_tag),.data_o(d_payload_out),
                .replace_credit_i(d_replace_credit),.consume_i(d_admit));
            assign d_reserved_rs=0;assign d_reserved_lsq=0;
        end else if(DISPATCH_PIPELINE!=0) begin:g_reserved_dispatch
            assign dispatch_packet_ready=1'b1;
            rv32_reserved_dispatch_packet #(.LANES(BE_WIDTH),.PAYLOAD_WIDTH(DISPATCH_PAYLOAD_WIDTH),
                .TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES)) packet (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.hold_i(branch_busy_domains[3]),
                .recovery_i(recovery_domains[7]),
                .recovery_head_i(recovery_head_views[0 +: ROB_SLOT_WIDTH]),
                .recovery_tag_i(recovery_tag_views[0 +: TAG_WIDTH]),
                .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1'b0}},recovery_descriptor_occupancy}),
                .rob_valid_i(rob_entry_valid),.rob_generation_i(rob_entry_generation),
                .valid_i(dispatch_valid & rob_alloc_fire),.tag_i(rob_alloc_tag),.data_i(d_payload_in),
                .saved_is_memory_i(d_is_load | d_is_store),
                .valid_o(d_valid),.tag_o(d_tag),.data_o(d_payload_out),
                .reserved_rs_o(d_reserved_rs),.reserved_lsq_o(d_reserved_lsq));
        end else begin:g_direct_dispatch
            assign dispatch_packet_ready=1'b1;
            assign d_valid=dispatch_valid;
            assign d_tag=rob_alloc_tag;
            assign d_payload_out=d_payload_in;
            assign d_reserved_rs=0;assign d_reserved_lsq=0;
        end
    endgenerate
    // The same predicate that writes an authoritative LSQ address
    // proves this load needs no later AGU. LSQ remains its sole completion
    // producer. Elastic mode admits only its actual D resource demand.
    wire [BE_WIDTH-1:0] load_without_agu = (EARLY_LOAD_ADDRESS>=2) ?
        (d_is_load & ~d_is_store & lsq_alloc_addr_valid) : {BE_WIDTH{1'b0}};

    localparam integer FAST_STORE_COMPLETE_ACTIVE=(FAST_STORE_COMPLETE!=0) &&
        (DISPATCH_PIPELINE!=0) && (DISPATCH_ELASTIC!=0) &&
        (STORE_ALLOC_EARLY_ADDRESS!=0) && (EARLY_STORE_ADDRESS!=0) &&
        (STORE_ALLOC_EARLY_DATA!=0) && (ROB_ALLOC_BANKED_WRITE!=0) &&
        (ROB_ENTRIES>=BE_WIDTH) && (LIGHT_RETIRE_PAYLOAD!=0) &&
        (ROB_MMIO_PREDECODE!=0) && (ROB_LEGACY_HALT_PAYLOAD==0) &&
        (ROB_RETURN_VALUE_ENABLE==0);
    wire [BE_WIDTH-1:0] ready_store_candidates,store_without_agu,rob_fast_store_valid;
    wire [BE_WIDTH-1:0] potential_store_candidates,potential_store_grants;
    wire [TAG_WIDTH-1:0] preselected_store_tag;
    // Identity selection depends only on the already saved D packet. It
    // intentionally precedes PRF readiness and address-class qualification.
    rv32_frequency_event_select #(.WIDTH(TAG_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) store_identity_selector (
        .events_i(potential_store_grants),.values_i(d_tag),.write_o(),.value_o(preselected_store_tag));
    wire [BE_WIDTH-1:0] rob_fast_store_publish_valid=(FAST_STORE_IDENTITY_PRESELECT!=0) ?
        {{(BE_WIDTH-1){1'b0}},(|rob_fast_store_valid)} : rob_fast_store_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] rob_fast_store_publish_tag=(FAST_STORE_IDENTITY_PRESELECT!=0) ?
        {{((BE_WIDTH-1)*TAG_WIDTH){1'b0}},preselected_store_tag} : d_tag;
    generate if(FAST_STORE_COMPLETE_ACTIVE!=0) begin:g_ready_ram_store_complete
        for(genvar ready_store_lane=0;ready_store_lane<BE_WIDTH;ready_store_lane=ready_store_lane+1) begin:g_lane
            wire [31:0] address=lsq_alloc_addr[ready_store_lane*32 +: 32];
            wire [31:0] immediate=d_imm[ready_store_lane*32 +: 32];
            wire [`RV32IM_OP_WIDTH-1:0] op=d_op[ready_store_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];
            wire [1:0] size=d_mem_size[ready_store_lane*2 +: 2];
            wire [2:0] address_flags=((FAST_STORE_ADDRESS_PREDECODE!=0) && PARALLEL_STORE_ADDRESS) ?
                prf_store_address_flags[ready_store_lane*3 +: 3] :
                {address[1:0]==2'b00,!address[0],address[31:28]==4'b0000};
            wire ordinary_store=(op==`RV32IM_OP_SB && size==2'd0) ||
                (op==`RV32IM_OP_SH && size==2'd1 && address_flags[1]) ||
                (op==`RV32IM_OP_SW && size==2'd2 && address_flags[2]);
            wire canonical_immediate=(STORE_ALLOC_IMM12==0) ||
                immediate[31:12]=={20{immediate[11]}};
            // LSQ already trusts these authoritative address/data values.
            // Exclude MMIO/non-RAM and malformed/misaligned tuples from this
            // optimization; they retain their original execution protocol.
            assign ready_store_candidates[ready_store_lane]=d_valid[ready_store_lane] &&
                d_is_store[ready_store_lane] && !d_is_load[ready_store_lane] &&
                lsq_alloc_addr_valid[ready_store_lane] && lsq_alloc_data_valid[ready_store_lane] &&
                address_flags[0] && ordinary_store && canonical_immediate &&
                // Original ALU uses explicit trace store data when nonzero,
                // otherwise its authoritative src2. Core always passes0;
                // other callers keep that exact override on the old path.
                d_store_data[ready_store_lane*32 +: 32]==32'b0;
            wire ordinary_store_metadata=(op==`RV32IM_OP_SB && size==2'd0) ||
                (op==`RV32IM_OP_SH && size==2'd1) || (op==`RV32IM_OP_SW && size==2'd2);
            assign potential_store_candidates[ready_store_lane]=(FAST_STORE_IDENTITY_PRESELECT!=0) &&
                d_valid[ready_store_lane] && d_is_store[ready_store_lane] && !d_is_load[ready_store_lane] &&
                ordinary_store_metadata && canonical_immediate &&
                d_store_data[ready_store_lane*32 +: 32]==32'b0;
            if(ready_store_lane==0) begin:g_first
                assign potential_store_grants[ready_store_lane]=potential_store_candidates[ready_store_lane];
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane] &&
                    ((FAST_STORE_IDENTITY_PRESELECT==0) || potential_store_grants[ready_store_lane]);
            end else begin:g_later
                assign potential_store_grants[ready_store_lane]=potential_store_candidates[ready_store_lane] &&
                    !(|potential_store_candidates[ready_store_lane-1:0]);
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane] &&
                    ((FAST_STORE_IDENTITY_PRESELECT!=0) ? potential_store_grants[ready_store_lane] :
                    !(|ready_store_candidates[ready_store_lane-1:0]));
            end
            // Only a real atomic D/LSQ allocation may publish completion.
            // Saved D tags remain separate per lane, so ROB identity matching
            // can finish before the late ready/allocation event arrives.
            assign rob_fast_store_valid[ready_store_lane]=!reset_i && !flush_i &&
                !branch_busy_domains[3] && store_without_agu[ready_store_lane] &&
                lsq_alloc_fire[ready_store_lane];
        end
    end else begin:g_original_store_execution
        assign potential_store_candidates=0;
        assign potential_store_grants=0;
        assign ready_store_candidates={BE_WIDTH{1'b0}};
        assign store_without_agu={BE_WIDTH{1'b0}};
        assign rob_fast_store_valid={BE_WIDTH{1'b0}};
    end endgenerate

    // Count raw D demand before gating either allocator, avoiding an
    // alloc_fire -> valid -> alloc_fire combinational readiness loop.
    // Only saved occupancy/free counts determine atomic acceptance.
    wire [BE_WIDTH-1:0] d_rs_need=d_valid & ~(load_without_agu | store_without_agu);
    wire [BE_WIDTH-1:0] d_lsq_need=d_valid & (d_is_load | d_is_store);
    reg [CREDIT_WIDTH-1:0] d_rs_demand,d_lsq_demand;
    integer demand_lane;
    always @* begin
        d_rs_demand=0;d_lsq_demand=0;
        for(demand_lane=0;demand_lane<BE_WIDTH;demand_lane=demand_lane+1) begin
            d_rs_demand=d_rs_demand+d_rs_need[demand_lane];
            d_lsq_demand=d_lsq_demand+d_lsq_need[demand_lane];
        end
    end
    // This conservative credit path intentionally has no PRF read, early
    // load readiness, allocation result or R-input dependency. Counting ALL
    // valid lanes as RS demand guarantees admission regardless of which
    // ready loads later skip RS. Thus replace_credit implies d_admit/pop.
    reg [CREDIT_WIDTH-1:0] d_replace_rs_demand,d_replace_lsq_demand;
    integer replace_lane;
    always @* begin
        d_replace_rs_demand=0;d_replace_lsq_demand=0;
        for(replace_lane=0;replace_lane<BE_WIDTH;replace_lane=replace_lane+1) begin
            d_replace_rs_demand=d_replace_rs_demand+d_valid[replace_lane];
            d_replace_lsq_demand=d_replace_lsq_demand+
                (d_valid[replace_lane] && (d_is_load[replace_lane] || d_is_store[replace_lane]));
        end
    end
    wire d_replace_credit=(DISPATCH_FULL_REPLACE!=0) && (|d_valid) &&
        !reset_i && !flush_i && !branch_busy_domains[3] &&
        d_replace_rs_demand<=rs_free_count && d_replace_lsq_demand<=lsq_free_count;
    assign d_admit=(DISPATCH_ELASTIC==0) ||
        (!reset_i && !flush_i && !branch_busy_domains[3] &&
         (d_rs_demand<=rs_free_count) && (d_lsq_demand<=lsq_free_count));
    assign rs_alloc_valid=d_rs_need & {BE_WIDTH{d_admit}};
    assign lsq_alloc_valid=d_lsq_need & {BE_WIDTH{d_admit}};

    assign commit_valid_o = rob_commit_valid;
    assign perf_rob_occupancy_o = {{(16-ROB_COUNT_WIDTH){1'b0}}, rob_occupancy};
    assign perf_rs_occupancy_o = rs_occupancy;
    assign perf_lsq_occupancy_o = lsq_occupancy;
    assign perf_issue_valid_o = rs_issue_valid & rs_issue_ready;
    assign perf_branch_pending_o = branch_pending;
    assign perf_mdu_busy_o = mdu_busy;
    assign commit_pc_o = rob_commit_pc;
    assign commit_inst_o = rob_commit_inst;
    assign commit_rd_o = rob_commit_rd;
    assign commit_rd_we_o = rob_commit_rd_we;
    assign commit_value_o = rob_commit_value;
    assign commit_is_store_o = rob_commit_is_store;
    assign commit_store_addr_o = rob_commit_store_addr;
    assign commit_store_mask_o = rob_commit_store_mask;
    assign commit_store_data_o = rob_commit_store_data;
    assign commit_tag_o = rob_commit_tag;
    generate if(EARLY_FRONT_REDIRECT!=0) begin:g_early_front_redirect
        // Same first-lane grant and full ROB-generation authority used to
        // acquire branch_pending. The pending queue blocks a second redirect
        // until recovery applies. Do not redirect again on the preview edge.
        assign redirect_valid_o=branch_capture_write;
        assign redirect_pc_o=branch_capture_next[31:0];
    end else begin:g_preview_front_redirect
        // History-indexed prediction retains its registered history snapshot.
        assign redirect_valid_o=recovery_preview_fire;
        assign redirect_pc_o=rob_redirect_pc;
    end endgenerate
    assign redirect_epoch_o = rob_redirect_epoch;
    assign branch_feedback_valid_o = branch_feedback_valid_r;
    assign branch_feedback_pc_o = branch_feedback_pc_r;
    assign branch_feedback_kind_o = branch_feedback_kind_r;
    assign branch_feedback_taken_o = branch_feedback_taken_r;
    assign branch_feedback_target_o = branch_feedback_target_r;
    assign branch_feedback_pred_taken_o = branch_feedback_pred_taken_r;
    assign branch_feedback_pred_target_o = branch_feedback_pred_target_r;
    wire [15:0] rob_pred_metadata_mem [0:ROB_ENTRIES-1];

    // Train on every resolved control-flow instruction, not only on the
    // mispredictions that enter branch_pending.  The previous policy left
    // loop counters and BTB entries almost untrained once a prediction became
    // correct.  One feedback port selects the oldest/lowest issue lane.
    wire [BE_WIDTH-1:0] branch_training_live;
    genvar training_lane;
    generate for (training_lane = 0; training_lane < BE_WIDTH; training_lane = training_lane + 1) begin : g_training_live
        assign branch_training_live[training_lane] = !reset_i && !flush_i && !alu_flush_r[training_lane] &&
            alu_exec_tag[training_lane*TAG_WIDTH] &&
            producer_live_reads[training_lane*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&
            (alu_exec_tag[training_lane*TAG_WIDTH+3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==
             producer_live_reads[training_lane*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]);
    end endgenerate

    localparam integer FEEDBACK_LANE_WIDTH=(BE_WIDTH<=1)?1:$clog2(BE_WIDTH);
    localparam integer FEEDBACK_PACKET_WIDTH=100+ROB_SLOT_WIDTH;
    wire [BE_WIDTH-1:0] feedback_candidates,feedback_grants;
    wire [FEEDBACK_LANE_WIDTH-1:0] feedback_lane;
    wire [BE_WIDTH*FEEDBACK_PACKET_WIDTH-1:0] feedback_values;
    wire [FEEDBACK_PACKET_WIDTH-1:0] feedback_packet;
    rv32_frequency_first_two #(.ENTRIES(BE_WIDTH),.INDEX_WIDTH(FEEDBACK_LANE_WIDTH)) feedback_selector (
        .candidates_i(feedback_candidates),.first_valid_o(branch_feedback_valid_r),.first_index_o(feedback_lane),
        .second_valid_o(),.second_index_o());
    rv32_frequency_event_select #(.WIDTH(FEEDBACK_PACKET_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) feedback_payload_selector (
        .events_i(feedback_grants),.values_i(feedback_values),.write_o(),.value_o(feedback_packet));
    assign {branch_feedback_slot,branch_feedback_pc_r,branch_feedback_kind_r,branch_feedback_taken_r,
        branch_feedback_target_r,branch_feedback_pred_taken_r,branch_feedback_pred_target_r}=feedback_packet;
    genvar feedback_source,feedback_row;
    generate
        for(feedback_source=0;feedback_source<BE_WIDTH;feedback_source=feedback_source+1) begin:g_feedback_source
            wire [ROB_SLOT_WIDTH-1:0] slot=alu_exec_tag[feedback_source*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            wire [31:0] pc,pred_target;
            wire [1:0] kind;
            wire pred_taken;
            assign feedback_candidates[feedback_source]=alu_exec_valid[feedback_source] && alu_exec_ready[feedback_source] &&
                (PREDICTOR_META==0 || branch_training_live[feedback_source]) && alu_exec_is_branch[feedback_source];
            assign feedback_grants[feedback_source]=branch_feedback_valid_r && feedback_lane==feedback_source;
            // Every exported lane has its own complete ROB lifetime check.
            // No new execution-ready/backpressure condition is introduced.
            assign branch_feedback_lane_valid_o[feedback_source]=
                feedback_candidates[feedback_source] && branch_training_live[feedback_source];
            if(RS_ISSUE_METADATA!=0) begin:g_inline
                assign pc=alu_exec_source_pc[feedback_source*32 +: 32];
                assign kind=alu_exec_pred_kind[feedback_source*2 +: 2];
                assign pred_taken=alu_exec_pred_taken[feedback_source];
                assign pred_target=alu_exec_pred_target[feedback_source*32 +: 32];
            end else begin:g_legacy
                wire [ROB_ENTRIES*67-1:0] metadata_rows;
                for(feedback_row=0;feedback_row<ROB_ENTRIES;feedback_row=feedback_row+1) begin:g_row
                    assign metadata_rows[feedback_row*67 +: 67]={rob_pc_mem[feedback_row],
                        rob_pred_kind_mem[feedback_row],rob_pred_taken_mem[feedback_row],rob_pred_target_mem[feedback_row]};
                end
                rv32_frequency_array_read #(.WIDTH(67),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(ROB_SLOT_WIDTH)) metadata_read (
                    .rows_i(metadata_rows),.index_i(slot),.value_o({pc,kind,pred_taken,pred_target}));
            end
            // Expand only after execution, outside FQ/dispatch/RS storage.
            // Training receives the full expected target for a page-qualified
            // JALR or the exact computed target for direct control flow.
            wire [31:0] full_pred_target=(COMPACT_PRED_TARGET!=0)?
                ((kind==`RV32IM_PRED_JALR)?{pc[31:12],pred_target[11:0]}:
                    alu_exec_branch_target[feedback_source*32 +: 32]):pred_target;
            assign feedback_values[feedback_source*FEEDBACK_PACKET_WIDTH +: FEEDBACK_PACKET_WIDTH]={
                slot,pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};
            assign branch_feedback_lane_packets_o[feedback_source*100 +: 100]={
                pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};
            if(PREDICTOR_META!=0) begin:g_indexed_training
                wire [ROB_ENTRIES*16-1:0] rows;
                for(genvar history_row=0;history_row<ROB_ENTRIES;history_row=history_row+1) begin:g_row
                    assign rows[history_row*16 +: 16]=rob_pred_metadata_mem[history_row];
                end
                rv32_frequency_array_read #(.WIDTH(16),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(ROB_SLOT_WIDTH)) history_read (
                    .rows_i(rows),.index_i(slot),
                    .value_o(branch_feedback_lane_metadata_o[feedback_source*16 +: 16]));
            end else begin:g_pc_indexed_training
                assign branch_feedback_lane_metadata_o[feedback_source*16 +: 16]=0;
            end
        end
        if(PREDICTOR_META!=0) begin:g_feedback_history
            wire [ROB_ENTRIES*16-1:0] history_rows;
            wire [15:0] history;
            for(feedback_row=0;feedback_row<ROB_ENTRIES;feedback_row=feedback_row+1) begin:g_row
                assign history_rows[feedback_row*16 +: 16]=rob_pred_metadata_mem[feedback_row];
            end
            rv32_frequency_array_read #(.WIDTH(16),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(ROB_SLOT_WIDTH)) history_read (
                .rows_i(history_rows),.index_i(branch_feedback_slot),.value_o(history));
            rv32_frequency_event_select #(.WIDTH(16),.EVENTS(1)) valid_selector (
                .events_i(branch_feedback_valid_r),.values_i(history),.write_o(),.value_o(branch_feedback_metadata_o));
        end else begin:g_no_feedback_history
            assign branch_feedback_metadata_o=0;
        end
    endgenerate

    // One shared MDU accepts the oldest M-class selection while independent
    // ALUs may accept all other selected instructions in the same cycle.

    localparam integer MDU_ISSUE_BASE_PAYLOAD_WIDTH=`RV32IM_OP_WIDTH+64+TAG_WIDTH+PAW;
    localparam integer MDU_ISSUE_PAYLOAD_WIDTH=MDU_ISSUE_BASE_PAYLOAD_WIDTH+
        ((RS_ISSUE_CANCEL_PREDECODE_ACTIVE!=0)?1:0);
    localparam integer MDU_LANE_WIDTH=(BE_WIDTH<=1)?1:$clog2(BE_WIDTH);
    wire [BE_WIDTH-1:0] mdu_candidates=rs_issue_valid & rs_issue_is_mdu & rs_issue_allowed;
    wire mdu_found;
    wire [MDU_LANE_WIDTH-1:0] mdu_lane;
    wire [BE_WIDTH*MDU_ISSUE_PAYLOAD_WIDTH-1:0] mdu_values;
    rv32_frequency_first_two #(.ENTRIES(BE_WIDTH),.INDEX_WIDTH(MDU_LANE_WIDTH)) mdu_first_selector (
        .candidates_i(mdu_candidates),.first_valid_o(mdu_found),.first_index_o(mdu_lane),
        .second_valid_o(),.second_index_o());
    genvar mdu_route_lane;
    generate for(mdu_route_lane=0;mdu_route_lane<BE_WIDTH;mdu_route_lane=mdu_route_lane+1) begin:g_mdu_route
        assign mdu_select[mdu_route_lane]=mdu_found && mdu_lane==mdu_route_lane;
        wire [MDU_ISSUE_BASE_PAYLOAD_WIDTH-1:0] base_payload={
            rs_issue_op[mdu_route_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH],
            rs_issue_src1[mdu_route_lane*32 +: 32],rs_issue_src2[mdu_route_lane*32 +: 32],
            rs_issue_tag[mdu_route_lane*TAG_WIDTH +: TAG_WIDTH],rs_issue_phys[mdu_route_lane*PAW +: PAW]};
        if(RS_ISSUE_CANCEL_PREDECODE_ACTIVE!=0) begin:g_cancel_sideband
            assign mdu_values[mdu_route_lane*MDU_ISSUE_PAYLOAD_WIDTH +: MDU_ISSUE_PAYLOAD_WIDTH]=
                {raw_rs_issue_cancel[mdu_route_lane],base_payload};
        end else begin:g_original_payload
            assign mdu_values[mdu_route_lane*MDU_ISSUE_PAYLOAD_WIDTH +: MDU_ISSUE_PAYLOAD_WIDTH]=base_payload;
        end
    end endgenerate
    wire [MDU_ISSUE_PAYLOAD_WIDTH-1:0] mdu_selected_payload;
    rv32_frequency_event_select #(.WIDTH(MDU_ISSUE_PAYLOAD_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) mdu_payload_selector (
        .events_i(mdu_select),.values_i(mdu_values),.write_o(),.value_o(mdu_selected_payload));
    assign {mdu_issue_op,mdu_issue_src1,mdu_issue_src2,mdu_issue_tag,mdu_issue_phys}=
        mdu_selected_payload[0 +: MDU_ISSUE_BASE_PAYLOAD_WIDTH];
    generate if(RS_ISSUE_CANCEL_PREDECODE_ACTIVE!=0) begin:g_mdu_selected_cancel
        assign mdu_issue_cancel=mdu_selected_payload[MDU_ISSUE_BASE_PAYLOAD_WIDTH];
    end else begin:g_no_mdu_selected_cancel
        assign mdu_issue_cancel=1'b0;
    end endgenerate
    assign mdu_issue_valid = (|mdu_select);
    // Issue acceptance is independent from completion/CDB backpressure.  The
    // previous wiring reused alu_exec_ready for both directions, creating a
    // combinational loop through the reservation station's issue_valid path.
    assign mdu_completion_ready = producer_ready[MDU_SOURCE];
    assign lsq_load_complete_ready = producer_ready[LSQ_SOURCE];

    assign rob_completion_valid = completion_valid_r;
    assign rob_completion_tag = completion_tag_r;
    assign rob_completion_value = completion_value_r;
    assign rob_completion_done = completion_done_r;
    assign rob_completion_error = completion_error_r;
    assign rob_completion_store_addr = completion_store_addr_r;
    assign rob_completion_store_mask = completion_store_mask_r;
    assign rob_completion_store_data = completion_store_data_r;

    // The ROB owns the physical mappings of in-flight instructions.  Recovery
    // restores the branch RAT checkpoint, keeps the branch's own destination,
    // and returns only destinations allocated by the killed younger suffix.
    wire [CHECK_RAT_WIDTH-1:0] parallel_recovery_rat;
    generate if (RAT_RECOVERY_IMPL != 0 && CHECKPOINT_IMPL != 0) begin : g_parallel_rat_recovery
        rv32_rat_recovery #(.ROB_ENTRIES(ROB_ENTRIES), .PAW(PAW), .IMPL(2),
            .SUFFIX_KEEPS_BRANCH_MAPPING(RAT_SUFFIX_BRANCH_MAPPING)) rat_recovery (
            .rat_i(rat_state), .head_i(rob_head_views[0 +: ROB_SLOT_WIDTH]),
            .branch_slot_i(recovery_tag_views[TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
            .occupancy_i(rob_occupancy), .valid_i(rob_entry_valid),
            .rd_we_i(rob_entry_rd_we), .rd_i(rob_entry_rd), .old_phys_i(rob_entry_old_phys),
            .branch_rd_we_i(rob_recovery_rd_we), .branch_rd_i(rob_recovery_rd),
            .branch_new_phys_i(rob_recovery_new_phys), .restore_o(parallel_recovery_rat)
        );
    end else begin : g_no_parallel_rat_recovery
        assign parallel_recovery_rat = {CHECK_RAT_WIDTH{1'b0}};
    end endgenerate
    always @* begin
        recovery_rat_state = (CHECKPOINT_IMPL == 0) ?
            rob_checkpoint_restore[CHECK_RAT_WIDTH-1:0] :
            ((RAT_RECOVERY_IMPL != 0) ? parallel_recovery_rat : rat_state);
        recovery_rat_branch_age = recovery_tag_views[TAG_WIDTH+3 +: ROB_SLOT_WIDTH] - rob_head_views[0 +: ROB_SLOT_WIDTH];
        if (CHECKPOINT_IMPL != 0 && RAT_RECOVERY_IMPL == 0) begin
            // Undo the killed suffix youngest-to-oldest.  Each old-physical
            // link restores the mapping that existed immediately before that
            // instruction, so repeated writes to one architectural register
            // collapse correctly without a full RAT snapshot per ROB entry.
            for (recovery_rat_age = ROB_ENTRIES - 1; recovery_rat_age >= 0;
                 recovery_rat_age = recovery_rat_age - 1) begin
                recovery_rat_slot = rob_head_views[0 +: ROB_SLOT_WIDTH] + recovery_rat_age;
                if (recovery_rat_slot >= ROB_ENTRIES)
                    recovery_rat_slot = recovery_rat_slot - ROB_ENTRIES;
                if ((recovery_rat_age > recovery_rat_branch_age) &&
                    (recovery_rat_age < rob_occupancy) &&
                    rob_entry_valid[recovery_rat_slot] &&
                    rob_entry_rd_we[recovery_rat_slot] &&
                    (rob_entry_rd[recovery_rat_slot*5 +: 5] != 0))
                    recovery_rat_state[
                        rob_entry_rd[recovery_rat_slot*5 +: 5]*PAW +: PAW] =
                        rob_entry_old_phys[recovery_rat_slot*PAW +: PAW];
            end
        end
        if ((CHECKPOINT_IMPL == 0 || RAT_RECOVERY_IMPL == 0) &&
            rob_recovery_rd_we && (rob_recovery_rd != 0))
            recovery_rat_state[(rob_recovery_rd*PAW) +: PAW] = rob_recovery_new_phys;
        recovery_free_bitmap = free_bitmap_state | recovery_descriptor_reclaim;
        recovery_free_bitmap[0] = 1'b0;
        recovery_free_count = free_count + recovery_descriptor_reclaim_count;
    end

    // External flushes clear the station.  A branch recovery clears only
    // entries younger than the resolving branch; older unresolved work still
    // belongs to the retained ROB prefix and must remain executable.
    always @* begin
        recovery_rs_index = 0;
        rs_preview_kill_mask = {RS_ENTRIES{1'b0}};
        recovery_rs_rob_slot = 0;
        recovery_rs_branch_slot = recovery_tag_views[2*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
        recovery_rs_age = 0;
        recovery_rs_branch_age = recovery_rs_branch_slot - rob_head_views[ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
        if (flush_i) begin
            rs_preview_kill_mask = {RS_ENTRIES{1'b1}};
        end else if (rob_recovery_preview) begin
            for (recovery_rs_index = 0; recovery_rs_index < RS_ENTRIES; recovery_rs_index = recovery_rs_index + 1) begin
                recovery_rs_rob_slot = rs_entry_rob_tag[(recovery_rs_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                recovery_rs_age = recovery_rs_rob_slot - rob_head_views[ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                if (rs_entry_valid[recovery_rs_index] &&
                    (!rs_entry_rob_tag[recovery_rs_index*TAG_WIDTH] ||
                     (recovery_rs_age > recovery_rs_branch_age) ||
                     (recovery_rs_age >= rob_occupancy)))
                    rs_preview_kill_mask[recovery_rs_index] = 1'b1;
            end
        end
    end

    always @* begin
        rs_flush_kill_mask = flush_i ? {RS_ENTRIES{1'b1}} : recovery_descriptor_rs_kill;
    end

    // Completions may be queued out of program order.  Recovery invalidates
    // only entries younger than the resolving branch so retained work still
    // reaches the ROB while reclaimed physical registers cannot be poisoned
    // by wrong-path writeback.
    always @* begin
        recovery_completion_index = 0;
        completion_kill_mask = {COMPLETION_DEPTH{1'b0}};
        recovery_completion_rob_slot = 0;
        recovery_completion_age = 0;
        recovery_completion_branch_age = recovery_tag_views[3*TAG_WIDTH+3 +: ROB_SLOT_WIDTH] - recovery_head_views[2*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
        if (recovery_domains[3]) begin
            for (recovery_completion_index = 0; recovery_completion_index < COMPLETION_DEPTH;
                 recovery_completion_index = recovery_completion_index + 1) begin
                recovery_completion_rob_slot =
                    completion_entry_tag[(recovery_completion_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                recovery_completion_age = recovery_completion_rob_slot - recovery_head_views[2*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                if (completion_entry_valid[recovery_completion_index] &&
                    (!completion_entry_tag[recovery_completion_index*TAG_WIDTH] ||
                     (recovery_completion_age > recovery_completion_branch_age) ||
                     (recovery_completion_age >= recovery_descriptor_occupancy)))
                    completion_kill_mask[recovery_completion_index] = 1'b1;
            end
        end
    end

    // Rename and PRF form the operand/producer boundary.
    always @* begin
        rs_src1_tag = {BE_WIDTH*TAG_WIDTH{1'b0}};
        rs_src2_tag = {BE_WIDTH*TAG_WIDTH{1'b0}};
        rs_src1_ready = {BE_WIDTH{1'b0}};
        rs_src2_ready = {BE_WIDTH{1'b0}};
        rs_src1_value = {BE_WIDTH*32{1'b0}};
        rs_src2_value = {BE_WIDTH*32{1'b0}};
        for (source_lane = 0; source_lane < BE_WIDTH; source_lane = source_lane + 1) begin
            rs_src1_value[source_lane*32 +: 32] =
                prf_read_data[(2*source_lane)*32 +: 32];
            rs_src2_value[source_lane*32 +: 32] =
                prf_read_data[(2*source_lane+1)*32 +: 32];
            if (d_src1_phys[source_lane*PAW +: PAW] < PHYS_REGS)
                if (PHYS_TAG_IMPL == 0)
                    rs_src1_tag[source_lane*TAG_WIDTH +: TAG_WIDTH] =
                        tag_read_values[(2*source_lane+0)*TAG_WIDTH +: TAG_WIDTH];
            if (d_src2_phys[source_lane*PAW +: PAW] < PHYS_REGS)
                if (PHYS_TAG_IMPL == 0)
                    rs_src2_tag[source_lane*TAG_WIDTH +: TAG_WIDTH] =
                        tag_read_values[(2*source_lane+1)*TAG_WIDTH +: TAG_WIDTH];
            if (PHYS_TAG_IMPL != 0) begin
                for (source_rob_slot = 0; source_rob_slot < ROB_ENTRIES;
                     source_rob_slot = source_rob_slot + 1) begin
                    if (rob_entry_valid[source_rob_slot] &&
                        (rob_entry_new_phys[source_rob_slot*PAW +: PAW] ==
                         d_src1_phys[source_lane*PAW +: PAW]))
                        rs_src1_tag[source_lane*TAG_WIDTH +: TAG_WIDTH] =
                            {rob_entry_generation[source_rob_slot*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH],
                             source_rob_slot[ROB_SLOT_WIDTH-1:0], 2'b00, 1'b1};
                    if (rob_entry_valid[source_rob_slot] &&
                        (rob_entry_new_phys[source_rob_slot*PAW +: PAW] ==
                         d_src2_phys[source_lane*PAW +: PAW]))
                        rs_src2_tag[source_lane*TAG_WIDTH +: TAG_WIDTH] =
                            {rob_entry_generation[source_rob_slot*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH],
                             source_rob_slot[ROB_SLOT_WIDTH-1:0], 2'b00, 1'b1};
                end
            end
            rs_src1_ready[source_lane] =
                (d_src1_phys[source_lane*PAW +: PAW] == 0) ||
                prf_read_ready[2*source_lane];
            rs_src2_ready[source_lane] =
                (d_src2_phys[source_lane*PAW +: PAW] == 0) ||
                prf_read_ready[2*source_lane+1];
            // Free physical registers can still look ready until allocation's
            // clock edge. Explicitly link later lanes to earlier producers.
            if(DISPATCH_PIPELINE==0) for (dependency_lane = 0; dependency_lane < BE_WIDTH; dependency_lane = dependency_lane + 1) begin
                if ((dependency_lane < source_lane) && rename_valid[dependency_lane] &&
                    rename_rd_we[dependency_lane] &&
                    (rename_rs1_phys[source_lane*PAW +: PAW] ==
                     rename_new_phys[dependency_lane*PAW +: PAW])) begin
                    rs_src1_tag[source_lane*TAG_WIDTH +: TAG_WIDTH] =
                        rob_alloc_tag[dependency_lane*TAG_WIDTH +: TAG_WIDTH];
                    rs_src1_ready[source_lane] = 1'b0;
                end
                if ((dependency_lane < source_lane) && rename_valid[dependency_lane] &&
                    rename_rd_we[dependency_lane] &&
                    (rename_rs2_phys[source_lane*PAW +: PAW] ==
                     rename_new_phys[dependency_lane*PAW +: PAW])) begin
                    rs_src2_tag[source_lane*TAG_WIDTH +: TAG_WIDTH] =
                        rob_alloc_tag[dependency_lane*TAG_WIDTH +: TAG_WIDTH];
                    rs_src2_ready[source_lane] = 1'b0;
                end
            end
        end
    end

    rv32_rename_unit #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .RAT_READ_BYPASS(RAT_READ_BYPASS), .REGISTERED_FREE_POOL(1), .RETAIN_FREE_POOL_ON_RESTORE(RENAME_RETAIN_FREE_POOL)) rename (
        .clk_i(clk_i), .reset_i(reset_i), .rename_ready_i(!halted_o && !flush_i && !branch_busy_domains[1] && dispatch_packet_ready),
        .decoded_valid_i(dec_valid), .decoded_rd_we_i(dec_rd_we), .decoded_rs1_used_i(dec_rs1_used), .decoded_rs2_used_i(dec_rs2_used),
        .decoded_rs_need_i(dec_rs_need), .decoded_lsq_need_i(dec_lsq_need), .decoded_rd_i(dec_rd), .decoded_rs1_i(dec_rs1), .decoded_rs2_i(dec_rs2),
        .rob_free_count_i({{(16-CREDIT_WIDTH){1'b0}},rob_credit}),
        .rs_free_count_i((DISPATCH_ELASTIC!=0)?16'hffff:{{(16-CREDIT_WIDTH){1'b0}},rs_credit}),
        .lsq_free_count_i((DISPATCH_ELASTIC!=0)?16'hffff:{{(16-CREDIT_WIDTH){1'b0}},lsq_credit}),
        .rename_valid_o(rename_valid), .rename_rd_we_o(rename_rd_we), .rename_rd_o(rename_rd), .rename_old_phys_o(rename_old_phys), .rename_new_phys_o(rename_new_phys),
        .rename_rs1_phys_o(rename_rs1_phys), .rename_rs2_phys_o(rename_rs2_phys), .rename_count_o(rename_count), .rat_state_o(rat_state), .rrat_state_o(rrat_state),
        .free_bitmap_state_o(free_bitmap_state), .free_count_o(free_count), .allocatable_count_o(phys_credit),
        .commit_valid_i((|rob_commit_valid) && commit_ready_i), .commit_rd_we_i(rob_commit_rd_we), .commit_rd_i(rob_commit_rd),
        .commit_old_phys_i(commit_old_phys), .commit_new_phys_i(commit_new_phys),
        .restore_valid_i(rob_checkpoint_restore_valid), .restore_rat_i(recovery_descriptor_rat),
        .restore_free_bitmap_i(recovery_free_bitmap), .restore_free_count_i(recovery_free_count)
    );

    localparam integer PARALLEL_STORE_ADDRESS=(STORE_ALLOC_EARLY_ADDRESS==2) &&
        (STORE_ALLOC_IMM12!=0) && (PRF_READ_MUX_IMPL!=0);
    wire [BE_WIDTH*12-1:0] prf_store_offsets;
    wire [BE_WIDTH*32-1:0] prf_store_address;
    wire [BE_WIDTH*3-1:0] prf_store_address_flags;
    generate for(genvar store_offset_lane=0;store_offset_lane<BE_WIDTH;store_offset_lane=store_offset_lane+1) begin:g_store_offset
        assign prf_store_offsets[store_offset_lane*12 +: 12]=d_imm[store_offset_lane*32 +: 12];
    end endgenerate
    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1), .STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS), .STORE_ADDRESS_FLAGS((FAST_STORE_ADDRESS_PREDECODE!=0) && FAST_STORE_COMPLETE_ACTIVE && PARALLEL_STORE_ADDRESS)) prf (
        .clk_i(clk_i), .reset_i(reset_i), .read_phys_i(prf_read_phys), .read_data_o(prf_read_data), .read_ready_o(prf_read_ready),
        .store_offset_i(prf_store_offsets), .store_address_o(prf_store_address), .store_address_flags_o(prf_store_address_flags),
        .alloc_phys_i(prf_alloc_phys), .alloc_valid_i(prf_alloc_valid), .write_phys_i(prf_write_phys), .write_data_i(prf_write_data), .write_valid_i(prf_write_valid)
    );

    // Build one RAT checkpoint per lane in program order. A branch in lane N
    // therefore preserves mappings created by older lanes in the same bundle.
    always @* begin
        checkpoint_rat_work = rat_state;
        rob_alloc_checkpoint = {BE_WIDTH*CHECKPOINT_WIDTH{1'b0}};
        rob_alloc_pc = trace_pc_i;
        rob_alloc_inst = trace_inst_i;
        rob_alloc_rd = trace_rd_i;
        rob_alloc_old_phys = rename_old_phys;
        rob_alloc_new_phys = rename_new_phys;
        rob_alloc_is_store = trace_is_store_i;
        rob_alloc_is_branch = trace_is_branch_i;
        rob_alloc_is_halt = trace_is_halt_i;
        rob_alloc_is_error = trace_is_error_i;
        for (checkpoint_lane = 0; checkpoint_lane < BE_WIDTH; checkpoint_lane = checkpoint_lane + 1) begin
            if (rename_valid[checkpoint_lane] && rename_rd_we[checkpoint_lane])
                checkpoint_rat_work[rename_rd[checkpoint_lane*5 +: 5]*PAW +: PAW] =
                    rename_new_phys[checkpoint_lane*PAW +: PAW];
            rob_alloc_checkpoint[checkpoint_lane*CHECKPOINT_WIDTH +: CHECKPOINT_WIDTH] =
                checkpoint_rat_work;
        end
    end

    rv32_rob #(.BE_WIDTH(BE_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .PHYS_REGS(PHYS_REGS), .PHYS_ADDR_WIDTH(PAW), .GENERATION_WIDTH(ROB_GENERATION_WIDTH), .TAG_WIDTH(TAG_WIDTH), .CHECKPOINT_WIDTH(CHECKPOINT_WIDTH), .CHECKPOINT_IMPL(CHECKPOINT_IMPL), .ASAP7_FANOUT_BUFFERS(ASAP7_FANOUT_BUFFERS), .ROB_CONTROL_REGISTER_BANKS(ROB_CONTROL_REGISTER_BANKS), .STAGED_RECOVERY(RECOVERY_DIRECT_ACTIVE==0), .COMMIT_BANKED_READ(ROB_COMMIT_BANKED_READ), .ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .RECLAIM_UNIQUE_DESTINATIONS(ROB_UNIQUE_RECLAIM_COUNT), .FAST_STORE_COMPLETE(FAST_STORE_COMPLETE_ACTIVE), .FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .MMIO_PREDECODE(ROB_MMIO_PREDECODE), .LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD), .LEGACY_HALT_PAYLOAD(ROB_LEGACY_HALT_PAYLOAD), .RETURN_VALUE_ENABLE(ROB_RETURN_VALUE_ENABLE), .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE)) rob (
        .clk_i(clk_i), .reset_i(reset_i), .alloc_valid_i(rob_alloc_valid), .alloc_pc_i(rob_alloc_pc), .alloc_inst_i(rob_alloc_inst), .alloc_rd_i(rob_alloc_rd),
        .alloc_rd_we_i(rename_rd_we), .alloc_old_phys_i(rob_alloc_old_phys), .alloc_new_phys_i(rob_alloc_new_phys), .alloc_is_store_i(rob_alloc_is_store),
        .alloc_is_branch_i(rob_alloc_is_branch), .alloc_is_halt_i(rob_alloc_is_halt), .alloc_is_error_i(rob_alloc_is_error), .alloc_checkpoint_i(rob_alloc_checkpoint),
        .alloc_ready_o(rob_alloc_ready), .alloc_fire_o(rob_alloc_fire), .alloc_tag_o(rob_alloc_tag), .alloc_count_o(rob_alloc_count),
        .fast_store_valid_i(rob_fast_store_publish_valid), .fast_store_tag_i(rob_fast_store_publish_tag),
        .completion_valid_i(rob_completion_valid), .completion_tag_i(rob_completion_tag), .completion_value_i(rob_completion_value), .completion_done_i(rob_completion_done), .completion_error_i(rob_completion_error),
        .completion_store_addr_i(rob_completion_store_addr), .completion_store_mask_i(rob_completion_store_mask), .completion_store_data_i(rob_completion_store_data),
        .commit_ready_i(commit_ready_i), .commit_valid_o(rob_commit_valid), .commit_rd_we_o(rob_commit_rd_we), .commit_rd_o(rob_commit_rd), .commit_pc_o(rob_commit_pc), .commit_inst_o(rob_commit_inst), .commit_value_o(rob_commit_value), .commit_is_store_o(rob_commit_is_store),
        .commit_store_addr_o(rob_commit_store_addr), .commit_store_mask_o(rob_commit_store_mask), .commit_store_data_o(rob_commit_store_data), .commit_tag_o(rob_commit_tag), .commit_old_phys_o(commit_old_phys), .commit_new_phys_o(commit_new_phys),
        .store_commit_valid_o(rob_store_commit_valid), .store_commit_ready_i(rob_store_commit_ready), .store_commit_tag_o(rob_store_commit_tag), .store_commit_addr_o(rob_store_commit_addr), .store_commit_mask_o(rob_store_commit_mask), .store_commit_data_o(rob_store_commit_data), .store_ack_valid_i(rob_store_ack_valid), .store_ack_tag_i(rob_store_ack_tag), .store_ack_error_i(lsq_store_ack_error),
        .recovery_valid_i({ {(BE_WIDTH-1){1'b0}}, branch_pending }), .recovery_tag_i({ {(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, recovery_tag_views[0 +: TAG_WIDTH] }), .recovery_pc_i({ {(BE_WIDTH-1)*32{1'b0}}, branch_pending_pc }),
        .recovery_apply_i(recovery_descriptor_valid), .recovery_hold_i(branch_busy_domains[3]),
        .recovery_preview_valid_o(rob_recovery_preview), .recovery_accept_o(rob_recovery_accept_source), .redirect_valid_o(rob_redirect_valid), .redirect_pc_o(rob_redirect_pc), .redirect_epoch_o(rob_redirect_epoch), .checkpoint_restore_valid_o(rob_checkpoint_restore_valid), .checkpoint_restore_o(rob_checkpoint_restore), .recovery_rd_we_o(rob_recovery_rd_we), .recovery_rd_o(rob_recovery_rd), .recovery_new_phys_o(rob_recovery_new_phys), .recovery_reclaim_bitmap_o(rob_recovery_reclaim_bitmap), .recovery_reclaim_count_o(rob_recovery_reclaim_count), .halted_o(halted_o), .error_o(error_o), .return_value_o(return_value_o), .head_o(rob_head_source), .head_domains_o(rob_registered_head_views), .tail_o(rob_tail), .occupancy_o(rob_occupancy), .entry_valid_o(rob_entry_valid), .entry_generation_o(rob_entry_generation), .entry_new_phys_o(rob_entry_new_phys), .entry_rd_we_o(rob_entry_rd_we), .entry_rd_o(rob_entry_rd), .entry_old_phys_o(rob_entry_old_phys)
    );


    // The new edge uses the direct RS contract and selective execution
    // cancellation together. Other pipeline/recovery modes retain old gating.
    localparam integer RECOVERY_APPLY_ISSUE_ACTIVE=(RECOVERY_APPLY_OLDER_ISSUE!=0) &&
        (LOCAL_EXEC_RECOVERY!=0) && (ISSUE_PIPELINE==0);

    // Evaluate the same preview/apply predicates from saved RS row tags.
    // Ready/rank selection then carries one qualified bit beside its payload;
    // a late wakeup cannot enter a post-selection ROB generation read.
    genvar qualification_row;
    generate if(RS_ROW_QUALIFICATION_ACTIVE!=0) begin:g_rs_row_qualification
        wire [RS_ENTRIES*EXEC_RECOVERY_WIDTH-1:0] packet_views;
        rv32_frequency_control_tree #(.WIDTH(EXEC_RECOVERY_WIDTH),.LEAVES(RS_ENTRIES)) packet_tree (
            .signal_i({recovery_domains[6],recovery_descriptor_occupancy,
                recovery_descriptor_head,execution_branch_age}),.views_o(packet_views));
        for(qualification_row=0;qualification_row<RS_ENTRIES;qualification_row=qualification_row+1) begin:g_row
            wire [TAG_WIDTH-1:0] row_tag=rs_entry_rob_tag[qualification_row*TAG_WIDTH +: TAG_WIDTH];
            wire [ROB_SLOT_WIDTH-1:0] row_age=row_tag[3 +: ROB_SLOT_WIDTH]-rob_head;
            wire [ROB_SLOT_WIDTH-1:0] pending_age=recovery_tag_views[3 +: ROB_SLOT_WIDTH]-rob_head;
            wire older_preview=(RECOVERY_PREVIEW_OLDER_ISSUE!=0) && branch_pending &&
                rob_recovery_preview && !recovery_descriptor_valid && !reset_i && !flush_i &&
                rs_entry_valid[qualification_row] && row_tag[0] &&
                row_age<pending_age && row_age<rob_occupancy;
            wire older_apply;
            if(RECOVERY_APPLY_ISSUE_ACTIVE!=0) begin:g_apply
                wire row_live_match;
                wire row_cancel;
                if(RS_ROW_LIVE_MEMBERSHIP_ACTIVE!=0) begin:g_direct_membership
                    localparam integer IDENTITY_WIDTH=ROB_SLOT_WIDTH+ROB_GENERATION_WIDTH;
                    localparam integer MEMBERSHIP_LEAVES=1<<ROB_SLOT_WIDTH;
                    localparam integer QUERY_DOMAINS=(ROB_ENTRIES+3)/4;
                    wire [QUERY_DOMAINS*IDENTITY_WIDTH-1:0] query_views;
                    wire live_tree [1:2*MEMBERSHIP_LEAVES-1];
                    rv32_frequency_control_tree #(.WIDTH(IDENTITY_WIDTH),.LEAVES(QUERY_DOMAINS)) query_tree (
                        .signal_i(row_tag[3 +: IDENTITY_WIDTH]),.views_o(query_views));
                    for(genvar member=0;member<MEMBERSHIP_LEAVES;member=member+1) begin:g_member
                        if(member<ROB_ENTRIES) begin:g_present
                            assign live_tree[MEMBERSHIP_LEAVES+member]=rob_entry_valid[member] &&
                                query_views[(member/4)*IDENTITY_WIDTH +: IDENTITY_WIDTH]==
                                {rob_entry_generation[member*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH],
                                 member[ROB_SLOT_WIDTH-1:0]};
                        end else begin:g_padding
                            assign live_tree[MEMBERSHIP_LEAVES+member]=1'b0;
                        end
                    end
                    for(genvar member_node=1;member_node<MEMBERSHIP_LEAVES;member_node=member_node+1) begin:g_or
                        assign live_tree[member_node]=live_tree[2*member_node] || live_tree[2*member_node+1];
                    end
                    assign row_live_match=row_tag[0] && live_tree[1];
                end else begin:g_original_live_read
                    wire [ROB_LIVE_WIDTH-1:0] row_live;
                    rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                        .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                        .rows_i(rob_live_rows),.index_i(row_tag[3 +: ROB_SLOT_WIDTH]),.value_o(row_live));
                    assign row_live_match=row_tag[0] && row_live[ROB_GENERATION_WIDTH] &&
                        row_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==row_live[0 +: ROB_GENERATION_WIDTH];
                end
                assign rs_entry_current_live_match[qualification_row]=row_live_match;
                assign rs_entry_issue_cancel[qualification_row]=row_cancel;
                rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
                    .ENABLED(1),.KILL_BRANCH(1)) age_guard (
                    .packet_i(packet_views[qualification_row*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
                    .active_i(rs_entry_valid[qualification_row]),.tag_i(row_tag),.cancel_o(row_cancel));
                assign older_apply=branch_pending && recovery_descriptor_valid && recovery_domains[4] &&
                    !reset_i && !flush_i && rs_entry_valid[qualification_row] &&
                    row_live_match && !row_cancel;
            end else begin:g_no_apply
                assign older_apply=1'b0;
                assign rs_entry_current_live_match[qualification_row]=1'b0;
                assign rs_entry_issue_cancel[qualification_row]=1'b0;
            end
            assign rs_entry_recovery_qualified[qualification_row]=older_preview || older_apply;
        end
    end else begin:g_no_row_qualification
        assign rs_entry_current_live_match={RS_ENTRIES{1'b0}};
        assign rs_entry_issue_cancel={RS_ENTRIES{1'b0}};
        assign rs_entry_recovery_qualified={RS_ENTRIES{1'b0}};
    end endgenerate

    // Registered RS selection / execution boundary.
    localparam integer ISSUE_PAYLOAD_WIDTH = `RV32IM_OP_WIDTH + 32 + TAG_WIDTH + PAW + 32 + 32 + 32 + RS_METADATA_WIDTH + ((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES));
    wire [BE_WIDTH-1:0] raw_rs_issue_valid, raw_rs_issue_ready;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] raw_rs_issue_op;
    wire [BE_WIDTH*32-1:0] raw_rs_issue_pc;
    wire [BE_WIDTH*TAG_WIDTH-1:0] raw_rs_issue_tag;
    wire [BE_WIDTH*PAW-1:0] raw_rs_issue_phys;
    wire [BE_WIDTH*32-1:0] raw_rs_issue_src1;
    wire [BE_WIDTH*32-1:0] raw_rs_issue_src2;
    wire [BE_WIDTH*32-1:0] raw_rs_issue_store;
    wire [BE_WIDTH*RS_METADATA_WIDTH-1:0] raw_rs_issue_metadata;
    wire [BE_WIDTH*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))-1:0] raw_rs_issue_slot;
    rv32_reservation_station #(.BE_WIDTH(BE_WIDTH), .ENTRIES(RS_ENTRIES), .TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW), .WAKE_WIDTH(RS_WAKE_WIDTH), .STORE_DATA_WIDTH(32), .METADATA_WIDTH(RS_METADATA_WIDTH), .SOURCE_TAG_WIDTH(RS_SOURCE_TAG_WIDTH), .WAKE_UNIQUE_OWNER(RS_DIRECT_WAKE), .WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL), .REGISTERED_BASE_PROBE(STORE_RS_LINKS), .AGE_ORDER_MATRIX(2), .LOCAL_PAYLOAD_ROWS(1), .ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE), .AGE_WIDTH(RS_AGE_WIDTH), .RECOVERY_ISSUE_RELEASE(RECOVERY_APPLY_ISSUE_ACTIVE), .ISSUE_RECOVERY_QUALIFICATION(RS_ROW_QUALIFICATION_ACTIVE), .ISSUE_RECOVERY_CANCEL(RS_ISSUE_CANCEL_PREDECODE_ACTIVE)) rs (
        .entry_issue_cancel_i(rs_entry_issue_cancel), .issue_cancel_o(raw_rs_issue_cancel),
        .entry_recovery_qualified_i(rs_entry_recovery_qualified),
        .issue_recovery_qualified_o(raw_rs_issue_recovery_qualified),
        .alloc_metadata_i(rs_alloc_metadata), .issue_metadata_o(raw_rs_issue_metadata), .entry_metadata_o(rs_entry_metadata),
        .entry_base_ready_o(rs_entry_base_ready), .entry_base_value_o(rs_entry_base_value),
        .alloc_slot_o(rs_alloc_slot),.entry_release_o(rs_entry_release),
        .clk_i(clk_i), .reset_i(reset_i), .alloc_valid_i(rs_alloc_valid), .alloc_op_i(d_op), .alloc_pc_i(d_pc), .alloc_rob_tag_i(d_tag), .alloc_target_live_i(d_valid), .alloc_phys_rd_i(d_new_phys),
        .alloc_src1_value_i(rs_src1_value), .alloc_src1_tag_i(rs_source1_identity), .alloc_src1_ready_i(rs_src1_ready), .alloc_src2_value_i(rs_src2_value), .alloc_src2_tag_i(rs_source2_identity), .alloc_src2_ready_i(rs_src2_ready), .alloc_store_data_i(d_store_data), .alloc_ready_o(rs_alloc_ready), .alloc_fire_o(rs_alloc_fire), .alloc_count_o(rs_alloc_count),
        .wake_valid_i(rs_wake_valid), .wake_tag_i(rs_wake_tag), .wake_value_i(rs_wake_value), .issue_ready_i(raw_rs_issue_ready), .issue_valid_o(raw_rs_issue_valid), .issue_op_o(raw_rs_issue_op), .issue_pc_o(raw_rs_issue_pc), .issue_rob_tag_o(raw_rs_issue_tag), .issue_phys_rd_o(raw_rs_issue_phys), .issue_src1_value_o(raw_rs_issue_src1), .issue_src2_value_o(raw_rs_issue_src2), .issue_store_data_o(raw_rs_issue_store), .issue_slot_o(raw_rs_issue_slot), .flush_valid_i(flush_i || recovery_domains[4]), .flush_kill_mask_i(rs_flush_kill_mask), .entry_valid_o(rs_entry_valid), .entry_rob_tag_o(rs_entry_rob_tag), .occupancy_o(rs_occupancy)
    );

    genvar pipe_lane;
    generate for (pipe_lane=0; pipe_lane<BE_WIDTH; pipe_lane=pipe_lane+1) begin : g_issue_pipeline
        if (ISSUE_PIPELINE != 0) begin : g_registered
            wire [ISSUE_PAYLOAD_WIDTH-1:0] in_payload, out_payload;
            assign in_payload = {raw_rs_issue_op[pipe_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH], raw_rs_issue_pc[pipe_lane*32 +: 32], raw_rs_issue_tag[pipe_lane*TAG_WIDTH +: TAG_WIDTH], raw_rs_issue_phys[pipe_lane*PAW +: PAW], raw_rs_issue_src1[pipe_lane*32 +: 32], raw_rs_issue_src2[pipe_lane*32 +: 32], raw_rs_issue_store[pipe_lane*32 +: 32], raw_rs_issue_metadata[pipe_lane*RS_METADATA_WIDTH +: RS_METADATA_WIDTH], raw_rs_issue_slot[pipe_lane*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES)) +: ((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))]};
            assign {rs_issue_op[pipe_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH], rs_issue_pc[pipe_lane*32 +: 32], rs_issue_tag[pipe_lane*TAG_WIDTH +: TAG_WIDTH], rs_issue_phys[pipe_lane*PAW +: PAW], rs_issue_src1[pipe_lane*32 +: 32], rs_issue_src2[pipe_lane*32 +: 32], rs_issue_store[pipe_lane*32 +: 32], rs_issue_metadata[pipe_lane*RS_METADATA_WIDTH +: RS_METADATA_WIDTH], rs_issue_slot[pipe_lane*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES)) +: ((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))]} = out_payload;
            wire [`RV32IM_OP_WIDTH-1:0] raw_op = raw_rs_issue_op[pipe_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];
            wire raw_mdu = (raw_op == `RV32IM_OP_MUL) || (raw_op == `RV32IM_OP_MULH) || (raw_op == `RV32IM_OP_MULHSU) || (raw_op == `RV32IM_OP_MULHU) || (raw_op == `RV32IM_OP_DIV) || (raw_op == `RV32IM_OP_DIVU) || (raw_op == `RV32IM_OP_REM) || (raw_op == `RV32IM_OP_REMU);
            rv32_issue_pipeline_slot #(.PAYLOAD_WIDTH(ISSUE_PAYLOAD_WIDTH),
                .TAG_WIDTH(TAG_WIDTH), .ROB_ENTRIES(ROB_ENTRIES)) pipe (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i),
                .recovery_i(recovery_domains[4]), .recovery_tag_i(recovery_tag_views[4*TAG_WIDTH +: TAG_WIDTH]),
                .head_i(recovery_head_views[5*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]),
                .valid_i(raw_rs_issue_valid[pipe_lane]),
                .eligible_i((pipe_lane < INT_ISSUE_WIDTH) || raw_mdu),
                .ready_o(raw_rs_issue_ready[pipe_lane]), .data_i(in_payload),
                .tag_i(raw_rs_issue_tag[pipe_lane*TAG_WIDTH +: TAG_WIDTH]),
                .valid_o(rs_issue_valid[pipe_lane]), .ready_i(rs_issue_ready[pipe_lane]),
                .data_o(out_payload));
        end else begin : g_direct
            assign rs_issue_valid[pipe_lane] = raw_rs_issue_valid[pipe_lane];
            assign raw_rs_issue_ready[pipe_lane] = rs_issue_ready[pipe_lane];
            assign rs_issue_op[pipe_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] = raw_rs_issue_op[pipe_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];
            assign rs_issue_pc[pipe_lane*32 +: 32] = raw_rs_issue_pc[pipe_lane*32 +: 32];
            assign rs_issue_tag[pipe_lane*TAG_WIDTH +: TAG_WIDTH] = raw_rs_issue_tag[pipe_lane*TAG_WIDTH +: TAG_WIDTH];
            assign rs_issue_phys[pipe_lane*PAW +: PAW] = raw_rs_issue_phys[pipe_lane*PAW +: PAW];
            assign rs_issue_src1[pipe_lane*32 +: 32] = raw_rs_issue_src1[pipe_lane*32 +: 32];
            assign rs_issue_src2[pipe_lane*32 +: 32] = raw_rs_issue_src2[pipe_lane*32 +: 32];
            assign rs_issue_store[pipe_lane*32 +: 32] = raw_rs_issue_store[pipe_lane*32 +: 32];
            assign rs_issue_metadata[pipe_lane*RS_METADATA_WIDTH +: RS_METADATA_WIDTH] = raw_rs_issue_metadata[pipe_lane*RS_METADATA_WIDTH +: RS_METADATA_WIDTH];
            assign rs_issue_slot[pipe_lane*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES)) +: ((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))] = raw_rs_issue_slot[pipe_lane*((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES)) +: ((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))];
        end
    end endgenerate

    genvar alu_lane;
    generate
        for (alu_lane = 0; alu_lane < BE_WIDTH; alu_lane = alu_lane + 1) begin : g_alu
            rv32i_alu #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW), .SHIFT_IMPL(SHIFT_IMPL), .SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL), .COMPACT_PRED_TARGET(COMPACT_PRED_TARGET), .FORWARD_METADATA(RS_ISSUE_METADATA), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY), .RECOVERY_OLDER_ISSUE(RECOVERY_APPLY_ISSUE_ACTIVE), .ISSUE_RECOVERY_PREDECODE(RS_ISSUE_CANCEL_PREDECODE_ACTIVE)) alu (
                .exec_source_pc_o(alu_exec_source_pc[alu_lane*32 +: 32]),
                .exec_pred_taken_o(alu_exec_pred_taken[alu_lane]),
                .exec_pred_target_o(alu_exec_pred_target[alu_lane*32 +: 32]),
                .exec_pred_kind_o(alu_exec_pred_kind[alu_lane*2 +: 2]),
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(alu_flush_r[alu_lane]),
                .recovery_packet_i(execution_recovery_views[alu_lane*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
                .issue_valid_i(rs_issue_allowed[alu_lane] &&
                               (alu_lane < INT_ISSUE_WIDTH) &&
                               rs_issue_valid[alu_lane] &&
                               !rs_issue_is_mdu[alu_lane]),
                .issue_cancel_i(raw_rs_issue_cancel[alu_lane]),
                .issue_ready_o(alu_issue_ready[alu_lane]),
                .issue_op_i(rs_issue_op[alu_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH]),
                .issue_pc_i(rs_issue_pc[alu_lane*32 +: 32]),
                .issue_imm_i(rs_issue_imm[alu_lane*32 +: 32]),
                .issue_src1_value_i(rs_issue_src1[alu_lane*32 +: 32]),
                .issue_src2_value_i(rs_issue_src2[alu_lane*32 +: 32]),
                .issue_store_data_i(rs_issue_store[alu_lane*32 +: 32]),
                .issue_phys_rd_i(rs_issue_phys[alu_lane*PAW +: PAW]),
                .issue_rob_tag_i(rs_issue_tag[alu_lane*TAG_WIDTH +: TAG_WIDTH]),
                .issue_epoch_i(4'b0), .issue_target_live_i(rs_issue_valid[alu_lane]),
                .issue_pred_taken_i(rs_issue_pred_taken[alu_lane]),
                .issue_pred_target_i(rs_issue_pred_target[alu_lane*32 +: 32]),
                .issue_pred_kind_i(rs_issue_pred_kind[alu_lane*2 +: 2]),
                .issue_mem_size_i(rs_issue_mem_size[alu_lane*2 +: 2]),
                .issue_mem_unsigned_i(rs_issue_mem_unsigned[alu_lane]),
                .exec_valid_o(alu_exec_valid[alu_lane]), .exec_saved_valid_o(alu_exec_saved_valid[alu_lane]),
                .exec_ready_i(alu_exec_ready[alu_lane]),
                .exec_value_o(alu_exec_value[alu_lane*32 +: 32]),
                .exec_phys_rd_o(alu_exec_phys[alu_lane*PAW +: PAW]),
                .exec_rob_tag_o(alu_exec_tag[alu_lane*TAG_WIDTH +: TAG_WIDTH]),
                .exec_epoch_o(), .exec_rd_we_o(alu_exec_rd_we[alu_lane]),
                .exec_is_branch_o(alu_exec_is_branch[alu_lane]),
                .exec_branch_taken_o(alu_exec_branch_taken[alu_lane]),
                .exec_branch_target_o(alu_exec_branch_target[alu_lane*32 +: 32]),
                .exec_redirect_valid_o(alu_exec_redirect_valid[alu_lane]),
                .exec_redirect_pc_o(alu_exec_redirect_pc[alu_lane*32 +: 32]),
                .exec_is_memory_o(alu_exec_is_memory[alu_lane]),
                .exec_is_load_o(alu_exec_is_load[alu_lane]),
                .exec_is_store_o(alu_exec_is_store[alu_lane]),
                .exec_mem_addr_o(alu_exec_mem_addr[alu_lane*32 +: 32]),
                .exec_mem_size_o(alu_exec_mem_size[alu_lane*2 +: 2]),
                .exec_mem_unsigned_o(alu_exec_mem_unsigned[alu_lane]),
                .exec_store_data_o(alu_exec_store_data[alu_lane*32 +: 32]),
                .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}})
            );
        end
    endgenerate

    rv32m_mdu_reservation_station #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW), .MUL_IMPL(MUL_IMPL), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY), .RECOVERY_OLDER_ISSUE(RECOVERY_APPLY_ISSUE_ACTIVE), .ISSUE_RECOVERY_PREDECODE(RS_ISSUE_CANCEL_PREDECODE_ACTIVE)) mdu (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_packet_i(execution_recovery_views[BE_WIDTH*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]), .issue_valid_i(mdu_issue_valid), .issue_cancel_i(mdu_issue_cancel), .issue_op_i(mdu_issue_op), .issue_src1_i(mdu_issue_src1), .issue_src2_i(mdu_issue_src2), .issue_rob_tag_i(mdu_issue_tag), .issue_phys_rd_i(mdu_issue_phys), .issue_target_live_i(1'b1), .issue_ready_o(mdu_issue_ready), .completion_valid_o(mdu_completion_valid), .completion_ready_i(mdu_completion_ready), .completion_value_o(mdu_completion_value), .completion_rob_tag_o(mdu_completion_tag), .completion_phys_rd_o(mdu_completion_phys), .completion_rd_we_o(mdu_completion_rd_we), .busy_o(mdu_busy), .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}})
    );

    rv32_lsq #(.BE_WIDTH(BE_WIDTH), .LSQ_ENTRIES(LSQ_ENTRIES), .STORE_ADMISSION_BYPASS(LSQ_STORE_ADMISSION_BYPASS), .STORE_ADDRESS_PROBE(EARLY_STORE_ADDRESS == 2), .REQUEST_PIPELINE(1), .LOAD_ADDRESS_LOOKTHROUGH(EARLY_LOAD_ADDRESS>=3), .LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS), .LOAD_WAKE_BYPASS(RS_LOAD_RETURN_WAKE), .ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .SECOND_REPORT_RECLAIM(LSQ_SECOND_REPORT_RECLAIM), .EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS), .PICK_LOCAL_VALIDITY(LSQ_PICK_LOCAL_VALIDITY), .FORWARD_ONEHOT(LSQ_FORWARD_ONEHOT), .PICK_ONEHOT(LSQ_PICK_ONEHOT), .LOCAL_REPORT_CANCEL(LOCAL_EXEC_RECOVERY), .REPORT_ROB_PREDECODE(LSQ_ROB_QUERY_PREDECODE), .RESPONSE_QUERY_PREDECODE(LSQ_RESPONSE_QUERY_PREDECODE), .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .PHYS_ADDR_WIDTH(PAW)) lsq (
        .early_addr_valid_i(shared_store_addr_valid), .early_addr_tag_i(shared_store_addr_tag),
        .early_addr_i(shared_store_addr), .store_addr_pending_o(lsq_store_addr_pending),
        .store_addr_rob_tag_o(lsq_store_addr_rob_tag), .store_addr_lsq_tag_o(lsq_store_addr_lsq_tag),
        .head_o(lsq_head),
        .retire_valid_i(rob_commit_valid & {BE_WIDTH{commit_ready_i}}),
        .retire_rob_tag_i(rob_commit_tag),
.clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_valid_i(recovery_domains[5]), .recovery_tag_i(recovery_tag_views[5*TAG_WIDTH +: TAG_WIDTH]), .recovery_head_i(recovery_head_views[3*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]), .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1'b0}}, recovery_descriptor_occupancy}), .alloc_valid_i(lsq_alloc_valid), .alloc_ready_o(lsq_alloc_ready), .alloc_fire_o(lsq_alloc_fire), .alloc_count_o(lsq_alloc_count), .alloc_lsq_tag_o(lsq_alloc_tag), .alloc_is_load_i(d_is_load), .alloc_is_store_i(d_is_store), .alloc_rob_tag_i(d_tag), .alloc_phys_rd_i(d_new_phys), .alloc_size_i(d_mem_size), .alloc_unsigned_i(d_mem_unsigned), .alloc_addr_valid_i(lsq_alloc_addr_valid), .alloc_addr_i(lsq_alloc_addr), .alloc_data_valid_i(lsq_alloc_data_valid), .alloc_store_data_i(lsq_alloc_store_data), .alloc_store_mask_i({BE_WIDTH*4{1'b0}}), .addr_update_valid_i(lsq_addr_update_valid), .addr_update_tag_i(lsq_addr_update_tag), .addr_update_i(lsq_addr_update), .data_update_valid_i(lsq_data_update_valid), .data_update_tag_i(lsq_data_update_tag), .data_update_i(alu_exec_store_data), .data_mask_update_i({BE_WIDTH*4{1'b0}}), .wakeup_valid_i({BE_WIDTH{1'b0}}), .wakeup_tag_i({BE_WIDTH*TAG_WIDTH{1'b0}}), .wakeup_value_i({BE_WIDTH*32{1'b0}}), .store_commit_valid_i(rob_store_commit_valid), .store_commit_ready_o(rob_store_commit_ready), .store_commit_rob_tag_i(rob_store_commit_tag), .dcache_req_valid_o(dcache_req_valid_o), .dcache_req_ready_i(dcache_req_ready_i), .dcache_req_is_load_o(dcache_req_is_load_o), .dcache_req_is_store_o(dcache_req_is_store_o), .dcache_req_addr_o(dcache_req_addr_o), .dcache_req_size_o(dcache_req_size_o), .dcache_req_unsigned_o(dcache_req_unsigned_o), .dcache_req_mask_o(dcache_req_mask_o), .dcache_req_wdata_o(dcache_req_wdata_o), .dcache_req_rob_tag_o(dcache_req_rob_tag_o), .dcache_req_lsq_tag_o(dcache_req_lsq_tag_o), .dcache_resp_valid_i(dcache_resp_valid_i), .dcache_resp_ready_o(dcache_resp_ready_o), .dcache_resp_lsq_tag_i(dcache_resp_lsq_tag_i), .dcache_resp_addr_i(dcache_resp_addr_i), .dcache_resp_line_data_i(dcache_resp_line_data_i), .dcache_resp_word_data_i(dcache_resp_word_data_i), .dcache_resp_line_valid_i(dcache_resp_line_valid_i), .dcache_resp_error_i(dcache_resp_error_i), .load_return_wake_valid_o(lsq_return_wake_valid), .load_return_wake_rob_tag_o(lsq_return_wake_tag),
        .load_return_wake_phys_o(lsq_return_wake_phys), .load_return_wake_value_o(lsq_return_wake_value),
        .load_complete_valid_o(lsq_load_complete_valid), .load_complete_ready_i(lsq_load_complete_ready), .load_complete_rob_tag_o(lsq_load_complete_tag), .load_complete_rob_query_o(lsq_load_complete_rob_query), .load_complete_lsq_tag_o(lsq_load_complete_lsq_tag), .load_complete_value_o(lsq_load_complete_value), .load_complete_phys_rd_o(lsq_load_complete_phys), .load_complete_unretired_o(lsq_load_complete_unretired), .load_complete_cancel_o(lsq_load_complete_cancel), .report_recovery_packet_i(execution_recovery_views[(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]), .load_complete_error_o(lsq_load_complete_error), .dcache_store_ack_valid_i(dcache_store_ack_valid_i), .dcache_store_ack_lsq_tag_i(dcache_store_ack_lsq_tag_i), .dcache_store_ack_error_i(dcache_store_ack_error_i), .store_ack_valid_o(lsq_store_ack_valid), .store_ack_ready_i(1'b1), .store_ack_rob_tag_o(lsq_store_ack_rob_tag), .store_ack_lsq_tag_o(lsq_store_ack_lsq_tag), .store_ack_error_o(lsq_store_ack_error), .occupancy_o(lsq_occupancy), .tail_o()
    );

    // Keep producer positions fixed.  The completion network already skips
    // invalid sources while preserving source-index priority, so dynamically
    // compacting every wide payload and rank-decoding ready is redundant.
    // Sources [0, BE_WIDTH) are ALUs, followed by the shared MDU and LSQ.
    always @* begin
        producer_valid_r = {PRODUCERS{1'b0}}; producer_target_live_r = {PRODUCERS{1'b0}}; producer_rd_we_r = {PRODUCERS{1'b0}}; producer_store_r = {PRODUCERS{1'b0}}; producer_branch_r = {PRODUCERS{1'b0}}; producer_taken_r = {PRODUCERS{1'b0}}; producer_redirect_r = {PRODUCERS{1'b0}}; producer_memory_r = {PRODUCERS{1'b0}}; producer_load_r = {PRODUCERS{1'b0}};
        producer_tag_r = 0; producer_phys_r = 0; producer_value_r = 0; producer_addr_r = 0; producer_branch_target_r = 0; producer_store_data_r = 0;
        producer_recovery_index = 0;
        for (producer_index = 0; producer_index < BE_WIDTH; producer_index = producer_index + 1) begin
            producer_tag_r[producer_index*TAG_WIDTH +: TAG_WIDTH] = alu_exec_tag[producer_index*TAG_WIDTH +: TAG_WIDTH];
            producer_phys_r[producer_index*PAW +: PAW] = alu_exec_phys[producer_index*PAW +: PAW];
            producer_value_r[producer_index*32 +: 32] = alu_exec_value[producer_index*32 +: 32];
            producer_addr_r[producer_index*32 +: 32] = alu_exec_mem_addr[producer_index*32 +: 32];
            producer_branch_target_r[producer_index*32 +: 32] = alu_exec_branch_target[producer_index*32 +: 32];
            producer_store_data_r[producer_index*32 +: 32] = alu_exec_store_data[producer_index*32 +: 32];
            // Payload follows its retained source independently of valid.
            if (alu_exec_valid[producer_index] &&
                // A redirecting branch is captured into branch_pending and
                // completed together with ROB recovery on the next edge.  Do
                // not also enqueue it into the ordinary completion network:
                // at high frontend throughput that copy can reach commit
                // before recovery and leave a permanently stale pending tag.
                !alu_exec_redirect_valid[producer_index] &&
                (!alu_exec_is_load[producer_index] || alu_exec_is_store[producer_index])) begin
                producer_valid_r[producer_index] = 1'b1;
                producer_target_live_r[producer_index] = 1'b1;
                producer_rd_we_r[producer_index] = alu_exec_rd_we[producer_index];
                producer_store_r[producer_index] = alu_exec_is_store[producer_index];
                producer_branch_r[producer_index] = alu_exec_is_branch[producer_index];
                producer_taken_r[producer_index] = alu_exec_branch_taken[producer_index];
                producer_redirect_r[producer_index] = alu_exec_redirect_valid[producer_index];
                producer_memory_r[producer_index] = alu_exec_is_memory[producer_index];
            end
        end
        producer_tag_r[MDU_SOURCE*TAG_WIDTH +: TAG_WIDTH]=mdu_completion_tag;
        producer_phys_r[MDU_SOURCE*PAW +: PAW]=mdu_completion_phys;
        producer_value_r[MDU_SOURCE*32 +: 32]=mdu_completion_value;
        producer_tag_r[LSQ_SOURCE*TAG_WIDTH +: TAG_WIDTH]=lsq_load_complete_tag;
        producer_phys_r[LSQ_SOURCE*PAW +: PAW]=lsq_load_complete_phys;
        producer_value_r[LSQ_SOURCE*32 +: 32]=lsq_load_complete_value;
        if (mdu_completion_valid) begin
            producer_valid_r[MDU_SOURCE]=1'b1;
            producer_target_live_r[MDU_SOURCE]=1'b1;
            producer_rd_we_r[MDU_SOURCE]=mdu_completion_rd_we;
        end
        if (lsq_load_complete_valid) begin
            producer_valid_r[LSQ_SOURCE]=1'b1;
            producer_target_live_r[LSQ_SOURCE]=1'b1;
            producer_rd_we_r[LSQ_SOURCE]=1'b1;
            producer_load_r[LSQ_SOURCE]=1'b1;
            producer_memory_r[LSQ_SOURCE]=1'b1;
        end
        // A long-latency unit may still hold work older than a resolving
        // branch. Keep that work alive, while continuously rejecting stale
        // completions by ROB generation after recovery truncates the younger
        // suffix (whose slots and physical destinations may then be reused).
        for (producer_recovery_index = 0; producer_recovery_index < PRODUCERS;
             producer_recovery_index = producer_recovery_index + 1) begin
            if (producer_valid_r[producer_recovery_index] &&
                (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                 !producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] ||
                 (producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 + ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] !=
                  producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH])))
                producer_target_live_r[producer_recovery_index] = 1'b0;
        end
        producer_recovery_rob_slot = 0;
        producer_recovery_age = 0;
        producer_recovery_branch_age = recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH] - recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
        if (recovery_domains[6]) begin
            for (producer_recovery_index = 0; producer_recovery_index < PRODUCERS;
                 producer_recovery_index = producer_recovery_index + 1) begin
                producer_recovery_rob_slot =
                    producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                producer_recovery_age = producer_recovery_rob_slot - recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                if (producer_valid_r[producer_recovery_index] &&
                    (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                     (producer_recovery_age > producer_recovery_branch_age) ||
                     (producer_recovery_age >= recovery_descriptor_occupancy)))
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
    // ALUs have one registered result. On recovery, discard the resolving
    // branch and younger results, but preserve any strict-older completion.
    // The shared MDU is not globally flushed because it can contain an older
    // multi-cycle operation; the ROB-generation filter above safely drains
    // younger operations that were already in flight.
    always @* begin
        alu_flush_r = {BE_WIDTH{flush_i}};
        alu_recovery_slot = 0;
        alu_recovery_age = 0;
        alu_recovery_branch_age = recovery_tag_views[7*TAG_WIDTH+3 +: ROB_SLOT_WIDTH] - recovery_head_views[5*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
        if (LOCAL_EXEC_RECOVERY==0 && recovery_domains[6]) begin
            for (alu_recovery_lane = 0; alu_recovery_lane < BE_WIDTH;
                 alu_recovery_lane = alu_recovery_lane + 1) begin
                alu_recovery_slot =
                    alu_exec_tag[alu_recovery_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH];
                alu_recovery_age = alu_recovery_slot - recovery_head_views[5*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                if (alu_exec_valid[alu_recovery_lane] &&
                    (alu_recovery_age >= alu_recovery_branch_age))
                    alu_flush_r[alu_recovery_lane] = 1'b1;
            end
        end
    end
    always @* begin
        alu_exec_ready_r = {BE_WIDTH{1'b0}};
        redirect_ready_found = 0;
        for (alu_ready_lane = 0; alu_ready_lane < BE_WIDTH; alu_ready_lane = alu_ready_lane + 1) begin
            // Payload may retain a former result after its valid bit
            // clears. An empty slot cannot reserve the single redirect grant.
            if (!alu_exec_valid[alu_ready_lane]) begin
                alu_exec_ready_r[alu_ready_lane] = 1'b1;
            end else if (alu_exec_is_load[alu_ready_lane]) begin
                alu_exec_ready_r[alu_ready_lane] = 1'b1;
            end else if (alu_exec_redirect_valid[alu_ready_lane]) begin
                // branch_pending is a one-entry recovery queue.  Consume only
                // the redirect that can actually claim it; any other redirect
                // must remain stable in its ALU until the pending recovery
                // completes or explicitly flushes that younger result.
                if (!branch_pending && !redirect_ready_found) begin
                    alu_exec_ready_r[alu_ready_lane] = 1'b1;
                    redirect_ready_found = 1;
                end
            end else begin
                alu_exec_ready_r[alu_ready_lane] = producer_ready[alu_ready_lane];
            end
        end
    end
    assign alu_exec_ready = alu_exec_ready_r;

    rv32_completion_network #(.BE_WIDTH(BE_WIDTH), .CDB_WIDTH(CDB_WIDTH), .SOURCES(PRODUCERS), .FIFO_DEPTH(COMPLETION_DEPTH), .TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PAW), .BYPASS(COMPLETION_BYPASS), .DIRECT_BRANCH_PAYLOAD(0),
        .DIRECT_STORE_PAYLOAD((LIGHT_RETIRE_PAYLOAD==0) || (ROB_RETURN_VALUE_ENABLE!=0))) completion (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .kill_valid_i(recovery_domains[6]), .kill_mask_i(completion_kill_mask), .producer_valid_i(producer_valid), .producer_ready_o(producer_ready_r), .producer_tag_i(producer_tag), .producer_phys_rd_i(producer_phys), .producer_value_i(producer_value), .producer_addr_i(producer_addr), .producer_branch_target_i(producer_branch_target), .producer_store_data_i(producer_store_data), .producer_rd_we_i(producer_rd_we), .producer_is_store_i(producer_store), .producer_is_branch_i(producer_branch), .producer_branch_taken_i(producer_taken), .producer_redirect_valid_i(producer_redirect), .producer_is_memory_i(producer_memory), .producer_is_load_i(producer_load), .producer_target_live_i(producer_target_live_r), .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}}), .cdb_valid_o(cdb_valid), .cdb_ready_i(cdb_ready), .cdb_tag_o(cdb_tag), .cdb_phys_rd_o(cdb_phys), .cdb_value_o(cdb_value), .cdb_addr_o(cdb_addr), .cdb_branch_target_o(cdb_branch_target), .cdb_store_data_o(cdb_store_data), .cdb_rd_we_o(cdb_rd_we), .cdb_is_store_o(cdb_is_store), .cdb_is_branch_o(cdb_is_branch), .cdb_branch_taken_o(cdb_branch_taken), .cdb_redirect_valid_o(cdb_redirect_valid), .cdb_is_memory_o(cdb_is_memory), .cdb_is_load_o(cdb_is_load), .prf_write_valid_o(completion_prf_write_valid), .prf_write_tag_o(prf_wb_tag), .prf_write_phys_rd_o(completion_prf_write_phys), .prf_write_value_o(completion_prf_write_data), .rob_ready_valid_o(rob_wb_valid), .rob_ready_tag_o(rob_wb_tag), .rob_ready_value_o(rob_wb_value), .wakeup_valid_o(wake_wb_valid), .wakeup_tag_o(wake_wb_tag), .wakeup_value_o(wake_wb_value), .entry_valid_o(completion_entry_valid), .entry_tag_o(completion_entry_tag), .occupancy_o()
    );
    // A valid producer holds its result until the completion network accepts
    // it.  Its value can therefore wake a dependent RS entry even when the
    // completion FIFO is temporarily full.  Keeping the wake path independent
    // of producer_ready also avoids the FIFO admission/backpressure chain on
    // the producer -> RS -> ALU same-cycle bypass path.  A producer killed by
    // recovery is suppressed in each ALU/MDU owner. LSQ additionally
    // carries unretired lifetime with its report and applies the same snapshot.
    // CDB/PRF/ROB generation filtering is unchanged.
    // A locally owned ALU/MDU result loses valid on recovery BEFORE its
    // destination can be reclaimed. Completion still uses the full ROB
    // valid/generation authority above. A retained retired load cannot
    // wake, even if a late response reaches its still-allocated LSQ row.
    wire lsq_wake_cancel;
    generate if(LOCAL_EXEC_RECOVERY!=0) begin:g_preselected_lsq_cancel
        // Exact cancellation is selected with the LSQ report, removing the
        // late selected-tag subtraction/comparisons from the RS wake chain.
        assign lsq_wake_cancel=lsq_load_complete_cancel;
    end else begin:g_legacy_lsq_cancel
        rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
            .ENABLED(LOCAL_EXEC_RECOVERY),.KILL_BRANCH(0)) lsq_wake_guard (
            .packet_i(execution_recovery_views[(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
            .active_i(lsq_load_complete_valid),.tag_i(lsq_load_complete_tag),.cancel_o(lsq_wake_cancel));
    end endgenerate
    wire [PRODUCERS-1:0] producer_wake_live;
    generate for(genvar wake_owner=0;wake_owner<PRODUCERS;wake_owner=wake_owner+1) begin:g_wake_owner
        if(LOCAL_EXEC_RECOVERY!=0 && wake_owner<=MDU_SOURCE) begin:g_local_execution
            assign producer_wake_live[wake_owner]=!reset_i && !flush_i &&
                producer_tag[wake_owner*TAG_WIDTH];
        end else if(LOCAL_EXEC_RECOVERY!=0 && wake_owner==LSQ_SOURCE) begin:g_local_load
            assign producer_wake_live[wake_owner]=!reset_i && !flush_i &&
                lsq_load_complete_unretired && lsq_load_complete_tag[0] && !lsq_wake_cancel;
        end else begin:g_rob_authority
            assign producer_wake_live[wake_owner]=producer_target_live_r[wake_owner];
        end
    end endgenerate
    generate if(RS_DIRECT_WAKE!=0) begin:g_direct_producer_wake
        assign rs_base_wake_valid=producer_valid & producer_rd_we & producer_wake_live;
        assign rs_base_wake_value=producer_value;
    end else begin:g_queued_or_legacy_wake
        assign rs_base_wake_valid={producer_valid & producer_rd_we & producer_wake_live,wake_wb_valid};
        assign rs_base_wake_value={producer_value,wake_wb_value};
    end endgenerate

    // Keep the saved LSQ completion wake and new response wake in separate
    // columns: simultaneous returns must not hide an accepted older result.
    generate if(RS_LOAD_RETURN_WAKE!=0) begin:g_early_load_wake
        assign rs_wake_valid={lsq_return_wake_valid,rs_base_wake_valid};
        assign rs_wake_value={lsq_return_wake_value,rs_base_wake_value};
    end else begin:g_original_load_wake
        assign rs_wake_valid=rs_base_wake_valid;
        assign rs_wake_value=rs_base_wake_value;
    end endgenerate

    genvar wake_identity_lane;
    generate if(RS_PHYSICAL_WAKEUP!=0) begin:g_physical_wake_identity
        for(wake_identity_lane=0;wake_identity_lane<RS_WAKE_WIDTH;wake_identity_lane=wake_identity_lane+1) begin:g_lane
            wire [PAW-1:0] phys;
            if(RS_LOAD_RETURN_WAKE!=0 && wake_identity_lane==RS_BASE_WAKE_WIDTH) begin:g_return_load
                assign phys=lsq_return_wake_phys;
            end else if(RS_DIRECT_WAKE!=0) begin:g_direct_producer
                assign phys=producer_phys[wake_identity_lane*PAW +: PAW];
            end else if(wake_identity_lane<BE_WIDTH) begin:g_completed
                // Completion exports wake tag/value from this same CDB lane.
                assign phys=cdb_phys[wake_identity_lane*PAW +: PAW];
            end else begin:g_held_producer
                assign phys=producer_phys[(wake_identity_lane-BE_WIDTH)*PAW +: PAW];
            end
            assign rs_wake_tag[wake_identity_lane*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]={phys,(phys!=0 && phys<PHYS_REGS)};
        end
    end else begin:g_rob_wake_identity
        assign rs_wake_tag={producer_tag,wake_wb_tag};
    end endgenerate



    localparam integer ROB_COMPLETION_PACKET_WIDTH=TAG_WIDTH+103;
    localparam integer ROB_COMPLETION_PACKET_WORDS=(ROB_COMPLETION_PACKET_WIDTH+15)/16;
    wire [BE_WIDTH-1:0] completion_recovery_modes;
    rv32_frequency_control_tree #(.LEAVES(BE_WIDTH)) completion_recovery_tree (
        .signal_i(branch_pending),.views_o(completion_recovery_modes));
    genvar routed_lane,routed_word;
    generate for(routed_lane=0;routed_lane<BE_WIDTH;routed_lane=routed_lane+1) begin:g_rob_completion_route
        wire [ROB_SLOT_WIDTH-1:0] normal_slot=rob_wb_tag[routed_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
        wire normal_in_range=normal_slot<ROB_ENTRIES;
        wire normal_error=rob_wb_valid[routed_lane] && normal_in_range &&
            (completion_state_reads[routed_lane*3+2] || completion_live_load_error[routed_lane]);
        wire [1:0] normal_size=completion_state_reads[routed_lane*3 +: 2];
        wire [3:0] normal_mask=(rob_wb_valid[routed_lane] && normal_in_range && cdb_is_store[routed_lane])?
            ((normal_size==`RV32IM_MEM_BYTE)?4'b0001:((normal_size==`RV32IM_MEM_HALF)?4'b0011:4'b1111)):4'b0;
        wire [ROB_COMPLETION_PACKET_WIDTH-1:0] normal_packet={
            (rob_wb_valid[routed_lane] && cdb_ready[routed_lane]),rob_wb_valid[routed_lane],normal_error,
            rob_wb_tag[routed_lane*TAG_WIDTH +: TAG_WIDTH],rob_wb_value[routed_lane*32 +: 32],
            cdb_addr[routed_lane*32 +: 32],normal_mask,cdb_store_data[routed_lane*32 +: 32]};
        wire [ROB_COMPLETION_PACKET_WIDTH-1:0] recovery_packet,routed_packet;
        if(routed_lane==0) begin:g_branch
            assign recovery_packet={1'b1,1'b1,1'b0,recovery_tag_views[0 +: TAG_WIDTH],branch_pending_value,
                32'b0,4'b0,32'b0};
        end else if(routed_lane-1<CDB_WIDTH-1) begin:g_shifted
            localparam integer SOURCE=routed_lane-1;
            wire accepted=rob_wb_valid[SOURCE] && cdb_ready[SOURCE];
            wire [ROB_SLOT_WIDTH-1:0] slot=rob_wb_tag[SOURCE*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            wire in_range=slot<ROB_ENTRIES;
            wire error=(completion_state_reads[SOURCE*3+2] || completion_live_load_error[SOURCE]) && in_range;
            wire [1:0] size=completion_state_reads[SOURCE*3 +: 2];
            wire [3:0] mask=(in_range && cdb_is_store[SOURCE])?
                ((size==`RV32IM_MEM_BYTE)?4'b0001:((size==`RV32IM_MEM_HALF)?4'b0011:4'b1111)):4'b0;
            wire [63:0] store_payload;
            rv32_frequency_event_select #(.WIDTH(64),.EVENTS(1)) store_selector (
                .events_i(in_range),.values_i({cdb_addr[SOURCE*32 +: 32],cdb_store_data[SOURCE*32 +: 32]}),
                .write_o(),.value_o(store_payload));
            rv32_frequency_event_select #(.WIDTH(ROB_COMPLETION_PACKET_WIDTH),.EVENTS(1)) accepted_selector (
                .events_i(accepted),
                .values_i({1'b1,1'b1,error,rob_wb_tag[SOURCE*TAG_WIDTH +: TAG_WIDTH],rob_wb_value[SOURCE*32 +: 32],
                    store_payload[63:32],mask,store_payload[31:0]}),.write_o(),.value_o(recovery_packet));
        end else begin:g_unavailable
            assign recovery_packet=0;
        end
        wire [ROB_COMPLETION_PACKET_WORDS-1:0] mode_views;
        rv32_frequency_control_tree #(.LEAVES(ROB_COMPLETION_PACKET_WORDS)) lane_mode_tree (
            .signal_i(completion_recovery_modes[routed_lane]),.views_o(mode_views));
        for(routed_word=0;routed_word<ROB_COMPLETION_PACKET_WORDS;routed_word=routed_word+1) begin:g_word
            localparam integer LOW=routed_word*16;
            localparam integer BITS=(ROB_COMPLETION_PACKET_WIDTH-LOW>=16)?16:ROB_COMPLETION_PACKET_WIDTH-LOW;
            assign routed_packet[LOW +: BITS]=mode_views[routed_word]?
                recovery_packet[LOW +: BITS]:normal_packet[LOW +: BITS];
        end
        assign {completion_valid_r[routed_lane],completion_done_r[routed_lane],completion_error_r[routed_lane],
            completion_tag_r[routed_lane*TAG_WIDTH +: TAG_WIDTH],completion_value_r[routed_lane*32 +: 32],
            completion_store_addr_r[routed_lane*32 +: 32],completion_store_mask_r[routed_lane*4 +: 4],
            completion_store_data_r[routed_lane*32 +: 32]}=routed_packet;
    end endgenerate

    // R-stage metadata and D-stage maps are payloads. A valid ROB/LSQ
    // transaction always allocates these rows before a consumer can use them.
    // Reset clears the transaction validity in its owner, not these payloads.
    localparam integer MAP_DOMAINS=4;
    localparam integer R_META_WIDTH=2+((RS_ISSUE_METADATA==0)?100:0)+
        ((PREDICTOR_META!=0)?16:0);
    wire [MAP_DOMAINS*BE_WIDTH-1:0] r_map_writes,d_map_writes;
    wire [MAP_DOMAINS*BE_WIDTH*ROB_SLOT_WIDTH-1:0] r_map_slots,d_rob_map_slots;
    wire [MAP_DOMAINS*BE_WIDTH*R_META_WIDTH-1:0] r_map_values;
    wire [MAP_DOMAINS*BE_WIDTH*TAG_WIDTH-1:0] d_rob_map_values;
    wire [BE_WIDTH*ROB_SLOT_WIDTH-1:0] r_slot_input,d_rob_slot_input;
    wire [BE_WIDTH*R_META_WIDTH-1:0] r_metadata_input;
    wire [ROB_ENTRIES-1:0] error_reset_views,error_response_views;
    wire [MAP_DOMAINS*ROB_SLOT_WIDTH-1:0] error_slot_views;
    wire error_response=lsq_load_complete_valid && lsq_load_complete_ready &&
        lsq_load_complete_error && lsq_load_complete_tag[0] &&
        lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]<ROB_ENTRIES &&
        producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&
        lsq_load_complete_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
        producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH];
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(MAP_DOMAINS)) r_write_tree (
        .signal_i(dispatch_valid & rob_alloc_fire & {BE_WIDTH{!reset_i}}),.views_o(r_map_writes));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(MAP_DOMAINS)) d_write_tree (
        .signal_i(d_valid & lsq_alloc_fire & {BE_WIDTH{!reset_i}}),.views_o(d_map_writes));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*ROB_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) r_slot_tree (
        .signal_i(r_slot_input),.views_o(r_map_slots));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*ROB_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) d_rob_slot_tree (
        .signal_i(d_rob_slot_input),.views_o(d_rob_map_slots));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*R_META_WIDTH),.LEAVES(MAP_DOMAINS)) r_value_tree (
        .signal_i(r_metadata_input),.views_o(r_map_values));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*TAG_WIDTH),.LEAVES(MAP_DOMAINS)) d_rob_value_tree (
        .signal_i(lsq_alloc_tag),.views_o(d_rob_map_values));
    rv32_frequency_control_tree #(.LEAVES(ROB_ENTRIES)) error_reset_tree (
        .signal_i(reset_i),.views_o(error_reset_views));
    rv32_frequency_control_tree #(.LEAVES(ROB_ENTRIES)) error_response_tree (
        .signal_i(error_response),.views_o(error_response_views));
    rv32_frequency_control_tree #(.WIDTH(ROB_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) error_slot_tree (
        .signal_i(lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]),.views_o(error_slot_views));
    genvar map_row,map_lane_id;
    generate
        for(map_lane_id=0;map_lane_id<BE_WIDTH;map_lane_id=map_lane_id+1) begin:g_map_input
            assign r_slot_input[map_lane_id*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]=
                rob_alloc_tag[map_lane_id*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            assign d_rob_slot_input[map_lane_id*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]=
                d_tag[map_lane_id*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            assign r_metadata_input[map_lane_id*R_META_WIDTH +: 2]=trace_mem_size_i[map_lane_id*2 +: 2];
            if(RS_ISSUE_METADATA==0) begin:g_legacy
                assign r_metadata_input[map_lane_id*R_META_WIDTH+2 +: 100]={
                    trace_mem_unsigned_i[map_lane_id],trace_pred_kind_i[map_lane_id*2 +: 2],
                    trace_pred_target_i[map_lane_id*32 +: 32],trace_pred_taken_i[map_lane_id],
                    trace_imm_i[map_lane_id*32 +: 32],trace_pc_i[map_lane_id*32 +: 32]};
            end
            if(PREDICTOR_META!=0) begin:g_history
                assign r_metadata_input[map_lane_id*R_META_WIDTH+2+((RS_ISSUE_METADATA==0)?100:0) +: 16]=
                    trace_pred_metadata_i[map_lane_id*16 +: 16];
            end
        end
        for(map_row=0;map_row<ROB_ENTRIES;map_row=map_row+1) begin:g_rob_map_row
            localparam integer DOMAIN=(map_row*MAP_DOMAINS)/ROB_ENTRIES;
            wire [BE_WIDTH-1:0] r_matches,d_matches;
            wire r_write,d_write;
            wire [R_META_WIDTH-1:0] r_value,r_saved;
            wire [TAG_WIDTH-1:0] d_value;
            for(map_lane_id=0;map_lane_id<BE_WIDTH;map_lane_id=map_lane_id+1) begin:g_match
                assign r_matches[map_lane_id]=r_map_writes[DOMAIN*BE_WIDTH+map_lane_id] &&
                    r_map_slots[(DOMAIN*BE_WIDTH+map_lane_id)*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_row;
                assign d_matches[map_lane_id]=d_map_writes[DOMAIN*BE_WIDTH+map_lane_id] &&
                    d_rob_map_slots[(DOMAIN*BE_WIDTH+map_lane_id)*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_row;
            end
            rv32_frequency_event_select #(.WIDTH(R_META_WIDTH),.EVENTS(BE_WIDTH)) r_select (
                .events_i(r_matches),.values_i(r_map_values[DOMAIN*BE_WIDTH*R_META_WIDTH +: BE_WIDTH*R_META_WIDTH]),
                .write_o(r_write),.value_o(r_value));
            rv32_frequency_word_bank #(.WIDTH(R_META_WIDTH)) r_owner (
                .clk_i(clk_i),.write_i(r_write),.data_i(r_value),.data_o(r_saved));
            assign rob_mem_size_mem[map_row]=r_saved[0 +: 2];
            if(RS_ISSUE_METADATA==0) begin:g_legacy
                assign {rob_mem_unsigned_mem[map_row],rob_pred_kind_mem[map_row],rob_pred_target_mem[map_row],
                    rob_pred_taken_mem[map_row],rob_imm_mem[map_row],rob_pc_mem[map_row]}=r_saved[2 +: 100];
            end else begin:g_inline
                assign rob_mem_unsigned_mem[map_row]=0;
                assign rob_pred_kind_mem[map_row]=0;
                assign rob_pred_target_mem[map_row]=0;
                assign rob_pred_taken_mem[map_row]=0;
                assign rob_imm_mem[map_row]=0;
                assign rob_pc_mem[map_row]=0;
            end
            if(PREDICTOR_META!=0) begin:g_history
                assign rob_pred_metadata_mem[map_row]=r_saved[2+((RS_ISSUE_METADATA==0)?100:0) +: 16];
            end else begin:g_no_history
                assign rob_pred_metadata_mem[map_row]=0;
            end
            rv32_frequency_event_select #(.WIDTH(TAG_WIDTH),.EVENTS(BE_WIDTH)) d_select (
                .events_i(d_matches),.values_i(d_rob_map_values[DOMAIN*BE_WIDTH*TAG_WIDTH +: BE_WIDTH*TAG_WIDTH]),
                .write_o(d_write),.value_o(d_value));
            rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH)) d_owner (
                .clk_i(clk_i),.write_i(d_write),.data_i(d_value),.data_o(rob_to_lsq_mem[map_row]));
            reg error_q;
            assign load_error_mem[map_row]=error_q;
            always @(posedge clk_i) begin
                if(error_reset_views[map_row]) error_q<=1'b0;
                else if(error_response_views[map_row] &&
                        error_slot_views[DOMAIN*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_row) error_q<=1'b1;
                else if(r_write) error_q<=1'b0;
            end
        end
    endgenerate

    assign rob_store_ack_valid = lsq_store_ack_valid;
    assign rob_store_ack_tag = lsq_store_ack_rob_tag;

    generate if(RECOVERY_DIRECT_ACTIVE!=0) begin:g_direct_recovery_descriptor
        // All consumers share the current pre-edge ROB prefix. No allocation
        // or commit occurs on this apply edge; full GEN authority stays in ROB.
        assign recovery_descriptor_valid=branch_pending && rob_recovery_preview;
        assign recovery_descriptor_rat=recovery_rat_state;
        assign recovery_descriptor_reclaim=rob_recovery_reclaim_bitmap;
        assign recovery_descriptor_reclaim_count=rob_recovery_reclaim_count;
        assign recovery_descriptor_head=rob_head_views[0 +: ROB_SLOT_WIDTH];
        assign recovery_descriptor_occupancy=rob_occupancy;
        assign recovery_descriptor_rs_kill=rs_preview_kill_mask;
    end else begin:g_staged_recovery_descriptor
        reg recovery_descriptor_valid_saved;
        reg [FREE_COUNT_WIDTH-1:0] recovery_descriptor_reclaim_count_saved;
        reg [ROB_SLOT_WIDTH-1:0] recovery_descriptor_head_saved;
        reg [ROB_COUNT_WIDTH-1:0] recovery_descriptor_occupancy_saved;
        reg [RS_ENTRIES-1:0] recovery_descriptor_rs_kill_saved;
        assign recovery_descriptor_valid=recovery_descriptor_valid_saved;
        assign recovery_descriptor_reclaim_count=recovery_descriptor_reclaim_count_saved;
        assign recovery_descriptor_head=recovery_descriptor_head_saved;
        assign recovery_descriptor_occupancy=recovery_descriptor_occupancy_saved;
        assign recovery_descriptor_rs_kill=recovery_descriptor_rs_kill_saved;
    rv32_frequency_word_bank #(.WIDTH(CHECK_RAT_WIDTH)) rat_descriptor_owner (
        .clk_i(clk_i),.write_i(recovery_capture_domains[1]),
        .data_i(recovery_rat_state),.data_o(recovery_descriptor_rat));
    rv32_frequency_word_bank #(.WIDTH(PHYS_REGS)) reclaim_descriptor_owner (
        .clk_i(clk_i),.write_i(recovery_capture_domains[2]),
        .data_i(rob_recovery_reclaim_bitmap),.data_o(recovery_descriptor_reclaim));
    always @(posedge clk_i) begin
        if(reset_i || flush_i) recovery_descriptor_valid_saved<=1'b0;
        else if(recovery_domains[7]) recovery_descriptor_valid_saved<=1'b0;
        else if(recovery_capture_domains[0]) recovery_descriptor_valid_saved<=1'b1;
        if(recovery_capture_domains[2]) begin
            recovery_descriptor_reclaim_count_saved<=rob_recovery_reclaim_count;
        end
        if(recovery_capture_domains[3]) begin
            recovery_descriptor_head_saved<=rob_head_views[0 +: ROB_SLOT_WIDTH];
            recovery_descriptor_occupancy_saved<=rob_occupancy;
            recovery_descriptor_rs_kill_saved<=rs_preview_kill_mask;
        end
    end
    end endgenerate

    // Only accepted live redirects can acquire this packet. Select the first
    // lane exactly as the old ordered loop, then distribute the qualified
    // grants and write enable into at most sixteen payload bits per leaf.
    // Direct ROB apply is sourced only by branch_pending. Capture
    // requires !branch_pending, so selective apply cancellation is zero in
    // its whole acceptance domain. All real execution ports keep cancel.
    localparam integer CAPTURE_PHASE_VALID_ACTIVE=(BRANCH_CAPTURE_PHASE_VALID!=0) &&
        (BRANCH_CAPTURE_REDIRECT_READY!=0) && (RECOVERY_DIRECT_ACTIVE!=0);
    wire [BE_WIDTH-1:0] branch_capture_valid=(CAPTURE_PHASE_VALID_ACTIVE!=0)?
        alu_exec_saved_valid:alu_exec_valid;
    wire [BE_WIDTH-1:0] capture_redirect_claim=
        branch_capture_valid & alu_exec_redirect_valid & ~alu_exec_is_load;
    wire [BE_WIDTH-1:0] capture_redirect_ready;
    genvar capture_lane;
    generate for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_branch_capture
        // Under valid+redirect+!pending, the original ready loop selects
        // loads unconditionally; otherwise only earlier valid non-load
        // redirects can block this lane. Their GEN validity does not change
        // that original priority. Ordinary producer_ready cannot affect it.
        if(capture_lane==0) begin:g_first_ready
            assign capture_redirect_ready[capture_lane]=1'b1;
        end else begin:g_later_ready
            assign capture_redirect_ready[capture_lane]=alu_exec_is_load[capture_lane] ||
                !(|capture_redirect_claim[capture_lane-1:0]);
        end
        assign branch_capture_match[capture_lane]=!reset_i && !flush_i && !branch_pending &&
            branch_capture_valid[capture_lane] &&
            ((BRANCH_CAPTURE_REDIRECT_READY!=0)?capture_redirect_ready[capture_lane]:alu_exec_ready[capture_lane]) &&
            branch_training_live[capture_lane] && alu_exec_redirect_valid[capture_lane];
        if(capture_lane==0) begin:g_first
            assign branch_capture_grant[capture_lane]=branch_capture_match[capture_lane];
        end else begin:g_priority
            assign branch_capture_grant[capture_lane]=branch_capture_match[capture_lane] &&
                !(|branch_capture_match[capture_lane-1:0]);
        end
        assign branch_capture_values[capture_lane*BRANCH_CAPTURE_WIDTH +: BRANCH_CAPTURE_WIDTH]={
            alu_exec_tag[capture_lane*TAG_WIDTH +: TAG_WIDTH],
            alu_exec_phys[capture_lane*PAW +: PAW],alu_exec_rd_we[capture_lane],
            alu_exec_value[capture_lane*32 +: 32],alu_exec_redirect_pc[capture_lane*32 +: 32]};
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(BRANCH_CAPTURE_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) branch_capture_selector (
        .events_i(branch_capture_grant),.values_i(branch_capture_values),
        .write_o(branch_capture_write),.value_o(branch_capture_next));
    rv32_frequency_word_bank #(.WIDTH(BRANCH_CAPTURE_WIDTH)) branch_capture_owner (
        .clk_i(clk_i),.write_i(branch_capture_write),.data_i(branch_capture_next),.data_o(branch_capture_saved));
    assign {branch_pending_tag,branch_pending_phys,branch_pending_rd_we,
            branch_pending_value,branch_pending_pc}=branch_capture_saved;
    generate if(PREDICTOR_META!=0) begin:g_branch_history_capture
        wire [BE_WIDTH*8-1:0] histories;
        wire history_write;
        wire [7:0] history_next,history_saved;
        for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_lane
            wire [ROB_SLOT_WIDTH-1:0] slot=alu_exec_tag[capture_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            wire [1:0] kind=(RS_ISSUE_METADATA!=0)?
                alu_exec_pred_kind[capture_lane*2 +: 2]:rob_pred_kind_mem[slot];
            assign histories[capture_lane*8 +: 8]=(kind==`RV32IM_PRED_BRANCH)?
                {rob_pred_metadata_mem[slot][14:8],alu_exec_branch_taken[capture_lane]}:
                rob_pred_metadata_mem[slot][15:8];
        end
        rv32_frequency_event_select #(.WIDTH(8),.EVENTS(BE_WIDTH),.PRIORITY(0)) history_selector (
            .events_i(branch_capture_grant),.values_i(histories),.write_o(history_write),.value_o(history_next));
        rv32_frequency_word_bank #(.WIDTH(8)) history_owner (
            .clk_i(clk_i),.write_i(history_write),.data_i(history_next),.data_o(history_saved));
        // Early redirect and GHR repair must use the same accepted branch on
        // the same edge. Waiting for history_saved adds a fetch bubble or
        // restores a previous branch's checkpoint. Preview mode uses saved.
        assign branch_recovery_history_o=(EARLY_FRONT_REDIRECT!=0 && branch_capture_write)?
            history_next:history_saved;
    end else begin:g_no_branch_history
        assign branch_recovery_history_o=8'b0;
    end endgenerate

    always @(posedge clk_i) begin
        if(reset_i) branch_pending<=1'b0;
        else if(flush_i || (branch_pending && !recovery_descriptor_valid && !rob_recovery_preview))
            branch_pending<=1'b0;
        else if(recovery_domains[7] && branch_pending) branch_pending<=1'b0;
        else if(branch_capture_write) branch_pending<=1'b1;
        else if(branch_pending && commit_ready_i && rob_commit_valid[0] &&
                rob_commit_tag[TAG_WIDTH-1:0]==recovery_tag_views[0 +: TAG_WIDTH])
            branch_pending<=1'b0;
    end

endmodule

// Two retained entries break the functional-unit ready -> RS ready path.
// Unstalled first-result latency is still one registered selection stage.
module rv32_issue_pipeline_slot #(
    parameter integer PAYLOAD_WIDTH=192, TAG_WIDTH=17, ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES)
) (
    input wire clk_i, reset_i, flush_i, recovery_i,
    input wire [SW-1:0] head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire valid_i, eligible_i,
    output wire ready_o,
    input wire [PAYLOAD_WIDTH-1:0] data_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire valid_o,
    input wire ready_i,
    output wire [PAYLOAD_WIDTH-1:0] data_o
);
    localparam integer CHUNKS=(PAYLOAD_WIDTH+15)/16;
    reg [1:0] count,entry_valid;
    reg read_slot,write_slot;
    reg [PAYLOAD_WIDTH-1:0] payload [0:1];
    reg [TAG_WIDTH-1:0] saved_tag [0:1];
    wire [1:0] recovery_keep;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-head_i;
    wire push=valid_i && ready_o;
    wire pop=valid_o && ready_i;
    wire [CHUNKS-1:0] read_views;
    rv32_frequency_control_tree #(.LEAVES(CHUNKS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    // Ready depends only on registered occupancy, with one spare entry to
    // absorb backpressure. A full queue advertises space after its pop edge.
    assign ready_o=(count<2) && eligible_i && !reset_i && !flush_i && !recovery_i;
    assign valid_o=(count!=0) && !reset_i && !flush_i && !recovery_i;
    genvar queue_row,chunk;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        wire [SW-1:0] age=saved_tag[queue_row][3 +: SW]-head_i;
        assign recovery_keep[queue_row]=entry_valid[queue_row] &&
            saved_tag[queue_row][0] && age<branch_age;
        wire [CHUNKS:0] write_views;
        rv32_frequency_control_tree #(.LEAVES(CHUNKS+1)) write_tree (
            .signal_i(push && write_slot==queue_row),.views_o(write_views));
        always @(posedge clk_i) if(write_views[CHUNKS]) saved_tag[queue_row]<=tag_i;
        for(chunk=0;chunk<CHUNKS;chunk=chunk+1) begin:g_chunk
            localparam integer LOW=chunk*16;
            localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
            always @(posedge clk_i) if(write_views[chunk])
                payload[queue_row][LOW +: BITS]<=data_i[LOW +: BITS];
        end
    end
    for(chunk=0;chunk<CHUNKS;chunk=chunk+1) begin:g_read
        localparam integer LOW=chunk*16;
        localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
        assign data_o[LOW +: BITS]=read_views[chunk]?
            payload[1][LOW +: BITS]:payload[0][LOW +: BITS];
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            count<=0;entry_valid<=0;read_slot<=0;write_slot<=0;
        end else if(recovery_i) begin
            entry_valid<=recovery_keep;
            case(recovery_keep)
                2'b11: count<=2;
                2'b01: begin count<=1;read_slot<=0;write_slot<=1;end
                2'b10: begin count<=1;read_slot<=1;write_slot<=0;end
                default: begin count<=0;read_slot<=0;write_slot<=0;end
            endcase
        end else begin
            count<=count+push-pop;
            if(pop) begin entry_valid[read_slot]<=1'b0;read_slot<=!read_slot;end
            if(push) begin entry_valid[write_slot]<=1'b1;write_slot<=!write_slot;end
        end
    end
endmodule


module rv32_producer_tag_row #(parameter integer LANES=4,TAG_WIDTH=17) (
    input wire clk_i,reset_i,
    input wire [LANES-1:0] match_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    output wire [TAG_WIDTH-1:0] tag_o
);
    reg stored_valid;
    reg [TAG_WIDTH-1:0] stored_tag;
    wire [LANES-1:0] grants,local_grants;
    wire write_local;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_grant
        if(lane==LANES-1) assign grants[lane]=match_i[lane];
        else assign grants[lane]=match_i[lane] && !(|match_i[LANES-1:lane+1]);
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) grant_tree (
        .signal_i(grants),.views_o(local_grants));
    rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
        .signal_i(!reset_i && (|match_i)),.views_o(write_local));
    reg [TAG_WIDTH-1:0] next_tag;
    integer writer;
    always @* begin
        next_tag=0;
        for(writer=0;writer<LANES;writer=writer+1)
            next_tag=next_tag | ({TAG_WIDTH{local_grants[writer]}} &
                               tag_i[writer*TAG_WIDTH +: TAG_WIDTH]);
    end
    always @(posedge clk_i) if(write_local) stored_tag<=next_tag;
    always @(posedge clk_i) begin
        if(reset_i) stored_valid<=0;
        else if(|match_i) stored_valid<=1;
    end
    // Before the first write after reset, the visible tag is exactly zero,
    // matching the former full-word reset. A write replaces all tag bits.
    assign tag_o={TAG_WIDTH{stored_valid}} & stored_tag;
endmodule


// A deterministic one-bundle pipeline. Its resource reservations guarantee
// complete D admission, so no RS/LSQ admission signal feeds back into R.
module rv32_reserved_dispatch_packet #(
    parameter integer LANES=4,PAYLOAD_WIDTH=160,TAG_WIDTH=17,ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer GW=TAG_WIDTH-SW-3
) (
    input wire clk_i,reset_i,flush_i,hold_i,recovery_i,
    input wire [SW-1:0] recovery_head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire [15:0] recovery_occupancy_i,
    input wire [ROB_ENTRIES-1:0] rob_valid_i,
    input wire [ROB_ENTRIES*GW-1:0] rob_generation_i,
    input wire [LANES-1:0] valid_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    input wire [LANES-1:0] saved_is_memory_i,
    output wire [LANES-1:0] valid_o,
    output wire [LANES*TAG_WIDTH-1:0] tag_o,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o,
    output reg [15:0] reserved_rs_o,reserved_lsq_o
);
    reg [LANES-1:0] valid_q;
    wire [TAG_WIDTH-1:0] tag_q [0:LANES-1];
    wire [ROB_ENTRIES*(GW+1)-1:0] live_rows;
    genvar live_row;
    generate for(live_row=0;live_row<ROB_ENTRIES;live_row=live_row+1) begin:g_live_row
        assign live_rows[live_row*(GW+1) +: GW+1]={rob_valid_i[live_row],rob_generation_i[live_row*GW +: GW]};
    end endgenerate
    wire [LANES-1:0] recovery_keep;
    wire normal=!reset_i && !flush_i && !hold_i && !recovery_i;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-recovery_head_i;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_lane
        wire [SW-1:0] slot=tag_q[lane][3 +: SW];
        wire [SW-1:0] age=slot-recovery_head_i;
        wire [GW:0] live;
        rv32_frequency_array_read #(.WIDTH(GW+1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) live_reader (
            .rows_i(live_rows),.index_i(slot),.value_o(live));
        wire generation_live=live[GW] && tag_q[lane][3+SW +: GW]==live[0 +: GW];
        assign recovery_keep[lane]=valid_q[lane] && tag_q[lane][0] &&
            generation_live && age<branch_age && age<recovery_occupancy_i;
        assign valid_o[lane]=normal && valid_q[lane];
        assign tag_o[lane*TAG_WIDTH +: TAG_WIDTH]=tag_q[lane];
        rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH)) tag_owner (
            .clk_i(clk_i),.write_i(normal && valid_i[lane]),
            .data_i(tag_i[lane*TAG_WIDTH +: TAG_WIDTH]),.data_o(tag_q[lane]));
        rv32_frequency_word_bank #(.WIDTH(PAYLOAD_WIDTH)) payload_owner (
            .clk_i(clk_i),.write_i(normal && valid_i[lane]),
            .data_i(data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]),
            .data_o(data_o[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]));
    end endgenerate
    integer count_lane;
    always @* begin
        reserved_rs_o=0;reserved_lsq_o=0;
        for(count_lane=0;count_lane<LANES;count_lane=count_lane+1) begin
            if(valid_q[count_lane]) reserved_rs_o=reserved_rs_o+1'b1;
            if(valid_q[count_lane] && saved_is_memory_i[count_lane])
                reserved_lsq_o=reserved_lsq_o+1'b1;
        end
    end
    always @(posedge clk_i) begin
        if(reset_i || flush_i) valid_q<=0;
        else if(recovery_i) valid_q<=recovery_keep;
        else if(!hold_i) valid_q<=valid_i;
    end
endmodule

// Two bundle entries break the D-resource/PRF path from R acceptance.
// R allocates ROB/physical destinations once. D emits the entire oldest
// bundle only when both its actual RS and LSQ demands fit the saved free
// counts. Recovery retains only full-generation-live, older ROB tags.
module rv32_elastic_dispatch_packet #(
    parameter integer FULL_REPLACE=0,
    parameter integer LANES=2,PAYLOAD_WIDTH=160,TAG_WIDTH=16,ROB_ENTRIES=32,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer GW=TAG_WIDTH-SW-3
) (
    input wire clk_i,reset_i,flush_i,hold_i,recovery_i,
    input wire [SW-1:0] recovery_head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire [15:0] recovery_occupancy_i,
    input wire [ROB_ENTRIES-1:0] rob_valid_i,
    input wire [ROB_ENTRIES*GW-1:0] rob_generation_i,
    input wire [LANES-1:0] valid_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output wire ready_o,
    output wire [LANES-1:0] valid_o,
    output wire [LANES*TAG_WIDTH-1:0] tag_o,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o,
    // Caller guarantees consume_i when this credit is asserted. It is a
    // saved-capacity proof, not a late consume/PRF combinational ready path.
    input wire replace_credit_i,
    input wire consume_i
);
    reg [1:0] count;
    reg read_slot,write_slot;
    reg [LANES-1:0] valids [0:1];
    wire [TAG_WIDTH-1:0] tags [0:2*LANES-1];
    wire [PAYLOAD_WIDTH-1:0] payloads [0:2*LANES-1];
    wire [LANES-1:0] recovery_keep [0:1];
    wire [ROB_ENTRIES*(GW+1)-1:0] live_rows;
    wire normal=!reset_i && !flush_i && !hold_i && !recovery_i;
    // At full occupancy read_slot==write_slot. The old head is consumed
    // before this edge; nonblocking writes replace it as the new tail. The
    // existing pop-then-push validity priority deliberately makes push win.
    assign ready_o=normal && (count<2 ||
        ((FULL_REPLACE!=0) && count==2 && replace_credit_i));
    wire push=(|valid_i) && ready_o;
    wire pop=normal && count!=0 && consume_i;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-recovery_head_i;
    genvar rob_row,row,lane,word;
    generate for(rob_row=0;rob_row<ROB_ENTRIES;rob_row=rob_row+1) begin:g_live_row
        assign live_rows[rob_row*(GW+1) +: GW+1]={rob_valid_i[rob_row],rob_generation_i[rob_row*GW +: GW]};
    end endgenerate
    localparam integer OUTPUT_WORDS=(PAYLOAD_WIDTH+TAG_WIDTH+15)/16;
    wire [LANES*OUTPUT_WORDS-1:0] read_views;
    rv32_frequency_control_tree #(.LEAVES(LANES*OUTPUT_WORDS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    generate
        for(row=0;row<2;row=row+1) begin:g_row
            for(lane=0;lane<LANES;lane=lane+1) begin:g_lane
                wire [TAG_WIDTH-1:0] tag=tags[row*LANES+lane];
                wire [SW-1:0] slot=tag[3 +: SW];
                wire [SW-1:0] age=slot-recovery_head_i;
                wire [GW:0] live;
                rv32_frequency_array_read #(.WIDTH(GW+1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) live_reader (
                    .rows_i(live_rows),.index_i(slot),.value_o(live));
                assign recovery_keep[row][lane]=valids[row][lane] && tag[0] &&
                    live[GW] && tag[3+SW +: GW]==live[0 +: GW] &&
                    age<branch_age && age<recovery_occupancy_i;
                rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH+PAYLOAD_WIDTH)) packet_owner (
                    .clk_i(clk_i),.write_i(push && write_slot==row && valid_i[lane]),
                    .data_i({tag_i[lane*TAG_WIDTH +: TAG_WIDTH],data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]}),
                    .data_o({tags[row*LANES+lane],payloads[row*LANES+lane]}));
            end
        end
        for(lane=0;lane<LANES;lane=lane+1) begin:g_output
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] selected;
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] first={tags[lane],payloads[lane]};
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] second={tags[LANES+lane],payloads[LANES+lane]};
            for(word=0;word<OUTPUT_WORDS;word=word+1) begin:g_word
                localparam integer LOW=16*word;
                localparam integer BITS=TAG_WIDTH+PAYLOAD_WIDTH-LOW>=16?16:TAG_WIDTH+PAYLOAD_WIDTH-LOW;
                assign selected[LOW +: BITS]=read_views[lane*OUTPUT_WORDS+word]?
                    second[LOW +: BITS]:first[LOW +: BITS];
            end
            assign {tag_o[lane*TAG_WIDTH +: TAG_WIDTH],data_o[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]}=selected;
            assign valid_o[lane]=normal && count!=0 && (read_slot?valids[1][lane]:valids[0][lane]);
        end
    endgenerate
    wire keep_first=|recovery_keep[read_slot];
    wire keep_second=(count==2) && (|recovery_keep[!read_slot]);
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            count<=0;read_slot<=0;write_slot<=0;valids[0]<=0;valids[1]<=0;
        end else if(recovery_i) begin
            valids[0]<=recovery_keep[0];valids[1]<=recovery_keep[1];
            if(count==0 || (!keep_first && !keep_second)) begin
                count<=0;read_slot<=0;write_slot<=0;valids[0]<=0;valids[1]<=0;
            end else if(keep_first && keep_second) begin
                count<=2;
            end else if(keep_first) begin
                count<=1;write_slot<=!read_slot;valids[!read_slot]<=0;
            end else begin
                count<=1;read_slot<=!read_slot;write_slot<=read_slot;valids[read_slot]<=0;
            end
        end else if(!hold_i) begin
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:count<=count;
            endcase
            if(pop) begin valids[read_slot]<=0;read_slot<=!read_slot;end
            if(push) begin valids[write_slot]<=valid_i;write_slot<=!write_slot;end
        end
    end
endmodule
