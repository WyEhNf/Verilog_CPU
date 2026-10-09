`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Exact relative LOAD formatting. The original admission predicate gates the
// formatted output, since formatting an all-zero word produces all zeros.
// Late sign bits drive one bounded tree input instead of 16/24 output gates.
// No state, new owner, size restriction or changed completion edge.
(* keep_hierarchy = 1 *)
module rv32_frequency_load_format (
    input wire [31:0] raw_i,
    input wire [1:0] size_i,
    input wire unsigned_i,valid_i,
    output wire [31:0] value_o
);
    wire byte_load=!size_i[1] && !size_i[0];
    wire upper_sign=!unsigned_i && !size_i[1] &&
        (size_i[0] ? raw_i[15] : raw_i[7]);
    wire [2:0] sign_views;
    wire [3:0] valid_views;
    wire byte_view;
    wire [1:0] word_views;
    rv32_frequency_control_tree #(.LEAVES(3)) sign_tree (
        .signal_i(upper_sign),.views_o(sign_views));
    rv32_frequency_control_tree #(.LEAVES(4)) valid_tree (
        .signal_i(valid_i),.views_o(valid_views));
    rv32_frequency_control_tree #(.LEAVES(1)) byte_tree (
        .signal_i(byte_load),.views_o(byte_view));
    // Both codes 2 and 3 retain the original default full-word behavior.
    rv32_frequency_control_tree #(.LEAVES(2)) word_tree (
        .signal_i(size_i[1]),.views_o(word_views));
    generate for(genvar bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_bit
        if(bit_id<8) begin:g_low
            assign value_o[bit_id]=valid_views[0] && raw_i[bit_id];
        end else if(bit_id<16) begin:g_byte_extend
            assign value_o[bit_id]=valid_views[1] &&
                (byte_view ? sign_views[0] : raw_i[bit_id]);
        end else begin:g_upper
            assign value_o[bit_id]=valid_views[bit_id/8] &&
                ((word_views[(bit_id-16)/8] && raw_i[bit_id]) || sign_views[(bit_id-8)/8]);
        end
    end endgenerate
endmodule
