`timescale 1ns/1ps
module rv32_dcache_narrow_query_tb;
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
    wire lsq_done;
    // This already bounded fixture also checks the new raw LSQ word across
    // fresh/held/partial-forwarded requests, MMIO and full-generation reuse.
    rv32_lsq_saved_route_fixture #(.SAVED(1)) lsq (.done(lsq_done));
    always @(posedge lsq.clk) if(!lsq.reset && lsq.request_valid)
        assert(lsq.request_data==({96'b0,lsq.dut.dcache_req_raw_word_o} << {lsq.request_addr[3:0],3'b0}))
            else $fatal(1,"Raw LSQ word differs from original valid request data");
    genvar policy;
    generate for(policy=0;policy<2;policy=policy+1) begin:g_cache
        rv32_dcache_nonblocking #(.NARROW_REQUEST_WORD(policy),.TAG_WIDTH(16),
            .CACHE_LINES(16),.CACHE_WAYS(2),.MSHR_ENTRIES(2),.WAITER_ENTRIES(2),
            .PREFETCH(0),.TAG_SRAM(1),.STATIC_UPDATES(2),.WORD_RESPONSE(1),
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
                $fatal(1,"Narrow query changed a public handshake/cycle");
            if(resp_valid[0] && {resp_word[0],resp_addr[0],resp_tag[0],resp_line[0],resp_error[0]} !==
                                {resp_word[1],resp_addr[1],resp_tag[1],resp_line[1],resp_error[1]})
                $fatal(1,"Narrow query changed a valid response payload");
            if(ack_valid[0] && {ack_tag[0],ack_error[0]} !== {ack_tag[1],ack_error[1]})
                $fatal(1,"Narrow query changed a valid acknowledgement");
            if(mem_valid[0] && {mem_write[0],mem_addr[0],mem_data[0],mem_mask[0],mem_id[0]} !==
                               {mem_write[1],mem_addr[1],mem_data[1],mem_mask[1],mem_id[1]})
                $fatal(1,"Narrow query changed a valid memory request");
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
            #1;if(!ack_valid[0] || ack_tag[0]!=tag) $fatal(1,"Expected store acknowledgement missing");
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
    initial begin
        tick;tick;@(negedge clk);reset=0;
        expected_line=line_a;expected_line[8 +: 8]=8'h7f;expected_line[48 +: 16]=16'hbeef;
        expected_line[96 +: 32]=32'h12345678;
        // Three different relative words merge in one pending miss, while
        // the RFO command and each acknowledgement encounter backpressure.
        send(1,32'h101,0,32'habcdef7f,16'h0002,16'h11);wait_ack(16'h11);
        send(1,32'h106,1,32'h1234beef,16'h00c0,16'h19);wait_ack(16'h19);
        send(1,32'h10c,2,32'h12345678,16'hf000,16'h21);wait_ack(16'h21);
        if(reads!=0 || writes!=0) $fatal(1,"Held memory command was accepted");
        mem_gate=1;
        send(0,32'h100,2,32'h55667788,16'h000f,16'h29);wait_load(16'h29,{16'h89ab,8'h7f,8'hef});
        send(0,32'h104,2,0,16'h00f0,16'h31);wait_load(16'h31,32'hbeef5544);
        send(0,32'h10c,2,0,16'hf000,16'h39);wait_load(16'h39,32'h12345678);
        // Two further colliding lines force the merged dirty way to write
        // back its exact enabled bytes and unmodified remainder.
        send(0,32'h180,2,0,16'h000f,16'h41);wait_load(16'h41,32'h76543210);
        send(0,32'h200,2,0,16'h000f,16'h49);wait_load(16'h49,32'h76543210);
        if(ack_fires!=3 || writes!=1 || written_addr!=32'h100 || written_line!=expected_line)
            $fatal(1,"Merged dirty line/writeback ownership changed");
        wait(lsq_done);#4;
        $display("PASS: limited paired narrow D-cache query and LSQ raw-word sample");$finish;
    end
    initial begin #5000;$fatal(1,"Narrow query sample timeout");end
endmodule
