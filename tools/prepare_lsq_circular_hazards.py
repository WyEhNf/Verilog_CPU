"""Factor static LSQ pair ages and selected-store order; no HDL/EDA tests."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'    wire [7*LSQ_ENTRIES-1:0] circular_wrap_views;',
        '''    wire [8*LSQ_ENTRIES-1:0] circular_wrap_views;
    localparam integer HAZARD_WRAP_GROUPS=(LSQ_ENTRIES+3)/4;
    wire [LSQ_ENTRIES*HAZARD_WRAP_GROUPS-1:0] hazard_wrap_views;''')
    source=change(source,'''        rv32_frequency_control_tree #(.LEAVES(7)) wrap_tree (
            .signal_i(wrap_row<head_query_views[wrap_row*SLOT_WIDTH +: SLOT_WIDTH]),
            .views_o(circular_wrap_views[wrap_row*7 +: 7]));
        assign pick_wrap[LSQ_ENTRIES+wrap_row]=circular_wrap_views[wrap_row*7];''',
        '''        wire row_wrap=wrap_row<head_query_views[wrap_row*SLOT_WIDTH +: SLOT_WIDTH];
        rv32_frequency_control_tree #(.LEAVES(8)) wrap_tree (
            .signal_i(row_wrap),.views_o(circular_wrap_views[wrap_row*8 +: 8]));
        // Each leaf serves at most four opposite rows in the hazard matrix.
        rv32_frequency_control_tree #(.LEAVES(HAZARD_WRAP_GROUPS)) hazard_wrap_tree (
            .signal_i(row_wrap),
            .views_o(hazard_wrap_views[wrap_row*HAZARD_WRAP_GROUPS +: HAZARD_WRAP_GROUPS]));
        assign pick_wrap[LSQ_ENTRIES+wrap_row]=circular_wrap_views[wrap_row*8];''')
    for old,new in (
        ('circular_wrap_views[forward_slot*7+1+forward_byte]', 'circular_wrap_views[forward_slot*8+1+forward_byte]'),
        ('circular_wrap_views[report_row*7+5]', 'circular_wrap_views[report_row*8+5]'),
        ('circular_wrap_views[metadata_row*7+6]', 'circular_wrap_views[metadata_row*8+6]'),
    ):
        source=change(source,old,new)
    source=change(source,'    wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH];',
        '''    wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH];
    localparam integer FORWARD_ORDER_WIDTH=SLOT_WIDTH+1;
    wire [LSQ_ENTRIES*FORWARD_ORDER_WIDTH-1:0] selected_order_views;
    wire selected_wrap=selected_slot<head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH];
    rv32_frequency_control_tree #(.WIDTH(FORWARD_ORDER_WIDTH),.LEAVES(LSQ_ENTRIES)) selected_order_tree (
        .signal_i({selected_wrap,selected_slot}),.views_o(selected_order_views));''')
    source=change(source,'            assign store_overlap[age_slot] =',
        '''            wire [SLOT_WIDTH-1:0] local_selected_slot;
            wire local_selected_wrap;
            assign {local_selected_wrap,local_selected_slot}=
                selected_order_views[age_slot*FORWARD_ORDER_WIDTH +: FORWARD_ORDER_WIDTH];
            wire older_than_selected=
                (circular_wrap_views[age_slot*8+7]==local_selected_wrap) ?
                    (age_slot<local_selected_slot) :
                    (!circular_wrap_views[age_slot*8+7] && local_selected_wrap);
            assign store_overlap[age_slot] =''')
    source=change(source,'                (entry_age[age_slot] < selected_age) &&',
        '                (CIRCULAR_ORDER_POWER2 ? older_than_selected : (entry_age[age_slot] < selected_age)) &&')
    source=change(source,'''                  older_slot = older_slot + 1) begin : g_older_hazard
                assign older_hazard[older_slot] =
                    (entry_age[older_slot] < entry_age[request_slot]) &&''',
        '''                  older_slot = older_slot + 1) begin : g_older_hazard
                wire older_wrap=hazard_wrap_views[older_slot*HAZARD_WRAP_GROUPS+request_slot/4];
                wire request_wrap=hazard_wrap_views[request_slot*HAZARD_WRAP_GROUPS+older_slot/4];
                wire ordered_before;
                if(older_slot<request_slot) begin:g_lower_slot
                    assign ordered_before=!older_wrap || request_wrap;
                end else if(older_slot>request_slot) begin:g_higher_slot
                    assign ordered_before=!older_wrap && request_wrap;
                end else begin:g_same_slot
                    assign ordered_before=1'b0;
                end
                assign older_hazard[older_slot] =
                    (CIRCULAR_ORDER_POWER2 ? ordered_before : (entry_age[older_slot] < entry_age[request_slot])) &&''')
    return source


if __name__=='__main__':
    prepare('DD_lsq_circular_hazards',ROOT/'DC_lsq_circular_priority',
        {'rtl/backend/rv32_lsq.v':lsq},
        'Static LSQ older/request order uses two bounded wrap keys with row order resolved at elaboration; selected forwarding compares circular slot keys; original eligibility/masks/value/ownership/edges retained; no HDL/EDA tests')
