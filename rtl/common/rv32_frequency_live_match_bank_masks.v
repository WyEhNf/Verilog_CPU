`timescale 1ns/1ps

// Compare every original full generation before the late decoded slot query.
// The caller supplies a single identity's two one-hot query banks. There is
// no saved liveness certificate and no generation/range shortening.
(* keep_hierarchy = 1 *)
module rv32_frequency_live_match_bank_masks #(
    parameter integer ENTRIES=32,GENERATION_WIDTH=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LOW_BITS=(INDEX_WIDTH+1)/2,HIGH_BITS=INDEX_WIDTH-LOW_BITS,
    parameter integer LOW_ROWS=1<<LOW_BITS,HIGH_ROWS=1<<HIGH_BITS,
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*(GENERATION_WIDTH+1)-1:0] rows_i,
    input wire [GENERATION_WIDTH-1:0] generation_i,
    input wire [LOW_ROWS+HIGH_ROWS-1:0] query_i,
    output wire match_o
);
    wire [DOMAINS*GENERATION_WIDTH-1:0] generation_views;
    wire [DOMAINS*(LOW_ROWS+HIGH_ROWS)-1:0] query_views;
    wire match_tree [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(GENERATION_WIDTH),.LEAVES(DOMAINS)) generation_tree (
        .signal_i(generation_i),.views_o(generation_views));
    rv32_frequency_control_tree #(.WIDTH(LOW_ROWS+HIGH_ROWS),.LEAVES(DOMAINS)) query_tree (
        .signal_i(query_i),.views_o(query_views));
    for(genvar row=0;row<LEAVES;row=row+1) begin:g_row
        if(row<ENTRIES && row<(1<<INDEX_WIDTH)) begin:g_present
            wire same_generation=rows_i[row*(GENERATION_WIDTH+1) +: GENERATION_WIDTH]==
                generation_views[(row/4)*GENERATION_WIDTH +: GENERATION_WIDTH];
            assign match_tree[LEAVES+row]=same_generation &&
                rows_i[row*(GENERATION_WIDTH+1)+GENERATION_WIDTH] &&
                query_views[(row/4)*(LOW_ROWS+HIGH_ROWS)+row%LOW_ROWS] &&
                query_views[(row/4)*(LOW_ROWS+HIGH_ROWS)+LOW_ROWS+row/LOW_ROWS];
        end else begin:g_padding
            assign match_tree[LEAVES+row]=0;
        end
    end
    for(genvar node=1;node<LEAVES;node=node+1) begin:g_merge
        rv32_lsq_identity_pair_or #(.WIDTH(1)) pair (
            .left_i(match_tree[2*node]),.right_i(match_tree[2*node+1]),.value_o(match_tree[node]));
    end
    assign match_o=match_tree[1];
endmodule
