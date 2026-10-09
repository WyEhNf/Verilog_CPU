`timescale 1ns/1ps
// One finite real-transaction pair; all state is allocated by public requests/refills.
module rv32_icache_class_send_tb;
    reg clk=0,reset=1;
    always #5 clk=~clk;
    reg [3:0] epoch=4'h9;
    reg req_valid=0,resp_ready=0,mem_gate=0,reply_valid=0,reply_error=0;
    reg [31:0] req_pc=0,reply_addr=0;
    reg [7:0] reply_id=0;
    reg [127:0] reply_data=0;
    wire [1:0] req_ready,resp_valid,resp_error,mem_valid,mem_ready;
    wire [31:0] resp_pc[0:1],resp_addr[0:1],mem_addr[0:1];
    wire [127:0] resp_data[0:1];
    wire [3:0] resp_epoch[0:1];
    wire [7:0] mem_id[0:1];
    wire [4:0] events[0:1];
    localparam [127:0] NOPS={4{32'h00000013}};
    localparam [127:0] JUMP={{3{32'h00000013}},32'h7000006f}; // 0x100 -> 0x800
    reg [31:0] issued_addr[0:15];
    reg [7:0] issued_id[0:15];
    integer issued=0,replies=0,held=0,three_classes=0,stale_checked=0,step=0,n,slot;
    integer demand_count,control_count,sequential_count;
    generate for(genvar policy=0;policy<2;policy=policy+1) begin:g_pair
        rv32_icache_nonblocking #(.EPOCH_WIDTH(4),.MSHR_ENTRIES(8),.CLASS_SEND_SELECT(policy),
            .MSHR_STATIC_WRITES(1),.MSHR_STATE_BANKS(1),.CACHE_LINES(128),.CACHE_WAYS(2),
            .TAG_MATCH_PARALLEL(1),.TAG_REGION_BITS(12),.LOCAL_RESPONSE_READY(1),
            .REQUEST_PIPELINE(1),.OWNER_PAYLOAD_SELECT(1),.LOOP_BUFFER_LINES(16),.LOOP_BUFFER_SRAM(1),
            .NEXT_LINE_PREFETCH(1),.PREFETCH_DISTANCE(7)) dut (
            .clk_i(clk),.reset_i(reset),.current_epoch_i(epoch),
            .if_req_valid_i(req_valid),.if_req_ready_o(req_ready[policy]),.if_req_pc_i(req_pc),.if_req_epoch_i(epoch),
            .if_resp_valid_o(resp_valid[policy]),.if_resp_ready_i(resp_ready),.if_resp_pc_o(resp_pc[policy]),
            .if_resp_line_addr_o(resp_addr[policy]),.if_resp_line_data_o(resp_data[policy]),
            .if_resp_epoch_o(resp_epoch[policy]),.if_resp_error_o(resp_error[policy]),
            .mem_req_valid_o(mem_valid[policy]),.mem_req_ready_i(mem_gate),
            .mem_req_line_addr_o(mem_addr[policy]),.mem_req_id_o(mem_id[policy]),
            .mem_resp_valid_i(reply_valid),.mem_resp_ready_o(mem_ready[policy]),
            .mem_resp_line_addr_i(reply_addr),.mem_resp_data_i(reply_data),.mem_resp_id_i(reply_id),
            .mem_resp_error_i(reply_error),.event_request_o(events[policy][0]),.event_hit_o(events[policy][1]),
            .event_miss_o(events[policy][2]),.event_refill_o(events[policy][3]),.event_stall_o(events[policy][4]));
    end endgenerate
    always @(posedge clk) if(!reset) begin
        if(req_ready[0]!==req_ready[1] || resp_valid[0]!==resp_valid[1] ||
           mem_valid[0]!==mem_valid[1] || mem_ready[0]!==mem_ready[1] || events[0]!==events[1] ||
           mem_addr[0]!==mem_addr[1] || mem_id[0]!==mem_id[1])
            $fatal(1,"Class pair public control/full raw request differs step=%0d",step);
        if(resp_valid[0] && {resp_pc[0],resp_addr[0],resp_data[0],resp_epoch[0],resp_error[0]} !==
                            {resp_pc[1],resp_addr[1],resp_data[1],resp_epoch[1],resp_error[1]})
            $fatal(1,"Class pair full instruction reply differs step=%0d",step);
        for(integer row=0;row<8;row=row+1) begin
            if({g_pair[0].dut.mshr_valid[row],g_pair[0].dut.mshr_sent[row],g_pair[0].dut.mshr_prefetch[row],g_pair[0].dut.mshr_control_prefetch[row]} !==
               {g_pair[1].dut.mshr_valid[row],g_pair[1].dut.mshr_sent[row],g_pair[1].dut.mshr_prefetch[row],g_pair[1].dut.mshr_control_prefetch[row]})
                $fatal(1,"Class pair MSHR lifecycle differs row=%0d",row);
            if(g_pair[0].dut.mshr_valid[row] &&
               {g_pair[0].dut.mshr_line[row],g_pair[0].dut.mshr_pc[row],g_pair[0].dut.mshr_txn_epoch[row],g_pair[0].dut.mshr_demand_epoch[row]} !==
               {g_pair[1].dut.mshr_line[row],g_pair[1].dut.mshr_pc[row],g_pair[1].dut.mshr_txn_epoch[row],g_pair[1].dut.mshr_demand_epoch[row]})
                $fatal(1,"Class pair full MSHR identity differs row=%0d",row);
        end
        if(mem_valid[0] && mem_gate) begin
            if(issued>=16) $fatal(1,"Unexpected repeated send");
            issued_addr[issued]=mem_addr[0];issued_id[issued]=mem_id[0];issued=issued+1;
        end
        if(resp_valid[0] && resp_ready) replies=replies+1;
        if(resp_valid[0] && !resp_ready) held=held+1;
    end
    task submit;
        input [31:0] address;
        begin
            @(negedge clk);req_pc=address;req_valid=1;
            #1;while(!req_ready[0]) begin @(negedge clk);#1;end
            @(negedge clk);req_valid=0;
            repeat(3) @(negedge clk);
        end
    endtask
    task send_one;
        input [31:0] address;
        input [3:0] expected_epoch;
        begin
            @(negedge clk);#1;
            if(!mem_valid[0] || mem_addr[0]!==address || mem_id[0][3:0]!==expected_epoch)
                $fatal(1,"Wrong class priority step=%0d wanted=%h got=%h id=%h",step,address,mem_addr[0],mem_id[0]);
            mem_gate=1;
            @(negedge clk);mem_gate=0;
        end
    endtask
    task return_line;
        input [31:0] address;
        input [127:0] data;
        input error;
        begin
            slot=-1;
            for(n=0;n<issued;n=n+1) if(issued_addr[n]==address) slot=n;
            if(slot<0) $fatal(1,"Fixture returning unsent line");
            @(negedge clk);reply_valid=1;reply_addr=address;reply_id=issued_id[slot];reply_data=data;reply_error=error;
            #1;while(!mem_ready[0]) begin @(negedge clk);#1;end
            @(negedge clk);reply_valid=0;reply_error=0;
        end
    endtask
    task expect_reply;
        input [31:0] address;
        input [127:0] data;
        input error;
        begin
            #1;while(!resp_valid[0]) begin @(negedge clk);#1;end
            if(resp_pc[0]!==address || resp_addr[0]!==address || resp_data[0]!==data ||
               resp_epoch[0]!==epoch || resp_error[0]!==error)
                $fatal(1,"Wrong architectural reply step=%0d pc=%h",step,resp_pc[0]);
        end
    endtask
    task consume;
        begin @(negedge clk);resp_ready=1;@(negedge clk);resp_ready=0;end
    endtask
    initial begin
        repeat(3) @(negedge clk);reset=0;
        step=1;submit(32'h100);repeat(8) @(negedge clk);
        send_one(32'h100,4'h9);return_line(32'h100,JUMP,0);expect_reply(32'h100,JUMP,0);
        repeat(3) @(negedge clk);
        if(!mem_valid[0] || mem_addr[0]!==32'h800) $fatal(1,"Control target did not outrank sequential traffic");
        consume;
        step=2;submit(32'h110);
        demand_count=0;control_count=0;sequential_count=0;
        for(n=0;n<8;n=n+1) if(g_pair[0].dut.mshr_valid[n] && !g_pair[0].dut.mshr_sent[n]) begin
            if(!g_pair[0].dut.mshr_prefetch[n]) demand_count=demand_count+1;
            else if(g_pair[0].dut.mshr_control_prefetch[n]) control_count=control_count+1;
            else sequential_count=sequential_count+1;
        end
        if(demand_count!=1 || control_count!=1 || sequential_count<2)
            $fatal(1,"Real three-class competition missing d=%0d c=%0d s=%0d",demand_count,control_count,sequential_count);
        three_classes=three_classes+1;
        send_one(32'h110,4'h9);send_one(32'h800,4'h9);send_one(32'h120,4'h9);
        return_line(32'h110,NOPS,0);expect_reply(32'h110,NOPS,0);
        repeat(3) @(negedge clk);consume;
        // Ordinary old-epoch rows disappear immediately; actual control rows survive.
        step=3;@(negedge clk);epoch=4'h3;
        #1;if(!g_pair[0].dut.mshr_valid[0] || !g_pair[0].dut.mshr_control_prefetch[0])
            $fatal(1,"Real old control ownership missing at redirect");
        submit(32'h900);send_one(32'h900,4'h3);
        return_line(32'h120,NOPS,0);repeat(2) @(negedge clk);
        if(resp_valid[0]) $fatal(1,"Stale sequential response became architectural reply");
        stale_checked=stale_checked+1;
        return_line(32'h800,NOPS,0);repeat(2) @(negedge clk);
        if(resp_valid[0]) $fatal(1,"Unpromoted control response became architectural reply");
        step=4;return_line(32'h900,NOPS,1);expect_reply(32'h900,NOPS,1);consume;
        if(replies!=3 || issued!=5 || held<6 || three_classes!=1 || stale_checked!=1)
            $fatal(1,"Incomplete finite coverage replies=%0d sends=%0d held=%0d",replies,issued,held);
        $display("PASS: finite I-cache class send pair sends=%0d replies=%0d held=%0d three_classes=%0d stale=%0d",issued,replies,held,three_classes,stale_checked);
        $finish;
    end
    initial begin #20000;$fatal(1,"Finite class send timeout step=%0d",step);end
endmodule
