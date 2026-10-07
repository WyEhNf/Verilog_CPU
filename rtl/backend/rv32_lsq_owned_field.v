`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Owns actual architectural queue fields. The enable/hold mux is local,
// so a shared write decision drives one input rather than every data bit.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.
module rv32_lsq_owned_field #(parameter integer WIDTH=32) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) payload_owner (
        .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
endmodule
