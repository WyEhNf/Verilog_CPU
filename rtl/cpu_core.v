`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parameterized RV32IM out-of-order top-level. Frontend bundles are decoded
// lane-wise and a contiguous prefix is dispatched to the backend each cycle.
module cpu_core #(
    parameter integer FE_WIDTH = `RV32IM_FE_WIDTH_DEFAULT,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer RS_ENTRIES = 8,
    parameter integer LSQ_ENTRIES = 8,
    parameter integer INT_ISSUE_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer CDB_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer ENABLE_CACHE_STATS = 0,
    parameter integer ENABLE_CACHES = 1,
    parameter integer ICACHE_FAST_HIT = 1,
    parameter integer ICACHE_COMBINATIONAL_HIT = 0,
    parameter integer ICACHE_PREFETCH = 1,
    parameter integer ICACHE_MSHRS = 8,
    parameter integer DCACHE_MSHRS = 4,
    parameter integer ENABLE_PREDICTOR = 1,
    parameter integer FETCH_QUEUE_DEPTH = 16,
    parameter integer MUL_IMPL = 0,
    parameter integer SHIFT_IMPL = 0,
    parameter integer PHYS_TAG_IMPL = 0,
    parameter integer CHECKPOINT_IMPL = 0,
    parameter integer STORE_BUFFERED_RETIRE = 1,
    parameter integer COMPLETION_BYPASS = 0,
    parameter integer SERIAL_BACKEND = 0,
    parameter integer GENERATION_WIDTH = `RV32IM_ROB_GENERATION_WIDTH,
    parameter integer COMPLETION_DEPTH = (BE_WIDTH <= 1) ? 4 :
                                         ((BE_WIDTH == 2) ? 8 : 16)
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
    localparam integer ROB_TAG_WIDTH = 1 + 2 +
        ((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) +
        GENERATION_WIDTH;

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

    wire [FE_WIDTH-1:0] pred_taken_bus, pred_btb_hit_bus;
    wire [FE_WIDTH*32-1:0] pred_target_bus;
    wire [FE_WIDTH*2-1:0] pred_kind_bus;
    wire [FE_WIDTH-1:0] pred_taken_raw_bus, pred_btb_hit_raw_bus;
    wire [FE_WIDTH*32-1:0] pred_target_raw_bus;
    wire [FE_WIDTH*2-1:0] pred_kind_raw_bus;
    wire [FE_WIDTH*6-1:0] pred_bht_index_bus;
    wire [FE_WIDTH*4-1:0] pred_btb_index_bus;
    wire [FE_WIDTH*2-1:0] pred_counter_bus;
    wire [FE_WIDTH*32-1:0] pred_count_bus, pred_correct_bus;
    wire [31:0] pred_count = pred_count_bus[31:0];
    wire [31:0] pred_correct = pred_correct_bus[31:0];

    // Small speculative return-address stack shared by all fetch lanes.  The
    // replicated bimodal/BTB predictors cannot each maintain a coherent RAS
    // because a call and its return may appear in different bundle lanes.
    // Updating here, after the frontend accepts a bundle, keeps one ordered
    // stack for the whole fetch stream at very small area cost.
    reg [31:0] ras_stack [0:3];
    reg [1:0] ras_sp;
    reg [2:0] ras_count;
    reg ras_push;
    reg ras_pop;
    reg [31:0] ras_push_address;
    integer ras_lane;
    integer ras_word_index;
    integer ras_event_found;
    reg [31:0] ras_inst;
    reg [31:0] ras_pc;
    wire [1:0] ras_top_index = ras_sp - 1'b1;
    wire [31:0] ras_target = ras_stack[ras_top_index];

    // Every fetch lane needs a predictor read.  The small predictor state is
    // replicated, while all copies receive identical feedback and therefore
    // remain coherent.  This avoids forcing lanes 1..N to predict not-taken.
    genvar predictor_lane;
    generate
        for (predictor_lane = 0; predictor_lane < FE_WIDTH;
             predictor_lane = predictor_lane + 1) begin : g_predictor
            wire [2:0] query_word_index =
                {1'b0, if_resp_pc[3:2]} + predictor_lane;
            wire query_valid = if_resp_valid && (query_word_index < 3'd4);
            wire [31:0] query_pc = if_resp_pc + (predictor_lane * 32'd4);
            wire [31:0] query_inst =
                if_resp_line_data >> (query_word_index * 32);
            wire query_is_return = (query_inst[6:0] == 7'b1100111) &&
                                   (query_inst[14:12] == 3'b000) &&
                                   (query_inst[11:7] == 5'd0) &&
                                   ((query_inst[19:15] == 5'd1) ||
                                    (query_inst[19:15] == 5'd5)) &&
                                   (query_inst[31:20] == 12'd0);
            wire ras_return_hit = (ENABLE_PREDICTOR != 0) && query_valid &&
                                  query_is_return && (ras_count != 0);

            if (ENABLE_PREDICTOR != 0) begin : g_enabled
            rv32_branch_predictor predictor (
                .clk_i(clk), .reset_i(reset), .query_valid_i(query_valid),
                .query_pc_i(query_pc), .query_inst_i(query_inst),
                .pred_taken_o(pred_taken_raw_bus[predictor_lane]),
                .pred_target_o(pred_target_raw_bus[predictor_lane*32 +: 32]),
                .pred_kind_o(pred_kind_raw_bus[predictor_lane*2 +: 2]),
                .pred_btb_hit_o(pred_btb_hit_raw_bus[predictor_lane]),
                .pred_bht_index_o(pred_bht_index_bus[predictor_lane*6 +: 6]),
                .pred_btb_index_o(pred_btb_index_bus[predictor_lane*4 +: 4]),
                .pred_counter_o(pred_counter_bus[predictor_lane*2 +: 2]),
                .feedback_valid_i(branch_feedback_valid),
                .feedback_pc_i(branch_feedback_pc),
                .feedback_kind_i(branch_feedback_kind),
                .feedback_taken_i(branch_feedback_taken),
                .feedback_target_i(branch_feedback_target),
                .feedback_pred_taken_i(branch_feedback_pred_taken),
                .feedback_pred_target_i(branch_feedback_pred_target),
                .prediction_count_o(pred_count_bus[predictor_lane*32 +: 32]),
                .correct_count_o(pred_correct_bus[predictor_lane*32 +: 32])
            );
            end else begin : g_disabled
                assign pred_taken_raw_bus[predictor_lane] = 1'b0;
                assign pred_target_raw_bus[predictor_lane*32 +: 32] = 32'b0;
                assign pred_kind_raw_bus[predictor_lane*2 +: 2] = `RV32IM_PRED_NONE;
                assign pred_btb_hit_raw_bus[predictor_lane] = 1'b0;
                assign pred_bht_index_bus[predictor_lane*6 +: 6] = 6'b0;
                assign pred_btb_index_bus[predictor_lane*4 +: 4] = 4'b0;
                assign pred_counter_bus[predictor_lane*2 +: 2] = 2'b0;
                assign pred_count_bus[predictor_lane*32 +: 32] = 32'b0;
                assign pred_correct_bus[predictor_lane*32 +: 32] = 32'b0;
            end
            assign pred_taken_bus[predictor_lane] = ras_return_hit ? 1'b1 :
                                                     pred_taken_raw_bus[predictor_lane];
            assign pred_target_bus[predictor_lane*32 +: 32] = ras_return_hit ?
                ras_target : pred_target_raw_bus[predictor_lane*32 +: 32];
            assign pred_kind_bus[predictor_lane*2 +: 2] = ras_return_hit ?
                `RV32IM_PRED_JALR : pred_kind_raw_bus[predictor_lane*2 +: 2];
            assign pred_btb_hit_bus[predictor_lane] = ras_return_hit ? 1'b1 :
                                                       pred_btb_hit_raw_bus[predictor_lane];
        end
    endgenerate

    always @* begin
        ras_push = 1'b0;
        ras_pop = 1'b0;
        ras_push_address = 32'd0;
        ras_event_found = 0;
        ras_word_index = 0;
        ras_inst = 32'd0;
        ras_pc = 32'd0;
        if ((ENABLE_PREDICTOR != 0) && if_resp_valid && if_resp_ready) begin
            for (ras_lane = 0; ras_lane < FE_WIDTH; ras_lane = ras_lane + 1) begin
                ras_word_index = if_resp_pc[3:2] + ras_lane;
                if (!ras_event_found && (ras_word_index < 4)) begin
                    ras_inst = if_resp_line_data >> (ras_word_index * 32);
                    ras_pc = if_resp_pc + (ras_lane * 32'd4);
                    if (((ras_inst[6:0] == 7'b1101111) ||
                         ((ras_inst[6:0] == 7'b1100111) &&
                          (ras_inst[14:12] == 3'b000))) &&
                        ((ras_inst[11:7] == 5'd1) ||
                         (ras_inst[11:7] == 5'd5))) begin
                        ras_push = 1'b1;
                        ras_push_address = ras_pc + 32'd4;
                        ras_event_found = 1;
                    end else if ((ras_inst[6:0] == 7'b1100111) &&
                                 (ras_inst[14:12] == 3'b000) &&
                                 (ras_inst[11:7] == 5'd0) &&
                                 ((ras_inst[19:15] == 5'd1) ||
                                  (ras_inst[19:15] == 5'd5)) &&
                                 (ras_inst[31:20] == 12'd0)) begin
                        if (ras_count != 0)
                            ras_pop = 1'b1;
                        ras_event_found = 1;
                    end else if (pred_taken_bus[ras_lane]) begin
                        // The frontend stops the accepted bundle at the first
                        // predicted-taken control transfer.
                        ras_event_found = 1;
                    end
                end
            end
        end
    end

    integer ras_reset_index;
    always @(posedge clk) begin
        if (reset) begin
            ras_sp <= 2'd0;
            ras_count <= 3'd0;
            for (ras_reset_index = 0; ras_reset_index < 4;
                 ras_reset_index = ras_reset_index + 1)
                ras_stack[ras_reset_index] <= 32'd0;
        end else if (ras_push) begin
            ras_stack[ras_sp] <= ras_push_address;
            ras_sp <= ras_sp + 1'b1;
            if (ras_count < 4)
                ras_count <= ras_count + 1'b1;
        end else if (ras_pop) begin
            ras_sp <= ras_sp - 1'b1;
            ras_count <= ras_count - 1'b1;
        end
    end

    rv32_fetch_frontend #(.FE_WIDTH(FE_WIDTH), .FQ_DEPTH(FETCH_QUEUE_DEPTH)) frontend (
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
    wire dcache_req_valid, dcache_req_ready, dcache_req_load, dcache_req_store, dcache_req_unsigned;
    wire [31:0] dcache_req_addr;
    wire [1:0] dcache_req_size;
    wire [15:0] dcache_req_mask;
    wire [ROB_TAG_WIDTH-1:0] dcache_req_rob_tag, dcache_req_lsq_tag;
    wire [127:0] dcache_req_wdata;
    wire dcache_resp_valid, dcache_resp_ready, dcache_resp_line_valid, dcache_resp_error;
    wire [ROB_TAG_WIDTH-1:0] dcache_resp_lsq_tag;
    wire [31:0] dcache_resp_addr, dcache_resp_word;
    wire [127:0] dcache_resp_line;
    wire dcache_store_ack_valid, dcache_store_ack_error;
    wire [ROB_TAG_WIDTH-1:0] dcache_store_ack_lsq_tag;
    wire dc_mem_req_valid, dc_mem_req_ready, dc_mem_req_write, dc_mem_resp_valid, dc_mem_resp_ready, dc_mem_resp_error;
    wire [31:0] dc_mem_req_line_addr, dc_mem_resp_line_addr;
    wire [127:0] dc_mem_req_wdata, dc_mem_resp_data;
    wire [15:0] dc_mem_req_wmask;
    wire [7:0] dc_mem_req_id, dc_mem_resp_id;
    wire dc_event_request, dc_event_hit, dc_event_miss, dc_event_refill, dc_event_writeback, dc_event_stall;
    wire dcache_debug_s0_valid, dcache_debug_s0_store;
    wire dcache_debug_s1_valid, dcache_debug_s1_store;
    wire dcache_debug_s2_valid, dcache_debug_s2_store, dcache_debug_s2_hit;
    wire dcache_debug_mshr_valid, dcache_debug_ack_valid, dcache_debug_resp_valid;
    generate
    if (ENABLE_CACHES != 0) begin : g_cached_memory
    if (ICACHE_MSHRS > 1) begin : g_nonblocking_icache
    rv32_icache_nonblocking #(
        .MSHR_ENTRIES(ICACHE_MSHRS),
        .NEXT_LINE_PREFETCH(ICACHE_PREFETCH),
        // Keep the initial stream conservative.  Filling every MSHR before
        // the first line has exposed its control flow leaves the external
        // queue full of uncancellable wrong-path requests at a taken jump.
        // The I-cache's sliding window replenishes this credit as sequential
        // demand advances, so long straight-line regions still stream.
        .PREFETCH_DISTANCE((ICACHE_MSHRS > 4) ? 3 :
                           ((ICACHE_MSHRS > 1) ? (ICACHE_MSHRS-1) : 1))
    ) icache (
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
    end else begin : g_blocking_icache
    rv32_icache #(
        .FAST_HIT(ICACHE_FAST_HIT),
        .COMBINATIONAL_HIT(ICACHE_COMBINATIONAL_HIT),
        .NEXT_LINE_PREFETCH(ICACHE_PREFETCH)
    ) icache (
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
    end

    if (DCACHE_MSHRS > 1) begin : g_nonblocking_dcache
    rv32_dcache_nonblocking #(
        .TAG_WIDTH(ROB_TAG_WIDTH), .MSHR_ENTRIES(DCACHE_MSHRS)
    ) dcache (
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
    end else begin : g_blocking_dcache
    rv32_dcache #(.TAG_WIDTH(ROB_TAG_WIDTH)) dcache (
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
    end

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
    // Stable diagnostic aliases avoid testbench dependence on generate paths.
    assign dcache_debug_s0_valid = 1'b0;
    assign dcache_debug_s0_store = 1'b0;
    assign dcache_debug_s1_valid = 1'b0;
    assign dcache_debug_s1_store = 1'b0;
    assign dcache_debug_s2_valid = 1'b0;
    assign dcache_debug_s2_store = 1'b0;
    assign dcache_debug_s2_hit = 1'b0;
    assign dcache_debug_mshr_valid = dc_mem_req_valid;
    assign dcache_debug_ack_valid = dcache_store_ack_valid;
    assign dcache_debug_resp_valid = dcache_resp_valid;
    end else begin : g_uncached_memory
        rv32_uncached_memory #(
            .EPOCH_WIDTH(EPOCH_WIDTH), .TAG_WIDTH(ROB_TAG_WIDTH)
        ) uncached_memory (
            .clk_i(clk), .reset_i(reset),
            .if_req_valid_i(if_req_valid), .if_req_ready_o(if_req_ready),
            .if_req_pc_i(if_req_pc), .if_req_epoch_i(if_req_epoch),
            .current_epoch_i(frontend_epoch),
            .if_resp_valid_o(if_resp_valid), .if_resp_ready_i(if_resp_ready),
            .if_resp_pc_o(if_resp_pc), .if_resp_line_addr_o(if_resp_line_addr),
            .if_resp_line_data_o(if_resp_line_data), .if_resp_epoch_o(if_resp_epoch),
            .if_resp_error_o(if_resp_error),
            .d_req_valid_i(dcache_req_valid), .d_req_ready_o(dcache_req_ready),
            .d_req_is_load_i(dcache_req_load), .d_req_is_store_i(dcache_req_store),
            .d_req_addr_i(dcache_req_addr), .d_req_size_i(dcache_req_size),
            .d_req_unsigned_i(dcache_req_unsigned), .d_req_mask_i(dcache_req_mask),
            .d_req_wdata_i(dcache_req_wdata), .d_req_lsq_tag_i(dcache_req_lsq_tag),
            .d_resp_valid_o(dcache_resp_valid), .d_resp_ready_i(dcache_resp_ready),
            .d_resp_lsq_tag_o(dcache_resp_lsq_tag), .d_resp_addr_o(dcache_resp_addr),
            .d_resp_line_data_o(dcache_resp_line), .d_resp_word_data_o(dcache_resp_word),
            .d_resp_line_valid_o(dcache_resp_line_valid), .d_resp_error_o(dcache_resp_error),
            .d_store_ack_valid_o(dcache_store_ack_valid), .d_store_ack_ready_i(1'b1),
            .d_store_ack_lsq_tag_o(dcache_store_ack_lsq_tag),
            .d_store_ack_error_o(dcache_store_ack_error),
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
            .mem_d_resp_error_i(mem_d_resp_error)
        );
        assign ic_mem_req_valid = 1'b0;
        assign ic_mem_req_line_addr = 32'b0;
        assign ic_mem_req_id = 8'b0;
        assign ic_mem_resp_ready = 1'b0;
        assign dc_mem_req_valid = 1'b0;
        assign dc_mem_req_write = 1'b0;
        assign dc_mem_req_line_addr = 32'b0;
        assign dc_mem_req_wdata = 128'b0;
        assign dc_mem_req_wmask = 16'b0;
        assign dc_mem_req_id = 8'b0;
        assign dc_mem_resp_ready = 1'b0;
        assign ic_event_request = if_req_valid && if_req_ready;
        assign ic_event_hit = 1'b0;
        assign ic_event_miss = ic_event_request;
        assign ic_event_refill = if_resp_valid && if_resp_ready;
        assign ic_event_stall = if_req_valid && !if_req_ready;
        assign dc_event_request = dcache_req_valid && dcache_req_ready;
        assign dc_event_hit = 1'b0;
        assign dc_event_miss = dc_event_request;
        assign dc_event_refill = dcache_resp_valid && dcache_resp_ready;
        assign dc_event_writeback = dcache_store_ack_valid;
        assign dc_event_stall = dcache_req_valid && !dcache_req_ready;
        assign dcache_debug_s0_valid = 1'b0;
        assign dcache_debug_s0_store = 1'b0;
        assign dcache_debug_s1_valid = 1'b0;
        assign dcache_debug_s1_store = 1'b0;
        assign dcache_debug_s2_valid = 1'b0;
        assign dcache_debug_s2_store = 1'b0;
        assign dcache_debug_s2_hit = 1'b0;
        assign dcache_debug_mshr_valid = uncached_memory.d_pending;
        assign dcache_debug_ack_valid = dcache_store_ack_valid;
        assign dcache_debug_resp_valid = dcache_resp_valid;
    end
    endgenerate

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
    wire [BE_WIDTH*16-1:0] commit_store_mask;
    wire [BE_WIDTH*ROB_TAG_WIDTH-1:0] commit_tag;
    wire [BE_WIDTH*128-1:0] commit_store_data;
    wire [15:0] perf_rob_occupancy, perf_rs_occupancy, perf_lsq_occupancy;
    wire [BE_WIDTH-1:0] perf_issue_valid;
    wire perf_branch_pending, perf_mdu_busy;
    assign commit_ready = 1'b1;
    generate if (SERIAL_BACKEND != 0) begin : g_serial_backend
    rv32_serial_backend #(.BE_WIDTH(BE_WIDTH), .SHIFT_IMPL(SHIFT_IMPL),
        .TAG_WIDTH(ROB_TAG_WIDTH)) backend (
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
    assign perf_rob_occupancy = 16'd0;
    assign perf_rs_occupancy = 16'd0;
    assign perf_lsq_occupancy = 16'd0;
    assign perf_issue_valid = {BE_WIDTH{1'b0}};
    assign perf_branch_pending = 1'b0;
    assign perf_mdu_busy = 1'b0;
    end else begin : g_ooo_backend
    rv32_backend_joint #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .ROB_ENTRIES(ROB_ENTRIES), .RS_ENTRIES(RS_ENTRIES), .LSQ_ENTRIES(LSQ_ENTRIES), .INT_ISSUE_WIDTH(INT_ISSUE_WIDTH), .CDB_WIDTH(CDB_WIDTH), .MUL_IMPL(MUL_IMPL), .SHIFT_IMPL(SHIFT_IMPL), .PHYS_TAG_IMPL(PHYS_TAG_IMPL), .CHECKPOINT_IMPL(CHECKPOINT_IMPL), .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE), .COMPLETION_BYPASS(COMPLETION_BYPASS), .COMPLETION_DEPTH(COMPLETION_DEPTH), .TAG_WIDTH(ROB_TAG_WIDTH)) backend (
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
         .branch_feedback_pred_taken_o(branch_feedback_pred_taken), .branch_feedback_pred_target_o(branch_feedback_pred_target),
         .perf_rob_occupancy_o(perf_rob_occupancy), .perf_rs_occupancy_o(perf_rs_occupancy),
         .perf_lsq_occupancy_o(perf_lsq_occupancy), .perf_issue_valid_o(perf_issue_valid),
         .perf_branch_pending_o(perf_branch_pending), .perf_mdu_busy_o(perf_mdu_busy)
    );
    end endgenerate

    wire [63:0] perf_i_requests, perf_i_hits, perf_i_misses, perf_i_refills, perf_i_stalls;
    wire [63:0] perf_d_requests, perf_d_hits, perf_d_misses, perf_d_refills;
    wire [63:0] perf_d_writebacks, perf_d_stalls, perf_i_mem_requests;
    wire [63:0] perf_d_mem_reads, perf_d_mem_writes;
    generate
        if (ENABLE_CACHE_STATS != 0) begin : gen_cache_stats
            rv32_cache_stats stats (
                .clk_i(clk), .reset_i(reset), .i_event_request_i(ic_event_request), .i_event_hit_i(ic_event_hit),
                .i_event_miss_i(ic_event_miss), .i_event_refill_i(ic_event_refill), .i_event_stall_i(ic_event_stall),
                .d_event_request_i(dc_event_request), .d_event_hit_i(dc_event_hit), .d_event_miss_i(dc_event_miss),
                .d_event_refill_i(dc_event_refill), .d_event_writeback_i(dc_event_writeback), .d_event_stall_i(dc_event_stall),
                .i_mem_request_fire_i(mem_i_req_valid && mem_i_req_ready),
                .d_mem_read_fire_i(mem_d_req_valid && mem_d_req_ready && !mem_d_req_write),
                .d_mem_write_fire_i(mem_d_req_valid && mem_d_req_ready && mem_d_req_write),
                .i_request_count_o(perf_i_requests), .i_hit_count_o(perf_i_hits),
                .i_miss_count_o(perf_i_misses), .i_refill_count_o(perf_i_refills),
                .i_stall_count_o(perf_i_stalls), .d_request_count_o(perf_d_requests),
                .d_hit_count_o(perf_d_hits), .d_miss_count_o(perf_d_misses),
                .d_refill_count_o(perf_d_refills), .d_writeback_count_o(perf_d_writebacks),
                .d_stall_count_o(perf_d_stalls), .i_mem_request_count_o(perf_i_mem_requests),
                .d_mem_read_count_o(perf_d_mem_reads), .d_mem_write_count_o(perf_d_mem_writes)
            );
        end else begin : gen_no_cache_stats
            assign perf_i_requests = 64'd0; assign perf_i_hits = 64'd0;
            assign perf_i_misses = 64'd0; assign perf_i_refills = 64'd0;
            assign perf_i_stalls = 64'd0; assign perf_d_requests = 64'd0;
            assign perf_d_hits = 64'd0; assign perf_d_misses = 64'd0;
            assign perf_d_refills = 64'd0; assign perf_d_writebacks = 64'd0;
            assign perf_d_stalls = 64'd0; assign perf_i_mem_requests = 64'd0;
            assign perf_d_mem_reads = 64'd0; assign perf_d_mem_writes = 64'd0;
        end
    endgenerate

    reg [63:0] perf_frontend_empty_cycles;
    reg [63:0] perf_backend_stall_cycles;
    reg [63:0] perf_no_commit_cycles;
    reg [63:0] perf_commit_active_cycles;
    reg [63:0] perf_issue_count;
    reg [63:0] perf_rob_full_cycles;
    reg [63:0] perf_rs_full_cycles;
    reg [63:0] perf_lsq_full_cycles;
    reg [63:0] perf_branch_pending_cycles;
    reg [63:0] perf_mdu_busy_cycles;

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
            perf_frontend_empty_cycles <= 64'd0;
            perf_backend_stall_cycles <= 64'd0;
            perf_no_commit_cycles <= 64'd0;
            perf_commit_active_cycles <= 64'd0;
            perf_issue_count <= 64'd0;
            perf_rob_full_cycles <= 64'd0;
            perf_rs_full_cycles <= 64'd0;
            perf_lsq_full_cycles <= 64'd0;
            perf_branch_pending_cycles <= 64'd0;
            perf_mdu_busy_cycles <= 64'd0;
        end else begin
            cycles <= cycles + 32'd1;
            if ((|commit_valid) && commit_ready)
                instret <= instret + commit_popcount(commit_valid);
            if (ENABLE_CACHE_STATS != 0) begin
                if (!(|fetch_valid)) perf_frontend_empty_cycles <= perf_frontend_empty_cycles + 1'b1;
                if ((|trace_valid) && !(|trace_ready)) perf_backend_stall_cycles <= perf_backend_stall_cycles + 1'b1;
                if (!(|commit_valid)) perf_no_commit_cycles <= perf_no_commit_cycles + 1'b1;
                else perf_commit_active_cycles <= perf_commit_active_cycles + 1'b1;
                perf_issue_count <= perf_issue_count + commit_popcount(perf_issue_valid);
                if (perf_rob_occupancy >= ROB_ENTRIES) perf_rob_full_cycles <= perf_rob_full_cycles + 1'b1;
                if (perf_rs_occupancy >= RS_ENTRIES) perf_rs_full_cycles <= perf_rs_full_cycles + 1'b1;
                if (perf_lsq_occupancy >= LSQ_ENTRIES) perf_lsq_full_cycles <= perf_lsq_full_cycles + 1'b1;
                if (perf_branch_pending) perf_branch_pending_cycles <= perf_branch_pending_cycles + 1'b1;
                if (perf_mdu_busy) perf_mdu_busy_cycles <= perf_mdu_busy_cycles + 1'b1;
            end
        end
    end
endmodule
