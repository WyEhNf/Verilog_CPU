`timescale 1ns/1ps

// Exact (row-head) modulo ENTRIES < count, including every count encoding.
// Decode the two saved scalars independently; no head+count carry precedes
// a row comparison, and no queue-valid/occupancy invariant is assumed.
(* keep_hierarchy = 1 *)
module rv32_lsq_report_range_mask #(
    parameter integer ENTRIES=16,
    parameter integer SLOT_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer COUNT_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES+1),
    parameter integer DOMAINS=(ENTRIES+3)/4
) (
    input wire [SLOT_WIDTH-1:0] head_i,
    input wire [COUNT_WIDTH-1:0] count_i,
    output wire [ENTRIES-1:0] range_o
);
    wire [ENTRIES-1:0] head_decode,count_threshold;
    wire [DOMAINS*2*ENTRIES-1:0] predicate_views;
    for(genvar h=0;h<ENTRIES;h=h+1) begin:g_decode
        assign head_decode[h]=head_i==SLOT_WIDTH'(h);
        assign count_threshold[h]=32'(count_i)>h;
    end
    rv32_frequency_control_tree #(.WIDTH(2*ENTRIES),.LEAVES(DOMAINS)) predicate_tree (
        .signal_i({count_threshold,head_decode}),.views_o(predicate_views));
    for(genvar row=0;row<ENTRIES;row=row+1) begin:g_row
        wire terms [1:2*ENTRIES-1];
        for(genvar h=0;h<ENTRIES;h=h+1) begin:g_head
            localparam integer AGE=(row-h)&(ENTRIES-1);
            assign terms[ENTRIES+h]=predicate_views[(row/4)*2*ENTRIES+h] &&
                predicate_views[(row/4)*2*ENTRIES+ENTRIES+AGE];
        end
        for(genvar node=1;node<ENTRIES;node=node+1) begin:g_merge
            rv32_lsq_identity_pair_or #(.WIDTH(1)) pair (
                .left_i(terms[2*node]),.right_i(terms[2*node+1]),.value_o(terms[node]));
        end
        assign range_o[row]=terms[1];
    end
    initial if(ENTRIES<2 || ENTRIES>32 || (ENTRIES&(ENTRIES-1))!=0)
        $fatal(1,"Report range predecode requires power-of-two entries 2..32");
endmodule
