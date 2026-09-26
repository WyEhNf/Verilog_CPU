`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32i_alu_compare_tb;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg reset = 1'b1;
    reg issue_valid = 1'b0;
    reg [`RV32IM_OP_WIDTH-1:0] op = 0;
    reg [31:0] lhs = 0, rhs = 0;
    wire issue_ready, exec_valid, branch_taken, redirect_valid;
    wire [31:0] exec_value;
    integer seed, trial, operation;
    reg expected;
    reg [31:0] expected_value;

    rv32i_alu dut (
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0),
        .issue_valid_i(issue_valid), .issue_ready_o(issue_ready),
        .issue_op_i(op), .issue_pc_i(32'h100), .issue_imm_i(32'h20),
        .issue_src1_value_i(lhs), .issue_src2_value_i(rhs),
        .issue_store_data_i(32'b0), .issue_phys_rd_i(6'b0),
        .issue_rob_tag_i(16'h0001), .issue_epoch_i(4'b0),
        .issue_target_live_i(1'b1), .issue_pred_taken_i(1'b0),
        .issue_pred_target_i(32'h120), .issue_pred_kind_i(2'b0),
        .issue_mem_size_i(2'b0), .issue_mem_unsigned_i(1'b0),
        .exec_valid_o(exec_valid), .exec_ready_i(1'b1),
        .exec_value_o(exec_value), .exec_branch_taken_o(branch_taken),
        .exec_redirect_valid_o(redirect_valid),
        .live_tag_valid_i(1'b0), .live_tag_i(16'b0)
    );

    initial begin
        seed = 32'h5729e11b;
        #12 reset = 1'b0;
        for (trial = 0; trial < 3000; trial = trial + 1) begin
            lhs = $random(seed);
            rhs = $random(seed);
            if (trial % 32 == 0) rhs = lhs;
            if (trial % 32 == 1) begin lhs = 32'h80000000; rhs = 32'h7fffffff; end
            if (trial % 32 == 2) begin lhs = 0; rhs = 32'hffffffff; end
            for (operation = 0; operation < 11; operation = operation + 1) begin
                @(negedge clk);
                issue_valid = 1'b1;
                case (operation)
                    0: begin op = `RV32IM_OP_BEQ; expected = lhs == rhs; end
                    1: begin op = `RV32IM_OP_BNE; expected = lhs != rhs; end
                    2: begin op = `RV32IM_OP_BLT; expected = $signed(lhs) < $signed(rhs); end
                    3: begin op = `RV32IM_OP_BGE; expected = $signed(lhs) >= $signed(rhs); end
                    4: begin op = `RV32IM_OP_BLTU; expected = lhs < rhs; end
                    5: begin op = `RV32IM_OP_BGEU; expected = lhs >= rhs; end
                    6: begin op = `RV32IM_OP_SLT; expected = $signed(lhs) < $signed(rhs); end
                    7: begin op = `RV32IM_OP_SLTU; expected = lhs < rhs; end
                    8: begin op = `RV32IM_OP_ADD; expected_value = lhs + rhs; end
                    9: begin op = `RV32IM_OP_SUB; expected_value = lhs - rhs; end
                    10: begin op = `RV32IM_OP_ADDI; expected_value = lhs + 32'h20; end
                endcase
                if (!issue_ready) $fatal(1, "ALU not ready trial=%0d op=%0d", trial, operation);
                @(posedge clk); #1;
                if (!exec_valid) $fatal(1, "ALU completion missing trial=%0d op=%0d", trial, operation);
                if (operation < 6) begin
                    if (branch_taken !== expected || redirect_valid !== expected)
                        $fatal(1, "branch compare mismatch trial=%0d op=%0d lhs=%h rhs=%h expected=%b got=%b",
                            trial, operation, lhs, rhs, expected, branch_taken);
                end else if (operation < 8 && exec_value !== {31'b0, expected}) begin
                    $fatal(1, "SLT compare mismatch trial=%0d op=%0d lhs=%h rhs=%h expected=%b got=%h",
                        trial, operation, lhs, rhs, expected, exec_value);
                end else if (operation >= 8 && exec_value !== expected_value) begin
                    $fatal(1, "adder mismatch trial=%0d op=%0d lhs=%h rhs=%h expected=%h got=%h",
                        trial, operation, lhs, rhs, expected_value, exec_value);
                end
            end
        end
        $display("PASS: ALU compare/add 3000 pairs x 11 ops");
        $finish;
    end
endmodule
