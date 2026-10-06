"""Prepare dispatch-owned LSQ/RS address links; source-only, no hardware tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


LINK_OWNER = '''

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
    wire [BE_WIDTH*LANE_WIDTH-1:0] allocation_packet;
    wire [LSQ_ENTRIES*BE_WIDTH*LANE_WIDTH-1:0] allocation_views;
    wire [LSQ_ENTRIES*RS_ENTRIES-1:0] release_views;
    wire [LSQ_ENTRIES-1:0] reset_views,flush_views,recovery_views;
    genvar lane,row,entry;
    generate for(lane=0;lane<BE_WIDTH;lane=lane+1) begin:g_allocation_packet
        assign allocation_packet[lane*LANE_WIDTH +: LANE_WIDTH]={
            lsq_alloc_fire_i[lane],
            alloc_is_store_i[lane] && rs_alloc_fire_i[lane],
            alloc_lsq_tag_i[lane*TAG_WIDTH+3 +: LSQ_SW],
            alloc_rs_slot_i[lane*RS_SW +: RS_SW]};
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*LANE_WIDTH),.LEAVES(LSQ_ENTRIES)) allocation_tree (
        .signal_i(allocation_packet),.views_o(allocation_views));
    rv32_frequency_control_tree #(.WIDTH(RS_ENTRIES),.LEAVES(LSQ_ENTRIES)) release_tree (
        .signal_i(rs_release_i),.views_o(release_views));
    rv32_frequency_control_tree #(.LEAVES(LSQ_ENTRIES)) reset_tree (
        .signal_i(reset_i),.views_o(reset_views));
    rv32_frequency_control_tree #(.LEAVES(LSQ_ENTRIES)) flush_tree (
        .signal_i(flush_i),.views_o(flush_views));
    rv32_frequency_control_tree #(.LEAVES(LSQ_ENTRIES)) recovery_tree (
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
                allocation_views[(row*BE_WIDTH+lane)*LANE_WIDTH +: LANE_WIDTH];
            assign allocation_events[lane]=accepted && lsq_slot==row;
            assign allocation_values[lane*(RS_SW+1) +: RS_SW+1]={linked_store,allocated_rs_slot};
        end
        rv32_frequency_event_select #(.WIDTH(RS_SW+1),.EVENTS(BE_WIDTH)) allocation_selector (
            .events_i(allocation_events),.values_i(allocation_values),
            .write_o(allocation_write),.value_o({new_valid,new_rs_slot}));
        for(entry=0;entry<RS_ENTRIES;entry=entry+1) begin:g_release
            assign selected_releases[entry]=(rs_slot==entry) && release_views[row*RS_ENTRIES+entry];
        end
        wire released=valid && (|selected_releases);
        // Capture only on the same normal edge on which BOTH queues allocate.
        // Recovery inhibits allocations but still releases killed RS owners.
        always @(posedge clk_i) begin
            if(reset_views[row] || flush_views[row]) valid<=1'b0;
            else if(!recovery_views[row] && allocation_write) begin
                valid<=new_valid;
                rs_slot<=new_rs_slot;
            end else if(released) valid<=1'b0;
        end
        assign link_valid_o[row]=valid;
        assign link_rs_slot_o[row*RS_SW +: RS_SW]=rs_slot;
    end endgenerate
endmodule
'''


def rs_exports(t):
    t=change(t, '''    output wire [((ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1))-1:0] occupancy_o
);''',
        '''    output wire [((ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1))-1:0] occupancy_o,
    // Read-only identities/events of existing state changes. No new RS state.
    output wire [BE_WIDTH*SLOT_WIDTH-1:0] alloc_slot_o,
    output wire [ENTRIES-1:0] entry_release_o
);''')
    t=change(t, '''    wire [ENTRIES-1:0] alloc_row_write;
    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];''',
        '''    wire [ENTRIES-1:0] alloc_row_write;
    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];
    genvar export_lane,export_row;
    generate
        for(export_lane=0;export_lane<BE_WIDTH;export_lane=export_lane+1) begin:g_allocation_identity
            if(ALLOC_STATIC_WRITE!=0)
                assign alloc_slot_o[export_lane*SLOT_WIDTH +: SLOT_WIDTH]=allocation_slots[export_lane];
            else assign alloc_slot_o[export_lane*SLOT_WIDTH +: SLOT_WIDTH]=0;
        end
        for(export_row=0;export_row<ENTRIES;export_row=export_row+1) begin:g_release_identity
            wire [BE_WIDTH-1:0] issued_here;
            for(export_lane=0;export_lane<BE_WIDTH;export_lane=export_lane+1) begin:g_lane
                assign issued_here[export_lane]=issue_valid_o[export_lane] && issue_ready_i[export_lane] &&
                    issue_slot_o[export_lane*SLOT_WIDTH +: SLOT_WIDTH]==export_row;
            end
            // Mirrors valid_mem's reset / flush / ordinary issue priorities.
            assign entry_release_o[export_row]=reset_i ||
                (flush_valid_i ? flush_kill_mask_i[export_row] : (|issued_here));
        end
    endgenerate''')
    return t


def selector(t):
    t=change(t, '    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)',
        '''    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES),
    parameter integer LINKED_RS = 0,
    parameter integer RS_SW = (RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES)''')
    t=change(t, '''    output wire [RS_ENTRIES-1:0] base_select_o
);''',
        '''    output wire [RS_ENTRIES-1:0] base_select_o,
    // Enabled only for dispatch-owned links invalidated by RS release.
    input wire [LSQ_ENTRIES-1:0] link_valid_i,
    input wire [LSQ_ENTRIES*RS_SW-1:0] link_rs_slot_i
);''')
    t=change(t, '    localparam integer RS_MATCH_WIDTH=RS_ENTRIES*(ROB_TAG_WIDTH+1);',
        '    localparam integer RS_MATCH_WIDTH=(LINKED_RS!=0)?RS_ENTRIES:RS_ENTRIES*(ROB_TAG_WIDTH+1);')
    t=change(t, '''            assign rs_match_input[entry*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH+1]={
                base_ready_i[entry],rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]};''',
        '''            if(LINKED_RS!=0) begin:g_linked_ready
                assign rs_match_input[entry]=base_ready_i[entry];
            end else begin:g_tagged_ready
                assign rs_match_input[entry*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH+1]={
                    base_ready_i[entry],rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]};
            end''')
    t=change(t, '''                assign row_match_mask[entry]=rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1)+ROB_TAG_WIDTH] &&
                    store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]==
                    rs_match_views[((row/4)*RS_ENTRIES+entry)*(ROB_TAG_WIDTH+1) +: ROB_TAG_WIDTH];
                if(entry==0) begin:g_first_match''',
        '''                if(LINKED_RS!=0) begin:g_linked_owner
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
                if(LINKED_RS!=0 || entry==0) begin:g_first_match''')
    return t+LINK_OWNER


def backend(t):
    t=change(t, '    wire [RS_ENTRIES-1:0] rs_entry_base_ready;',
        '''    wire [RS_ENTRIES-1:0] rs_entry_base_ready;
    localparam integer STORE_RS_LINKS=(EARLY_STORE_ADDRESS==2) && (RS_ALLOC_STATIC_WRITE!=0);
    localparam integer STORE_RS_SW=(RS_ENTRIES<=1)?1:$clog2(RS_ENTRIES);
    wire [BE_WIDTH*STORE_RS_SW-1:0] rs_alloc_slot;
    wire [RS_ENTRIES-1:0] rs_entry_release;
    wire [LSQ_ENTRIES-1:0] store_rs_link_valid;
    wire [LSQ_ENTRIES*STORE_RS_SW-1:0] store_rs_link_slot;''')
    t=change(t, '''    generate if (EARLY_STORE_ADDRESS == 2) begin : g_shared_store_address
        wire selected;''',
        '''    generate if(STORE_RS_LINKS!=0) begin:g_store_rs_links
        rv32_store_rs_links #(.BE_WIDTH(BE_WIDTH),.LSQ_ENTRIES(LSQ_ENTRIES),
            .RS_ENTRIES(RS_ENTRIES),.TAG_WIDTH(TAG_WIDTH)) owner (
            .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),
            .recovery_i(recovery_domains[4] || recovery_domains[5]),
            .lsq_alloc_fire_i(lsq_alloc_fire),.rs_alloc_fire_i(rs_alloc_fire),
            .alloc_is_store_i(d_is_store),.alloc_lsq_tag_i(lsq_alloc_tag),
            .alloc_rs_slot_i(rs_alloc_slot),.rs_release_i(rs_entry_release),
            .link_valid_o(store_rs_link_valid),.link_rs_slot_o(store_rs_link_slot));
    end else begin:g_no_store_rs_links
        assign store_rs_link_valid=0;
        assign store_rs_link_slot=0;
    end endgenerate
    generate if (EARLY_STORE_ADDRESS == 2) begin : g_shared_store_address
        wire selected;''')
    t=change(t, '''            .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH)) selector (
            .head_i(lsq_head), .pending_i(lsq_store_addr_pending),''',
        '''            .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH),.LINKED_RS(STORE_RS_LINKS)) selector (
            .link_valid_i(store_rs_link_valid),.link_rs_slot_i(store_rs_link_slot),
            .head_i(lsq_head), .pending_i(lsq_store_addr_pending),''')
    t=change(t, '''        .entry_base_ready_o(rs_entry_base_ready), .entry_base_value_o(rs_entry_base_value),''',
        '''        .entry_base_ready_o(rs_entry_base_ready), .entry_base_value_o(rs_entry_base_value),
        .alloc_slot_o(rs_alloc_slot),.entry_release_o(rs_entry_release),''')
    return t


if __name__ == '__main__':
    prepare('DL_store_rs_links', ROOT/'DK_store_address_prefix',
        {'rtl/backend/rv32_reservation_station.v':rs_exports,
         'rtl/backend/rv32_store_address_select.v':selector,
         'rtl/backend/rv32_backend_joint.v':backend},
        'Replace the early store-address 16x12 full ROB-tag association with dispatch-captured 4-bit RS links and same-edge release invalidation; 80 new link bits, no pipeline cycle, final ROB authority retained; inherit DH/DI/DJ/DK.')
