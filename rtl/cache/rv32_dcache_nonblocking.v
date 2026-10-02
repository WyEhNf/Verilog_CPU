`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Non-blocking, write-back data cache for the performance profiles. Loads use
// independent MSHRs, merge behind an outstanding line, and trigger a clean
// next-line prefetch. A demand that reaches an in-flight prefetch promotes it
// in place so the returned line completes the original LSQ entry.
module rv32_dcache_nonblocking #(
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer MSHR_ENTRIES = 4,
    parameter integer WAITER_ENTRIES = 8,
    parameter integer PREFETCH = 1,
    parameter integer CACHE_LINES = 256,
    parameter integer CACHE_WAYS = 1,
    parameter integer INDEX_HASH = 0,
    parameter integer STORE_MERGE_DELAY = 0,
    parameter integer TAG_SRAM = 0,
    // 0: legacy dynamic writes; 1: flat static enables; 2: functional state banks.
    parameter integer STATIC_UPDATES = 0,
    parameter integer CACHE_SETS = CACHE_LINES / CACHE_WAYS,
    parameter integer CACHE_INDEX_WIDTH = $clog2(CACHE_SETS),
    parameter integer CACHE_TAG_WIDTH = 32 - 4 - CACHE_INDEX_WIDTH
) (
    input  wire                     clk_i,
    input  wire                     reset_i,
    input  wire                     flush_i,
    input  wire                     dcache_req_valid_i,
    output wire                     dcache_req_ready_o,
    input  wire                     dcache_req_is_load_i,
    input  wire                     dcache_req_is_store_i,
    input  wire [31:0]              dcache_req_addr_i,
    input  wire [1:0]               dcache_req_size_i,
    input  wire                     dcache_req_unsigned_i,
    input  wire [15:0]              dcache_req_mask_i,
    input  wire [127:0]             dcache_req_wdata_i,
    input  wire [TAG_WIDTH-1:0]     dcache_req_rob_tag_i,
    input  wire [TAG_WIDTH-1:0]     dcache_req_lsq_tag_i,
    output wire                     dcache_resp_valid_o,
    input  wire                     dcache_resp_ready_i,
    output wire [TAG_WIDTH-1:0]     dcache_resp_lsq_tag_o,
    output wire [31:0]              dcache_resp_addr_o,
    output wire [127:0]             dcache_resp_line_data_o,
    output wire [31:0]              dcache_resp_word_data_o,
    output wire                     dcache_resp_line_valid_o,
    output wire                     dcache_resp_error_o,
    output wire                     dcache_store_ack_valid_o,
    input  wire                     dcache_store_ack_ready_i,
    output wire [TAG_WIDTH-1:0]     dcache_store_ack_lsq_tag_o,
    output wire                     dcache_store_ack_error_o,
    output wire                     mem_req_valid_o,
    input  wire                     mem_req_ready_i,
    output wire                     mem_req_write_o,
    output wire [31:0]              mem_req_line_addr_o,
    output wire [127:0]             mem_req_wdata_o,
    output wire [15:0]              mem_req_wmask_o,
    output wire [7:0]               mem_req_id_o,
    input  wire                     mem_resp_valid_i,
    output wire                     mem_resp_ready_o,
    input  wire [31:0]              mem_resp_line_addr_i,
    input  wire [127:0]             mem_resp_data_i,
    input  wire [7:0]               mem_resp_id_i,
    input  wire                     mem_resp_error_i,
    output reg                      event_request_o,
    output reg                      event_hit_o,
    output reg                      event_miss_o,
    output reg                      event_refill_o,
    output reg                      event_writeback_o,
    output reg                      event_stall_o
);
    // Shared read views have exactly one selected implementation as their
    // owner. Bank outputs must not share a procedural driver with legacy FFs.
    wire [CACHE_LINES-1:0] valid_bits;
    wire [CACHE_LINES-1:0] dirty_bits;
    reg [CACHE_LINES-1:0] legacy_valid_bits;
    reg [CACHE_LINES-1:0] legacy_dirty_bits;
    reg [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];
    wire [CACHE_SETS-1:0] lru_way_mem;
    reg [CACHE_SETS-1:0] legacy_lru_way_mem;
    localparam integer CACHE_ENTRY_WIDTH = $clog2(CACHE_LINES);

    reg mshr_valid [0:MSHR_ENTRIES-1];
    reg mshr_sent [0:MSHR_ENTRIES-1];
    reg mshr_store [0:MSHR_ENTRIES-1];
    reg mshr_prefetch [0:MSHR_ENTRIES-1];
    reg mshr_writeback [0:MSHR_ENTRIES-1];
    localparam integer MERGE_COUNT_WIDTH = (STORE_MERGE_DELAY < 1) ? 1 :
                                          $clog2(STORE_MERGE_DELAY + 1);
    localparam [MERGE_COUNT_WIDTH-1:0] MERGE_DELAY = STORE_MERGE_DELAY;
    reg [MERGE_COUNT_WIDTH-1:0] mshr_merge_delay [0:MSHR_ENTRIES-1];
    // Once a read has been offered, valid must not be withdrawn even if later
    // stores complete its mask. An unoffered fully known line needs no RFO.
    reg mshr_rfo_offered [0:MSHR_ENTRIES-1];
    reg send_locked;
    reg [2:0] send_locked_index;
    reg [31:0] mshr_addr [0:MSHR_ENTRIES-1];
    reg [1:0] mshr_size [0:MSHR_ENTRIES-1];
    reg mshr_unsigned [0:MSHR_ENTRIES-1];
    reg [15:0] mshr_mask [0:MSHR_ENTRIES-1];
    wire [127:0] mshr_wdata [0:MSHR_ENTRIES-1];
    reg [127:0] legacy_mshr_wdata [0:MSHR_ENTRIES-1];
    reg [TAG_WIDTH-1:0] mshr_lsq [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_victim_addr [0:MSHR_ENTRIES-1];
    reg [127:0] mshr_victim_data [0:MSHR_ENTRIES-1];
    reg [CACHE_ENTRY_WIDTH-1:0] mshr_victim_entry [0:MSHR_ENTRIES-1];

    // Secondary misses to an already outstanding demand line are accepted
    // here.  Keeping the returned line with each waiter lets refills retire
    // independently even if the direct-mapped cache slot is replaced later.
    reg waiter_valid [0:WAITER_ENTRIES-1];
    reg waiter_ready [0:WAITER_ENTRIES-1];
    reg waiter_store [0:WAITER_ENTRIES-1];
    reg [2:0] waiter_mshr [0:WAITER_ENTRIES-1];
    reg [31:0] waiter_addr [0:WAITER_ENTRIES-1];
    reg [1:0] waiter_size [0:WAITER_ENTRIES-1];
    reg waiter_unsigned [0:WAITER_ENTRIES-1];
    reg [TAG_WIDTH-1:0] waiter_lsq [0:WAITER_ENTRIES-1];
    reg [127:0] waiter_line [0:WAITER_ENTRIES-1];
    reg waiter_error [0:WAITER_ENTRIES-1];

    reg resp_valid_reg;
    reg [TAG_WIDTH-1:0] resp_lsq_reg;
    reg [31:0] resp_addr_reg;
    reg [127:0] resp_line_reg;
    reg [31:0] resp_word_reg;
    reg resp_line_valid_reg;
    reg resp_error_reg;
    // The synchronous SRAM result and hit metadata become valid together.
    // Capture the result on the following edge before the macro can make its
    // output undefined during an idle/write cycle or a backpressured response.
    reg resp_from_sram;
    reg [1:0] resp_size_reg;
    reg resp_unsigned_reg;
    reg victim_from_sram;
    reg [2:0] victim_mshr_reg;
    wire [127:0] data_rdata;
    reg ack_valid_reg;
    reg [TAG_WIDTH-1:0] ack_lsq_reg;
    reg ack_error_reg;

    // Keep the original high address tag. XOR index folding is reversible
    // given that tag, so dirty victims retain their exact physical address.
    function [CACHE_INDEX_WIDTH-1:0] cache_index;
        input [31:0] address;
        begin
            cache_index = address >> 4;
            if (INDEX_HASH != 0)
                cache_index = cache_index ^ (address >> (CACHE_INDEX_WIDTH + 4));
        end
    endfunction

    function [31:0] victim_line_address;
        input [CACHE_TAG_WIDTH-1:0] tag;
        input [CACHE_INDEX_WIDTH-1:0] index;
        reg [CACHE_INDEX_WIDTH-1:0] original_index;
        begin
            original_index = index;
            if (INDEX_HASH != 0) original_index = index ^ tag;
            victim_line_address = {tag, original_index, 4'b0};
        end
    endfunction

    function [CACHE_ENTRY_WIDTH-1:0] cache_entry;
        input [CACHE_INDEX_WIDTH-1:0] set_index;
        input integer way;
        begin
            cache_entry = set_index * CACHE_WAYS + way;
        end
    endfunction

    wire core_req_valid, core_req_ready, core_req_is_load, core_req_is_store;
    wire [31:0] core_req_addr;
    wire [1:0] core_req_size;
    wire core_req_unsigned;
    wire [15:0] core_req_mask;
    wire [127:0] core_req_wdata;
    wire [TAG_WIDTH-1:0] core_req_rob_tag, core_req_lsq_tag;
    wire [(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] request_tags, prefetch_tags;
    integer response_index;
    integer local_fill_index;
    wire refill_array_write, local_array_write;
    wire data_we;
    wire [CACHE_ENTRY_WIDTH-1:0] data_addr;
    wire [127:0] data_wdata;
    wire [15:0] data_wmask;
    wire [CACHE_WAYS*128-1:0] request_data_ways;
    wire request_data_ready;
    wire request_dirty_victim;
    wire tag_array_write = refill_array_write || local_array_write;
    wire [CACHE_ENTRY_WIDTH-1:0] tag_write_entry = local_array_write ?
        mshr_victim_entry[local_fill_index] : mshr_victim_entry[response_index];
    wire [CACHE_INDEX_WIDTH-1:0] tag_write_set = tag_write_entry / CACHE_WAYS;
    wire [CACHE_TAG_WIDTH-1:0] tag_write_value = local_array_write ?
        mshr_addr[local_fill_index][31:CACHE_INDEX_WIDTH+4] :
        mshr_addr[response_index][31:CACHE_INDEX_WIDTH+4];
    wire [CACHE_WAYS-1:0] tag_write_mask = (CACHE_WAYS == 1) ? 1'b1 :
        (2'b01 << tag_write_entry[0]);
    genvar tag_way;
    generate if (TAG_SRAM == 0) begin : g_ff_tags
        assign request_data_ready = 1'b1;
        assign core_req_valid = dcache_req_valid_i;
        assign dcache_req_ready_o = core_req_ready;
        assign core_req_is_load = dcache_req_is_load_i;
        assign core_req_is_store = dcache_req_is_store_i;
        assign core_req_addr = dcache_req_addr_i;
        assign core_req_size = dcache_req_size_i;
        assign core_req_unsigned = dcache_req_unsigned_i;
        assign core_req_mask = dcache_req_mask_i;
        assign core_req_wdata = dcache_req_wdata_i;
        assign core_req_rob_tag = dcache_req_rob_tag_i;
        assign core_req_lsq_tag = dcache_req_lsq_tag_i;
        for (tag_way = 0; tag_way < CACHE_WAYS; tag_way = tag_way + 1) begin : g_way
            assign request_tags[tag_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] =
                tag_mem[cache_entry(cache_index(core_req_addr), tag_way)];
            assign prefetch_tags[tag_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] =
                tag_mem[cache_entry(cache_index({core_req_addr[31:4],4'b0} + 32'd16), tag_way)];
        end
    end else begin : g_sram_tags
        // Two real 1RW copies provide demand + next-line queries; both copies
        // receive every tag write. Each word packs all ways with per-way masks.
        // Read every data way alongside its tags. Post-edge way selection
        // permits a one-cycle load hit without a second data-port access.
        reg query_valid, query_from_sram;
        reg query_data_valid, query_data_from_sram;
        reg query_load, query_store, query_unsigned;
        reg [31:0] query_addr;
        reg [1:0] query_size;
        reg [15:0] query_mask;
        reg [127:0] query_wdata;
        reg [TAG_WIDTH-1:0] query_rob, query_lsq;
        reg [(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] demand_hold, prefetch_hold;
        wire [(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] demand_rdata, prefetch_rdata;
        wire [CACHE_WAYS*128-1:0] bank_rdata;
        reg [CACHE_WAYS*128-1:0] bank_hold;
        wire input_fire = dcache_req_valid_i && dcache_req_ready_o;
        // Store queries need only tags on a hit. Let a following store query
        // share the preceding store's DATA write edge, while tag SRAM reads.
        // If this query instead evicts dirty data, read all ways later before
        // transferring ownership; never capture undefined write/idle rdata.
        wire input_data_read = input_fire && !data_we;
        wire deferred_data_read = query_valid && !query_data_valid &&
            request_dirty_victim && !data_we && !tag_array_write;
        wire [31:0] input_prefetch_line = {dcache_req_addr_i[31:4],4'b0} + 32'd16;
        integer forward_way;
        assign dcache_req_ready_o = !reset_i && !flush_i && !tag_array_write &&
                                   (!data_we || dcache_req_is_store_i) &&
                                   (!query_valid || core_req_ready);
        assign core_req_valid = query_valid;
        assign core_req_is_load = query_load;
        assign core_req_is_store = query_store;
        assign core_req_addr = query_addr;
        assign core_req_size = query_size;
        assign core_req_unsigned = query_unsigned;
        assign core_req_mask = query_mask;
        assign core_req_wdata = query_wdata;
        assign core_req_rob_tag = query_rob;
        assign core_req_lsq_tag = query_lsq;
        assign request_tags = query_from_sram ? demand_rdata : demand_hold;
        assign prefetch_tags = query_from_sram ? prefetch_rdata : prefetch_hold;
        assign request_data_ways = query_data_from_sram ? bank_rdata : bank_hold;
        assign request_data_ready = query_data_valid;
        for (tag_way = 0; tag_way < CACHE_WAYS; tag_way = tag_way + 1) begin : g_data_way
            wire write_way = data_we && ((data_addr % CACHE_WAYS) == tag_way);
            sram_fakeram #(.DEPTH(CACHE_SETS), .WIDTH(128), .WRITE_GRANULARITY(8)) data_bank (
                .clk(clk_i), .en(!reset_i && (write_way || input_data_read || deferred_data_read)),
                .we(write_way), .wmask(data_wmask),
                .addr(write_way ? (data_addr / CACHE_WAYS) :
                    deferred_data_read ? cache_index(query_addr) : cache_index(dcache_req_addr_i)),
                .wdata(data_wdata), .rdata(bank_rdata[tag_way*128 +: 128])
            );
        end
        sram_fakeram #(.DEPTH(CACHE_SETS), .WIDTH(CACHE_WAYS*CACHE_TAG_WIDTH),
                      .WRITE_GRANULARITY(CACHE_TAG_WIDTH)) demand_tags (
            .clk(clk_i), .en(!reset_i && (tag_array_write || input_fire)),
            .we(tag_array_write), .wmask(tag_write_mask),
            .addr(tag_array_write ? tag_write_set : cache_index(dcache_req_addr_i)),
            .wdata({CACHE_WAYS{tag_write_value}}), .rdata(demand_rdata)
        );
        sram_fakeram #(.DEPTH(CACHE_SETS), .WIDTH(CACHE_WAYS*CACHE_TAG_WIDTH),
                      .WRITE_GRANULARITY(CACHE_TAG_WIDTH)) nextline_tags (
            .clk(clk_i), .en(!reset_i && (tag_array_write || input_fire)),
            .we(tag_array_write), .wmask(tag_write_mask),
            .addr(tag_array_write ? tag_write_set : cache_index(input_prefetch_line)),
            .wdata({CACHE_WAYS{tag_write_value}}), .rdata(prefetch_rdata)
        );
        always @(posedge clk_i) begin
            if (reset_i) begin
                query_valid <= 1'b0;
                query_from_sram <= 1'b0;
                query_data_valid <= 1'b0;
                query_data_from_sram <= 1'b0;
            end else begin
                query_from_sram <= input_fire;
                query_data_from_sram <= input_data_read || deferred_data_read;
                if (deferred_data_read) query_data_valid <= 1'b1;
                if (query_from_sram) begin
                    demand_hold <= demand_rdata;
                    prefetch_hold <= prefetch_rdata;
                end
                if (query_data_from_sram) begin
                    bank_hold <= bank_rdata;
                end
                // Keep payload and forwarded tags coherent when a held miss
                // observes a refill/local fill before its query can resolve.
                if (data_we && query_valid &&
                    (data_addr / CACHE_WAYS) == cache_index(query_addr)) begin
                    for (forward_way = 0; forward_way < CACHE_WAYS; forward_way = forward_way + 1)
                        if ((data_addr % CACHE_WAYS) == forward_way)
                            bank_hold[forward_way*128 +: 128] <= merge_store(
                                query_data_from_sram ? bank_rdata[forward_way*128 +: 128] :
                                                 bank_hold[forward_way*128 +: 128],
                                data_wdata, data_wmask);
                end
                // A stalled query can outlive a refill to the queried set.
                // Forward the written way into the saved lookup, not stale
                // tags which could pair an old hit with newly replaced data.
                if (tag_array_write && query_valid) begin
                    for (forward_way = 0; forward_way < CACHE_WAYS; forward_way = forward_way + 1)
                        if (tag_write_mask[forward_way]) begin
                            if (tag_write_set == cache_index(query_addr))
                                demand_hold[forward_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] <= tag_write_value;
                            if (tag_write_set == cache_index({query_addr[31:4],4'b0} + 32'd16))
                                prefetch_hold[forward_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] <= tag_write_value;
                        end
                end
                if (core_req_valid && core_req_ready)
                    query_valid <= 1'b0;
                // flush blocks new inputs but never discards a request whose
                // ownership was accepted earlier (especially a committed SW).
                if (input_fire) begin
                    query_valid <= 1'b1;
                    query_data_valid <= !data_we;
                    query_load <= dcache_req_is_load_i;
                    query_store <= dcache_req_is_store_i;
                    query_addr <= dcache_req_addr_i;
                    query_size <= dcache_req_size_i;
                    query_unsigned <= dcache_req_unsigned_i;
                    query_mask <= dcache_req_mask_i;
                    query_wdata <= dcache_req_wdata_i;
                    query_rob <= dcache_req_rob_tag_i;
                    query_lsq <= dcache_req_lsq_tag_i;
                end
            end
        end
    end endgenerate

    wire [CACHE_INDEX_WIDTH-1:0] request_index = cache_index(core_req_addr);
    wire [CACHE_TAG_WIDTH-1:0] request_tag =
        core_req_addr[31:CACHE_INDEX_WIDTH+4];
    reg request_hit;
    reg [CACHE_ENTRY_WIDTH-1:0] request_hit_entry;
    reg [CACHE_ENTRY_WIDTH-1:0] request_victim_entry;
    // Hit reads and dirty-victim snapshots share the single 1RW data port.
    // Refills have priority; store hits use byte masks without read/modify/write.
    wire [CACHE_ENTRY_WIDTH-1:0] request_data_entry =
        request_hit ? request_hit_entry : request_victim_entry;
    wire resp_slot_free = !resp_valid_reg || dcache_resp_ready_i;
    wire ack_slot_free = !ack_valid_reg || dcache_store_ack_ready_i;

    integer k;
    integer free_index;
    integer second_free_index;
    integer send_index;
    integer matching_index;
    integer waiter_free_index;
    integer waiter_load_ready_index;
    integer waiter_store_ready_index;
    reg free_found;
    reg second_free_found;
    reg send_found;
    reg local_fill_found;
    reg any_mshr;
    reg store_mshr_present;
    reg response_found;
    reg matching_found;
    reg matching_prefetch;
    reg prefetch_line_present;
    reg request_index_conflict;
    reg prefetch_index_conflict;
    reg waiter_free_found;
    reg waiter_load_ready_found;
    reg waiter_store_ready_found;
    wire [31:0] request_line_addr = {core_req_addr[31:4], 4'b0};
    wire [31:0] prefetch_line_addr = request_line_addr + 32'd16;
    wire [CACHE_INDEX_WIDTH-1:0] prefetch_index = cache_index(prefetch_line_addr);
    wire [CACHE_TAG_WIDTH-1:0] prefetch_tag =
        prefetch_line_addr[31:CACHE_INDEX_WIDTH+4];
    reg prefetch_cache_hit;
    reg [CACHE_ENTRY_WIDTH-1:0] prefetch_victim_entry;
    integer way_scan;
    reg request_invalid_found;
    reg prefetch_invalid_found;
    always @* begin
        request_hit = 1'b0;
        prefetch_cache_hit = 1'b0;
        request_hit_entry = cache_entry(request_index, 0);
        request_victim_entry = cache_entry(request_index,
            (CACHE_WAYS == 2) ? lru_way_mem[request_index] : 0);
        prefetch_victim_entry = cache_entry(prefetch_index,
            (CACHE_WAYS == 2) ? lru_way_mem[prefetch_index] : 0);
        request_invalid_found = 1'b0;
        prefetch_invalid_found = 1'b0;
        for (way_scan = 0; way_scan < CACHE_WAYS; way_scan = way_scan + 1) begin
            if (valid_bits[cache_entry(request_index, way_scan)] &&
                (request_tags[way_scan*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] == request_tag)) begin
                request_hit = 1'b1;
                request_hit_entry = cache_entry(request_index, way_scan);
            end
            if (!request_invalid_found &&
                !valid_bits[cache_entry(request_index, way_scan)]) begin
                request_invalid_found = 1'b1;
                request_victim_entry = cache_entry(request_index, way_scan);
            end
            if (valid_bits[cache_entry(prefetch_index, way_scan)] &&
                (prefetch_tags[way_scan*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] == prefetch_tag))
                prefetch_cache_hit = 1'b1;
            if (!prefetch_invalid_found &&
                !valid_bits[cache_entry(prefetch_index, way_scan)]) begin
                prefetch_invalid_found = 1'b1;
                prefetch_victim_entry = cache_entry(prefetch_index, way_scan);
            end
        end
    end
    always @* begin
        free_found = 1'b0;
        free_index = 0;
        second_free_found = 1'b0;
        second_free_index = 0;
        send_found = 1'b0;
        send_index = 0;
        local_fill_found = 1'b0;
        local_fill_index = 0;
        any_mshr = 1'b0;
        store_mshr_present = 1'b0;
        matching_found = 1'b0;
        matching_index = 0;
        matching_prefetch = 1'b0;
        prefetch_line_present = 1'b0;
        request_index_conflict = 1'b0;
        prefetch_index_conflict = 1'b0;
        waiter_free_found = 1'b0;
        waiter_free_index = 0;
        waiter_load_ready_found = 1'b0;
        waiter_load_ready_index = 0;
        waiter_store_ready_found = 1'b0;
        waiter_store_ready_index = 0;
        for (k = 0; k < MSHR_ENTRIES; k = k + 1) begin
            if (mshr_valid[k])
                any_mshr = 1'b1;
            if (mshr_valid[k] && mshr_store[k])
                store_mshr_present = 1'b1;
            if (!free_found && !mshr_valid[k]) begin
                free_found = 1'b1;
                free_index = k;
            end else if (!second_free_found && !mshr_valid[k]) begin
                second_free_found = 1'b1;
                second_free_index = k;
            end
            if (!local_fill_found && STORE_MERGE_DELAY != 0 &&
                mshr_valid[k] && mshr_store[k] && !mshr_sent[k] &&
                !mshr_writeback[k] && !mshr_rfo_offered[k] &&
                mshr_mask[k] == 16'hffff) begin
                local_fill_found = 1'b1;
                local_fill_index = k;
            end
            if (!send_found && mshr_valid[k] && !mshr_sent[k] &&
                (mshr_writeback[k] || !mshr_store[k] ||
                 STORE_MERGE_DELAY == 0 || mshr_rfo_offered[k] ||
                 (mshr_merge_delay[k] == 0 && mshr_mask[k] != 16'hffff))) begin
                send_found = 1'b1;
                send_index = k;
            end
            if (!matching_found && mshr_valid[k] && !mshr_writeback[k] &&
                ({mshr_addr[k][31:4], 4'b0} == request_line_addr)) begin
                matching_found = 1'b1;
                matching_index = k;
                matching_prefetch = mshr_prefetch[k];
            end
            if (mshr_valid[k] && !mshr_writeback[k] &&
                ({mshr_addr[k][31:4], 4'b0} == prefetch_line_addr))
                prefetch_line_present = 1'b1;
            // A refill into the same direct-mapped slot could overwrite a
            // store hit accepted now.  Other in-flight lines are independent
            // and must not serialize a cache-resident committed store.
            if (mshr_valid[k] &&
                (cache_index(mshr_addr[k]) == request_index))
                request_index_conflict = 1'b1;
            if (mshr_valid[k] &&
                (cache_index(mshr_addr[k]) == prefetch_index))
                prefetch_index_conflict = 1'b1;
        end
        // Keep all offered request fields stable across memory backpressure.
        // A new lower-index MSHR must not replace the selected transaction.
        if (send_locked) begin
            send_found = 1'b1;
            send_index = send_locked_index;
        end
        for (k = 0; k < WAITER_ENTRIES; k = k + 1) begin
            if (!waiter_free_found && !waiter_valid[k]) begin
                waiter_free_found = 1'b1;
                waiter_free_index = k;
            end
            if (!waiter_load_ready_found && waiter_valid[k] &&
                waiter_ready[k] && !waiter_store[k]) begin
                waiter_load_ready_found = 1'b1;
                waiter_load_ready_index = k;
            end
            if (!waiter_store_ready_found && waiter_valid[k] &&
                waiter_ready[k] && waiter_store[k]) begin
                waiter_store_ready_found = 1'b1;
                waiter_store_ready_index = k;
            end
        end
        response_index = mem_resp_id_i;
        response_found = (response_index >= 0) &&
                         (response_index < MSHR_ENTRIES) &&
                         mshr_valid[response_index] &&
                         mshr_sent[response_index];
    end

    wire request_is_store = core_req_is_store && !core_req_is_load;
    wire request_is_load = core_req_is_load && !core_req_is_store;
    wire response_matches = response_found &&
                            (mem_resp_line_addr_i ==
                             (mshr_writeback[response_index] ?
                              mshr_victim_addr[response_index] :
                              {mshr_addr[response_index][31:4], 4'b0}));
    wire response_writeback_failed = response_found &&
                                     mshr_writeback[response_index] &&
                                     (mem_resp_error_i || !response_matches);
    // The hit path, a completed waiter, and a returning MSHR all share one
    // registered output slot.  Admit a hit only when neither of the other
    // producers can claim that slot this cycle; otherwise the later
    // nonblocking assignment would silently overwrite the hit response.
    wire response_emits_load = mem_resp_valid_i && response_found &&
                               ((!mshr_writeback[response_index] &&
                                 !mshr_store[response_index] &&
                                 !mshr_prefetch[response_index]) ||
                                (response_writeback_failed &&
                                 !mshr_store[response_index]));
    // A committed store is acknowledged when its bytes are absorbed into an
    // MSHR.  The MSHR is the durable store buffer, so its later refill does
    // not produce a second LSQ acknowledgement.
    wire response_emits_store = 1'b0;
    wire matching_store_covers_load = matching_found &&
        mshr_store[matching_index] &&
        ((mshr_mask[matching_index] & core_req_mask) ==
         core_req_mask);
    wire load_can_accept = (request_hit ?
                            (resp_slot_free && !waiter_load_ready_found &&
                             !response_emits_load) :
                            (matching_found ?
                             ((matching_prefetch ||
                               (mshr_store[matching_index] ?
                                (matching_store_covers_load ?
                                 (resp_slot_free &&
                                  !waiter_load_ready_found &&
                                  !response_emits_load) : waiter_free_found) :
                                waiter_free_found)) &&
                              !(mem_resp_valid_i && response_found &&
                                (response_index == matching_index))) :
                             (free_found && !request_index_conflict)));
    wire store_can_accept = ack_slot_free &&
                            !waiter_store_ready_found &&
                            !response_emits_store &&
                            (request_hit ? !request_index_conflict :
                             (matching_found ?
                              ((matching_prefetch ||
                                mshr_store[matching_index]) &&
                               !(mem_resp_valid_i && response_found &&
                                 (response_index == matching_index))) :
                              (free_found && !request_index_conflict)));
    wire request_fire = core_req_valid && core_req_ready;
    wire response_needs_output = response_found &&
                                 (mshr_store[response_index] ? 1'b0 :
                                  (mshr_prefetch[response_index] ? 1'b0 :
                                   !resp_slot_free));
    wire demand_response_fire = mem_resp_valid_i && mem_resp_ready_o &&
                                response_found &&
                                !mshr_writeback[response_index] &&
                                !mshr_store[response_index] &&
                                !mshr_prefetch[response_index];
    wire store_response_fire = mem_resp_valid_i && mem_resp_ready_o &&
                               response_found &&
                               !mshr_writeback[response_index] &&
                               mshr_store[response_index];

    assign request_dirty_victim = !request_hit && !matching_found &&
        valid_bits[request_victim_entry] && dirty_bits[request_victim_entry];
    wire request_needs_array = (TAG_SRAM != 0) ?
        (request_hit && request_is_store) : (request_hit || request_dirty_victim);
    assign refill_array_write = !reset_i && mem_resp_valid_i &&
        mem_resp_ready_o && response_matches && !mem_resp_error_i &&
        !mshr_writeback[response_index];
    assign local_array_write = !reset_i && local_fill_found && !refill_array_write;
    wire request_array_access = request_fire && request_needs_array;
    assign data_we = refill_array_write || local_array_write ||
        (request_array_access && request_is_store && request_hit);
    assign data_addr = refill_array_write ?
        mshr_victim_entry[response_index] : local_array_write ?
        mshr_victim_entry[local_fill_index] : request_data_entry;
    assign data_wdata = refill_array_write ?
        (mshr_store[response_index] ? merge_store(mem_resp_data_i,
            mshr_wdata[response_index], mshr_mask[response_index]) : mem_resp_data_i) :
        local_array_write ? mshr_wdata[local_fill_index] : core_req_wdata;
    assign data_wmask = (refill_array_write || local_array_write) ?
        16'hffff : core_req_mask;
    generate if (TAG_SRAM == 0) begin : g_selected_data
    sram_fakeram #(.DEPTH(CACHE_LINES), .WIDTH(128), .WRITE_GRANULARITY(8)) data_array (
        .clk(clk_i), .en(!reset_i && (refill_array_write || local_array_write || request_array_access)),
        .we(data_we), .wmask(data_wmask), .addr(data_addr),
        .wdata(data_wdata), .rdata(data_rdata)
    );
    end else begin : g_parallel_data
        assign data_rdata = request_data_ways[(request_data_entry % CACHE_WAYS)*128 +: 128];
    end endgenerate

    assign core_req_ready = !reset_i && ((TAG_SRAM != 0) || !flush_i) &&
                                (!request_dirty_victim || request_data_ready) &&
                                !((refill_array_write || local_array_write) && request_needs_array) &&
                                !(local_array_write && matching_found &&
                                  matching_index == local_fill_index) &&
                                ((request_is_load && load_can_accept) ||
                                 (request_is_store && store_can_accept));
    wire bypass_load_hit = (TAG_SRAM != 0) && !reset_i && core_req_valid &&
        request_is_load && request_hit && !resp_valid_reg &&
        !waiter_load_ready_found && !response_emits_load;
    assign dcache_resp_valid_o = resp_valid_reg || bypass_load_hit;
    assign dcache_resp_lsq_tag_o = bypass_load_hit ? core_req_lsq_tag : resp_lsq_reg;
    assign dcache_resp_addr_o = bypass_load_hit ? core_req_addr : resp_addr_reg;
    assign dcache_resp_line_data_o = bypass_load_hit ? data_rdata :
        (resp_from_sram ? data_rdata : resp_line_reg);
    assign dcache_resp_word_data_o = bypass_load_hit ?
        extract_value(data_rdata, core_req_addr, core_req_size, core_req_unsigned) :
        (resp_from_sram ? extract_value(data_rdata, resp_addr_reg, resp_size_reg, resp_unsigned_reg) : resp_word_reg);
    assign dcache_resp_line_valid_o = bypass_load_hit || resp_line_valid_reg;
    assign dcache_resp_error_o = !bypass_load_hit && resp_error_reg;
    // The synchronous tag query already holds an accepted committed store.
    // Acknowledge at the SAME edge that writes its hit bytes or transfers
    // ownership into an MSHR. Do not add a second registered reply cycle.
    // If the consumer is stalled, retain the acknowledgement exactly once.
    wire bypass_store_ack = (TAG_SRAM != 0) && request_fire &&
                            request_is_store && !ack_valid_reg;
    assign dcache_store_ack_valid_o = ack_valid_reg || bypass_store_ack;
    assign dcache_store_ack_lsq_tag_o = bypass_store_ack ? core_req_lsq_tag : ack_lsq_reg;
    assign dcache_store_ack_error_o = !bypass_store_ack && ack_error_reg;

    assign mem_req_valid_o = send_found;
    assign mem_req_write_o = send_found && mshr_writeback[send_index];
    assign mem_req_line_addr_o = send_found ?
                                  (mshr_writeback[send_index] ?
                                   mshr_victim_addr[send_index] :
                                   {mshr_addr[send_index][31:4], 4'b0}) : 32'd0;
    assign mem_req_wdata_o = send_found && mshr_writeback[send_index] ?
                             ((victim_from_sram && victim_mshr_reg == send_index) ?
                              data_rdata : mshr_victim_data[send_index]) : 128'd0;
    assign mem_req_wmask_o = send_found && mshr_writeback[send_index] ?
                             16'hffff : 16'd0;
    assign mem_req_id_o = send_found ? send_index : 8'd0;
    assign mem_resp_ready_o = response_found && !response_needs_output;

    function [31:0] extract_value;
        input [127:0] line_data;
        input [31:0] address;
        input [1:0] size;
        input unsigned_load;
        reg [31:0] value;
        begin
            value = line_data >> (address[3:0] * 8);
            case (size)
                `RV32IM_MEM_BYTE:
                    extract_value = unsigned_load ? {24'd0, value[7:0]} :
                                    {{24{value[7]}}, value[7:0]};
                `RV32IM_MEM_HALF:
                    extract_value = unsigned_load ? {16'd0, value[15:0]} :
                                    {{16{value[15]}}, value[15:0]};
                default: extract_value = value;
            endcase
        end
    endfunction

    function [127:0] merge_store;
        input [127:0] line_data;
        input [127:0] store_data;
        input [15:0] mask;
        integer n;
        reg [127:0] merged;
        begin
            merged = line_data;
            for (n = 0; n < 16; n = n + 1)
                if (mask[n])
                    merged[(n*8) +: 8] = store_data[(n*8) +: 8];
            merge_store = merged;
        end
    endfunction

    integer reset_index;
    integer line_index;
    integer waiter_index;
    reg [127:0] updated_line;

    // Encode precisely the existing request priority before any wide state
    // write. The alternate implementation decodes a word/byte enable once,
    // rather than nesting a global request enable around dynamic vector writes.
    reg [3:0] static_request_action;
    always @* begin
        static_request_action = 4'd0;
        if (request_fire) begin
            if (request_is_load && request_hit)
                static_request_action = 4'd1;
            else if (request_is_store && request_hit)
                static_request_action = 4'd2;
            else if (request_is_load && matching_found &&
                     mshr_store[matching_index] && matching_store_covers_load)
                static_request_action = 4'd3;
            else if (request_is_load && matching_found && matching_prefetch)
                static_request_action = 4'd4;
            else if (request_is_load && matching_found)
                static_request_action = 4'd5;
            else if (request_is_store && matching_found && matching_prefetch)
                static_request_action = 4'd6;
            else if (request_is_store && matching_found && mshr_store[matching_index])
                static_request_action = 4'd7;
            else
                static_request_action = 4'd8;
        end
    end
    wire static_prefetch_allocate = (static_request_action == 4'd8) &&
        (PREFETCH != 0) && request_is_load && second_free_found &&
        !prefetch_cache_hit && !prefetch_line_present && !prefetch_index_conflict &&
        (prefetch_index != request_index) &&
        !(valid_bits[prefetch_victim_entry] && dirty_bits[prefetch_victim_entry]);

    genvar update_group, update_row, update_set, update_mshr, update_byte;
    generate if (STATIC_UPDATES == 0) begin : g_legacy_updates
        assign valid_bits = legacy_valid_bits;
        assign dirty_bits = legacy_dirty_bits;
        assign lru_way_mem = legacy_lru_way_mem;
        for (update_mshr = 0; update_mshr < MSHR_ENTRIES; update_mshr = update_mshr + 1) begin : g_data_view
            assign mshr_wdata[update_mshr] = legacy_mshr_wdata[update_mshr];
        end
    end else if (STATIC_UPDATES == 1) begin : g_static_updates
        localparam integer GROUP_ROWS = 16;
        localparam integer GROUP_COUNT = CACHE_LINES / GROUP_ROWS;
        reg [CACHE_LINES-1:0] static_valid_bits, static_dirty_bits;
        reg [CACHE_SETS-1:0] static_lru_way_mem;
        reg [127:0] static_mshr_wdata [0:MSHR_ENTRIES-1];
        assign valid_bits = static_valid_bits;
        assign dirty_bits = static_dirty_bits;
        assign lru_way_mem = static_lru_way_mem;
        // These are distinct address-qualified Boolean functions, not aliases
        // or external buffer cells. Retaining the decoder boundaries bounds
        // each group's metadata write fanout without adding a pipeline cycle.
        (* keep = 1 *) wire [GROUP_COUNT-1:0] miss_group, prefetch_group;
        (* keep = 1 *) wire [GROUP_COUNT-1:0] store_group, local_group, refill_group;
        (* keep = 1 *) wire [GROUP_ROWS-1:0] miss_row, prefetch_row, store_row;
        (* keep = 1 *) wire [GROUP_ROWS-1:0] local_row, refill_row;
        wire [CACHE_ENTRY_WIDTH-1:0] local_entry = mshr_victim_entry[local_fill_index];
        wire [CACHE_ENTRY_WIDTH-1:0] refill_entry = mshr_victim_entry[response_index];
        for (update_group = 0; update_group < GROUP_COUNT; update_group = update_group + 1) begin : g_group
            assign miss_group[update_group] = (static_request_action == 4'd8) &&
                (request_victim_entry / GROUP_ROWS == update_group);
            assign prefetch_group[update_group] = static_prefetch_allocate &&
                (prefetch_victim_entry / GROUP_ROWS == update_group);
            assign store_group[update_group] = (static_request_action == 4'd2) &&
                (request_hit_entry / GROUP_ROWS == update_group);
            assign local_group[update_group] = local_array_write &&
                (local_entry / GROUP_ROWS == update_group);
            assign refill_group[update_group] = refill_array_write &&
                (refill_entry / GROUP_ROWS == update_group);
        end
        for (update_row = 0; update_row < GROUP_ROWS; update_row = update_row + 1) begin : g_low_row
            assign miss_row[update_row] = (request_victim_entry[3:0] == update_row);
            assign prefetch_row[update_row] = (prefetch_victim_entry[3:0] == update_row);
            assign store_row[update_row] = (request_hit_entry[3:0] == update_row);
            assign local_row[update_row] = (local_entry[3:0] == update_row);
            assign refill_row[update_row] = (refill_entry[3:0] == update_row);
        end
        for (update_row = 0; update_row < CACHE_LINES; update_row = update_row + 1) begin : g_metadata
            wire miss_clear = miss_group[update_row / GROUP_ROWS] && miss_row[update_row % GROUP_ROWS];
            wire prefetch_clear = prefetch_group[update_row / GROUP_ROWS] && prefetch_row[update_row % GROUP_ROWS];
            wire store_dirty = store_group[update_row / GROUP_ROWS] && store_row[update_row % GROUP_ROWS];
            wire local_install = local_group[update_row / GROUP_ROWS] && local_row[update_row % GROUP_ROWS];
            wire refill_install = refill_group[update_row / GROUP_ROWS] && refill_row[update_row % GROUP_ROWS];
            always @(posedge clk_i) begin
                if (reset_i) begin
                    static_valid_bits[update_row] <= 1'b0;
                    // Preserve the original no-reset dirty-bit semantics.
                end else begin
                    // Later original nonblocking assignments win: refill,
                    // then local fill, then prefetch/miss, then store hit.
                    if (refill_install) begin
                        static_valid_bits[update_row] <= 1'b1;
                        static_dirty_bits[update_row] <= mshr_store[response_index];
                    end else if (local_install) begin
                        static_valid_bits[update_row] <= 1'b1;
                        static_dirty_bits[update_row] <= 1'b1;
                    end else if (prefetch_clear || miss_clear) begin
                        static_valid_bits[update_row] <= 1'b0;
                        static_dirty_bits[update_row] <= 1'b0;
                    end else if (store_dirty)
                        static_dirty_bits[update_row] <= 1'b1;
                end
            end
        end
        for (update_set = 0; update_set < CACHE_SETS; update_set = update_set + 1) begin : g_lru
            always @(posedge clk_i) begin
                if (reset_i) static_lru_way_mem[update_set] <= 1'b0;
                else if (CACHE_WAYS == 2) begin
                    if (static_prefetch_allocate && prefetch_index == update_set)
                        static_lru_way_mem[update_set] <= !prefetch_victim_entry[0];
                    else if (static_request_action == 4'd8 && request_index == update_set)
                        static_lru_way_mem[update_set] <= !request_victim_entry[0];
                    else if ((static_request_action == 4'd1 || static_request_action == 4'd2) &&
                             request_index == update_set)
                        static_lru_way_mem[update_set] <= !request_hit_entry[0];
                end
            end
        end
        for (update_mshr = 0; update_mshr < MSHR_ENTRIES; update_mshr = update_mshr + 1) begin : g_mshr_data
            assign mshr_wdata[update_mshr] = static_mshr_wdata[update_mshr];
            (* keep = 1 *) wire write_zero = static_prefetch_allocate && second_free_index == update_mshr;
            (* keep = 1 *) wire write_word =
                ((static_request_action == 4'd8) && free_index == update_mshr) ||
                ((static_request_action == 4'd6) && matching_index == update_mshr);
            (* keep = 1 *) wire merge_word = (static_request_action == 4'd7) && matching_index == update_mshr;
            for (update_byte = 0; update_byte < 16; update_byte = update_byte + 1) begin : g_byte
                (* keep = 1 *) wire write_byte = write_word || (merge_word && core_req_mask[update_byte]);
                always @(posedge clk_i) begin
                    if (reset_i) static_mshr_wdata[update_mshr][update_byte*8 +: 8] <= 8'd0;
                    else if (write_zero) static_mshr_wdata[update_mshr][update_byte*8 +: 8] <= 8'd0;
                    else if (write_byte)
                        static_mshr_wdata[update_mshr][update_byte*8 +: 8] <= core_req_wdata[update_byte*8 +: 8];
                end
            end
        end
    end else begin : g_banked_updates
        localparam integer GROUP_ROWS = 16;
        localparam integer GROUP_SETS = GROUP_ROWS / CACHE_WAYS;
        localparam integer GROUP_COUNT = CACHE_LINES / GROUP_ROWS;
        wire [CACHE_ENTRY_WIDTH-1:0] local_entry = mshr_victim_entry[local_fill_index];
        wire [CACHE_ENTRY_WIDTH-1:0] refill_entry = mshr_victim_entry[response_index];
        // These modules own the actual state and its address-qualified write
        // logic. No extra cycle, buffer-cell stub or replacement SRAM is used.
        for (update_group = 0; update_group < GROUP_COUNT; update_group = update_group + 1) begin : g_metadata
            rv32_dcache_metadata_bank #(
                .CACHE_LINES(CACHE_LINES), .CACHE_WAYS(CACHE_WAYS),
                .GROUP_ROWS(GROUP_ROWS), .GROUP_ID(update_group),
                .ENTRY_WIDTH(CACHE_ENTRY_WIDTH), .SET_WIDTH(CACHE_INDEX_WIDTH)
            ) state_bank (
                .clk_i(clk_i), .reset_i(reset_i),
                .refill_valid_i(refill_array_write), .refill_entry_i(refill_entry),
                .refill_dirty_i(mshr_store[response_index]),
                .local_valid_i(local_array_write), .local_entry_i(local_entry),
                .miss_valid_i(static_request_action == 4'd8), .miss_entry_i(request_victim_entry),
                .prefetch_valid_i(static_prefetch_allocate), .prefetch_entry_i(prefetch_victim_entry),
                .store_hit_i(static_request_action == 4'd2), .hit_entry_i(request_hit_entry),
                .hit_valid_i(static_request_action == 4'd1 || static_request_action == 4'd2),
                .request_set_i(request_index), .prefetch_set_i(prefetch_index),
                .valid_o(valid_bits[update_group*GROUP_ROWS +: GROUP_ROWS]),
                .dirty_o(dirty_bits[update_group*GROUP_ROWS +: GROUP_ROWS]),
                .lru_o(lru_way_mem[update_group*GROUP_SETS +: GROUP_SETS])
            );
        end
        for (update_mshr = 0; update_mshr < MSHR_ENTRIES; update_mshr = update_mshr + 1) begin : g_mshr_data
            rv32_dcache_mshr_data_bank #(.MSHR_ID(update_mshr)) state_bank (
                .clk_i(clk_i), .reset_i(reset_i), .request_action_i(static_request_action),
                .prefetch_allocate_i(static_prefetch_allocate), .second_free_i(second_free_index[2:0]),
                .free_i(free_index[2:0]), .matching_i(matching_index[2:0]),
                .write_mask_i(core_req_mask), .write_data_i(core_req_wdata),
                .data_o(mshr_wdata[update_mshr])
            );
        end
    end endgenerate

    always @(posedge clk_i) begin
        if (reset_i) begin
            resp_valid_reg <= 1'b0;
            resp_from_sram <= 1'b0;
            resp_size_reg <= 2'd0;
            resp_unsigned_reg <= 1'b0;
            victim_from_sram <= 1'b0;
            victim_mshr_reg <= 3'd0;
            ack_valid_reg <= 1'b0;
            send_locked <= 1'b0;
            send_locked_index <= 3'd0;
            event_request_o <= 1'b0;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_writeback_o <= 1'b0;
            event_stall_o <= 1'b0;
            if (STATIC_UPDATES == 0) begin
                legacy_valid_bits <= {CACHE_LINES{1'b0}};
                legacy_lru_way_mem <= {CACHE_SETS{1'b0}};
            end
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1) begin
                mshr_valid[reset_index] <= 1'b0;
                mshr_sent[reset_index] <= 1'b0;
                mshr_store[reset_index] <= 1'b0;
                mshr_prefetch[reset_index] <= 1'b0;
                mshr_writeback[reset_index] <= 1'b0;
                mshr_merge_delay[reset_index] <= {MERGE_COUNT_WIDTH{1'b0}};
                mshr_rfo_offered[reset_index] <= 1'b0;
                mshr_addr[reset_index] <= 32'd0;
                mshr_size[reset_index] <= 2'd0;
                mshr_unsigned[reset_index] <= 1'b0;
                mshr_mask[reset_index] <= 16'd0;
                if (STATIC_UPDATES == 0) legacy_mshr_wdata[reset_index] <= 128'd0;
                mshr_lsq[reset_index] <= {TAG_WIDTH{1'b0}};
                mshr_victim_addr[reset_index] <= 32'd0;
                mshr_victim_data[reset_index] <= 128'd0;
                mshr_victim_entry[reset_index] <= {CACHE_ENTRY_WIDTH{1'b0}};
            end
            for (reset_index = 0; reset_index < WAITER_ENTRIES; reset_index = reset_index + 1) begin
                waiter_valid[reset_index] <= 1'b0;
                waiter_ready[reset_index] <= 1'b0;
                waiter_store[reset_index] <= 1'b0;
                waiter_mshr[reset_index] <= 3'd0;
                waiter_addr[reset_index] <= 32'd0;
                waiter_size[reset_index] <= 2'd0;
                waiter_unsigned[reset_index] <= 1'b0;
                waiter_lsq[reset_index] <= {TAG_WIDTH{1'b0}};
                waiter_line[reset_index] <= 128'd0;
                waiter_error[reset_index] <= 1'b0;
            end
        end else begin
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1)
                if (mshr_valid[reset_index] && mshr_merge_delay[reset_index] != 0)
                    mshr_merge_delay[reset_index] <= mshr_merge_delay[reset_index] - 1'b1;
            if (mem_req_valid_o) begin
                if (!mem_req_write_o)
                    mshr_rfo_offered[send_index] <= 1'b1;
                send_locked <= !mem_req_ready_i;
                if (!mem_req_ready_i)
                    send_locked_index <= send_index[2:0];
            end
            resp_from_sram <= 1'b0;
            victim_from_sram <= 1'b0;
            if (resp_from_sram && resp_valid_reg) begin
                resp_line_reg <= data_rdata;
                resp_word_reg <= extract_value(data_rdata, resp_addr_reg,
                                               resp_size_reg, resp_unsigned_reg);
            end
            if (victim_from_sram)
                mshr_victim_data[victim_mshr_reg] <= data_rdata;
            event_request_o <= request_fire;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_writeback_o <= 1'b0;
            event_stall_o <= core_req_valid && !core_req_ready;
            if (resp_valid_reg && dcache_resp_ready_i)
                resp_valid_reg <= 1'b0;
            if (ack_valid_reg && dcache_store_ack_ready_i)
                ack_valid_reg <= 1'b0;

            if (request_fire) begin
                if (request_is_load && request_hit) begin
                    event_hit_o <= 1'b1;
                    // A bypass accepted on this edge is already delivered.
                    // Otherwise capture it once for a stable held response.
                    resp_valid_reg <= !(bypass_load_hit && dcache_resp_ready_i);
                    resp_lsq_reg <= core_req_lsq_tag;
                    resp_addr_reg <= core_req_addr;
                    resp_from_sram <= (TAG_SRAM == 0);
                    if (TAG_SRAM != 0) begin
                        resp_line_reg <= data_rdata;
                        resp_word_reg <= extract_value(data_rdata, core_req_addr,
                                                       core_req_size, core_req_unsigned);
                    end
                    resp_size_reg <= core_req_size;
                    resp_unsigned_reg <= core_req_unsigned;
                    resp_line_valid_reg <= 1'b1;
                    resp_error_reg <= 1'b0;
                    if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                        legacy_lru_way_mem[request_index] <= !request_hit_entry[0];
                end else if (request_is_store && request_hit) begin
                    event_hit_o <= 1'b1;
                    if (STATIC_UPDATES == 0) legacy_dirty_bits[request_hit_entry] <= 1'b1;
                    if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                        legacy_lru_way_mem[request_index] <= !request_hit_entry[0];
                    ack_valid_reg <= !(bypass_store_ack && dcache_store_ack_ready_i);
                    ack_lsq_reg <= core_req_lsq_tag;
                    ack_error_reg <= 1'b0;
                end else if (request_is_load && matching_found &&
                             mshr_store[matching_index] &&
                             matching_store_covers_load) begin
                    // The older committed store has already supplied every
                    // byte this load still needs.  Forward directly from the
                    // store-buffer MSHR without waiting for read-for-ownership.
                    event_hit_o <= 1'b1;
                    resp_valid_reg <= 1'b1;
                    resp_lsq_reg <= core_req_lsq_tag;
                    resp_addr_reg <= core_req_addr;
                    resp_line_reg <= mshr_wdata[matching_index];
                    resp_word_reg <= extract_value(mshr_wdata[matching_index],
                                                   core_req_addr,
                                                   core_req_size,
                                                   core_req_unsigned);
                    resp_line_valid_reg <= 1'b1;
                    resp_error_reg <= 1'b0;
                end else if (request_is_load && matching_found && matching_prefetch) begin
                    // Turn the speculative line into the demand transaction;
                    // its memory request and ID remain unchanged.
                    event_miss_o <= 1'b1;
                    mshr_prefetch[matching_index] <= 1'b0;
                    mshr_addr[matching_index] <= core_req_addr;
                    mshr_size[matching_index] <= core_req_size;
                    mshr_unsigned[matching_index] <= core_req_unsigned;
                    mshr_lsq[matching_index] <= core_req_lsq_tag;
                end else if (request_is_load && matching_found) begin
                    // Merge a secondary demand behind the line fill instead
                    // of stalling the LSQ's oldest-request selector.
                    event_miss_o <= 1'b1;
                    waiter_valid[waiter_free_index] <= 1'b1;
                    waiter_ready[waiter_free_index] <= 1'b0;
                    waiter_store[waiter_free_index] <= 1'b0;
                    waiter_mshr[waiter_free_index] <= matching_index[2:0];
                    waiter_addr[waiter_free_index] <= core_req_addr;
                    waiter_size[waiter_free_index] <= core_req_size;
                    waiter_unsigned[waiter_free_index] <= core_req_unsigned;
                    waiter_lsq[waiter_free_index] <= core_req_lsq_tag;
                    waiter_error[waiter_free_index] <= 1'b0;
                end else if (request_is_store && matching_found &&
                             matching_prefetch) begin
                    // A committed store owns the prefetched line from now on;
                    // retain the transaction ID and turn its refill into the
                    // store miss completion.
                    event_miss_o <= 1'b1;
                    mshr_store[matching_index] <= 1'b1;
                    mshr_prefetch[matching_index] <= 1'b0;
                    mshr_addr[matching_index] <= core_req_addr;
                    mshr_size[matching_index] <= core_req_size;
                    mshr_unsigned[matching_index] <= 1'b0;
                    mshr_mask[matching_index] <= core_req_mask;
                    if (STATIC_UPDATES == 0) legacy_mshr_wdata[matching_index] <= core_req_wdata;
                    mshr_lsq[matching_index] <= core_req_lsq_tag;
                    mshr_merge_delay[matching_index] <= MERGE_DELAY;
                end else if (request_is_store && matching_found &&
                             mshr_store[matching_index]) begin
                    // Consecutive committed stores to one missing line share
                    // the refill.  Later bytes override earlier bytes while
                    // every LSQ entry retains its own completion ack.
                    event_miss_o <= 1'b1;
                    if (STATIC_UPDATES == 0)
                        legacy_mshr_wdata[matching_index] <=
                            merge_store(mshr_wdata[matching_index],
                                        core_req_wdata,
                                        core_req_mask);
                    mshr_mask[matching_index] <= mshr_mask[matching_index] |
                                                 core_req_mask;
                end else begin
                    event_miss_o <= 1'b1;
                    mshr_valid[free_index] <= 1'b1;
                    mshr_sent[free_index] <= 1'b0;
                    mshr_rfo_offered[free_index] <= 1'b0;
                    mshr_merge_delay[free_index] <= request_is_store ? MERGE_DELAY :
                                                               {MERGE_COUNT_WIDTH{1'b0}};
                    mshr_store[free_index] <= request_is_store;
                    mshr_prefetch[free_index] <= 1'b0;
                    mshr_writeback[free_index] <= valid_bits[request_victim_entry] &&
                                                  dirty_bits[request_victim_entry];
                    mshr_addr[free_index] <= core_req_addr;
                    mshr_size[free_index] <= core_req_size;
                    mshr_unsigned[free_index] <= core_req_unsigned;
                    mshr_mask[free_index] <= request_is_store ? core_req_mask : 16'd0;
                    if (STATIC_UPDATES == 0) legacy_mshr_wdata[free_index] <= core_req_wdata;
                    mshr_lsq[free_index] <= core_req_lsq_tag;
                    mshr_victim_addr[free_index] <=
                        victim_line_address(request_tags[(request_victim_entry % CACHE_WAYS)*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH], request_index);
                    mshr_victim_data[free_index] <= 128'd0;
                    if (request_dirty_victim) begin
                        if (TAG_SRAM == 0) begin
                            victim_from_sram <= 1'b1;
                            victim_mshr_reg <= free_index[2:0];
                        end else begin
                            mshr_victim_data[free_index] <= data_rdata;
                        end
                    end
                    mshr_victim_entry[free_index] <= request_victim_entry;
                    if (STATIC_UPDATES == 0) begin
                        legacy_valid_bits[request_victim_entry] <= 1'b0;
                        legacy_dirty_bits[request_victim_entry] <= 1'b0;
                    end
                    if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                        legacy_lru_way_mem[request_index] <= !request_victim_entry[0];

                    // Store streams already expose every committed address
                    // to the cache.  Prefetching after a store miss wastes a
                    // scarce external read slot (notably during BSS clear)
                    // and can delay the first real load stream.  Independent
                    // store lines may occupy separate MSHRs instead.
                    if ((PREFETCH != 0) && request_is_load &&
                        second_free_found && !prefetch_cache_hit &&
                        !prefetch_line_present &&
                        !prefetch_index_conflict &&
                        (prefetch_index != request_index) &&
                        !(valid_bits[prefetch_victim_entry] &&
                          dirty_bits[prefetch_victim_entry])) begin
                        mshr_valid[second_free_index] <= 1'b1;
                        mshr_sent[second_free_index] <= 1'b0;
                        mshr_rfo_offered[second_free_index] <= 1'b0;
                        mshr_merge_delay[second_free_index] <= {MERGE_COUNT_WIDTH{1'b0}};
                        mshr_store[second_free_index] <= 1'b0;
                        mshr_prefetch[second_free_index] <= 1'b1;
                        mshr_writeback[second_free_index] <= 1'b0;
                        mshr_addr[second_free_index] <= prefetch_line_addr;
                        mshr_size[second_free_index] <= `RV32IM_MEM_WORD;
                        mshr_unsigned[second_free_index] <= 1'b1;
                        mshr_mask[second_free_index] <= 16'd0;
                        if (STATIC_UPDATES == 0) legacy_mshr_wdata[second_free_index] <= 128'd0;
                        mshr_lsq[second_free_index] <= {TAG_WIDTH{1'b0}};
                        mshr_victim_addr[second_free_index] <= 32'd0;
                        mshr_victim_data[second_free_index] <= 128'd0;
                        mshr_victim_entry[second_free_index] <= prefetch_victim_entry;
                        if (STATIC_UPDATES == 0) begin
                            legacy_valid_bits[prefetch_victim_entry] <= 1'b0;
                            legacy_dirty_bits[prefetch_victim_entry] <= 1'b0;
                        end
                        if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                            legacy_lru_way_mem[prefetch_index] <= !prefetch_victim_entry[0];
                    end
                end
                if (request_is_store) begin
                    // Ownership has transferred to the cache/store buffer;
                    // the LSQ no longer needs to retain the committed entry.
                    ack_valid_reg <= !(bypass_store_ack && dcache_store_ack_ready_i);
                    ack_lsq_reg <= core_req_lsq_tag;
                    ack_error_reg <= 1'b0;
                end
            end

            if (mem_req_valid_o && mem_req_ready_i)
                mshr_sent[send_index] <= 1'b1;

            if (local_array_write) begin
                // Full byte coverage makes the line independent of old RAM
                // contents. Stores were acknowledged on ownership transfer;
                // local completion installs dirty data, never a second ack.
                mshr_valid[local_fill_index] <= 1'b0;
                if (STATIC_UPDATES == 0) begin
                    legacy_valid_bits[mshr_victim_entry[local_fill_index]] <= 1'b1;
                    legacy_dirty_bits[mshr_victim_entry[local_fill_index]] <= 1'b1;
                end
                if (TAG_SRAM == 0)
                    tag_mem[mshr_victim_entry[local_fill_index]] <=
                        mshr_addr[local_fill_index][31:CACHE_INDEX_WIDTH+4];
                event_refill_o <= 1'b1;
                for (waiter_index = 0; waiter_index < WAITER_ENTRIES;
                     waiter_index = waiter_index + 1) begin
                    if (waiter_valid[waiter_index] && !waiter_ready[waiter_index] &&
                        waiter_mshr[waiter_index] == local_fill_index[2:0]) begin
                        waiter_ready[waiter_index] <= 1'b1;
                        waiter_error[waiter_index] <= 1'b0;
                        if (!waiter_store[waiter_index])
                            waiter_line[waiter_index] <= mshr_wdata[local_fill_index];
                    end
                end
            end

            if (resp_slot_free && waiter_load_ready_found &&
                !demand_response_fire) begin
                resp_valid_reg <= 1'b1;
                resp_lsq_reg <= waiter_lsq[waiter_load_ready_index];
                resp_addr_reg <= waiter_addr[waiter_load_ready_index];
                resp_line_reg <= waiter_line[waiter_load_ready_index];
                resp_word_reg <= extract_value(waiter_line[waiter_load_ready_index],
                                               waiter_addr[waiter_load_ready_index],
                                               waiter_size[waiter_load_ready_index],
                                               waiter_unsigned[waiter_load_ready_index]);
                resp_line_valid_reg <= !waiter_error[waiter_load_ready_index];
                resp_error_reg <= waiter_error[waiter_load_ready_index];
                waiter_valid[waiter_load_ready_index] <= 1'b0;
                waiter_ready[waiter_load_ready_index] <= 1'b0;
            end

            if (ack_slot_free && waiter_store_ready_found &&
                !store_response_fire) begin
                ack_valid_reg <= 1'b1;
                ack_lsq_reg <= waiter_lsq[waiter_store_ready_index];
                ack_error_reg <= waiter_error[waiter_store_ready_index];
                waiter_valid[waiter_store_ready_index] <= 1'b0;
                waiter_ready[waiter_store_ready_index] <= 1'b0;
            end

            if (mem_resp_valid_i && mem_resp_ready_o) begin
                mshr_sent[response_index] <= 1'b0;
                if (mshr_writeback[response_index] &&
                    !mem_resp_error_i && response_matches) begin
                    mshr_writeback[response_index] <= 1'b0;
                    event_writeback_o <= 1'b1;
                end else if (mshr_writeback[response_index]) begin
                    mshr_valid[response_index] <= 1'b0;
                    if (mshr_store[response_index]) begin
                        ack_valid_reg <= 1'b1;
                        ack_lsq_reg <= mshr_lsq[response_index];
                        ack_error_reg <= 1'b1;
                    end else begin
                        resp_valid_reg <= 1'b1;
                        resp_lsq_reg <= mshr_lsq[response_index];
                        resp_addr_reg <= mshr_addr[response_index];
                        resp_line_reg <= 128'd0;
                        resp_word_reg <= 32'd0;
                        resp_line_valid_reg <= 1'b0;
                        resp_error_reg <= 1'b1;
                    end
                end else if (mshr_store[response_index]) begin
                    mshr_valid[response_index] <= 1'b0;
                    updated_line = merge_store(mem_resp_data_i,
                                               mshr_wdata[response_index],
                                               mshr_mask[response_index]);
                    for (waiter_index = 0; waiter_index < WAITER_ENTRIES;
                         waiter_index = waiter_index + 1) begin
                        if (waiter_valid[waiter_index] && !waiter_ready[waiter_index] &&
                            (waiter_mshr[waiter_index] == response_index[2:0])) begin
                            waiter_ready[waiter_index] <= 1'b1;
                            waiter_error[waiter_index] <= mem_resp_error_i ||
                                                          !response_matches;
                            if (!waiter_store[waiter_index])
                                waiter_line[waiter_index] <= updated_line;
                        end
                    end
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_victim_entry[response_index];
                        if (STATIC_UPDATES == 0) begin
                            legacy_valid_bits[line_index] <= 1'b1;
                            legacy_dirty_bits[line_index] <= 1'b1;
                        end
                        if (TAG_SRAM == 0)
                            tag_mem[line_index] <= mshr_addr[response_index][31:CACHE_INDEX_WIDTH+4];
                        event_refill_o <= 1'b1;
                    end
                end else if (mshr_prefetch[response_index]) begin
                    mshr_valid[response_index] <= 1'b0;
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_victim_entry[response_index];
                        if (STATIC_UPDATES == 0) legacy_valid_bits[line_index] <= 1'b1;
                        if (TAG_SRAM == 0)
                            tag_mem[line_index] <= mshr_addr[response_index][31:CACHE_INDEX_WIDTH+4];
                        if (STATIC_UPDATES == 0) legacy_dirty_bits[line_index] <= 1'b0;
                        event_refill_o <= 1'b1;
                    end
                end else begin
                    mshr_valid[response_index] <= 1'b0;
                    for (waiter_index = 0; waiter_index < WAITER_ENTRIES;
                         waiter_index = waiter_index + 1) begin
                        if (waiter_valid[waiter_index] && !waiter_ready[waiter_index] &&
                            !waiter_store[waiter_index] &&
                            (waiter_mshr[waiter_index] == response_index[2:0])) begin
                            waiter_ready[waiter_index] <= 1'b1;
                            waiter_line[waiter_index] <= mem_resp_data_i;
                            waiter_error[waiter_index] <= mem_resp_error_i ||
                                                          !response_matches;
                        end
                    end
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_victim_entry[response_index];
                        if (STATIC_UPDATES == 0) legacy_valid_bits[line_index] <= 1'b1;
                        if (TAG_SRAM == 0)
                            tag_mem[line_index] <= mshr_addr[response_index][31:CACHE_INDEX_WIDTH+4];
                        if (STATIC_UPDATES == 0) legacy_dirty_bits[line_index] <= 1'b0;
                        event_refill_o <= 1'b1;
                    end
                    resp_valid_reg <= 1'b1;
                    resp_lsq_reg <= mshr_lsq[response_index];
                    resp_addr_reg <= mshr_addr[response_index];
                    resp_line_reg <= mem_resp_data_i;
                    resp_word_reg <= extract_value(mem_resp_data_i,
                                                   mshr_addr[response_index],
                                                   mshr_size[response_index],
                                                   mshr_unsigned[response_index]);
                    resp_line_valid_reg <= !mem_resp_error_i && response_matches;
                    resp_error_reg <= mem_resp_error_i || !response_matches;
                end
            end
        end
    end

    initial begin
        if (TAG_WIDTH < 8 || MSHR_ENTRIES < 2 || MSHR_ENTRIES > 8 ||
            WAITER_ENTRIES < 1 || WAITER_ENTRIES > 16 ||
            (PREFETCH != 0 && PREFETCH != 1) ||
            (INDEX_HASH != 0 && INDEX_HASH != 1) || CACHE_LINES < 16 ||
            ((CACHE_WAYS != 1) && (CACHE_WAYS != 2)) ||
            STORE_MERGE_DELAY < 0 || STORE_MERGE_DELAY > 255 ||
            (TAG_SRAM != 0 && TAG_SRAM != 1) ||
            (STATIC_UPDATES < 0 || STATIC_UPDATES > 2) ||
            (CACHE_LINES % CACHE_WAYS != 0) ||
            CACHE_LINES > 4096 ||
            ((CACHE_LINES & (CACHE_LINES - 1)) != 0)) begin
            $display("ERROR: invalid rv32_dcache_nonblocking parameter");
            $finish;
        end
    end
endmodule
