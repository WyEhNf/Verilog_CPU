"""Own retained SRAM queries and sixteen-bit lookup routing; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


INPUT_OWNER = r'''        localparam integer INPUT_PAYLOAD_WIDTH=181+2*TAG_WIDTH;
        wire [INPUT_PAYLOAD_WIDTH-1:0] input_payload_saved;
        rv32_frequency_word_bank #(.WIDTH(INPUT_PAYLOAD_WIDTH)) query_input_owner (
            .clk_i(clk_i),.write_i(input_fire),
            .data_i({dcache_req_rob_tag_i,dcache_req_lsq_tag_i,dcache_req_wdata_i,dcache_req_mask_i,dcache_req_addr_i,
                     dcache_req_is_load_i,dcache_req_is_store_i,dcache_req_size_i,dcache_req_unsigned_i}),
            .data_o(input_payload_saved));
        assign {query_rob,query_lsq,query_wdata,query_mask,query_addr,query_load,query_store,query_size,query_unsigned}=input_payload_saved;
        if(REGISTERED_INDEX!=0) begin:g_query_indices
            wire [2*CACHE_INDEX_WIDTH-1:0] saved_indices;
            rv32_frequency_word_bank #(.WIDTH(2*CACHE_INDEX_WIDTH)) index_owner (
                .clk_i(clk_i),.write_i(input_fire),
                .data_i({cache_index(dcache_req_addr_i),cache_index(input_prefetch_line)}),.data_o(saved_indices));
            assign {query_request_index,query_prefetch_index}=saved_indices;
        end else begin:g_combinational_query_indices
            // These fields have no consumers in the combinational-index mode.
            assign query_request_index=0;
            assign query_prefetch_index=0;
        end
'''


LOOKUP = r'''        localparam integer LOOKUP_TAG_WORDS=(CACHE_WAYS*CACHE_TAG_WIDTH+15)/16;
        localparam integer LOOKUP_DATA_WORDS=8*CACHE_WAYS;
        localparam integer LOOKUP_WORDS=2*LOOKUP_TAG_WORDS+LOOKUP_DATA_WORDS;
        wire [2*LOOKUP_WORDS-1:0] lookup_read_views;
        rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(LOOKUP_WORDS)) lookup_read_tree (
            .signal_i({query_data_from_sram,query_from_sram}),.views_o(lookup_read_views));
        genvar lookup_word;
        for(lookup_word=0;lookup_word<LOOKUP_TAG_WORDS;lookup_word=lookup_word+1) begin:g_lookup_tag_word
            localparam integer LOW=lookup_word*16;
            localparam integer BITS=(CACHE_WAYS*CACHE_TAG_WIDTH-LOW>=16)?16:CACHE_WAYS*CACHE_TAG_WIDTH-LOW;
            assign request_tags[LOW +: BITS]=lookup_read_views[2*lookup_word]?
                demand_rdata[LOW +: BITS]:demand_hold[LOW +: BITS];
            assign prefetch_tags[LOW +: BITS]=lookup_read_views[2*(LOOKUP_TAG_WORDS+lookup_word)]?
                prefetch_rdata[LOW +: BITS]:prefetch_hold[LOW +: BITS];
        end
        for(lookup_word=0;lookup_word<LOOKUP_DATA_WORDS;lookup_word=lookup_word+1) begin:g_lookup_data_word
            assign request_data_ways[lookup_word*16 +: 16]=lookup_read_views[2*(2*LOOKUP_TAG_WORDS+lookup_word)+1]?
                bank_rdata[lookup_word*16 +: 16]:bank_hold[lookup_word*16 +: 16];
        end
        wire [3*CACHE_WAYS-1:0] hold_event_views;
        rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(CACHE_WAYS)) hold_event_tree (
            .signal_i({reset_i,query_data_from_sram,query_from_sram}),.views_o(hold_event_views));
        genvar hold_way;
        for(hold_way=0;hold_way<CACHE_WAYS;hold_way=hold_way+1) begin:g_lookup_hold_owner
            wire local_reset,data_copy,tag_copy;
            assign {local_reset,data_copy,tag_copy}=hold_event_views[hold_way*3 +: 3];
            wire bank_forward=!local_reset && data_we && query_valid &&
                data_addr/CACHE_WAYS==core_request_index && data_addr%CACHE_WAYS==hold_way;
            wire tag_forward=!local_reset && tag_array_write && query_valid && tag_write_mask[hold_way];
            wire demand_forward=tag_forward && tag_write_set==core_request_index;
            wire prefetch_forward=tag_forward && tag_write_set==core_prefetch_index;
            wire demand_write,prefetch_write,data_write;
            wire [CACHE_TAG_WIDTH-1:0] demand_next,prefetch_next;
            wire [127:0] data_next;
            rv32_frequency_event_select #(.WIDTH(CACHE_TAG_WIDTH),.EVENTS(2)) demand_selector (
                .events_i({demand_forward,!local_reset && tag_copy}),
                .values_i({tag_write_value,demand_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]}),
                .write_o(demand_write),.value_o(demand_next));
            rv32_frequency_word_bank #(.WIDTH(CACHE_TAG_WIDTH)) demand_owner (
                .clk_i(clk_i),.write_i(demand_write),.data_i(demand_next),.data_o(demand_hold[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
            rv32_frequency_event_select #(.WIDTH(CACHE_TAG_WIDTH),.EVENTS(2)) prefetch_selector (
                .events_i({prefetch_forward,!local_reset && tag_copy}),
                .values_i({tag_write_value,prefetch_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]}),
                .write_o(prefetch_write),.value_o(prefetch_next));
            rv32_frequency_word_bank #(.WIDTH(CACHE_TAG_WIDTH)) prefetch_owner (
                .clk_i(clk_i),.write_i(prefetch_write),.data_i(prefetch_next),.data_o(prefetch_hold[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
            rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) data_selector (
                .events_i({bank_forward,!local_reset && data_copy}),
                .values_i({merge_store(request_data_ways[hold_way*128 +: 128],data_wdata,data_wmask),bank_rdata[hold_way*128 +: 128]}),
                .write_o(data_write),.value_o(data_next));
            rv32_frequency_word_bank #(.WIDTH(128)) data_owner (
                .clk_i(clk_i),.write_i(data_write),.data_i(data_next),.data_o(bank_hold[hold_way*128 +: 128]));
        end
'''


def query(t):
    declarations=['query_load, query_store, query_unsigned','[31:0] query_addr',
                  '[CACHE_INDEX_WIDTH-1:0] query_request_index, query_prefetch_index',
                  '[1:0] query_size','[15:0] query_mask','[127:0] query_wdata',
                  '[TAG_WIDTH-1:0] query_rob, query_lsq',
                  '[(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] demand_hold, prefetch_hold',
                  '[CACHE_WAYS*128-1:0] bank_hold']
    for declaration in declarations:
        t=change(t,'        reg '+declaration+';','        wire '+declaration+';')
    a=t.index('        wire [8:0] query_write_views;')
    b=t.index('        assign dcache_req_ready_o',a)
    t=t[:a]+INPUT_OWNER+t[b:]
    a=t.index('        assign request_tags = query_from_sram ?')
    b=t.index('        assign request_data_ready = query_data_valid;',a)
    t=t[:a]+LOOKUP+t[b:]
    a=t.index('                if (query_from_sram) begin\n                    demand_hold <=')
    b=t.index('                if (core_req_valid && core_req_ready)',a)
    t=t[:a]+'''                // Payload owners preserve copy<forward ordering independently
                // of the scalar query-valid and deferred-read state below.
'''+t[b:]
    t=change(t,'''        assign data_rdata = request_data_ways[(request_data_entry % CACHE_WAYS)*128 +: 128];''',r'''        localparam integer DATA_WAY_WIDTH=(CACHE_WAYS<=1)?1:$clog2(CACHE_WAYS);
        wire [DATA_WAY_WIDTH-1:0] selected_way=request_data_entry%CACHE_WAYS;
        rv32_frequency_array_read #(.WIDTH(128),.ENTRIES(CACHE_WAYS),.INDEX_WIDTH(DATA_WAY_WIDTH)) data_way_reader (
            .rows_i(request_data_ways),.index_i(selected_way),.value_o(data_rdata));''')
    # The response identity is an eight-bit ID. Feeding its full ID preserves
    # rejection of out-of-range responses and avoids distributing 24 zeros.
    t=change(t,'.INDEX_WIDTH(32)) response_read (\n        .rows_i(mshr_read_rows),.index_i(response_index)',
               '.INDEX_WIDTH(8)) response_read (\n        .rows_i(mshr_read_rows),.index_i(mem_resp_id_i)')
    return t


if __name__=='__main__':
    prepare('BI_dcache_query_and_hold_owners',ROOT/'BH_bounded_backend_recovery_routing',
            {'rtl/cache/rv32_dcache_nonblocking.v':query},
            'BH plus sixteen-bit Dcache input query ownership, row-owned retained SRAM tag/data copy<forward events and bounded held/live lookup and data-way selection; preserve deferred read, same-edge byte merge/tag forwarding, no payload reset/extra FF/cycles; full eight-bit memory response ID query without aliasing, no EDA')
