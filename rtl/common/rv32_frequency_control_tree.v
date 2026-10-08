`timescale 1ns/1ps
`include "rv32im_defs.vh"

// One inversion produces a negative representation at the root. Negative
// internal nodes distribute it; individual leaf inverters restore the original
// positive signal. For LEAVES>1 this removes two serial inversions on every
// path and LEAVES+1 inverter instances per bit versus the old positive-node
// tree. Each internal driver still owns at most four child gate inputs.
// LEAVES=1 remains a two-inverter, positive-output leaf.
module rv32_frequency_control_tree #(
    parameter integer WIDTH=1,
    parameter integer LEAVES=4,
    parameter integer COMPACT_CONTROL=`RV32IM_COMPACT_CONTROL_DEFAULT
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign views_o = {LEAVES{signal_i}};
`else
    generate if(COMPACT_CONTROL!=0) begin:g_compact
        // This is a synthesis policy, with identical values and clock edges.
        // Removing forced keep cells also permits dead source cones to vanish.
        assign views_o={LEAVES{signal_i}};
    end else begin:g_distributed
    localparam integer CHILDREN=LEAVES>4?4:LEAVES;
    localparam integer BASE_COUNT=LEAVES/CHILDREN;
    localparam integer EXTRA_COUNT=LEAVES%CHILDREN;
    wire [WIDTH-1:0] negative;
    genvar bit_id,child;
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(signal_i[bit_id]),.signal_o(negative[bit_id]));
        end
        if(LEAVES==1) begin:g_leaf
            rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(1)) subtree (
                .negative_i(negative),.views_o(views_o));
        end else begin:g_branches
            for(child=0;child<CHILDREN;child=child+1) begin:g_child
                localparam integer COUNT=BASE_COUNT+(child<EXTRA_COUNT);
                localparam integer OFFSET=child*BASE_COUNT+
                    (child<EXTRA_COUNT?child:EXTRA_COUNT);
                rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(COUNT)) subtree (
                    .negative_i(negative),
                    .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
            end
        end
    end endgenerate
`endif
endmodule
