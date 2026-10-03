"""Prepare a frequency/IPC tradeoff alternative; no EDA or simulation."""
from prepare_staged_frequency_candidate import change,prepare,ROOT

def empty_bypass(t):
    t=change(t,'    parameter integer REQUEST_PIPELINE = 0,',
             '    parameter integer REQUEST_PIPELINE = 0,\n    parameter integer REQUEST_EMPTY_BYPASS = 0,')
    t=change(t,'rv32_icache_query_queue #(.EPOCH_WIDTH(EPOCH_WIDTH)) requests (',
             'rv32_icache_query_queue #(.EPOCH_WIDTH(EPOCH_WIDTH),.EMPTY_BYPASS(REQUEST_EMPTY_BYPASS)) requests (')
    t=change(t,'module rv32_icache_query_queue #(parameter integer EPOCH_WIDTH=4) (',
             'module rv32_icache_query_queue #(parameter integer EPOCH_WIDTH=4,EMPTY_BYPASS=0) (')
    t=change(t,'''    assign {pc_o,epoch_o}=read_local?payload[1]:payload[0];
    wire stale=count!=0 && epoch_o!=current_epoch_i;
    assign ready_o=!reset_i && count<2;
    assign valid_o=!reset_i && count!=0 && !stale;
    wire push=valid_i && ready_o;
    wire pop=!reset_i && (stale || (valid_o && ready_i));''', '''    wire [1:0] empty_views;
    rv32_frequency_control_tree #(.LEAVES(2)) empty_tree (
        .signal_i(EMPTY_BYPASS!=0 && count==0),.views_o(empty_views));
    wire [32+EPOCH_WIDTH-1:0] stored_payload=read_local?payload[1]:payload[0];
    assign {pc_o,epoch_o}=empty_views[0]?{pc_i,epoch_i}:stored_payload;
    wire stored_stale=count!=0 && stored_payload[EPOCH_WIDTH-1:0]!=current_epoch_i;
    wire input_stale=epoch_i!=current_epoch_i;
    // Published input ready still uses ONLY registered occupancy. Internal
    // lookup readiness decides whether an accepted input needs to be stored.
    assign ready_o=!reset_i && count<2;
    assign valid_o=!reset_i && (empty_views[1]?(valid_i && !input_stale):(count!=0 && !stored_stale));
    wire direct_consumed=empty_views[1] && valid_o && ready_i;
    wire direct_discarded=empty_views[1] && valid_i && ready_o && input_stale;
    wire push=valid_i && ready_o && !direct_consumed && !direct_discarded;
    wire pop=!reset_i && count!=0 && (stored_stale || (valid_o && ready_i));''')
    return t

def enable_bypass(t):
    return change(t,'.REQUEST_PIPELINE(1),', '.REQUEST_PIPELINE(1), .REQUEST_EMPTY_BYPASS(1),')

if __name__=='__main__':
    prepare('R_icache_empty_bypass_tradeoff',ROOT/'Q_icache_response_data_owner',
            {'rtl/cache/rv32_icache_nonblocking.v':empty_bypass,'rtl/cpu_core.v':enable_bypass},
            'Separate untested tradeoff: Q plus empty-queue direct lookup with occupancy-only published ready and retained stalled requests; may restore warm fetch throughput but reopens predicted-PC forward combinational path, so adopt only after timing evidence')
