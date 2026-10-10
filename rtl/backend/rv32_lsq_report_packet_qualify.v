`timescale 1ns/1ps

// Range is a prefix of circular age. The caller has already selected the
// complete oldest saved packet and the independently matched full held tag.
// Qualify these packets only after their wide reads, retaining original zeros
// when no covered saved row exists and the original invalid-slot head default.
(* keep_hierarchy = 1 *)
module rv32_lsq_report_packet_qualify #(
    parameter integer WIDTH=80,
    parameter integer SLOT_WIDTH=4,
    parameter integer WORDS=(WIDTH+15)/16
) (
    input wire [WIDTH-1:0] normal_i,held_i,
    input wire covered_i,held_live_i,fast_head_i,
    input wire [SLOT_WIDTH-1:0] normal_slot_i,held_slot_i,head_i,
    output wire [WIDTH-1:0] packet_o,
    output wire valid_o,
    output wire [SLOT_WIDTH-1:0] slot_o
);
    wire [WORDS*2-1:0] views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(WORDS)) controls (
        .signal_i({held_live_i,covered_i}),.views_o(views));
    for(genvar word_index=0;word_index<WORDS;word_index=word_index+1) begin:g_word
        localparam integer LOW=word_index*16;
        localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
        assign packet_o[LOW +: BITS]=views[word_index*2+1] ? held_i[LOW +: BITS] :
            ({BITS{views[word_index*2]}} & normal_i[LOW +: BITS]);
    end
    assign valid_o=covered_i || fast_head_i;
    assign slot_o=!valid_o ? head_i : held_live_i ? held_slot_i :
        fast_head_i ? head_i : normal_slot_i;
    initial if(WIDTH<1 || SLOT_WIDTH<1 || WORDS!=(WIDTH+15)/16)
        $fatal(1,"Complete report packet qualification requires complete packet geometry");
endmodule
