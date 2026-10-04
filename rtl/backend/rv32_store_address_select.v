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

    localparam integer MATCH_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer RS_MATCH_WIDTH=RS_ENTRIES*(ROB_TAG_WIDTH+1);
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
            assign rs_match_input[entry*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH+1]={
                base_ready_i[entry],rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]};
        end
        for(row=0;row<LSQ_ENTRIES;row=row+1) begin:g_store
            wire [RS_ENTRIES-1:0] row_match_mask;
            wire [RS_ENTRIES-1:0] match_grants;
            wire match_found=|row_match_mask;
            for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_match
                assign row_match_mask[entry]=rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1)+ROB_TAG_WIDTH] &&
                    store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]==
                    rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
                if(entry==0) begin:g_first_match
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
