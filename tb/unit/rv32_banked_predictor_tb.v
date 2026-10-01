`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_banked_predictor_tb;
    parameter integer WIDTH = 4;
    parameter integer DIRECT_BRANCH_TARGET = 0;
    reg clk = 0;
    always #5 clk = ~clk;
    reg reset, qvalid, fvalid, ftaken, fptaken;
    reg [31:0] pc, fpc, target, fptarget;
    reg [127:0] line;
    reg [1:0] fkind;
    wire [WIDTH-1:0] taken, hit, ref_taken, ref_hit;
    wire [WIDTH*32-1:0] predicted_target, ref_target, ref_count, ref_correct;
    wire [WIDTH*2-1:0] kind, counter, ref_kind, ref_counter;
    wire [WIDTH*6-1:0] bi, ref_bi;
    wire [WIDTH*4-1:0] ti, ref_ti;
    wire [31:0] count, correct;
    rv32_banked_predictor #(.FE_WIDTH(WIDTH), .DIRECT_BRANCH_TARGET(DIRECT_BRANCH_TARGET)) dut (
        .clk_i(clk), .reset_i(reset), .query_valid_i(qvalid), .query_pc_i(pc), .query_line_i(line),
        .pred_taken_o(taken), .pred_btb_hit_o(hit), .pred_target_o(predicted_target),
        .pred_kind_o(kind), .pred_counter_o(counter), .pred_bht_index_o(bi), .pred_btb_index_o(ti),
        .feedback_valid_i(fvalid), .feedback_pc_i(fpc), .feedback_kind_i(fkind),
        .feedback_taken_i(ftaken), .feedback_target_i(target), .feedback_pred_taken_i(fptaken),
        .feedback_pred_target_i(fptarget), .prediction_count_o(count), .correct_count_o(correct));
    genvar lane;
    generate for (lane = 0; lane < WIDTH; lane = lane + 1) begin : g_reference
        wire [2:0] word_index = {1'b0, pc[3:2]} + lane;
        wire [31:0] query_pc = pc + lane * 32'd4;
        wire [31:0] inst = line >> (word_index * 32);
        rv32_branch_predictor #(.DIRECT_BRANCH_TARGET(DIRECT_BRANCH_TARGET)) reference (
            .clk_i(clk), .reset_i(reset), .query_valid_i(qvalid && word_index < 4),
            .query_pc_i(query_pc), .query_inst_i(inst), .pred_taken_o(ref_taken[lane]),
            .pred_btb_hit_o(ref_hit[lane]), .pred_target_o(ref_target[lane*32 +: 32]),
            .pred_kind_o(ref_kind[lane*2 +: 2]), .pred_counter_o(ref_counter[lane*2 +: 2]),
            .pred_bht_index_o(ref_bi[lane*6 +: 6]), .pred_btb_index_o(ref_ti[lane*4 +: 4]),
            .feedback_valid_i(fvalid), .feedback_pc_i(fpc), .feedback_kind_i(fkind),
            .feedback_taken_i(ftaken), .feedback_target_i(target), .feedback_pred_taken_i(fptaken),
            .feedback_pred_target_i(fptarget), .prediction_count_o(ref_count[lane*32 +: 32]),
            .correct_count_o(ref_correct[lane*32 +: 32]));
    end endgenerate
    integer step, word_slot, seed = 32'h52fe9876;
    reg [31:0] random_word;
    task compare;
        begin
            // Compare invalid lanes too: counters and default targets are
            // preserved even when queries reach beyond the 16-byte response.
            if ({taken, hit, predicted_target, kind, counter, bi, ti} !==
                {ref_taken, ref_hit, ref_target, ref_kind, ref_counter, ref_bi, ref_ti} ||
                count !== ref_count[31:0] || correct !== ref_correct[31:0]) begin
                $display("FAIL: banked predictor width=%0d step=%0d pc=%h", WIDTH, step, pc);
                $display("taken %b/%b hit %b/%b counter %h/%h target %h/%h",
                         taken, ref_taken, hit, ref_hit, counter, ref_counter, predicted_target, ref_target);
                $finish(1);
            end
        end
    endtask
    initial begin
        reset = 1; qvalid = 0; fvalid = 0; ftaken = 0; fptaken = 0;
        pc = 0; fpc = 0; target = 0; fptarget = 0; line = 0; fkind = 0;
        @(posedge clk); #1;
        for (step = 0; step < 4000; step = step + 1) begin
            @(negedge clk);
            random_word = $random(seed);
            reset = step % 137 == 0;
            qvalid = random_word[0]; fvalid = random_word[3:2] != 0;
            ftaken = random_word[4]; fptaken = random_word[5]; fkind = random_word[7:6];
            pc = 32'h1000 + ($random(seed) & 32'h7fc);
            if (step % 97 == 0) pc = 32'hfffffffc;
            fpc = (step % 3 == 0) ? pc : 32'h1000 + ($random(seed) & 32'h7fc);
            target = $random(seed); fptarget = random_word[8] ? target : $random(seed);
            for (word_slot = 0; word_slot < 4; word_slot = word_slot + 1) begin
                random_word = $random(seed);
                case ((step + word_slot) % 5)
                    0: line[word_slot*32 +: 32] = {random_word[31:7], 7'h63};
                    1: line[word_slot*32 +: 32] = 32'h000080e7;
                    2: line[word_slot*32 +: 32] = {random_word[31:7], 7'h6f};
                    3: line[word_slot*32 +: 32] = 32'h00100093;
                    4: line[word_slot*32 +: 32] = 32'h000090e7;
                endcase
            end
            #1; compare;
            @(posedge clk); #1; compare;
        end
        $display("PASS: banked predictor width=%0d direct=%0d 4000 cycles exact replicated-reference comparison", WIDTH, DIRECT_BRANCH_TARGET);
        $finish(0);
    end
    initial begin #50000; $display("FAIL: banked predictor timeout"); $finish(1); end
endmodule
