`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32im_tag_compare #(
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer SLOT_WIDTH = `RV32IM_ROB_SLOT_WIDTH_DEFAULT,
    parameter integer GENERATION_WIDTH = `RV32IM_ROB_GENERATION_WIDTH
) (
    input  wire [TAG_WIDTH-1:0] lhs_i,
    input  wire [TAG_WIDTH-1:0] rhs_i,
    output wire                 lhs_live_o,
    output wire                 rhs_live_o,
    output wire                 match_o
);
    localparam integer KIND_LSB = 1;
    localparam integer SLOT_LSB = KIND_LSB + 2;
    localparam integer GENERATION_LSB = SLOT_LSB + SLOT_WIDTH;

    assign lhs_live_o = lhs_i[0];
    assign rhs_live_o = rhs_i[0];
    assign match_o = lhs_live_o && rhs_live_o &&
                     (lhs_i[KIND_LSB +: 2] == rhs_i[KIND_LSB +: 2]) &&
                     (lhs_i[SLOT_LSB +: SLOT_WIDTH] == rhs_i[SLOT_LSB +: SLOT_WIDTH]) &&
                     (lhs_i[GENERATION_LSB +: GENERATION_WIDTH] == rhs_i[GENERATION_LSB +: GENERATION_WIDTH]);
endmodule
