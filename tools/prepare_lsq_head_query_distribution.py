"""Bound LSQ head/age read consumers in an untested source candidate."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'    reg [SLOT_WIDTH-1:0] head_reg;','''    reg [SLOT_WIDTH-1:0] head_reg;
    // Head address had shared decoded drivers feeding ~170 mapped pins.
    // Every row owns its age/ack/pop query; non-row uses get one extra view.
    wire [(LSQ_ENTRIES+1)*SLOT_WIDTH-1:0] head_query_views;
    rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(LSQ_ENTRIES+1)) head_query_tree (
        .signal_i(head_reg),.views_o(head_query_views));
    wire [6*LSQ_ENTRIES-1:0] head_metadata_rows;
    wire head_valid,head_load,head_complete,head_reported,head_store,head_ack;
    rv32_frequency_array_read #(.WIDTH(6),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) head_metadata_read (
        .rows_i(head_metadata_rows),.index_i(head_reg),
        .value_o({head_valid,head_load,head_complete,head_reported,head_store,head_ack}));
    generate for(genvar head_row=0;head_row<LSQ_ENTRIES;head_row=head_row+1) begin:g_head_metadata
        assign head_metadata_rows[head_row*6 +: 6]={valid_mem[head_row],load_mem[head_row],
            complete_mem[head_row],load_reported_mem[head_row],store_mem[head_row],store_ack_mem[head_row]};
    end endgenerate''')
    source=change(source,'wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_reg;',
                        'wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH];')
    source=change(source,'assign entry_age[age_slot] = (age_slot - head_reg) & (LSQ_ENTRIES - 1);',
                        'assign entry_age[age_slot] = (age_slot - head_query_views[age_slot*SLOT_WIDTH +: SLOT_WIDTH]) & (LSQ_ENTRIES - 1);')
    source=change(source,'occupancy_reg!=0 && head_reg==report_row &&',
                        'occupancy_reg!=0 && head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH]==report_row &&')
    source=change(source,'wire [META_LSQ_AGE_WIDTH-1:0] lsq_difference=metadata_row-head_reg;',
                        'wire [META_LSQ_AGE_WIDTH-1:0] lsq_difference=metadata_row-head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH];')
    source=change(source,'wire pop_event=metadata_events[metadata_row*7+6] && head_reg==metadata_row;',
                        'wire pop_event=metadata_events[metadata_row*7+6] && head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==metadata_row;')
    source=change(source,'                scan = head_reg + slot;',
                        '                scan = head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH] + slot;')
    # All former head-indexed accesses are reads. Hold the state arrays and
    # their writers unchanged; one six-bit parallel query serves the checks.
    for array,field in [('valid_mem','head_valid'),('load_mem','head_load'),
                        ('complete_mem','head_complete'),('load_reported_mem','head_reported'),
                        ('store_mem','head_store'),('store_ack_mem','head_ack')]:
        old=array+'[head_reg]'
        if old+' <=' in source or old+'=' in source:
            raise ValueError('Unexpected dynamic head writer: '+array)
        if old not in source:
            raise ValueError('Missing expected head read: '+array)
        source=source.replace(old,field)
    return source


if __name__=='__main__':
    prepare('CI_lsq_head_query_distribution',ROOT/'CH_icache_metadata_distribution',{
        'rtl/backend/rv32_lsq.v':lsq,
    },'CH plus per-row head address views for LSQ age/ack/pop and bounded six-bit static head metadata selection. Same head/occupancy update, age arithmetic, recovery scan, valid/tag/protocol and cycle. No extra state; no HDL/EDA/simulation. Independent unadopted source candidate.')
