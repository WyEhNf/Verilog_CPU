`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Private drivers for SRAM macro input pins.
//
// A FakeRAM macro pin presents 5 fF, roughly nine standard gate inputs. The
// course mapper sizes a net that feeds macros as ONE 5 fF output, however
// many macro pins share it, so a command shared by sixteen macros is mapped
// as if it drove one. These two modules give every macro pin its own real
// library inverter, whose single 5 fF load is exactly what the mapper
// assumes, and leave the feeding logic with ordinary gate loads.
//
// The inverter is ordinary synthesizable RTL. Its hierarchy boundary is the
// only preserved boundary in the design: without it the two inversions of a
// tree would cancel and the macro pins would share one driver again.
(* keep_hierarchy = 1 *)
module rv32_sram_pin_inverter(input wire signal_i, output wire signal_o);
    assign signal_o = ~signal_i;
endmodule

// views_o is LEAVES identical copies of signal_i; no state, no new edge.
// ROOTED=0: the complement comes from ordinary logic (one net, LEAVES gate
//           loads). Use it when LEAVES is small.
// ROOTED=1: one preserved root inverter per GROUP leaves, so the feeding
//           logic sees one gate load per group.
module rv32_sram_pin_tree #(
    parameter integer WIDTH=1,
    parameter integer LEAVES=1,
    parameter integer ROOTED=0,
    parameter integer GROUP=8
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
`ifdef CPU2026_WORD_SIM
    assign views_o = {LEAVES{signal_i}};
`else
    localparam integer ROOTS=(ROOTED!=0)?((LEAVES+GROUP-1)/GROUP):1;
    wire [WIDTH*ROOTS-1:0] negative;
    genvar bit_id,root_id,leaf_id;
    generate
        for(root_id=0;root_id<ROOTS;root_id=root_id+1) begin:g_root
            if(ROOTED!=0) begin:g_preserved
                for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_bit
                    rv32_sram_pin_inverter root (
                        .signal_i(signal_i[bit_id]),
                        .signal_o(negative[root_id*WIDTH+bit_id]));
                end
            end else begin:g_logic
                assign negative[root_id*WIDTH +: WIDTH]=~signal_i;
            end
        end
        for(leaf_id=0;leaf_id<LEAVES;leaf_id=leaf_id+1) begin:g_leaf
            localparam integer ROOT=(ROOTED!=0)?(leaf_id/GROUP):0;
            for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_bit
                rv32_sram_pin_inverter leaf (
                    .signal_i(negative[ROOT*WIDTH+bit_id]),
                    .signal_o(views_o[leaf_id*WIDTH+bit_id]));
            end
        end
    endgenerate
`endif
endmodule
