`timescale 1ns/1ps
module rv32_lsq_alloc_request_tb;
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
    rv32_lsq #(.ALLOC_LOAD_REQUEST_BYPASS(1),.ALLOC_LOAD_SELECTION_BYPASS(1), .BE_WIDTH(2),.LSQ_ENTRIES(4),.ROB_ENTRIES(8),.TAG_WIDTH(16),.ROB_TAG_WIDTH(16),
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
        .load_complete_ready_i(1'b0),
        .dcache_store_ack_valid_i(ack_valid),
        .dcache_store_ack_lsq_tag_i(ack_tag),
        .dcache_store_ack_error_i('0),
        .store_ack_query_valid_i('0),
        .store_ack_query_tag_i('0),
        .store_ack_ready_i(1'b1),
        .report_recovery_packet_i('0),
        .occupancy_o(occupancy),.load_complete_valid_o(load_valid),.load_complete_value_o(load_value),.load_complete_error_o(load_error),.load_complete_rob_tag_o(load_rob_tag),.load_complete_phys_rd_o(selected_phys),.alloc_ready_o(alloc_ready),.alloc_lsq_tag_o(alloc_tag),.store_commit_ready_o(commit_ready),
        .dcache_req_valid_o(request_valid),.dcache_req_is_store_o(request_store),
        .dcache_req_addr_o(request_addr),.dcache_req_wdata_o(request_data),.dcache_req_mask_o(request_mask),
        .dcache_req_lsq_tag_o(request_tag),.store_ack_valid_o(store_ack_valid)
    );
    always @(posedge clk) if(!reset && request_valid && request_ready) begin
        if(request_store || request_tag!==ticket || request_addr!==expected_addr)
            $fatal(1,"allocation load request identity/payload changed");
        requests=requests+1;
    end
    task tick;begin @(posedge clk);#1;end endtask
    task clear;begin
        @(negedge clk);reset=1;alloc_valid=0;loads=0;stores=0;request_ready=0;response_valid=0;recovery=0;
        tick;tick;@(negedge clk);reset=0;requests=0;
    end endtask
    task offer(input [31:0] address,input [1:0] size,input unsigned_bit);
        begin
            alloc_valid=1;loads=1;stores=0;alloc_rob=32'h101;alloc_addr=address;alloc_size=size;
            unsigned_load=unsigned_bit;expected_addr=address;#1;ticket=alloc_tag[15:0];
            if(!alloc_ready || !request_valid || request_store || request_tag!=ticket || request_addr!=address)
                $fatal(1,"fresh owned load did not offer on allocation edge");
        end
    endtask
    task response(input [31:0] data,input [31:0] expected);
        begin
            response_valid=1;response_tag=ticket;response_data=data;tick;@(negedge clk);response_valid=0;#1;
            if(!load_valid || load_error || load_rob_tag!=16'h101 || selected_phys!=9 || load_value!=expected)
                $fatal(1,"allocation request response lost exact row/data/phys identity");
        end
    endtask
    initial begin
        // Accepted on allocation edge: saved row starts sent/waiting, and no
        // selection ticket survives to repeat the cache access.
        clear;offer(32'h100,2,0);request_ready=1;tick;@(negedge clk);alloc_valid=0;loads=0;#1;
        if(request_valid || requests!=1 || occupancy!=1) $fatal(1,"accepted allocation load reoffered");
        request_ready=0;response(32'h11223344,32'h11223344);
        // First offer stalled: original ticket owns the same packet after
        // inputs change, then it sends once and accepts a byte response.
        clear;offer(32'h101,0,1);tick;@(negedge clk);alloc_valid=0;loads=0;alloc_addr=32'hdeadbeef;#1;
        if(!request_valid || request_tag!=ticket || request_addr!=32'h101 || request_mask!=16'h0002)
            $fatal(1,"backpressured allocation load was not retained");
        tick;@(negedge clk);request_ready=1;tick;@(negedge clk);request_ready=0;#1;
        if(request_valid || requests!=1) $fatal(1,"held allocation load duplicated");
        response(32'h80,32'h80);
        // Any old store blocks the fresh shortcut, even with a known nonalias
        // address; current recovery also blocks it.
        clear;alloc_valid=1;stores=1;alloc_addr=32'h200;alloc_size=2;alloc_rob=32'h109;
        tick;@(negedge clk);stores=0;loads=1;alloc_addr=32'h100;alloc_rob=32'h101;#1;
        if(request_valid) $fatal(1,"allocation request crossed old store");
        clear;recovery=1;alloc_valid=1;loads=1;#1;
        if(request_valid) $fatal(1,"allocation request crossed recovery");
        $display("PASS: limited LSQ allocation-load request sample");$finish;
    end
    initial begin #2000;$fatal(1,"allocation request sample timeout");end
endmodule
