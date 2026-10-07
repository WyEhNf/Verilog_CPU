`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Internal distribution receives a NEGATIVE representation and returns
// positive leaves. Every leaf has its own inverter; internal nodes retain a
// negative representation using two real inverters and at most four children.
// Thus no alias leaf can expose a parent directly to its payload consumer load.
module rv32_frequency_negative_subtree #(
    parameter integer WIDTH=1,LEAVES=1
) (
    input wire [WIDTH-1:0] negative_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign views_o = {LEAVES{~negative_i}};
`else
    localparam integer CHILDREN=LEAVES>4?4:LEAVES;
    localparam integer BASE_COUNT=LEAVES/CHILDREN;
    localparam integer EXTRA_COUNT=LEAVES%CHILDREN;
    genvar bit_id,child;
    generate if(LEAVES==1) begin:g_leaf
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion restore_positive (
                .signal_i(negative_i[bit_id]),.signal_o(views_o[bit_id]));
        end
    end else begin:g_internal
        wire [WIDTH-1:0] positive,distributed_negative;
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(negative_i[bit_id]),.signal_o(positive[bit_id]));
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_output (
                .signal_i(positive[bit_id]),.signal_o(distributed_negative[bit_id]));
        end
        for(child=0;child<CHILDREN;child=child+1) begin:g_child
            localparam integer COUNT=BASE_COUNT+(child<EXTRA_COUNT);
            localparam integer OFFSET=child*BASE_COUNT+
                (child<EXTRA_COUNT?child:EXTRA_COUNT);
            rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(COUNT)) subtree (
                .negative_i(distributed_negative),
                .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
        end
    end endgenerate
`endif
endmodule
