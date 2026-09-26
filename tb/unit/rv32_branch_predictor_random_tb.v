`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_branch_predictor_random_tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg reset, qvalid, fvalid, ftaken, fptaken;
    reg [31:0] qpc, inst, fpc, target, fptarget;
    reg [1:0] fkind;
    wire taken, hit;
    wire [31:0] predicted_target, count, correct;
    wire [1:0] kind, counter;
    wire [5:0] bi;
    wire [3:0] ti;
    rv32_branch_predictor dut (
        .clk_i(clk), .reset_i(reset), .query_valid_i(qvalid), .query_pc_i(qpc),
        .query_inst_i(inst), .pred_taken_o(taken), .pred_target_o(predicted_target),
        .pred_kind_o(kind), .pred_btb_hit_o(hit), .pred_bht_index_o(bi),
        .pred_btb_index_o(ti), .pred_counter_o(counter), .feedback_valid_i(fvalid),
        .feedback_pc_i(fpc), .feedback_kind_i(fkind), .feedback_taken_i(ftaken),
        .feedback_target_i(target), .feedback_pred_taken_i(fptaken),
        .feedback_pred_target_i(fptarget), .prediction_count_o(count), .correct_count_o(correct));

    reg [1:0] history [0:255];
    reg valid [0:63];
    reg [23:0] tags [0:63];
    reg [31:0] targets [0:63];
    reg [1:0] kinds [0:63];
    reg [31:0] expected_count = 0, expected_correct = 0;
    reg expected_taken, expected_hit;
    reg [1:0] expected_kind;
    reg [31:0] expected_target, immediate, random_word;
    integer step, slot, seed = 32'h1b7b1234;

    task model_tick;
        begin
            if (reset) begin
                expected_count = 0;
                expected_correct = 0;
                for (slot = 0; slot < 256; slot = slot + 1) history[slot] = 2'b10;
                for (slot = 0; slot < 64; slot = slot + 1) begin
                    valid[slot] = 0;
                    tags[slot] = 0;
                    targets[slot] = 0;
                    kinds[slot] = `RV32IM_PRED_NONE;
                end
            end else if (fvalid) begin
                expected_count = expected_count + 1;
                if ((fptaken == ftaken) && (!ftaken || (fptarget == target)))
                    expected_correct = expected_correct + 1;
                if (fkind == `RV32IM_PRED_BRANCH) begin
                    if (ftaken && history[fpc[9:2]] != 3)
                        history[fpc[9:2]] = history[fpc[9:2]] + 1;
                    else if (!ftaken && history[fpc[9:2]] != 0)
                        history[fpc[9:2]] = history[fpc[9:2]] - 1;
                    if (ftaken) begin
                        valid[fpc[7:2]] = 1;
                        tags[fpc[7:2]] = fpc[31:8];
                        targets[fpc[7:2]] = target;
                        kinds[fpc[7:2]] = `RV32IM_PRED_BRANCH;
                    end
                end else if (fkind == `RV32IM_PRED_JALR && ftaken) begin
                    valid[fpc[7:2]] = 1;
                    tags[fpc[7:2]] = fpc[31:8];
                    targets[fpc[7:2]] = target & 32'hfffffffe;
                    kinds[fpc[7:2]] = `RV32IM_PRED_JALR;
                end
            end
        end
    endtask

    task check_query;
        begin
            expected_taken = 0;
            expected_hit = 0;
            expected_kind = `RV32IM_PRED_NONE;
            expected_target = qpc + 4;
            if (qvalid) begin
                case (inst[6:0])
                    7'h63: begin
                        expected_kind = `RV32IM_PRED_BRANCH;
                        expected_hit = valid[qpc[7:2]] && tags[qpc[7:2]] == qpc[31:8] &&
                                       kinds[qpc[7:2]] == `RV32IM_PRED_BRANCH;
                        immediate = {{19{inst[31]}}, inst[31], inst[7], inst[30:25], inst[11:8], 1'b0};
                        if (expected_hit && history[qpc[9:2]][1]) begin
                            expected_taken = 1;
                            expected_target = targets[qpc[7:2]];
                        end else if (!expected_hit && immediate[31]) begin
                            expected_taken = 1;
                            expected_target = qpc + immediate;
                        end
                    end
                    7'h6f: begin
                        expected_kind = `RV32IM_PRED_JAL;
                        expected_taken = 1;
                        immediate = {{11{inst[31]}}, inst[31], inst[19:12], inst[20], inst[30:21], 1'b0};
                        expected_target = qpc + immediate;
                    end
                    7'h67: if (inst[14:12] == 0) begin
                        expected_kind = `RV32IM_PRED_JALR;
                        expected_hit = valid[qpc[7:2]] && tags[qpc[7:2]] == qpc[31:8] &&
                                       kinds[qpc[7:2]] == `RV32IM_PRED_JALR;
                        if (expected_hit) begin
                            expected_taken = 1;
                            expected_target = targets[qpc[7:2]];
                        end
                    end
                    default: begin end
                endcase
            end
            if ({taken, hit, kind, predicted_target} !==
                {expected_taken, expected_hit, expected_kind, expected_target} ||
                counter !== history[qpc[9:2]] || bi !== qpc[7:2] || ti !== qpc[5:2] ||
                count !== expected_count || correct !== expected_correct) begin
                $display("FAIL: predictor random oracle step=%0d pc=%h inst=%h", step, qpc, inst);
                $finish(1);
            end
        end
    endtask

    initial begin
        reset = 1; qvalid = 0; fvalid = 0; ftaken = 0; fptaken = 0;
        qpc = 0; inst = 0; fpc = 0; target = 0; fptarget = 0; fkind = 0;
        for (step = 0; step < 4000; step = step + 1) begin
            @(negedge clk);
            reset = (step % 157 == 0);
            random_word = $random(seed); qvalid = random_word[0];
            qpc = 32'h1000 + (random_word & 32'h3fc);
            fpc = 32'h1000 + ($random(seed) & 32'h3fc);
            random_word = $random(seed); fkind = random_word[1:0];
            fvalid = random_word[3:2] != 0;
            ftaken = random_word[4]; fptaken = random_word[5];
            target = $random(seed); fptarget = random_word[6] ? target : $random(seed);
            random_word = $random(seed);
            case (step % 5)
                0: inst = {random_word[31:7], 7'h63};
                1: inst = 32'h000080e7;
                2: inst = {random_word[31:7], 7'h6f};
                3: inst = 32'h00100093;
                4: inst = 32'h000090e7; // reserved JALR funct3 must not predict
            endcase
            @(posedge clk);
            model_tick;
            #1; check_query;
        end
        $display("PASS: predictor random oracle 4000 cycles including warm resets");
        $finish(0);
    end
    initial begin #50000; $display("FAIL: predictor random timeout"); $finish(1); end
endmodule
