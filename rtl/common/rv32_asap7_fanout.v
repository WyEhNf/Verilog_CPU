`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Preserve the legacy optional interface without importing external cells.
module rv32_asap7_fanout #(
    parameter integer WIDTH = 1,
    parameter integer LEAVES = 16,
    parameter integer ENABLED = 0
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] replicas_o
);
    genvar leaf;
    generate
        if (ENABLED != 0) begin:g_distribution
            rv32_frequency_control_tree #(.WIDTH(WIDTH), .LEAVES(LEAVES)) tree (
                .signal_i(signal_i), .views_o(replicas_o));
        end else begin:g_aliases
            for (leaf=0; leaf<LEAVES; leaf=leaf+1) begin:g_leaf
                assign replicas_o[leaf*WIDTH +: WIDTH] = signal_i;
            end
        end
    endgenerate
endmodule
