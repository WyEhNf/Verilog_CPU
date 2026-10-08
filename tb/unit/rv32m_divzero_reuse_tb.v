`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32m_divzero_reuse_tb;
    reg clk=0,reset=1,request_valid=0,response_ready=0;
    always #5 clk=~clk;
    reg [5:0] operation=0;
    reg [31:0] a=0,b=0;
    reg [15:0] tag=1;
    wire [1:0] request_ready,response_valid;
    wire [63:0] values;
    wire [31:0] tags;
    wire [11:0] physicals;
    wire [1:0] rd_we;
    integer cases=0;
    generate for(genvar policy=0;policy<2;policy=policy+1) begin:g_pair
        rv32m_mdu_iterative #(.DIVZERO_REMAINDER_REUSE(policy),.TAG_WIDTH(16),.PHYS_ADDR_WIDTH(6)) dut (
            .clk_i(clk),.reset_i(reset),.flush_i(1'b0),.recovery_packet_i('0),
            .req_valid_i(request_valid),.req_ready_o(request_ready[policy]),.req_op_i(operation),
            .req_src1_i(a),.req_src2_i(b),.req_rob_tag_i(tag),.req_phys_rd_i(6'd5),.req_target_live_i(1'b1),
            .resp_valid_o(response_valid[policy]),.resp_ready_i(response_ready),
            .resp_value_o(values[policy*32 +: 32]),.resp_rob_tag_o(tags[policy*16 +: 16]),
            .resp_phys_rd_o(physicals[policy*6 +: 6]),.resp_rd_we_o(rd_we[policy]),
            .live_tag_valid_i(1'b0),.live_tag_i('0));
    end endgenerate
    task tick;begin @(posedge clk);#1;end endtask
    task probe(input [5:0] op,input [31:0] lhs,rhs,expected);
        integer cycles;
        begin
            @(negedge clk);operation=op;a=lhs;b=rhs;tag=16'(1+cases*8);request_valid=1;response_ready=0;#1;
            if(request_ready!==2'b11) $fatal(1,"sample MDU not ready");
            tick;@(negedge clk);request_valid=0;cycles=0;
            while(response_valid==0 && cycles<36) begin tick;cycles=cycles+1;end
            if(response_valid!==2'b11 || values!=={expected,expected} || tags!=={tag,tag} ||
               physicals!=={6'd5,6'd5} || rd_we!==2'b11)
                $fatal(1,"MDU sample op=%0d a=%h b=%h expected=%h got=%h",op,lhs,rhs,expected,values);
            if(cases==0) begin
                @(negedge clk);a=32'hdeadbeef;b=32'h12345678;
                tick;tick;
                if(response_valid!==2'b11 || values!=={expected,expected}) $fatal(1,"held completion changed");
            end
            @(negedge clk);response_ready=1;tick;cases=cases+1;
        end
    endtask
    initial begin
        tick;tick;@(negedge clk);reset=0;
        probe(`RV32IM_OP_REM,0,0,0);
        probe(`RV32IM_OP_REM,32'h12345678,0,32'h12345678);
        probe(`RV32IM_OP_REM,32'hfffffff9,0,32'hfffffff9);
        probe(`RV32IM_OP_REM,32'h80000000,0,32'h80000000);
        probe(`RV32IM_OP_REMU,32'h80000001,0,32'h80000001);
        probe(`RV32IM_OP_DIV,32'hfffffff9,0,32'hffffffff);
        probe(`RV32IM_OP_DIVU,7,0,32'hffffffff);
        probe(`RV32IM_OP_REM,32'hfffffff9,3,32'hffffffff);
        probe(`RV32IM_OP_REM,7,32'hfffffffd,1);
        probe(`RV32IM_OP_REM,32'h80000000,32'hffffffff,0);
        probe(`RV32IM_OP_DIV,32'h80000000,32'hffffffff,32'h80000000);
        probe(`RV32IM_OP_MULH,32'hfffffffe,3,32'hffffffff);
        $display("PASS: limited MDU remainder-reuse sample, 12 arithmetic points with response identity and one held completion");
        $finish;
    end
    initial begin #6000;$fatal(1,"small MDU sample timed out");end
endmodule
