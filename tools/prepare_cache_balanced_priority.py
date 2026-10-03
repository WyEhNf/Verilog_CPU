"""Replace cache serial scans with balanced first/two-first trees; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


PRIORITY = r'''

// Merge the first two entries of each half concurrently. Every node owns
// only two short indices; payload routing is a separate bounded operation.
module rv32_frequency_first_two #(
    parameter integer ENTRIES=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES-1:0] candidates_i,
    output wire first_valid_o,second_valid_o,
    output wire [INDEX_WIDTH-1:0] first_index_o,second_index_o
);
    wire first_valid [1:2*LEAVES-1];
    wire second_valid [1:2*LEAVES-1];
    wire [INDEX_WIDTH-1:0] first_index [1:2*LEAVES-1];
    wire [INDEX_WIDTH-1:0] second_index [1:2*LEAVES-1];
    assign first_valid_o=first_valid[1];
    assign second_valid_o=second_valid[1];
    assign first_index_o=first_index[1];
    assign second_index_o=second_index[1];
    genvar slot,node;
    generate
        for(slot=0;slot<LEAVES;slot=slot+1) begin:g_leaf
            if(slot<ENTRIES) begin:g_present
                assign first_valid[LEAVES+slot]=candidates_i[slot];
                assign first_index[LEAVES+slot]=candidates_i[slot]?INDEX_WIDTH'(slot):{INDEX_WIDTH{1'b0}};
            end else begin:g_padding
                assign first_valid[LEAVES+slot]=1'b0;
                assign first_index[LEAVES+slot]=0;
            end
            assign second_valid[LEAVES+slot]=1'b0;
            assign second_index[LEAVES+slot]=0;
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_merge
            assign first_valid[node]=first_valid[2*node] || first_valid[2*node+1];
            assign second_valid[node]=second_valid[2*node] ||
                (first_valid[2*node] && first_valid[2*node+1]) || second_valid[2*node+1];
            assign first_index[node]=first_valid[2*node]?first_index[2*node]:first_index[2*node+1];
            assign second_index[node]=second_valid[2*node]?second_index[2*node]:
                (first_valid[2*node]?first_index[2*node+1]:second_index[2*node+1]);
        end
    endgenerate
endmodule
'''


SELECTORS = r'''
    wire [MSHR_ENTRIES-1:0] free_candidates,send_candidates,local_candidates,matching_candidates;
    wire [MSHR_ENTRIES-1:0] live_candidates,store_candidates,prefetch_present_candidates,request_conflict_candidates,prefetch_conflict_candidates;
    wire [WAITER_ENTRIES-1:0] waiter_free_candidates,waiter_load_candidates,waiter_store_candidates;
    wire unlocked_send_found;
    wire [2:0] unlocked_send_index;
    genvar scan_mshr,scan_waiter;
    generate
        for(scan_mshr=0;scan_mshr<MSHR_ENTRIES;scan_mshr=scan_mshr+1) begin:g_mshr_candidates
            assign live_candidates[scan_mshr]=mshr_valid[scan_mshr];
            assign store_candidates[scan_mshr]=mshr_valid[scan_mshr] && mshr_store[scan_mshr];
            assign free_candidates[scan_mshr]=!mshr_valid[scan_mshr];
            assign local_candidates[scan_mshr]=STORE_MERGE_DELAY!=0 && mshr_valid[scan_mshr] &&
                mshr_store[scan_mshr] && !mshr_sent[scan_mshr] && !mshr_writeback[scan_mshr] &&
                !mshr_rfo_offered[scan_mshr] && mshr_mask[scan_mshr]==16'hffff;
            assign send_candidates[scan_mshr]=mshr_valid[scan_mshr] && !mshr_sent[scan_mshr] &&
                (mshr_writeback[scan_mshr] || !mshr_store[scan_mshr] || STORE_MERGE_DELAY==0 ||
                 mshr_rfo_offered[scan_mshr] || (mshr_merge_delay[scan_mshr]==0 && mshr_mask[scan_mshr]!=16'hffff));
            assign matching_candidates[scan_mshr]=mshr_valid[scan_mshr] && !mshr_writeback[scan_mshr] &&
                {mshr_addr[scan_mshr][31:4],4'b0}==request_line_addr;
            assign prefetch_present_candidates[scan_mshr]=mshr_valid[scan_mshr] && !mshr_writeback[scan_mshr] &&
                {mshr_addr[scan_mshr][31:4],4'b0}==prefetch_line_addr;
            assign request_conflict_candidates[scan_mshr]=mshr_valid[scan_mshr] && cache_index(mshr_addr[scan_mshr])==request_index;
            assign prefetch_conflict_candidates[scan_mshr]=mshr_valid[scan_mshr] && cache_index(mshr_addr[scan_mshr])==prefetch_index;
        end
        for(scan_waiter=0;scan_waiter<WAITER_ENTRIES;scan_waiter=scan_waiter+1) begin:g_waiter_candidates
            assign waiter_free_candidates[scan_waiter]=!waiter_valid[scan_waiter];
            assign waiter_load_candidates[scan_waiter]=waiter_valid[scan_waiter] && waiter_ready[scan_waiter] && !waiter_store[scan_waiter];
            assign waiter_store_candidates[scan_waiter]=waiter_valid[scan_waiter] && waiter_ready[scan_waiter] && waiter_store[scan_waiter];
        end
    endgenerate
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) free_selector (
        .candidates_i(free_candidates),.first_valid_o(free_found),.second_valid_o(second_free_found),
        .first_index_o(free_index),.second_index_o(second_free_index));
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) send_selector (
        .candidates_i(send_candidates),.first_valid_o(unlocked_send_found),.first_index_o(unlocked_send_index),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) local_selector (
        .candidates_i(local_candidates),.first_valid_o(local_fill_found),.first_index_o(local_fill_index),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) matching_selector (
        .candidates_i(matching_candidates),.first_valid_o(matching_found),.first_index_o(matching_index),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_free_selector (
        .candidates_i(waiter_free_candidates),.first_valid_o(waiter_free_found),.first_index_o(waiter_free_index),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_load_selector (
        .candidates_i(waiter_load_candidates),.first_valid_o(waiter_load_ready_found),.first_index_o(waiter_load_ready_index),
        .second_valid_o(),.second_index_o());
    rv32_frequency_first_two #(.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_store_selector (
        .candidates_i(waiter_store_candidates),.first_valid_o(waiter_store_ready_found),.first_index_o(waiter_store_ready_index),
        .second_valid_o(),.second_index_o());
    assign send_found=send_locked || unlocked_send_found;
    assign send_index=send_locked?send_locked_index:unlocked_send_index;
    assign any_mshr=|live_candidates;
    assign store_mshr_present=|store_candidates;
    assign matching_prefetch=matching_found && mshr_prefetch[matching_index];
    assign prefetch_line_present=|prefetch_present_candidates;
    assign request_index_conflict=|request_conflict_candidates;
    assign prefetch_index_conflict=|prefetch_conflict_candidates;
    always @* begin
        response_index=mem_resp_id_i;
        response_found=(response_index>=0) && (response_index<MSHR_ENTRIES) &&
            mshr_valid[response_index] && mshr_sent[response_index];
    end
'''


def cache(t):
    for field in ['free_index','second_free_index','send_index','matching_index']:
        t=change(t,'    integer '+field+';','    wire [2:0] '+field+';')
    t=change(t,'    integer local_fill_index;','    wire [2:0] local_fill_index;')
    for field in ['waiter_free_index','waiter_load_ready_index','waiter_store_ready_index']:
        t=change(t,'    integer '+field+';','    wire [WAITER_SLOT_WIDTH-1:0] '+field+';')
    for field in ['free_found','second_free_found','send_found','local_fill_found','any_mshr','store_mshr_present',
                  'matching_found','matching_prefetch','prefetch_line_present','request_index_conflict',
                  'prefetch_index_conflict','waiter_free_found','waiter_load_ready_found','waiter_store_ready_found']:
        t=change(t,'    reg '+field+';','    wire '+field+';')
    start=t.index('    always @* begin\n        free_found =')
    stop=t.index('\n    assign request_is_store',start)
    return t[:start]+SELECTORS+t[stop:]


if __name__=='__main__':
    prepare('BE_balanced_cache_priority',ROOT/'BD_dedicated_target_and_address_adders',{
        'rtl/cache/rv32_dcache_nonblocking.v':cache,
        'rtl/common/rv32_asap7_fanout.v':lambda t:t+PRIORITY,
    },'BD plus concurrent first/two-first binary priority merge for MSHR and waiter selection, per-row candidates and reduction flags; preserve lowest-index priority, second-free order, send lock identity and accepted response qualification; bounded indices, no new FF/cycles and no EDA')
