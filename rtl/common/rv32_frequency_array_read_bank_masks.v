`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Read a packed row array using two already-decoded index banks. A selected
// input bit drives bounded row groups; no encoded-index decode follows the
// late report selection. The caller retains the full normal generation check.
(* keep_hierarchy = 1 *)
module rv32_frequency_array_read_bank_masks #(
    parameter integer WIDTH=9,ENTRIES=64,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LOW_BITS=(INDEX_WIDTH+1)/2,
    parameter integer HIGH_BITS=INDEX_WIDTH-LOW_BITS,
    parameter integer LOW_ROWS=1<<LOW_BITS,HIGH_ROWS=1<<HIGH_BITS,
    parameter integer WORDS=(WIDTH+15)/16,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [LOW_ROWS+HIGH_ROWS-1:0] query_i,
    output wire [WIDTH-1:0] value_o
);
    wire unused_WORDS_bits = &{1'b0, (WORDS != 0)};

    wire unused_LEAVES_bits = &{1'b0, (LEAVES != 0)};

// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    reg [WIDTH-1:0] selected;
    integer row;
    always @* begin
        selected = 0;
        for (row=0; row<ENTRIES; row=row+1)
            if (row < (1<<INDEX_WIDTH) && query_i[row%LOW_ROWS] && query_i[LOW_ROWS+row/LOW_ROWS])
                selected = selected | rows_i[row*WIDTH +: WIDTH];
    end
    assign value_o = selected;
`else
    wire [2*(LOW_ROWS+HIGH_ROWS)-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(LOW_ROWS+HIGH_ROWS),.LEAVES(2)) query_tree (
        .signal_i(query_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,word,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES && row<(1<<INDEX_WIDTH)) begin:g_present
                localparam integer DOMAIN=(row*2)/ENTRIES;
                wire [WORDS-1:0] selects;
                wire hit=query_views[DOMAIN*(LOW_ROWS+HIGH_ROWS)+(row%LOW_ROWS)] &&
                    query_views[DOMAIN*(LOW_ROWS+HIGH_ROWS)+LOW_ROWS+(row/LOW_ROWS)];
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(hit),.views_o(selects));
                for(word=0;word<WORDS;word=word+1) begin:g_word
                    localparam integer LOW=word*16;
                    localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
                    assign reads[LEAVES+row][LOW +: BITS]=
                        {BITS{selects[word]}} & rows_i[row*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
`endif
endmodule
