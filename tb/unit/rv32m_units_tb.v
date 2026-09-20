`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32m_units_tb #(
    parameter integer MUL_IMPL = 0
);
    localparam integer TAGW = `RV32IM_ROB_TAG_WIDTH_DEFAULT;
    localparam integer PAW = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT;
    localparam integer MUL_WAIT = (MUL_IMPL == 2) ? 40 : 24;
    reg clk, reset, flush;
    reg mul_valid, mul_ready, div_valid, div_ready;
    reg [5:0] mul_op, div_op;
    reg [31:0] mul_a, mul_b, div_a, div_b;
    reg [TAGW-1:0] mul_tag, div_tag;
    reg [PAW-1:0] mul_phys, div_phys;
    reg mul_live, div_live, live_tag_valid;
    reg [TAGW-1:0] live_tag;
    wire mul_req_ready, mul_resp_valid, div_req_ready, div_resp_valid;
    wire [31:0] mul_value, div_value;
    wire [TAGW-1:0] mul_resp_tag, div_resp_tag;
    wire [PAW-1:0] mul_resp_phys, div_resp_phys;
    wire mul_rd_we, div_rd_we;
    integer bad, cycle, random_index, random_op_index;
    reg [31:0] random_a, random_b, random_expected;

    function [31:0] expected_multiply;
        input [5:0] op;
        input [31:0] operand_a;
        input [31:0] operand_b;
        reg signed [63:0] signed_a;
        reg signed [63:0] signed_b;
        reg signed [63:0] signed_unsigned_b;
        reg [63:0] unsigned_a;
        reg [63:0] unsigned_b;
        reg signed [63:0] product_signed;
        reg [63:0] product_unsigned;
        begin
            signed_a = {{32{operand_a[31]}}, operand_a};
            signed_b = {{32{operand_b[31]}}, operand_b};
            signed_unsigned_b = {32'b0, operand_b};
            unsigned_a = {32'b0, operand_a};
            unsigned_b = {32'b0, operand_b};
            product_signed = 64'b0;
            product_unsigned = 64'b0;
            case (op)
                `RV32IM_OP_MUL: begin
                    product_unsigned = unsigned_a * unsigned_b;
                    expected_multiply = product_unsigned[31:0];
                end
                `RV32IM_OP_MULH: begin
                    product_signed = signed_a * signed_b;
                    expected_multiply = product_signed[63:32];
                end
                `RV32IM_OP_MULHSU: begin
                    product_signed = signed_a * signed_unsigned_b;
                    expected_multiply = product_signed[63:32];
                end
                `RV32IM_OP_MULHU: begin
                    product_unsigned = unsigned_a * unsigned_b;
                    expected_multiply = product_unsigned[63:32];
                end
                default: expected_multiply = 32'b0;
            endcase
        end
    endfunction

    generate
        if (MUL_IMPL == 0) begin : gen_wallace_multiplier
            rv32m_multiplier mul (
                .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(mul_valid), .req_ready_o(mul_req_ready),
                .req_op_i(mul_op), .req_src1_i(mul_a), .req_src2_i(mul_b), .req_rob_tag_i(mul_tag), .req_phys_rd_i(mul_phys), .req_target_live_i(mul_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_ready), .resp_value_o(mul_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
            );
        end else if (MUL_IMPL == 1) begin : gen_radix4_multiplier
            rv32m_multiplier_radix4 mul (
                .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(mul_valid), .req_ready_o(mul_req_ready),
                .req_op_i(mul_op), .req_src1_i(mul_a), .req_src2_i(mul_b), .req_rob_tag_i(mul_tag), .req_phys_rd_i(mul_phys), .req_target_live_i(mul_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_ready), .resp_value_o(mul_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
            );
        end else begin : gen_unified_multiplier
            rv32m_mdu_iterative mul (
                .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(mul_valid), .req_ready_o(mul_req_ready),
                .req_op_i(mul_op), .req_src1_i(mul_a), .req_src2_i(mul_b), .req_rob_tag_i(mul_tag), .req_phys_rd_i(mul_phys), .req_target_live_i(mul_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_ready), .resp_value_o(mul_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
            );
        end
    endgenerate
    generate
    if (MUL_IMPL < 2) begin : gen_standalone_divider
    rv32m_divider div (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(div_valid), .req_ready_o(div_req_ready),
        .req_op_i(div_op), .req_src1_i(div_a), .req_src2_i(div_b), .req_rob_tag_i(div_tag), .req_phys_rd_i(div_phys), .req_target_live_i(div_live),
        .resp_valid_o(div_resp_valid), .resp_ready_i(div_ready), .resp_value_o(div_value), .resp_rob_tag_o(div_resp_tag), .resp_phys_rd_o(div_resp_phys), .resp_rd_we_o(div_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
    );
    end else begin : gen_unified_divider
        rv32m_mdu_iterative div (
            .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(div_valid), .req_ready_o(div_req_ready),
            .req_op_i(div_op), .req_src1_i(div_a), .req_src2_i(div_b), .req_rob_tag_i(div_tag), .req_phys_rd_i(div_phys), .req_target_live_i(div_live),
            .resp_valid_o(div_resp_valid), .resp_ready_i(div_ready), .resp_value_o(div_value), .resp_rob_tag_o(div_resp_tag), .resp_phys_rd_o(div_resp_phys), .resp_rd_we_o(div_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
        );
    end
    endgenerate
    initial begin clk = 0; forever #5 clk = ~clk; end
    task clear_inputs;
        begin mul_valid=0; mul_ready=1; mul_op=0; mul_a=0; mul_b=0; mul_tag=16'h0101; mul_phys=0; mul_live=1; div_valid=0; div_ready=1; div_op=0; div_a=0; div_b=0; div_tag=16'h0201; div_phys=0; div_live=1; live_tag_valid=0; live_tag=0; flush=0; end
    endtask
    task issue_mul;
        input [5:0] operation;
        input [31:0] operand_a;
        input [31:0] operand_b;
        begin
            while (!mul_req_ready) @(posedge clk);
            #1; mul_op=operation; mul_a=operand_a; mul_b=operand_b; mul_valid=1;
            @(posedge clk); #1; mul_valid=0;
        end
    endtask
    task wait_mul;
        input [31:0] expected;
        reg found;
        begin
            cycle=0; found=mul_resp_valid;
            while (!found && cycle < MUL_WAIT) begin @(posedge clk); #1; cycle=cycle+1; if (mul_resp_valid) found=1; end
            if (!found || mul_value !== expected || mul_resp_tag !== mul_tag || !mul_rd_we) begin
                $display("FAIL_DETAIL: mul op=%0d a=%08x b=%08x found=%b got=%08x expected=%08x",
                         mul_op, mul_a, mul_b, found, mul_value, expected);
                bad=bad+1;
            end
            if (found) begin @(posedge clk); #1; end
        end
    endtask
    task wait_div;
        input [31:0] expected;
        reg found;
        begin
            cycle=0; found=div_resp_valid;
            while (!found && cycle < 40) begin @(posedge clk); #1; cycle=cycle+1; if (div_resp_valid) found=1; end
            if (!found || div_value !== expected || div_resp_tag !== div_tag || !div_rd_we) begin
                $display("FAIL_DETAIL: div op=%0d a=%08x b=%08x found=%b got=%08x expected=%08x",
                         div_op, div_a, div_b, found, div_value, expected);
                bad=bad+1;
            end
            if (found) begin @(posedge clk); #1; end
        end
    endtask
    initial begin
        bad=0; reset=1; clear_inputs(); #12; reset=0; #1;
        issue_mul(`RV32IM_OP_MUL, 7, 9); wait_mul(63);
        issue_mul(`RV32IM_OP_MULH, 32'hffffffff, 32'd2); wait_mul(32'hffffffff);
        issue_mul(`RV32IM_OP_MULHSU, 32'hffffffff, 32'hffffffff); wait_mul(32'hffffffff);
        issue_mul(`RV32IM_OP_MULHU, 32'hffffffff, 32'h2); wait_mul(1);
        // Back-to-back operations must preserve opcode/product alignment.
        if (MUL_IMPL == 0) begin
            mul_ready=1; mul_op=`RV32IM_OP_MUL; mul_a=2; mul_b=3; mul_valid=1; @(posedge clk); #1;
            // The low-latency Wallace result is legitimately consumed on
            // the next ready edge, so sample each response while launching
            // the following request rather than waiting until both launches
            // have completed.
            if (!mul_resp_valid || mul_value !== 32'd6) begin
                $display("FAIL_DETAIL: back-to-back first valid=%b value=%08x", mul_resp_valid, mul_value);
                bad=bad+1;
            end
            mul_op=`RV32IM_OP_MULHU; mul_a=32'hffffffff; mul_b=2; @(posedge clk); #1;
            if (!mul_resp_valid || mul_value !== 32'd1) begin
                $display("FAIL_DETAIL: back-to-back second valid=%b value=%08x", mul_resp_valid, mul_value);
                bad=bad+1;
            end
            mul_valid=0;
            // Retire the second ready response before beginning the
            // independent backpressure scenario below.
            @(posedge clk); #1;
        end else begin
            issue_mul(`RV32IM_OP_MUL, 2, 3); wait_mul(6);
            issue_mul(`RV32IM_OP_MULHU, 32'hffffffff, 2); wait_mul(1);
        end
        // Output backpressure retains a completed product.
        mul_ready=0; #1; issue_mul(`RV32IM_OP_MUL, 11, 12);
        cycle=0; while (!mul_resp_valid && cycle<MUL_WAIT) begin @(posedge clk); #1; cycle=cycle+1; end
        if (!mul_resp_valid || mul_value != 132) begin
            $display("FAIL_DETAIL: mul backpressure initial valid=%b value=%08x", mul_resp_valid, mul_value);
            bad=bad+1;
        end
        repeat (4) begin @(posedge clk); #1; if (!mul_resp_valid || mul_value != 132) begin
            $display("FAIL_DETAIL: mul backpressure hold valid=%b value=%08x", mul_resp_valid, mul_value);
            bad=bad+1;
        end end
        mul_ready=1; @(posedge clk); #1;
        // Flush kills all younger multiplier pipeline stages.
        mul_ready=0; issue_mul(`RV32IM_OP_MUL, 3, 5); flush=1; @(posedge clk); #1; flush=0; mul_ready=1; repeat (20) @(posedge clk); if (mul_resp_valid) bad=bad+1;

        // Random arithmetic comparison covers all four signedness modes.
        for (random_index = 0; random_index < 128; random_index = random_index + 1) begin
            random_a = $random;
            random_b = $random;
            for (random_op_index = 0; random_op_index < 4; random_op_index = random_op_index + 1) begin
                case (random_op_index)
                    0: mul_op = `RV32IM_OP_MUL;
                    1: mul_op = `RV32IM_OP_MULH;
                    2: mul_op = `RV32IM_OP_MULHSU;
                    default: mul_op = `RV32IM_OP_MULHU;
                endcase
                random_expected = expected_multiply(mul_op, random_a, random_b);
                issue_mul(mul_op, random_a, random_b);
                wait_mul(random_expected);
            end
        end

        div_op=`RV32IM_OP_DIV; div_a=100; div_b=7; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(14);
        div_op=`RV32IM_OP_REM; div_a=32'hffffff9c; div_b=7; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(32'hfffffffe);
        div_op=`RV32IM_OP_DIVU; div_a=32'hffffffff; div_b=16; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(32'h0fffffff);
        div_op=`RV32IM_OP_REMU; div_a=32'hffffffff; div_b=16; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(15);
        div_op=`RV32IM_OP_DIV; div_a=32'h80000000; div_b=32'hffffffff; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(32'h80000000);
        div_op=`RV32IM_OP_REM; div_a=32'h80000000; div_b=32'hffffffff; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(0);
        div_op=`RV32IM_OP_DIVU; div_a=32'h12345678; div_b=0; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(32'hffffffff);
        div_op=`RV32IM_OP_REM; div_a=32'hfffffffb; div_b=0; div_valid=1; @(posedge clk); #1; div_valid=0; wait_div(32'hfffffffb);
        // Divider flush must release its busy state and suppress the result.
        div_op=`RV32IM_OP_DIVU; div_a=100; div_b=3; div_valid=1; @(posedge clk); #1; div_valid=0; repeat (5) @(posedge clk); flush=1; @(posedge clk); #1; flush=0; #1; if (!div_req_ready) bad=bad+1;
        if (bad != 0) begin $display("FAIL: B-06 M units checks=%0d", bad); $finish(1); end
        $display("PASS: B-06 multiplier/divider MUL_IMPL=%0d", MUL_IMPL); $finish(0);
    end
endmodule
