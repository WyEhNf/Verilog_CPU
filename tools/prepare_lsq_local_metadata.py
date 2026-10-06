"""Replace global LSQ metadata write program with row-local owners, no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare


def write(field, value):
    return (f'{field}_write_data[metadata_row]={value}; '
            f'{field}_write_enable[metadata_row]=1\'b1;')


def defaults(fields):
    return '\n'.join(f'                {f}_write_data[metadata_row]=0; {f}_write_enable[metadata_row]=0;' for f in fields)


def clears(fields):
    return '\n'.join('                    '+write(f,"1'b0") for f in fields)


PREFIX = r'''
    // Three independent metadata groups per physical LSQ row. Local mode
    // leaves cannot collapse into one reset/recovery driver across all rows.
    localparam integer META_LSQ_AGE_WIDTH=((LSQ_ENTRIES & (LSQ_ENTRIES-1))==0)?SLOT_WIDTH:SLOT_WIDTH+1;
    wire [7*LSQ_ENTRIES-1:0] metadata_events;
    wire metadata_pop=(occupancy_reg!=0) && valid_mem[head_reg] &&
        ((load_mem[head_reg] && complete_mem[head_reg] &&
          (load_reported_mem[head_reg] || (load_complete_valid_o && load_complete_ready_i && complete_slot_select==head_reg))) ||
         (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i));
    wire metadata_forward=candidate_found && load_mem[candidate] &&
        !request_sent_mem[candidate] && !complete_mem[candidate] && ((fwd_mask & target_mask)==target_mask);
    rv32_frequency_control_tree #(.WIDTH(7),.LEAVES(LSQ_ENTRIES)) metadata_event_tree (
        .signal_i({metadata_pop,metadata_forward,request_fire,response_fire,dcache_store_ack_valid_i,
                   load_complete_valid_o && load_complete_ready_i,store_commit_valid_i && store_commit_ready_o}),
        .views_o(metadata_events));
    genvar metadata_row,metadata_lane;
    generate for(metadata_row=0;metadata_row<LSQ_ENTRIES;metadata_row=metadata_row+1) begin:g_metadata_row
        wire [8:0] modes;
        rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(3)) mode_tree (
            .signal_i(payload_modes[metadata_row*3 +: 3]),.views_o(modes));
        wire [BE_WIDTH-1:0] alloc_matches,addr_matches,data_matches,wake_matches,retire_matches;
        wire [BE_WIDTH*11-1:0] alloc_values;
        wire allocated;
        wire [10:0] allocation;
        for(metadata_lane=0;metadata_lane<BE_WIDTH;metadata_lane=metadata_lane+1) begin:g_match
            assign alloc_matches[metadata_lane]=alloc_fire_o[metadata_lane] &&
                payload_alloc_slot[metadata_lane]==metadata_row;
            assign alloc_values[metadata_lane*11 +: 11]={
                alloc_store_mask_i[metadata_lane*4 +: 4],
                alloc_data_valid_i[metadata_lane] || alloc_is_load_i[metadata_lane],
                alloc_addr_valid_i[metadata_lane],alloc_unsigned_i[metadata_lane],
                alloc_size_i[metadata_lane*2 +: 2],alloc_is_store_i[metadata_lane],alloc_is_load_i[metadata_lane]};
            assign addr_matches[metadata_lane]=addr_update_valid_i[metadata_lane] &&
                tag_matches_slot(addr_update_tag_i[metadata_lane*TAG_WIDTH +: TAG_WIDTH],metadata_row);
            assign data_matches[metadata_lane]=data_update_valid_i[metadata_lane] &&
                tag_matches_slot(data_update_tag_i[metadata_lane*TAG_WIDTH +: TAG_WIDTH],metadata_row);
            assign wake_matches[metadata_lane]=wakeup_valid_i[metadata_lane] &&
                tag_matches_slot(wakeup_tag_i[metadata_lane*TAG_WIDTH +: TAG_WIDTH],metadata_row);
            assign retire_matches[metadata_lane]=retire_valid_i[metadata_lane] && valid_mem[metadata_row] &&
                load_mem[metadata_row] && rob_tag_mem[metadata_row]==retire_rob_tag_i[metadata_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH];
        end
        rv32_frequency_event_select #(.WIDTH(11),.EVENTS(BE_WIDTH)) allocation_selector (
            .events_i(alloc_matches),.values_i(alloc_values),.write_o(allocated),.value_o(allocation));
        wire [GENERATION_WIDTH-1:0] allocated_generation=(generation_next_mem[metadata_row]==0)?
            {{(GENERATION_WIDTH-1){1'b0}},1'b1}:generation_next_mem[metadata_row];
        wire [META_LSQ_AGE_WIDTH-1:0] lsq_difference=metadata_row-head_reg;
        wire [META_LSQ_AGE_WIDTH-1:0] lsq_age=
            (((LSQ_ENTRIES & (LSQ_ENTRIES-1))!=0) && lsq_difference[META_LSQ_AGE_WIDTH-1])?
            lsq_difference+LSQ_ENTRIES:lsq_difference;
        wire [RECOVERY_ARITH_WIDTH-1:0] row_rob_age=payload_recovery_age(rob_tag_mem[metadata_row]);
        wire kill=lsq_age<occupancy_reg && valid_mem[metadata_row] &&
            !(store_mem[metadata_row] && store_commit_mem[metadata_row]) &&
            !(load_mem[metadata_row] && retired_mem[metadata_row]) &&
            row_rob_age>payload_branch_age && row_rob_age<recovery_occupancy_i;
        wire response_allowed=!(row_rob_age>payload_branch_age && row_rob_age<recovery_occupancy_i);
        wire commit_event=metadata_events[metadata_row*7] && commit_slot_select==metadata_row;
        wire report_event=metadata_events[metadata_row*7+1] && complete_slot_select==metadata_row;
        wire ack_event=metadata_events[metadata_row*7+2] &&
            tag_matches_slot(dcache_store_ack_lsq_tag_i,metadata_row) &&
            request_sent_mem[metadata_row] && response_wait_mem[metadata_row];
        wire response_event=metadata_events[metadata_row*7+3] && response_slot==metadata_row;
        wire request_event=metadata_events[metadata_row*7+4] && candidate==metadata_row;
        wire forward_event=metadata_events[metadata_row*7+5] && candidate==metadata_row;
        wire pop_event=metadata_events[metadata_row*7+6] && head_reg==metadata_row;
        wire early_event=(STORE_ADDRESS_PROBE!=0) && early_addr_valid_i &&
            tag_matches_slot(early_addr_tag_i,metadata_row) && store_mem[metadata_row] &&
            !addr_ready_mem[metadata_row] && !request_sent_mem[metadata_row] && !complete_mem[metadata_row];
'''


def owner_source():
    static=['load_mem','store_mem','generation_mem','generation_next_mem','size_mem','unsigned_mem']
    ready=['addr_ready_mem','data_ready_mem','mask_mem']
    live=['valid_mem','retired_mem','request_sent_mem','response_wait_mem','complete_mem',
          'load_reported_mem','complete_error_mem','forward_mask_mem','store_commit_mem','store_ack_mem','store_ack_error_mem']
    flushed=['valid_mem','retired_mem','request_sent_mem','response_wait_mem','complete_mem',
             'load_reported_mem','store_commit_mem','store_ack_mem']
    killed=[f for f in flushed if f!='retired_mem']
    popped=['valid_mem','request_sent_mem','response_wait_mem','complete_mem','load_reported_mem','store_ack_mem']
    result=PREFIX+'\n        always @* begin:g_static_commands\n'+defaults(static)+'''
                if(modes[0]) begin
                    @GENRESET@
                    @NEXTRESET@
                end else if(!modes[1] && !modes[2] && allocated) begin
                    @GENALLOC@
                    @NEXTALLOC@
                    @LOADALLOC@
                    @STOREALLOC@
                    @SIZEALLOC@
                    @UNSIGNEDALLOC@
                end
        end
        always @* begin:g_ready_commands
            integer update_lane;
            update_lane=0;
'''+defaults(ready)+'''
            if(!modes[3] && !modes[4]) begin
                if(!modes[5] && early_event) begin
                    @ADDRREADY@
                    if(mask_mem[metadata_row]==0) begin @ACCESSMASK@ end
                end
                // Both ordinary execution and recovery accept older live
                // AGU/data/wakeup updates. Later lanes preserve old priority.
                for(update_lane=0;update_lane<BE_WIDTH;update_lane=update_lane+1) begin
                    if(addr_matches[update_lane]) begin
                        @ADDRREADY@
                        if(mask_mem[metadata_row]==0 && store_mem[metadata_row]) begin @ACCESSMASK@ end
                    end
                    if(data_matches[update_lane]) begin
                        @DATAREADY@
                        if(data_mask_update_i[update_lane*4 +: 4]!=0) begin @DATAMASK@ end
                    end
                    if(wake_matches[update_lane]) begin @DATAREADY@ end
                end
                if(!modes[5] && allocated) begin
                    @ALLOCADDRREADY@
                    @ALLOCDATAREADY@
                    @ALLOCMASK@
                end
            end
        end
        always @* begin:g_lifecycle_commands
'''+defaults(live)+'''
            if(modes[6] || modes[7]) begin
@FLUSHED@
            end else if(modes[8]) begin
                if(kill) begin
@KILLED@
                end
                if(ack_event) begin
                    @ACK@
                    @ACKERROR@
                    @WAITCLEAR@
                end
                if(response_event && response_allowed) begin
                    @COMPLETEERROR@
                    @COMPLETE@
                    @WAITCLEAR@
                end
            end else begin
                if(commit_event) begin @COMMITTED@ end
                if(|retire_matches) begin @RETIRED@ end
                if(forward_event) begin
                    @COMPLETEERRORZERO@
                    @COMPLETE@
                end
                if(request_event) begin
                    @REQUESTSENT@
                    @WAIT@
                    if(load_mem[metadata_row]) begin @FORWARDMASK@ end
                end
                if(response_event) begin
                    @COMPLETEERROR@
                    @COMPLETE@
                    @WAITCLEAR@
                end
                if(report_event) begin @REPORTED@ end
                if(ack_event) begin
                    @ACK@
                    @ACKERROR@
                    @WAITCLEAR@
                end
                if(pop_event) begin
@POPPED@
                end
                if(allocated) begin
                    @VALID@
@ALLOCZERO@
                end
            end
        end
    end endgenerate
'''
    replacements={
        'GENRESET':write('generation_mem',"{{(GENERATION_WIDTH-1){1'b0}},1'b1}"),
        'NEXTRESET':write('generation_next_mem',"{{(GENERATION_WIDTH-1){1'b0}},1'b1}"),
        'GENALLOC':write('generation_mem','allocated_generation'),
        'NEXTALLOC':write('generation_next_mem',"(allocated_generation=={GENERATION_WIDTH{1'b1}})?{{(GENERATION_WIDTH-1){1'b0}},1'b1}:allocated_generation+1'b1"),
        'LOADALLOC':write('load_mem','allocation[0]'),
        'STOREALLOC':write('store_mem','allocation[1]'),
        'SIZEALLOC':write('size_mem','allocation[2 +: 2]'),
        'UNSIGNEDALLOC':write('unsigned_mem','allocation[4]'),
        'ADDRREADY':write('addr_ready_mem',"1'b1"),
        'DATAREADY':write('data_ready_mem',"1'b1"),
        'ACCESSMASK':write('mask_mem','access_mask(size_mem[metadata_row])'),
        'DATAMASK':write('mask_mem','data_mask_update_i[update_lane*4 +: 4]'),
        'ALLOCADDRREADY':write('addr_ready_mem','allocation[5]'),
        'ALLOCDATAREADY':write('data_ready_mem','allocation[6]'),
        'ALLOCMASK':write('mask_mem',"(allocation[7 +: 4]!=0)?allocation[7 +: 4]:((allocation[1] && allocation[5])?access_mask(allocation[2 +: 2]):4'b0)"),
        'FLUSHED':clears(flushed),'KILLED':clears(killed),'POPPED':clears(popped),
        'ACK':write('store_ack_mem',"1'b1"),
        'ACKERROR':write('store_ack_error_mem','dcache_store_ack_error_i'),
        'WAITCLEAR':write('response_wait_mem',"1'b0"),
        'COMPLETEERROR':write('complete_error_mem','dcache_resp_error_i'),
        'COMPLETEERRORZERO':write('complete_error_mem',"1'b0"),
        'COMPLETE':write('complete_mem',"1'b1"),
        'COMMITTED':write('store_commit_mem',"1'b1"),
        'RETIRED':write('retired_mem',"1'b1"),
        'REQUESTSENT':write('request_sent_mem',"1'b1"),
        'WAIT':write('response_wait_mem',"1'b1"),
        'FORWARDMASK':write('forward_mask_mem','fwd_mask'),
        'REPORTED':write('load_reported_mem',"1'b1"),
        'VALID':write('valid_mem',"1'b1"),
        'ALLOCZERO':clears([f for f in live if f!='valid_mem']),
    }
    for key,value in replacements.items(): result=result.replace('@'+key+'@',value)
    if '@' in result.replace('always @*',''): raise ValueError('Unresolved source placeholder')
    return result


def localize(t):
    start=t.index('    always @* begin : g_state_commands')
    stop=t.index('\n    always @(posedge clk_i) begin',start)
    return t[:start]+owner_source()+t[stop:]


if __name__=='__main__':
    prepare('AO_lsq_local_metadata_owners',ROOT/'AN_backend_owned_transaction_maps',
            {'rtl/backend/rv32_lsq.v':localize},
            'AN plus three row-local LSQ metadata groups, bounded reset/flush/recovery events, highest-lane allocation packet, narrow LSQ age and generation wrap; preserves older responses, recovery AGU/data/ACK writes, committed-store and retired-load exceptions and allocation-last/pop priority; removes centralized metadata write program; no new FF/cycles and no EDA')
