"""Row-local Dcache MSHR lifecycle with original NBA order; no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    localparam integer MSHR_LIFECYCLE_WIDTH=31;
    wire [MSHR_PAYLOAD_DOMAINS*MSHR_LIFECYCLE_WIDTH-1:0] mshr_lifecycle_views;
    rv32_frequency_control_tree #(.WIDTH(MSHR_LIFECYCLE_WIDTH),.LEAVES(MSHR_PAYLOAD_DOMAINS)) mshr_lifecycle_tree (
        .signal_i({reset_i,static_request_action,free_index[2:0],matching_index[2:0],second_free_index[2:0],
            static_prefetch_allocate,request_is_store,(request_victim_valid && request_victim_dirty),
            (mem_req_valid_o && !mem_req_write_o),send_index[2:0],(mem_req_valid_o && mem_req_ready_i),
            local_array_write,local_fill_index[2:0],(mem_resp_valid_i && mem_resp_ready_o),response_index[2:0],
            (!mem_resp_error_i && response_matches)}),.views_o(mshr_lifecycle_views));
    genvar lifecycle_mshr;
    generate for(lifecycle_mshr=0;lifecycle_mshr<MSHR_ENTRIES;lifecycle_mshr=lifecycle_mshr+1) begin:g_mshr_lifecycle
        wire local_reset,prefetch_allocate,request_store,dirty_victim,rfo_offer,send_accept,local_fill,response_accept,response_success;
        wire [3:0] action;
        wire [2:0] free_slot,matching_slot,second_slot,send_slot,local_slot,response_slot;
        assign {local_reset,action,free_slot,matching_slot,second_slot,prefetch_allocate,request_store,dirty_victim,
                rfo_offer,send_slot,send_accept,local_fill,local_slot,response_accept,response_slot,response_success}=
            mshr_lifecycle_views[(lifecycle_mshr/4)*MSHR_LIFECYCLE_WIDTH +: MSHR_LIFECYCLE_WIDTH];
        wire load_promote=action==4'd4 && matching_slot==lifecycle_mshr;
        wire store_promote=action==4'd6 && matching_slot==lifecycle_mshr;
        wire demand_allocate=action==4'd8 && free_slot==lifecycle_mshr;
        wire prefetch_new=prefetch_allocate && second_slot==lifecycle_mshr;
        wire accept_response=response_accept && response_slot==lifecycle_mshr;
        always @(posedge clk_i) begin
            if(local_reset) begin
                mshr_valid[lifecycle_mshr]<=1'b0;
                mshr_sent[lifecycle_mshr]<=1'b0;
                mshr_store[lifecycle_mshr]<=1'b0;
                mshr_prefetch[lifecycle_mshr]<=1'b0;
                mshr_writeback[lifecycle_mshr]<=1'b0;
                mshr_merge_delay[lifecycle_mshr]<=0;
                mshr_rfo_offered[lifecycle_mshr]<=1'b0;
            end else begin
                if(mshr_valid[lifecycle_mshr] && mshr_merge_delay[lifecycle_mshr]!=0)
                    mshr_merge_delay[lifecycle_mshr]<=mshr_merge_delay[lifecycle_mshr]-1'b1;
                if(rfo_offer && send_slot==lifecycle_mshr) mshr_rfo_offered[lifecycle_mshr]<=1'b1;
                if(load_promote) mshr_prefetch[lifecycle_mshr]<=1'b0;
                if(store_promote) begin
                    mshr_store[lifecycle_mshr]<=1'b1;
                    mshr_prefetch[lifecycle_mshr]<=1'b0;
                    mshr_merge_delay[lifecycle_mshr]<=MERGE_DELAY;
                end
                if(demand_allocate) begin
                    mshr_valid[lifecycle_mshr]<=1'b1;
                    mshr_sent[lifecycle_mshr]<=1'b0;
                    mshr_rfo_offered[lifecycle_mshr]<=1'b0;
                    mshr_merge_delay[lifecycle_mshr]<=request_store?MERGE_DELAY:0;
                    mshr_store[lifecycle_mshr]<=request_store;
                    mshr_prefetch[lifecycle_mshr]<=1'b0;
                    mshr_writeback[lifecycle_mshr]<=dirty_victim;
                end
                if(prefetch_new) begin
                    mshr_valid[lifecycle_mshr]<=1'b1;
                    mshr_sent[lifecycle_mshr]<=1'b0;
                    mshr_rfo_offered[lifecycle_mshr]<=1'b0;
                    mshr_merge_delay[lifecycle_mshr]<=0;
                    mshr_store[lifecycle_mshr]<=1'b0;
                    mshr_prefetch[lifecycle_mshr]<=1'b1;
                    mshr_writeback[lifecycle_mshr]<=1'b0;
                end
                if(send_accept && send_slot==lifecycle_mshr) mshr_sent[lifecycle_mshr]<=1'b1;
                if(local_fill && local_slot==lifecycle_mshr) mshr_valid[lifecycle_mshr]<=1'b0;
                // Accepted memory response is the last original writer. A
                // successful victim writeback retains its demand transaction.
                if(accept_response) begin
                    mshr_sent[lifecycle_mshr]<=1'b0;
                    if(mshr_writeback[lifecycle_mshr] && response_success)
                        mshr_writeback[lifecycle_mshr]<=1'b0;
                    else mshr_valid[lifecycle_mshr]<=1'b0;
                end
            end
        end
    end endgenerate
'''


def lifecycle(t):
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            resp_valid_reg')
    stop=t.index('\n    initial begin',start)
    commands=t[start:stop]
    # Keep legacy data reset when its implementation is requested.
    a=commands.index('            for (reset_index = 0; reset_index < MSHR_ENTRIES;')
    b=commands.index('            end\n',a)+len('            end\n')
    commands=commands[:a]+'''            if(STATIC_UPDATES==0)
                for(reset_index=0;reset_index<MSHR_ENTRIES;reset_index=reset_index+1)
                    legacy_mshr_wdata[reset_index]<=128'b0;
'''+commands[b:]
    commands=change(commands,'''            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1)
                if (mshr_valid[reset_index] && mshr_merge_delay[reset_index] != 0)
                    mshr_merge_delay[reset_index] <= mshr_merge_delay[reset_index] - 1'b1;
''','')
    commands=change(commands,'''                if (!mem_req_write_o)
                    mshr_rfo_offered[send_index] <= 1'b1;
''','')
    commands=change(commands,'''            if (mem_req_valid_o && mem_req_ready_i)
                mshr_sent[send_index] <= 1'b1;
''','')
    for field in ['mshr_valid','mshr_sent','mshr_store','mshr_prefetch','mshr_writeback','mshr_merge_delay','mshr_rfo_offered']:
        commands,n=re.subn(r'^ +'+field+r'\[[^\n]*?\]\s*<=\s*[^;]*;\n','',commands,flags=re.M)
        if re.search(r'^ +'+field+r'\[[^\]\n]*\]\s*<=',commands,flags=re.M):
            raise ValueError('Residual lifecycle write '+field)
    # The merged line temporary lost its only consumers when waiter owners
    # acquired the fill. The owners compute the same old-state merged line.
    commands=change(commands,'''                    updated_line = merge_store(mem_resp_data_i,
                                               mshr_wdata[response_index],
                                               mshr_mask[response_index]);
''','')
    t=change(t,'    integer waiter_index;\n    reg [127:0] updated_line;\n','')
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            resp_valid_reg')
    stop=t.index('\n    initial begin',start)
    return t[:start]+OWNERS+'\n'+commands+t[stop:]


if __name__=='__main__':
    prepare('BB_dcache_mshr_local_lifecycle',ROOT/'BA_dcache_waiter_row_owners',
            {'rtl/cache/rv32_dcache_nonblocking.v':lifecycle},
            'BA plus Dcache MSHR row-owned valid/sent/store/prefetch/writeback/RFO-offered/merge-delay lifecycle, bounded distributed event tuple; preserve decrement<offer<promote<demand<prefetch<send<localfill<memory-response NBA order and legacy payload branch; no added FF/cycles and no EDA')
