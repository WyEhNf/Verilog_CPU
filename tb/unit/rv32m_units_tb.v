`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32m_units_tb;
    localparam integer TAGW = `RV32IM_ROB_TAG_WIDTH_DEFAULT;
    localparam integer PAW = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT;
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
    integer bad, cycle;

    rv32m_multiplier mul (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(mul_valid), .req_ready_o(mul_req_ready),
        .req_op_i(mul_op), .req_src1_i(mul_a), .req_src2_i(mul_b), .req_rob_tag_i(mul_tag), .req_phys_rd_i(mul_phys), .req_target_live_i(mul_live),
        .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_ready), .resp_value_o(mul_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
    );
    rv32m_divider div (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .req_valid_i(div_valid), .req_ready_o(div_req_ready),
        .req_op_i(div_op), .req_src1_i(div_a), .req_src2_i(div_b), .req_rob_tag_i(div_tag), .req_phys_rd_i(div_phys), .req_target_live_i(div_live),
        .resp_valid_o(div_resp_valid), .resp_ready_i(div_ready), .resp_value_o(div_value), .resp_rob_tag_o(div_resp_tag), .resp_phys_rd_o(div_resp_phys), .resp_rd_we_o(div_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
    );
    initial begin clk = 0; forever #5 clk = ~clk; end
    task clear_inputs;
        begin mul_valid=0; mul_ready=1; mul_op=0; mul_a=0; mul_b=0; mul_tag=16'h0101; mul_phys=0; mul_live=1; div_valid=0; div_ready=1; div_op=0; div_a=0; div_b=0; div_tag=16'h0201; div_phys=0; div_live=1; live_tag_valid=0; live_tag=0; flush=0; end
    endtask
    task wait_mul;
        input [31:0] expected;
        reg found;
        begin
            cycle=0; found=mul_resp_valid;
            while (!found && cycle < 12) begin @(posedge clk); #1; cycle=cycle+1; if (mul_resp_valid) found=1; end
            if (!found || mul_value !== expected || mul_resp_tag !== mul_tag || !mul_rd_we) bad=bad+1;
            if (found) begin @(posedge clk); #1; end
        end
    endtask
    task wait_div;
        input [31:0] expected;
        reg found;
        begin
            cycle=0; found=div_resp_valid;
            while (!found && cycle < 40) begin @(posedge clk); #1; cycle=cycle+1; if (div_resp_valid) found=1; end
            if (!found || div_value !== expected || div_resp_tag !== div_tag || !div_rd_we) bad=bad+1;
            if (found) begin @(posedge clk); #1; end
        end
    endtask
    initial begin
        bad=0; reset=1; clear_inputs(); #12; reset=0; #1;
        mul_op=`RV32IM_OP_MUL; mul_a=7; mul_b=9; mul_valid=1; @(posedge clk); #1; mul_valid=0; wait_mul(63);
        mul_op=`RV32IM_OP_MULH; mul_a=32'hffffffff; mul_b=32'd2; mul_valid=1; @(posedge clk); #1; mul_valid=0; wait_mul(32'hffffffff);
        mul_op=`RV32IM_OP_MULHSU; mul_a=32'hffffffff; mul_b=32'hffffffff; mul_valid=1; @(posedge clk); #1; mul_valid=0; wait_mul(32'hffffffff);
        mul_op=`RV32IM_OP_MULHU; mul_a=32'hffffffff; mul_b=32'h2; mul_valid=1; @(posedge clk); #1; mul_valid=0; wait_mul(1);
        // Back-to-back operations must preserve opcode/product alignment.
        mul_ready=1; mul_op=`RV32IM_OP_MUL; mul_a=2; mul_b=3; mul_valid=1; @(posedge clk); #1;
        mul_op=`RV32IM_OP_MULHU; mul_a=32'hffffffff; mul_b=2; @(posedge clk); #1; mul_valid=0; wait_mul(6); wait_mul(1);
        // Output backpressure retains a completed product.
        mul_op=`RV32IM_OP_MUL; mul_a=11; mul_b=12; mul_ready=0; mul_valid=1; @(posedge clk); #1; mul_valid=0; repeat (4) @(posedge clk); if (!mul_resp_valid || mul_value != 132) bad=bad+1; mul_ready=1; @(posedge clk); #1;
        // Flush kills all younger multiplier pipeline stages.
        mul_ready=0; mul_op=`RV32IM_OP_MUL; mul_a=3; mul_b=5; mul_valid=1; @(posedge clk); #1; mul_valid=0; flush=1; @(posedge clk); #1; flush=0; mul_ready=1; repeat (4) @(posedge clk); if (mul_resp_valid) bad=bad+1;

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
        $display("PASS: B-06 multiplier/divider"); $finish(0);
    end
endmodule
