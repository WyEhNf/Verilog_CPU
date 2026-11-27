`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Narrow table read: each row hit directly drives at most four data masks.
// Retain the original four-row index distribution and balanced OR reduction;
// wide payload reads still use the original bounded word/select trees.
module rv32_frequency_narrow_array_read #(
    parameter integer WIDTH=3,ENTRIES=64,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [INDEX_WIDTH-1:0] index_i,
    output wire [WIDTH-1:0] value_o
);
    wire unused_DOMAINS_bits = &{1'b0, (DOMAINS != 0)};

    wire unused_LEAVES_bits = &{1'b0, (LEAVES != 0)};

// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign value_o = (32'(index_i) < ENTRIES) ? rows_i[index_i*WIDTH +: WIDTH] : {WIDTH{1'b0}};
    initial if (WIDTH < 1 || WIDTH > 4) $fatal(1,"Narrow array read width must be1..4");
`else
    wire [DOMAINS*INDEX_WIDTH-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(INDEX_WIDTH),.LEAVES(DOMAINS)) query_tree (
        .signal_i(index_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES) begin:g_present
                wire hit=query_views[(row/4)*INDEX_WIDTH +: INDEX_WIDTH]==row;
                assign reads[LEAVES+row]={WIDTH{hit}} & rows_i[row*WIDTH +: WIDTH];
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
    initial begin
        if(WIDTH<1 || WIDTH>4)
            $fatal(1,"Narrow array read width must be1..4");
    end
`endif
endmodule
