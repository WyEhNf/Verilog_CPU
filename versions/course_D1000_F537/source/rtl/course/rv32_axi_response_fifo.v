`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Registered-credit FIFO for completed line responses, not a cache or RAM
// replacement. A nonempty queue has no fall-through input-to-output path.
// Concurrent push/pop sustains one line/cycle when a slot is already free;
// a full queue releases credit on the following cycle, never through READY.
module rv32_axi_response_fifo #(
    parameter integer WIDTH = 169,
    parameter integer DEPTH = 2,
    parameter integer PTR_WIDTH = $clog2(DEPTH),
    parameter integer COUNT_WIDTH = $clog2(DEPTH + 1)
) (
    input wire clock, reset,
    input wire in_valid, output wire in_ready,
    input wire [WIDTH-1:0] in_packet,
    output wire out_valid, input wire out_ready,
    output wire [WIDTH-1:0] out_packet
);
    wire [DEPTH*WIDTH-1:0] packets;
    reg [PTR_WIDTH-1:0] head, tail;
    reg [COUNT_WIDTH-1:0] count;
    assign in_ready = !reset && 32'(count) < DEPTH;
    assign out_valid = !reset && count != 0;
    rv32_frequency_array_read #(.WIDTH(WIDTH),.ENTRIES(DEPTH),.INDEX_WIDTH(PTR_WIDTH)) output_reader (
        .rows_i(packets),.index_i(head),.value_o(out_packet));
    genvar packet_row;
    generate for(packet_row=0;packet_row<DEPTH;packet_row=packet_row+1) begin:g_packet_owner
        rv32_frequency_word_bank #(.WIDTH(WIDTH)) owner (
            .clk_i(clock),.write_i(push && tail==packet_row),.data_i(in_packet),
            .data_o(packets[packet_row*WIDTH +: WIDTH]));
    end endgenerate
    wire push = in_valid && in_ready;
    wire pop = out_valid && out_ready;
    always @(posedge clock) begin
        if (reset)
        begin
            head <= 0;
            tail <= 0;
            count <= 0;
        end
        else
        begin
            if (push)
            begin
                tail <= tail + 1'b1;
            end
            if (pop)
                head <= head + 1'b1;
            case ({push, pop})
            2'b10: count <= count + 1'b1;
            2'b01: count <= count - 1'b1;
            default: ; // Both/neither operations leave the count unchanged.
            endcase
        end
    end
    initial begin
        if (WIDTH < 1 || DEPTH < 2 || (DEPTH & (DEPTH-1)) != 0) begin
            $display("ERROR: response FIFO needs positive width and power-of-two depth >= 2");
            $finish;
        end
    end
endmodule
