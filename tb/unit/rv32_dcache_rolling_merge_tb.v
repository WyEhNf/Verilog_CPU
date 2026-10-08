`timescale 1ns/1ps
// Limited directed rolling coalescing sample, not a whole-cache/CPU proof.
module rv32_dcache_rolling_merge_tb #(
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
        .STORE_MERGE_DELAY(16), .STORE_MERGE_POLICY(1), .TAG_SRAM(TAG_SRAM),
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
    reg [127:0] expected_line;
    task prefix_line;
        input [31:0] base;
        begin
            submit(base,1,128'h11111111,16'h000f,2);
            repeat(8) begin
                if(mem_valid) $fatal(1,"prefix started RFO too early");
                @(negedge clk);
            end
            submit(base+4,1,128'h2222222200000000,16'h00f0,2);
            repeat(8) begin
                if(mem_valid) $fatal(1,"second word did not renew prefix timer");
                @(negedge clk);
            end
            submit(base+8,1,128'h333333330000000000000000,16'h0f00,2);
            repeat(8) begin
                if(mem_valid) $fatal(1,"third word did not renew prefix timer");
                @(negedge clk);
            end
            submit(base+12,1,128'h44444444000000000000000000000000,16'hf000,2);
            repeat(4) @(negedge clk);
            if(mem_valid) $fatal(1,"fully known prefix line sent RFO");
        end
    endtask
    initial begin
        repeat(3) @(negedge clk); reset=0;
        step=1;
        prefix_line(0);
        if(writes!=0 || reads!=0 || acknowledgements!=4)
            $fatal(1,"prefix traffic/fast ACK counts");
        submit(0,0,0,16'hf,2); consume(32'h11111111);
        submit(12,0,0,16'hf000,2); consume(32'h44444444);
        step=2;
        // Non-prefix word starts an RFO immediately. Even completing the
        // mask under backpressure must not retract this already offered read.
        submit(68,1,128'hbbbbbbbb00000000,16'h00f0,2);
        if(!mem_valid || mem_write || mem_addr!==64) $fatal(1,"scatter RFO not eager");
        saved_id=mem_id;
        submit(64,1,128'haaaaaaaa,16'h000f,2);
        submit(72,1,128'hcccccccc0000000000000000,16'h0f00,2);
        submit(76,1,128'hdddddddd000000000000000000000000,16'hf000,2);
        repeat(3) begin
            if(!mem_valid || mem_write || mem_addr!==64 || mem_id!==saved_id)
                $fatal(1,"offered RFO withdrew or changed identity");
            @(negedge clk);
        end
        take_memory(0,64,0); response(64,128'hdeadbeefdeadbeefdeadbeefdeadbeef,0);
        submit(64,0,0,16'hf,2); consume(32'haaaaaaaa);
        submit(76,0,0,16'hf000,2); consume(32'hdddddddd);
        step=3;
        // Populate the other way with a fully known dirty line.
        prefix_line(128);
        submit(256,1,128'h55555555,16'h000f,2);
        while(!mem_valid) @(negedge clk);
        expected_line=128'h44444444333333332222222211111111;
        if(!mem_write || mem_addr!==0 || mem_mask!==16'hffff || mem_data!==expected_line)
            $fatal(1,"dirty victim data changed before prefix refill");
        take_memory(1,0,16'hffff);
        // Let the original allocation timer expire during writeback.
        repeat(20) @(negedge clk);
        response(0,0,0);
        repeat(8) begin
            if(mem_valid) $fatal(1,"victim response did not renew merge window");
            @(negedge clk);
        end
        submit(260,1,128'h6666666600000000,16'h00f0,2);
        repeat(8) begin
            if(mem_valid) $fatal(1,"post-victim second prefix window");
            @(negedge clk);
        end
        submit(264,1,128'h777777770000000000000000,16'h0f00,2);
        submit(268,1,128'h88888888000000000000000000000000,16'hf000,2);
        repeat(4) @(negedge clk);
        if(mem_valid || reads!=1 || writes!=1 || acknowledgements!=16)
            $fatal(1,"post-victim prefix RFO/count or fast ACK failure");
        submit(256,0,0,16'hf,2); consume(32'h55555555);
        submit(268,0,0,16'hf000,2); consume(32'h88888888);
        $display("PASS: limited rolling merge prefix renewal, eager scatter, irrevocable RFO, victim-window renewal, masks/data and fast ACK");
        $finish;
    end
endmodule
