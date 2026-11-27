`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Write ownership is distributed AFTER qualification. Each last driver
// controls at most 16 existing payload hold muxes, with no payload reset.
module rv32_frequency_word_bank #(parameter integer WIDTH=32) (
    input wire clk_i, write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    always @(posedge clk_i) if (write_i)
        data_o <= data_i;
`else
    localparam integer WORDS=(WIDTH+15)/16;
    wire [WORDS-1:0] write_words;
    rv32_frequency_control_tree #(.LEAVES(WORDS)) write_tree (
        .signal_i(write_i), .views_o(write_words));
    genvar word_id;
    generate for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
        localparam integer LOW=word_id*16;
        localparam integer BITS=WIDTH-LOW>=16 ? 16 : WIDTH-LOW;
        always @(posedge clk_i) if(write_words[word_id])
            data_o[LOW +: BITS]<=data_i[LOW +: BITS];
    end endgenerate
`endif
endmodule
