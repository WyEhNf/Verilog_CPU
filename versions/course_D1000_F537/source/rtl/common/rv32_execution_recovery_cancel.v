`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Execution ownership uses the registered recovery snapshot, not a late
// dynamic ROB read. Packet layout: {apply,occupancy,head,branch_relative_age}.
// Default-disabled instances retain old standalone interfaces and semantics.
module rv32_execution_recovery_cancel #(
    parameter integer TAG_WIDTH=17, ROB_ENTRIES=64, ENABLED=0, KILL_BRANCH=0,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer CW=$clog2(ROB_ENTRIES+1),
    parameter integer WIDTH=1+2*SW+CW
) (
    input wire [WIDTH-1:0] packet_i,
    input wire active_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire cancel_o
);
    wire unused_tag_i_bits = &{1'b0, tag_i};

    generate if(ENABLED!=0) begin:g_enabled
        wire apply;
        wire [CW-1:0] occupancy;
        wire [SW-1:0] head,branch_age;
        wire [SW-1:0] age=tag_i[3 +: SW]-head;
        assign {apply,occupancy,head,branch_age}=packet_i;
        assign cancel_o=active_i && apply && (!tag_i[0] || 6'(age)>=occupancy ||
            ((KILL_BRANCH != 0) ? age>=branch_age : age>branch_age));
    end else begin:g_disabled
        assign cancel_o=1'b0;
    end endgenerate
endmodule
