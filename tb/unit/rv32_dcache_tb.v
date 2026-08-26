`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_dcache_tb;
    reg clk, reset, flush;
    reg req_valid, req_load, req_store, req_unsigned;
    wire req_ready;
    reg [31:0] req_addr;
    reg [1:0] req_size;
    reg [15:0] req_mask, req_rob;
    reg [127:0] req_wdata;
    reg [15:0] req_lsq;
    wire resp_valid, resp_line_valid, resp_error;
    reg resp_ready;
    wire [15:0] resp_lsq;
    wire [31:0] resp_addr, resp_word;
    wire [127:0] resp_line;
    wire ack_valid, ack_error;
    reg ack_ready;
    wire [15:0] ack_lsq;
    wire mem_req_valid, mem_req_ready, mem_req_write;
    wire [31:0] mem_req_addr;
    wire [127:0] mem_req_wdata;
    wire [15:0] mem_req_wmask;
    wire [7:0] mem_req_id;
    wire mem_resp_valid, mem_resp_ready, mem_resp_error;
    wire [31:0] mem_resp_addr;
    wire [127:0] mem_resp_data;
    wire [7:0] mem_resp_id;
    wire event_request, event_hit, event_miss, event_refill, event_writeback, event_stall;
    integer cycle, bad, writebacks, refills, last_req_cycle, actual_req_cycle;
    reg [15:0] held_lsq;
    reg [31:0] held_addr, held_word;
    reg [127:0] held_line;
    reg held_error;

    rv32_dcache dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush),
        .dcache_req_valid_i(req_valid), .dcache_req_ready_o(req_ready),
        .dcache_req_is_load_i(req_load), .dcache_req_is_store_i(req_store),
        .dcache_req_addr_i(req_addr), .dcache_req_size_i(req_size),
        .dcache_req_unsigned_i(req_unsigned), .dcache_req_mask_i(req_mask),
        .dcache_req_wdata_i(req_wdata), .dcache_req_rob_tag_i(req_rob),
        .dcache_req_lsq_tag_i(req_lsq), .dcache_resp_valid_o(resp_valid),
        .dcache_resp_ready_i(resp_ready), .dcache_resp_lsq_tag_o(resp_lsq),
        .dcache_resp_addr_o(resp_addr), .dcache_resp_line_data_o(resp_line),
        .dcache_resp_word_data_o(resp_word), .dcache_resp_line_valid_o(resp_line_valid),
        .dcache_resp_error_o(resp_error), .dcache_store_ack_valid_o(ack_valid),
        .dcache_store_ack_ready_i(ack_ready), .dcache_store_ack_lsq_tag_o(ack_lsq),
        .dcache_store_ack_error_o(ack_error), .mem_req_valid_o(mem_req_valid),
        .mem_req_ready_i(mem_req_ready), .mem_req_write_o(mem_req_write),
        .mem_req_line_addr_o(mem_req_addr), .mem_req_wdata_o(mem_req_wdata),
        .mem_req_wmask_o(mem_req_wmask), .mem_req_id_o(mem_req_id),
        .mem_resp_valid_i(mem_resp_valid), .mem_resp_ready_o(mem_resp_ready),
        .mem_resp_line_addr_i(mem_resp_addr), .mem_resp_data_i(mem_resp_data),
        .mem_resp_id_i(mem_resp_id), .mem_resp_error_i(mem_resp_error),
        .event_request_o(event_request), .event_hit_o(event_hit),
        .event_miss_o(event_miss), .event_refill_o(event_refill),
        .event_writeback_o(event_writeback), .event_stall_o(event_stall)
    );

    rv32im_memory_model mem (
        .clk_i(clk), .reset_i(reset), .i_req_valid_i(1'b0), .i_req_ready_o(),
        .i_req_line_addr_i(32'd0), .i_req_id_i(8'd0), .i_resp_valid_o(),
        .i_resp_ready_i(1'b1), .i_resp_line_addr_o(), .i_resp_data_o(),
        .i_resp_id_o(), .i_resp_error_o(), .d_req_valid_i(mem_req_valid),
        .d_req_ready_o(mem_req_ready), .d_req_write_i(mem_req_write),
        .d_req_line_addr_i(mem_req_addr), .d_req_wdata_i(mem_req_wdata),
        .d_req_wmask_i(mem_req_wmask), .d_req_id_i(mem_req_id),
        .d_resp_valid_o(mem_resp_valid), .d_resp_ready_i(mem_resp_ready),
        .d_resp_line_addr_o(mem_resp_addr), .d_resp_data_o(mem_resp_data),
        .d_resp_id_o(mem_resp_id), .d_resp_error_o(mem_resp_error)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (dut.request_fire) actual_req_cycle = cycle;
        if (event_writeback) writebacks = writebacks + 1;
        if (event_refill) refills = refills + 1;
    end

    task clear_req;
        begin
            req_valid = 1'b0; req_load = 1'b0; req_store = 1'b0; req_unsigned = 1'b0;
            req_addr = 0; req_size = 0; req_mask = 0; req_rob = 0; req_wdata = 0; req_lsq = 0;
        end
    endtask

    task send_req;
        input is_load;
        input is_store;
        input [31:0] address;
        input [1:0] size;
        input unsign;
        input [15:0] mask;
        input [127:0] wdata;
        input [15:0] lsq;
        begin
            @(negedge clk);
            req_valid = 1'b1; req_load = is_load; req_store = is_store; req_addr = address;
            req_size = size; req_unsigned = unsign; req_mask = mask; req_wdata = wdata; req_lsq = lsq; req_rob = lsq;
            while (!req_ready) @(negedge clk);
            @(posedge clk); #1; last_req_cycle = cycle; @(negedge clk); clear_req();
        end
    endtask

    task wait_load;
        input [15:0] lsq;
        input [31:0] address;
        input [31:0] expected;
        input expect_error;
        begin
            while (!resp_valid) @(negedge clk);
            if (resp_lsq != lsq || resp_addr != address || resp_word != expected ||
                resp_error != expect_error || (!expect_error && !resp_line_valid)) begin
                $display("FAIL: A-05 load lsq=%04x/%04x addr=%08x/%08x word=%08x/%08x error=%b/%b line=%b",
                         resp_lsq, lsq, resp_addr, address, resp_word, expected, resp_error, expect_error, resp_line_valid);
                bad = bad + 1;
            end
            held_lsq = resp_lsq; held_addr = resp_addr; held_word = resp_word; held_line = resp_line; held_error = resp_error;
            @(negedge clk);
            if (resp_valid && (resp_lsq != held_lsq || resp_addr != held_addr || resp_word != held_word || resp_line != held_line || resp_error != held_error)) begin
                $display("FAIL: A-05 load response changed after handshake"); bad = bad + 1;
            end
        end
    endtask

    task wait_store;
        input [15:0] lsq;
        begin
            while (!ack_valid) @(negedge clk);
            if (ack_lsq != lsq || ack_error) begin
                $display("FAIL: A-05 store ack lsq=%04x/%04x error=%b", ack_lsq, lsq, ack_error);
                bad = bad + 1;
            end
            @(negedge clk);
        end
    endtask

    initial begin
        cycle = 0; bad = 0; writebacks = 0; refills = 0; last_req_cycle = 0; actual_req_cycle = 0; reset = 1; flush = 0; resp_ready = 1'b1; ack_ready = 1'b1; clear_req();
        mem.memory[16'h0100] = 8'h11; mem.memory[16'h0101] = 8'h22; mem.memory[16'h0102] = 8'h33; mem.memory[16'h0103] = 8'h44;
        mem.memory[16'h1100] = 8'h55; mem.memory[16'h1101] = 8'h66; mem.memory[16'h1102] = 8'h77; mem.memory[16'h1103] = 8'h88;
        mem.memory[16'h2000] = 8'h80;
        repeat (3) @(posedge clk); @(negedge clk); reset = 1'b0; #1;

        // Cold miss/refill and little-endian word extraction.
        send_req(1, 0, 32'h00000100, `RV32IM_MEM_WORD, 1'b1, 16'h0, 0, 16'h0101);
        wait_load(16'h0101, 32'h00000100, 32'h44332211, 1'b0);

        // Warm hit has a strict three-cycle request-to-response latency.
        send_req(1, 0, 32'h00000100, `RV32IM_MEM_WORD, 1'b1, 16'h0, 0, 16'h0102);
        wait_load(16'h0102, 32'h00000100, 32'h44332211, 1'b0);
        #1;
        // The response is sampled on the following negedge, i.e. four counter
        // ticks after the accepting rising edge (three registered stages).
        if ((cycle - actual_req_cycle) != 4) begin $display("FAIL: A-05 warm-hit latency %0d (accept=%0d now=%0d)", cycle-actual_req_cycle, actual_req_cycle, cycle); bad = bad + 1; end

        // A response must hold every payload field while the consumer is stalled.
        resp_ready = 1'b0;
        send_req(1, 0, 32'h00000100, `RV32IM_MEM_WORD, 1'b1, 16'h0, 0, 16'h0105);
        while (!resp_valid) @(negedge clk);
        held_lsq = resp_lsq; held_addr = resp_addr; held_word = resp_word; held_line = resp_line; held_error = resp_error;
        repeat (3) begin
            @(negedge clk);
            if (!resp_valid || resp_lsq != held_lsq || resp_addr != held_addr || resp_word != held_word || resp_line != held_line || resp_error != held_error) begin
                $display("FAIL: A-05 response changed under backpressure"); bad = bad + 1;
            end
        end
        resp_ready = 1'b1;
        wait_load(16'h0105, 32'h00000100, 32'h44332211, 1'b0);

        // Store hit updates one byte and is visible to subsequent loads.
        send_req(0, 1, 32'h00000101, `RV32IM_MEM_BYTE, 1'b0, 16'h0002,
                 128'h0000000000000000000000000000aa00, 16'h0103);
        wait_store(16'h0103);
        send_req(1, 0, 32'h00000100, `RV32IM_MEM_WORD, 1'b1, 16'h0, 0, 16'h0104);
        wait_load(16'h0104, 32'h00000100, 32'h4433aa11, 1'b0);

        // Same-set conflict forces dirty writeback then refill of the new line.
        send_req(1, 0, 32'h00001100, `RV32IM_MEM_WORD, 1'b1, 16'h0, 0, 16'h1101);
        wait_load(16'h1101, 32'h00001100, 32'h88776655, 1'b0);
        if (writebacks == 0) begin $display("FAIL: A-05 dirty eviction did not write back"); bad = bad + 1; end

        // Flushing a load miss drops its response but retains the refilled line.
        send_req(1, 0, 32'h00002000, `RV32IM_MEM_BYTE, 1'b0, 16'h0, 0, 16'h2001);
        while (!mem_req_valid) @(negedge clk);
        @(negedge clk); flush = 1'b1; @(posedge clk); @(negedge clk); flush = 1'b0;
        repeat (60) @(negedge clk);
        if (resp_valid) begin $display("FAIL: A-05 flushed load response escaped"); bad = bad + 1; end
        send_req(1, 0, 32'h00002000, `RV32IM_MEM_BYTE, 1'b0, 16'h0, 0, 16'h2002);
        wait_load(16'h2002, 32'h00002000, 32'hffffff80, 1'b0);

        // Out-of-range memory returns a deterministic error.
        send_req(1, 0, 32'h00100000, `RV32IM_MEM_WORD, 1'b1, 16'h0, 0, 16'he001);
        wait_load(16'he001, 32'h00100000, 32'd0, 1'b1);

        if (bad != 0 || refills < 3) begin
            $display("FAIL: A-05 D-cache checks=%0d refills=%0d writebacks=%0d", bad, refills, writebacks);
            $finish(1);
        end
        $display("PASS: A-05 D-cache hits, byte merge, writeback, flush, and errors");
        $finish(0);
    end

    initial begin
        #30000;
        $display("FAIL: A-05 timeout cycle=%0d", cycle);
        $finish(1);
    end
endmodule
