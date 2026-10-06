"""Prepare an untested source candidate from measured CD1 Dcache fanout."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def dcache(source):
    source=change(source,'''        // These modules own the actual state and its address-qualified write
        // logic. No extra cycle, buffer-cell stub or replacement SRAM is used.''','''        // The CD1 mapped victim-way driver fed 1255 pins. A bank-local
        // decode does not bound the shared input's load across 64 banks.
        // Distribute every metadata input after its final qualification;
        // each leaf feeds exactly one existing state owner on the same edge.
        localparam integer METADATA_INPUT_WIDTH=9+5*CACHE_ENTRY_WIDTH+4*CACHE_INDEX_WIDTH;
        wire [GROUP_COUNT*METADATA_INPUT_WIDTH-1:0] metadata_input_views;
        rv32_frequency_control_tree #(.WIDTH(METADATA_INPUT_WIDTH),.LEAVES(GROUP_COUNT)) metadata_input_tree (
            .signal_i({static_request_action,refill_array_write,refill_entry,query_response_mshr_store,
                       local_array_write,local_entry,request_victim_entry,
                       static_prefetch_allocate,prefetch_victim_entry,request_hit_entry,
                       request_index,prefetch_index,dcache_req_valid_i && dcache_req_ready_o,
                       cache_index(dcache_req_addr_i),
                       cache_index({dcache_req_addr_i[31:4],4'b0}+32'd16)}),
            .views_o(metadata_input_views));
        // These modules own the actual state and its address-qualified write
        // logic. No extra cycle, buffer-cell stub or replacement SRAM is used.''')
    source=change(source,'''        for (update_group = 0; update_group < GROUP_COUNT; update_group = update_group + 1) begin : g_metadata
            rv32_dcache_metadata_bank #(''','''        for (update_group = 0; update_group < GROUP_COUNT; update_group = update_group + 1) begin : g_metadata
            wire [3:0] metadata_action;
            wire metadata_refill,metadata_refill_dirty,metadata_local,metadata_prefetch,metadata_query_fire;
            wire [CACHE_ENTRY_WIDTH-1:0] metadata_refill_entry,metadata_local_entry,
                metadata_miss_entry,metadata_prefetch_entry,metadata_hit_entry;
            wire [CACHE_INDEX_WIDTH-1:0] metadata_request_set,metadata_prefetch_set,
                metadata_query_request_set,metadata_query_prefetch_set;
            assign {metadata_action,metadata_refill,metadata_refill_entry,metadata_refill_dirty,
                    metadata_local,metadata_local_entry,metadata_miss_entry,
                    metadata_prefetch,metadata_prefetch_entry,metadata_hit_entry,
                    metadata_request_set,metadata_prefetch_set,metadata_query_fire,
                    metadata_query_request_set,metadata_query_prefetch_set}=
                metadata_input_views[update_group*METADATA_INPUT_WIDTH +: METADATA_INPUT_WIDTH];
            rv32_dcache_metadata_bank #(''')
    return change(source,'''                .request_action_i(static_request_action),
                .refill_valid_i(refill_array_write), .refill_entry_i(refill_entry),
                .refill_dirty_i(query_response_mshr_store),
                .local_valid_i(local_array_write), .local_entry_i(local_entry),
                .miss_valid_i(static_request_action == 4'd8), .miss_entry_i(request_victim_entry),
                .prefetch_valid_i(static_prefetch_allocate), .prefetch_entry_i(prefetch_victim_entry),
                .store_hit_i(static_request_action == 4'd2), .hit_entry_i(request_hit_entry),
                .hit_valid_i(static_request_action == 4'd1 || static_request_action == 4'd2),
                .request_set_i(request_index), .prefetch_set_i(prefetch_index),
                .query_fire_i(dcache_req_valid_i && dcache_req_ready_o),
                .query_request_set_i(cache_index(dcache_req_addr_i)),
                .query_prefetch_set_i(cache_index({dcache_req_addr_i[31:4],4'b0} + 32'd16)),''','''                .request_action_i(metadata_action),
                .refill_valid_i(metadata_refill), .refill_entry_i(metadata_refill_entry),
                .refill_dirty_i(metadata_refill_dirty),
                .local_valid_i(metadata_local), .local_entry_i(metadata_local_entry),
                .miss_valid_i(metadata_action == 4'd8), .miss_entry_i(metadata_miss_entry),
                .prefetch_valid_i(metadata_prefetch), .prefetch_entry_i(metadata_prefetch_entry),
                .store_hit_i(metadata_action == 4'd2), .hit_entry_i(metadata_hit_entry),
                .hit_valid_i(metadata_action == 4'd1 || metadata_action == 4'd2),
                .request_set_i(metadata_request_set), .prefetch_set_i(metadata_prefetch_set),
                .query_fire_i(metadata_query_fire),
                .query_request_set_i(metadata_query_request_set),
                .query_prefetch_set_i(metadata_query_prefetch_set),''')


if __name__=='__main__':
    prepare('CE_dcache_metadata_input_distribution',ROOT/'CD1_sv_identifier_repair',{
        'rtl/cache/rv32_dcache_nonblocking.v':dcache,
    },'CD1 measured 99.659367 MHz: victim-way AOI31 drives 1255 pins /572.3894fF, 6.6391ns gate delay plus downstream slew delay; bounded ordinary RTL inversion tree distributes all final-qualified metadata ports to their existing bank owners. Same state, priority, edge, cache parameters, SRAM/constraints and protocol. No EDA/simulation started; candidate remains separate from frozen CD1.')
