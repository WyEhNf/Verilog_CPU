`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parameterized RV32IM out-of-order top-level. Frontend bundles are decoded
// lane-wise and a contiguous prefix is dispatched to the backend each cycle.
module cpu_core #(
    parameter integer FE_WIDTH = `RV32IM_FE_WIDTH_DEFAULT,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT
) (
    input  wire       clk,
    input  wire       reset,
    output wire       halted,
    output wire       error,
    output wire [7:0] return_value,
    output reg  [31:0] cycles,
    output reg  [31:0] instret,
    output wire        mem_i_req_valid,
    input  wire        mem_i_req_ready,
    output wire [31:0] mem_i_req_line_addr,
    output wire [7:0]  mem_i_req_id,
    input  wire        mem_i_resp_valid,
    output wire        mem_i_resp_ready,
    input  wire [31:0] mem_i_resp_line_addr,
    input  wire [127:0] mem_i_resp_data,
    input  wire [7:0]  mem_i_resp_id,
    input  wire        mem_i_resp_error,
    output wire        mem_d_req_valid,
    input  wire        mem_d_req_ready,
    output wire        mem_d_req_write,
    output wire [31:0] mem_d_req_line_addr,
    output wire [127:0] mem_d_req_wdata,
    output wire [15:0] mem_d_req_wmask,
    output wire [7:0]  mem_d_req_id,
    input  wire        mem_d_resp_valid,
    output wire        mem_d_resp_ready,
    input  wire [31:0] mem_d_resp_line_addr,
    input  wire [127:0] mem_d_resp_data,
    input  wire [7:0]  mem_d_resp_id,
    input  wire        mem_d_resp_error
);
    localparam integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH;
    localparam integer PACKET_WIDTH = `RV32IM_FETCH_PACKET_WIDTH;
    localparam integer DISPATCH_LANES = (FE_WIDTH < BE_WIDTH) ? FE_WIDTH : BE_WIDTH;

    initial begin
        if ((FE_WIDTH != 1) && (FE_WIDTH != 2) && (FE_WIDTH != 4)) begin
            $display("ERROR: invalid FE_WIDTH=%0d; expected 1, 2, or 4", FE_WIDTH);
            $finish;
        end
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if ((ROB_ENTRIES < 2) || ((ROB_ENTRIES & (ROB_ENTRIES - 1)) != 0)) begin
            $display("ERROR: invalid ROB_ENTRIES=%0d; expected a power of two", ROB_ENTRIES);
            $finish;
        end
    end

    wire if_req_valid, if_req_ready;
    wire [31:0] if_req_pc;
    wire [EPOCH_WIDTH-1:0] if_req_epoch;
    wire if_resp_valid, if_resp_ready, if_resp_error;
    wire [31:0] if_resp_pc, if_resp_line_addr;
    wire [127:0] if_resp_line_data;
    wire [EPOCH_WIDTH-1:0] if_resp_epoch;
    wire [FE_WIDTH-1:0] fetch_valid, fetch_ready;
    wire [FE_WIDTH*PACKET_WIDTH-1:0] fetch_packet;
    wire [EPOCH_WIDTH-1:0] frontend_epoch;
    wire frontend_frozen, frontend_event_fetch, frontend_event_redirect, frontend_event_stall;
    wire redirect_valid;
    wire [31:0] redirect_pc;
    wire [3:0] redirect_epoch;
    wire branch_feedback_valid, branch_feedback_taken, branch_feedback_pred_taken;
    wire [31:0] branch_feedback_pc, branch_feedback_target, branch_feedback_pred_target;
    wire [1:0] branch_feedback_kind;

    wire pred_taken, pred_btb_hit;
    wire [31:0] pred_target;
    wire [1:0] pred_kind;
    wire [5:0] pred_bht_index;
    wire [3:0] pred_btb_index;
    wire [1:0] pred_counter;
    wire [31:0] pred_count, pred_correct;
    reg [31:0] predictor_query_inst;
    reg [FE_WIDTH-1:0] pred_taken_bus, pred_btb_hit_bus;
    reg [FE_WIDTH*32-1:0] pred_target_bus;
    reg [FE_WIDTH*2-1:0] pred_kind_bus;

    always @* begin
        case (if_resp_pc[3:2])
            2'd0: predictor_query_inst = if_resp_line_data[31:0];
            2'd1: predictor_query_inst = if_resp_line_data[63:32];
            2'd2: predictor_query_inst = if_resp_line_data[95:64];
            default: predictor_query_inst = if_resp_line_data[127:96];
        endcase
        pred_taken_bus = {FE_WIDTH{1'b0}};
        pred_btb_hit_bus = {FE_WIDTH{1'b0}};
        pred_target_bus = {FE_WIDTH*32{1'b0}};
        pred_kind_bus = {FE_WIDTH*2{1'b0}};
        pred_taken_bus[0] = pred_taken;
        pred_btb_hit_bus[0] = pred_btb_hit;
        pred_target_bus[31:0] = pred_target;
        pred_kind_bus[1:0] = pred_kind;
    end

    rv32_branch_predictor predictor (
        .clk_i(clk), .reset_i(reset), .query_valid_i(if_resp_valid),
        .query_pc_i(if_resp_pc), .query_inst_i(predictor_query_inst),
        .pred_taken_o(pred_taken), .pred_target_o(pred_target),
        .pred_kind_o(pred_kind), .pred_btb_hit_o(pred_btb_hit),
         .pred_bht_index_o(pred_bht_index), .pred_btb_index_o(pred_btb_index),
         .pred_counter_o(pred_counter), .feedback_valid_i(branch_feedback_valid),
         .feedback_pc_i(branch_feedback_pc), .feedback_kind_i(branch_feedback_kind),
         .feedback_taken_i(branch_feedback_taken), .feedback_target_i(branch_feedback_target),
         .feedback_pred_taken_i(branch_feedback_pred_taken), .feedback_pred_target_i(branch_feedback_pred_target),
        .prediction_count_o(pred_count), .correct_count_o(pred_correct)
    );

    rv32_fetch_frontend #(.FE_WIDTH(FE_WIDTH)) frontend (
        .clk_i(clk), .reset_i(reset), .redirect_valid_i(redirect_valid),
        .redirect_pc_i(redirect_pc), .redirect_epoch_i(redirect_epoch),
        .stop_i(halted), .error_i(error), .if_req_valid_o(if_req_valid),
        .if_req_ready_i(if_req_ready), .if_req_pc_o(if_req_pc),
        .if_req_epoch_o(if_req_epoch), .if_resp_valid_i(if_resp_valid),
        .if_resp_ready_o(if_resp_ready), .if_resp_pc_i(if_resp_pc),
        .if_resp_line_addr_i(if_resp_line_addr), .if_resp_line_data_i(if_resp_line_data),
        .if_resp_epoch_i(if_resp_epoch), .if_resp_error_i(if_resp_error),
        .if_resp_pred_taken_i(pred_taken_bus), .if_resp_pred_target_i(pred_target_bus),
        .if_resp_pred_kind_i(pred_kind_bus), .if_resp_pred_btb_hit_i(pred_btb_hit_bus),
        .fetch_valid_o(fetch_valid), .fetch_ready_i(fetch_ready),
        .fetch_packet_o(fetch_packet), .current_epoch_o(frontend_epoch),
        .frozen_o(frontend_frozen), .event_fetch_o(frontend_event_fetch),
        .event_redirect_o(frontend_event_redirect), .event_stall_o(frontend_event_stall)
    );

    wire ic_mem_req_valid, ic_mem_req_ready, ic_mem_resp_valid, ic_mem_resp_ready, ic_mem_resp_error;
    wire [31:0] ic_mem_req_line_addr, ic_mem_resp_line_addr;
    wire [7:0] ic_mem_req_id, ic_mem_resp_id;
    wire [127:0] ic_mem_resp_data;
    wire ic_event_request, ic_event_hit, ic_event_miss, ic_event_refill, ic_event_stall;
    rv32_icache icache (
        .clk_i(clk), .reset_i(reset), .current_epoch_i(frontend_epoch),
        .if_req_valid_i(if_req_valid), .if_req_ready_o(if_req_ready), .if_req_pc_i(if_req_pc),
        .if_req_epoch_i(if_req_epoch), .if_resp_valid_o(if_resp_valid),
        .if_resp_ready_i(if_resp_ready), .if_resp_pc_o(if_resp_pc),
        .if_resp_line_addr_o(if_resp_line_addr), .if_resp_line_data_o(if_resp_line_data),
        .if_resp_epoch_o(if_resp_epoch), .if_resp_error_o(if_resp_error),
        .mem_req_valid_o(ic_mem_req_valid), .mem_req_ready_i(ic_mem_req_ready),
        .mem_req_line_addr_o(ic_mem_req_line_addr), .mem_req_id_o(ic_mem_req_id),
        .mem_resp_valid_i(ic_mem_resp_valid), .mem_resp_ready_o(ic_mem_resp_ready),
        .mem_resp_line_addr_i(ic_mem_resp_line_addr), .mem_resp_data_i(ic_mem_resp_data),
        .mem_resp_id_i(ic_mem_resp_id), .mem_resp_error_i(ic_mem_resp_error),
        .event_request_o(ic_event_request), .event_hit_o(ic_event_hit),
        .event_miss_o(ic_event_miss), .event_refill_o(ic_event_refill), .event_stall_o(ic_event_stall)
    );

    wire dcache_req_valid, dcache_req_ready, dcache_req_load, dcache_req_store, dcache_req_unsigned;
    wire [31:0] dcache_req_addr;
    wire [1:0] dcache_req_size;
    wire [15:0] dcache_req_mask, dcache_req_rob_tag, dcache_req_lsq_tag;
    wire [127:0] dcache_req_wdata;
    wire dcache_resp_valid, dcache_resp_ready, dcache_resp_line_valid, dcache_resp_error;
    wire [15:0] dcache_resp_lsq_tag;
    wire [31:0] dcache_resp_addr, dcache_resp_word;
    wire [127:0] dcache_resp_line;
    wire dcache_store_ack_valid, dcache_store_ack_error;
    wire [15:0] dcache_store_ack_lsq_tag;
    wire dc_mem_req_valid, dc_mem_req_ready, dc_mem_req_write, dc_mem_resp_valid, dc_mem_resp_ready, dc_mem_resp_error;
    wire [31:0] dc_mem_req_line_addr, dc_mem_resp_line_addr;
    wire [127:0] dc_mem_req_wdata, dc_mem_resp_data;
    wire [15:0] dc_mem_req_wmask;
    wire [7:0] dc_mem_req_id, dc_mem_resp_id;
    wire dc_event_request, dc_event_hit, dc_event_miss, dc_event_refill, dc_event_writeback, dc_event_stall;
    rv32_dcache dcache (
        // LSQ generations reject wrong-path responses while retaining older
        // loads across a redirect.  The cache itself has no ROB-age context.
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0), .dcache_req_valid_i(dcache_req_valid),
        .dcache_req_ready_o(dcache_req_ready), .dcache_req_is_load_i(dcache_req_load),
        .dcache_req_is_store_i(dcache_req_store), .dcache_req_addr_i(dcache_req_addr),
        .dcache_req_size_i(dcache_req_size), .dcache_req_unsigned_i(dcache_req_unsigned),
        .dcache_req_mask_i(dcache_req_mask), .dcache_req_wdata_i(dcache_req_wdata),
        .dcache_req_rob_tag_i(dcache_req_rob_tag), .dcache_req_lsq_tag_i(dcache_req_lsq_tag),
        .dcache_resp_valid_o(dcache_resp_valid), .dcache_resp_ready_i(dcache_resp_ready),
        .dcache_resp_lsq_tag_o(dcache_resp_lsq_tag), .dcache_resp_addr_o(dcache_resp_addr),
        .dcache_resp_line_data_o(dcache_resp_line), .dcache_resp_word_data_o(dcache_resp_word),
        .dcache_resp_line_valid_o(dcache_resp_line_valid), .dcache_resp_error_o(dcache_resp_error),
        .dcache_store_ack_valid_o(dcache_store_ack_valid), .dcache_store_ack_ready_i(1'b1),
        .dcache_store_ack_lsq_tag_o(dcache_store_ack_lsq_tag), .dcache_store_ack_error_o(dcache_store_ack_error),
        .mem_req_valid_o(dc_mem_req_valid), .mem_req_ready_i(dc_mem_req_ready),
        .mem_req_write_o(dc_mem_req_write), .mem_req_line_addr_o(dc_mem_req_line_addr),
        .mem_req_wdata_o(dc_mem_req_wdata), .mem_req_wmask_o(dc_mem_req_wmask),
        .mem_req_id_o(dc_mem_req_id), .mem_resp_valid_i(dc_mem_resp_valid),
        .mem_resp_ready_o(dc_mem_resp_ready), .mem_resp_line_addr_i(dc_mem_resp_line_addr),
        .mem_resp_data_i(dc_mem_resp_data), .mem_resp_id_i(dc_mem_resp_id),
        .mem_resp_error_i(dc_mem_resp_error), .event_request_o(dc_event_request),
        .event_hit_o(dc_event_hit), .event_miss_o(dc_event_miss), .event_refill_o(dc_event_refill),
        .event_writeback_o(dc_event_writeback), .event_stall_o(dc_event_stall)
    );

    rv32_memory_bridge memory_bridge (
        .clk_i(clk), .reset_i(reset), .cache_i_req_valid_i(ic_mem_req_valid),
        .cache_i_req_ready_o(ic_mem_req_ready), .cache_i_req_line_addr_i(ic_mem_req_line_addr),
        .cache_i_req_id_i(ic_mem_req_id), .cache_i_resp_valid_o(ic_mem_resp_valid),
        .cache_i_resp_ready_i(ic_mem_resp_ready), .cache_i_resp_line_addr_o(ic_mem_resp_line_addr),
        .cache_i_resp_data_o(ic_mem_resp_data), .cache_i_resp_id_o(ic_mem_resp_id),
        .cache_i_resp_error_o(ic_mem_resp_error), .cache_d_req_valid_i(dc_mem_req_valid),
        .cache_d_req_ready_o(dc_mem_req_ready), .cache_d_req_write_i(dc_mem_req_write),
        .cache_d_req_line_addr_i(dc_mem_req_line_addr), .cache_d_req_wdata_i(dc_mem_req_wdata),
        .cache_d_req_wmask_i(dc_mem_req_wmask), .cache_d_req_id_i(dc_mem_req_id),
        .cache_d_resp_valid_o(dc_mem_resp_valid), .cache_d_resp_ready_i(dc_mem_resp_ready),
        .cache_d_resp_line_addr_o(dc_mem_resp_line_addr), .cache_d_resp_data_o(dc_mem_resp_data),
        .cache_d_resp_id_o(dc_mem_resp_id), .cache_d_resp_error_o(dc_mem_resp_error),
        .mem_i_req_valid_o(mem_i_req_valid), .mem_i_req_ready_i(mem_i_req_ready),
        .mem_i_req_line_addr_o(mem_i_req_line_addr), .mem_i_req_id_o(mem_i_req_id),
        .mem_i_resp_valid_i(mem_i_resp_valid), .mem_i_resp_ready_o(mem_i_resp_ready),
        .mem_i_resp_line_addr_i(mem_i_resp_line_addr), .mem_i_resp_data_i(mem_i_resp_data),
        .mem_i_resp_id_i(mem_i_resp_id), .mem_i_resp_error_i(mem_i_resp_error),
        .mem_d_req_valid_o(mem_d_req_valid), .mem_d_req_ready_i(mem_d_req_ready),
        .mem_d_req_write_o(mem_d_req_write), .mem_d_req_line_addr_o(mem_d_req_line_addr),
        .mem_d_req_wdata_o(mem_d_req_wdata), .mem_d_req_wmask_o(mem_d_req_wmask),
        .mem_d_req_id_o(mem_d_req_id), .mem_d_resp_valid_i(mem_d_resp_valid),
        .mem_d_resp_ready_o(mem_d_resp_ready), .mem_d_resp_line_addr_i(mem_d_resp_line_addr),
        .mem_d_resp_data_i(mem_d_resp_data), .mem_d_resp_id_i(mem_d_resp_id),
        .mem_d_resp_error_i(mem_d_resp_error), .event_i_mem_request_o(),
        .event_d_mem_read_o(), .event_d_mem_write_o()
    );

    wire [BE_WIDTH-1:0] trace_valid, trace_ready;
    wire [BE_WIDTH*PACKET_WIDTH-1:0] trace_packet;
    wire [BE_WIDTH*32-1:0] trace_pc, trace_inst;
    wire [BE_WIDTH-1:0] trace_pred_taken;
    wire [BE_WIDTH*32-1:0] trace_pred_target;
    wire [BE_WIDTH*2-1:0] trace_pred_kind;
    wire [BE_WIDTH-1:0] dec_legal, dec_rd_we, dec_rs1_used, dec_rs2_used;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] dec_op, backend_op;
    wire [BE_WIDTH*4-1:0] dec_class;
    wire [BE_WIDTH*5-1:0] dec_rd, dec_rs1, dec_rs2, backend_rs1, backend_rs2;
    wire [BE_WIDTH*32-1:0] dec_imm;
    wire [BE_WIDTH-1:0] dec_load, dec_store, dec_branch, dec_jump, dec_serialize;
    wire [BE_WIDTH*2-1:0] dec_mem_size;
    wire [BE_WIDTH-1:0] dec_mem_unsigned;
    wire [BE_WIDTH*4-1:0] dec_mem_base_mask;
    wire [BE_WIDTH-1:0] dec_jalr_clear_lsb, is_halt_trace, backend_rs1_used;

    genvar frontend_lane;
    generate
        for (frontend_lane = 0; frontend_lane < FE_WIDTH; frontend_lane = frontend_lane + 1) begin : g_frontend_ready
            if (frontend_lane < BE_WIDTH)
                assign fetch_ready[frontend_lane] = trace_ready[frontend_lane];
            else
                assign fetch_ready[frontend_lane] = 1'b0;
        end
    endgenerate

    genvar decode_lane;
    generate
        for (decode_lane = 0; decode_lane < BE_WIDTH; decode_lane = decode_lane + 1) begin : g_decode
            if (decode_lane < FE_WIDTH) begin : g_has_frontend_lane
                assign trace_valid[decode_lane] = fetch_valid[decode_lane];
                assign trace_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH] =
                    fetch_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH];
            end else begin : g_no_frontend_lane
                assign trace_valid[decode_lane] = 1'b0;
                assign trace_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH] =
                    {PACKET_WIDTH{1'b0}};
            end
            assign trace_pc[decode_lane*32 +: 32] =
                trace_packet[decode_lane*PACKET_WIDTH +: 32];
            assign trace_inst[decode_lane*32 +: 32] =
                trace_packet[decode_lane*PACKET_WIDTH + 32 +: 32];
            assign trace_pred_taken[decode_lane] =
                trace_packet[decode_lane*PACKET_WIDTH + 64];
            assign trace_pred_target[decode_lane*32 +: 32] =
                trace_packet[decode_lane*PACKET_WIDTH + 65 +: 32];
            assign trace_pred_kind[decode_lane*2 +: 2] =
                trace_packet[decode_lane*PACKET_WIDTH + 97 +: 2];

            rv32im_decoder decoder (
                .inst_i(trace_inst[decode_lane*32 +: 32]),
                .legal_o(dec_legal[decode_lane]),
                .op_o(dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH]),
                .class_o(dec_class[decode_lane*4 +: 4]),
                .rd_o(dec_rd[decode_lane*5 +: 5]),
                .rs1_o(dec_rs1[decode_lane*5 +: 5]),
                .rs2_o(dec_rs2[decode_lane*5 +: 5]),
                .rd_we_o(dec_rd_we[decode_lane]),
                .rs1_used_o(dec_rs1_used[decode_lane]),
                .rs2_used_o(dec_rs2_used[decode_lane]),
                .imm_o(dec_imm[decode_lane*32 +: 32]),
                .is_load_o(dec_load[decode_lane]),
                .is_store_o(dec_store[decode_lane]),
                .is_branch_o(dec_branch[decode_lane]),
                .is_jump_o(dec_jump[decode_lane]),
                .is_serialize_o(dec_serialize[decode_lane]),
                .mem_size_o(dec_mem_size[decode_lane*2 +: 2]),
                .mem_unsigned_o(dec_mem_unsigned[decode_lane]),
                .mem_base_mask_o(dec_mem_base_mask[decode_lane*4 +: 4]),
                .jalr_clear_lsb_o(dec_jalr_clear_lsb[decode_lane])
            );

            // HALT commits the live architectural a0 value through the normal
            // ALU/read path while retaining precise sentinel classification.
            assign is_halt_trace[decode_lane] =
                (dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_HALT);
            assign backend_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] =
                is_halt_trace[decode_lane] ? `RV32IM_OP_ADD :
                dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];
            assign backend_rs1[decode_lane*5 +: 5] =
                is_halt_trace[decode_lane] ? 5'd10 : dec_rs1[decode_lane*5 +: 5];
            assign backend_rs2[decode_lane*5 +: 5] =
                is_halt_trace[decode_lane] ? 5'd0 : dec_rs2[decode_lane*5 +: 5];
            assign backend_rs1_used[decode_lane] =
                is_halt_trace[decode_lane] ? 1'b1 : dec_rs1_used[decode_lane];
        end
    endgenerate

    wire [BE_WIDTH-1:0] commit_valid, commit_rd_we, commit_is_store;
    wire commit_ready;
    wire [BE_WIDTH*32-1:0] commit_pc, commit_inst, commit_value, commit_store_addr;
    wire [BE_WIDTH*5-1:0] commit_rd;
    wire [BE_WIDTH*16-1:0] commit_store_mask, commit_tag;
    wire [BE_WIDTH*128-1:0] commit_store_data;
    assign commit_ready = 1'b1;
    rv32_backend_joint #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .ROB_ENTRIES(ROB_ENTRIES)) backend (
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0), .trace_valid_i(trace_valid),
        .trace_ready_o(trace_ready), .trace_pc_i(trace_pc), .trace_inst_i(trace_inst),
        .trace_op_i(backend_op), .trace_imm_i(dec_imm), .trace_rd_i(dec_rd), .trace_rs1_i(backend_rs1),
        .trace_rs2_i(backend_rs2), .trace_rd_we_i(dec_rd_we), .trace_rs1_used_i(backend_rs1_used),
        .trace_rs2_used_i(dec_rs2_used & ~is_halt_trace), .trace_is_load_i(dec_load), .trace_is_store_i(dec_store),
        .trace_is_branch_i(dec_branch | dec_jump), .trace_is_halt_i(is_halt_trace),
        .trace_is_error_i(trace_valid & ~dec_legal), .trace_mem_size_i(dec_mem_size),
        .trace_mem_unsigned_i(dec_mem_unsigned), .trace_store_data_i({BE_WIDTH*128{1'b0}}),
        .trace_pred_taken_i(trace_pred_taken), .trace_pred_target_i(trace_pred_target),
        .trace_pred_kind_i(trace_pred_kind), .dcache_req_valid_o(dcache_req_valid),
        .dcache_req_ready_i(dcache_req_ready), .dcache_req_is_load_o(dcache_req_load),
        .dcache_req_is_store_o(dcache_req_store), .dcache_req_addr_o(dcache_req_addr),
        .dcache_req_size_o(dcache_req_size), .dcache_req_unsigned_o(dcache_req_unsigned),
        .dcache_req_mask_o(dcache_req_mask), .dcache_req_wdata_o(dcache_req_wdata),
        .dcache_req_rob_tag_o(dcache_req_rob_tag), .dcache_req_lsq_tag_o(dcache_req_lsq_tag),
        .dcache_resp_valid_i(dcache_resp_valid), .dcache_resp_ready_o(dcache_resp_ready),
        .dcache_resp_lsq_tag_i(dcache_resp_lsq_tag), .dcache_resp_addr_i(dcache_resp_addr),
        .dcache_resp_line_data_i(dcache_resp_line), .dcache_resp_word_data_i(dcache_resp_word),
        .dcache_resp_line_valid_i(dcache_resp_line_valid), .dcache_resp_error_i(dcache_resp_error),
        .dcache_store_ack_valid_i(dcache_store_ack_valid), .dcache_store_ack_lsq_tag_i(dcache_store_ack_lsq_tag),
        .dcache_store_ack_error_i(dcache_store_ack_error), .commit_ready_i(commit_ready),
        .commit_valid_o(commit_valid), .commit_pc_o(commit_pc), .commit_inst_o(commit_inst),
        .commit_rd_o(commit_rd), .commit_rd_we_o(commit_rd_we), .commit_value_o(commit_value),
        .commit_is_store_o(commit_is_store), .commit_store_addr_o(commit_store_addr),
        .commit_store_mask_o(commit_store_mask), .commit_store_data_o(commit_store_data),
         .commit_tag_o(commit_tag), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc),
         .redirect_epoch_o(redirect_epoch), .halted_o(halted), .error_o(error),
         .return_value_o(return_value), .branch_feedback_valid_o(branch_feedback_valid),
         .branch_feedback_pc_o(branch_feedback_pc), .branch_feedback_kind_o(branch_feedback_kind),
         .branch_feedback_taken_o(branch_feedback_taken), .branch_feedback_target_o(branch_feedback_target),
         .branch_feedback_pred_taken_o(branch_feedback_pred_taken), .branch_feedback_pred_target_o(branch_feedback_pred_target)
    );

    rv32_cache_stats stats (
        .clk_i(clk), .reset_i(reset), .i_event_request_i(ic_event_request), .i_event_hit_i(ic_event_hit),
        .i_event_miss_i(ic_event_miss), .i_event_refill_i(ic_event_refill), .i_event_stall_i(ic_event_stall),
        .d_event_request_i(dc_event_request), .d_event_hit_i(dc_event_hit), .d_event_miss_i(dc_event_miss),
        .d_event_refill_i(dc_event_refill), .d_event_writeback_i(dc_event_writeback), .d_event_stall_i(dc_event_stall),
        .i_mem_request_fire_i(1'b0), .d_mem_read_fire_i(1'b0), .d_mem_write_fire_i(1'b0),
        .i_request_count_o(), .i_hit_count_o(), .i_miss_count_o(), .i_refill_count_o(), .i_stall_count_o(),
        .d_request_count_o(), .d_hit_count_o(), .d_miss_count_o(), .d_refill_count_o(), .d_writeback_count_o(),
        .d_stall_count_o(), .i_mem_request_count_o(), .d_mem_read_count_o(), .d_mem_write_count_o()
    );

    function [31:0] commit_popcount;
        input [BE_WIDTH-1:0] bits;
        integer lane;
        begin
            commit_popcount = 32'd0;
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                if (bits[lane]) commit_popcount = commit_popcount + 32'd1;
        end
    endfunction

    always @(posedge clk) begin
        if (reset) begin
            cycles <= 32'd0;
            instret <= 32'd0;
        end else begin
            cycles <= cycles + 32'd1;
            if ((|commit_valid) && commit_ready)
                instret <= instret + commit_popcount(commit_valid);
        end
    end
endmodule
