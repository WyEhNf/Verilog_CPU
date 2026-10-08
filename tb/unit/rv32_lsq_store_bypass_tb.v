`timescale 1ns/1ps
module rv32_lsq_store_bypass_tb;
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
    integer requests=0;
    reg [15:0] ticket;
    reg [31:0] expected_addr;
    reg [127:0] expected_data;
    reg [15:0] expected_mask;
    rv32_lsq #(.BE_WIDTH(2),.LSQ_ENTRIES(4),.ROB_ENTRIES(8),.TAG_WIDTH(16),.ROB_TAG_WIDTH(16),
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
        .alloc_is_load_i('0),
        .alloc_is_store_i(alloc_valid),
        .alloc_rob_tag_i(alloc_rob),
        .alloc_phys_rd_i('0),
        .alloc_size_i(alloc_size),
        .alloc_unsigned_i('0),
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
        .dcache_resp_valid_i('0),
        .dcache_resp_lsq_tag_i('0),
        .dcache_resp_query_valid_i('0),
        .dcache_resp_query_tags_i('0),
        .dcache_resp_addr_i('0),
        .dcache_resp_line_data_i('0),
        .dcache_resp_word_data_i('0),
        .dcache_resp_line_valid_i('0),
        .dcache_resp_error_i('0),
        .load_complete_ready_i(1'b1),
        .dcache_store_ack_valid_i(ack_valid),
        .dcache_store_ack_lsq_tag_i(ack_tag),
        .dcache_store_ack_error_i('0),
        .store_ack_query_valid_i('0),
        .store_ack_query_tag_i('0),
        .store_ack_ready_i(1'b1),
        .report_recovery_packet_i('0),
        .alloc_ready_o(alloc_ready),.alloc_lsq_tag_o(alloc_tag),.store_commit_ready_o(commit_ready),
        .dcache_req_valid_o(request_valid),.dcache_req_is_store_o(request_store),
        .dcache_req_addr_o(request_addr),.dcache_req_wdata_o(request_data),.dcache_req_mask_o(request_mask),
        .dcache_req_lsq_tag_o(request_tag),.store_ack_valid_o(store_ack_valid)
    );
    always @(posedge clk) if(!reset && request_valid && request_ready) begin
        if(!request_store || request_tag!==ticket || request_addr!==expected_addr ||
           request_data!==expected_data || request_mask!==expected_mask)
            $fatal(1,"store packet identity/payload changed");
        requests=requests+1;
    end
    task tick; begin @(posedge clk); #1; end endtask
    task clear;
        begin
            @(negedge clk); reset=1;alloc_valid=0;commit_valid=0;ack_valid=0;recovery=0;request_ready=0;
            tick;tick;@(negedge clk);reset=0;requests=0;
        end
    endtask
    task allocate(input [31:0] address,input [31:0] value,input [1:0] size);
        begin
            alloc_addr={32'b0,address};alloc_data={32'b0,value};alloc_size={2'b0,size};
            alloc_rob={16'b0,16'h101};alloc_valid=1;#1;
            if(!alloc_ready) $fatal(1,"small sample allocation blocked");
            ticket=alloc_tag[15:0];expected_addr=address;
            expected_mask=(size==2)?16'h000f:16'h0008;
            expected_data=(size==2)?128'(value):(128'(value)<<24);
            tick;@(negedge clk);alloc_valid=0;
        end
    endtask
    task check_offer;
        begin
            #1;
            if(!request_valid || !request_store || request_tag!==ticket ||
               request_addr!==expected_addr || request_mask!==expected_mask || request_data!==expected_data)
                $fatal(1,"architecturally admitted store did not bypass exact packet");
        end
    endtask
    initial begin
        // Word: no offer before admission, no acceptance for a stale GEN,
        // same-cycle offer at exact admission, then a stable held packet.
        clear;allocate(32'h100,32'h12345678,2);
        repeat(2) begin #1;if(request_valid) $fatal(1,"speculative store offered");tick;@(negedge clk);end
        commit_valid=1;commit_tag=16'h141;#1;
        if(commit_ready || request_valid) $fatal(1,"stale ROB generation admitted");
        tick;@(negedge clk);commit_tag=16'h101;check_offer;
        tick;@(negedge clk);commit_valid=0;check_offer;
        tick;@(negedge clk);check_offer;request_ready=1;
        tick;@(negedge clk);repeat(2) tick;
        if(requests!=1 || request_valid) $fatal(1,"held word store duplicated");
        @(negedge clk);ack_valid=1;ack_tag=ticket;tick;
        #1;if(!store_ack_valid) $fatal(1,"original ACK owner did not publish");
        // Byte: natural lane mask/data formatting, immediate acceptance.
        clear;allocate(32'h203,32'habcdefab,0);commit_valid=1;commit_tag=16'h101;request_ready=1;
        check_offer;tick;@(negedge clk);commit_valid=0;repeat(2) tick;
        if(requests!=1 || request_valid) $fatal(1,"byte store duplicated");
        // Recovery does not authorize an uncommitted store on its apply edge;
        // an already admitted held store remains owned and resumes afterward.
        clear;allocate(32'h300,32'h89abcdef,2);commit_valid=1;commit_tag=16'h101;check_offer;
        tick;@(negedge clk);commit_valid=0;recovery=1;#1;
        if(request_valid) $fatal(1,"request offered on recovery apply");
        tick;@(negedge clk);recovery=0;check_offer;request_ready=1;
        tick;@(negedge clk);repeat(2) tick;
        if(requests!=1) $fatal(1,"committed store was lost/duplicated by recovery");
        $display("PASS: limited committed-store bypass sample, exact admission/stale GEN/held word/byte mask/recovery/ACK");
        $finish;
    end
    initial begin #3000;$fatal(1,"small store bypass sample timed out");end
endmodule
