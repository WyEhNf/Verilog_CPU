`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Pure two-input bitwise OR; no priority, assumptions, state or clock.
module rv32_lsq_identity_pair_or #(parameter integer WIDTH=85) (
    input wire [WIDTH-1:0] left_i,right_i,
    output wire [WIDTH-1:0] value_o
);
    assign value_o=left_i | right_i;
endmodule
