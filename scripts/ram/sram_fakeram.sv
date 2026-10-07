`timescale 1ns/1ps
// Public RAM interface. Automatically included by the framework.
// See docs/sram.md for supported configurations and access semantics.
module sram_fakeram #(
    parameter integer DEPTH = 256,
    parameter integer WIDTH = 32,
    parameter integer WRITE_GRANULARITY = WIDTH
) (
    input  wire clk,
    input  wire en,
    input  wire we,
    input  wire [((WRITE_GRANULARITY > 0 && WIDTH >= WRITE_GRANULARITY)
                  ? WIDTH / WRITE_GRANULARITY : 1)-1:0] wmask,
    input  wire [((DEPTH > 1) ? $clog2(DEPTH) : 1)-1:0] addr,
    input  wire [((WIDTH > 0) ? WIDTH : 1)-1:0] wdata,
    output reg  [((WIDTH > 0) ? WIDTH : 1)-1:0] rdata
);
    // Synthesis elaborates the empty interface with -noblackbox, then the
    // framework replaces each specialization with generated macro instances.
`ifndef SYNTHESIS
    generate
        if (DEPTH < 1 || DEPTH > 1048576) begin : invalid_depth
            initial $fatal(1, "RAM library error (%m): sram_fakeram DEPTH must be 1..1048576");
        end else if (WIDTH < 1 || WIDTH > 4096) begin : invalid_width
            initial $fatal(1, "RAM library error (%m): sram_fakeram WIDTH must be 1..4096");
        end else if (DEPTH > 16777216 / WIDTH) begin : invalid_capacity
            initial $fatal(1, "RAM library error (%m): sram_fakeram capacity exceeds 16777216 bits");
        end else if (WRITE_GRANULARITY < 1 || WRITE_GRANULARITY > WIDTH) begin : invalid_granularity
            initial $fatal(1, "RAM library error (%m): WRITE_GRANULARITY must be 1..WIDTH");
        end else if (WIDTH % WRITE_GRANULARITY != 0) begin : invalid_mask
            initial $fatal(1, "RAM library error (%m): WIDTH must be divisible by WRITE_GRANULARITY");
        end else begin : storage
            reg [WIDTH-1:0] words [0:DEPTH-1];
            function automatic [WIDTH-1:0] merge_write;
                input [WIDTH-1:0] old_word, new_word;
                input [WIDTH/WRITE_GRANULARITY-1:0] mask;
                integer lane;
                begin
                    merge_write = old_word;
                    for (lane = 0; lane < WIDTH / WRITE_GRANULARITY; lane = lane + 1)
                        if (mask[lane])
                            merge_write[lane*WRITE_GRANULARITY +: WRITE_GRANULARITY]
                                = new_word[lane*WRITE_GRANULARITY +: WRITE_GRANULARITY];
                end
            endfunction
            always @(posedge clk) begin
                rdata <= 'x;
                if (en) begin
                    if (int'(addr) >= DEPTH)
                        $fatal(1, "RAM library error (%m): address outside sram_fakeram DEPTH");
                    if (we) begin
                        // Merge locally, then schedule one array assignment.
                        // This also supports large lane counts in Verilator 5.020.
                        words[addr] <= merge_write(words[addr], wdata, wmask);
                    end else begin
                        rdata <= words[addr];
                    end
                end
            end
        end
    endgenerate
`endif
endmodule
