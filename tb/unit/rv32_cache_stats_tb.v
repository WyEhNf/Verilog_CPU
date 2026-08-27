`timescale 1ns/1ps

module rv32_cache_stats_tb;
    reg clk, reset;
    reg i_request, i_hit, i_miss, i_refill, i_stall;
    reg d_request, d_hit, d_miss, d_refill, d_writeback, d_stall;
    reg i_mem_request, d_mem_read, d_mem_write;
    wire [7:0] i_requests, i_hits, i_misses, i_refills, i_stalls;
    wire [7:0] d_requests, d_hits, d_misses, d_refills, d_writebacks, d_stalls;
    wire [7:0] i_mem_requests, d_mem_reads, d_mem_writes;

    rv32_cache_stats #(.COUNTER_WIDTH(8)) dut (
        .clk_i(clk), .reset_i(reset),
        .i_event_request_i(i_request), .i_event_hit_i(i_hit),
        .i_event_miss_i(i_miss), .i_event_refill_i(i_refill),
        .i_event_stall_i(i_stall), .d_event_request_i(d_request),
        .d_event_hit_i(d_hit), .d_event_miss_i(d_miss),
        .d_event_refill_i(d_refill), .d_event_writeback_i(d_writeback),
        .d_event_stall_i(d_stall), .i_mem_request_fire_i(i_mem_request),
        .d_mem_read_fire_i(d_mem_read), .d_mem_write_fire_i(d_mem_write),
        .i_request_count_o(i_requests), .i_hit_count_o(i_hits),
        .i_miss_count_o(i_misses), .i_refill_count_o(i_refills),
        .i_stall_count_o(i_stalls), .d_request_count_o(d_requests),
        .d_hit_count_o(d_hits), .d_miss_count_o(d_misses),
        .d_refill_count_o(d_refills), .d_writeback_count_o(d_writebacks),
        .d_stall_count_o(d_stalls), .i_mem_request_count_o(i_mem_requests),
        .d_mem_read_count_o(d_mem_reads), .d_mem_write_count_o(d_mem_writes)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end

    task clear_events;
        begin
            i_request = 0; i_hit = 0; i_miss = 0; i_refill = 0; i_stall = 0;
            d_request = 0; d_hit = 0; d_miss = 0; d_refill = 0; d_writeback = 0; d_stall = 0;
            i_mem_request = 0; d_mem_read = 0; d_mem_write = 0;
        end
    endtask

    task check_zero;
        begin
            if (i_requests !== 0 || i_hits !== 0 || i_misses !== 0 || i_refills !== 0 || i_stalls !== 0 ||
                d_requests !== 0 || d_hits !== 0 || d_misses !== 0 || d_refills !== 0 ||
                d_writebacks !== 0 || d_stalls !== 0 || i_mem_requests !== 0 ||
                d_mem_reads !== 0 || d_mem_writes !== 0) begin
                $display("FAIL: A-06 statistics reset values are not zero"); $finish(1);
            end
        end
    endtask

    initial begin
        reset = 1'b1; clear_events();
        repeat (3) @(posedge clk); #1; check_zero();
        @(negedge clk); reset = 1'b0;

        // Every event input is an edge-qualified pulse and increments only its counter.
        i_request = 1; i_hit = 1; i_miss = 1; i_refill = 1; i_stall = 1;
        d_request = 1; d_hit = 1; d_miss = 1; d_refill = 1; d_writeback = 1; d_stall = 1;
        i_mem_request = 1; d_mem_read = 1; d_mem_write = 1;
        @(posedge clk); #1; clear_events();
        if (i_requests != 1 || i_hits != 1 || i_misses != 1 || i_refills != 1 || i_stalls != 1 ||
            d_requests != 1 || d_hits != 1 || d_misses != 1 || d_refills != 1 ||
            d_writebacks != 1 || d_stalls != 1 || i_mem_requests != 1 ||
            d_mem_reads != 1 || d_mem_writes != 1) begin
            $display("FAIL: A-06 statistics did not count simultaneous pulses"); $finish(1);
        end

        // A high event on consecutive cycles represents consecutive handshakes/stall cycles.
        @(negedge clk); i_stall = 1; d_stall = 1;
        repeat (3) @(posedge clk);
        #1; clear_events();
        if (i_stalls != 4 || d_stalls != 4 || i_requests != 1 || d_requests != 1 ||
            i_mem_requests != 1 || d_mem_reads != 1 || d_mem_writes != 1) begin
            $display("FAIL: A-06 statistics edge accounting Istall=%0d Dstall=%0d", i_stalls, d_stalls);
            $finish(1);
        end

        repeat (3) @(posedge clk); #1;
        if (i_stalls != 4 || d_stalls != 4) begin
            $display("FAIL: A-06 statistics changed without events"); $finish(1);
        end
        @(negedge clk); reset = 1'b1;
        @(posedge clk); #1; check_zero();
        $display("PASS: A-06 cache statistics count only defined event edges");
        $finish(0);
    end

    initial begin
        #2000;
        $display("FAIL: A-06 cache statistics timeout");
        $finish(1);
    end
endmodule
