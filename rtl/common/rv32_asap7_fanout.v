`timescale 1ns/1ps

// Functional simulation views of actual cells in the original ASAP7 RVT TT
// INVBUF library. Synthesis imports and prices the real Liberty definitions;
// these are not zero-area logic exclusions or FakeRAM interface declarations.
`ifdef SYNTHESIS
(* blackbox *)
`endif
module BUFx16f_ASAP7_75t_R(input wire A, output wire Y);
`ifndef SYNTHESIS
    assign Y = A;
`endif
endmodule

`ifdef SYNTHESIS
(* blackbox *)
`endif
module BUFx2_ASAP7_75t_R(input wire A, output wire Y);
`ifndef SYNTHESIS
    assign Y = A;
`endif
endmodule

module rv32_asap7_fanout #(
    parameter integer WIDTH = 1,
    parameter integer LEAVES = 16,
    parameter integer ENABLED = 0
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] replicas_o
);
    initial begin
        if (WIDTH < 1 || LEAVES < 1 || LEAVES > 32 ||
            (ENABLED != 0 && ENABLED != 1))
            $fatal(1, "invalid ASAP7 fanout-tree configuration");
    end
    genvar bit_id, leaf;
    generate
        if (ENABLED != 0) begin : g_physical
            wire [WIDTH-1:0] trunk;
            for (bit_id = 0; bit_id < WIDTH; bit_id = bit_id + 1) begin : g_root
                (* keep = 1 *) BUFx16f_ASAP7_75t_R buffer_root(
                    .A(signal_i[bit_id]), .Y(trunk[bit_id]));
                for (leaf = 0; leaf < LEAVES; leaf = leaf + 1) begin : g_leaf
                    (* keep = 1 *) BUFx2_ASAP7_75t_R buffer_leaf(
                        .A(trunk[bit_id]), .Y(replicas_o[leaf*WIDTH+bit_id]));
                end
            end
        end else begin : g_wires
            for (leaf = 0; leaf < LEAVES; leaf = leaf + 1) begin : g_leaf
                assign replicas_o[leaf*WIDTH +: WIDTH] = signal_i;
            end
        end
    endgenerate
endmodule

// Actual priced ASAP7 cells preserve separate electrical domains through ABC.
// No cycle is added. Each output must be wired to its own real consumers.
module rv32_frequency_control_tree #(
    parameter integer WIDTH=1, LEAVES=4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    wire [WIDTH-1:0] trunk;
    genvar bit_id, leaf;
    generate for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_bit
        (* keep=1 *) BUFx16f_ASAP7_75t_R root_cell (
            .A(signal_i[bit_id]),.Y(trunk[bit_id]));
        for(leaf=0;leaf<LEAVES;leaf=leaf+1) begin:g_leaf
            (* keep=1 *) BUFx16f_ASAP7_75t_R leaf_cell (
                .A(trunk[bit_id]),.Y(views_o[leaf*WIDTH+bit_id]));
        end
    end endgenerate
endmodule
