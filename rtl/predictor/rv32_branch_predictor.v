`timescale 1ns/1ps
`include "rv32im_defs.vh"

// 256-entry bimodal predictor plus a 64-entry direct-mapped BTB.
// Table updates use accepted resolution feedback from the backend.
/* verilator lint_off UNUSEDSIGNAL */
module rv32_branch_predictor #(
    // A bank stores the high index bits; its caller routes low-bit ownership.
    // BANK_BITS=0 preserves the standalone full-table predictor interface.
    parameter integer BANK_BITS = 0,
    parameter integer DIRECT_BRANCH_TARGET = 0,
    parameter integer HISTORY_BITS = 6
) (
    input  wire        clk_i,
    input  wire        reset_i,

    input  wire        query_valid_i,
    input  wire [31:0] query_pc_i,
    input  wire [31:0] query_inst_i,
    input  wire [7:0]  query_history_i,
    output wire [7:0]  pred_training_index_o,
    output reg          pred_taken_o,
    output reg  [31:0] pred_target_o,
    output reg  [1:0]  pred_kind_o,
    output reg          pred_btb_hit_o,
    output wire [5:0]  pred_bht_index_o,
    output wire [3:0]  pred_btb_index_o,
    output wire [1:0]  pred_counter_o,

    input  wire        feedback_valid_i,
    input  wire [31:0] feedback_pc_i,
    input  wire [1:0]  feedback_kind_i,
    input  wire        feedback_taken_i,
    input  wire [31:0] feedback_target_i,
    input  wire        feedback_pred_taken_i,
    input  wire [31:0] feedback_pred_target_i,
    input  wire [7:0]  feedback_training_index_i,

    output reg  [31:0] prediction_count_o,
    output reg  [31:0] correct_count_o
);
    localparam integer BHT_ENTRIES = 256 >> BANK_BITS;
    localparam integer BTB_ENTRIES = 64 >> BANK_BITS;
    reg [1:0] bht [0:BHT_ENTRIES-1];
    reg bht_trained [0:BHT_ENTRIES-1];
    reg       btb_valid [0:BTB_ENTRIES-1];
    reg [23:0] btb_tag [0:BTB_ENTRIES-1];
    reg [31:0] btb_target [0:BTB_ENTRIES-1];
    reg [1:0] btb_kind [0:BTB_ENTRIES-1];

    wire [6:0] query_opcode = query_inst_i[6:0];
    localparam [7:0] HISTORY_MASK = (1 << HISTORY_BITS) - 1;
    wire [7:0] query_full_index = query_pc_i[9:2] ^
        ((DIRECT_BRANCH_TARGET == 2) ? ((query_history_i & HISTORY_MASK) << BANK_BITS) : 8'b0);
    wire [7-BANK_BITS:0] query_bht_index = query_full_index[7:BANK_BITS];
    assign pred_training_index_o = query_full_index;
    wire [5-BANK_BITS:0] query_btb_index = query_pc_i[7:2+BANK_BITS];
    wire query_btb_match = btb_valid[query_btb_index] &&
                           (btb_tag[query_btb_index] == query_pc_i[31:8]);
    wire [31:0] jal_imm = {{11{query_inst_i[31]}}, query_inst_i[31],
                           query_inst_i[19:12], query_inst_i[20],
                           query_inst_i[30:21], 1'b0};
    wire [31:0] branch_imm = {{19{query_inst_i[31]}}, query_inst_i[31],
                              query_inst_i[7], query_inst_i[30:25],
                              query_inst_i[11:8], 1'b0};
    wire [7-BANK_BITS:0] feedback_bht_index = (DIRECT_BRANCH_TARGET == 2) ?
        feedback_training_index_i[7:BANK_BITS] : feedback_pc_i[9:2+BANK_BITS];
    wire [5-BANK_BITS:0] feedback_btb_index = feedback_pc_i[7:2+BANK_BITS];
    wire feedback_btb_write = feedback_valid_i && feedback_taken_i &&
                             (((DIRECT_BRANCH_TARGET == 0) &&
                               (feedback_kind_i == `RV32IM_PRED_BRANCH)) ||
                              (feedback_kind_i == `RV32IM_PRED_JALR));
    wire [31:0] feedback_btb_target = (feedback_kind_i == `RV32IM_PRED_JALR) ?
                                    {feedback_target_i[31:1], 1'b0} : feedback_target_i;
    integer i;

    assign pred_bht_index_o = query_pc_i[7:2];
    assign pred_btb_index_o = query_pc_i[5:2];
    assign pred_counter_o = bht[query_bht_index];

    always @* begin
        pred_taken_o = 1'b0;
        pred_target_o = query_pc_i + 32'd4;
        pred_kind_o = `RV32IM_PRED_NONE;
        pred_btb_hit_o = 1'b0;

        if (query_valid_i) begin
            case (query_opcode)
                7'b1100011: begin
                    pred_kind_o = `RV32IM_PRED_BRANCH;
                    pred_btb_hit_o = query_btb_match &&
                                     (btb_kind[query_btb_index] == `RV32IM_PRED_BRANCH);
                    if (DIRECT_BRANCH_TARGET != 0) begin
                        // RV32 conditional targets are PC+decoded immediate;
                        // a BTB miss/alias must not discard a trained direction.
                        // Keep BTFNT on a cold BHT row, but after training use
                        // its counter regardless of indirect-target residency.
                        if (bht_trained[query_bht_index] ? bht[query_bht_index][1] : branch_imm[31]) begin
                            pred_taken_o = 1'b1;
                            pred_target_o = query_pc_i + branch_imm;
                        end
                    end else if (bht[query_bht_index][1] && pred_btb_hit_o) begin
                        pred_taken_o = 1'b1;
                        pred_target_o = btb_target[query_btb_index];
                    end else if (!pred_btb_hit_o && branch_imm[31]) begin
                        // Backward-taken/forward-not-taken gives a cold loop a
                        // useful target before its first BTB allocation.
                        pred_taken_o = 1'b1;
                        pred_target_o = query_pc_i + branch_imm;
                    end
                end
                7'b1101111: begin
                    pred_kind_o = `RV32IM_PRED_JAL;
                    pred_taken_o = 1'b1;
                    pred_target_o = query_pc_i + jal_imm;
                end
                7'b1100111: begin
                    if (query_inst_i[14:12] == 3'b000) begin
                        pred_kind_o = `RV32IM_PRED_JALR;
                        pred_btb_hit_o = query_btb_match &&
                                         (btb_kind[query_btb_index] == `RV32IM_PRED_JALR);
                        if (pred_btb_hit_o) begin
                            pred_taken_o = 1'b1;
                            pred_target_o = btb_target[query_btb_index];
                        end
                    end
                end
                default: begin end
            endcase
        end
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            prediction_count_o <= 32'd0;
            correct_count_o <= 32'd0;
            for (i = 0; i < BHT_ENTRIES; i = i + 1) begin
                bht[i] <= 2'b10; // weakly taken
                bht_trained[i] <= 1'b0;
            end
            for (i = 0; i < BTB_ENTRIES; i = i + 1) begin
                btb_valid[i] <= 1'b0;
            end
        end else if (feedback_valid_i) begin
            prediction_count_o <= prediction_count_o + 32'd1;
            if ((feedback_pred_taken_i == feedback_taken_i) &&
                (!feedback_taken_i || (feedback_pred_target_i == feedback_target_i)))
                correct_count_o <= correct_count_o + 32'd1;

            if (feedback_kind_i == `RV32IM_PRED_BRANCH) begin
                bht_trained[feedback_bht_index] <= 1'b1;
                if (feedback_taken_i) begin
                    if (bht[feedback_bht_index] != 2'b11)
                        bht[feedback_bht_index] <= bht[feedback_bht_index] + 2'b01;
                end else if (bht[feedback_bht_index] != 2'b00) begin
                    bht[feedback_bht_index] <= bht[feedback_bht_index] - 2'b01;
                end
            end
            if (feedback_btb_write) begin
                btb_valid[feedback_btb_index] <= 1'b1;
            end
        end
    end

    // Only valid bits need reset: every payload read is gated by a valid,
    // matching tag and kind. A warm reset invalidates retained payload too.
    // Branch/JALR allocations are exclusive and share one payload write port.
    always @(posedge clk_i) begin
        if (!reset_i && feedback_btb_write) begin
            btb_tag[feedback_btb_index] <= feedback_pc_i[31:8];
            btb_target[feedback_btb_index] <= feedback_btb_target;
            btb_kind[feedback_btb_index] <= feedback_kind_i;
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
