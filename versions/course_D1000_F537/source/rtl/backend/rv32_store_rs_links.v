`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Each live link names a still-owned RS row, not a completed/queued payload.
// RS release invalidates the link on the same edge that frees that RS row.
// Every LSQ allocation overwrites the row link, including non-store rows.
module rv32_store_rs_links #(
    parameter integer BE_WIDTH=4, LSQ_ENTRIES=16, RS_ENTRIES=12,
    parameter integer TAG_WIDTH=17,
    parameter integer LSQ_SW=(LSQ_ENTRIES<=1)?1:$clog2(LSQ_ENTRIES),
    parameter integer RS_SW=(RS_ENTRIES<=1)?1:$clog2(RS_ENTRIES)
) (
    input wire clk_i,reset_i,flush_i,recovery_i,
    input wire [BE_WIDTH-1:0] lsq_alloc_fire_i,rs_alloc_fire_i,alloc_is_store_i,
    input wire [BE_WIDTH*TAG_WIDTH-1:0] alloc_lsq_tag_i,
    input wire [BE_WIDTH*RS_SW-1:0] alloc_rs_slot_i,
    input wire [RS_ENTRIES-1:0] rs_release_i,
    output wire [LSQ_ENTRIES-1:0] link_valid_o,
    output wire [LSQ_ENTRIES*RS_SW-1:0] link_rs_slot_o
);
    wire unused_alloc_lsq_tag_i_bits = &{1'b0, alloc_lsq_tag_i};

    localparam integer LANE_WIDTH=LSQ_SW+RS_SW+2;
    localparam integer DOMAINS=(LSQ_ENTRIES+3)/4;
    wire [BE_WIDTH*LANE_WIDTH-1:0] allocation_packet;
    wire [DOMAINS*BE_WIDTH*LANE_WIDTH-1:0] allocation_views;
    wire [DOMAINS*RS_ENTRIES-1:0] release_views;
    // Each control/field leaf reaches at most four short link owners.
    wire [DOMAINS-1:0] reset_views,flush_views,recovery_views;
    genvar lane,row,entry;
    generate for(lane=0;lane<BE_WIDTH;lane=lane+1) begin:g_allocation_packet
        assign allocation_packet[lane*LANE_WIDTH +: LANE_WIDTH]={
            lsq_alloc_fire_i[lane],
            alloc_is_store_i[lane] && rs_alloc_fire_i[lane],
            alloc_lsq_tag_i[lane*TAG_WIDTH+3 +: LSQ_SW],
            alloc_rs_slot_i[lane*RS_SW +: RS_SW]};
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*LANE_WIDTH),.LEAVES(DOMAINS)) allocation_tree (
        .signal_i(allocation_packet),.views_o(allocation_views));
    rv32_frequency_control_tree #(.WIDTH(RS_ENTRIES),.LEAVES(DOMAINS)) release_tree (
        .signal_i(rs_release_i),.views_o(release_views));
    rv32_frequency_control_tree #(.LEAVES(DOMAINS)) reset_tree (
        .signal_i(reset_i),.views_o(reset_views));
    rv32_frequency_control_tree #(.LEAVES(DOMAINS)) flush_tree (
        .signal_i(flush_i),.views_o(flush_views));
    rv32_frequency_control_tree #(.LEAVES(DOMAINS)) recovery_tree (
        .signal_i(recovery_i),.views_o(recovery_views));
    generate for(row=0;row<LSQ_ENTRIES;row=row+1) begin:g_link
        reg valid;
        reg [RS_SW-1:0] rs_slot;
        wire [BE_WIDTH-1:0] allocation_events;
        wire [BE_WIDTH*(RS_SW+1)-1:0] allocation_values;
        wire allocation_write,new_valid;
        wire [RS_SW-1:0] new_rs_slot;
        wire [RS_ENTRIES-1:0] selected_releases;
        for(lane=0;lane<BE_WIDTH;lane=lane+1) begin:g_lane
            wire accepted,linked_store;
            wire [LSQ_SW-1:0] lsq_slot;
            wire [RS_SW-1:0] allocated_rs_slot;
            assign {accepted,linked_store,lsq_slot,allocated_rs_slot}=
                allocation_views[((row/4)*BE_WIDTH+lane)*LANE_WIDTH +: LANE_WIDTH];
            assign allocation_events[lane]=accepted && lsq_slot==row;
            assign allocation_values[lane*(RS_SW+1) +: RS_SW+1]={linked_store,allocated_rs_slot};
        end
        rv32_frequency_event_select #(.WIDTH(RS_SW+1),.EVENTS(BE_WIDTH)) allocation_selector (
            .events_i(allocation_events),.values_i(allocation_values),
            .write_o(allocation_write),.value_o({new_valid,new_rs_slot}));
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_release
            assign selected_releases[entry]=(rs_slot==entry) && release_views[(row/4)*RS_ENTRIES+entry];
        end
        wire released=valid && (|selected_releases);
        // Capture only on the same normal edge on which BOTH queues allocate.
        // Recovery inhibits allocations but still releases killed RS owners.
        always @(posedge clk_i) begin
            if(reset_views[row/4] || flush_views[row/4])
                valid<=1'b0;
            else
                if(!recovery_views[row/4] && allocation_write)
                begin
                    valid<=new_valid;
                    rs_slot<=new_rs_slot;
                end
                else
                    if(released)
                        valid<=1'b0;
        end
        assign link_valid_o[row]=valid;
        assign link_rs_slot_o[row*RS_SW +: RS_SW]=rs_slot;
    end endgenerate
endmodule
