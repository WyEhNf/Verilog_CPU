`timescale 1ns/1ps
`include "rv32im_defs.vh"
module rv32_rs_fresh_data_case #(parameter integer W=1)(output reg done=0);
    localparam integer E=2*W, SW=$clog2(E), CW=$clog2(E+1), AW=$clog2(W+1);
    localparam integer OW=`RV32IM_OP_WIDTH, TW=16, PW=6, MW=70;
    localparam integer PAY=OW+32+TW+PW+64+32+MW+SW;
    reg clk=0,reset=1,flush=0;
    always #5 clk=~clk;
    reg [W-1:0] alloc=0,ready=0,sready={W{1'b1}},wake=0;
    reg [W*OW-1:0] op=0;
    reg [W*32-1:0] pc=0,v1=0,v2=0,store=0;
    reg [W*TW-1:0] tag=0;
    reg [W*PW-1:0] phys=0;
    reg [W*MW-1:0] metadata=0;
    wire [W-1:0] fire[0:1], valid[0:1],cancel[0:1],qualified[0:1];
    wire [W*SW-1:0] alloc_slot[0:1],slot[0:1];
    wire [W*OW-1:0] out_op[0:1];
    wire [W*32-1:0] out_pc[0:1],out_v1[0:1],out_v2[0:1],out_store[0:1];
    wire [W*TW-1:0] out_tag[0:1];
    wire [W*PW-1:0] out_phys[0:1];
    wire [W*MW-1:0] out_metadata[0:1];
    wire [CW-1:0] occupancy[0:1];
    wire [AW-1:0] count[0:1],release_count[0:1];
    wire alloc_ready[0:1];
    wire [E-1:0] entries[0:1],entry_release[0:1];
    wire [E*TW-1:0] entry_tags[0:1];
    wire [W*PAY-1:0] packet[0:1];
    for(genvar version=0;version<2;version=version+1) begin:g_version
        rv32_reservation_station #(.BE_WIDTH(W),.ENTRIES(E),.TAG_WIDTH(TW),.SOURCE_TAG_WIDTH(TW),
            .PHYS_ADDR_WIDTH(PW),.WAKE_WIDTH(W),.METADATA_WIDTH(MW),.AGE_WIDTH(8),.AGE_ORDER_MATRIX(2),
            .ALLOC_STATIC_WRITE(1),.LOCAL_PAYLOAD_ROWS(1),.RELEASE_CREDITS(0),.ALLOC_EMPTY_BYPASS(1),
            .FRESH_DEFAULT_LANE_DATA(version),.ISSUE_RECOVERY_QUALIFICATION(1),.ISSUE_RECOVERY_CANCEL(1)) dut (
            .clk_i(clk),.reset_i(reset),.alloc_valid_i(alloc),.alloc_op_i(op),.alloc_pc_i(pc),
            .alloc_rob_tag_i(tag),.alloc_target_live_i(alloc),.alloc_phys_rd_i(phys),
            .alloc_src1_value_i(v1),.alloc_src1_tag_i({W{16'h201}}),.alloc_src1_ready_i(sready),
            .alloc_src2_value_i(v2),.alloc_src2_tag_i('0),.alloc_src2_ready_i({W{1'b1}}),
            .alloc_store_data_i(store),.alloc_metadata_i(metadata),.allocation_release_count_o(release_count[version]),
            .alloc_ready_o(alloc_ready[version]),.alloc_fire_o(fire[version]),.alloc_count_o(count[version]),
            .alloc_slot_o(alloc_slot[version]),.wake_valid_i(wake),.wake_tag_i({W{16'h201}}),
            .wake_value_i({W{32'habc}}),.issue_ready_i(ready),.entry_recovery_qualified_i('0),.entry_issue_cancel_i('0),
            .issue_valid_o(valid[version]),.issue_op_o(out_op[version]),.issue_pc_o(out_pc[version]),
            .issue_rob_tag_o(out_tag[version]),.issue_phys_rd_o(out_phys[version]),
            .issue_src1_value_o(out_v1[version]),.issue_src2_value_o(out_v2[version]),
            .issue_store_data_o(out_store[version]),.issue_metadata_o(out_metadata[version]),.issue_slot_o(slot[version]),
            .issue_cancel_o(cancel[version]),.issue_recovery_qualified_o(qualified[version]),
            .flush_valid_i(flush),.flush_kill_mask_i('0),.entry_valid_o(entries[version]),
            .entry_rob_tag_o(entry_tags[version]),.entry_release_o(entry_release[version]),.occupancy_o(occupancy[version]));
        for(genvar lane=0;lane<W;lane=lane+1) begin:g_packet
            assign packet[version][lane*PAY +: PAY]={out_op[version][lane*OW +: OW],out_pc[version][lane*32 +: 32],
                out_tag[version][lane*TW +: TW],out_phys[version][lane*PW +: PW],
                out_v1[version][lane*32 +: 32],out_v2[version][lane*32 +: 32],out_store[version][lane*32 +: 32],
                out_metadata[version][lane*MW +: MW],slot[version][lane*SW +: SW]};
        end
    end
    task compare; begin
        if ({fire[0],valid[0],count[0],alloc_ready[0],occupancy[0],entries[0],entry_tags[0],entry_release[0],release_count[0],alloc_slot[0]} !==
            {fire[1],valid[1],count[1],alloc_ready[1],occupancy[1],entries[1],entry_tags[1],entry_release[1],release_count[1],alloc_slot[1]})
            $fatal(1,"shared RS valid/owner/state mismatch width %0d",W);
        for(integer lane=0;lane<W;lane=lane+1) if(valid[0][lane]) begin
            if(packet[0][lane*PAY +: PAY]!==packet[1][lane*PAY +: PAY] ||
                cancel[0][lane]!==cancel[1][lane] || qualified[0][lane]!==qualified[1][lane])
                $fatal(1,"shared RS valid packet mismatch width %0d lane %0d",W,lane);
        end
    end endtask
    task tick; begin #1;compare;@(posedge clk);#1;compare;end endtask
    task candidate(input integer n); begin
        for(integer lane=0;lane<W;lane=lane+1) begin
            op[lane*OW +: OW]=lane==0 ? `RV32IM_OP_SUB : `RV32IM_OP_MUL;
            pc[lane*32 +: 32]=n+lane;
            tag[lane*TW +: TW]=16'h101+16'(n*8+lane*8);
            phys[lane*PW +: PW]=PW'(3+lane);
            v1[lane*32 +: 32]=32'h80000000+32'(n+lane);
            v2[lane*32 +: 32]=32'hffffffff-32'(n+lane);
            store[lane*32 +: 32]=32'h12345678+32'(n+lane);
            metadata[lane*MW +: MW]=MW'(n)+MW'(lane)+70'h123456789abcdef012;
        end
    end endtask
    initial begin
        tick;@(negedge clk);reset=0;candidate(10);tick; // idle raw packet
        @(negedge clk);alloc='1;tick; // fresh offer, stalled
        @(negedge clk);alloc=0;candidate(20);#1;
        if(occupancy[1]!=W || valid[1]!={W{1'b1}} || out_pc[1][31:0]!=10)
            $fatal(1,"stalled fresh packet was not retained width %0d",W);
        ready='1;tick;@(negedge clk);candidate(30);alloc='1;#1;
        if(valid[1]!={W{1'b1}} || out_pc[1][31:0]!=30) $fatal(1,"fresh packet missing width %0d",W);
        tick;@(negedge clk);alloc=0;#1;
        if(occupancy[1]!=0 || valid[1]!=0) $fatal(1,"fresh packet issued twice width %0d",W);
        candidate(40);alloc='1;sready='1;sready[0]=0;tick;
        @(negedge clk);alloc=0;#1;
        if(occupancy[1]!=1 || valid[1]!=0) $fatal(1,"unready owner lost width %0d",W);
        wake[0]=1;#1;
        if(valid[1]!=1 || out_pc[1][31:0]!=40 || out_v1[1][31:0]!=32'habc)
            $fatal(1,"retained owner wake mismatch width %0d",W);
        tick;@(negedge clk);wake=0;sready='1;flush=1;alloc='1;candidate(50);tick;
        @(negedge clk);flush=0;ready=0;candidate(60);alloc='1;tick;
        @(negedge clk);candidate(70);tick; // fill both batches
        @(negedge clk);candidate(80);#1;
        if(occupancy[1]!=E || fire[1]!=0 || out_pc[1][31:0]!=60)
            $fatal(1,"full RS used an unaccepted candidate width %0d",W);
        tick;@(negedge clk);reset=1;alloc=0;tick;
        @(negedge clk);reset=0;ready='1;alloc='1;candidate(90);tick;
        @(negedge clk);alloc=0;tick;
        if(occupancy[1]!=0) $fatal(1,"reset/reuse did not drain width %0d",W);
        done=1;
    end
endmodule
module rv32_rs_fresh_data_tb;
    wire d1,d2;
    rv32_rs_fresh_data_case #(.W(1)) one(d1);
    rv32_rs_fresh_data_case #(.W(2)) two(d2);
    initial begin wait(d1&&d2);$display("PASS: limited shared RS fresh-data sample widths 1/2");$finish;end
    initial begin #2000;$fatal(1,"fresh-data sample timeout");end
endmodule
