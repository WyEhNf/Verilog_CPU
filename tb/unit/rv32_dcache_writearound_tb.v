`timescale 1ns/1ps
// Limited directed ownership/traffic sample, not a whole-cache/CPU proof.
module rv32_dcache_writearound_tb #(
    parameter integer TAG_SRAM=1,
    parameter integer STATIC_UPDATES=2,
    parameter integer CACHE_WAYS=2,
    parameter integer REGISTERED_INDEX=1
);
    reg clk=0, reset=1, flush=0;
    always #5 clk=~clk;
    reg req_valid=0, req_load=1, req_store=0;
    reg [31:0] req_addr=0;
    reg [1:0] req_size=2;
    reg req_unsigned=1;
    reg [15:0] req_mask=16'hf, req_tag=0;
    reg [127:0] req_data=0;
    wire req_ready, resp_valid, resp_error, ack_valid, ack_error;
    reg resp_ready=0, ack_ready=1;
    wire [31:0] resp_word, resp_addr;
    wire [127:0] resp_line;
    wire [15:0] resp_tag, ack_tag;
    wire mem_valid, mem_write, mem_resp_ready;
    reg mem_ready=0, mem_resp_valid=0, mem_error=0;
    wire [31:0] mem_addr;
    wire [127:0] mem_data;
    wire [15:0] mem_mask;
    wire [7:0] mem_id;
    reg [31:0] mem_resp_addr=0;
    reg [127:0] mem_resp_data=0;
    reg [7:0] mem_resp_id=0, saved_id;
    integer writes=0, reads=0, acknowledgements=0, step=0;
    reg [15:0] around_tag;
    always @(posedge clk) if(!reset) begin
        if(mem_valid && mem_ready) begin
            if(mem_write) writes=writes+1; else reads=reads+1;
        end
        if(ack_valid && ack_ready) acknowledgements=acknowledgements+1;
    end
    initial begin #20000; $fatal(1,"write-around timeout step=%0d",step); end
    rv32_dcache_nonblocking #(.CACHE_LINES(16), .CACHE_WAYS(CACHE_WAYS),
        .MSHR_ENTRIES(4), .PREFETCH(0), .TAG_WIDTH(16),
        .STORE_MERGE_DELAY(16), .STORE_MISS_WRITE_AROUND(1), .TAG_SRAM(TAG_SRAM),
        .STATIC_UPDATES(STATIC_UPDATES), .REGISTERED_INDEX(REGISTERED_INDEX),
        .LOCAL_METADATA_QUERY(TAG_SRAM)) dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush),
        .dcache_req_valid_i(req_valid), .dcache_req_ready_o(req_ready),
        .dcache_req_is_load_i(req_load), .dcache_req_is_store_i(req_store),
        .dcache_req_addr_i(req_addr), .dcache_req_size_i(req_size),
        .dcache_req_unsigned_i(req_unsigned), .dcache_req_mask_i(req_mask),
        .dcache_req_wdata_i(req_data), .dcache_req_rob_tag_i(req_tag),
        .dcache_req_lsq_tag_i(req_tag), .dcache_resp_valid_o(resp_valid),
        .dcache_resp_ready_i(resp_ready), .dcache_resp_lsq_tag_o(resp_tag),
        .dcache_resp_addr_o(resp_addr), .dcache_resp_line_data_o(resp_line),
        .dcache_resp_word_data_o(resp_word), .dcache_resp_error_o(resp_error),
        .dcache_store_ack_valid_o(ack_valid), .dcache_store_ack_ready_i(ack_ready),
        .dcache_store_ack_lsq_tag_o(ack_tag),
        .dcache_store_ack_error_o(ack_error), .mem_req_valid_o(mem_valid),
        .mem_req_ready_i(mem_ready), .mem_req_write_o(mem_write),
        .mem_req_line_addr_o(mem_addr), .mem_req_wdata_o(mem_data),
        .mem_req_wmask_o(mem_mask), .mem_req_id_o(mem_id), .mem_resp_valid_i(mem_resp_valid),
        .mem_resp_ready_o(mem_resp_ready), .mem_resp_line_addr_i(mem_resp_addr),
        .mem_resp_data_i(mem_resp_data), .mem_resp_id_i(mem_resp_id),
        .mem_resp_error_i(mem_error)
    );
    task submit;
        input [31:0] address;
        input store;
        input [127:0] data;
        input [15:0] mask;
        input [1:0] size;
        begin
            @(negedge clk);
            req_tag=req_tag+1; req_addr=address;
            req_load=!store; req_store=store; req_data=data;
            req_mask=mask; req_size=size; req_valid=1;
            #1;
            while(!req_ready) begin @(negedge clk); #1; end
            @(negedge clk); req_valid=0;
            // The synchronous-tag interface owns one accepted query.
            if(TAG_SRAM!=0) begin
                #1;
                while(dut.core_req_valid && !dut.core_req_ready) begin @(negedge clk); #1; end
                @(negedge clk);
            end
        end
    endtask
    task take_memory;
        input write;
        input [31:0] address;
        input [15:0] mask;
        begin
            while(!mem_valid) @(negedge clk);
            if(mem_write!==write || mem_addr!==address || (write && mem_mask!==mask))
                $fatal(1,"memory packet step=%0d write=%b addr=%h mask=%h",step,mem_write,mem_addr,mem_mask);
            saved_id=mem_id;
            mem_ready=1; @(negedge clk); mem_ready=0;
        end
    endtask
    task response;
        input [31:0] address;
        input [127:0] data;
        input error;
        begin
            mem_resp_addr=address; mem_resp_data=data;
            mem_resp_id=saved_id; mem_error=error; mem_resp_valid=1;
            #1;
            while(!mem_resp_ready) begin @(negedge clk); #1; end
            @(negedge clk); mem_resp_valid=0; mem_error=0;
        end
    endtask
    task consume;
        input [31:0] expected;
        begin
            while(!resp_valid) @(negedge clk);
            if(resp_error || resp_tag!==req_tag || resp_word!==expected)
                $fatal(1,"load step=%0d data=%h expected=%h tag=%h/%h",step,resp_word,expected,resp_tag,req_tag);
            resp_ready=1; @(negedge clk); resp_ready=0;
        end
    endtask
    initial begin
        repeat(3) @(negedge clk); reset=0;
        // Fill both ways of one set, then dirty them through normal hit writes.
        step=1;
        submit(0,0,0,16'hf,2); take_memory(0,0,0); response(0,128'h11223344,0); consume(32'h11223344);
        submit(128,0,0,16'hf,2); take_memory(0,128,0); response(128,128'h55667788,0); consume(32'h55667788);
        submit(0,1,128'h12345678,16'hf,2);
        submit(128,1,128'h87654321,16'hf,2);
        repeat(2) @(negedge clk);
        if(acknowledgements!=2) $fatal(1,"normal hit ACK changed");
        step=2;
        // A single enabled byte is a masked write, not an RFO or victim write.
        ack_ready=0;
        submit(261,1,128'h00000000000000000000aa0000000000,16'h0020,0);
        around_tag=req_tag;
        while(!mem_valid) @(negedge clk);
        saved_id=mem_id;
        repeat(3) begin
            if(!mem_valid || !mem_write || mem_addr!==256 || mem_mask!==16'h0020 ||
               mem_data!==128'h00000000000000000000aa0000000000 || ack_valid ||
               dut.valid_bits!==16'h0003 || dut.dirty_bits[1:0]!==2'b11)
                $fatal(1,"unstable offer, early ACK, or victim corrupted");
            @(negedge clk);
        end
        // Covered byte forwards while the memory offer is backpressured.
        submit(261,0,0,16'h0020,0); consume(32'haa);
        step=3;
        // An uncovered word waits for the around write before reading memory.
        @(negedge clk); req_tag=req_tag+1; req_addr=256; req_size=2;
        req_mask=16'hf; req_valid=1; req_load=1; req_store=0;
        #1;
        if(TAG_SRAM!=0) begin
            if(!req_ready) $fatal(1,"tag query admission failed");
            @(negedge clk); req_valid=0;
        end
        repeat(3) begin
            #1;
            if(dut.core_req_ready || resp_valid || ack_valid)
                $fatal(1,"uncovered load did not wait for write response");
            @(negedge clk);
        end
        take_memory(1,256,16'h0020);
        response(256,0,0);
        #1;
        if(!ack_valid || ack_error || ack_tag!==around_tag)
            $fatal(1,"B response lost full store owner");
        // FF-tag interface now accepts the waiting load; SRAM query was held.
        if(TAG_SRAM==0) begin
            while(!req_ready) @(negedge clk);
            @(negedge clk); req_valid=0;
        end
        // The subsequent load may allocate normally and evict a dirty line.
        // Its full-line writeback belongs to that load, not the around store.
        while(!mem_valid) @(negedge clk);
        if(mem_data!==128'h12345678) $fatal(1,"normal dirty victim bytes changed");
        take_memory(1,0,16'hffff);
        response(0,0,0);
        take_memory(0,256,0); response(256,128'h00000000000000000000aa00abcdef01,0);
        consume(32'habcdef01);
        repeat(3) begin
            if(!ack_valid || ack_error || ack_tag!==around_tag || writes!=2 || reads!=3)
                $fatal(1,"held around ACK lost/duplicated or extra traffic");
            @(negedge clk);
        end
        ack_ready=1; @(negedge clk);
        if(ack_valid || acknowledgements!=3) $fatal(1,"around ACK consumed twice");
        submit(128,0,0,16'hf,2); consume(32'h87654321);
        if(reads!=3) $fatal(1,"around miss evicted the other dirty way");
        step=4;
        // Reading the new line may evict a dirty victim normally. Reset just
        // isolates the next protocol sample from ordinary replacement traffic.
        reset=1; repeat(2) @(negedge clk); reset=0;
        writes=0; reads=0; acknowledgements=0; ack_ready=0;
        submit(394,1,128'h00000000cafe00000000000000000000,16'h0c00,1);
        around_tag=req_tag;
        take_memory(1,384,16'h0c00);
        // Address mismatch is a precise error, with no follow-up RFO.
        response(400,0,0);
        repeat(3) begin
            if(!ack_valid || !ack_error || ack_tag!==around_tag || mem_valid || writes!=1 || reads!=0)
                $fatal(1,"mismatched B response error/ownership or RFO");
            @(negedge clk);
        end
        ack_ready=1; @(negedge clk);
        if(ack_valid || acknowledgements!=1) $fatal(1,"error ACK consumed twice");
        $display("PASS: limited write-around masked offer, covered forwarding, uncovered-load ordering, dirty preservation, held/full-tag ACK and mismatch error tag=%0d mode=%0d",TAG_SRAM,STATIC_UPDATES);
        $finish;
    end
endmodule
