`timescale 1ns/1ps
`include "rv32im_defs.vh"

// A complete functional RTL module. ABC maps this inversion to real library
// logic. The hierarchy boundary prevents cancellation with the next inversion;
// keep on each instance prevents identical sibling instances from merging.
// No external cell declaration, blackbox, whitebox, or area override is used.
(* keep_hierarchy = 1 *)
module rv32_frequency_inversion(input wire signal_i, output wire signal_o);
    assign signal_o = ~signal_i;
endmodule
