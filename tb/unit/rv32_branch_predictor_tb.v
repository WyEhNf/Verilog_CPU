`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_branch_predictor_tb;
    reg clk, reset;
    reg query_valid;
    reg [31:0] query_pc, query_inst;
    wire pred_taken, pred_btb_hit;
    wire [31:0] pred_target;
    wire [1:0] pred_kind, pred_counter;
    wire [5:0] pred_bht_index;
    wire [3:0] pred_btb_index;
    reg feedback_valid, feedback_taken, feedback_pred_taken;
    reg [31:0] feedback_pc, feedback_target, feedback_pred_target;
    reg [1:0] feedback_kind;
    wire [31:0] prediction_count, correct_count;

    rv32_branch_predictor dut (
        .clk_i(clk), .reset_i(reset), .query_valid_i(query_valid),
        .query_pc_i(query_pc), .query_inst_i(query_inst),
        .pred_taken_o(pred_taken), .pred_target_o(pred_target),
        .pred_kind_o(pred_kind), .pred_btb_hit_o(pred_btb_hit),
        .pred_bht_index_o(pred_bht_index), .pred_btb_index_o(pred_btb_index),
        .pred_counter_o(pred_counter), .feedback_valid_i(feedback_valid),
        .feedback_pc_i(feedback_pc), .feedback_kind_i(feedback_kind),
        .feedback_taken_i(feedback_taken), .feedback_target_i(feedback_target),
        .feedback_pred_taken_i(feedback_pred_taken),
        .feedback_pred_target_i(feedback_pred_target),
        .prediction_count_o(prediction_count), .correct_count_o(correct_count)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end

    task train;
        input [31:0] pc;
        input [1:0] kind;
        input taken;
        input [31:0] target;
        input was_taken;
        input [31:0] was_target;
        begin
            @(negedge clk);
            feedback_valid = 1'b1;
            feedback_pc = pc;
            feedback_kind = kind;
            feedback_taken = taken;
            feedback_target = target;
            feedback_pred_taken = was_taken;
            feedback_pred_target = was_target;
            @(negedge clk);
            feedback_valid = 1'b0;
        end
    endtask

    task query;
        input [31:0] pc;
        input [31:0] inst;
        begin
            query_pc = pc;
            query_inst = inst;
            query_valid = 1'b1;
            #1;
        end
    endtask

    initial begin
        reset = 1'b1;
        query_valid = 1'b0;
        query_pc = 0;
        query_inst = 0;
        feedback_valid = 1'b0;
        feedback_pc = 0;
        feedback_kind = 0;
        feedback_taken = 0;
        feedback_target = 0;
        feedback_pred_taken = 0;
        feedback_pred_target = 0;
        repeat (2) @(posedge clk);
        @(negedge clk); reset = 1'b0;

        query(32'h00000100, 32'h00208463); // BEQ, BTB initially empty
        if (pred_taken || pred_btb_hit || pred_kind != `RV32IM_PRED_BRANCH || pred_counter != 2'b10) begin
            $display("FAIL: branch BTB-miss policy"); $finish(1);
        end
        train(32'h100, `RV32IM_PRED_BRANCH, 1'b1, 32'h180, pred_taken, pred_target);
        query(32'h100, 32'h00208463);
        if (!pred_taken || !pred_btb_hit || pred_target != 32'h180 || pred_counter != 2'b11) begin
            $display("FAIL: taken branch training"); $finish(1);
        end

        train(32'h100, `RV32IM_PRED_BRANCH, 1'b0, 32'h104, pred_taken, pred_target);
        query(32'h100, 32'h00208463);
        if (!pred_taken || pred_counter != 2'b10) begin $display("FAIL: weak-taken transition"); $finish(1); end
        train(32'h100, `RV32IM_PRED_BRANCH, 1'b0, 32'h104, pred_taken, pred_target);
        query(32'h100, 32'h00208463);
        if (pred_taken || pred_counter != 2'b01) begin $display("FAIL: not-taken transition"); $finish(1); end
        train(32'h100, `RV32IM_PRED_BRANCH, 1'b0, 32'h104, pred_taken, pred_target);
        train(32'h100, `RV32IM_PRED_BRANCH, 1'b0, 32'h104, 1'b0, 32'h104);
        query(32'h100, 32'h00208463);
        if (pred_counter != 2'b00) begin $display("FAIL: strongly-not-taken saturation"); $finish(1); end

        // BHT aliases at +0x100, while BTB aliases at +0x40 and must reject old tags.
        train(32'h204, `RV32IM_PRED_BRANCH, 1'b1, 32'h280, 1'b0, 32'h208);
        query(32'h304, 32'h00208463);
        if (pred_counter != 2'b11 || pred_btb_hit) begin $display("FAIL: BHT/BTB alias behavior counter=%b hit=%b", pred_counter, pred_btb_hit); $finish(1); end
        train(32'h244, `RV32IM_PRED_BRANCH, 1'b1, 32'h2c0, 1'b0, 32'h248);
        query(32'h204, 32'h00208463);
        if (pred_btb_hit) begin $display("FAIL: direct-mapped BTB tag replacement"); $finish(1); end

        query(32'h400, 32'h008000ef); // JAL +8
        if (!pred_taken || pred_target != 32'h408 || pred_kind != `RV32IM_PRED_JAL || pred_btb_hit) begin
            $display("FAIL: direct JAL prediction"); $finish(1);
        end

        query(32'h500, 32'h000080e7); // JALR, miss
        if (pred_taken || pred_kind != `RV32IM_PRED_JALR || pred_btb_hit) begin $display("FAIL: JALR miss"); $finish(1); end
        train(32'h500, `RV32IM_PRED_JALR, 1'b1, 32'h601, pred_taken, pred_target);
        query(32'h500, 32'h000080e7);
        if (!pred_taken || !pred_btb_hit || pred_target != 32'h600) begin $display("FAIL: JALR BTB prediction"); $finish(1); end

        query(32'h600, 32'h00100093); // ADDI
        if (pred_taken || pred_kind != `RV32IM_PRED_NONE || pred_target != 32'h604) begin $display("FAIL: non-control prediction"); $finish(1); end

        if (prediction_count != 8 || correct_count != 2) begin
            $display("FAIL: prediction statistics count=%0d correct=%0d", prediction_count, correct_count);
            $finish(1);
        end
        $display("PASS: A-02 bimodal predictor and BTB");
        $finish(0);
    end

    initial begin
        #3000;
        $display("FAIL: A-02 predictor timeout");
        $finish(1);
    end
endmodule
