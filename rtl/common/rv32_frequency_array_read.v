`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Four-row query domains, sixteen-bit selection leaves and a binary OR tree.
// Payload remains unqualified here: its transaction validity is checked by
// the consumer at the same point as the former dynamic array read.
module rv32_frequency_array_read #(
    parameter integer WIDTH=32,ENTRIES=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer WORDS=(WIDTH+15)/16,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [INDEX_WIDTH-1:0] index_i,
    output wire [WIDTH-1:0] value_o
);
    wire unused_DOMAINS_bits = &{1'b0, (DOMAINS != 0)};

    wire unused_WORDS_bits = &{1'b0, (WORDS != 0)};

    wire unused_LEAVES_bits = &{1'b0, (LEAVES != 0)};

// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign value_o=(32'(index_i)<ENTRIES)?rows_i[(32'(index_i)*WIDTH) +: WIDTH]:{WIDTH{1'b0}};
`else
    wire [DOMAINS*INDEX_WIDTH-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(INDEX_WIDTH),.LEAVES(DOMAINS)) query_tree (
        .signal_i(index_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,word,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES) begin:g_present
                wire [WORDS-1:0] selects;
                wire hit=query_views[(row/4)*INDEX_WIDTH +: INDEX_WIDTH]==row;
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
