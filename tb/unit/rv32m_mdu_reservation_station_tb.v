`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32m_mdu_reservation_station_tb;
    reg clk, reset, flush, issue_valid, completion_ready, live_tag_valid;
    reg [5:0] issue_op;
    reg [31:0] issue_src1, issue_src2;
    reg [15:0] issue_tag, live_tag;
    reg [5:0] issue_phys;
    reg issue_live;
    wire issue_ready, completion_valid, completion_rd_we;
    wire [31:0] completion_value;
    wire [15:0] completion_tag;
    wire [5:0] completion_phys;
    integer bad, cycles;
    rv32m_mdu_reservation_station dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .issue_valid_i(issue_valid), .issue_ready_o(issue_ready), .issue_op_i(issue_op),
        .issue_src1_i(issue_src1), .issue_src2_i(issue_src2), .issue_rob_tag_i(issue_tag), .issue_phys_rd_i(issue_phys), .issue_target_live_i(issue_live),
        .completion_valid_o(completion_valid), .completion_ready_i(completion_ready), .completion_value_o(completion_value), .completion_rob_tag_o(completion_tag), .completion_phys_rd_o(completion_phys), .completion_rd_we_o(completion_rd_we), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
    );
    initial begin clk=0; forever #5 clk=~clk; end
    task clear_inputs;
        begin issue_valid=0; issue_op=0; issue_src1=0; issue_src2=0; issue_tag=16'h0101; issue_phys=0; issue_live=1; completion_ready=1; live_tag_valid=0; live_tag=0; flush=0; end
    endtask
    initial begin
        bad=0; reset=1; clear_inputs(); #12; reset=0; #1;
        issue_op=`RV32IM_OP_MUL; issue_src1=6; issue_src2=7; issue_valid=1; @(posedge clk); #1; issue_valid=0;
        if (issue_ready) bad=bad+1;
        cycles=0; while (!completion_valid && cycles<12) begin @(posedge clk); #1; cycles=cycles+1; end
        if (!completion_valid || completion_value!=42 || completion_tag!=16'h0101 || !completion_rd_we) bad=bad+1;
        @(posedge clk); #1;
        issue_op=`RV32IM_OP_DIVU; issue_src1=100; issue_src2=9; issue_tag=16'h0201; issue_valid=1; @(posedge clk); #1; issue_valid=0;
        if (issue_ready) bad=bad+1;
        cycles=0; while (!completion_valid && cycles<40) begin @(posedge clk); #1; cycles=cycles+1; end
        if (!completion_valid || completion_value!=11 || completion_tag!=16'h0201) bad=bad+1;
        @(posedge clk); #1;
        // A queued operation is killed by recovery before it reaches a unit.
        issue_op=`RV32IM_OP_MUL; issue_src1=8; issue_src2=8; issue_valid=1; @(posedge clk); #1; issue_valid=0; flush=1; @(posedge clk); #1; flush=0; repeat (5) @(posedge clk); if (completion_valid) bad=bad+1;
        if (bad != 0) begin $display("FAIL: B-06 MDU RS checks=%0d", bad); $finish(1); end
        $display("PASS: B-06 MDU RS"); $finish(0);
    end
endmodule
