`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Each bank owns an actual queue field and its local write selection.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.

// Functional payload state remains visible to pruning. Local event selection
// and word ownership bound the actual payload consumers of every control leaf.
module rv32_frontend_queue_payload_bank #(
    parameter integer WIDTH=32,FE_WIDTH=4,PTR_WIDTH=4,ROW_ID=0
) (
    input wire clk_i,reset_i,redirect_i,
    input wire [FE_WIDTH-1:0] write_valid_i,
    input wire [FE_WIDTH*PTR_WIDTH-1:0] write_slots_i,
    input wire [FE_WIDTH*WIDTH-1:0] write_data_i,
    output wire [WIDTH-1:0] data_o
);
    wire unused_reset_i_bits = &{1'b0, reset_i};

    wire unused_redirect_i_bits = &{1'b0, redirect_i};

    wire [FE_WIDTH-1:0] selected;
    wire write_qualified;
    wire [WIDTH-1:0] payload;
    genvar lane;
    generate for(lane=0;lane<FE_WIDTH;lane=lane+1) begin:g_lane
        assign selected[lane]=write_valid_i[lane] && 32'(write_slots_i[lane*PTR_WIDTH +: PTR_WIDTH])==ROW_ID;
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(WIDTH),.EVENTS(FE_WIDTH)) selector (
        .events_i(selected),.values_i(write_data_i),.write_o(write_qualified),.value_o(payload));
    // Occupancy owns reset/redirect invalidation. Each newly valid row has
    // a complete payload write, matching the existing frontend contract.
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) state_owner (
        .clk_i(clk_i),.write_i(write_qualified),.data_i(payload),.data_o(data_o));
endmodule
