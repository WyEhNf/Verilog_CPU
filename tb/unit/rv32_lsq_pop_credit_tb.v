`timescale 1ns/1ps
module rv32_lsq_pop_credit_tb;
    reg clk=0,reset=1,recovery=0;
    always #5 clk=~clk;
    reg [1:0] alloc_valid=0;
    reg [31:0] alloc_rob=0;
    reg [3:0] alloc_size=0;
    reg [63:0] alloc_addr=0,alloc_data=0;
    reg commit_valid=0,request_ready=0,ack_valid=0;
    reg [15:0] commit_tag=0,ack_tag=0;
    wire alloc_ready,commit_ready,request_valid,request_store,store_ack_valid;
    wire [31:0] alloc_tag,request_addr;
    wire [15:0] request_tag,request_mask;
    wire [127:0] request_data;
    reg [1:0] loads=0,stores=0,unsigned_load=0;
    reg report_ready=0;wire release_credit;wire [1:0] allocation_fire;
    reg [15:0] tickets [0:3];reg [15:0] new_ticket;
    integer limit;
    reg response_valid=0;
    reg [15:0] response_tag=0;
    reg [31:0] response_data=0;
    wire load_valid,load_error;
    wire [31:0] load_value;
    wire [15:0] load_rob_tag;
    wire [5:0] selected_phys;
    wire [2:0] occupancy;
    integer requests=0;
    reg [15:0] ticket;
    reg [31:0] expected_addr;
    reg [127:0] expected_data;
    reg [15:0] expected_mask;
    rv32_lsq #(.RELEASE_CREDITS(2),.LOAD_COMPLETION_BYPASS(2), .BE_WIDTH(2),.LSQ_ENTRIES(4),.ROB_ENTRIES(8),.TAG_WIDTH(16),.ROB_TAG_WIDTH(16),
        .REQUEST_PIPELINE(1),.EMPTY_SELECTION_BYPASS(2),.PICK_LOCAL_VALIDITY(1),
        .STORE_ADMISSION_BYPASS(1),.COMMITTED_STORE_BYPASS(1)) dut (
        .clk_i(clk),
        .reset_i(reset),
        .flush_i('0),
        .recovery_valid_i(recovery),
        .recovery_tag_i(16'h41),
        .recovery_head_i('0),
        .recovery_occupancy_i(16'd8),
        .retire_valid_i('0),
        .retire_rob_tag_i('0),
        .alloc_valid_i(alloc_valid),
        .alloc_plan_valid_i(alloc_valid),
        .alloc_is_load_i(loads),
        .alloc_is_store_i(stores),
        .alloc_rob_tag_i(alloc_rob),
        .alloc_phys_rd_i(12'd9),
        .alloc_size_i(alloc_size),
        .alloc_unsigned_i(unsigned_load),
        .alloc_addr_valid_i(alloc_valid),
        .alloc_addr_i(alloc_addr),
        .alloc_data_valid_i(alloc_valid),
        .alloc_store_data_i(alloc_data),
        .alloc_store_mask_i('0),
        .early_addr_valid_i('0),
        .early_addr_tag_i('0),
        .early_addr_i('0),
        .addr_update_valid_i('0),
        .addr_update_tag_i('0),
        .addr_update_i('0),
        .data_update_valid_i('0),
        .data_update_tag_i('0),
        .data_update_i('0),
        .data_mask_update_i('0),
        .wakeup_valid_i('0),
        .wakeup_tag_i('0),
        .wakeup_value_i('0),
        .store_commit_valid_i(commit_valid),
        .store_commit_rob_tag_i(commit_tag),
        .dcache_req_ready_i(request_ready),
        .dcache_resp_valid_i(response_valid),
        .dcache_resp_lsq_tag_i(response_tag),
        .dcache_resp_query_valid_i('0),
        .dcache_resp_query_tags_i('0),
        .dcache_resp_addr_i('0),
        .dcache_resp_line_data_i('0),
        .dcache_resp_word_data_i(response_data),
        .dcache_resp_line_valid_i('0),
        .dcache_resp_error_i('0),
        .load_complete_ready_i(report_ready),
        .dcache_store_ack_valid_i(ack_valid),
        .dcache_store_ack_lsq_tag_i(ack_tag),
        .dcache_store_ack_error_i('0),
        .store_ack_query_valid_i('0),
        .store_ack_query_tag_i('0),
        .store_ack_ready_i(1'b1),
        .report_recovery_packet_i('0),
        .occupancy_o(occupancy),.load_complete_valid_o(load_valid),.load_complete_value_o(load_value),.load_complete_error_o(load_error),.load_complete_rob_tag_o(load_rob_tag),.load_complete_phys_rd_o(selected_phys),.allocation_release_o(release_credit),.alloc_fire_o(allocation_fire),.alloc_ready_o(alloc_ready),.alloc_lsq_tag_o(alloc_tag),.store_commit_ready_o(commit_ready),
        .dcache_req_valid_o(request_valid),.dcache_req_is_store_o(request_store),
        .dcache_req_addr_o(request_addr),.dcache_req_wdata_o(request_data),.dcache_req_mask_o(request_mask),
        .dcache_req_lsq_tag_o(request_tag),.store_ack_valid_o(store_ack_valid)
    );
    always @(posedge clk) if(!reset && request_valid && request_ready) begin
        if(request_store) $fatal(1,"pop sample unexpectedly offered store");
        if(requests<4) tickets[requests]=request_tag;
        requests=requests+1;
    end
    task tick;begin @(posedge clk);#1;end endtask
    initial begin
        tick;tick;@(negedge clk);reset=0;request_ready=1;loads=3;alloc_valid=3;
        alloc_size=4'ha;alloc_rob={16'h109,16'h101};alloc_addr={32'h104,32'h100};
        tick;@(negedge clk);alloc_rob={16'h119,16'h111};alloc_addr={32'h10c,32'h108};
        tick;@(negedge clk);alloc_valid=0;loads=0;
        for(limit=0;limit<12 && requests<4;limit=limit+1) begin tick;@(negedge clk);end
        if(requests!=4 || occupancy!=4) $fatal(1,"bounded full load queue setup failed");
        request_ready=0;alloc_valid=1;loads=1;alloc_rob=32'h121;alloc_addr=64'h110;
        response_valid=1;response_tag=tickets[0];response_data=32'habcdef01;#1;
        if(!load_valid || release_credit || allocation_fire!=0)
            $fatal(1,"LSQ borrowed response before report acceptance");
        report_ready=1;#1;new_ticket=alloc_tag[15:0];
        if(!release_credit || allocation_fire!=1 || new_ticket==tickets[0] ||
            load_rob_tag!=16'h101 || load_value!=32'habcdef01)
            $fatal(1,"full queue current response/report/pop allocation failed");
        tick;@(negedge clk);response_valid=0;alloc_valid=0;loads=0;report_ready=0;request_ready=1;#1;
        if(occupancy!=4 || dut.complete_mem[0] || dut.load_reported_mem[0])
            $fatal(1,"old response metadata polluted new generation");
        if(!request_valid || request_tag!=new_ticket || request_addr!=32'h110)
            $fatal(1,"recycled row did not own new request");
        tick;@(negedge clk);request_ready=0;response_valid=1;response_tag=tickets[0];response_data=32'hffffffff;
        tick;@(negedge clk);response_valid=0;#1;
        if(dut.complete_mem[0] || load_valid || requests!=5)
            $fatal(1,"stale full-GEN reply completed waiting recycled row");
        response_valid=1;response_tag=new_ticket;response_data=32'h13579bdf;
        tick;@(negedge clk);response_valid=0;#1;
        if(!load_valid || load_rob_tag!=16'h121 || load_value!=32'h13579bdf)
            $fatal(1,"new full-GEN reply lost recycled row identity/value");
        $display("PASS: limited LSQ current-pop credit sample");$finish;
    end
    initial begin #2000;$fatal(1,"LSQ pop sample timeout");end
endmodule
