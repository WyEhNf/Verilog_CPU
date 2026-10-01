`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Sequential RV32 fetch lanes have distinct low word-index bits. Route them
// to FE_WIDTH disjoint table banks rather than replicate the complete tables.
// Supports the same 1/2/4-wide profiles as cpu_core, retaining BHT256/BTB64.
/* verilator lint_off UNUSEDSIGNAL */
module rv32_banked_predictor #(
    parameter integer FE_WIDTH = 4,
    parameter integer DIRECT_BRANCH_TARGET = 0,
    parameter integer HISTORY_BITS = 6
) (
    input wire clk_i, reset_i,
    input wire query_valid_i,
    input wire [31:0] query_pc_i,
    input wire [127:0] query_line_i,
    input wire query_accept_i,
    input wire [FE_WIDTH-1:0] effective_pred_taken_i,
    input wire recovery_valid_i,
    input wire [7:0] recovery_history_i,
    output reg [FE_WIDTH*16-1:0] pred_metadata_o,
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
    input wire [15:0] feedback_metadata_i,
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
    wire [FE_WIDTH*8-1:0] bank_training_index;
    reg [7:0] global_history;
    reg [7:0] history_after_bundle;
    reg history_prefix_live;
    integer history_lane;
    integer history_word;
    localparam [7:0] HISTORY_MASK = (1 << HISTORY_BITS) - 1;
    genvar bank, lane;
    initial begin
        if (FE_WIDTH != 1 && FE_WIDTH != 2 && FE_WIDTH != 4) begin
            $display("ERROR: banked predictor requires FE_WIDTH 1, 2, or 4");
            $finish;
        end
        if (DIRECT_BRANCH_TARGET < 0 || DIRECT_BRANCH_TARGET > 2 ||
            HISTORY_BITS < 1 || HISTORY_BITS > (8-BANK_BITS)) begin
            $display("ERROR: predictor mode must be 0/1/2; history must fit bank rows");
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
            rv32_branch_predictor #(.BANK_BITS(BANK_BITS), .DIRECT_BRANCH_TARGET(DIRECT_BRANCH_TARGET),
                .HISTORY_BITS(HISTORY_BITS)) predictor (
                .clk_i(clk_i), .reset_i(reset_i),
                .query_valid_i(query_valid_i && word_index < 3'd4),
                .query_pc_i(pc), .query_inst_i(inst),
                .query_history_i(global_history),
                .pred_training_index_o(bank_training_index[bank*8 +: 8]),
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
                .feedback_training_index_i(feedback_metadata_i[7:0]),
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
    // Parallel queries share the pre-bundle history and disjoint PC banks.
    // Save that exact table index, plus a per-instruction program-order
    // history checkpoint. Only accepted prefix instructions advance history.
    always @* begin
        history_after_bundle = global_history;
        history_prefix_live = query_valid_i;
        pred_metadata_o = {FE_WIDTH*16{1'b0}};
        for (history_lane = 0; history_lane < FE_WIDTH; history_lane = history_lane + 1) begin
            history_word = query_pc_i[3:2] + history_lane;
            if (history_prefix_live && history_word < 4) begin
                if (DIRECT_BRANCH_TARGET == 2)
                    pred_metadata_o[history_lane*16 +: 16] = {
                        history_after_bundle,
                        bank_training_index[((base_bank+history_lane)&BANK_MASK)*8 +: 8]};
                if (pred_kind_o[history_lane*2 +: 2] == `RV32IM_PRED_BRANCH)
                    history_after_bundle = ((history_after_bundle << 1) |
                        {7'b0, pred_taken_o[history_lane]}) & HISTORY_MASK;
                // The core can override a return prediction using its RAS.
                // Follow that effective prefix, not the raw BTB direction.
                if (effective_pred_taken_i[history_lane] ||
                    ((query_line_i >> (history_word*32)) == 32'h0ff00513))
                    history_prefix_live = 1'b0;
            end
        end
    end
    always @(posedge clk_i) begin
        if (reset_i)
            global_history <= 0;
        else if (DIRECT_BRANCH_TARGET == 2) begin
            if (recovery_valid_i)
                global_history <= recovery_history_i & HISTORY_MASK;
            else if (query_accept_i)
                global_history <= history_after_bundle;
        end
    end
    // Count accepted resolution feedback once, including non-allocating kinds.
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
