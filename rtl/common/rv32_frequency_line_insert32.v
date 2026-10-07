`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Insert an access-relative word at any byte offset, preserving the original
// 128-bit left shift and overflow truncation. Increasing intermediate widths
// retain all reachable bits; each amount leaf owns <=16 actual mux bits.
module rv32_frequency_line_insert32 (
    input wire [31:0] value_i,
    input wire [3:0] offset_i,
    output wire [127:0] line_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    // Shift only the two possibly nonzero native words, then place them in
    // the line. The high word is discarded when the offset lies in word 3.
    wire [63:0] byte_words = {32'b0,value_i} << {offset_i[1:0],3'b0};
    genvar native_word;
    generate for(native_word=0;native_word<4;native_word=native_word+1) begin:g_native_word
        if(native_word==0) begin:g_first
            assign line_o[native_word*32 +: 32] =
                (offset_i[3:2]==2'(native_word)) ? byte_words[31:0] : 32'b0;
        end else begin:g_later
            assign line_o[native_word*32 +: 32] =
                (offset_i[3:2]==2'(native_word)) ? byte_words[31:0] :
                ((offset_i[3:2]==2'(native_word-1)) ? byte_words[63:32] : 32'b0);
        end
    end endgenerate
`else
    wire [39:0] shift8;
    wire [55:0] shift16;
    wire [87:0] shift32;
    wire [127:0] original [0:3];
    wire [127:0] shifted [0:3];
    wire [2:0] amount8;
    wire [3:0] amount16;
    wire [5:0] amount32;
    wire [7:0] amount64;
    assign original[0]={96'b0,value_i};
    assign shifted[0]={88'b0,value_i,8'b0};
    assign original[1]={88'b0,shift8};
    assign shifted[1]={72'b0,shift8,16'b0};
    assign original[2]={72'b0,shift16};
    assign shifted[2]={40'b0,shift16,32'b0};
    assign original[3]={40'b0,shift32};
    assign shifted[3]={shift32[63:0],64'b0};
    rv32_frequency_control_tree #(.LEAVES(3)) amount8_tree (
        .signal_i(offset_i[0]),.views_o(amount8));
    rv32_frequency_control_tree #(.LEAVES(4)) amount16_tree (
        .signal_i(offset_i[1]),.views_o(amount16));
    rv32_frequency_control_tree #(.LEAVES(6)) amount32_tree (
        .signal_i(offset_i[2]),.views_o(amount32));
    rv32_frequency_control_tree #(.LEAVES(8)) amount64_tree (
        .signal_i(offset_i[3]),.views_o(amount64));
    genvar bit_id;
    generate
        for(bit_id=0;bit_id<40;bit_id=bit_id+1) begin:g_shift8
            assign shift8[bit_id]=amount8[bit_id/16]?shifted[0][bit_id]:original[0][bit_id];
        end
        for(bit_id=0;bit_id<56;bit_id=bit_id+1) begin:g_shift16
            assign shift16[bit_id]=amount16[bit_id/16]?shifted[1][bit_id]:original[1][bit_id];
        end
        for(bit_id=0;bit_id<88;bit_id=bit_id+1) begin:g_shift32
            assign shift32[bit_id]=amount32[bit_id/16]?shifted[2][bit_id]:original[2][bit_id];
        end
        for(bit_id=0;bit_id<128;bit_id=bit_id+1) begin:g_shift64
            assign line_o[bit_id]=amount64[bit_id/16]?shifted[3][bit_id]:original[3][bit_id];
        end
    endgenerate
`endif
endmodule
