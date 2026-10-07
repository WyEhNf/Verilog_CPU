`timescale 1ns/1ps
`include "rv32im_defs.vh"

// A deterministic one-bundle pipeline. Its resource reservations guarantee
// complete D admission, so no RS/LSQ admission signal feeds back into R.
module rv32_reserved_dispatch_packet #(
    parameter integer LANES=4,PAYLOAD_WIDTH=160,TAG_WIDTH=17,ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer GW=TAG_WIDTH-SW-3
) (
    input wire clk_i,reset_i,flush_i,hold_i,recovery_i,
    input wire [SW-1:0] recovery_head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire [15:0] recovery_occupancy_i,
    input wire [ROB_ENTRIES-1:0] rob_valid_i,
    input wire [ROB_ENTRIES*GW-1:0] rob_generation_i,
    input wire [LANES-1:0] valid_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    input wire [LANES-1:0] saved_is_memory_i,
    output wire [LANES-1:0] valid_o,
    output wire [LANES*TAG_WIDTH-1:0] tag_o,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o,
    output reg [15:0] reserved_rs_o,reserved_lsq_o
);
    reg [LANES-1:0] valid_q;
    wire [TAG_WIDTH-1:0] tag_q [0:LANES-1];
    wire [ROB_ENTRIES*(GW+1)-1:0] live_rows;
    genvar live_row;
    generate for(live_row=0;live_row<ROB_ENTRIES;live_row=live_row+1) begin:g_live_row
        assign live_rows[live_row*(GW+1) +: GW+1]={rob_valid_i[live_row],rob_generation_i[live_row*GW +: GW]};
    end endgenerate
    wire [LANES-1:0] recovery_keep;
    wire normal=!reset_i && !flush_i && !hold_i && !recovery_i;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-recovery_head_i;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_lane
        wire [SW-1:0] slot=tag_q[lane][3 +: SW];
        wire [SW-1:0] age=slot-recovery_head_i;
        wire [GW:0] live;
        rv32_frequency_array_read #(.WIDTH(GW+1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) live_reader (
            .rows_i(live_rows),.index_i(slot),.value_o(live));
        wire generation_live=live[GW] && tag_q[lane][3+SW +: GW]==live[0 +: GW];
        assign recovery_keep[lane]=valid_q[lane] && tag_q[lane][0] &&
            generation_live && age<branch_age && age<recovery_occupancy_i;
        assign valid_o[lane]=normal && valid_q[lane];
        assign tag_o[lane*TAG_WIDTH +: TAG_WIDTH]=tag_q[lane];
        rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH)) tag_owner (
            .clk_i(clk_i),.write_i(normal && valid_i[lane]),
            .data_i(tag_i[lane*TAG_WIDTH +: TAG_WIDTH]),.data_o(tag_q[lane]));
        rv32_frequency_word_bank #(.WIDTH(PAYLOAD_WIDTH)) payload_owner (
            .clk_i(clk_i),.write_i(normal && valid_i[lane]),
            .data_i(data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]),
            .data_o(data_o[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]));
    end endgenerate
    integer count_lane;
    always @* begin
        reserved_rs_o=0;reserved_lsq_o=0;
        for(count_lane=0;count_lane<LANES;count_lane=count_lane+1) begin
            if(valid_q[count_lane]) reserved_rs_o=reserved_rs_o+1'b1;
            if(valid_q[count_lane] && saved_is_memory_i[count_lane])
                reserved_lsq_o=reserved_lsq_o+1'b1;
        end
    end
    always @(posedge clk_i) begin
        if(reset_i || flush_i)
            valid_q<=0;
        else
            if(recovery_i)
                valid_q<=recovery_keep;
            else
                if(!hold_i)
                    valid_q<=valid_i;
    end
endmodule
