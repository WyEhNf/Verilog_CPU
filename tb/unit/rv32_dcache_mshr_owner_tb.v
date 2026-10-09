`timescale 1ns/1ps
module rv32_dcache_mshr_owner_tb;
    reg clk=0,reset=1;always #5 clk=~clk;
    reg req_valid=0,req_load=0,req_store=0;
    reg [31:0] req_addr=0,raw_word=0;
    reg [1:0] req_size=2;
    reg [15:0] req_mask=0,req_tag=0;
    wire [127:0] req_line={96'b0,raw_word} << {req_addr[3:0],3'b0};
    reg resp_ready=0,ack_ready=0,mem_gate=0;
    wire [1:0] req_ready,resp_valid,resp_error,ack_valid,ack_error;
    wire [31:0] resp_word[0:1],resp_addr[0:1];
    wire [15:0] resp_tag[0:1],ack_tag[0:1];
    wire [127:0] resp_line[0:1];
    wire [1:0] mem_valid,mem_write,mem_resp_ready;
    wire [31:0] mem_addr[0:1];wire [127:0] mem_data[0:1];
    wire [15:0] mem_mask[0:1];wire [7:0] mem_id[0:1];
    reg mem_response=0,busy=0;integer delay_count=0;
    reg [31:0] returned_addr=0;reg [127:0] returned_line=0;
    reg [7:0] returned_id=0;
    wire mem_ready=mem_gate && !busy && !mem_response;
    reg [127:0] line_a=128'hffeeddccbbaa99887766554489abcdef;
    reg [127:0] line_b=128'h112233445566778899aabbcc76543210;
    reg [127:0] expected_line;
    integer reads=0,writes=0,ack_fires=0,limit;
    reg [127:0] written_line=0;reg [31:0] written_addr=0;
    genvar policy;
    generate for(policy=0;policy<2;policy=policy+1) begin:g_cache
        rv32_dcache_nonblocking #(.NARROW_REQUEST_WORD(1),.MSHR_DATA_NO_CLEAR(policy),.TAG_WIDTH(16),
            .CACHE_LINES(16),.CACHE_WAYS(2),.MSHR_ENTRIES(2),.WAITER_ENTRIES(2),
            .PREFETCH(1),.TAG_SRAM(1),.STATIC_UPDATES(2),.WORD_RESPONSE(1),
            .WAY_PARALLEL_QUERY(1),.LOCAL_SRAM_COMMANDS(1),.HIT_RESPONSE_COISSUE(1),
            .REGISTERED_INDEX(1),.LOCAL_METADATA_QUERY(1),.LOCAL_ACTION_DECODE(1)) dut (
            .clk_i(clk),.reset_i(reset),.flush_i(1'b0),
            .dcache_req_valid_i(req_valid),.dcache_req_ready_o(req_ready[policy]),
            .dcache_req_is_load_i(req_load),.dcache_req_is_store_i(req_store),
            .dcache_req_addr_i(req_addr),.dcache_req_size_i(req_size),.dcache_req_unsigned_i(1'b1),
            .dcache_req_mask_i(req_mask),.dcache_req_wdata_i(req_line),.dcache_req_raw_word_i(raw_word),
            .dcache_req_rob_tag_i(req_tag),.dcache_req_lsq_tag_i(req_tag),
            .dcache_resp_valid_o(resp_valid[policy]),.dcache_resp_ready_i(resp_ready),
            .dcache_resp_lsq_tag_o(resp_tag[policy]),.dcache_resp_addr_o(resp_addr[policy]),
            .dcache_resp_line_data_o(resp_line[policy]),.dcache_resp_word_data_o(resp_word[policy]),
            .dcache_resp_error_o(resp_error[policy]),
            .dcache_store_ack_valid_o(ack_valid[policy]),.dcache_store_ack_ready_i(ack_ready),
            .dcache_store_ack_lsq_tag_o(ack_tag[policy]),.dcache_store_ack_error_o(ack_error[policy]),
            .mem_req_valid_o(mem_valid[policy]),.mem_req_ready_i(mem_ready),
            .mem_req_write_o(mem_write[policy]),.mem_req_line_addr_o(mem_addr[policy]),
            .mem_req_wdata_o(mem_data[policy]),.mem_req_wmask_o(mem_mask[policy]),.mem_req_id_o(mem_id[policy]),
            .mem_resp_valid_i(mem_response),.mem_resp_ready_o(mem_resp_ready[policy]),
            .mem_resp_line_addr_i(returned_addr),.mem_resp_data_i(returned_line),
            .mem_resp_id_i(returned_id),.mem_resp_error_i(1'b0));
    end endgenerate
    always @(negedge clk) begin
        #2;
        if(!reset) begin
            if({req_ready[0],resp_valid[0],ack_valid[0],mem_valid[0],mem_resp_ready[0]} !==
               {req_ready[1],resp_valid[1],ack_valid[1],mem_valid[1],mem_resp_ready[1]})
                $fatal(1,"MSHR owner changed a public handshake/cycle");
            if(resp_valid[0] && {resp_word[0],resp_addr[0],resp_tag[0],resp_line[0],resp_error[0]} !==
                                {resp_word[1],resp_addr[1],resp_tag[1],resp_line[1],resp_error[1]})
                $fatal(1,"MSHR owner changed a valid response payload");
            if(ack_valid[0] && {ack_tag[0],ack_error[0]} !== {ack_tag[1],ack_error[1]})
                $fatal(1,"MSHR owner changed a valid acknowledgement");
            if(mem_valid[0] && {mem_write[0],mem_addr[0],mem_data[0],mem_mask[0],mem_id[0]} !==
                               {mem_write[1],mem_addr[1],mem_data[1],mem_mask[1],mem_id[1]})
                $fatal(1,"MSHR owner changed a valid memory request");
            if(g_cache[0].dut.core_req_valid && g_cache[0].dut.core_req_wdata !== g_cache[1].dut.core_req_wdata)
                $fatal(1,"Rebuilt held query differs from original 128-bit data");
        end
    end
    always @(posedge clk) begin
        if(reset) begin busy<=0;mem_response<=0;delay_count<=0;end
        else begin
            if(ack_valid[0] && ack_ready) begin
                ack_fires<=ack_fires+1;
                if(ack_error[0]) $fatal(1,"Unexpected store acknowledgement error");
            end
            if(mem_response && mem_resp_ready[0]) mem_response<=0;
            if(busy) begin
                if(delay_count==0) begin busy<=0;mem_response<=1;end
                else delay_count<=delay_count-1;
            end
            if(mem_valid[0] && mem_ready) begin
                busy<=1;delay_count<=3;returned_addr<=mem_addr[0];returned_id<=mem_id[0];
                returned_line<=mem_write[0] ? 128'b0 : (mem_addr[0]==32'h100 ? line_a : line_b);
                if(mem_write[0]) begin
                    writes<=writes+1;written_line<=mem_data[0];written_addr<=mem_addr[0];
                    if(mem_mask[0]!=16'hffff) $fatal(1,"Dirty writeback mask changed");
                end else reads<=reads+1;
            end
        end
    end
    task tick;begin @(posedge clk);#1;end endtask
    task send(input bit store,input [31:0] address,input [1:0] size,input [31:0] word,input [15:0] mask,input [15:0] tag);
        begin
            $display("SAMPLE send t=%0t addr=%h tag=%h",$time,address,tag);
            @(negedge clk);req_valid=1;req_store=store;req_load=!store;req_addr=address;
            req_size=size;raw_word=word;req_mask=mask;req_tag=tag;#1;
            for(limit=0;limit<40 && !req_ready[0];limit=limit+1) begin tick;@(negedge clk);#1;end
            if(!req_ready[0]) $fatal(1,"Request timed out");
            tick;@(negedge clk);req_valid=0;raw_word=32'hdeadbeef;req_addr=32'hbad0bad0;
        end
    endtask
    task wait_ack(input [15:0] tag);
        begin
            for(limit=0;limit<40 && !ack_valid[0];limit=limit+1) begin tick;@(negedge clk);end
            #1;if(!ack_valid[0] || ack_tag[0]!=tag) $fatal(1,"Expected store acknowledgement missing tag=%h got=%h valid=%b action=%h query=%b ready=%b matching=%b free=%b",tag,ack_tag[0],ack_valid[0],g_cache[0].dut.static_request_action,g_cache[0].dut.core_req_valid,g_cache[0].dut.core_req_ready,g_cache[0].dut.matching_found,g_cache[0].dut.free_found);
            tick;@(negedge clk);#1;
            if(!ack_valid[0] || ack_tag[0]!=tag) $fatal(1,"Held acknowledgement changed");
            ack_ready=1;tick;@(negedge clk);ack_ready=0;
        end
    endtask
    task wait_load(input [15:0] tag,input [31:0] value);
        begin
            for(limit=0;limit<60 && !resp_valid[0];limit=limit+1) begin tick;@(negedge clk);end
            #1;if(!resp_valid[0] || resp_tag[0]!=tag || resp_word[0]!=value || resp_error[0])
                $fatal(1,"Expected merged/hit word differs: tag=%h word=%h expected=%h",resp_tag[0],resp_word[0],value);
            tick;@(negedge clk);#1;
            if(!resp_valid[0] || resp_tag[0]!=tag || resp_word[0]!=value) $fatal(1,"Held load result changed");
            resp_ready=1;tick;@(negedge clk);resp_ready=0;
        end
    endtask
    task drain;
        begin
            for(limit=0;limit<100 && (busy || mem_response ||
                    g_cache[0].dut.mshr_valid[0] || g_cache[0].dut.mshr_valid[1]);limit=limit+1) tick;
            if(busy || mem_response || g_cache[0].dut.mshr_valid[0] || g_cache[0].dut.mshr_valid[1])
                $fatal(1,"MSHR transactions did not drain");
            @(negedge clk);
        end
    endtask
    task reset_cache;
        begin
            @(negedge clk);reset=1;mem_gate=0;tick;@(negedge clk);reset=0;
        end
    endtask
    initial begin
        tick;tick;@(negedge clk);reset=0;
        // Seed BOTH banks with nonzero data before reset/reuse. Hold RFOs.
        send(1,32'h101,0,32'hba,16'h0002,16'h11);wait_ack(16'h11);
        // Use a different set: the cache deliberately holds conflicting
        // misses to the same set until the original refill is installed.
        send(1,32'h111,0,32'hdc,16'h0002,16'h19);wait_ack(16'h19);
        if(g_cache[1].dut.mshr_wdata[0]==0 || g_cache[1].dut.mshr_wdata[1]==0)
            $fatal(1,"Both stale MSHR words were not seeded");
        mem_gate=1;drain;reset_cache;
        if(g_cache[0].dut.mshr_wdata[1]!==0 || g_cache[1].dut.mshr_wdata[1]==0)
            $fatal(1,"Reset did not create deliberately different unowned words");
        // A miss creates a demand LOAD and a neighboring prefetch. Keep both
        // unsent, including the already-offered RFO, then promote/merge STOREs.
        send(0,32'h200,2,0,16'h000f,16'h21);
        tick;@(negedge clk);
        if(!g_cache[1].dut.mshr_prefetch[1] || g_cache[1].dut.mshr_store[1] ||
                g_cache[0].dut.mshr_wdata[1]!==0 || g_cache[1].dut.mshr_wdata[1]==0)
            $fatal(1,"Prefetch did not preserve unowned stale bank data");
        send(1,32'h211,0,32'haa,16'h0002,16'h29);wait_ack(16'h29);
        send(1,32'h218,2,32'haabbccdd,16'h0f00,16'h31);wait_ack(16'h31);
        if(!g_cache[1].dut.mshr_store[1] || g_cache[1].dut.mshr_prefetch[1] ||
                g_cache[0].dut.mshr_wdata[1]!==g_cache[1].dut.mshr_wdata[1])
            $fatal(1,"Store promotion did not initialize the whole word before merge");
        mem_gate=1;wait_load(16'h21,32'h76543210);drain;
        expected_line=line_b;expected_line[8 +: 8]=8'haa;expected_line[64 +: 32]=32'haabbccdd;
        send(0,32'h210,2,0,16'h000f,16'h39);wait_load(16'h39,32'h7654aa10);
        send(0,32'h218,2,0,16'h0f00,16'h41);wait_load(16'h41,32'haabbccdd);
        // WORD_RESPONSE exposes a word and zero line-data. Inspect the whole
        // merged line through a real dirty eviction, where all bytes are valid.
        send(0,32'h290,2,0,16'h000f,16'h43);wait_load(16'h43,32'h76543210);drain;
        send(0,32'h390,2,0,16'h000f,16'h45);wait_load(16'h45,32'h76543210);drain;
        if(writes!=1 || written_addr!=32'h210 || written_line!==expected_line)
            $fatal(1,"Promoted partial store dirty line differs from the full expected payload");
        // Reuse a nonzero bank again as a NONSTORE prefetch. Its refill must
        // use only memory, including the bytes left by the preceding stores.
        reset_cache;
        send(0,32'h300,2,0,16'h000f,16'h49);
        tick;@(negedge clk);
        if(!g_cache[1].dut.mshr_prefetch[1] || g_cache[1].dut.mshr_store[1] ||
                g_cache[1].dut.mshr_wdata[1]==0)
            $fatal(1,"Second stale nonstore prefetch was not exercised");
        mem_gate=1;wait_load(16'h49,32'h76543210);drain;
        send(0,32'h310,2,0,16'h000f,16'h51);wait_load(16'h51,32'h76543210);
        $display("PASS: limited paired MSHR unowned-clear cache sample");$finish;
    end
    initial begin #5000;$fatal(1,"MSHR owner sample timeout");end
endmodule
