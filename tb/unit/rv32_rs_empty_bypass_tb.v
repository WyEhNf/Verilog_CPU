`timescale 1ns/1ps
module rv32_rs_empty_bypass_tb;
    reg clk=0,reset=1,flush=0;
    always #5 clk=~clk;
    reg [1:0] alloc=0,issue_ready=0;
    reg [63:0] pc=0;
    reg [31:0] tag=0;
    reg [1:0] source_ready=3,wake_valid=0;
    wire [63:0] issue_value;
    wire [1:0] fire,issue_valid,release_count;
    wire [63:0] issue_pc;
    wire [31:0] issue_tag;
    wire [2:0] occupancy;
    rv32_reservation_station #(.BE_WIDTH(2),.ENTRIES(4),.TAG_WIDTH(16),.SOURCE_TAG_WIDTH(16),
        .AGE_WIDTH(8),.AGE_ORDER_MATRIX(2),.ALLOC_STATIC_WRITE(1),.LOCAL_PAYLOAD_ROWS(1),.RELEASE_CREDITS(0),.ALLOC_EMPTY_BYPASS(1)) dut (
        .clk_i(clk),
        .reset_i(reset),
        .alloc_valid_i(alloc),
        .alloc_op_i('0),
        .alloc_pc_i(pc),
        .alloc_rob_tag_i(tag),
        .alloc_target_live_i(alloc),
        .alloc_phys_rd_i('0),
        .alloc_src1_value_i('0),
        .alloc_src1_tag_i(32'h201),
        .alloc_src1_ready_i(source_ready),
        .alloc_src2_value_i('0),
        .alloc_src2_tag_i('0),
        .alloc_src2_ready_i(2'b11),
        .alloc_store_data_i('0),
        .alloc_metadata_i('0),
        .allocation_release_count_o(release_count),
        .alloc_fire_o(fire),
        .wake_valid_i(wake_valid),
        .wake_tag_i(32'h201),
        .wake_value_i(64'habc),
        .issue_ready_i(issue_ready),
        .entry_recovery_qualified_i('0),
        .entry_issue_cancel_i('0),
        .issue_valid_o(issue_valid),
        .issue_pc_o(issue_pc),.issue_src1_value_o(issue_value),
        .issue_rob_tag_o(issue_tag),
        .flush_valid_i(flush),
        .flush_kill_mask_i('0),
        .occupancy_o(occupancy)
    );
    task tick;begin @(posedge clk);#1;end endtask
    initial begin
        tick;@(negedge clk);reset=0;alloc=3;pc={32'd20,32'd10};tag={16'h109,16'h101};#1;
        if(fire!=3 || issue_valid!=3 || issue_pc!={32'd20,32'd10}) $fatal(1,"empty RS did not offer new owned prefix");
        tick;@(negedge clk);alloc=0;pc=64'hdeadbeef;tag=0;#1;
        if(occupancy!=2 || issue_valid!=3 || issue_pc!={32'd20,32'd10} || issue_tag!={16'h109,16'h101})
            $fatal(1,"stalled fresh RS payload/identity was not retained");
        issue_ready=3;tick;@(negedge clk);#1;
        if(occupancy!=0 || issue_valid!=0) $fatal(1,"held RS prefix did not drain");
        alloc=3;pc={32'd40,32'd30};tag={16'h119,16'h111};#1;
        if(issue_valid!=3 || issue_pc!={32'd40,32'd30}) $fatal(1,"empty RS fresh ready prefix not visible");
        tick;@(negedge clk);alloc=0;#1;
        if(occupancy!=0 || issue_valid!=0) $fatal(1,"consumed fresh RS instruction queued twice");
        // Younger ready incoming lane may issue; older unready allocation
        // must stay queued with its original source tag until wakeup.
        alloc=3;source_ready=2;pc={32'd60,32'd50};tag={16'h129,16'h121};#1;
        if(issue_valid!=1 || issue_pc[31:0]!=60 || issue_tag[15:0]!=16'h129)
            $fatal(1,"fresh ready-lane compaction failed");
        tick;@(negedge clk);alloc=0;#1;
        if(occupancy!=1 || issue_valid!=0) $fatal(1,"unready older allocation was lost or issued");
        wake_valid=1;#1;
        if(issue_valid!=1 || issue_pc[31:0]!=50 || issue_tag[15:0]!=16'h121 || issue_value[31:0]!=32'habc)
            $fatal(1,"retained older fresh allocation lost source wake/identity");
        tick;@(negedge clk);wake_valid=0;#1;
        if(occupancy!=0 || issue_valid!=0) $fatal(1,"retained older instruction did not drain once");
        alloc=3;source_ready=3;flush=1;#1;
        if(issue_valid!=0) $fatal(1,"fresh RS bypass crossed recovery boundary");
        $display("PASS: limited shared RS empty-bypass sample");$finish;
    end
    initial begin #2000;$fatal(1,"empty RS sample timeout");end
endmodule
