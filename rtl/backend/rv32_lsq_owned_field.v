`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Owns actual architectural queue fields. The enable/hold mux is local,
// so a shared write decision drives one input rather than every data bit.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.
module rv32_lsq_owned_field #(parameter integer WIDTH=32, QUALIFIED_INPUT=0) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    initial if(QUALIFIED_INPUT!=0 && QUALIFIED_INPUT!=1)
        $fatal(1,"QUALIFIED_INPUT must be 0 or 1");
    generate if(QUALIFIED_INPUT!=0) begin:g_qualified
        rv32_frequency_qualified_word_bank #(.WIDTH(WIDTH)) payload_owner (
            .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
    end else begin:g_original
        rv32_frequency_word_bank #(.WIDTH(WIDTH)) payload_owner (
            .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
    end endgenerate
endmodule
