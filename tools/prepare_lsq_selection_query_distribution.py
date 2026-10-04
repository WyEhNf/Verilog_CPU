"""Replace LSQ selected/picked/candidate array reads in source only."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'''    wire selection_live=selection_valid && tag_matches_slot(selection_lsq_tag,selection_slot) &&
        !request_sent_mem[selection_slot] && !complete_mem[selection_slot] && !response_wait_mem[selection_slot];''','''    localparam integer SELECT_STATE_WIDTH=GENERATION_WIDTH+8;
    localparam integer PICK_PAYLOAD_WIDTH=GENERATION_WIDTH+ROB_TAG_WIDTH+40;
    wire [LSQ_ENTRIES*SELECT_STATE_WIDTH-1:0] selection_state_rows;
    wire [LSQ_ENTRIES*PICK_PAYLOAD_WIDTH-1:0] pick_payload_rows;
    wire [LSQ_ENTRIES*4-1:0] candidate_state_rows;
    wire selection_row_valid,selection_row_sent,selection_row_complete,selection_row_wait,
        selection_row_store,selection_row_commit,selection_row_load,selection_row_retired;
    wire [GENERATION_WIDTH-1:0] selection_row_generation,pick_generation;
    wire [ROB_TAG_WIDTH-1:0] pick_rob_tag;
    wire [31:0] pick_store_data;
    wire [3:0] pick_store_mask;
    wire pick_load,pick_unsigned;
    wire [1:0] pick_size;
    wire candidate_wait,candidate_load,candidate_sent,candidate_complete;
    rv32_frequency_array_read #(.WIDTH(SELECT_STATE_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) selection_state_read (
        .rows_i(selection_state_rows),.index_i(selection_slot),
        .value_o({selection_row_generation,selection_row_valid,selection_row_sent,selection_row_complete,selection_row_wait,
                  selection_row_store,selection_row_commit,selection_row_load,selection_row_retired}));
    rv32_frequency_array_read #(.WIDTH(PICK_PAYLOAD_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) pick_payload_read (
        .rows_i(pick_payload_rows),.index_i(pick_slot[1]),
        .value_o({pick_generation,pick_rob_tag,pick_store_data,pick_store_mask,pick_load,pick_size,pick_unsigned}));
    rv32_frequency_array_read #(.WIDTH(4),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) candidate_state_read (
        .rows_i(candidate_state_rows),.index_i(candidate[SLOT_WIDTH-1:0]),
        .value_o({candidate_wait,candidate_load,candidate_sent,candidate_complete}));
    generate for(genvar query_row=0;query_row<LSQ_ENTRIES;query_row=query_row+1) begin:g_selected_query
        assign selection_state_rows[query_row*SELECT_STATE_WIDTH +: SELECT_STATE_WIDTH]={
            generation_mem[query_row],valid_mem[query_row],request_sent_mem[query_row],complete_mem[query_row],response_wait_mem[query_row],
            store_mem[query_row],store_commit_mem[query_row],load_mem[query_row],retired_mem[query_row]};
        assign pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH]={
            generation_mem[query_row],rob_tag_mem[query_row],data_mem[query_row],mask_mem[query_row],
            load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};
        assign candidate_state_rows[query_row*4 +: 4]={
            response_wait_mem[query_row],load_mem[query_row],request_sent_mem[query_row],complete_mem[query_row]};
    end endgenerate
    wire selection_live=selection_valid && selection_row_valid && selection_lsq_tag[0] &&
        selection_lsq_tag[3 +: SLOT_WIDTH]==selection_slot &&
        selection_lsq_tag[3+SLOT_WIDTH +: GENERATION_WIDTH]==selection_row_generation &&
        !selection_row_sent && !selection_row_complete && !selection_row_wait;''')
    for slot,items in [
        ('selection_slot',[('store_mem','selection_row_store'),('store_commit_mem','selection_row_commit'),
                           ('load_mem','selection_row_load'),('retired_mem','selection_row_retired')]),
        ('pick_slot[1]',[('generation_mem','pick_generation'),('rob_tag_mem','pick_rob_tag'),
                          ('data_mem','pick_store_data'),('mask_mem','pick_store_mask'),
                          ('load_mem','pick_load'),('size_mem','pick_size'),('unsigned_mem','pick_unsigned')]),
        ('candidate',[('response_wait_mem','candidate_wait'),('load_mem','candidate_load'),
                       ('request_sent_mem','candidate_sent'),('complete_mem','candidate_complete')]),
    ]:
        for array,field in items:
            old=array+'['+slot+']'
            if old+' <=' in source or old+'=' in source:
                raise ValueError('Unexpected indexed writer: '+old)
            if old not in source:
                raise ValueError('Expected indexed read missing: '+old)
            source=source.replace(old,field)
    return source


if __name__=='__main__':
    prepare('CK_lsq_selection_query_distribution',ROOT/'CJ_lsq_response_query_distribution',{
        'rtl/backend/rv32_lsq.v':lsq,
    },'CJ plus bounded static row reads for selection live/generation/recovery flags, tournament-picked allocation payload, and candidate request flags. Exact full generation/tag comparison retained, capacities and all transfer/hold/recovery edges unchanged. No new FF/cycle/SRAM or hardware tests; independent unadopted source candidate.')
