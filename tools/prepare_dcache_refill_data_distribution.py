"""Bound Dcache final refill/local data selection in a source-only candidate."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def dcache(source):
    return change(source,'''    assign data_wdata = refill_array_write ?
        (query_response_mshr_store ? merge_store(mem_resp_data_i,
            query_response_mshr_wdata, query_response_mshr_mask) : mem_resp_data_i) :
        local_array_write ? query_local_mshr_wdata : core_req_wdata;''','''    // Metadata distribution alone leaves the shared response-store flag
    // controlling the global 128-bit refill merge/forwarding data mux.
    // Eight local control packets bound every final select to16 data bits.
    wire [23:0] array_data_views;
    rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(8)) array_data_tree (
        .signal_i({refill_array_write,local_array_write,query_response_mshr_store}),
        .views_o(array_data_views));
    generate for(genvar array_word=0;array_word<8;array_word=array_word+1) begin:g_array_write_word
        wire refill_select,local_select,response_store;
        wire [15:0] refill_data;
        assign {refill_select,local_select,response_store}=array_data_views[array_word*3 +: 3];
        for(genvar array_byte=0;array_byte<2;array_byte=array_byte+1) begin:g_refill_byte
            localparam integer BYTE=array_word*2+array_byte;
            assign refill_data[array_byte*8 +: 8]=(response_store && query_response_mshr_mask[BYTE])?
                query_response_mshr_wdata[BYTE*8 +: 8]:mem_resp_data_i[BYTE*8 +: 8];
        end
        assign data_wdata[array_word*16 +: 16]=refill_select?refill_data:
            (local_select?query_local_mshr_wdata[array_word*16 +: 16]:core_req_wdata[array_word*16 +: 16]);
    end endgenerate''')


if __name__=='__main__':
    prepare('CM_dcache_refill_data_distribution',ROOT/'CL_lsq_parallel_recovery_trim',{
        'rtl/cache/rv32_dcache_nonblocking.v':dcache,
    },'CL plus final global Dcache refill/local/response-store data control split into16-bit leaves, preserving per-byte mask and refill>local>request priority. Same packet/data/edge/state/SRAM/latency. Independent source-only candidate, no HDL/EDA/simulation.')
