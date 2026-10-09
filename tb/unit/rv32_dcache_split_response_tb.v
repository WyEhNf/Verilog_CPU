`timescale 1ns/1ps
module rv32_dcache_split_response_tb;
    reg clk=0,reset=1;always #5 clk=~clk;
    reg req_valid=0,req_load=1,req_store=0;
    reg [31:0] req_addr=0,raw_word=0;
    reg [15:0] req_mask=16'h000f,req_tag=0;
    wire [127:0] req_line={96'b0,raw_word} << {req_addr[3:0],3'b0};
    reg resp_ready=0;
    wire [1:0] req_ready,resp_valid,resp_error,resp_line_valid,ack_valid,ack_error;
    wire [31:0] resp_word[0:1],resp_addr[0:1];
    wire [15:0] resp_tag[0:1],ack_tag[0:1],ack_query[0:1];
    wire [127:0] resp_line[0:1];
    wire [1:0] query_valid[0:1];wire [31:0] query_tags[0:1];
    wire [1:0] cache_mem_valid,cache_mem_write,cache_mem_resp_ready;
    wire [31:0] cache_mem_addr[0:1];wire [127:0] cache_mem_data[0:1];
    wire [15:0] cache_mem_mask[0:1];wire [7:0] cache_mem_id[0:1];
    wire cache_mem_ready,bridge_resp_valid,bridge_resp_error;
    wire [31:0] bridge_resp_addr;wire [127:0] bridge_resp_data;wire [7:0] bridge_resp_id;
    wire [1:0] source_select,source_errors;wire [15:0] source_ids;wire [63:0] source_addresses;
    wire memory_valid,memory_write,memory_resp_ready;
    wire [31:0] memory_addr;wire [127:0] memory_data;wire [15:0] memory_mask;wire [7:0] memory_id;
    reg busy=0,memory_response=0,returned_error=0;
    reg prefetch_return_gate=0,idle_odd=0,writeback_fault=0;
    integer delay_count=0;
    reg [31:0] returned_addr=0;reg [127:0] returned_line=0;reg [7:0] returned_id=0;
    reg hold_prefetch=0;
    wire memory_ready=!busy && !memory_response;
    wire [7:0] external_id=(!memory_response && idle_odd)?8'hff:returned_id;
    wire [31:0] external_addr=(!memory_response && idle_odd)?32'hdeadbeef:returned_addr;
    wire external_error=(!memory_response && idle_odd)?1'b1:returned_error;
    integer reads=0,writes=0,acks=0,loads=0,expected_loads=0,limit=0;
    integer local_checks=0,source_collisions=0,blocked_hit_checks=0,writeback_errors=0,address_errors=0;
    reg [15:0] expected_tags[0:7];reg [31:0] expected_words[0:7];reg expected_errors[0:7];

    rv32_memory_bridge #(.MEMORY_SIZE(4096)) bridge (
        .clk_i(clk),.reset_i(reset),
        .cache_i_req_valid_i(1'b0),.cache_i_req_line_addr_i(32'b0),.cache_i_req_id_i(8'b0),
        .cache_i_resp_ready_i(1'b1),.mem_i_req_ready_i(1'b1),.mem_i_resp_valid_i(1'b0),
        .mem_i_resp_line_addr_i(32'b0),.mem_i_resp_data_i(128'b0),.mem_i_resp_id_i(8'b0),.mem_i_resp_error_i(1'b0),
        .cache_d_req_valid_i(cache_mem_valid[0]),.cache_d_req_ready_o(cache_mem_ready),
        .cache_d_req_write_i(cache_mem_write[0]),.cache_d_req_line_addr_i(cache_mem_addr[0]),
        .cache_d_req_wdata_i(cache_mem_data[0]),.cache_d_req_wmask_i(cache_mem_mask[0]),.cache_d_req_id_i(cache_mem_id[0]),
        .cache_d_resp_valid_o(bridge_resp_valid),.cache_d_resp_ready_i(cache_mem_resp_ready[0]),
        .cache_d_resp_line_addr_o(bridge_resp_addr),.cache_d_resp_data_o(bridge_resp_data),
        .cache_d_resp_id_o(bridge_resp_id),.cache_d_resp_error_o(bridge_resp_error),
        .cache_d_resp_query_select_o(source_select),.cache_d_resp_query_ids_o(source_ids),
        .cache_d_resp_query_addresses_o(source_addresses),.cache_d_resp_query_errors_o(source_errors),
        .mem_d_req_valid_o(memory_valid),.mem_d_req_ready_i(memory_ready),.mem_d_req_write_o(memory_write),
        .mem_d_req_line_addr_o(memory_addr),.mem_d_req_wdata_o(memory_data),.mem_d_req_wmask_o(memory_mask),.mem_d_req_id_o(memory_id),
        .mem_d_resp_valid_i(memory_response),.mem_d_resp_ready_o(memory_resp_ready),
        .mem_d_resp_line_addr_i(external_addr),.mem_d_resp_data_i(returned_line),.mem_d_resp_id_i(external_id),.mem_d_resp_error_i(external_error));

    generate for(genvar policy=0;policy<2;policy=policy+1) begin:g_cache
        rv32_dcache_nonblocking #(.SPLIT_MEMORY_RESPONSE_QUERY(policy),.NARROW_REQUEST_WORD(1),.MSHR_DATA_NO_CLEAR(1),.TAG_WIDTH(16),
            .CACHE_LINES(16),.CACHE_WAYS(2),.MSHR_ENTRIES(4),.WAITER_ENTRIES(8),
            .PREFETCH(1),.TAG_SRAM(1),.STATIC_UPDATES(2),.WORD_RESPONSE(1),
            .WAY_PARALLEL_QUERY(1),.LOCAL_SRAM_COMMANDS(1),.HIT_RESPONSE_COISSUE(1),
            .REGISTERED_INDEX(1),.LOCAL_METADATA_QUERY(1),.LOCAL_ACTION_DECODE(1)) dut (
            .clk_i(clk),.reset_i(reset),.flush_i(1'b0),
            .dcache_req_valid_i(req_valid),.dcache_req_ready_o(req_ready[policy]),
            .dcache_req_is_load_i(req_load),.dcache_req_is_store_i(req_store),.dcache_req_addr_i(req_addr),
            .dcache_req_size_i(2'd2),.dcache_req_unsigned_i(1'b1),.dcache_req_mask_i(req_mask),
            .dcache_req_wdata_i(req_line),.dcache_req_raw_word_i(raw_word),.dcache_req_rob_tag_i(req_tag),.dcache_req_lsq_tag_i(req_tag),
            .dcache_resp_valid_o(resp_valid[policy]),.dcache_resp_ready_i(resp_ready),
            .dcache_resp_lsq_tag_o(resp_tag[policy]),.dcache_resp_query_valid_o(query_valid[policy]),.dcache_resp_query_tags_o(query_tags[policy]),
            .dcache_resp_addr_o(resp_addr[policy]),.dcache_resp_line_data_o(resp_line[policy]),.dcache_resp_word_data_o(resp_word[policy]),
            .dcache_resp_line_valid_o(resp_line_valid[policy]),.dcache_resp_error_o(resp_error[policy]),
            .dcache_store_ack_valid_o(ack_valid[policy]),.dcache_store_ack_ready_i(1'b1),
            .dcache_store_ack_lsq_tag_o(ack_tag[policy]),.dcache_store_ack_query_tag_o(ack_query[policy]),.dcache_store_ack_error_o(ack_error[policy]),
            .mem_req_valid_o(cache_mem_valid[policy]),.mem_req_ready_i(cache_mem_ready),.mem_req_write_o(cache_mem_write[policy]),
            .mem_req_line_addr_o(cache_mem_addr[policy]),.mem_req_wdata_o(cache_mem_data[policy]),.mem_req_wmask_o(cache_mem_mask[policy]),.mem_req_id_o(cache_mem_id[policy]),
            .mem_resp_valid_i(bridge_resp_valid),.mem_resp_ready_o(cache_mem_resp_ready[policy]),
            .mem_resp_line_addr_i(bridge_resp_addr),.mem_resp_data_i(bridge_resp_data),.mem_resp_id_i(bridge_resp_id),.mem_resp_error_i(bridge_resp_error),
            .mem_resp_query_select_i(source_select),.mem_resp_query_ids_i(source_ids),.mem_resp_query_addresses_i(source_addresses),.mem_resp_query_errors_i(source_errors));
    end endgenerate
    always @(negedge clk) begin
        #2;
        if(!reset) begin
            assert({req_ready[0],resp_valid[0],ack_valid[0],cache_mem_valid[0],cache_mem_resp_ready[0],query_valid[0]}==
                   {req_ready[1],resp_valid[1],ack_valid[1],cache_mem_valid[1],cache_mem_resp_ready[1],query_valid[1]})
                else $fatal(1,"Split response changed public cycle/readiness");
            if(resp_valid[0]) assert({resp_tag[0],resp_addr[0],resp_line[0],resp_word[0],resp_line_valid[0],resp_error[0]}==
                                    {resp_tag[1],resp_addr[1],resp_line[1],resp_word[1],resp_line_valid[1],resp_error[1]})
                else $fatal(1,"Split response changed a complete valid LOAD packet");
            if(ack_valid[0]) assert({ack_tag[0],ack_query[0],ack_error[0]}=={ack_tag[1],ack_query[1],ack_error[1]});
            if(cache_mem_valid[0]) assert({cache_mem_write[0],cache_mem_addr[0],cache_mem_data[0],cache_mem_mask[0],cache_mem_id[0]}==
                                         {cache_mem_write[1],cache_mem_addr[1],cache_mem_data[1],cache_mem_mask[1],cache_mem_id[1]});
            for(integer q=0;q<2;q=q+1) if(query_valid[0][q]) assert(query_tags[0][q*16 +: 16]==query_tags[1][q*16 +: 16]);
        end
    end
    generate for(genvar row=0;row<4;row=row+1) begin:g_state_check
        always @(posedge clk) if(!reset)
            assert({g_cache[0].dut.mshr_valid[row],g_cache[0].dut.mshr_sent[row],g_cache[0].dut.mshr_writeback[row],g_cache[0].dut.mshr_store[row],g_cache[0].dut.mshr_prefetch[row]}==
                   {g_cache[1].dut.mshr_valid[row],g_cache[1].dut.mshr_sent[row],g_cache[1].dut.mshr_writeback[row],g_cache[1].dut.mshr_store[row],g_cache[1].dut.mshr_prefetch[row]});
    end endgenerate
    always @(posedge clk) begin
        if(reset) begin busy<=0;memory_response<=0;delay_count<=0;end
        else begin
            if(memory_response && memory_resp_ready) memory_response<=0;
            if(busy) begin
                if(delay_count==0 && (!hold_prefetch || prefetch_return_gate)) begin busy<=0;memory_response<=1;end
                else if(delay_count!=0) delay_count<=delay_count-1;
            end
            if(memory_valid && memory_ready) begin
                busy<=1;delay_count<=2;returned_id<=memory_id;
                hold_prefetch<=memory_addr==32'h110;
                returned_addr<=(!memory_write && memory_addr==32'h400)?32'h410:memory_addr;
                returned_line<=(memory_addr==32'h180)?128'h112233445566778899aabbcc76543210:128'hffeeddccbbaa99887766554489abcdef;
                returned_error<=memory_write && writeback_fault;
                if(memory_write) begin writes=writes+1;if(writeback_fault) writeback_errors=writeback_errors+1;end
                else begin reads=reads+1;if(memory_addr==32'h400) address_errors=address_errors+1;end
            end
            if(source_select[0]) begin
                local_checks=local_checks+1;
                if(memory_response) begin
                    source_collisions=source_collisions+1;
                    assert(!memory_resp_ready) else $fatal(1,"Local error consumed a competing external return");
                end
                if(g_cache[1].dut.core_req_valid && g_cache[1].dut.request_hit) begin
                    blocked_hit_checks=blocked_hit_checks+1;
                    assert(!g_cache[1].dut.bypass_load_hit) else $fatal(1,"Error return lost its original LOAD slot priority");
                end
            end
            if(ack_valid[0]) begin assert(!ack_error[0]);acks=acks+1;end
            if(resp_valid[0] && resp_ready) begin
                if(loads>=expected_loads || resp_tag[0]!=expected_tags[loads] || resp_error[0]!=expected_errors[loads] ||
                   (!expected_errors[loads] && resp_word[0]!=expected_words[loads]))
                    $fatal(1,"Unexpected ordered LOAD packet index=%0d tag=%h error=%0d word=%h",loads,resp_tag[0],resp_error[0],resp_word[0]);
                loads=loads+1;
            end
        end
    end
    task tick;begin @(posedge clk);#1;end endtask
    task expect_load(input [15:0] tag,input [31:0] word,input bit fault);
        begin expected_tags[expected_loads]=tag;expected_words[expected_loads]=word;expected_errors[expected_loads]=fault;expected_loads=expected_loads+1;end
    endtask
    task send(input bit store,input [31:0] address,word,input [15:0] tag);
        begin
            @(negedge clk);req_valid=1;req_load=!store;req_store=store;req_addr=address;raw_word=word;req_tag=tag;#1;
            for(limit=0;limit<60 && !req_ready[0];limit=limit+1) begin tick;@(negedge clk);#1;end
            if(!req_ready[0]) $fatal(1,"Finite request admission timeout");
            tick;@(negedge clk);req_valid=0;
        end
    endtask
    task wait_loads;
        begin for(limit=0;limit<80 && loads!=expected_loads;limit=limit+1) tick;
            if(loads!=expected_loads) $fatal(1,"Finite LOAD replies did not drain");@(negedge clk);end
    endtask
    task drain;
        begin for(limit=0;limit<100 && (busy || memory_response || g_cache[0].dut.any_mshr || bridge.d_local_error);limit=limit+1) tick;
            if(busy || memory_response || g_cache[0].dut.any_mshr || bridge.d_local_error) $fatal(1,"Finite memory work did not drain");@(negedge clk);end
    endtask
    initial begin
        tick;tick;@(negedge clk);reset=0;
        expect_load(16'h11,32'h89abcdef,0);send(0,32'h100,0,16'h11);
        for(limit=0;limit<40 && !resp_valid[0];limit=limit+1) tick;
        if(!resp_valid[0]) $fatal(1,"Normal reply not held");
        expect_load(16'h21,0,1);send(0,32'h2000,0,16'h21);
        for(limit=0;limit<40 && !source_select[0];limit=limit+1) tick;
        if(!source_select[0]) $fatal(1,"Invalid line did not acquire a real local error owner");
        expect_load(16'h31,32'h89abcdef,0);send(0,32'h100,0,16'h31);
        prefetch_return_gate=1;idle_odd=1;repeat(5) tick;
        if(local_checks==0 || source_collisions==0 || blocked_hit_checks==0)
            $fatal(1,"Local/external source and blocked-hit competition absent");
        @(negedge clk);resp_ready=1;wait_loads;drain;
        // Invalid-cycle metadata must preserve the original ready behavior.
        idle_odd=1;repeat(2) tick;@(negedge clk);idle_odd=0;
        expect_load(16'h41,32'h76543210,0);send(0,32'h180,0,16'h41);wait_loads;drain;
        send(1,32'h100,32'hdeadbeef,16'h51);
        for(limit=0;limit<40 && acks<1;limit=limit+1) tick;
        send(1,32'h180,32'hbeadcafe,16'h61);
        for(limit=0;limit<40 && acks<2;limit=limit+1) tick;
        if(acks!=2) $fatal(1,"Real dirty STORE acknowledgements absent");
        writeback_fault=1;expect_load(16'h71,0,1);send(0,32'h280,0,16'h71);wait_loads;drain;
        if(writeback_errors==0) $fatal(1,"Real dirty writeback failure absent");
        writeback_fault=0;expect_load(16'h79,0,1);send(0,32'h400,0,16'h79);wait_loads;drain;
        if(address_errors!=1 || loads!=6) $fatal(1,"Full-address mismatch failure absent");
        $display("PASS: finite split memory response query pair loads=%0d stores=%0d local=%0d collisions=%0d blocked_hits=%0d wb_errors=%0d bad_address=%0d",loads,acks,local_checks,source_collisions,blocked_hit_checks,writeback_errors,address_errors);
        $finish;
    end
    initial begin #6000;$fatal(1,"Finite split response query sample timeout");end
endmodule
