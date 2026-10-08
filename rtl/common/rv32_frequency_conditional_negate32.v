`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Exactly negate ? (~value + increment) : value, modulo 2^32.
// For increment=1 the lowest set bit and all lower bits stay unchanged;
// every higher bit flips. For increment=0 every bit flips. A balanced
// prefix-OR replaces the conditional incrementer and subsequent word mux.
module rv32_frequency_conditional_negate32 (
    input wire [31:0] value_i,
    input wire negate_i,increment_i,
    output wire [31:0] value_o
);
    wire [31:0] any0=value_i;
    wire [31:0] any1=any0 | (any0 << 1);
    wire [31:0] any2=any1 | (any1 << 2);
    wire [31:0] any4=any2 | (any2 << 4);
    wire [31:0] any8=any4 | (any4 << 8);
    wire [31:0] any16=any8 | (any8 << 16);
    wire [3:0] controls;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(2)) control_tree (
        .signal_i({negate_i,increment_i}),.views_o(controls));
    genvar bit_id;
    generate for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_bit
        localparam integer LEAF=bit_id/16;
        wire flip;
        if(bit_id==0) begin:g_low
            assign flip=controls[LEAF*2+1] && !controls[LEAF*2];
        end else begin:g_high
            assign flip=controls[LEAF*2+1] && (!controls[LEAF*2] || any16[bit_id-1]);
        end
        assign value_o[bit_id]=value_i[bit_id] ^ flip;
    end endgenerate
endmodule
