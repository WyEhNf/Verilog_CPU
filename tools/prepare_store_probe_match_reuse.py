"""Reuse the store/RS match matrix and remove serial re-match; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


SELECT = r'''
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
    rv32_frequency_event_select #(.WIDTH(STORE_PACKET_WIDTH),.EVENTS(LSQ_ENTRIES)) store_packet_selector (
        .events_i(first),.values_i(row_packets),.write_o(),.value_o(chosen_packet));
    rv32_frequency_control_tree #(.WIDTH(RS_INDEX_WIDTH),.LEAVES(BASE_DOMAINS)) base_index_tree (
        .signal_i(chosen_rs),.views_o(base_index_views));
    rv32_frequency_control_tree #(.LEAVES(BASE_DOMAINS)) base_valid_tree (
        .signal_i(valid_o),.views_o(base_valid_views));
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RS_ENTRIES)) base_selector (
        .events_i(base_select_o),.values_i(base_value_i),.write_o(),.value_o(base_value_o));
    genvar row,entry;
    generate
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_input
            assign rs_match_input[entry*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH+1]={
                base_ready_i[entry],rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]};
        end
        for(row=0;row<LSQ_ENTRIES;row=row+1) begin:g_store
            wire [RS_ENTRIES-1:0] matches;
            wire match_found;
            wire [RS_INDEX_WIDTH-1:0] match_slot;
            for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_rs_match
                assign matches[entry]=rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1)+ROB_TAG_WIDTH] &&
                    store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]==
                    rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
            end
            // Compute the lowest matching RS index alongside eligibility.
            // After choosing the oldest store, only this small index is
            // selected; the chosen ROB tag is never compared again.
            rv32_frequency_first_two #(.ENTRIES(RS_ENTRIES),.INDEX_WIDTH(RS_INDEX_WIDTH)) match_selector (
                .candidates_i(matches),.first_valid_o(match_found),.first_index_o(match_slot),
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
'''


def selector(t):
    t=change(t,'    output wire [31:0] base_value_o\n',
             '    output wire [31:0] base_value_o,\n    output wire [RS_ENTRIES-1:0] base_select_o\n')
    a=t.index('    wire [LSQ_ENTRIES-1:0] eligible, upper, choices, first;')
    b=t.index('    initial begin',a)
    return t[:a]+SELECT+t[b:]


def backend(t):
    t=change(t,'        wire [31:0] selected_imm;',
             '        wire [31:0] selected_imm;\n        wire [RS_ENTRIES-1:0] selected_rs;')
    t=change(t,'.rob_tag_o(selected_rob_tag), .base_value_o(selected_base)',
             '.rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)')
    a=t.index('            wire [RS_ENTRIES-1:0] metadata_matches, selected_rs;')
    b=t.index('        end else begin : g_rob_imm',a)
    t=t[:a]+r'''            wire [RS_ENTRIES*32-1:0] immediate_rows;
            genvar meta_slot;
            for(meta_slot=0;meta_slot<RS_ENTRIES;meta_slot=meta_slot+1) begin:g_immediate_row
                assign immediate_rows[meta_slot*32 +: 32]=rs_entry_metadata[meta_slot*RS_METADATA_WIDTH +: 32];
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RS_ENTRIES)) immediate_selector (
                .events_i(selected_rs),.values_i(immediate_rows),.write_o(),.value_o(selected_imm));
'''+t[b:]
    return t


if __name__=='__main__':
    prepare('BP_store_probe_match_reuse',ROOT/'BO_shared_rob_status_queries',{
        'rtl/backend/rv32_store_address_select.v':selector,
        'rtl/backend/rv32_backend_joint.v':backend,
    },'BO plus parallel per-store lowest-ready-RS index from the existing match matrix; circular oldest-store balanced arbitration selects tags and RS index together; base operand and inline immediate share this selected RS grant, removing two serial post-selection tag re-matches; query domains at most four rows and final sixteen-bit one-hot payload selection; no new FF/cycles, no EDA')
