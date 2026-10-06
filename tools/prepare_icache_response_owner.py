"""Prepare one final Icache response-data write owner; no hardware tools."""
from prepare_staged_frequency_candidate import change,prepare,ROOT

def response_owner(t):
    insert='''    // Preserve the old NBA priority: a live memory response overwrites
    // copying the previous SRAM response. Invalid payload need not reset.
    wire response_promoted=request_fire && request_match_found && request_match_index==response_index;
    wire response_memory_write=!reset_i && mem_resp_valid_i && mem_resp_ready_o && response_target_found &&
        ((response_promoted && lookup_req_epoch==current_epoch_i) ||
         (!response_promoted && !mshr_prefetch[response_index] && mshr_demand_epoch[response_index]==current_epoch_i));
    wire response_sram_copy=!reset_i && resp_from_sram && resp_valid_reg;
    wire [3:0] response_data_write,response_data_memory;
    rv32_frequency_control_tree #(.LEAVES(4)) response_write_tree (
        .signal_i(response_memory_write || response_sram_copy),.views_o(response_data_write));
    rv32_frequency_control_tree #(.LEAVES(4)) response_select_tree (
        .signal_i(response_memory_write),.views_o(response_data_memory));
    genvar response_word;
    generate for(response_word=0;response_word<4;response_word=response_word+1) begin:g_response_data
        always @(posedge clk_i) if(response_data_write[response_word])
            resp_data_reg[response_word*32 +: 32]<=response_data_memory[response_word]?
                mem_resp_data_i[response_word*32 +: 32]:data_rdata[response_word*32 +: 32];
    end endgenerate

'''
    t=change(t,'    integer reset_index;\n',insert+'    integer reset_index;\n')
    t=change(t,"            resp_data_reg <= 128'd0;\n",'')
    t=change(t,'            if (resp_from_sram && resp_valid_reg)\n                resp_data_reg <= data_rdata;\n','')
    line='                        resp_data_reg <= mem_resp_data_i;\n'
    t=change(t,line,'')
    t=change(t,'                    resp_data_reg <= mem_resp_data_i;\n','')
    return t

if __name__=='__main__':
    prepare('Q_icache_response_data_owner',ROOT/'P_local_prf_storage',
            {'rtl/cache/rv32_icache_nonblocking.v':response_owner},
            'Separate untested alternative: P plus one Icache response-data owner with final qualified local word write/select drivers, unchanged SRAM-copy/refill priority and no new latency')
