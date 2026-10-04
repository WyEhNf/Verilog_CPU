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
    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)
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
    output wire [RS_ENTRIES-1:0] base_select_o
);

    localparam integer RS_INDEX_WIDTH=(RS_ENTRIES<=1)?1:$clog2(RS_ENTRIES);
    localparam integer LSQ_INDEX_WIDTH=(LSQ_ENTRIES<=1)?1:$clog2(LSQ_ENTRIES);
    localparam integer MATCH_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer BASE_DOMAINS=(RS_ENTRIES+3)/4;
    localparam integer RS_MATCH_WIDTH=RS_ENTRIES*(ROB_TAG_WIDTH+1);
    localparam integer STORE_PACKET_WIDTH=TAG_WIDTH+ROB_TAG_WIDTH+RS_INDEX_WIDTH;
    wire [RS_MATCH_WIDTH-1:0] rs_match_input;
    wire [MATCH_DOMAINS*RS_MATCH_WIDTH-1:0] rs_match_views;
    wire [MATCH_DOMAINS*HEAD_WIDTH-1:0] head_views;
    wire [LSQ_ENTRIES-1:0] eligible,upper,first;
    wire [LSQ_ENTRIES*STORE_PACKET_WIDTH-1:0] row_packets;
    wire [STORE_PACKET_WIDTH-1:0] chosen_packet;
    wire upper_found,wrap_found;
    wire [LSQ_INDEX_WIDTH-1:0] upper_slot,wrap_slot;
    wire [LSQ_INDEX_WIDTH-1:0] chosen_slot=upper_found?upper_slot:wrap_slot;
    wire [RS_INDEX_WIDTH-1:0] chosen_rs=chosen_packet[0 +: RS_INDEX_WIDTH];
    wire [BASE_DOMAINS*RS_INDEX_WIDTH-1:0] base_index_views;
    wire [BASE_DOMAINS-1:0] base_valid_views;
    assign valid_o=upper_found || wrap_found;
    assign rob_tag_o=chosen_packet[RS_INDEX_WIDTH +: ROB_TAG_WIDTH];
    assign lsq_tag_o=chosen_packet[RS_INDEX_WIDTH+ROB_TAG_WIDTH +: TAG_WIDTH];
    rv32_frequency_control_tree #(.WIDTH(RS_MATCH_WIDTH),.LEAVES(MATCH_DOMAINS)) rs_match_tree (
        .signal_i(rs_match_input),.views_o(rs_match_views));
    rv32_frequency_control_tree #(.WIDTH(HEAD_WIDTH),.LEAVES(MATCH_DOMAINS)) head_tree (
        .signal_i(head_i),.views_o(head_views));
    rv32_frequency_first_two #(.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(LSQ_INDEX_WIDTH)) upper_selector (
        .candidates_i(upper),.first_valid_o(upper_found),.first_index_o(upper_slot),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(LSQ_INDEX_WIDTH)) wrap_selector (
        .candidates_i(eligible),.first_valid_o(wrap_found),.first_index_o(wrap_slot),
        .second_valid_o(),.second_index_o());
    rv32_frequency_event_select #(.WIDTH(STORE_PACKET_WIDTH),.EVENTS(LSQ_ENTRIES),.PRIORITY(0)) store_packet_selector (
        .events_i(first),.values_i(row_packets),.write_o(),.value_o(chosen_packet));
    rv32_frequency_control_tree #(.WIDTH(RS_INDEX_WIDTH),.LEAVES(BASE_DOMAINS)) base_index_tree (
        .signal_i(chosen_rs),.views_o(base_index_views));
    rv32_frequency_control_tree #(.LEAVES(BASE_DOMAINS)) base_valid_tree (
        .signal_i(valid_o),.views_o(base_valid_views));
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RS_ENTRIES),.PRIORITY(0)) base_selector (
        .events_i(base_select_o),.values_i(base_value_i),.write_o(),.value_o(base_value_o));
    genvar row,entry;
    generate
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_input
            assign rs_match_input[entry*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH+1]={
                base_ready_i[entry],rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]};
        end
        for(row=0;row<LSQ_ENTRIES;row=row+1) begin:g_store
            wire [RS_ENTRIES-1:0] row_match_mask;
            wire match_found;
            wire [RS_INDEX_WIDTH-1:0] match_slot;
            for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_match
                assign row_match_mask[entry]=rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1)+ROB_TAG_WIDTH] &&
                    store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]==
                    rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
            end
            // Compute the lowest matching RS index alongside eligibility.
            // After choosing the oldest store, only this small index is
            // selected; the chosen ROB tag is never compared again.
            rv32_frequency_first_two #(.ENTRIES(RS_ENTRIES),.INDEX_WIDTH(RS_INDEX_WIDTH)) match_selector (
                .candidates_i(row_match_mask),.first_valid_o(match_found),.first_index_o(match_slot),
                .second_valid_o(),.second_index_o());
            assign eligible[row]=pending_i[row] && match_found;
            assign upper[row]=eligible[row] && row>=head_views[(row/4)*HEAD_WIDTH +: HEAD_WIDTH];
            assign first[row]=valid_o && chosen_slot==row;
            assign row_packets[row*STORE_PACKET_WIDTH +: STORE_PACKET_WIDTH]={
                lsq_tag_i[row*TAG_WIDTH +: TAG_WIDTH],store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH],match_slot};
        end
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_base_pick
            assign base_select_o[entry]=base_valid_views[entry/4] &&
                base_index_views[(entry/4)*RS_INDEX_WIDTH +: RS_INDEX_WIDTH]==entry;
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
