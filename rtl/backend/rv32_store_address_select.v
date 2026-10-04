`timescale 1ns/1ps

// Select one pending store whose existing RS base operand is ready. Select
// oldest in the circular LSQ, then lowest RS slot for deterministic duplicate
// tags. Only the address is published; this never dequeues RS work, produces
// a completion, marks store data ready or authorizes a memory write.
module rv32_store_address_select #(
    parameter integer LSQ_ENTRIES = 16,
    parameter integer RS_ENTRIES = 16,
    parameter integer TAG_WIDTH = 17,
    parameter integer ROB_TAG_WIDTH = TAG_WIDTH,
    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES),
    parameter integer LINKED_RS = 0,
    parameter integer RS_SW = (RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES)
) (
    input wire [HEAD_WIDTH-1:0] head_i,
    input wire [LSQ_ENTRIES-1:0] pending_i,
    input wire [LSQ_ENTRIES*TAG_WIDTH-1:0] lsq_tag_i,
    input wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] store_rob_tag_i,
    input wire [RS_ENTRIES-1:0] base_ready_i,
    input wire [RS_ENTRIES*ROB_TAG_WIDTH-1:0] rs_rob_tag_i,
    input wire [RS_ENTRIES*32-1:0] base_value_i,
    output wire valid_o,
    output wire [TAG_WIDTH-1:0] lsq_tag_o,
    output wire [ROB_TAG_WIDTH-1:0] rob_tag_o,
    output wire [31:0] base_value_o,
    output wire [RS_ENTRIES-1:0] base_select_o,
    // Enabled only for dispatch-owned links invalidated by RS release.
    input wire [LSQ_ENTRIES-1:0] link_valid_i,
    input wire [LSQ_ENTRIES*RS_SW-1:0] link_rs_slot_i
);

    localparam integer MATCH_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer RS_MATCH_WIDTH=(LINKED_RS!=0)?RS_ENTRIES:RS_ENTRIES*(ROB_TAG_WIDTH+1);
    // Preserve the lowest matching RS row as one-hot through store
    // selection. No selected index must be distributed and decoded again.
    localparam integer STORE_PACKET_WIDTH=TAG_WIDTH+ROB_TAG_WIDTH+RS_ENTRIES;
    wire [RS_MATCH_WIDTH-1:0] rs_match_input;
    wire [MATCH_DOMAINS*RS_MATCH_WIDTH-1:0] rs_match_views;
    wire [MATCH_DOMAINS*HEAD_WIDTH-1:0] head_views;
    wire [LSQ_ENTRIES-1:0] eligible,upper,first;
    wire [LSQ_ENTRIES*STORE_PACKET_WIDTH-1:0] row_packets;
    wire [STORE_PACKET_WIDTH-1:0] chosen_packet;
    wire upper_found=|upper;
    wire [MATCH_DOMAINS-1:0] wrap_enable_views;
    assign valid_o=|eligible;
    assign base_select_o=chosen_packet[0 +: RS_ENTRIES];
    assign rob_tag_o=chosen_packet[RS_ENTRIES +: ROB_TAG_WIDTH];
    assign lsq_tag_o=chosen_packet[RS_ENTRIES+ROB_TAG_WIDTH +: TAG_WIDTH];
    rv32_frequency_control_tree #(.WIDTH(RS_MATCH_WIDTH),.LEAVES(MATCH_DOMAINS)) rs_match_tree (
        .signal_i(rs_match_input),.views_o(rs_match_views));
    rv32_frequency_control_tree #(.WIDTH(HEAD_WIDTH),.LEAVES(MATCH_DOMAINS)) head_tree (
        .signal_i(head_i),.views_o(head_views));
    rv32_frequency_control_tree #(.LEAVES(MATCH_DOMAINS)) wrap_enable_tree (
        .signal_i(!upper_found),.views_o(wrap_enable_views));
    rv32_frequency_event_select #(.WIDTH(STORE_PACKET_WIDTH),.EVENTS(LSQ_ENTRIES),.PRIORITY(0)) store_packet_selector (
        .events_i(first),.values_i(row_packets),.write_o(),.value_o(chosen_packet));
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RS_ENTRIES),.PRIORITY(0)) base_selector (
        .events_i(base_select_o),.values_i(base_value_i),.write_o(),.value_o(base_value_o));
    genvar row,entry;
    generate
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_input
            if(LINKED_RS!=0) begin:g_linked_ready
                assign rs_match_input[entry]=base_ready_i[entry];
            end else begin:g_tagged_ready
                assign rs_match_input[entry*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH+1]={
                    base_ready_i[entry],rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]};
            end
        end
        for(row=0;row<LSQ_ENTRIES;row=row+1) begin:g_store
            wire [RS_ENTRIES-1:0] row_match_mask;
            wire [RS_ENTRIES-1:0] match_grants;
            wire match_found=|row_match_mask;
            for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_match
                if(LINKED_RS!=0) begin:g_linked_owner
                    assign row_match_mask[entry]=link_valid_i[row] &&
                        link_rs_slot_i[row*RS_SW +: RS_SW]==entry &&
                        rs_match_views[(row/4)*RS_ENTRIES+entry];
                end else begin:g_tagged_owner
                    assign row_match_mask[entry]=rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1)+ROB_TAG_WIDTH] &&
                        store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]==
                        rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
                end
                // A valid linked row names exactly one RS row. Legacy mode
                // keeps its lowest-index priority for duplicate full tags.
                if(LINKED_RS!=0 || entry==0) begin:g_first_match
                    assign match_grants[entry]=row_match_mask[entry];
                end else begin:g_later_match
                    assign match_grants[entry]=row_match_mask[entry] && !(|row_match_mask[entry-1:0]);
                end
            end
            assign eligible[row]=pending_i[row] && match_found;
            assign upper[row]=eligible[row] && row>=head_views[(row/4)*HEAD_WIDTH +: HEAD_WIDTH];
            // Circular priority: lowest eligible row at/above head,
            // otherwise lowest eligible row. Prefixes are parallel reductions.
            if(row==0) begin:g_first_store
                assign first[row]=upper[row] ||
                    (wrap_enable_views[row/4] && eligible[row]);
            end else begin:g_later_store
                assign first[row]=(upper[row] && !(|upper[row-1:0])) ||
                    (wrap_enable_views[row/4] && eligible[row] && !(|eligible[row-1:0]));
            end
            assign row_packets[row*STORE_PACKET_WIDTH +: STORE_PACKET_WIDTH]={
                lsq_tag_i[row*TAG_WIDTH +: TAG_WIDTH],store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH],match_grants};
        end
    endgenerate
    initial begin
        if (LSQ_ENTRIES < 1 || (LSQ_ENTRIES & (LSQ_ENTRIES-1)) != 0 ||
            RS_ENTRIES < 1 || TAG_WIDTH < 1 || ROB_TAG_WIDTH < 1) begin
            $display("ERROR: invalid shared store-address selector geometry");
            $finish;
        end
    end
endmodule


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
            if(reset_views[row/4] || flush_views[row/4]) valid<=1'b0;
            else if(!recovery_views[row/4] && allocation_write) begin
                valid<=new_valid;
                rs_slot<=new_rs_slot;
            end else if(released) valid<=1'b0;
        end
        assign link_valid_o[row]=valid;
        assign link_rs_slot_o[row*RS_SW +: RS_SW]=rs_slot;
    end endgenerate
endmodule
