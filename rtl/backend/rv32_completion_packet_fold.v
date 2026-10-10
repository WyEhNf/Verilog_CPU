`timescale 1ns/1ps

// Fold exact candidate choice into the original direct source grant. Keep the
// same full payload, zero when unselected, without another edge or queue port.
(* keep_hierarchy = 1 *)
module rv32_completion_packet_fold #(
    parameter integer WIDTH=80,
    parameter integer WORDS=(WIDTH+15)/16
) (
    input wire [WIDTH-1:0] head_i,saved_i,
    input wire head_choice_i,grant_i,
    output wire [WIDTH-1:0] packet_o
);
    wire [WORDS*2-1:0] views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(WORDS)) choices (
        .signal_i({grant_i && head_choice_i,grant_i && !head_choice_i}),.views_o(views));
    for(genvar word_index=0;word_index<WORDS;word_index=word_index+1) begin:g_word
        localparam integer LOW=word_index*16;
        localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
        assign packet_o[LOW +: BITS]=
            ({BITS{views[word_index*2+1]}} & head_i[LOW +: BITS]) |
            ({BITS{views[word_index*2]}} & saved_i[LOW +: BITS]);
    end
    initial if(WIDTH<1 || WORDS!=(WIDTH+15)/16) $fatal(1,"Complete candidate payload geometry required");
endmodule
