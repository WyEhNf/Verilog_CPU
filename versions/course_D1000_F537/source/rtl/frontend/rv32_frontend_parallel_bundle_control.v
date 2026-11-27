`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Same accepted prefix as bundle_count, without count encoding/decoding on
// next-PC or response-capacity paths. No new state or acceptance boundary.
module rv32_frontend_parallel_bundle_control #(
    parameter integer FE_WIDTH=4,FQ_DEPTH=16,LEGACY_SENTINEL_HALT=0,
    parameter integer DIRECT_WORD_BOUNDS=0
) (
    input wire [31:0] base_pc_i,
    input wire [FE_WIDTH*32-1:0] words_i,targets_i,
    input wire [FE_WIDTH-1:0] taken_i,
    input wire signed [31:0] queue_count_i,
    input wire response_error_i,
    output wire queue_space_o,
    output wire [31:0] next_pc_o
);
    wire [FE_WIDTH-1:0] stops,lane_live,capacity_violation;
    wire [2*FE_WIDTH:0] events;
    wire [(2*FE_WIDTH+1)*32-1:0] values;
    genvar lane;
    generate for(lane=0;lane<FE_WIDTH;lane=lane+1) begin:g_lane
        wire [2:0] word_number={1'b0,base_pc_i[3:2]}+3'(lane);
        wire unused_word_number_bits = &{1'b0, word_number};

        wire word_in_line,word_is_last;
        if(DIRECT_WORD_BOUNDS!=0) begin:g_direct_bound
            localparam [1:0] LAST_START=3-lane;
            if (lane == 0) begin : g_first_word
                assign word_in_line=1'b1;
            end else begin : g_later_word
                assign word_in_line=base_pc_i[3:2]<=LAST_START;
            end
            assign word_is_last=base_pc_i[3:2]==LAST_START;
        end else begin:g_original_bound
            assign word_in_line=word_number<3'd4;
            assign word_is_last=word_number==3'd3;
        end
        wire prior_prefix_live;
        assign stops[lane]=taken_i[lane] || ((LEGACY_SENTINEL_HALT!=0) &&
            words_i[lane*32 +: 32]==32'h0ff00513);
        if(lane==0) begin:g_first
            assign prior_prefix_live=1'b1;
        end else begin:g_later
            assign prior_prefix_live=!(|stops[lane-1:0]);
        end
        assign lane_live[lane]=!response_error_i && prior_prefix_live && word_in_line;
        wire ends_bundle=lane_live[lane] &&
            (stops[lane] || (lane==FE_WIDTH-1) || word_is_last);
        // An error has no bundle. Otherwise exactly one live lane ends it.
        // Target/sequential events are disjoint and directly select data.
        assign events[2*lane]=ends_bundle && taken_i[lane];
        assign events[2*lane+1]=ends_bundle && !taken_i[lane];
        assign values[2*lane*32 +: 32]=targets_i[lane*32 +: 32];
        assign values[(2*lane+1)*32 +: 32]=base_pc_i+((lane+1)*32'd4);
        // Every live lane must fit. Parallel constant comparisons avoid the
        // bundle_count + occupancy adder, and preserve no dequeue credit.
        assign capacity_violation[lane]=lane_live[lane] &&
            queue_count_i>(FQ_DEPTH-(lane+1));
    end endgenerate
    assign events[2*FE_WIDTH]=response_error_i;
    assign values[2*FE_WIDTH*32 +: 32]=base_pc_i+32'd4;
    assign queue_space_o=(queue_count_i<=FQ_DEPTH) && !(|capacity_violation);
wire  unused_next_pc_selector_write_o;
rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2*FE_WIDTH+1),.PRIORITY(0)) next_pc_selector (
        .events_i(events),.values_i(values),.write_o(unused_next_pc_selector_write_o),.value_o(next_pc_o));
endmodule
