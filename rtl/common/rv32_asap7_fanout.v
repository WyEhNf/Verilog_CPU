`timescale 1ns/1ps

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

// Write ownership is distributed AFTER qualification. Each last driver
// controls at most 32 existing payload hold muxes, with no payload reset.
module rv32_frequency_word_bank #(parameter integer WIDTH=32) (
    input wire clk_i, write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    localparam integer WORDS=(WIDTH+31)/32;
    wire [WORDS-1:0] write_words;
    rv32_frequency_control_tree #(.LEAVES(WORDS)) write_tree (
        .signal_i(write_i), .views_o(write_words));
    genvar word_id;
    generate for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
        localparam integer LOW=word_id*32;
        localparam integer BITS=WIDTH-LOW>=32 ? 32 : WIDTH-LOW;
        always @(posedge clk_i) if(write_words[word_id])
            data_o[LOW +: BITS]<=data_i[LOW +: BITS];
    end endgenerate
endmodule
