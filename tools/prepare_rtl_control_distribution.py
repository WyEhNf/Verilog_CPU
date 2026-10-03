"""Prepare complete RTL control distribution; no EDA or simulation is invoked.

The course imports Liberty after prepared RTL. Consequently defining physical
ASAP7 cell names either conflicts with read_liberty or fails the RAM validator.
These ordinary modules use distinct RTL names and are mapped by course ABC.
"""
from prepare_staged_frequency_candidate import prepare, ROOT


RTL = r'''`timescale 1ns/1ps

// A complete functional RTL module. ABC maps this inversion to real library
// logic. The hierarchy boundary prevents cancellation with the next inversion;
// keep on each instance prevents identical sibling instances from merging.
// No external cell declaration, blackbox, whitebox, or area override is used.
(* keep_hierarchy = 1 *)
module rv32_frequency_inversion(input wire signal_i, output wire signal_o);
    assign signal_o = ~signal_i;
endmodule

// Four-way recursive distribution with a pair of real inversions at each
// node. Every internal driver has at most four child consumers. Leaf outputs
// must be attached to bounded groups of actual consumers by the caller.
// Combinational only: the observable signal and cycle remain unchanged.
module rv32_frequency_control_tree #(
    parameter integer WIDTH = 1,
    parameter integer LEAVES = 4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    localparam integer CHILDREN = LEAVES > 4 ? 4 : LEAVES;
    localparam integer BASE_COUNT = LEAVES / CHILDREN;
    localparam integer EXTRA_COUNT = LEAVES % CHILDREN;
    wire [WIDTH-1:0] inverted, distributed;
    genvar bit_id, child;
    generate
        for (bit_id=0; bit_id<WIDTH; bit_id=bit_id+1) begin:g_driver
            (* keep = 1, keep_hierarchy = 1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(signal_i[bit_id]), .signal_o(inverted[bit_id]));
            (* keep = 1, keep_hierarchy = 1 *)
            rv32_frequency_inversion invert_output (
                .signal_i(inverted[bit_id]), .signal_o(distributed[bit_id]));
        end
        if (LEAVES == 1) begin:g_leaf
            assign views_o = distributed;
        end else begin:g_branches
            for (child=0; child<CHILDREN; child=child+1) begin:g_child
                localparam integer COUNT = BASE_COUNT + (child < EXTRA_COUNT);
                localparam integer OFFSET = child*BASE_COUNT +
                    (child < EXTRA_COUNT ? child : EXTRA_COUNT);
                rv32_frequency_control_tree #(.WIDTH(WIDTH), .LEAVES(COUNT)) subtree (
                    .signal_i(distributed),
                    .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
            end
        end
    endgenerate
endmodule

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
'''


if __name__ == '__main__':
    prepare('S_functional_rtl_control_distribution', ROOT/'Q_icache_response_data_owner',
            {'rtl/common/rv32_asap7_fanout.v': lambda _: RTL},
            'Source-only Q follow-up: replace every external BUF declaration with complete ordinary RTL inversion modules, kept functional hierarchy and bounded four-way recursive internal distribution; no course/tool/library changes, no mapping yet')
