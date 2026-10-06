"""Group RS wake broadcasts and bound first/last value selection, no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


def domains(t):
    anchor='    generate if (WAKE_MUX_IMPL != 0) begin : g_parallel_wake\n'
    local=r'''        localparam integer WAKE_DOMAINS=(ENTRIES+3)/4;
        wire [WAKE_DOMAINS*WAKE_WIDTH-1:0] valid_views;
        wire [WAKE_DOMAINS*WAKE_WIDTH*TAG_WIDTH-1:0] tag_views;
        wire [WAKE_DOMAINS*WAKE_WIDTH*32-1:0] value_views;
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH),.LEAVES(WAKE_DOMAINS)) valid_tree (
            .signal_i(wake_valid_i),.views_o(valid_views));
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH*TAG_WIDTH),.LEAVES(WAKE_DOMAINS)) tag_tree (
            .signal_i(wake_tag_i),.views_o(tag_views));
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH*32),.LEAVES(WAKE_DOMAINS)) value_tree (
            .signal_i(wake_value_i),.views_o(value_views));
'''
    t=change(t,anchor,anchor+local)
    start=t.index('        for (wr = 0; wr < ENTRIES;',t.index(anchor))
    stop=t.index('\n    end endgenerate',start)
    block=t[start:stop]
    block=change(block,'            wire [WAKE_WIDTH-1:0] first1, last1, first2, last2;',
        '''            localparam integer DOMAIN=wr/4;
            wire [WAKE_WIDTH-1:0] first1, last1, first2, last2;
            wire [WAKE_WIDTH-1:0] local_valid=valid_views[DOMAIN*WAKE_WIDTH +: WAKE_WIDTH];
            wire [WAKE_WIDTH*TAG_WIDTH-1:0] local_tags=tag_views[DOMAIN*WAKE_WIDTH*TAG_WIDTH +: WAKE_WIDTH*TAG_WIDTH];
            wire [WAKE_WIDTH*32-1:0] local_values=value_views[DOMAIN*WAKE_WIDTH*32 +: WAKE_WIDTH*32];''')
    block=block.replace('wake_valid_i[wl]','local_valid[wl]').replace('wake_tag_i[wl*TAG_WIDTH]','local_tags[wl*TAG_WIDTH]').replace('wake_tag_i[wl*TAG_WIDTH +: TAG_WIDTH]','local_tags[wl*TAG_WIDTH +: TAG_WIDTH]')
    pos=block.index('            reg [31:0] f1, l1, f2, l2;')
    # Stop before the next generate branch: four primitive selectors implement
    # the existing one-hot grants; conflicting tags keep first/last semantics.
    selectors=r'''            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) first1_selector (
                .events_i(first1),.values_i(local_values),.write_o(),.value_o(wake1_first[wr]));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) last1_selector (
                .events_i(last1),.values_i(local_values),.write_o(),.value_o(wake1_last[wr]));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) first2_selector (
                .events_i(first2),.values_i(local_values),.write_o(),.value_o(wake2_first[wr]));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) last2_selector (
                .events_i(last2),.values_i(local_values),.write_o(),.value_o(wake2_last[wr]));
        end
'''
    block=block[:pos]+selectors
    return t[:start]+block+t[stop:]


if __name__=='__main__':
    prepare('AU1_rs_local_wake_broadcasts',ROOT/'AT1_sixteen_bit_payload_control_budget',
            {'rtl/backend/rv32_reservation_station.v':domains},
            'AT1 plus RS wake tag/valid/value broadcasts grouped into at most four rows, bounded first/last value selectors with balanced OR; preserves conflicting duplicate-tag first combinational bypass vs last sequential overwrite semantics, same-cycle wake and original ready policy; no FF/latency change and no EDA')
