`timescale 1ns/1ps
// Both policies must return the correct instruction after a same-set refill
// collides with an unaccepted hit. Policy0 may replay that request as a miss.
module rv32_icache_refill_policy_tb;
    parameter integer LINES=128, MSHRS=8, PROTECT=1;
    localparam integer STRIDE=(LINES/2)*16;
    reg clk=0, reset=1;
    always #5 clk=~clk;
    reg req_valid=0, resp_ready=0, reply_valid=0;
    reg [31:0] req_pc=0, reply_addr=0;
    reg [127:0] reply_data=0;
    reg [7:0] reply_id=0;
    wire req_ready, resp_valid, resp_error, mem_valid, mem_ready;
    wire [31:0] resp_pc, resp_addr, mem_addr;
    wire [127:0] resp_data;
    wire [1:0] resp_epoch;
    wire [7:0] mem_id;
    reg [31:0] pending_addr [0:15];
    reg [7:0] pending_id [0:15];
    reg pending_used [0:15];
    integer issued=0, accepted=0, n, slot, step=0;
    localparam [127:0] A={4{32'h00100013}}, B={4{32'h00200013}}, C={4{32'h00300013}};
    rv32_icache_nonblocking #(.EPOCH_WIDTH(2),.MSHR_ENTRIES(MSHRS),
        .CACHE_LINES(LINES),.CACHE_WAYS(2),.NEXT_LINE_PREFETCH(0),
        .REFILL_PROTECT_PENDING_HIT(PROTECT)) dut (
        .clk_i(clk),.reset_i(reset),.current_epoch_i(2'd0),
        .if_req_valid_i(req_valid),.if_req_ready_o(req_ready),.if_req_pc_i(req_pc),.if_req_epoch_i(2'd0),
        .if_resp_valid_o(resp_valid),.if_resp_ready_i(resp_ready),.if_resp_pc_o(resp_pc),
        .if_resp_line_addr_o(resp_addr),.if_resp_line_data_o(resp_data),.if_resp_epoch_o(resp_epoch),
        .if_resp_error_o(resp_error),.mem_req_valid_o(mem_valid),.mem_req_ready_i(1'b1),
        .mem_req_line_addr_o(mem_addr),.mem_req_id_o(mem_id),.mem_resp_valid_i(reply_valid),
        .mem_resp_ready_o(mem_ready),.mem_resp_line_addr_i(reply_addr),.mem_resp_data_i(reply_data),
        .mem_resp_id_i(reply_id),.mem_resp_error_i(1'b0)
    );
    always @(posedge clk) begin
        if(!reset && mem_valid) begin
            if(issued>=16) $fatal(1,"Unexpected repeated memory request");
            pending_addr[issued]=mem_addr;pending_id[issued]=mem_id;pending_used[issued]=0;issued=issued+1;
        end
        if(!reset && req_valid && req_ready) accepted=accepted+1;
    end
    task submit;
        input [31:0] pc;
        begin
            @(negedge clk);req_pc=pc;req_valid=1;
            #1;while(!req_ready) begin @(negedge clk);#1;end
            @(negedge clk);req_valid=0;
        end
    endtask
    task find_pending;
        input [31:0] address;
        begin
            slot=-1;
            while(slot<0) begin
                for(n=0;n<issued;n=n+1) if(!pending_used[n] && pending_addr[n]==address) slot=n;
                if(slot<0) @(negedge clk);
            end
        end
    endtask
    task return_line;
        input [31:0] address;
        input [127:0] data;
        begin
            find_pending(address);@(negedge clk);
            reply_addr=address;reply_id=pending_id[slot];pending_used[slot]=1;
            reply_data=data;reply_valid=1;
            #1;while(!mem_ready) begin @(negedge clk);#1;end
            @(negedge clk);reply_valid=0;
        end
    endtask
    task expect_response;
        input [31:0] pc;
        input [127:0] data;
        begin
            #1;if(resp_valid!==1 || resp_pc!==pc || resp_addr!==pc || resp_data!==data ||
                  resp_epoch!==0 || resp_error!==0)
                $fatal(1,"Wrong response step=%0d pc=%h got=%h data=%h",step,pc,resp_pc,resp_data);
        end
    endtask
    task consume;
        begin @(negedge clk);resp_ready=1;@(negedge clk);resp_ready=0;end
    endtask
    initial begin
        repeat(3) @(negedge clk);reset=0;
        step=1;submit(0);return_line(0,A);expect_response(0,A);consume;
        step=2;submit(STRIDE);return_line(STRIDE,B);expect_response(STRIDE,B);consume;
        step=3;submit(STRIDE);expect_response(STRIDE,B);consume;
        // A is the LRU way. C refills that same set while fetch A waits.
        step=4;submit(2*STRIDE);find_pending(2*STRIDE);@(negedge clk);
        reply_addr=2*STRIDE;reply_id=pending_id[slot];pending_used[slot]=1;
        reply_data=C;reply_valid=1;req_pc=0;req_valid=1;
        #1;if(mem_ready!==1 || req_ready!==0) $fatal(1,"Hit accepted while SRAM refilling");
        @(negedge clk);reply_valid=0;expect_response(2*STRIDE,C);
        repeat(2) begin @(negedge clk);expect_response(2*STRIDE,C);end
        @(negedge clk);resp_ready=1;
        #1;if(req_ready!==1) $fatal(1,"Pending fetch not admitted after refill");
        @(negedge clk);req_valid=0;resp_ready=0;
        step=5;
        if(PROTECT==0) begin
            #1;if(resp_valid!==0) $fatal(1,"Evicted A was incorrectly treated as a hit");
            return_line(0,A);
        end
        expect_response(0,A);
        repeat(2) begin @(negedge clk);expect_response(0,A);end
        consume;
        if(accepted!==5 || issued!==((PROTECT==0)?4:3))
            $fatal(1,"Requests lost/duplicated or policy not exercised: accepted=%0d issued=%0d",accepted,issued);
        $display("PASS: pending hit refill lines=%0d mshrs=%0d protect=%0d accepted=%0d memory=%0d",LINES,MSHRS,PROTECT,accepted,issued);
        $finish;
    end
    initial begin #100000;$fatal(1,"Refill policy timeout step=%0d",step);end
endmodule
