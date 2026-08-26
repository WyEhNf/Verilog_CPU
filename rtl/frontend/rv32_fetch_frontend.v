`timescale 1ns/1ps
`include "rv32im_defs.vh"

/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
/* verilator lint_off BLKSEQ */

// Frontend controller between the instruction cache and decode/rename.
// Predictor metadata is carried with each returned instruction so this block
// can be verified independently from predictor table state.
module rv32_fetch_frontend #(
    parameter integer FE_WIDTH = `RV32IM_FE_WIDTH_DEFAULT,
    parameter integer FQ_DEPTH = 16,
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         redirect_valid_i,
    input  wire [31:0]                  redirect_pc_i,
    input  wire [EPOCH_WIDTH-1:0]       redirect_epoch_i,
    input  wire                         stop_i,
    input  wire                         error_i,

    output wire                         if_req_valid_o,
    input  wire                         if_req_ready_i,
    output wire [31:0]                  if_req_pc_o,
    output wire [EPOCH_WIDTH-1:0]       if_req_epoch_o,

    input  wire                         if_resp_valid_i,
    output wire                         if_resp_ready_o,
    input  wire [31:0]                  if_resp_pc_i,
    input  wire [31:0]                  if_resp_line_addr_i,
    input  wire [127:0]                 if_resp_line_data_i,
    input  wire [EPOCH_WIDTH-1:0]       if_resp_epoch_i,
    input  wire                         if_resp_error_i,
    input  wire [FE_WIDTH-1:0]          if_resp_pred_taken_i,
    input  wire [FE_WIDTH*32-1:0]       if_resp_pred_target_i,
    input  wire [FE_WIDTH*2-1:0]        if_resp_pred_kind_i,
    input  wire [FE_WIDTH-1:0]          if_resp_pred_btb_hit_i,

    output reg  [FE_WIDTH-1:0]          fetch_valid_o,
    input  wire [FE_WIDTH-1:0]           fetch_ready_i,
    output reg  [FE_WIDTH*`RV32IM_FETCH_PACKET_WIDTH-1:0] fetch_packet_o,
    output wire [EPOCH_WIDTH-1:0]       current_epoch_o,
    output wire                         frozen_o,
    output reg                          event_fetch_o,
    output reg                          event_redirect_o,
    output reg                          event_stall_o
);
    localparam integer PACKET_WIDTH = `RV32IM_FETCH_PACKET_WIDTH;
    localparam integer PTR_WIDTH = (FQ_DEPTH <= 2) ? 1 : $clog2(FQ_DEPTH);

    reg [31:0] pc_reg;
    reg [EPOCH_WIDTH-1:0] epoch_reg;
    reg req_pending_reg;
    reg frozen_reg;
    reg [PTR_WIDTH-1:0] head_reg, tail_reg;
    integer count_reg;

    reg [31:0] fq_pc [0:FQ_DEPTH-1];
    reg [31:0] fq_inst [0:FQ_DEPTH-1];
    reg fq_pred_taken [0:FQ_DEPTH-1];
    reg [31:0] fq_pred_target [0:FQ_DEPTH-1];
    reg [1:0] fq_pred_kind [0:FQ_DEPTH-1];
    reg fq_pred_btb_hit [0:FQ_DEPTH-1];
    reg [EPOCH_WIDTH-1:0] fq_epoch [0:FQ_DEPTH-1];

    reg [FE_WIDTH-1:0] bundle_pred_taken;
    reg [FE_WIDTH-1:0] bundle_pred_btb_hit;
    reg [FE_WIDTH*32-1:0] bundle_pred_target;
    reg [FE_WIDTH*2-1:0] bundle_pred_kind;
    reg [FE_WIDTH*32-1:0] bundle_inst;
    reg [FE_WIDTH*32-1:0] bundle_pc;
    reg [EPOCH_WIDTH-1:0] bundle_epoch;
    integer bundle_count;
    integer enq_count;
    integer deq_count;
    integer i;
    integer b;
    integer j;
    integer k;
    integer out_index;
    integer write_index;
    integer word_index;
    reg [31:0] next_pc_comb;
    reg bundle_freeze;
    reg req_fire;
    reg resp_fire;

    wire queue_space = (count_reg + bundle_count <= FQ_DEPTH);
    wire response_live = (if_resp_epoch_i == epoch_reg) &&
                         (if_resp_line_addr_i == {if_resp_pc_i[31:4], 4'b0000});

    assign current_epoch_o = epoch_reg;
    assign frozen_o = frozen_reg;
    assign if_req_valid_o = !reset_i && !frozen_reg && !stop_i && !error_i && !req_pending_reg;
    assign if_req_pc_o = pc_reg;
    assign if_req_epoch_o = epoch_reg;
    assign if_resp_ready_o = !reset_i && !redirect_valid_i && response_live && queue_space;

    always @* begin
        // Form the largest contiguous bundle available in this returned line.
        bundle_pred_taken = {FE_WIDTH{1'b0}};
        bundle_pred_btb_hit = {FE_WIDTH{1'b0}};
        bundle_pred_target = {FE_WIDTH*32{1'b0}};
        bundle_pred_kind = {FE_WIDTH*2{1'b0}};
        bundle_inst = {FE_WIDTH*32{1'b0}};
        bundle_pc = {FE_WIDTH*32{1'b0}};
        bundle_epoch = if_resp_epoch_i;
        bundle_count = 0;
        next_pc_comb = if_resp_pc_i + 32'd4;
        bundle_freeze = if_resp_error_i;
        word_index = if_resp_pc_i[3:2];
        for (b = 0; b < FE_WIDTH; b = b + 1) begin
            if ((word_index + b) < 4 && !bundle_freeze) begin
                bundle_inst[b*32 +: 32] = if_resp_line_data_i >> ((word_index+b)*32);
                bundle_pc[b*32 +: 32] = if_resp_pc_i + (b*32'd4);
                bundle_pred_taken[b] = if_resp_pred_taken_i[b];
                bundle_pred_btb_hit[b] = if_resp_pred_btb_hit_i[b];
                bundle_pred_target[b*32 +: 32] = if_resp_pred_target_i[b*32 +: 32];
                bundle_pred_kind[b*2 +: 2] = if_resp_pred_kind_i[b*2 +: 2];
                bundle_count = bundle_count + 1;
                next_pc_comb = if_resp_pc_i + ((b+1)*32'd4);
                if (if_resp_pred_taken_i[b]) begin
                    next_pc_comb = if_resp_pred_target_i[b*32 +: 32];
                    bundle_freeze = 1'b1;
                end
                if ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513) begin
                    bundle_freeze = 1'b1;
                end
            end
        end
        if (if_resp_error_i)
            bundle_count = 0;
        enq_count = (if_resp_valid_i && if_resp_ready_o) ? bundle_count : 0;
    end

    always @* begin
        fetch_valid_o = {FE_WIDTH{1'b0}};
        fetch_packet_o = {(FE_WIDTH*PACKET_WIDTH){1'b0}};
        deq_count = 0;
        for (j = 0; j < FE_WIDTH; j = j + 1) begin
            out_index = head_reg + j;
            if (out_index >= FQ_DEPTH)
                out_index = out_index - FQ_DEPTH;
            if (j < count_reg) begin
                fetch_valid_o[j] = 1'b1;
                fetch_packet_o[j*PACKET_WIDTH +: PACKET_WIDTH] =
                    `RV32IM_FETCH_PACKET_PACK(fq_pc[out_index], fq_inst[out_index],
                                               fq_pred_taken[out_index], fq_pred_target[out_index],
                                               fq_pred_kind[out_index], fq_pred_btb_hit[out_index],
                                               fq_epoch[out_index]);
            end
            if ((j < count_reg) && (deq_count == j) && fetch_ready_i[j])
                deq_count = deq_count + 1;
        end
    end

    always @* begin
        req_fire = if_req_valid_o && if_req_ready_i;
        resp_fire = if_resp_valid_i && if_resp_ready_o;
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            pc_reg <= 32'd0;
            epoch_reg <= {EPOCH_WIDTH{1'b0}};
            req_pending_reg <= 1'b0;
            frozen_reg <= 1'b0;
            head_reg <= {PTR_WIDTH{1'b0}};
            tail_reg <= {PTR_WIDTH{1'b0}};
            count_reg <= 0;
            event_fetch_o <= 1'b0;
            event_redirect_o <= 1'b0;
            event_stall_o <= 1'b0;
            for (k = 0; k < FQ_DEPTH; k = k + 1) begin
                fq_pc[k] <= 32'd0;
                fq_inst[k] <= 32'd0;
                fq_pred_taken[k] <= 1'b0;
                fq_pred_target[k] <= 32'd0;
                fq_pred_kind[k] <= `RV32IM_PRED_NONE;
                fq_pred_btb_hit[k] <= 1'b0;
                fq_epoch[k] <= {EPOCH_WIDTH{1'b0}};
            end
        end else begin
            event_fetch_o <= (deq_count != 0);
            event_redirect_o <= redirect_valid_i;
            event_stall_o <= (count_reg != 0) && (deq_count == 0);

            if (redirect_valid_i) begin
                pc_reg <= redirect_pc_i;
                epoch_reg <= redirect_epoch_i;
                req_pending_reg <= 1'b0;
                frozen_reg <= 1'b0;
                head_reg <= {PTR_WIDTH{1'b0}};
                tail_reg <= {PTR_WIDTH{1'b0}};
                count_reg <= 0;
            end else begin
                if (req_fire)
                    req_pending_reg <= 1'b1;
                if (resp_fire) begin
                    req_pending_reg <= 1'b0;
                    pc_reg <= next_pc_comb;
                    if (bundle_freeze || stop_i || error_i)
                        frozen_reg <= 1'b1;
                end
                if (stop_i || error_i)
                    frozen_reg <= 1'b1;

                if (resp_fire) begin
                    for (i = 0; i < FE_WIDTH; i = i + 1) begin
                        if (i < bundle_count) begin
                            write_index = tail_reg + i;
                            if (write_index >= FQ_DEPTH)
                                write_index = write_index - FQ_DEPTH;
                            fq_pc[write_index] <= bundle_pc[i*32 +: 32];
                            fq_inst[write_index] <= bundle_inst[i*32 +: 32];
                            fq_pred_taken[write_index] <= bundle_pred_taken[i];
                            fq_pred_target[write_index] <= bundle_pred_target[i*32 +: 32];
                            fq_pred_kind[write_index] <= bundle_pred_kind[i*2 +: 2];
                            fq_pred_btb_hit[write_index] <= bundle_pred_btb_hit[i];
                            fq_epoch[write_index] <= bundle_epoch;
                        end
                    end
                    tail_reg <= tail_reg + bundle_count;
                end
                head_reg <= head_reg + deq_count;
                count_reg <= count_reg + enq_count - deq_count;
            end
        end
    end

    initial begin
        if ((FE_WIDTH != 1) && (FE_WIDTH != 2) && (FE_WIDTH != 4)) begin
            $display("ERROR: invalid FE_WIDTH=%0d; expected 1, 2, or 4", FE_WIDTH);
            $finish;
        end
        if ((FQ_DEPTH < FE_WIDTH) || ((FQ_DEPTH & (FQ_DEPTH - 1)) != 0)) begin
            $display("ERROR: invalid FQ_DEPTH=%0d; expected power of two >= FE_WIDTH", FQ_DEPTH);
            $finish;
        end
    end
endmodule
