"""Remove serial store/RS index encoding and decoding; source-only preparation."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def onehot(t):
    t = change(t, '''    localparam integer RS_INDEX_WIDTH=(RS_ENTRIES<=1)?1:$clog2(RS_ENTRIES);
    localparam integer LSQ_INDEX_WIDTH=(LSQ_ENTRIES<=1)?1:$clog2(LSQ_ENTRIES);
    localparam integer MATCH_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer BASE_DOMAINS=(RS_ENTRIES+3)/4;''',
        '''    localparam integer MATCH_DOMAINS=(LSQ_ENTRIES+3)/4;''')
    t = change(t, '    localparam integer STORE_PACKET_WIDTH=TAG_WIDTH+ROB_TAG_WIDTH+RS_INDEX_WIDTH;',
        '''    // Preserve the lowest matching RS row as one-hot through store
    // selection. No selected index must be distributed and decoded again.
    localparam integer STORE_PACKET_WIDTH=TAG_WIDTH+ROB_TAG_WIDTH+RS_ENTRIES;''')
    t = change(t, '''    wire upper_found,wrap_found;
    wire [LSQ_INDEX_WIDTH-1:0] upper_slot,wrap_slot;
    wire [LSQ_INDEX_WIDTH-1:0] chosen_slot=upper_found?upper_slot:wrap_slot;
    wire [RS_INDEX_WIDTH-1:0] chosen_rs=chosen_packet[0 +: RS_INDEX_WIDTH];
    wire [BASE_DOMAINS*RS_INDEX_WIDTH-1:0] base_index_views;
    wire [BASE_DOMAINS-1:0] base_valid_views;
    assign valid_o=upper_found || wrap_found;
    assign rob_tag_o=chosen_packet[RS_INDEX_WIDTH +: ROB_TAG_WIDTH];
    assign lsq_tag_o=chosen_packet[RS_INDEX_WIDTH+ROB_TAG_WIDTH +: TAG_WIDTH];''',
        '''    wire upper_found=|upper;
    wire [MATCH_DOMAINS-1:0] wrap_enable_views;
    assign valid_o=|eligible;
    assign base_select_o=chosen_packet[0 +: RS_ENTRIES];
    assign rob_tag_o=chosen_packet[RS_ENTRIES +: ROB_TAG_WIDTH];
    assign lsq_tag_o=chosen_packet[RS_ENTRIES+ROB_TAG_WIDTH +: TAG_WIDTH];''')
    t = change(t, '''    rv32_frequency_first_two #(.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(LSQ_INDEX_WIDTH)) upper_selector (
        .candidates_i(upper),.first_valid_o(upper_found),.first_index_o(upper_slot),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(LSQ_INDEX_WIDTH)) wrap_selector (
        .candidates_i(eligible),.first_valid_o(wrap_found),.first_index_o(wrap_slot),
        .second_valid_o(),.second_index_o());''',
        '''    rv32_frequency_control_tree #(.LEAVES(MATCH_DOMAINS)) wrap_enable_tree (
        .signal_i(!upper_found),.views_o(wrap_enable_views));''')
    t = change(t, '''    rv32_frequency_control_tree #(.WIDTH(RS_INDEX_WIDTH),.LEAVES(BASE_DOMAINS)) base_index_tree (
        .signal_i(chosen_rs),.views_o(base_index_views));
    rv32_frequency_control_tree #(.LEAVES(BASE_DOMAINS)) base_valid_tree (
        .signal_i(valid_o),.views_o(base_valid_views));
''', '')
    t = change(t, '''            wire match_found;
            wire [RS_INDEX_WIDTH-1:0] match_slot;''',
        '''            wire [RS_ENTRIES-1:0] match_grants;
            wire match_found=|row_match_mask;''')
    t = change(t, '''                    rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
            end
            // Compute the lowest matching RS index alongside eligibility.
            // After choosing the oldest store, only this small index is
            // selected; the chosen ROB tag is never compared again.
            rv32_frequency_first_two #(.ENTRIES(RS_ENTRIES),.INDEX_WIDTH(RS_INDEX_WIDTH)) match_selector (
                .candidates_i(row_match_mask),.first_valid_o(match_found),.first_index_o(match_slot),
                .second_valid_o(),.second_index_o());''',
        '''                    rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
                if(entry==0) begin:g_first_match
                    assign match_grants[entry]=row_match_mask[entry];
                end else begin:g_later_match
                    assign match_grants[entry]=row_match_mask[entry] && !(|row_match_mask[entry-1:0]);
                end
            end''')
    t = change(t, '''            assign first[row]=valid_o && chosen_slot==row;
            assign row_packets[row*STORE_PACKET_WIDTH +: STORE_PACKET_WIDTH]={
                lsq_tag_i[row*TAG_WIDTH +: TAG_WIDTH],store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH],match_slot};
        end
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_base_pick
            assign base_select_o[entry]=base_valid_views[entry/4] &&
                base_index_views[(entry/4)*RS_INDEX_WIDTH +: RS_INDEX_WIDTH]==entry;
        end''',
        '''            // Circular priority: lowest eligible row at/above head,
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
        end''')
    return t


if __name__ == '__main__':
    prepare('DJ_store_address_onehot', ROOT/'DI_lsq_preselected_cancel',
        {'rtl/backend/rv32_store_address_select.v': onehot},
        'Preserve circular LSQ and lowest-RS priority as direct one-hot grants, removing serial store/RS index encode-decode; retain LSQ report guards and byte-local refill controls.')
