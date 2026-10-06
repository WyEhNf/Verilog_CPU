"""Share and bound ROB status/metadata queries at existing edges; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


READS = r'''
    // Raw registered producer tags form the query independently of the
    // producer qualification process. Never feed that process's result
    // back through an asynchronous table read into its own live predicate.
    localparam integer ROB_LIVE_WIDTH=ROB_GENERATION_WIDTH+1;
    wire [ROB_ENTRIES*ROB_LIVE_WIDTH-1:0] rob_live_rows;
    wire [ROB_ENTRIES*3-1:0] rob_completion_state_rows;
    wire [PRODUCERS*TAG_WIDTH-1:0] producer_query_tags={
        lsq_load_complete_tag,mdu_completion_tag,alu_exec_tag};
    wire [PRODUCERS*ROB_LIVE_WIDTH-1:0] producer_live_reads;
    wire [BE_WIDTH*3-1:0] completion_state_reads;
    genvar status_row,status_source,status_lane;
    generate
        for(status_row=0;status_row<ROB_ENTRIES;status_row=status_row+1) begin:g_rob_status_row
            assign rob_live_rows[status_row*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]={
                rob_entry_valid[status_row],
                rob_entry_generation[status_row*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH]};
            assign rob_completion_state_rows[status_row*3 +: 3]={
                load_error_mem[status_row],rob_mem_size_mem[status_row]};
        end
        for(status_source=0;status_source<PRODUCERS;status_source=status_source+1) begin:g_producer_live_read
            rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                .rows_i(rob_live_rows),
                .index_i(producer_query_tags[status_source*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                .value_o(producer_live_reads[status_source*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]));
        end
        for(status_lane=0;status_lane<BE_WIDTH;status_lane=status_lane+1) begin:g_completion_state_read
            rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) state_read (
                .rows_i(rob_completion_state_rows),
                .index_i(rob_wb_tag[status_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                .value_o(completion_state_reads[status_lane*3 +: 3]));
        end
    endgenerate
'''


def queries(t):
    t=change(t,'    wire rob_mem_unsigned_mem [0:ROB_ENTRIES-1];',
             '    wire rob_mem_unsigned_mem [0:ROB_ENTRIES-1];\n'+READS)
    t=change(t,'    integer producer_live_slot;\n','')
    t=change(t,'''            producer_live_slot =
                producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
''','')
    t=change(t,'!rob_entry_valid[producer_live_slot]',
             '!producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH]')
    t=change(t,'rob_entry_generation[(producer_live_slot*ROB_GENERATION_WIDTH) +: ROB_GENERATION_WIDTH]',
             'producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]')
    t=change(t,'''        wire [ROB_SLOT_WIDTH-1:0] slot = alu_exec_tag[training_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
''','')
    t=change(t,'alu_exec_tag[training_lane*TAG_WIDTH] && rob_entry_valid[slot]',
             'alu_exec_tag[training_lane*TAG_WIDTH] &&\n            producer_live_reads[training_lane*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH]')
    t=change(t,'rob_entry_generation[slot*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH]',
             'producer_live_reads[training_lane*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]')
    t=change(t,'rob_entry_valid[lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]]',
             'producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH]')
    t=change(t,'rob_entry_generation[lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH]',
             'producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]')
    t=change(t,'load_error_mem[normal_slot]','completion_state_reads[routed_lane*3+2]')
    t=change(t,'rob_mem_size_mem[normal_slot]','completion_state_reads[routed_lane*3 +: 2]')
    t=change(t,'load_error_mem[slot]','completion_state_reads[SOURCE*3+2]')
    t=change(t,'rob_mem_size_mem[slot]','completion_state_reads[SOURCE*3 +: 2]')
    t=change(t,'''        wire [ROB_SLOT_WIDTH-1:0] selected_slot = selected_rob_tag[3 +: ROB_SLOT_WIDTH];''',
             '''        wire [ROB_SLOT_WIDTH-1:0] selected_slot = selected_rob_tag[3 +: ROB_SLOT_WIDTH];
        wire [ROB_LIVE_WIDTH-1:0] selected_live;
        rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
            .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
            .rows_i(rob_live_rows),.index_i(selected_slot),.value_o(selected_live));''')
    t=change(t,'selected_rob_tag[0] && rob_entry_valid[selected_slot]',
             'selected_rob_tag[0] && selected_live[ROB_GENERATION_WIDTH]')
    return change(t,'rob_entry_generation[selected_slot*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH]',
                  'selected_live[0 +: ROB_GENERATION_WIDTH]')


if __name__=='__main__':
    prepare('BO_shared_rob_status_queries',ROOT/'BN_memory_and_mdu_bounded_routing',
            {'rtl/backend/rv32_backend_joint.v':queries},
            'BN plus four-row ROB live/generation and completion error/size queries, reuse ALU live reads for training and LSQ live read for error response, share normal/shifted CDB metadata reads; queries depend on raw registered tags independently of producer filtering; early-store address live check uses the same bounded query topology; no added FF/cycles, no EDA')
