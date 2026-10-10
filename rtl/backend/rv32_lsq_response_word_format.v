`timescale 1ns/1ps

// Prepare one complete row's relative WORD response before the late match
// priority. The caller retains the original full identity/wait predicate and
// default row0. All four masks and size codes0..3 keep their original meaning.
(* keep_hierarchy = 1 *)
module rv32_lsq_response_word_format (
    input wire [31:0] word_i,forward_i,
    input wire [3:0] mask_i,
    input wire [1:0] size_i,
    input wire unsigned_i,
    output wire [31:0] value_o
);
    wire [31:0] mask={{8{mask_i[3]}},{8{mask_i[2]}},{8{mask_i[1]}},{8{mask_i[0]}}};
    wire [31:0] merged=(forward_i & mask) | (word_i & ~mask);
    rv32_frequency_load_format formatter (
        .raw_i(merged),.size_i(size_i),.unsigned_i(unsigned_i),.valid_i(1'b1),.value_o(value_o));
endmodule
