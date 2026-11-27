`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Contract: data_i is zero whenever write_i is zero, as produced by an
// event-select network. Thus D = data | (Q & !write) equals write ? data : Q.
// Retain the same unreset FF owner and edge, without a second data qualification.
// This implementation is also simulated directly in WORD_SIM builds.
module rv32_frequency_qualified_word_bank #(parameter integer WIDTH=32) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    localparam integer WORDS=(WIDTH+15)/16;
    wire [WORDS-1:0] write_views;
    rv32_frequency_control_tree #(.LEAVES(WORDS)) write_tree (
        .signal_i(write_i),.views_o(write_views));
    generate for(genvar word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
        localparam integer LOW=word_id*16;
        localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
        always @(posedge clk_i)
            data_o[LOW +: BITS] <= data_i[LOW +: BITS] |
                (data_o[LOW +: BITS] & {BITS{!write_views[word_id]}});
    end endgenerate
`ifdef VERILATOR
    always @(posedge clk_i) if(!write_i)
        assert(data_i=={WIDTH{1'b0}})
            else $fatal(1,"Qualified word owner received nonzero idle data");
`endif
endmodule
