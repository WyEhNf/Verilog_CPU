"""Remove unused distribution fields without changing metadata behavior."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def dcache(source):
    source=change(source,'        localparam integer METADATA_INPUT_WIDTH=9+5*CACHE_ENTRY_WIDTH+4*CACHE_INDEX_WIDTH;','''        // Local-query owners already latched set/row identities. They
        // consume only way bits of miss/prefetch/hit entries and never use
        // the non-query request/prefetch set ports. Preserve full fields in
        // the legacy query mode; current 1/2-way mode needs one way bit.
        localparam integer METADATA_SELECT_WIDTH=LOCAL_METADATA_ACTIVE ? 1:CACHE_ENTRY_WIDTH;
        localparam integer METADATA_SET_WIDTH=LOCAL_METADATA_ACTIVE ? 1:CACHE_INDEX_WIDTH;
        localparam integer METADATA_INPUT_WIDTH=9+2*CACHE_ENTRY_WIDTH+3*METADATA_SELECT_WIDTH+
            2*METADATA_SET_WIDTH+2*CACHE_INDEX_WIDTH;''')
    source=change(source,'''                       local_array_write,local_entry,request_victim_entry,
                       static_prefetch_allocate,prefetch_victim_entry,request_hit_entry,
                       request_index,prefetch_index,dcache_req_valid_i && dcache_req_ready_o,''','''                       local_array_write,local_entry,request_victim_entry[METADATA_SELECT_WIDTH-1:0],
                       static_prefetch_allocate,prefetch_victim_entry[METADATA_SELECT_WIDTH-1:0],
                       request_hit_entry[METADATA_SELECT_WIDTH-1:0],
                       (LOCAL_METADATA_ACTIVE ? {METADATA_SET_WIDTH{1'b0}}:request_index[METADATA_SET_WIDTH-1:0]),
                       (LOCAL_METADATA_ACTIVE ? {METADATA_SET_WIDTH{1'b0}}:prefetch_index[METADATA_SET_WIDTH-1:0]),
                       dcache_req_valid_i && dcache_req_ready_o,''')
    source=change(source,'''            wire [CACHE_INDEX_WIDTH-1:0] metadata_request_set,metadata_prefetch_set,
                metadata_query_request_set,metadata_query_prefetch_set;
            assign {metadata_action,metadata_refill,metadata_refill_entry,metadata_refill_dirty,''','''            wire [CACHE_INDEX_WIDTH-1:0] metadata_request_set,metadata_prefetch_set,
                metadata_query_request_set,metadata_query_prefetch_set;
            wire [METADATA_SELECT_WIDTH-1:0] metadata_miss_select,metadata_prefetch_select,metadata_hit_select;
            wire [METADATA_SET_WIDTH-1:0] metadata_request_set_field,metadata_prefetch_set_field;
            assign metadata_miss_entry={{(CACHE_ENTRY_WIDTH-METADATA_SELECT_WIDTH){1'b0}},metadata_miss_select};
            assign metadata_prefetch_entry={{(CACHE_ENTRY_WIDTH-METADATA_SELECT_WIDTH){1'b0}},metadata_prefetch_select};
            assign metadata_hit_entry={{(CACHE_ENTRY_WIDTH-METADATA_SELECT_WIDTH){1'b0}},metadata_hit_select};
            assign metadata_request_set={{(CACHE_INDEX_WIDTH-METADATA_SET_WIDTH){1'b0}},metadata_request_set_field};
            assign metadata_prefetch_set={{(CACHE_INDEX_WIDTH-METADATA_SET_WIDTH){1'b0}},metadata_prefetch_set_field};
            assign {metadata_action,metadata_refill,metadata_refill_entry,metadata_refill_dirty,''')
    return change(source,'''                    metadata_local,metadata_local_entry,metadata_miss_entry,
                    metadata_prefetch,metadata_prefetch_entry,metadata_hit_entry,
                    metadata_request_set,metadata_prefetch_set,metadata_query_fire,''','''                    metadata_local,metadata_local_entry,metadata_miss_select,
                    metadata_prefetch,metadata_prefetch_select,metadata_hit_select,
                    metadata_request_set_field,metadata_prefetch_set_field,metadata_query_fire,''')


if __name__=='__main__':
    prepare('CF_dcache_compact_metadata_distribution',ROOT/'CE_dcache_metadata_input_distribution',{
        'rtl/cache/rv32_dcache_nonblocking.v':dcache,
    },'CE plus parameter-aware metadata distribution: local query uses low way bit for miss/prefetch/hit and ignores non-query set ports; distribute current 52-bit packet instead of 95 bits. Full refill/local entries and captured query sets retained; full old-mode fields restored by constant parameters, allowed ways1/2 unchanged. No FF/edge/priority/SRAM/protocol changes, no EDA/simulation, independent unadopted candidate.')
