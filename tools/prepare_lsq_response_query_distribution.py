"""Prepare bounded response-identity/payload readers without HDL tests."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'''    wire [31:0] payload_response_word=dcache_resp_line_valid_i ?
        relative_data_from_line(dcache_resp_line_data_i,addr_mem[response_slot]) : dcache_resp_word_data_i;''','''    // Returning-cache identity previously selected separate dynamic arrays
    // with shared, wide decoded drivers. One static packet query reads the
    // exact same row; only the low address nibble is needed for extraction.
    localparam integer RESPONSE_QUERY_WIDTH=ROB_TAG_WIDTH+43;
    wire [LSQ_ENTRIES*RESPONSE_QUERY_WIDTH-1:0] response_query_rows;
    wire [3:0] response_query_offset,response_query_mask;
    wire [31:0] response_query_forward;
    wire [1:0] response_query_size;
    wire response_query_unsigned;
    wire [ROB_TAG_WIDTH-1:0] response_query_rob_tag;
    rv32_frequency_array_read #(.WIDTH(RESPONSE_QUERY_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) response_query_read (
        .rows_i(response_query_rows),.index_i(response_slot[SLOT_WIDTH-1:0]),
        .value_o({response_query_rob_tag,response_query_offset,response_query_forward,
                  response_query_mask,response_query_size,response_query_unsigned}));
    generate for(genvar response_row=0;response_row<LSQ_ENTRIES;response_row=response_row+1) begin:g_response_query
        assign response_query_rows[response_row*RESPONSE_QUERY_WIDTH +: RESPONSE_QUERY_WIDTH]={
            rob_tag_mem[response_row],addr_mem[response_row][3:0],forward_data_mem[response_row],
            forward_mask_mem[response_row],size_mem[response_row],unsigned_mem[response_row]};
    end endgenerate
    wire [LSQ_ENTRIES*SLOT_WIDTH-1:0] response_slot_views;
    rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(LSQ_ENTRIES)) response_slot_tree (
        .signal_i(response_slot[SLOT_WIDTH-1:0]),.views_o(response_slot_views));
    wire [31:0] response_line_word,payload_response_word;
    rv32_frequency_line_extract32 response_extract (
        .line_i(dcache_resp_line_data_i),.offset_i(response_query_offset),
        .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_line_word));
    wire [1:0] response_line_views;
    rv32_frequency_control_tree #(.LEAVES(2)) response_line_tree (
        .signal_i(dcache_resp_line_valid_i),.views_o(response_line_views));
    generate for(genvar response_word_id=0;response_word_id<2;response_word_id=response_word_id+1) begin:g_response_word
        assign payload_response_word[response_word_id*16 +: 16]=response_line_views[response_word_id]?
            response_line_word[response_word_id*16 +: 16]:dcache_resp_word_data_i[response_word_id*16 +: 16];
    end endgenerate''')
    source=change(source,'response_fire && response_slot==payload_row &&',
                        'response_fire && response_slot_views[payload_row*SLOT_WIDTH +: SLOT_WIDTH]==payload_row &&')
    source=change(source,'wire response_event=metadata_events[metadata_row*7+3] && response_slot==metadata_row;',
                        'wire response_event=metadata_events[metadata_row*7+3] && response_slot_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==metadata_row;')
    for array,field in [('forward_data_mem','response_query_forward'),
                        ('forward_mask_mem','response_query_mask'),
                        ('size_mem','response_query_size'),('unsigned_mem','response_query_unsigned'),
                        ('rob_tag_mem','response_query_rob_tag')]:
        old=array+'[response_slot]'
        if old+' <=' in source or old+'=' in source:
            raise ValueError('Unexpected response-state writer: '+array)
        if old not in source:
            raise ValueError('Missing expected response read: '+array)
        source=source.replace(old,field)
    # These two legacy temporaries have no remaining state writer, but keep
    # their RHS coherent with the payload owner's extraction/merge result.
    for indent in ('                    ','                '):
        source=change(source,indent+'''response_word = dcache_resp_line_valid_i ?
'''+indent+'''    relative_data_from_line(dcache_resp_line_data_i, addr_mem[response_slot]) :
'''+indent+'''    dcache_resp_word_data_i;''',indent+'response_word = payload_response_word;')
    if 'addr_mem[response_slot]' in source:
        raise ValueError('Unconverted response address read')
    return source


if __name__=='__main__':
    prepare('CJ_lsq_response_query_distribution',ROOT/'CI_lsq_head_query_distribution',{
        'rtl/backend/rv32_lsq.v':lsq,
    },'CI plus60-bit current-geometry static LSQ response row query, per-row response identity views, bounded line offset extraction and16-bit line-valid mux groups. Preserve response matching/generation, row/byte identity, merge/recovery priority and clock edges; no state/SRAM/cycle changes. Unadopted source-only candidate; no HDL/EDA/simulation.')
