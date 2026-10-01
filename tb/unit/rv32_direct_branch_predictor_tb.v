`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_direct_branch_predictor_tb #(
    parameter integer BANK_BITS = 0
);
    reg clk = 0;
    always #5 clk = !clk;
    reg reset, query_valid, feedback_valid, feedback_taken;
    reg [31:0] pc, inst, feedback_pc, feedback_target;
    reg [1:0] feedback_kind;
    wire taken, hit;
    wire [31:0] target;
    wire [1:0] kind, counter;
    wire [31:0] predictions, correct;
    integer row;
    rv32_branch_predictor #(.BANK_BITS(BANK_BITS), .DIRECT_BRANCH_TARGET(1)) dut (
        .clk_i(clk), .reset_i(reset), .query_valid_i(query_valid),
        .query_pc_i(pc), .query_inst_i(inst), .pred_taken_o(taken),
        .pred_target_o(target), .pred_kind_o(kind), .pred_btb_hit_o(hit),
        .pred_bht_index_o(), .pred_btb_index_o(), .pred_counter_o(counter),
        .feedback_valid_i(feedback_valid), .feedback_pc_i(feedback_pc),
        .feedback_kind_i(feedback_kind), .feedback_taken_i(feedback_taken),
        .feedback_target_i(feedback_target), .feedback_pred_taken_i(1'b0),
        .feedback_pred_target_i(32'b0), .prediction_count_o(predictions), .correct_count_o(correct)
    );
    task query;
        input [31:0] query_pc;
        input [31:0] query_inst;
        begin pc = query_pc; inst = query_inst; query_valid = 1; #1; end
    endtask
    task train;
        input [31:0] train_pc;
        input [1:0] train_kind;
        input train_taken;
        input [31:0] train_target;
        begin
            @(negedge clk);
            feedback_valid = 1; feedback_pc = train_pc; feedback_kind = train_kind;
            feedback_taken = train_taken; feedback_target = train_target;
            @(negedge clk); feedback_valid = 0;
        end
    endtask
    initial begin
        reset = 1; query_valid = 0; pc = 0; inst = 0;
        feedback_valid = 0; feedback_pc = 0; feedback_target = 0;
        feedback_taken = 0; feedback_kind = 0;
        repeat (2) @(negedge clk);
        reset = 0;
        query(32'h100, 32'h00208463); // BEQ +8, cold BTFNT
        if (taken !== 0 || hit !== 0 || counter !== 2'b10) $fatal(1, "Cold forward policy");
        query(32'h100, 32'hfe208ee3); // BEQ -4
        if (taken !== 1 || target !== 32'hfc || hit !== 0) $fatal(1, "Cold backward policy");
        // Deliberately nonsensical feedback target: direction training must
        // NOT replace the target implied by the fetched instruction.
        train(32'h100, `RV32IM_PRED_BRANCH, 1, 32'hdeadbeef);
        query(32'h100, 32'h00208463);
        if (taken !== 1 || target !== 32'h108 || counter !== 2'b11 || hit !== 0)
            $fatal(1, "Conditional target still depends on BTB allocation");
        // An indirect at +0x100 aliases the 64-entry BTB but not the 256 BHT.
        train(32'h200, `RV32IM_PRED_JALR, 1, 32'h601);
        query(32'h200, 32'h000080e7);
        if (taken !== 1 || target !== 32'h600 || hit !== 1) $fatal(1, "Indirect allocation/alignment");
        query(32'h100, 32'h00208463);
        if (taken !== 1 || target !== 32'h108 || hit !== 0) $fatal(1, "BTB collision erased trained direction");
        train(32'h100, `RV32IM_PRED_BRANCH, 0, 32'h104);
        train(32'h100, `RV32IM_PRED_BRANCH, 0, 32'h104);
        query(32'h100, 32'hfe208ee3);
        if (taken !== 0 || target !== 32'h104 || counter !== 2'b01)
            $fatal(1, "Trained not-taken direction ignored for a backward branch");
        // Conditional training must not evict that indirect's target entry.
        query(32'h200, 32'h000080e7);
        if (taken !== 1 || target !== 32'h600 || hit !== 1) $fatal(1, "Conditional allocated indirect BTB");
        query(32'h400, 32'h008000ef);
        if (taken !== 1 || target !== 32'h408 || kind !== `RV32IM_PRED_JAL) $fatal(1, "JAL changed");
        query_valid = 0; #1;
        if (taken !== 0 || target !== 32'h404 || kind !== `RV32IM_PRED_NONE) $fatal(1, "Invalid query leaked");
        @(negedge clk); reset = 1;
        @(negedge clk); reset = 0;
        if (predictions !== 0 || correct !== 0) $fatal(1, "Warm reset stats");
        for (row = 0; row < (64 >> BANK_BITS); row = row + 1) begin
            dut.btb_tag[row] = 24'bx; dut.btb_target[row] = 32'bx; dut.btb_kind[row] = 2'bx;
        end
        query(32'h100, 32'h00208463);
        if (taken !== 0 || target !== 32'h104 || counter !== 2'b10) $fatal(1, "Warm reset did not invalidate trained direction");
        query(32'h100, 32'hfe208ee3);
        if (taken !== 1 || target !== 32'hfc) $fatal(1, "Poisoned payload leaked into direct branch");
        query(32'h200, 32'h000080e7);
        if (taken !== 0 || hit !== 0 || target !== 32'h204) $fatal(1, "Poisoned payload leaked into invalid JALR");
        train(32'h100, `RV32IM_PRED_BRANCH, 1, 32'h1234);
        query(32'h100, 32'hfe208ee3);
        if (taken !== 1 || target !== 32'hfc) $fatal(1, "Reallocation after poisoned reset");
        $display("PASS: direct conditional target BANK_BITS=%0d", BANK_BITS);
        $finish;
    end
    initial begin #3000; $fatal(1, "Predictor timeout"); end
endmodule
