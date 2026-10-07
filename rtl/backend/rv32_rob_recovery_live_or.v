`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Pure single-bit OR. Keep binary reduction levels separate from GEN/slot
// predicates; all functional cells remain priced by the original course flow.
(* keep_hierarchy = 1 *)
module rv32_rob_recovery_live_or (
    input wire left_i,right_i,
    output wire value_o
);
    assign value_o=left_i | right_i;
endmodule
