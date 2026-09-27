`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Sequential RV32 fetch lanes have distinct low word-index bits. Route them
// to FE_WIDTH disjoint table banks rather than replicate the complete tables.
// Supports the same 1/2/4-wide profiles as cpu_core, retaining BHT256/BTB64.
/* verilator lint_off UNUSEDSIGNAL */
module rv32_banked_predictor #(
    parameter integer FE_WIDTH = 4
) (
    input wire clk_i, reset_i,
    input wire query_valid_i,
    input wire [31:0] query_pc_i,
    input wire [127:0] query_line_i,
    output wire [FE_WIDTH-1:0] pred_taken_o, pred_btb_hit_o,
    output wire [FE_WIDTH*32-1:0] pred_target_o,
    output wire [FE_WIDTH*2-1:0] pred_kind_o, pred_counter_o,
    output wire [FE_WIDTH*6-1:0] pred_bht_index_o,
    output wire [FE_WIDTH*4-1:0] pred_btb_index_o,
    input wire feedback_valid_i,
    input wire [31:0] feedback_pc_i,
    input wire [1:0] feedback_kind_i,
    input wire feedback_taken_i,
    input wire [31:0] feedback_target_i,
    input wire feedback_pred_taken_i,
    input wire [31:0] feedback_pred_target_i,
    output reg [31:0] prediction_count_o, correct_count_o
);
    localparam integer BANK_BITS = $clog2(FE_WIDTH);
    localparam [1:0] BANK_MASK = (FE_WIDTH == 1) ? 2'b00 :
                               ((FE_WIDTH == 2) ? 2'b01 : 2'b11);
    wire [1:0] base_bank = query_pc_i[3:2] & BANK_MASK;
    wire [1:0] feedback_bank = feedback_pc_i[3:2] & BANK_MASK;
    wire [FE_WIDTH-1:0] bank_taken, bank_hit;
    wire [FE_WIDTH*32-1:0] bank_target;
    wire [FE_WIDTH*2-1:0] bank_kind, bank_counter;
    genvar bank, lane;
    initial begin
        if (FE_WIDTH != 1 && FE_WIDTH != 2 && FE_WIDTH != 4) begin
            $display("ERROR: banked predictor requires FE_WIDTH 1, 2, or 4");
            $finish;
        end
    end
    generate
        for (bank = 0; bank < FE_WIDTH; bank = bank + 1) begin : g_bank
            localparam [1:0] BANK_NUMBER = bank;
            wire [1:0] offset = (BANK_NUMBER - base_bank) & BANK_MASK;
            wire [2:0] word_index = {1'b0, query_pc_i[3:2]} + {1'b0, offset};
            wire [31:0] pc = query_pc_i + {28'd0, offset, 2'b00};
            wire [127:0] shifted_line = query_line_i >> (word_index * 32);
            wire [31:0] inst = shifted_line[31:0];
            rv32_branch_predictor #(.BANK_BITS(BANK_BITS)) predictor (
                .clk_i(clk_i), .reset_i(reset_i),
                .query_valid_i(query_valid_i && word_index < 3'd4),
                .query_pc_i(pc), .query_inst_i(inst),
                .pred_taken_o(bank_taken[bank]), .pred_btb_hit_o(bank_hit[bank]),
                .pred_target_o(bank_target[bank*32 +: 32]),
                .pred_kind_o(bank_kind[bank*2 +: 2]),
                .pred_counter_o(bank_counter[bank*2 +: 2]),
                .pred_bht_index_o(), .pred_btb_index_o(),
                .feedback_valid_i(feedback_valid_i && feedback_bank == BANK_NUMBER),
                .feedback_pc_i(feedback_pc_i), .feedback_kind_i(feedback_kind_i),
                .feedback_taken_i(feedback_taken_i), .feedback_target_i(feedback_target_i),
                .feedback_pred_taken_i(feedback_pred_taken_i),
                .feedback_pred_target_i(feedback_pred_target_i),
                .prediction_count_o(), .correct_count_o()
            );
        end
        for (lane = 0; lane < FE_WIDTH; lane = lane + 1) begin : g_lane
            localparam [1:0] LANE_OFFSET = lane;
            wire [1:0] select_bank = (base_bank + LANE_OFFSET) & BANK_MASK;
            wire [31:0] pc = query_pc_i + (lane * 32'd4);
            assign pred_taken_o[lane] = bank_taken[select_bank];
            assign pred_btb_hit_o[lane] = bank_hit[select_bank];
            assign pred_target_o[lane*32 +: 32] = bank_target[select_bank*32 +: 32];
            assign pred_kind_o[lane*2 +: 2] = bank_kind[select_bank*2 +: 2];
            assign pred_counter_o[lane*2 +: 2] = bank_counter[select_bank*2 +: 2];
            assign pred_bht_index_o[lane*6 +: 6] = pc[7:2];
            assign pred_btb_index_o[lane*4 +: 4] = pc[5:2];
        end
    endgenerate
    // Count committed feedback once, including kinds that don't allocate BTB.
    always @(posedge clk_i) begin
        if (reset_i) begin
            prediction_count_o <= 0;
            correct_count_o <= 0;
        end else if (feedback_valid_i) begin
            prediction_count_o <= prediction_count_o + 1;
            if (feedback_pred_taken_i == feedback_taken_i &&
                (!feedback_taken_i || feedback_pred_target_i == feedback_target_i))
                correct_count_o <= correct_count_o + 1;
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
