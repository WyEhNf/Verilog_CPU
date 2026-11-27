`timescale 1ns/1ps

// Performance counters consume edge-qualified event pulses from the caches and
// the memory bridge. Flush does not clear architectural performance history.
module rv32_cache_stats #(
    parameter integer COUNTER_WIDTH = 64
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         i_event_request_i,
    input  wire                         i_event_hit_i,
    input  wire                         i_event_miss_i,
    input  wire                         i_event_refill_i,
    input  wire                         i_event_stall_i,
    input  wire                         d_event_request_i,
    input  wire                         d_event_hit_i,
    input  wire                         d_event_miss_i,
    input  wire                         d_event_refill_i,
    input  wire                         d_event_writeback_i,
    input  wire                         d_event_stall_i,
    input  wire                         i_mem_request_fire_i,
    input  wire                         d_mem_read_fire_i,
    input  wire                         d_mem_write_fire_i,
    output reg  [COUNTER_WIDTH-1:0]     i_request_count_o,
    output reg  [COUNTER_WIDTH-1:0]     i_hit_count_o,
    output reg  [COUNTER_WIDTH-1:0]     i_miss_count_o,
    output reg  [COUNTER_WIDTH-1:0]     i_refill_count_o,
    output reg  [COUNTER_WIDTH-1:0]     i_stall_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_request_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_hit_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_miss_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_refill_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_writeback_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_stall_count_o,
    output reg  [COUNTER_WIDTH-1:0]     i_mem_request_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_mem_read_count_o,
    output reg  [COUNTER_WIDTH-1:0]     d_mem_write_count_o
);
    always @(posedge clk_i) begin
        if (reset_i) begin
            i_request_count_o <= {COUNTER_WIDTH{1'b0}};
            i_hit_count_o <= {COUNTER_WIDTH{1'b0}};
            i_miss_count_o <= {COUNTER_WIDTH{1'b0}};
            i_refill_count_o <= {COUNTER_WIDTH{1'b0}};
            i_stall_count_o <= {COUNTER_WIDTH{1'b0}};
            d_request_count_o <= {COUNTER_WIDTH{1'b0}};
            d_hit_count_o <= {COUNTER_WIDTH{1'b0}};
            d_miss_count_o <= {COUNTER_WIDTH{1'b0}};
            d_refill_count_o <= {COUNTER_WIDTH{1'b0}};
            d_writeback_count_o <= {COUNTER_WIDTH{1'b0}};
            d_stall_count_o <= {COUNTER_WIDTH{1'b0}};
            i_mem_request_count_o <= {COUNTER_WIDTH{1'b0}};
            d_mem_read_count_o <= {COUNTER_WIDTH{1'b0}};
            d_mem_write_count_o <= {COUNTER_WIDTH{1'b0}};
        end else begin
            if (i_event_request_i) i_request_count_o <= i_request_count_o + 1'b1;
            if (i_event_hit_i) i_hit_count_o <= i_hit_count_o + 1'b1;
            if (i_event_miss_i) i_miss_count_o <= i_miss_count_o + 1'b1;
            if (i_event_refill_i) i_refill_count_o <= i_refill_count_o + 1'b1;
            if (i_event_stall_i) i_stall_count_o <= i_stall_count_o + 1'b1;
            if (d_event_request_i) d_request_count_o <= d_request_count_o + 1'b1;
            if (d_event_hit_i) d_hit_count_o <= d_hit_count_o + 1'b1;
            if (d_event_miss_i) d_miss_count_o <= d_miss_count_o + 1'b1;
            if (d_event_refill_i) d_refill_count_o <= d_refill_count_o + 1'b1;
            if (d_event_writeback_i) d_writeback_count_o <= d_writeback_count_o + 1'b1;
            if (d_event_stall_i) d_stall_count_o <= d_stall_count_o + 1'b1;
            if (i_mem_request_fire_i) i_mem_request_count_o <= i_mem_request_count_o + 1'b1;
            if (d_mem_read_fire_i) d_mem_read_count_o <= d_mem_read_count_o + 1'b1;
            if (d_mem_write_fire_i) d_mem_write_count_o <= d_mem_write_count_o + 1'b1;
        end
    end

    initial begin
        if (COUNTER_WIDTH < 1) begin
            $display("ERROR: cache statistics COUNTER_WIDTH must be positive (got %0d)", COUNTER_WIDTH);
            $finish;
        end
    end
endmodule
