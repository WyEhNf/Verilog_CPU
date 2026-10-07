`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Merge the first two entries of each half concurrently. Every node owns
// only two short indices; payload routing is a separate bounded operation.
module rv32_frequency_first_two #(
    parameter integer ENTRIES=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES-1:0] candidates_i,
    output wire first_valid_o,second_valid_o,
    output wire [INDEX_WIDTH-1:0] first_index_o,second_index_o
);
    wire unused_LEAVES_bits = &{1'b0, (LEAVES != 0)};

// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    wire [ENTRIES-1:0] after_first=candidates_i & (candidates_i-ENTRIES'(1));
    wire [ENTRIES-1:0] first_onehot=candidates_i & (~candidates_i+ENTRIES'(1));
    wire [ENTRIES-1:0] second_onehot=after_first & (~after_first+ENTRIES'(1));
    assign first_valid_o=|candidates_i;
    assign second_valid_o=|after_first;
    assign first_index_o=INDEX_WIDTH'($clog2(first_onehot));
    assign second_index_o=INDEX_WIDTH'($clog2(second_onehot));
`else
    wire first_valid [1:2*LEAVES-1];
    wire second_valid [1:2*LEAVES-1];
    wire [INDEX_WIDTH-1:0] first_index [1:2*LEAVES-1];
    wire [INDEX_WIDTH-1:0] second_index [1:2*LEAVES-1];
    assign first_valid_o=first_valid[1];
    assign second_valid_o=second_valid[1];
    assign first_index_o=first_index[1];
    assign second_index_o=second_index[1];
    genvar slot,node;
    generate
        for(slot=0;slot<LEAVES;slot=slot+1) begin:g_leaf
            if(slot<ENTRIES) begin:g_present
                assign first_valid[LEAVES+slot]=candidates_i[slot];
                assign first_index[LEAVES+slot]=candidates_i[slot]?INDEX_WIDTH'(slot):{INDEX_WIDTH{1'b0}};
            end else begin:g_padding
                assign first_valid[LEAVES+slot]=1'b0;
                assign first_index[LEAVES+slot]=0;
            end
            assign second_valid[LEAVES+slot]=1'b0;
            assign second_index[LEAVES+slot]=0;
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_merge
            assign first_valid[node]=first_valid[2*node] || first_valid[2*node+1];
            assign second_valid[node]=second_valid[2*node] ||
                (first_valid[2*node] && first_valid[2*node+1]) || second_valid[2*node+1];
            assign first_index[node]=first_valid[2*node]?first_index[2*node]:first_index[2*node+1];
            assign second_index[node]=second_valid[2*node]?second_index[2*node]:
                (first_valid[2*node]?first_index[2*node+1]:second_index[2*node+1]);
        end
    endgenerate
`endif
endmodule
