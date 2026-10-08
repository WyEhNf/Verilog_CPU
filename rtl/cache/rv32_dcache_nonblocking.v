`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Non-blocking, write-back data cache for the performance profiles. Loads use
// independent MSHRs, merge behind an outstanding line, and trigger a clean
// next-line prefetch. A demand that reaches an in-flight prefetch promotes it
// in place so the returned line completes the original LSQ entry.
module rv32_dcache_nonblocking #(
    parameter integer LOCAL_SRAM_COMMANDS = 0,
    parameter integer WAY_PARALLEL_QUERY = 0,
    parameter integer HIT_RESPONSE_COISSUE = 0,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer MSHR_ENTRIES = 4,
    parameter integer WAITER_ENTRIES = 8,
    parameter integer PREFETCH = 1,
    parameter integer CACHE_LINES = 256,
    parameter integer CACHE_WAYS = 1,
    parameter integer INDEX_HASH = 0,
    parameter integer STORE_MERGE_DELAY = 0,
    // 0: fixed allocation timer. 1: rolling whole-word prefix coalescing;
    // scatter stores start RFO immediately and never withdraw an offered RFO.
    parameter integer STORE_MERGE_POLICY = 0,
    // Cold store misses write enabled bytes without allocating a cache line.
    // The store remains owned by its MSHR until the memory write response.
    parameter integer STORE_MISS_WRITE_AROUND = 0,
    parameter integer TAG_SRAM = 0,
    // 0: legacy dynamic writes; 1: flat static enables; 2: functional state banks.
    parameter integer STATIC_UPDATES = 0,
    // Compute set indices on the existing synchronous tag-query capture edge.
    // This is a layout change, not an additional request pipeline cycle.
    parameter integer REGISTERED_INDEX = 0,
    // Bank-local same-edge query addresses and live metadata selection.
    // Active only with synchronous tags and actual state banks (mode 2).
    parameter integer LOCAL_METADATA_QUERY = 0,
    parameter integer LOCAL_ACTION_DECODE = 0,
    // Default retains the fast hit reply. Zero uses existing held response
    // metadata/data owners, adding no state and cutting late arbitration.
    parameter integer HIT_BYPASS = 1,
    parameter WORD_RESPONSE = 0,
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
    output wire [1:0]              dcache_resp_query_valid_o,
    output wire [2*TAG_WIDTH-1:0]   dcache_resp_query_tags_o,
    output wire [31:0]              dcache_resp_addr_o,
    output wire [127:0]             dcache_resp_line_data_o,
    output wire [31:0]              dcache_resp_word_data_o,
    output wire                     dcache_resp_line_valid_o,
    output wire                     dcache_resp_error_o,
    output wire                     dcache_store_ack_valid_o,
    input  wire                     dcache_store_ack_ready_i,
    output wire [TAG_WIDTH-1:0]     dcache_store_ack_lsq_tag_o,
    output wire [TAG_WIDTH-1:0]     dcache_store_ack_query_tag_o,
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
    wire unused_valid_bits_bits = &{1'b0, valid_bits};

    wire [CACHE_LINES-1:0] dirty_bits;
    wire unused_dirty_bits_bits = &{1'b0, dirty_bits};

    reg [CACHE_LINES-1:0] legacy_valid_bits;
    wire unused_legacy_valid_bits_bits = &{1'b0, legacy_valid_bits};

    reg [CACHE_LINES-1:0] legacy_dirty_bits;
    wire unused_legacy_dirty_bits_bits = &{1'b0, legacy_dirty_bits};

    reg [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];
    for (genvar unused_tag_mem_row=0; unused_tag_mem_row<=CACHE_LINES-1; unused_tag_mem_row=unused_tag_mem_row+1) begin : g_unused_tag_mem
        wire unused_tag_mem_bits = &{1'b0, tag_mem[unused_tag_mem_row]};
    end

    wire [CACHE_SETS-1:0] lru_way_mem;
    wire unused_lru_way_mem_bits = &{1'b0, lru_way_mem};

    reg [CACHE_SETS-1:0] legacy_lru_way_mem;
    wire unused_legacy_lru_way_mem_bits = &{1'b0, legacy_lru_way_mem};

    localparam integer CACHE_ENTRY_WIDTH = $clog2(CACHE_LINES);
    localparam integer WAITER_SLOT_WIDTH=(WAITER_ENTRIES<=1)?1:$clog2(WAITER_ENTRIES);
    localparam LOCAL_METADATA_ACTIVE = LOCAL_METADATA_QUERY != 0 &&
                                               STATIC_UPDATES == 2 && TAG_SRAM != 0;

    reg mshr_valid [0:MSHR_ENTRIES-1];
    reg mshr_sent [0:MSHR_ENTRIES-1];
    reg mshr_store [0:MSHR_ENTRIES-1];
    reg mshr_prefetch [0:MSHR_ENTRIES-1];
    reg mshr_writeback [0:MSHR_ENTRIES-1];
    wire mshr_writearound [0:MSHR_ENTRIES-1];
    wire [MSHR_ENTRIES-1:0] writearound_rows;
    wire query_matching_writearound, query_send_writearound, query_response_writearound;
    for (genvar around_row=0;around_row<MSHR_ENTRIES;around_row=around_row+1) begin:g_around_views
        assign writearound_rows[around_row]=mshr_writearound[around_row];
    end
    generate if (STORE_MISS_WRITE_AROUND != 0) begin:g_around_reads
    rv32_frequency_array_read #(.WIDTH(1),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) around_matching_read (
        .rows_i(writearound_rows),.index_i(matching_index),.value_o(query_matching_writearound));
    rv32_frequency_array_read #(.WIDTH(1),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) around_send_read (
        .rows_i(writearound_rows),.index_i(send_index),.value_o(query_send_writearound));
    rv32_frequency_array_read #(.WIDTH(1),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(8)) around_response_read (
        .rows_i(writearound_rows),.index_i(mem_resp_id_i),.value_o(query_response_writearound));
    end else begin:g_no_around_reads
        assign query_matching_writearound=1'b0;
        assign query_send_writearound=1'b0;
        assign query_response_writearound=1'b0;
    end endgenerate
    localparam integer MERGE_COUNT_WIDTH = (STORE_MERGE_DELAY < 1) ? 1 :
                                          $clog2(STORE_MERGE_DELAY + 1);
    localparam [MERGE_COUNT_WIDTH-1:0] MERGE_DELAY = MERGE_COUNT_WIDTH'(STORE_MERGE_DELAY);
    reg [MERGE_COUNT_WIDTH-1:0] mshr_merge_delay [0:MSHR_ENTRIES-1];
    // Once a read has been offered, valid must not be withdrawn even if later
    // stores complete its mask. An unoffered fully known line needs no RFO.
    reg mshr_rfo_offered [0:MSHR_ENTRIES-1];
    reg send_locked;
    reg [2:0] send_locked_index;
    wire [31:0] mshr_addr [0:MSHR_ENTRIES-1];
    wire [1:0] mshr_size [0:MSHR_ENTRIES-1];
    wire mshr_unsigned [0:MSHR_ENTRIES-1];
    wire [15:0] mshr_mask [0:MSHR_ENTRIES-1];
    wire [127:0] mshr_wdata [0:MSHR_ENTRIES-1];
    reg [127:0] legacy_mshr_wdata [0:MSHR_ENTRIES-1];
    for (genvar unused_legacy_mshr_wdata_row=0; unused_legacy_mshr_wdata_row<=MSHR_ENTRIES-1; unused_legacy_mshr_wdata_row=unused_legacy_mshr_wdata_row+1) begin : g_unused_legacy_mshr_wdata
        wire unused_legacy_mshr_wdata_bits = &{1'b0, legacy_mshr_wdata[unused_legacy_mshr_wdata_row]};
    end

    wire [TAG_WIDTH-1:0] mshr_lsq [0:MSHR_ENTRIES-1];
    wire [31:0] mshr_victim_addr [0:MSHR_ENTRIES-1];
    wire [127:0] mshr_victim_data [0:MSHR_ENTRIES-1];
    wire [CACHE_ENTRY_WIDTH-1:0] mshr_victim_entry [0:MSHR_ENTRIES-1];

    // Secondary misses to an already outstanding demand line are accepted
    // here.  Keeping the returned line with each waiter lets refills retire
    // independently even if the direct-mapped cache slot is replaced later.
    reg waiter_valid [0:WAITER_ENTRIES-1];
    reg waiter_ready [0:WAITER_ENTRIES-1];
    wire waiter_store [0:WAITER_ENTRIES-1];
    wire [2:0] waiter_mshr [0:WAITER_ENTRIES-1];
    wire [31:0] waiter_addr [0:WAITER_ENTRIES-1];
    wire [1:0] waiter_size [0:WAITER_ENTRIES-1];
    wire waiter_unsigned [0:WAITER_ENTRIES-1];
    wire [TAG_WIDTH-1:0] waiter_lsq [0:WAITER_ENTRIES-1];
    localparam integer WAITER_DATA_WIDTH=(WORD_RESPONSE!=0)?32:128;
    wire [WAITER_DATA_WIDTH-1:0] waiter_line [0:WAITER_ENTRIES-1];
    wire waiter_error [0:WAITER_ENTRIES-1];

    reg resp_valid_reg;
    wire [TAG_WIDTH-1:0] resp_lsq_reg;
    wire [31:0] resp_addr_reg;
    wire [127:0] resp_line_reg;
    wire [31:0] resp_word_reg;
    wire resp_line_valid_reg;
    wire resp_error_reg;
    // The synchronous SRAM result and hit metadata become valid together.
    // Capture the result on the following edge before the macro can make its
    // output undefined during an idle/write cycle or a backpressured response.
    reg resp_from_sram;
    wire [1:0] resp_size_reg;
    wire resp_unsigned_reg;
    reg victim_from_sram;
    reg [2:0] victim_mshr_reg;
    wire [127:0] data_rdata;
    reg ack_valid_reg;
    wire [TAG_WIDTH-1:0] ack_lsq_reg;
    wire ack_error_reg;

    // Keep the original high address tag. XOR index folding is reversible
    // given that tag, so dirty victims retain their exact physical address.
    function automatic [CACHE_INDEX_WIDTH-1:0] cache_index;
        input [31:0] address;
        begin
            cache_index = CACHE_INDEX_WIDTH'(address >> 4);
            if (INDEX_HASH != 0)
                cache_index = CACHE_INDEX_WIDTH'(32'(cache_index) ^ (address >> (CACHE_INDEX_WIDTH + 4)));
        end
    endfunction

    function automatic [31:0] victim_line_address;
        input [CACHE_TAG_WIDTH-1:0] tag;
        input [CACHE_INDEX_WIDTH-1:0] index;
        reg [CACHE_INDEX_WIDTH-1:0] original_index;
        begin
            original_index = index;
            if (INDEX_HASH != 0) original_index = CACHE_INDEX_WIDTH'(19'(index) ^ tag);
            victim_line_address = {tag, original_index, 4'b0};
        end
    endfunction

    function automatic [CACHE_ENTRY_WIDTH-1:0] cache_entry;
        input [CACHE_INDEX_WIDTH-1:0] set_index;
        input integer way;
        begin
            cache_entry = CACHE_ENTRY_WIDTH'(set_index * CACHE_WAYS + way);
        end
    endfunction

    wire core_req_valid, core_req_ready, core_req_is_load, core_req_is_store;
    wire [31:0] core_req_addr;
    wire [CACHE_INDEX_WIDTH-1:0] core_request_index, core_prefetch_index;
    wire [1:0] core_req_size;
    wire core_req_unsigned;
    wire [15:0] core_req_mask;
    wire [127:0] core_req_wdata;
    wire [TAG_WIDTH-1:0] core_req_rob_tag, core_req_lsq_tag;
    wire unused_core_req_rob_tag_bits = &{1'b0, core_req_rob_tag};

    wire [(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] request_tags, prefetch_tags;
    integer response_index;
    wire [2:0] local_fill_index;
    wire refill_array_write, local_array_write;
    wire data_we;
    wire [CACHE_ENTRY_WIDTH-1:0] data_addr;
    wire [127:0] data_wdata;
    wire [15:0] data_wmask;
    wire [CACHE_WAYS*128-1:0] request_data_ways;
    wire request_data_ready;
    wire request_dirty_victim;
    wire tag_array_write = refill_array_write || local_array_write;
    localparam integer TAG_WRITE_INPUT_WIDTH=CACHE_ENTRY_WIDTH+CACHE_TAG_WIDTH;
    localparam integer TAG_WRITE_INPUT_WORDS=(TAG_WRITE_INPUT_WIDTH+15)/16;
    wire [CACHE_ENTRY_WIDTH-1:0] tag_write_entry;
    wire [CACHE_INDEX_WIDTH-1:0] tag_write_set=CACHE_INDEX_WIDTH'(32'(tag_write_entry)/CACHE_WAYS);
    wire [CACHE_TAG_WIDTH-1:0] tag_write_value;
    wire [TAG_WRITE_INPUT_WIDTH-1:0] local_tag_input,response_tag_input,selected_tag_input;
    wire [TAG_WRITE_INPUT_WORDS-1:0] tag_write_source_views;
    assign local_tag_input={query_local_mshr_victim_entry,query_local_mshr_addr[31:CACHE_INDEX_WIDTH+4]};
    assign response_tag_input={query_response_mshr_victim_entry,query_response_mshr_addr[31:CACHE_INDEX_WIDTH+4]};
    assign {tag_write_entry,tag_write_value}=selected_tag_input;
    rv32_frequency_control_tree #(.LEAVES(TAG_WRITE_INPUT_WORDS)) tag_write_source_tree (
        .signal_i(local_array_write),.views_o(tag_write_source_views));
    generate for(genvar tag_input_word=0;tag_input_word<TAG_WRITE_INPUT_WORDS;tag_input_word=tag_input_word+1) begin:g_tag_input_word
        localparam integer LOW=tag_input_word*16;
        localparam integer BITS=(TAG_WRITE_INPUT_WIDTH-LOW>=16)?16:TAG_WRITE_INPUT_WIDTH-LOW;
        assign selected_tag_input[LOW +: BITS]=tag_write_source_views[tag_input_word]?
            local_tag_input[LOW +: BITS]:response_tag_input[LOW +: BITS];
    end endgenerate
    wire [CACHE_WAYS-1:0] tag_write_mask = (CACHE_WAYS == 1) ? CACHE_WAYS'(1'b1) :
        (2'b01 << tag_write_entry[0]);
    reg request_hit;
    reg [CACHE_ENTRY_WIDTH-1:0] request_hit_entry;
    wire request_fire, request_is_store;
    genvar tag_way;
    generate if (TAG_SRAM == 0) begin : g_ff_tags
        assign request_data_ready = 1'b1;
        assign core_req_valid = dcache_req_valid_i;
        assign dcache_req_ready_o = core_req_ready;
        assign core_req_is_load = dcache_req_is_load_i;
        assign core_req_is_store = dcache_req_is_store_i;
        assign core_req_addr = dcache_req_addr_i;
        assign core_request_index = cache_index(dcache_req_addr_i);
        assign core_prefetch_index = cache_index({dcache_req_addr_i[31:4],4'b0} + 32'd16);
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
        reg [CACHE_WAYS-1:0] query_data_valid, query_data_from_sram;
        wire [CACHE_WAYS-1:0] input_way_reads;
        wire query_load, query_store, query_unsigned;
        wire [31:0] query_addr;
        wire [CACHE_INDEX_WIDTH-1:0] query_request_index, query_prefetch_index;
        wire [1:0] query_size;
        wire [15:0] query_mask;
        wire [127:0] query_wdata;
        wire [TAG_WIDTH-1:0] query_rob, query_lsq;
        wire [(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] demand_hold, prefetch_hold;
        wire [(CACHE_WAYS*CACHE_TAG_WIDTH)-1:0] demand_rdata, prefetch_rdata;
        wire [CACHE_WAYS*128-1:0] bank_rdata;
        wire [CACHE_WAYS*128-1:0] bank_hold;
        wire input_fire = dcache_req_valid_i && dcache_req_ready_o;
        // Store queries need only tags on a hit. Let a following store query
        // share the preceding store's DATA write edge, while tag SRAM reads.
        // If this query instead evicts dirty data, read all ways later before
        // transferring ownership; never capture undefined write/idle rdata.
        // Data writes own one physical way. The remaining ways can read
        // the incoming tag query on that edge; never treat the written way's
        // undefined SRAM Q as a read result or as valid held data.
        wire input_data_read = input_fire && ((WAY_PARALLEL_QUERY!=0) || !data_we);
        wire deferred_data_read = query_valid && !request_data_ready &&
            (request_dirty_victim ||
             ((WAY_PARALLEL_QUERY!=0) && query_load && request_hit)) &&
            !data_we && !tag_array_write;
        for(genvar read_way=0;read_way<CACHE_WAYS;read_way=read_way+1) begin:g_input_way_read
            assign input_way_reads[read_way]=input_data_read &&
                !(data_we && ((32'(data_addr)%CACHE_WAYS)==read_way));
        end
        wire [31:0] input_prefetch_line = {dcache_req_addr_i[31:4],4'b0} + 32'd16;
        localparam integer INPUT_PAYLOAD_WIDTH=181+2*TAG_WIDTH;
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
        assign dcache_req_ready_o = !reset_i && !flush_i && !tag_array_write &&
                                   ((WAY_PARALLEL_QUERY!=0) || !data_we || dcache_req_is_store_i) &&
                                   (!query_valid || core_req_ready);
        assign core_req_valid = query_valid;
        assign core_req_is_load = query_load;
        assign core_req_is_store = query_store;
        assign core_req_addr = query_addr;
        assign core_request_index = (REGISTERED_INDEX != 0) ?
            query_request_index : cache_index(query_addr);
        assign core_prefetch_index = (REGISTERED_INDEX != 0) ?
            query_prefetch_index : cache_index({query_addr[31:4],4'b0} + 32'd16);
        assign core_req_size = query_size;
        assign core_req_unsigned = query_unsigned;
        assign core_req_mask = query_mask;
        assign core_req_wdata = query_wdata;
        assign core_req_rob_tag = query_rob;
        assign core_req_lsq_tag = query_lsq;
        localparam integer LOOKUP_TAG_WORDS=(CACHE_WAYS*CACHE_TAG_WIDTH+15)/16;
        localparam integer LOOKUP_DATA_WORDS=8*CACHE_WAYS;
        localparam integer LOOKUP_WORDS=2*LOOKUP_TAG_WORDS+LOOKUP_DATA_WORDS;
        localparam integer LOOKUP_SELECT_WIDTH=CACHE_WAYS+1;
        wire [LOOKUP_SELECT_WIDTH*LOOKUP_WORDS-1:0] lookup_read_views;
        rv32_frequency_control_tree #(.WIDTH(LOOKUP_SELECT_WIDTH),.LEAVES(LOOKUP_WORDS)) lookup_read_tree (
            .signal_i({query_data_from_sram,query_from_sram}),.views_o(lookup_read_views));
        genvar lookup_word;
        for(lookup_word=0;lookup_word<LOOKUP_TAG_WORDS;lookup_word=lookup_word+1) begin:g_lookup_tag_word
            localparam integer LOW=lookup_word*16;
            localparam integer BITS=(CACHE_WAYS*CACHE_TAG_WIDTH-LOW>=16)?16:CACHE_WAYS*CACHE_TAG_WIDTH-LOW;
            assign request_tags[LOW +: BITS]=lookup_read_views[LOOKUP_SELECT_WIDTH*lookup_word]?
                demand_rdata[LOW +: BITS]:demand_hold[LOW +: BITS];
            assign prefetch_tags[LOW +: BITS]=lookup_read_views[LOOKUP_SELECT_WIDTH*(LOOKUP_TAG_WORDS+lookup_word)]?
                prefetch_rdata[LOW +: BITS]:prefetch_hold[LOW +: BITS];
        end
        for(lookup_word=0;lookup_word<LOOKUP_DATA_WORDS;lookup_word=lookup_word+1) begin:g_lookup_data_word
            assign request_data_ways[lookup_word*16 +: 16]=lookup_read_views[LOOKUP_SELECT_WIDTH*(2*LOOKUP_TAG_WORDS+lookup_word)+1+(lookup_word/8)]?
                bank_rdata[lookup_word*16 +: 16]:bank_hold[lookup_word*16 +: 16];
        end
        localparam integer HOLD_SELECT_WIDTH=CACHE_WAYS+2;
        wire [HOLD_SELECT_WIDTH*CACHE_WAYS-1:0] hold_event_views;
        rv32_frequency_control_tree #(.WIDTH(HOLD_SELECT_WIDTH),.LEAVES(CACHE_WAYS)) hold_event_tree (
            .signal_i({reset_i,query_data_from_sram,query_from_sram}),.views_o(hold_event_views));
        localparam integer TAG_FORWARD_WIDTH=1+CACHE_WAYS+CACHE_INDEX_WIDTH+CACHE_TAG_WIDTH;
        wire [CACHE_WAYS*TAG_FORWARD_WIDTH-1:0] tag_forward_views;
        rv32_frequency_control_tree #(.WIDTH(TAG_FORWARD_WIDTH),.LEAVES(CACHE_WAYS)) tag_forward_tree (
            .signal_i({tag_array_write,tag_write_mask,tag_write_set,tag_write_value}),
            .views_o(tag_forward_views));
        genvar hold_way;
        for(hold_way=0;hold_way<CACHE_WAYS;hold_way=hold_way+1) begin:g_lookup_hold_owner
            wire local_reset,data_copy,tag_copy;
            assign local_reset=hold_event_views[hold_way*HOLD_SELECT_WIDTH+CACHE_WAYS+1];
            assign data_copy=hold_event_views[hold_way*HOLD_SELECT_WIDTH+1+hold_way];
            assign tag_copy=hold_event_views[hold_way*HOLD_SELECT_WIDTH];
            wire bank_forward=!local_reset && data_we && query_valid &&
                32'(data_addr)/CACHE_WAYS==32'(core_request_index) && 32'(data_addr)%CACHE_WAYS==hold_way;
            wire local_tag_write;
            wire [CACHE_WAYS-1:0] local_tag_mask;
            wire unused_local_tag_mask_bits = &{1'b0, local_tag_mask};

            wire [CACHE_INDEX_WIDTH-1:0] local_tag_set;
            wire [CACHE_TAG_WIDTH-1:0] local_tag_value;
            assign {local_tag_write,local_tag_mask,local_tag_set,local_tag_value}=
                tag_forward_views[hold_way*TAG_FORWARD_WIDTH +: TAG_FORWARD_WIDTH];
            wire tag_forward=!local_reset && local_tag_write && query_valid && local_tag_mask[hold_way];
            wire demand_forward=tag_forward && local_tag_set==core_request_index;
            wire prefetch_forward=tag_forward && local_tag_set==core_prefetch_index;
            wire demand_write,prefetch_write,data_write;
            wire [CACHE_TAG_WIDTH-1:0] demand_next,prefetch_next;
            wire [127:0] data_next;
            rv32_frequency_event_select #(.WIDTH(CACHE_TAG_WIDTH),.EVENTS(2)) demand_selector (
                .events_i({demand_forward,!local_reset && tag_copy}),
                .values_i({local_tag_value,demand_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]}),
                .write_o(demand_write),.value_o(demand_next));
            rv32_frequency_word_bank #(.WIDTH(CACHE_TAG_WIDTH)) demand_owner (
                .clk_i(clk_i),.write_i(demand_write),.data_i(demand_next),.data_o(demand_hold[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
            rv32_frequency_event_select #(.WIDTH(CACHE_TAG_WIDTH),.EVENTS(2)) prefetch_selector (
                .events_i({prefetch_forward,!local_reset && tag_copy}),
                .values_i({local_tag_value,prefetch_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]}),
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
        // Only the selected hit/victim way supplies load/victim data.
        assign request_data_ready = query_data_valid[32'(request_data_entry)%CACHE_WAYS];
        // Each way owns one command decode. The final controls and address
        // reach individual byte macros only through bounded distributions.
        localparam integer DATA_COMMAND_WIDTH=7;
        localparam integer DATA_ADDRESS_WIDTH=3*CACHE_ENTRY_WIDTH+2*CACHE_INDEX_WIDTH;
        wire [CACHE_WAYS*DATA_COMMAND_WIDTH-1:0] data_command_views;
        wire [CACHE_WAYS*DATA_ADDRESS_WIDTH-1:0] data_address_views;
        if(LOCAL_SRAM_COMMANDS!=0) begin:g_data_command_distribution
            rv32_frequency_control_tree #(.WIDTH(DATA_COMMAND_WIDTH),.LEAVES(CACHE_WAYS)) command_tree (
                .signal_i({reset_i,refill_array_write,local_array_write,
                           (request_fire && request_is_store && request_hit),
                           input_data_read,deferred_data_read,query_response_mshr_store}),
                .views_o(data_command_views));
            rv32_frequency_control_tree #(.WIDTH(DATA_ADDRESS_WIDTH),.LEAVES(CACHE_WAYS)) address_tree (
                .signal_i({query_response_mshr_victim_entry,query_local_mshr_victim_entry,
                           request_hit_entry,cache_index(dcache_req_addr_i),core_request_index}),
                .views_o(data_address_views));
        end else begin:g_unused_data_command_views
            assign data_command_views=0;
            assign data_address_views=0;
        end
        for (tag_way = 0; tag_way < CACHE_WAYS; tag_way = tag_way + 1) begin : g_data_way
            if (LOCAL_SRAM_COMMANDS != 0) begin:g_local_commands
                wire command_reset,command_refill,command_local,command_store;
                wire command_input_read,command_deferred_read,command_response_store;
                wire [CACHE_ENTRY_WIDTH-1:0] command_refill_entry,command_local_entry,command_hit_entry;
                wire [CACHE_INDEX_WIDTH-1:0] command_input_index,command_deferred_index;
                assign {command_reset,command_refill,command_local,command_store,
                        command_input_read,command_deferred_read,command_response_store}=
                    data_command_views[tag_way*DATA_COMMAND_WIDTH +: DATA_COMMAND_WIDTH];
                assign {command_refill_entry,command_local_entry,command_hit_entry,
                        command_input_index,command_deferred_index}=
                    data_address_views[tag_way*DATA_ADDRESS_WIDTH +: DATA_ADDRESS_WIDTH];
                rv32_dcache_command_line #(.SETS(CACHE_SETS),.WAYS(CACHE_WAYS),
                    .WAY(tag_way),.IW(CACHE_INDEX_WIDTH),.EW(CACHE_ENTRY_WIDTH)) port_bank (
                    .clk_i(clk_i),.reset_i(command_reset),
                    .refill_i(command_refill),.local_i(command_local),.store_i(command_store),
                    .input_read_i(command_input_read),.deferred_read_i(command_deferred_read),
                    .refill_entry_i(command_refill_entry),.local_entry_i(command_local_entry),
                    .hit_entry_i(command_hit_entry),.input_index_i(command_input_index),
                    .deferred_index_i(command_deferred_index),
                    .response_data_i(mem_resp_data_i),.response_store_i(command_response_store),
                    .response_store_data_i(query_response_mshr_wdata),.response_mask_i(query_response_mshr_mask),
                    .local_data_i(query_local_mshr_wdata),.store_data_i(core_req_wdata),.store_mask_i(core_req_mask),
                    .data_o(bank_rdata[tag_way*128 +: 128]));
            end else begin:g_original_port
            wire write_way = data_we && ((data_addr % CACHE_WAYS) == tag_way);
            sram_fakeram #(.DEPTH(CACHE_SETS), .WIDTH(128), .WRITE_GRANULARITY(8)) data_bank (
                .clk(clk_i), .en(!reset_i && (write_way || input_data_read || deferred_data_read)),
                .we(write_way), .wmask(data_wmask),
                .addr(write_way ? (data_addr / CACHE_WAYS) :
                    deferred_data_read ? core_request_index : cache_index(dcache_req_addr_i)),
                .wdata(data_wdata), .rdata(bank_rdata[tag_way*128 +: 128])
            );
            end
        end
        // Each former word-wide SRAM way retains the SAME global write
        // mode even when its mask bit is zero: it must not become a read
        // during the other way's write. Only command distribution changes.
        localparam integer TAG_PORTS=2*CACHE_WAYS;
        wire [TAG_PORTS-1:0] tag_port_write,tag_port_enable,tag_port_address_select;
        wire [TAG_PORTS*CACHE_TAG_WIDTH-1:0] tag_port_data;
        rv32_frequency_control_tree #(.LEAVES(TAG_PORTS)) tag_port_write_tree (
            .signal_i(tag_array_write),.views_o(tag_port_write));
        rv32_frequency_control_tree #(.LEAVES(TAG_PORTS)) tag_port_enable_tree (
            .signal_i(!reset_i && (tag_array_write || input_fire)),.views_o(tag_port_enable));
        rv32_frequency_control_tree #(.LEAVES(TAG_PORTS)) tag_port_address_tree (
            .signal_i(tag_array_write),.views_o(tag_port_address_select));
        rv32_frequency_control_tree #(.WIDTH(CACHE_TAG_WIDTH),.LEAVES(TAG_PORTS)) tag_port_data_tree (
            .signal_i(tag_write_value),.views_o(tag_port_data));
        for(genvar tag_port_way=0;tag_port_way<CACHE_WAYS;tag_port_way=tag_port_way+1) begin:g_tag_port_way
            sram_fakeram #(.DEPTH(CACHE_SETS),.WIDTH(CACHE_TAG_WIDTH),
                          .WRITE_GRANULARITY(CACHE_TAG_WIDTH)) demand_tags (
                .clk(clk_i),.en(tag_port_enable[2*tag_port_way]),
                .we(tag_port_write[2*tag_port_way]),.wmask(tag_write_mask[tag_port_way]),
                .addr(tag_port_address_select[2*tag_port_way]?tag_write_set:cache_index(dcache_req_addr_i)),
                .wdata(tag_port_data[2*tag_port_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]),
                .rdata(demand_rdata[tag_port_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
            sram_fakeram #(.DEPTH(CACHE_SETS),.WIDTH(CACHE_TAG_WIDTH),
                          .WRITE_GRANULARITY(CACHE_TAG_WIDTH)) nextline_tags (
                .clk(clk_i),.en(tag_port_enable[2*tag_port_way+1]),
                .we(tag_port_write[2*tag_port_way+1]),.wmask(tag_write_mask[tag_port_way]),
                .addr(tag_port_address_select[2*tag_port_way+1]?tag_write_set:cache_index(input_prefetch_line)),
                .wdata(tag_port_data[(2*tag_port_way+1)*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]),
                .rdata(prefetch_rdata[tag_port_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
        end
        always @(posedge clk_i) begin
            if (reset_i) begin
                query_valid <= 1'b0;
                query_from_sram <= 1'b0;
                query_data_valid <= 0;
                query_data_from_sram <= 0;
            end else begin
                query_from_sram <= input_fire;
                query_data_from_sram <= input_way_reads | {CACHE_WAYS{deferred_data_read}};
                if (deferred_data_read) query_data_valid <= {CACHE_WAYS{1'b1}};
                // Payload owners preserve copy<forward ordering independently
                // of the scalar query-valid and deferred-read state below.
                if (core_req_valid && core_req_ready)
                    query_valid <= 1'b0;
                // flush blocks new inputs but never discards a request whose
                // ownership was accepted earlier (especially a committed SW).
                if (input_fire) begin
                    query_valid <= 1'b1;
                    query_data_valid <= input_way_reads;
                end
            end
        end
    end endgenerate

    wire [CACHE_INDEX_WIDTH-1:0] request_index = core_request_index;
    wire [CACHE_TAG_WIDTH-1:0] request_tag =
        core_req_addr[31:CACHE_INDEX_WIDTH+4];
    reg [CACHE_ENTRY_WIDTH-1:0] request_victim_entry;
    // Hit reads and dirty-victim snapshots share the single 1RW data port.
    // Refills have priority; store hits use byte masks without read/modify/write.
    wire [CACHE_ENTRY_WIDTH-1:0] request_data_entry =
        request_hit ? request_hit_entry : request_victim_entry;
    wire resp_slot_free = !resp_valid_reg || dcache_resp_ready_i;
    wire ack_slot_free = !ack_valid_reg || dcache_store_ack_ready_i;

    wire [2:0] free_index;
    wire [2:0] second_free_index;
    wire [2:0] send_index;
    wire [2:0] matching_index;
    wire [WAITER_SLOT_WIDTH-1:0] waiter_free_index;
    wire [WAITER_SLOT_WIDTH-1:0] waiter_load_ready_index;
    wire [WAITER_SLOT_WIDTH-1:0] waiter_store_ready_index;
    wire free_found;
    wire second_free_found;
    wire send_found;
    wire local_fill_found;
    wire any_mshr;
    wire unused_any_mshr_bits = &{1'b0, any_mshr};

    wire store_mshr_present;
    wire unused_store_mshr_present_bits = &{1'b0, store_mshr_present};

    reg response_found;
    wire matching_found;
    wire matching_prefetch;
    wire prefetch_line_present;
    wire request_index_conflict;
    wire prefetch_index_conflict;
    wire waiter_free_found;
    wire waiter_load_ready_found;
    wire waiter_store_ready_found;
    wire [31:0] request_line_addr = {core_req_addr[31:4], 4'b0};
    wire [31:0] prefetch_line_addr = request_line_addr + 32'd16;
    wire [CACHE_INDEX_WIDTH-1:0] prefetch_index = core_prefetch_index;
    wire [CACHE_TAG_WIDTH-1:0] prefetch_tag =
        prefetch_line_addr[31:CACHE_INDEX_WIDTH+4];
    reg prefetch_cache_hit;
    reg [CACHE_ENTRY_WIDTH-1:0] prefetch_victim_entry;
    wire [CACHE_WAYS-1:0] request_query_valid, request_query_dirty;
    wire [CACHE_WAYS-1:0] prefetch_query_valid, prefetch_query_dirty;
    wire request_query_lru, prefetch_query_lru;
    wire request_victim_valid = request_query_valid[32'(request_victim_entry) % CACHE_WAYS];
    wire request_victim_dirty = request_query_dirty[32'(request_victim_entry) % CACHE_WAYS];
    wire prefetch_victim_valid = prefetch_query_valid[32'(prefetch_victim_entry) % CACHE_WAYS];
    wire prefetch_victim_dirty = prefetch_query_dirty[32'(prefetch_victim_entry) % CACHE_WAYS];
    genvar query_way;
    generate if (LOCAL_METADATA_ACTIVE == 0) begin : g_original_query_metadata
        for (query_way = 0; query_way < CACHE_WAYS; query_way = query_way + 1) begin : g_way
            assign request_query_valid[query_way] = valid_bits[cache_entry(request_index, query_way)];
            assign request_query_dirty[query_way] = dirty_bits[cache_entry(request_index, query_way)];
            assign prefetch_query_valid[query_way] = valid_bits[cache_entry(prefetch_index, query_way)];
            assign prefetch_query_dirty[query_way] = dirty_bits[cache_entry(prefetch_index, query_way)];
        end
        assign request_query_lru = lru_way_mem[request_index];
        assign prefetch_query_lru = lru_way_mem[prefetch_index];
    end endgenerate
    integer way_scan;
    reg request_invalid_found;
    reg prefetch_invalid_found;
    always @* begin
        request_hit = 1'b0;
        prefetch_cache_hit = 1'b0;
        request_hit_entry = cache_entry(request_index, 0);
        request_victim_entry = cache_entry(request_index,
            (CACHE_WAYS == 2) ? 32'(request_query_lru) : 0);
        prefetch_victim_entry = cache_entry(prefetch_index,
            (CACHE_WAYS == 2) ? 32'(prefetch_query_lru) : 0);
        request_invalid_found = 1'b0;
        prefetch_invalid_found = 1'b0;
        for (way_scan = 0; way_scan < CACHE_WAYS; way_scan = way_scan + 1) begin
            if (request_query_valid[way_scan] &&
                (request_tags[way_scan*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] == request_tag)) begin
                request_hit = 1'b1;
                request_hit_entry = cache_entry(request_index, way_scan);
            end
            if (!request_invalid_found &&
                !request_query_valid[way_scan]) begin
                request_invalid_found = 1'b1;
                request_victim_entry = cache_entry(request_index, way_scan);
            end
            if (prefetch_query_valid[way_scan] &&
                (prefetch_tags[way_scan*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH] == prefetch_tag))
                prefetch_cache_hit = 1'b1;
            if (!prefetch_invalid_found &&
                !prefetch_query_valid[way_scan]) begin
                prefetch_invalid_found = 1'b1;
                prefetch_victim_entry = cache_entry(prefetch_index, way_scan);
            end
        end
    end

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
            assign matching_candidates[scan_mshr]=mshr_valid[scan_mshr] && (!mshr_writeback[scan_mshr] || mshr_writearound[scan_mshr]) &&
                {mshr_addr[scan_mshr][31:4],4'b0}==request_line_addr;
            assign prefetch_present_candidates[scan_mshr]=mshr_valid[scan_mshr] && (!mshr_writeback[scan_mshr] || mshr_writearound[scan_mshr]) &&
                {mshr_addr[scan_mshr][31:4],4'b0}==prefetch_line_addr;
            assign request_conflict_candidates[scan_mshr]=mshr_valid[scan_mshr] && !mshr_writearound[scan_mshr] && cache_index(mshr_addr[scan_mshr])==request_index;
            assign prefetch_conflict_candidates[scan_mshr]=mshr_valid[scan_mshr] && !mshr_writearound[scan_mshr] && cache_index(mshr_addr[scan_mshr])==prefetch_index;
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
        wire  unused_send_selector_second_valid_o;
    wire [(3)-1:0] unused_send_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) send_selector (
        .candidates_i(send_candidates),.first_valid_o(unlocked_send_found),.first_index_o(unlocked_send_index),
        .second_valid_o(unused_send_selector_second_valid_o),.second_index_o(unused_send_selector_second_index_o));
        wire  unused_local_selector_second_valid_o;
    wire [(3)-1:0] unused_local_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) local_selector (
        .candidates_i(local_candidates),.first_valid_o(local_fill_found),.first_index_o(local_fill_index),
        .second_valid_o(unused_local_selector_second_valid_o),.second_index_o(unused_local_selector_second_index_o));
        wire  unused_matching_selector_second_valid_o;
    wire [(3)-1:0] unused_matching_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) matching_selector (
        .candidates_i(matching_candidates),.first_valid_o(matching_found),.first_index_o(matching_index),
        .second_valid_o(unused_matching_selector_second_valid_o),.second_index_o(unused_matching_selector_second_index_o));
        wire  unused_waiter_free_selector_second_valid_o;
    wire [(WAITER_SLOT_WIDTH)-1:0] unused_waiter_free_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_free_selector (
        .candidates_i(waiter_free_candidates),.first_valid_o(waiter_free_found),.first_index_o(waiter_free_index),
        .second_valid_o(unused_waiter_free_selector_second_valid_o),.second_index_o(unused_waiter_free_selector_second_index_o));
        wire  unused_waiter_load_selector_second_valid_o;
    wire [(WAITER_SLOT_WIDTH)-1:0] unused_waiter_load_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_load_selector (
        .candidates_i(waiter_load_candidates),.first_valid_o(waiter_load_ready_found),.first_index_o(waiter_load_ready_index),
        .second_valid_o(unused_waiter_load_selector_second_valid_o),.second_index_o(unused_waiter_load_selector_second_index_o));
        wire  unused_waiter_store_selector_second_valid_o;
    wire [(WAITER_SLOT_WIDTH)-1:0] unused_waiter_store_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_store_selector (
        .candidates_i(waiter_store_candidates),.first_valid_o(waiter_store_ready_found),.first_index_o(waiter_store_ready_index),
        .second_valid_o(unused_waiter_store_selector_second_valid_o),.second_index_o(unused_waiter_store_selector_second_index_o));
    assign send_found=send_locked || unlocked_send_found;
    assign send_index=send_locked?send_locked_index:unlocked_send_index;
    assign any_mshr=|live_candidates;
    assign store_mshr_present=|store_candidates;
    assign matching_prefetch=matching_found && query_matching_mshr_prefetch;
    assign prefetch_line_present=|prefetch_present_candidates;
    assign request_index_conflict=|request_conflict_candidates;
    assign prefetch_index_conflict=|prefetch_conflict_candidates;
    always @* begin
        response_index=32'(mem_resp_id_i);
        response_found=(response_index>=0) && (response_index<MSHR_ENTRIES) &&
            mshr_valid[response_index] && mshr_sent[response_index];
    end

    assign request_is_store = core_req_is_store && !core_req_is_load;
    wire request_is_load = core_req_is_load && !core_req_is_store;
    // Registered per-row identity is ready before the returning MSHR index.
    // Compare both legal address sources in parallel; late selection carries
    // one comparison bit instead of a selected flag plus a 32-bit address mux.
    wire [MSHR_ENTRIES-1:0] response_address_match_rows;
    wire selected_response_address_match;
    generate for(genvar match_mshr=0;match_mshr<MSHR_ENTRIES;match_mshr=match_mshr+1) begin:g_response_address_match
        assign response_address_match_rows[match_mshr]=
            (mshr_writeback[match_mshr] && mem_resp_line_addr_i==mshr_victim_addr[match_mshr]) ||
            (!mshr_writeback[match_mshr] && mem_resp_line_addr_i=={mshr_addr[match_mshr][31:4],4'b0});
    end endgenerate
    rv32_frequency_array_read #(.WIDTH(1),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(8)) response_address_match_read (
        .rows_i(response_address_match_rows),.index_i(mem_resp_id_i),.value_o(selected_response_address_match));
    // The original valid/sent/range response authority remains mandatory.
    wire response_matches=response_found && selected_response_address_match;
    wire response_writeback_failed = response_found &&
                                     query_response_mshr_writeback &&
                                     (mem_resp_error_i || !response_matches);
    // The hit path, a completed waiter, and a returning MSHR all share one
    // registered output slot.  Admit a hit only when neither of the other
    // producers can claim that slot this cycle; otherwise the later
    // nonblocking assignment would silently overwrite the hit response.
    wire response_emits_load = mem_resp_valid_i && response_found &&
                               ((!query_response_mshr_writeback &&
                                 !query_response_mshr_store &&
                                 !query_response_mshr_prefetch) ||
                                (response_writeback_failed &&
                                 !query_response_mshr_store));
    // Allocating stores acknowledge durable MSHR absorption once. Around
    // stores instead reserve the ACK output when their memory write returns.
    wire response_emits_store = mem_resp_valid_i && response_found && query_response_writearound;
    wire matching_store_covers_load = matching_found &&
        query_matching_mshr_store &&
        ((query_matching_mshr_mask & core_req_mask) ==
         core_req_mask);
    // A query hit can leave through the existing combinational bypass while
    // a waiter/refill takes the existing held reply slot at the same edge.
    // The offer never depends on ready. A blocked hit is captured once and
    // the competing reply remains at its original owner until a later edge.
    // Exclude local-fill candidates before response-ready arbitration, so
    // neither this offer nor request acceptance depends on refill priority.
    wire hit_coissue_offer=(HIT_RESPONSE_COISSUE!=0) && (HIT_BYPASS!=0) &&
        (TAG_SRAM!=0) && !reset_i && core_req_valid && request_is_load &&
        request_hit && request_data_ready && !resp_valid_reg && !local_fill_found;
    wire hit_coissue_holds_slot=hit_coissue_offer && !dcache_resp_ready_i;
    wire load_can_accept = (request_hit ?
                            (resp_slot_free && (hit_coissue_offer ||
                             (!waiter_load_ready_found && !response_emits_load))) :
                            (matching_found ?
                             ((matching_prefetch ||
                               (query_matching_mshr_store ?
                                (matching_store_covers_load ?
                                 (resp_slot_free &&
                                  !waiter_load_ready_found &&
                                  !response_emits_load) : (!query_matching_writearound && waiter_free_found)) :
                                waiter_free_found)) &&
                              !(mem_resp_valid_i && response_found &&
                                (response_index == 32'(matching_index)))) :
                             (free_found && !request_index_conflict)));
    wire store_can_accept = ack_slot_free &&
                            !waiter_store_ready_found &&
                            !response_emits_store &&
                            (request_hit ? !request_index_conflict :
                             (matching_found ?
                              ((matching_prefetch ||
                                query_matching_mshr_store) && !query_matching_writearound &&
                               !(mem_resp_valid_i && response_found &&
                                 (response_index == 32'(matching_index)))) :
                              (free_found && !request_index_conflict)));
    assign request_fire = core_req_valid && core_req_ready;
    wire response_needs_output = response_found &&
                                  (query_response_writearound ? !ack_slot_free :
                                   (query_response_mshr_store ? 1'b0 :
                                    (query_response_mshr_prefetch ? 1'b0 :
                                     !resp_slot_free)));
    wire demand_response_fire = mem_resp_valid_i && mem_resp_ready_o &&
                                response_found &&
                                !query_response_mshr_writeback &&
                                !query_response_mshr_store &&
                                !query_response_mshr_prefetch;
    wire store_response_fire = mem_resp_valid_i && mem_resp_ready_o &&
                               response_found &&
                               !query_response_mshr_writeback &&
                               query_response_mshr_store;

    wire request_writearound_new = (STORE_MISS_WRITE_AROUND != 0) &&
        request_is_store && !request_hit && !matching_found;
    assign request_dirty_victim = !request_hit && !matching_found && !request_writearound_new &&
        request_victim_valid && request_victim_dirty;
    wire request_needs_array = (TAG_SRAM != 0) ?
        (request_hit && request_is_store) : (request_hit || request_dirty_victim);
    assign refill_array_write = !reset_i && mem_resp_valid_i &&
        mem_resp_ready_o && response_matches && !mem_resp_error_i &&
        !query_response_mshr_writeback;
    assign local_array_write = !reset_i && local_fill_found && !refill_array_write;
    wire request_array_access = request_fire && request_needs_array;
    assign data_we = refill_array_write || local_array_write ||
        (request_array_access && request_is_store && request_hit);
    assign data_addr = refill_array_write ?
        query_response_mshr_victim_entry : local_array_write ?
        query_local_mshr_victim_entry : request_data_entry;
    // Metadata distribution alone leaves the shared response-store flag
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
    end endgenerate
    assign data_wmask = (refill_array_write || local_array_write) ?
        16'hffff : core_req_mask;
    generate if (TAG_SRAM == 0) begin : g_selected_data
    sram_fakeram #(.DEPTH(CACHE_LINES), .WIDTH(128), .WRITE_GRANULARITY(8)) data_array (
        .clk(clk_i), .en(!reset_i && (refill_array_write || local_array_write || request_array_access)),
        .we(data_we), .wmask(data_wmask), .addr(data_addr),
        .wdata(data_wdata), .rdata(data_rdata)
    );
    end else begin : g_parallel_data
        localparam integer DATA_WAY_WIDTH=(CACHE_WAYS<=1)?1:$clog2(CACHE_WAYS);
        wire [DATA_WAY_WIDTH-1:0] selected_way=DATA_WAY_WIDTH'(32'(request_data_entry)%CACHE_WAYS);
        rv32_frequency_array_read #(.WIDTH(128),.ENTRIES(CACHE_WAYS),.INDEX_WIDTH(DATA_WAY_WIDTH)) data_way_reader (
            .rows_i(request_data_ways),.index_i(selected_way),.value_o(data_rdata));
    end endgenerate

    assign core_req_ready = !reset_i && ((TAG_SRAM != 0) || !flush_i) &&
                                (!(request_dirty_victim ||
                                    ((WAY_PARALLEL_QUERY!=0) && (TAG_SRAM!=0) &&
                                     request_is_load && request_hit)) || request_data_ready) &&
                                !((refill_array_write || local_array_write) && request_needs_array) &&
                                !(local_array_write && matching_found &&
                                  matching_index == local_fill_index) &&
                                ((request_is_load && load_can_accept) ||
                                 (request_is_store && store_can_accept));
    wire bypass_load_hit = hit_coissue_offer ||
        ((HIT_BYPASS != 0) && (TAG_SRAM != 0) && !reset_i && core_req_valid &&
         request_is_load && request_hit && request_data_ready && !resp_valid_reg &&
         !waiter_load_ready_found && !response_emits_load);
    assign dcache_resp_valid_o = resp_valid_reg || bypass_load_hit;
    // Same actual public source priority. Candidate identities are available
    // independently before the late bypass decision routes a public ticket.
    assign dcache_resp_query_valid_o={bypass_load_hit,resp_valid_reg && !bypass_load_hit};
    assign dcache_resp_query_tags_o={core_req_lsq_tag,resp_lsq_reg};

    localparam integer RESPONSE_TAG_WORDS=(TAG_WIDTH+15)/16;
    localparam integer RESPONSE_OUTPUT_WORDS=RESPONSE_TAG_WORDS+13;
    wire [2*RESPONSE_OUTPUT_WORDS-1:0] response_output_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(RESPONSE_OUTPUT_WORDS)) response_output_tree (
        .signal_i({resp_from_sram,bypass_load_hit}),.views_o(response_output_views));
    // Share the same extracted word between immediate and captured hit
    // replies. Byte-offset fanout stays bounded inside each routing unit.
    wire [31:0] response_hit_word,response_deferred_word;
    rv32_frequency_line_extract32 hit_extract (
        .line_i(data_rdata),.offset_i(core_req_addr[3:0]),
        .size_i((WORD_RESPONSE!=0)?2'd2:core_req_size),.unsigned_i((WORD_RESPONSE!=0)?1'b1:core_req_unsigned),.value_o(response_hit_word));
    rv32_frequency_line_extract32 deferred_extract (
        .line_i(data_rdata),.offset_i(resp_addr_reg[3:0]),
        .size_i((WORD_RESPONSE!=0)?2'd2:resp_size_reg),.unsigned_i((WORD_RESPONSE!=0)?1'b1:resp_unsigned_reg),.value_o(response_deferred_word));
    genvar response_word;
    generate
        for(response_word=0;response_word<RESPONSE_TAG_WORDS;response_word=response_word+1) begin:g_response_tag_word
            localparam integer LOW=response_word*16;
            localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
            assign dcache_resp_lsq_tag_o[LOW +: BITS]=response_output_views[2*response_word]?
                core_req_lsq_tag[LOW +: BITS]:resp_lsq_reg[LOW +: BITS];
        end
        for(response_word=0;response_word<2;response_word=response_word+1) begin:g_response_address_word
            assign dcache_resp_addr_o[response_word*16 +: 16]=response_output_views[2*(RESPONSE_TAG_WORDS+response_word)]?
                core_req_addr[response_word*16 +: 16]:resp_addr_reg[response_word*16 +: 16];
        end
        for(response_word=0;response_word<8;response_word=response_word+1) begin:g_response_line_word
            wire bypass=response_output_views[2*(RESPONSE_TAG_WORDS+2+response_word)];
            wire deferred=response_output_views[2*(RESPONSE_TAG_WORDS+2+response_word)+1];
            assign dcache_resp_line_data_o[response_word*16 +: 16]=(WORD_RESPONSE!=0)?16'b0:
                ((bypass || deferred)?data_rdata[response_word*16 +: 16]:resp_line_reg[response_word*16 +: 16]);
        end
        for(response_word=0;response_word<2;response_word=response_word+1) begin:g_response_value_word
            wire bypass=response_output_views[2*(RESPONSE_TAG_WORDS+10+response_word)];
            wire deferred=response_output_views[2*(RESPONSE_TAG_WORDS+10+response_word)+1];
            assign dcache_resp_word_data_o[response_word*16 +: 16]=bypass?
                response_hit_word[response_word*16 +: 16]:(deferred?
                    response_deferred_word[response_word*16 +: 16]:resp_word_reg[response_word*16 +: 16]);
        end
    endgenerate
    assign dcache_resp_line_valid_o=(WORD_RESPONSE==0) && (response_output_views[2*(RESPONSE_OUTPUT_WORDS-1)] || resp_line_valid_reg);
    assign dcache_resp_error_o=!response_output_views[2*(RESPONSE_OUTPUT_WORDS-1)] && resp_error_reg;
    // The synchronous tag query already holds an accepted committed store.
    // Acknowledge at the SAME edge that writes its hit bytes or transfers
    // ownership into an MSHR. Do not add a second registered reply cycle.
    // If the consumer is stalled, retain the acknowledgement exactly once.
    wire bypass_store_ack = (TAG_SRAM != 0) && request_fire &&
                             request_is_store && !request_writearound_new && !ack_valid_reg;
    assign dcache_store_ack_valid_o = ack_valid_reg || bypass_store_ack;
    wire [RESPONSE_TAG_WORDS:0] ack_output_views;
    rv32_frequency_control_tree #(.LEAVES(RESPONSE_TAG_WORDS+1)) ack_output_tree (
        .signal_i(bypass_store_ack),.views_o(ack_output_views));
    generate for(response_word=0;response_word<RESPONSE_TAG_WORDS;response_word=response_word+1) begin:g_ack_tag_word
        localparam integer LOW=response_word*16;
        localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
        assign dcache_store_ack_lsq_tag_o[LOW +: BITS]=ack_output_views[response_word]?
            core_req_lsq_tag[LOW +: BITS]:ack_lsq_reg[LOW +: BITS];
    end endgenerate
    assign dcache_store_ack_error_o = !ack_output_views[RESPONSE_TAG_WORDS] && ack_error_reg;
    // Private candidate identity, meaningful only with actual ack-valid.
    // A saved ack wins; otherwise a valid bypass must belong to core_req.
    // Public valid/tag/error and all capture/consumption rules stay exact.
    wire [RESPONSE_TAG_WORDS-1:0] saved_ack_identity_views;
    rv32_frequency_control_tree #(.LEAVES(RESPONSE_TAG_WORDS)) ack_identity_tree (
        .signal_i(ack_valid_reg),.views_o(saved_ack_identity_views));
    generate for(genvar query_word=0;query_word<RESPONSE_TAG_WORDS;query_word=query_word+1) begin:g_ack_query_tag
        localparam integer LOW=query_word*16;
        localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
        assign dcache_store_ack_query_tag_o[LOW +: BITS]=saved_ack_identity_views[query_word] ?
            ack_lsq_reg[LOW +: BITS] : core_req_lsq_tag[LOW +: BITS];
    end endgenerate

    assign mem_req_valid_o = send_found;
    assign mem_req_write_o = send_found && query_send_mshr_writeback;
    wire [7:0] memory_write_data_enable,memory_victim_bypass;
    wire [1:0] memory_line_enable,memory_line_victim;
    wire memory_write=send_found && query_send_mshr_writeback;
    rv32_frequency_control_tree #(.LEAVES(8)) memory_write_tree (
        .signal_i(memory_write),.views_o(memory_write_data_enable));
    rv32_frequency_control_tree #(.LEAVES(8)) memory_victim_bypass_tree (
        .signal_i(victim_from_sram && victim_mshr_reg==send_index),.views_o(memory_victim_bypass));
    rv32_frequency_control_tree #(.LEAVES(2)) memory_line_enable_tree (
        .signal_i(send_found),.views_o(memory_line_enable));
    rv32_frequency_control_tree #(.LEAVES(2)) memory_line_victim_tree (
        .signal_i(query_send_mshr_writeback),.views_o(memory_line_victim));
    genvar memory_word;
    generate
        for(memory_word=0;memory_word<8;memory_word=memory_word+1) begin:g_memory_write_word
            wire [15:0] selected_data=memory_victim_bypass[memory_word]?
                data_rdata[memory_word*16 +: 16]:query_send_mshr_victim_data[memory_word*16 +: 16];
            assign mem_req_wdata_o[memory_word*16 +: 16]={16{memory_write_data_enable[memory_word]}} & selected_data;
        end
        for(memory_word=0;memory_word<2;memory_word=memory_word+1) begin:g_memory_address_word
            wire [31:0] demand_line={query_send_mshr_addr[31:4],4'b0};
            wire unused_demand_line_bits = &{1'b0, demand_line};

            wire [15:0] selected_address=memory_line_victim[memory_word]?
                query_send_mshr_victim_addr[memory_word*16 +: 16]:demand_line[memory_word*16 +: 16];
            assign mem_req_line_addr_o[memory_word*16 +: 16]={16{memory_line_enable[memory_word]}} & selected_address;
        end
    endgenerate
    assign mem_req_wmask_o = send_found && query_send_mshr_writeback ?
                             (query_send_writearound ? query_send_mshr_mask : 16'hffff) : 16'd0;
    assign mem_req_id_o = send_found ? 8'(send_index) : 8'd0;
    assign mem_resp_ready_o = response_found && !response_needs_output &&
        !(hit_coissue_holds_slot && response_emits_load);
    // Demand refills and failed victim writebacks both own a load reply.
    // A waiter must retain its ready row whenever either producer captures.
    wire load_response_capture=mem_resp_valid_i && mem_resp_ready_o && response_emits_load;

    function automatic [127:0] merge_store;
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

    localparam integer MSHR_READ_WIDTH=TAG_WIDTH+CACHE_ENTRY_WIDTH+342;
    wire [MSHR_ENTRIES*MSHR_READ_WIDTH-1:0] mshr_read_rows;
    genvar mshr_read_row;
    generate for(mshr_read_row=0;mshr_read_row<MSHR_ENTRIES;mshr_read_row=mshr_read_row+1) begin:g_mshr_read_rows
        assign mshr_read_rows[mshr_read_row*MSHR_READ_WIDTH +: MSHR_READ_WIDTH]={mshr_victim_data[mshr_read_row],mshr_victim_entry[mshr_read_row],mshr_victim_addr[mshr_read_row],mshr_lsq[mshr_read_row],mshr_wdata[mshr_read_row],mshr_mask[mshr_read_row],mshr_unsigned[mshr_read_row],mshr_size[mshr_read_row],mshr_addr[mshr_read_row],mshr_writeback[mshr_read_row],mshr_prefetch[mshr_read_row],mshr_store[mshr_read_row]};
    end endgenerate
    wire [127:0] query_send_mshr_victim_data;
    wire [CACHE_ENTRY_WIDTH-1:0] query_send_mshr_victim_entry;
    wire unused_query_send_mshr_victim_entry_bits = &{1'b0, query_send_mshr_victim_entry};

    wire [31:0] query_send_mshr_victim_addr;
    wire [TAG_WIDTH-1:0] query_send_mshr_lsq;
    wire unused_query_send_mshr_lsq_bits = &{1'b0, query_send_mshr_lsq};

    wire [127:0] query_send_mshr_wdata;
    wire unused_query_send_mshr_wdata_bits = &{1'b0, query_send_mshr_wdata};

    wire [15:0] query_send_mshr_mask;
    wire unused_query_send_mshr_mask_bits = &{1'b0, query_send_mshr_mask};

    wire query_send_mshr_unsigned;
    wire unused_query_send_mshr_unsigned_bits = &{1'b0, query_send_mshr_unsigned};

    wire [1:0] query_send_mshr_size;
    wire unused_query_send_mshr_size_bits = &{1'b0, query_send_mshr_size};

    wire [31:0] query_send_mshr_addr;
    wire unused_query_send_mshr_addr_bits = &{1'b0, query_send_mshr_addr};

    wire query_send_mshr_writeback;
    wire query_send_mshr_prefetch;
    wire unused_query_send_mshr_prefetch_bits = &{1'b0, query_send_mshr_prefetch};

    wire query_send_mshr_store;
    wire unused_query_send_mshr_store_bits = &{1'b0, query_send_mshr_store};

    rv32_frequency_array_read #(.WIDTH(MSHR_READ_WIDTH),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) send_read (
        .rows_i(mshr_read_rows),.index_i(send_index),.value_o({query_send_mshr_victim_data,query_send_mshr_victim_entry,query_send_mshr_victim_addr,query_send_mshr_lsq,query_send_mshr_wdata,query_send_mshr_mask,query_send_mshr_unsigned,query_send_mshr_size,query_send_mshr_addr,query_send_mshr_writeback,query_send_mshr_prefetch,query_send_mshr_store}));
    wire [127:0] query_matching_mshr_victim_data;
    wire unused_query_matching_mshr_victim_data_bits = &{1'b0, query_matching_mshr_victim_data};

    wire [CACHE_ENTRY_WIDTH-1:0] query_matching_mshr_victim_entry;
    wire unused_query_matching_mshr_victim_entry_bits = &{1'b0, query_matching_mshr_victim_entry};

    wire [31:0] query_matching_mshr_victim_addr;
    wire unused_query_matching_mshr_victim_addr_bits = &{1'b0, query_matching_mshr_victim_addr};

    wire [TAG_WIDTH-1:0] query_matching_mshr_lsq;
    wire unused_query_matching_mshr_lsq_bits = &{1'b0, query_matching_mshr_lsq};

    wire [127:0] query_matching_mshr_wdata;
    wire [15:0] query_matching_mshr_mask;
    wire query_matching_mshr_unsigned;
    wire unused_query_matching_mshr_unsigned_bits = &{1'b0, query_matching_mshr_unsigned};

    wire [1:0] query_matching_mshr_size;
    wire unused_query_matching_mshr_size_bits = &{1'b0, query_matching_mshr_size};

    wire [31:0] query_matching_mshr_addr;
    wire unused_query_matching_mshr_addr_bits = &{1'b0, query_matching_mshr_addr};

    wire query_matching_mshr_writeback;
    wire unused_query_matching_mshr_writeback_bits = &{1'b0, query_matching_mshr_writeback};

    wire query_matching_mshr_prefetch;
    wire query_matching_mshr_store;
    rv32_frequency_array_read #(.WIDTH(MSHR_READ_WIDTH),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) matching_read (
        .rows_i(mshr_read_rows),.index_i(matching_index),.value_o({query_matching_mshr_victim_data,query_matching_mshr_victim_entry,query_matching_mshr_victim_addr,query_matching_mshr_lsq,query_matching_mshr_wdata,query_matching_mshr_mask,query_matching_mshr_unsigned,query_matching_mshr_size,query_matching_mshr_addr,query_matching_mshr_writeback,query_matching_mshr_prefetch,query_matching_mshr_store}));
    wire [127:0] query_local_mshr_victim_data;
    wire unused_query_local_mshr_victim_data_bits = &{1'b0, query_local_mshr_victim_data};

    wire [CACHE_ENTRY_WIDTH-1:0] query_local_mshr_victim_entry;
    wire [31:0] query_local_mshr_victim_addr;
    wire unused_query_local_mshr_victim_addr_bits = &{1'b0, query_local_mshr_victim_addr};

    wire [TAG_WIDTH-1:0] query_local_mshr_lsq;
    wire unused_query_local_mshr_lsq_bits = &{1'b0, query_local_mshr_lsq};

    wire [127:0] query_local_mshr_wdata;
    wire [15:0] query_local_mshr_mask;
    wire unused_query_local_mshr_mask_bits = &{1'b0, query_local_mshr_mask};

    wire query_local_mshr_unsigned;
    wire unused_query_local_mshr_unsigned_bits = &{1'b0, query_local_mshr_unsigned};

    wire [1:0] query_local_mshr_size;
    wire unused_query_local_mshr_size_bits = &{1'b0, query_local_mshr_size};

    wire [31:0] query_local_mshr_addr;
    wire unused_query_local_mshr_addr_bits = &{1'b0, query_local_mshr_addr};

    wire query_local_mshr_writeback;
    wire unused_query_local_mshr_writeback_bits = &{1'b0, query_local_mshr_writeback};

    wire query_local_mshr_prefetch;
    wire unused_query_local_mshr_prefetch_bits = &{1'b0, query_local_mshr_prefetch};

    wire query_local_mshr_store;
    wire unused_query_local_mshr_store_bits = &{1'b0, query_local_mshr_store};

    rv32_frequency_array_read #(.WIDTH(MSHR_READ_WIDTH),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(3)) local_read (
        .rows_i(mshr_read_rows),.index_i(local_fill_index),.value_o({query_local_mshr_victim_data,query_local_mshr_victim_entry,query_local_mshr_victim_addr,query_local_mshr_lsq,query_local_mshr_wdata,query_local_mshr_mask,query_local_mshr_unsigned,query_local_mshr_size,query_local_mshr_addr,query_local_mshr_writeback,query_local_mshr_prefetch,query_local_mshr_store}));
    wire [127:0] query_response_mshr_victim_data;
    wire unused_query_response_mshr_victim_data_bits = &{1'b0, query_response_mshr_victim_data};

    wire [CACHE_ENTRY_WIDTH-1:0] query_response_mshr_victim_entry;
    wire [31:0] query_response_mshr_victim_addr;
    wire unused_query_response_mshr_victim_addr_bits = &{1'b0, query_response_mshr_victim_addr};

    wire [TAG_WIDTH-1:0] query_response_mshr_lsq;
    wire [127:0] query_response_mshr_wdata;
    wire [15:0] query_response_mshr_mask;
    wire query_response_mshr_unsigned;
    wire [1:0] query_response_mshr_size;
    wire [31:0] query_response_mshr_addr;
    wire query_response_mshr_writeback;
    wire query_response_mshr_prefetch;
    wire query_response_mshr_store;
    rv32_frequency_array_read #(.WIDTH(MSHR_READ_WIDTH),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(8)) response_read (
        .rows_i(mshr_read_rows),.index_i(mem_resp_id_i),.value_o({query_response_mshr_victim_data,query_response_mshr_victim_entry,query_response_mshr_victim_addr,query_response_mshr_lsq,query_response_mshr_wdata,query_response_mshr_mask,query_response_mshr_unsigned,query_response_mshr_size,query_response_mshr_addr,query_response_mshr_writeback,query_response_mshr_prefetch,query_response_mshr_store}));
    localparam integer WAITER_READ_WIDTH=TAG_WIDTH+39+WAITER_DATA_WIDTH;
    wire [WAITER_ENTRIES*WAITER_READ_WIDTH-1:0] waiter_read_rows;
    genvar waiter_read_row;
    generate for(waiter_read_row=0;waiter_read_row<WAITER_ENTRIES;waiter_read_row=waiter_read_row+1) begin:g_waiter_read_rows
        assign waiter_read_rows[waiter_read_row*WAITER_READ_WIDTH +: WAITER_READ_WIDTH]={waiter_line[waiter_read_row],waiter_lsq[waiter_read_row],waiter_unsigned[waiter_read_row],waiter_size[waiter_read_row],waiter_addr[waiter_read_row],waiter_mshr[waiter_read_row],waiter_error[waiter_read_row]};
    end endgenerate
    wire [WAITER_DATA_WIDTH-1:0] query_waiter_load_waiter_line;
    wire [TAG_WIDTH-1:0] query_waiter_load_waiter_lsq;
    wire query_waiter_load_waiter_unsigned;
    wire unused_query_waiter_load_waiter_unsigned_bits = &{1'b0, query_waiter_load_waiter_unsigned};

    wire [1:0] query_waiter_load_waiter_size;
    wire unused_query_waiter_load_waiter_size_bits = &{1'b0, query_waiter_load_waiter_size};

    wire [31:0] query_waiter_load_waiter_addr;
    wire [2:0] query_waiter_load_waiter_mshr;
    wire unused_query_waiter_load_waiter_mshr_bits = &{1'b0, query_waiter_load_waiter_mshr};

    wire query_waiter_load_waiter_error;
    rv32_frequency_array_read #(.WIDTH(WAITER_READ_WIDTH),.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_load_read (
        .rows_i(waiter_read_rows),.index_i(waiter_load_ready_index),.value_o({query_waiter_load_waiter_line,query_waiter_load_waiter_lsq,query_waiter_load_waiter_unsigned,query_waiter_load_waiter_size,query_waiter_load_waiter_addr,query_waiter_load_waiter_mshr,query_waiter_load_waiter_error}));
    wire [WAITER_DATA_WIDTH-1:0] query_waiter_store_waiter_line;
    wire unused_query_waiter_store_waiter_line_bits = &{1'b0, query_waiter_store_waiter_line};

    wire [TAG_WIDTH-1:0] query_waiter_store_waiter_lsq;
    wire query_waiter_store_waiter_unsigned;
    wire unused_query_waiter_store_waiter_unsigned_bits = &{1'b0, query_waiter_store_waiter_unsigned};

    wire [1:0] query_waiter_store_waiter_size;
    wire unused_query_waiter_store_waiter_size_bits = &{1'b0, query_waiter_store_waiter_size};

    wire [31:0] query_waiter_store_waiter_addr;
    wire unused_query_waiter_store_waiter_addr_bits = &{1'b0, query_waiter_store_waiter_addr};

    wire [2:0] query_waiter_store_waiter_mshr;
    wire unused_query_waiter_store_waiter_mshr_bits = &{1'b0, query_waiter_store_waiter_mshr};

    wire query_waiter_store_waiter_error;
    rv32_frequency_array_read #(.WIDTH(WAITER_READ_WIDTH),.ENTRIES(WAITER_ENTRIES),.INDEX_WIDTH(WAITER_SLOT_WIDTH)) waiter_store_read (
        .rows_i(waiter_read_rows),.index_i(waiter_store_ready_index),.value_o({query_waiter_store_waiter_line,query_waiter_store_waiter_lsq,query_waiter_store_waiter_unsigned,query_waiter_store_waiter_size,query_waiter_store_waiter_addr,query_waiter_store_waiter_mshr,query_waiter_store_waiter_error}));

    integer reset_index;

    wire unused_line_index_bits = &{1'b0, query_response_mshr_victim_entry};

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
                     query_matching_mshr_store && matching_store_covers_load)
                static_request_action = 4'd3;
            else if (request_is_load && matching_found && matching_prefetch)
                static_request_action = 4'd4;
            else if (request_is_load && matching_found)
                static_request_action = 4'd5;
            else if (request_is_store && matching_found && matching_prefetch)
                static_request_action = 4'd6;
            else if (request_is_store && matching_found && query_matching_mshr_store)
                static_request_action = 4'd7;
            else
                static_request_action = request_writearound_new ? 4'd9 : 4'd8;
        end
    end
    wire static_prefetch_allocate = (static_request_action == 4'd8) &&
        (PREFETCH != 0) && request_is_load && second_free_found &&
        !prefetch_cache_hit && !prefetch_line_present && !prefetch_index_conflict &&
        (prefetch_index != request_index) &&
        !(prefetch_victim_valid && prefetch_victim_dirty);

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
        wire [CACHE_ENTRY_WIDTH-1:0] local_entry = query_local_mshr_victim_entry;
        wire [CACHE_ENTRY_WIDTH-1:0] refill_entry = query_response_mshr_victim_entry;
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
                        static_dirty_bits[update_row] <= query_response_mshr_store;
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
                ((static_request_action == 4'd8 || (STORE_MISS_WRITE_AROUND != 0 && static_request_action == 4'd9)) && free_index == update_mshr) ||
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
`ifdef CPU2026_WORD_SIM
        if (CACHE_LINES == 1024 && CACHE_WAYS == 2 && LOCAL_METADATA_ACTIVE != 0) begin : g_word_metadata
            // All banks capture the same accepted address on the same edge.
            // Share that address in simulation and update only touched words.
            rv32_dcache_metadata_word state_words (
                .clk_i(clk_i), .reset_i(reset_i),
                .request_action_i(static_request_action),
                .refill_valid_i(refill_array_write),
                .refill_entry_i(query_response_mshr_victim_entry),
                .refill_dirty_i(query_response_mshr_store),
                .local_valid_i(local_array_write),
                .local_entry_i(query_local_mshr_victim_entry),
                .miss_way_i(request_victim_entry[0]),
                .prefetch_valid_i(static_prefetch_allocate),
                .prefetch_way_i(prefetch_victim_entry[0]),
                .hit_way_i(request_hit_entry[0]),
                .query_fire_i(dcache_req_valid_i && dcache_req_ready_o),
                .query_request_set_i(cache_index(dcache_req_addr_i)),
                .query_prefetch_set_i(cache_index({dcache_req_addr_i[31:4],4'b0}+32'd16)),
                .query_request_valid_o(request_query_valid),
                .query_request_dirty_o(request_query_dirty),
                .query_prefetch_valid_o(prefetch_query_valid),
                .query_prefetch_dirty_o(prefetch_query_dirty),
                .query_request_lru_o(request_query_lru),
                .query_prefetch_lru_o(prefetch_query_lru),
                .valid_o(valid_bits), .dirty_o(dirty_bits), .lru_o(lru_way_mem)
            );
        end else begin : g_original_metadata
`endif
        wire [GROUP_COUNT*CACHE_WAYS-1:0] group_request_valid, group_request_dirty;
        wire [GROUP_COUNT*CACHE_WAYS-1:0] group_prefetch_valid, group_prefetch_dirty;
        wire [GROUP_COUNT-1:0] group_request_lru, group_prefetch_lru;
        if (LOCAL_METADATA_ACTIVE != 0) begin : g_query_reduce
            reg [CACHE_WAYS-1:0] combined_request_valid, combined_request_dirty;
            reg [CACHE_WAYS-1:0] combined_prefetch_valid, combined_prefetch_dirty;
            integer query_group;
            always @* begin
                combined_request_valid = {CACHE_WAYS{1'b0}};
                combined_request_dirty = {CACHE_WAYS{1'b0}};
                combined_prefetch_valid = {CACHE_WAYS{1'b0}};
                combined_prefetch_dirty = {CACHE_WAYS{1'b0}};
                for (query_group = 0; query_group < GROUP_COUNT; query_group = query_group + 1) begin
                    combined_request_valid = combined_request_valid |
                        group_request_valid[query_group*CACHE_WAYS +: CACHE_WAYS];
                    combined_request_dirty = combined_request_dirty |
                        group_request_dirty[query_group*CACHE_WAYS +: CACHE_WAYS];
                    combined_prefetch_valid = combined_prefetch_valid |
                        group_prefetch_valid[query_group*CACHE_WAYS +: CACHE_WAYS];
                    combined_prefetch_dirty = combined_prefetch_dirty |
                        group_prefetch_dirty[query_group*CACHE_WAYS +: CACHE_WAYS];
                end
            end
            assign request_query_valid = combined_request_valid;
            assign request_query_dirty = combined_request_dirty;
            assign prefetch_query_valid = combined_prefetch_valid;
            assign prefetch_query_dirty = combined_prefetch_dirty;
            assign request_query_lru = |group_request_lru;
            assign prefetch_query_lru = |group_prefetch_lru;
        end
        wire [CACHE_ENTRY_WIDTH-1:0] local_entry = query_local_mshr_victim_entry;
        wire [CACHE_ENTRY_WIDTH-1:0] refill_entry = query_response_mshr_victim_entry;
        // The CD1 mapped victim-way driver fed 1255 pins. A bank-local
        // decode does not bound the shared input's load across 64 banks.
        // Distribute every metadata input after its final qualification;
        // each leaf feeds exactly one existing state owner on the same edge.
        // Local-query owners already latched set/row identities. They
        // consume only way bits of miss/prefetch/hit entries and never use
        // the non-query request/prefetch set ports. Preserve full fields in
        // the legacy query mode; current 1/2-way mode needs one way bit.
        localparam integer METADATA_SELECT_WIDTH=LOCAL_METADATA_ACTIVE ? 1:CACHE_ENTRY_WIDTH;
        localparam integer METADATA_SET_WIDTH=LOCAL_METADATA_ACTIVE ? 1:CACHE_INDEX_WIDTH;
        localparam integer METADATA_INPUT_WIDTH=9+2*CACHE_ENTRY_WIDTH+3*METADATA_SELECT_WIDTH+
            2*METADATA_SET_WIDTH+2*CACHE_INDEX_WIDTH;
        wire [GROUP_COUNT*METADATA_INPUT_WIDTH-1:0] metadata_input_views;
        rv32_frequency_control_tree #(.WIDTH(METADATA_INPUT_WIDTH),.LEAVES(GROUP_COUNT)) metadata_input_tree (
            .signal_i({static_request_action,refill_array_write,refill_entry,query_response_mshr_store,
                       local_array_write,local_entry,request_victim_entry[METADATA_SELECT_WIDTH-1:0],
                       static_prefetch_allocate,prefetch_victim_entry[METADATA_SELECT_WIDTH-1:0],
                       request_hit_entry[METADATA_SELECT_WIDTH-1:0],
                       (LOCAL_METADATA_ACTIVE ? {METADATA_SET_WIDTH{1'b0}}:request_index[METADATA_SET_WIDTH-1:0]),
                       (LOCAL_METADATA_ACTIVE ? {METADATA_SET_WIDTH{1'b0}}:prefetch_index[METADATA_SET_WIDTH-1:0]),
                       dcache_req_valid_i && dcache_req_ready_o,
                       cache_index(dcache_req_addr_i),
                       cache_index({dcache_req_addr_i[31:4],4'b0}+32'd16)}),
            .views_o(metadata_input_views));
        // These modules own the actual state and its address-qualified write
        // logic. No extra cycle, buffer-cell stub or replacement SRAM is used.
        for (update_group = 0; update_group < GROUP_COUNT; update_group = update_group + 1) begin : g_metadata
            wire [3:0] metadata_action;
            wire metadata_refill,metadata_refill_dirty,metadata_local,metadata_prefetch,metadata_query_fire;
            wire [CACHE_ENTRY_WIDTH-1:0] metadata_refill_entry,metadata_local_entry,
                metadata_miss_entry,metadata_prefetch_entry,metadata_hit_entry;
            wire [CACHE_INDEX_WIDTH-1:0] metadata_request_set,metadata_prefetch_set,
                metadata_query_request_set,metadata_query_prefetch_set;
            wire [METADATA_SELECT_WIDTH-1:0] metadata_miss_select,metadata_prefetch_select,metadata_hit_select;
            wire [METADATA_SET_WIDTH-1:0] metadata_request_set_field,metadata_prefetch_set_field;
            assign metadata_miss_entry={{(CACHE_ENTRY_WIDTH-METADATA_SELECT_WIDTH){1'b0}},metadata_miss_select};
            assign metadata_prefetch_entry={{(CACHE_ENTRY_WIDTH-METADATA_SELECT_WIDTH){1'b0}},metadata_prefetch_select};
            assign metadata_hit_entry={{(CACHE_ENTRY_WIDTH-METADATA_SELECT_WIDTH){1'b0}},metadata_hit_select};
            assign metadata_request_set={{(CACHE_INDEX_WIDTH-METADATA_SET_WIDTH){1'b0}},metadata_request_set_field};
            assign metadata_prefetch_set={{(CACHE_INDEX_WIDTH-METADATA_SET_WIDTH){1'b0}},metadata_prefetch_set_field};
            assign {metadata_action,metadata_refill,metadata_refill_entry,metadata_refill_dirty,
                    metadata_local,metadata_local_entry,metadata_miss_select,
                    metadata_prefetch,metadata_prefetch_select,metadata_hit_select,
                    metadata_request_set_field,metadata_prefetch_set_field,metadata_query_fire,
                    metadata_query_request_set,metadata_query_prefetch_set}=
                metadata_input_views[update_group*METADATA_INPUT_WIDTH +: METADATA_INPUT_WIDTH];
            rv32_dcache_metadata_bank #(
                .CACHE_LINES(CACHE_LINES), .CACHE_WAYS(CACHE_WAYS),
                .GROUP_ROWS(GROUP_ROWS), .GROUP_ID(update_group), .LOCAL_QUERY(LOCAL_METADATA_ACTIVE),
                .LOCAL_ACTION_DECODE(LOCAL_ACTION_DECODE),
                .ENTRY_WIDTH(CACHE_ENTRY_WIDTH), .SET_WIDTH(CACHE_INDEX_WIDTH)
            ) state_bank (
                .clk_i(clk_i), .reset_i(reset_i),
                .request_action_i(metadata_action),
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
                .query_prefetch_set_i(metadata_query_prefetch_set),
                .query_request_valid_o(group_request_valid[update_group*CACHE_WAYS +: CACHE_WAYS]),
                .query_request_dirty_o(group_request_dirty[update_group*CACHE_WAYS +: CACHE_WAYS]),
                .query_prefetch_valid_o(group_prefetch_valid[update_group*CACHE_WAYS +: CACHE_WAYS]),
                .query_prefetch_dirty_o(group_prefetch_dirty[update_group*CACHE_WAYS +: CACHE_WAYS]),
                .query_request_lru_o(group_request_lru[update_group]),
                .query_prefetch_lru_o(group_prefetch_lru[update_group]),
                .valid_o(valid_bits[update_group*GROUP_ROWS +: GROUP_ROWS]),
                .dirty_o(dirty_bits[update_group*GROUP_ROWS +: GROUP_ROWS]),
                .lru_o(lru_way_mem[update_group*GROUP_SETS +: GROUP_SETS])
            );
        end
`ifdef CPU2026_WORD_SIM
        end
`endif
        for (update_mshr = 0; update_mshr < MSHR_ENTRIES; update_mshr = update_mshr + 1) begin : g_mshr_data
            rv32_dcache_mshr_data_bank #(.MSHR_ID(update_mshr),
                .STORE_MISS_WRITE_AROUND(STORE_MISS_WRITE_AROUND)) state_bank (
                .clk_i(clk_i), .reset_i(reset_i), .request_action_i(static_request_action),
                .prefetch_allocate_i(static_prefetch_allocate), .second_free_i(second_free_index[2:0]),
                .free_i(free_index[2:0]), .matching_i(matching_index[2:0]),
                .write_mask_i(core_req_mask), .write_data_i(core_req_wdata),
                .data_o(mshr_wdata[update_mshr])
            );
        end
    end endgenerate

    // Allocation initializes every field before mshr_valid exposes it. A
    // promoted prefetch replaces only the demand descriptor; masked store
    // merging retains all older bytes. Lifecycle validity remains separate.
    localparam integer MSHR_PAYLOAD_DOMAINS=(MSHR_ENTRIES+3)/4;
    localparam integer MSHR_DEMAND_WIDTH=TAG_WIDTH+35;
    localparam integer MSHR_VICTIM_WIDTH=CACHE_ENTRY_WIDTH+32;
    localparam integer MSHR_ACTION_WIDTH=17;
    localparam integer MSHR_ARRAY_INDEX_WIDTH=(MSHR_ENTRIES<=1)?1:$clog2(MSHR_ENTRIES);
    wire [MSHR_PAYLOAD_DOMAINS*MSHR_ACTION_WIDTH-1:0] mshr_action_views;
    rv32_frequency_control_tree #(.WIDTH(MSHR_ACTION_WIDTH),.LEAVES(MSHR_PAYLOAD_DOMAINS)) mshr_action_tree (
        .signal_i({1'b0,reset_i,static_prefetch_allocate,victim_from_sram,
                   second_free_index[2:0],free_index[2:0],matching_index[2:0],static_request_action}),
        .views_o(mshr_action_views));
    genvar payload_mshr;
    generate for(payload_mshr=0;payload_mshr<MSHR_ENTRIES;payload_mshr=payload_mshr+1) begin:g_mshr_payload_owner
        wire local_reset,prefetch_allocate,victim_copy;
        wire [2:0] second_slot,free_slot,matching_slot;
        wire [3:0] action;
        assign {local_reset,prefetch_allocate,victim_copy,second_slot,free_slot,matching_slot,action}=
            16'(mshr_action_views[(payload_mshr/4)*MSHR_ACTION_WIDTH +: MSHR_ACTION_WIDTH]);
        wire load_promote=!local_reset && action==4'd4 && matching_slot==payload_mshr;
        wire store_promote=!local_reset && action==4'd6 && matching_slot==payload_mshr;
        wire store_merge=!local_reset && action==4'd7 && matching_slot==payload_mshr;
        wire around_allocate=(STORE_MISS_WRITE_AROUND != 0) && action==4'd9;
        wire demand_allocate=!local_reset && (action==4'd8 || around_allocate) && free_slot==payload_mshr;
        wire prefetch_new=!local_reset && prefetch_allocate && second_slot==payload_mshr;
        wire demand_write;
        wire [MSHR_DEMAND_WIDTH-1:0] demand_next,demand_saved;
        rv32_frequency_event_select #(.WIDTH(MSHR_DEMAND_WIDTH),.EVENTS(4)) demand_selector (
            .events_i({prefetch_new,demand_allocate,store_promote,load_promote}),
            .values_i({
                {TAG_WIDTH{1'b0}},1'b1,`RV32IM_MEM_WORD,prefetch_line_addr,
                core_req_lsq_tag,core_req_unsigned,core_req_size,core_req_addr,
                core_req_lsq_tag,1'b0,core_req_size,core_req_addr,
                core_req_lsq_tag,core_req_unsigned,core_req_size,core_req_addr}),
            .write_o(demand_write),.value_o(demand_next));
        rv32_frequency_word_bank #(.WIDTH(MSHR_DEMAND_WIDTH)) demand_owner (
            .clk_i(clk_i),.write_i(demand_write),.data_i(demand_next),.data_o(demand_saved));
        assign {mshr_lsq[payload_mshr],mshr_unsigned[payload_mshr],
                mshr_size[payload_mshr],mshr_addr[payload_mshr]}=demand_saved;

        wire mask_write;
        wire [15:0] mask_next;
        rv32_frequency_event_select #(.WIDTH(16),.EVENTS(4)) mask_selector (
            .events_i({prefetch_new,demand_allocate,store_merge,store_promote}),
            .values_i({16'b0,(request_is_store?core_req_mask:16'b0),
                       (mshr_mask[payload_mshr] | core_req_mask),core_req_mask}),
            .write_o(mask_write),.value_o(mask_next));
        rv32_frequency_word_bank #(.WIDTH(16)) mask_owner (
            .clk_i(clk_i),.write_i(mask_write),.data_i(mask_next),.data_o(mshr_mask[payload_mshr]));

        wire victim_write;
        wire [MSHR_VICTIM_WIDTH-1:0] victim_next,victim_saved;
        rv32_frequency_event_select #(.WIDTH(MSHR_VICTIM_WIDTH),.EVENTS(2)) victim_selector (
            .events_i({prefetch_new,demand_allocate}),
            .values_i({prefetch_victim_entry,32'b0,request_victim_entry,
                (around_allocate ? request_line_addr :
                 victim_line_address(request_tags[(32'(request_victim_entry)%CACHE_WAYS)*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH],request_index))}),
            .write_o(victim_write),.value_o(victim_next));
        rv32_frequency_word_bank #(.WIDTH(MSHR_VICTIM_WIDTH)) victim_owner (
            .clk_i(clk_i),.write_i(victim_write),.data_i(victim_next),.data_o(victim_saved));
        assign {mshr_victim_entry[payload_mshr],mshr_victim_addr[payload_mshr]}=victim_saved;

        // Deferred synchronous SRAM capture precedes new allocation in the
        // original process. New demand/prefetch allocation wins on collision.
        wire victim_data_write;
        wire [127:0] victim_data_next;
        wire deferred_capture=!local_reset && victim_copy && victim_mshr_reg==payload_mshr;
        wire [127:0] allocated_victim=around_allocate ? core_req_wdata :
            ((request_dirty_victim && TAG_SRAM!=0)?data_rdata:128'b0);
        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(3)) victim_data_selector (
            .events_i({prefetch_new,demand_allocate,deferred_capture}),
            .values_i({128'b0,allocated_victim,data_rdata}),
            .write_o(victim_data_write),.value_o(victim_data_next));
        rv32_frequency_word_bank #(.WIDTH(128)) victim_data_owner (
            .clk_i(clk_i),.write_i(victim_data_write),.data_i(victim_data_next),.data_o(mshr_victim_data[payload_mshr]));
    end endgenerate

    localparam integer WAITER_DOMAINS=(WAITER_ENTRIES+3)/4;
    localparam integer WAITER_META_WIDTH=TAG_WIDTH+38;
    localparam integer WAITER_EVENT_WIDTH=13+3*WAITER_SLOT_WIDTH;
    wire waiter_allocate_event=static_request_action==4'd5;
    wire waiter_load_consume=resp_slot_free && waiter_load_ready_found &&
        !((HIT_RESPONSE_COISSUE!=0)?load_response_capture:demand_response_fire) &&
        !hit_coissue_holds_slot;
    wire waiter_store_consume=ack_slot_free && waiter_store_ready_found &&
        !store_response_fire && !response_emits_store;
    wire [WAITER_EVENT_WIDTH*WAITER_DOMAINS-1:0] waiter_event_views;
    rv32_frequency_control_tree #(.WIDTH(WAITER_EVENT_WIDTH),.LEAVES(WAITER_DOMAINS)) waiter_event_tree (
        .signal_i({reset_i,waiter_allocate_event,local_array_write,store_response_fire,demand_response_fire,
            waiter_load_consume,waiter_store_consume,waiter_free_index[WAITER_SLOT_WIDTH-1:0],
            waiter_load_ready_index[WAITER_SLOT_WIDTH-1:0],waiter_store_ready_index[WAITER_SLOT_WIDTH-1:0],
            local_fill_index[2:0],response_index[2:0]}),.views_o(waiter_event_views));
    wire [127:0] waiter_store_fill=merge_store(mem_resp_data_i,query_response_mshr_wdata,query_response_mshr_mask);
    // A response-store flag formerly controlled 128 mux bits for every
    // waiter group. Each waiter now receives eight sixteen-bit leaves.
    genvar waiter_row;
    generate for(waiter_row=0;waiter_row<WAITER_ENTRIES;waiter_row=waiter_row+1) begin:g_waiter_owner
        wire local_reset,allocate_event,local_event,store_event,demand_event,load_consume,store_consume;
        wire [WAITER_SLOT_WIDTH-1:0] free_slot,load_slot,store_slot;
        wire [2:0] local_mshr,response_mshr;
        assign {local_reset,allocate_event,local_event,store_event,demand_event,load_consume,store_consume,
                free_slot,load_slot,store_slot,local_mshr,response_mshr}=
            waiter_event_views[(waiter_row/4)*WAITER_EVENT_WIDTH +: WAITER_EVENT_WIDTH];
        wire allocate=!local_reset && allocate_event && free_slot==waiter_row;
        wire local_fill=!local_reset && local_event && waiter_valid[waiter_row] &&
            !waiter_ready[waiter_row] && waiter_mshr[waiter_row]==local_mshr;
        wire response_fill=!local_reset && waiter_valid[waiter_row] && !waiter_ready[waiter_row] &&
            waiter_mshr[waiter_row]==response_mshr &&
            (store_event || (demand_event && !waiter_store[waiter_row]));
        // This source has only load waiter allocations. There is no producer
        // of a store waiter; its former reset/allocation FF was always zero.
        assign waiter_store[waiter_row]=1'b0;
        wire [WAITER_META_WIDTH-1:0] saved_metadata;
        rv32_frequency_word_bank #(.WIDTH(WAITER_META_WIDTH)) metadata_owner (
            .clk_i(clk_i),.write_i(allocate),
            .data_i({core_req_lsq_tag,core_req_unsigned,core_req_size,core_req_addr,matching_index[2:0]}),
            .data_o(saved_metadata));
        assign {waiter_lsq[waiter_row],waiter_unsigned[waiter_row],waiter_size[waiter_row],
                waiter_addr[waiter_row],waiter_mshr[waiter_row]}=saved_metadata;
        wire line_write;
        wire [127:0] line_next;
        wire unused_line_next_bits = &{1'b0, line_next};

        wire [7:0] store_data_views;
        wire [127:0] response_line;
        rv32_frequency_control_tree #(.LEAVES(8)) store_data_tree (
            .signal_i(store_event),.views_o(store_data_views));
        for(genvar line_word=0;line_word<8;line_word=line_word+1) begin:g_response_word
            assign response_line[line_word*16 +: 16]=store_data_views[line_word]?
                waiter_store_fill[line_word*16 +: 16]:mem_resp_data_i[line_word*16 +: 16];
        end
        if(WORD_RESPONSE!=0) begin:g_word_waiter
            // Natural LB/LH/LW alignment never crosses an aligned word.
            // Choose that word before capture, and shift its low byte index
            // only after the original waiter selection. This avoids a full
            // four-bit line shifter for each waiter.
            wire [31:0] response_word_data,local_word_data,word_next;
            rv32_frequency_line_extract32 response_word_extract (
                .line_i(response_line),.offset_i({waiter_addr[waiter_row][3:2],2'b0}),
                .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_word_data));
            rv32_frequency_line_extract32 local_word_extract (
                .line_i(query_local_mshr_wdata),.offset_i({waiter_addr[waiter_row][3:2],2'b0}),
                .size_i(2'd2),.unsigned_i(1'b1),.value_o(local_word_data));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2)) word_selector (
                .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
                .values_i({response_word_data,local_word_data}),.write_o(line_write),.value_o(word_next));
            rv32_frequency_word_bank #(.WIDTH(32)) word_owner (
                .clk_i(clk_i),.write_i(line_write),.data_i(word_next),.data_o(waiter_line[waiter_row]));
            assign line_next=0;
        end else begin:g_line_waiter
            rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) line_selector (
                .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
                .values_i({response_line,query_local_mshr_wdata}),
                .write_o(line_write),.value_o(line_next));
            rv32_frequency_word_bank #(.WIDTH(128)) line_owner (
                .clk_i(clk_i),.write_i(line_write),.data_i(line_next),.data_o(waiter_line[waiter_row]));
        end
        wire error_write,error_next;
        rv32_frequency_event_select #(.WIDTH(1),.EVENTS(3)) error_selector (
            .events_i({response_fill,local_fill,allocate}),
            .values_i({(mem_resp_error_i || !response_matches),1'b0,1'b0}),
            .write_o(error_write),.value_o(error_next));
        rv32_frequency_word_bank #(.WIDTH(1)) error_owner (
            .clk_i(clk_i),.write_i(error_write),.data_i(error_next),.data_o(waiter_error[waiter_row]));
        always @(posedge clk_i) begin
            if(local_reset) begin
                waiter_valid[waiter_row]<=1'b0;
                waiter_ready[waiter_row]<=1'b0;
            end else begin
                if(allocate) begin waiter_valid[waiter_row]<=1'b1;waiter_ready[waiter_row]<=1'b0;end
                if(local_fill) waiter_ready[waiter_row]<=1'b1;
                if(load_consume && load_slot==waiter_row) begin
                    waiter_valid[waiter_row]<=1'b0;waiter_ready[waiter_row]<=1'b0;
                end
                if(store_consume && store_slot==waiter_row) begin
                    waiter_valid[waiter_row]<=1'b0;waiter_ready[waiter_row]<=1'b0;
                end
                // Memory response is the last original NBA writer.
                if(response_fill) waiter_ready[waiter_row]<=1'b1;
            end
        end
    end endgenerate

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
        wire around_allocate=(STORE_MISS_WRITE_AROUND != 0) && action==4'd9;
        wire demand_allocate=(action==4'd8 || around_allocate) && free_slot==lifecycle_mshr;
        wire prefetch_new=prefetch_allocate && second_slot==lifecycle_mshr;
        wire accept_response=response_accept && response_slot==lifecycle_mshr;
        wire initial_merge_hint=(STORE_MERGE_POLICY==0) || core_req_mask==16'h000f;
        wire [15:0] merged_store_mask=mshr_mask[lifecycle_mshr] | core_req_mask;
        wire prefix_extends=(merged_store_mask==16'h00ff || merged_store_mask==16'h0fff) &&
            merged_store_mask!=mshr_mask[lifecycle_mshr];
        wire rolling_merge=(STORE_MERGE_POLICY!=0) && action==4'd7 && matching_slot==lifecycle_mshr &&
            !mshr_sent[lifecycle_mshr] && !mshr_writeback[lifecycle_mshr] &&
            !mshr_rfo_offered[lifecycle_mshr] && prefix_extends;
        // Disabled policy adds no state. An around transaction never merges
        // later stores, so its write payload remains stable under backpressure.
        if (STORE_MISS_WRITE_AROUND != 0) begin:g_around_owner
            reg around;
            assign mshr_writearound[lifecycle_mshr]=around;
            always @(posedge clk_i) begin
                if(local_reset) around<=1'b0;
                else if(prefetch_new) around<=1'b0;
                else if(demand_allocate) around<=(action==4'd9);
            end
        end else begin:g_no_around
            assign mshr_writearound[lifecycle_mshr]=1'b0;
        end
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
                if(rolling_merge) mshr_merge_delay[lifecycle_mshr]<=MERGE_DELAY;
                if(rfo_offer && send_slot==lifecycle_mshr) mshr_rfo_offered[lifecycle_mshr]<=1'b1;
                if(load_promote) mshr_prefetch[lifecycle_mshr]<=1'b0;
                if(store_promote) begin
                    mshr_store[lifecycle_mshr]<=1'b1;
                    mshr_prefetch[lifecycle_mshr]<=1'b0;
                    mshr_merge_delay[lifecycle_mshr]<=initial_merge_hint?MERGE_DELAY:0;
                end
                if(demand_allocate) begin
                    mshr_valid[lifecycle_mshr]<=1'b1;
                    mshr_sent[lifecycle_mshr]<=1'b0;
                    mshr_rfo_offered[lifecycle_mshr]<=1'b0;
                    mshr_merge_delay[lifecycle_mshr]<=(request_store && initial_merge_hint)?MERGE_DELAY:0;
                    mshr_store[lifecycle_mshr]<=request_store;
                    mshr_prefetch[lifecycle_mshr]<=1'b0;
                    mshr_writeback[lifecycle_mshr]<=dirty_victim || around_allocate;
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
                    if(mshr_writeback[lifecycle_mshr] && !mshr_writearound[lifecycle_mshr] && response_success) begin
                        mshr_writeback[lifecycle_mshr]<=1'b0;
                        // The old timer expired during victim writeback. A
                        // sequential first word now gets its actual merge window.
                        if(STORE_MERGE_POLICY!=0 && mshr_store[lifecycle_mshr] &&
                           !mshr_rfo_offered[lifecycle_mshr] && mshr_mask[lifecycle_mshr]==16'h000f)
                            mshr_merge_delay[lifecycle_mshr]<=MERGE_DELAY;
                    end else mshr_valid[lifecycle_mshr]<=1'b0;
                end
            end
        end
    end endgenerate

    localparam integer DCACHE_RESPONSE_META_WIDTH=TAG_WIDTH+34;
    wire response_hit_capture=!reset_i && static_request_action==4'd1;
    wire response_forward_capture=!reset_i && static_request_action==4'd3;
    wire response_waiter_capture=!reset_i && waiter_load_consume;
    wire response_victim_failure=!reset_i && mem_resp_valid_i && mem_resp_ready_o &&
        query_response_mshr_writeback && (mem_resp_error_i || !response_matches);
    wire response_failed_load=response_victim_failure && !query_response_mshr_store;
    wire response_failed_store=response_victim_failure && query_response_mshr_store;
    wire response_around_store=!reset_i && mem_resp_valid_i && mem_resp_ready_o &&
        response_found && query_response_writearound;
    wire response_demand_capture=!reset_i && demand_response_fire;
    wire response_metadata_write;
    wire [DCACHE_RESPONSE_META_WIDTH-1:0] response_metadata_next,response_metadata_saved;
    rv32_frequency_event_select #(.WIDTH(DCACHE_RESPONSE_META_WIDTH),.EVENTS(5)) response_metadata_selector (
        .events_i({response_demand_capture,response_failed_load,response_waiter_capture,response_forward_capture,response_hit_capture}),
        .values_i({
            query_response_mshr_lsq,query_response_mshr_addr,(!mem_resp_error_i && response_matches),(mem_resp_error_i || !response_matches),
            query_response_mshr_lsq,query_response_mshr_addr,1'b0,1'b1,
            query_waiter_load_waiter_lsq,query_waiter_load_waiter_addr,!query_waiter_load_waiter_error,query_waiter_load_waiter_error,
            core_req_lsq_tag,core_req_addr,1'b1,1'b0,
            core_req_lsq_tag,core_req_addr,1'b1,1'b0}),
        .write_o(response_metadata_write),.value_o(response_metadata_next));
    rv32_frequency_word_bank #(.WIDTH(DCACHE_RESPONSE_META_WIDTH)) response_metadata_owner (
        .clk_i(clk_i),.write_i(response_metadata_write),.data_i(response_metadata_next),.data_o(response_metadata_saved));
    assign {resp_lsq_reg,resp_addr_reg,resp_line_valid_reg,resp_error_reg}=response_metadata_saved;

    wire [31:0] response_memory_word,response_waiter_word,response_forward_word;
    rv32_frequency_line_extract32 memory_extract (
        .line_i(mem_resp_data_i),.offset_i(query_response_mshr_addr[3:0]),
        .size_i((WORD_RESPONSE!=0)?2'd2:query_response_mshr_size),.unsigned_i((WORD_RESPONSE!=0)?1'b1:query_response_mshr_unsigned),.value_o(response_memory_word));
    generate if(WORD_RESPONSE!=0) begin:g_word_waiter_extract
        rv32_frequency_line_extract32 waiter_extract (
            .line_i({96'b0,query_waiter_load_waiter_line}),.offset_i({2'b0,query_waiter_load_waiter_addr[1:0]}),
            .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_waiter_word));
    end else begin:g_line_waiter_extract
        rv32_frequency_line_extract32 waiter_extract (
            .line_i(query_waiter_load_waiter_line),.offset_i(query_waiter_load_waiter_addr[3:0]),
            .size_i(query_waiter_load_waiter_size),.unsigned_i(query_waiter_load_waiter_unsigned),.value_o(response_waiter_word));
    end endgenerate
    rv32_frequency_line_extract32 forward_extract (
        .line_i(query_matching_mshr_wdata),.offset_i(core_req_addr[3:0]),
        .size_i((WORD_RESPONSE!=0)?2'd2:core_req_size),.unsigned_i((WORD_RESPONSE!=0)?1'b1:core_req_unsigned),.value_o(response_forward_word));
    wire response_data_write;
    wire response_sram_capture=!reset_i && resp_from_sram && resp_valid_reg;
    generate if(WORD_RESPONSE!=0) begin:g_word_response_owner
        wire [31:0] response_word_next;
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(6)) response_word_selector (
            .events_i({response_demand_capture,response_failed_load,response_waiter_capture,response_forward_capture,
                       response_hit_capture && TAG_SRAM!=0,response_sram_capture}),
            .values_i({response_memory_word,32'b0,response_waiter_word,response_forward_word,
                       response_hit_word,response_deferred_word}),
            .write_o(response_data_write),.value_o(response_word_next));
        rv32_frequency_word_bank #(.WIDTH(32)) response_word_owner (
            .clk_i(clk_i),.write_i(response_data_write),.data_i(response_word_next),.data_o(resp_word_reg));
        assign resp_line_reg=128'b0;
    end else begin:g_line_response_owner
    wire [159:0] response_data_next,response_data_saved;
    rv32_frequency_event_select #(.WIDTH(160),.EVENTS(6)) response_data_selector (
        .events_i({response_demand_capture,response_failed_load,response_waiter_capture,response_forward_capture,
                   response_hit_capture && TAG_SRAM!=0,response_sram_capture}),
        .values_i({
            mem_resp_data_i,response_memory_word,
            128'b0,32'b0,
            query_waiter_load_waiter_line,response_waiter_word,
            query_matching_mshr_wdata,response_forward_word,
            data_rdata,response_hit_word,
            data_rdata,response_deferred_word}),
        .write_o(response_data_write),.value_o(response_data_next));
    rv32_frequency_word_bank #(.WIDTH(160)) response_data_owner (
        .clk_i(clk_i),.write_i(response_data_write),.data_i(response_data_next),.data_o(response_data_saved));
    assign {resp_line_reg,resp_word_reg}=response_data_saved;
    end endgenerate
    // This metadata is read only while the deferred synchronous hit is live;
    // the accepting hit initializes it before resp_from_sram exposes it.
    wire [2:0] response_size_saved;
    rv32_frequency_word_bank #(.WIDTH(3)) response_size_owner (
        .clk_i(clk_i),.write_i(response_hit_capture),.data_i({core_req_size,core_req_unsigned}),.data_o(response_size_saved));
    assign {resp_size_reg,resp_unsigned_reg}=response_size_saved;

    wire ack_payload_write;
    wire [TAG_WIDTH:0] ack_payload_next,ack_payload_saved;
    rv32_frequency_event_select #(.WIDTH(TAG_WIDTH+1),.EVENTS(3)) acknowledgement_selector (
        .events_i({response_failed_store || response_around_store,!reset_i && waiter_store_consume,
                   !reset_i && request_fire && request_is_store && !request_writearound_new}),
        .values_i({query_response_mshr_lsq,((STORE_MISS_WRITE_AROUND != 0) ? (mem_resp_error_i || !response_matches) : 1'b1),
                   query_waiter_store_waiter_lsq,query_waiter_store_waiter_error,core_req_lsq_tag,1'b0}),
        .write_o(ack_payload_write),.value_o(ack_payload_next));
    rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH+1)) acknowledgement_owner (
        .clk_i(clk_i),.write_i(ack_payload_write),.data_i(ack_payload_next),.data_o(ack_payload_saved));
    assign {ack_lsq_reg,ack_error_reg}=ack_payload_saved;

    always @(posedge clk_i) begin
        if (reset_i)
        begin
            resp_valid_reg <= 1'b0;
            resp_from_sram <= 1'b0;
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
            if (STATIC_UPDATES == 0)
            begin
                legacy_valid_bits <= {CACHE_LINES{1'b0}};
                legacy_lru_way_mem <= {CACHE_SETS{1'b0}};
            end
            if(STATIC_UPDATES==0)
                for(reset_index=0;reset_index<MSHR_ENTRIES;reset_index=reset_index+1)
                    legacy_mshr_wdata[reset_index]<=128'b0;
        end
        else
        begin
            if (mem_req_valid_o)
            begin
                send_locked <= !mem_req_ready_i;
                if (!mem_req_ready_i)
                    send_locked_index <= send_index[2:0];
            end
            resp_from_sram <= 1'b0;
            victim_from_sram <= 1'b0;
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
            if (request_fire)
            begin
                if (request_is_load && request_hit)
                begin
                    event_hit_o <= 1'b1;
                    resp_valid_reg <= !(bypass_load_hit && dcache_resp_ready_i);
                    resp_from_sram <= (TAG_SRAM == 0);
                    if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                        legacy_lru_way_mem[request_index] <= !request_hit_entry[0];
                end
                else
                    if (request_is_store && request_hit)
                    begin
                        event_hit_o <= 1'b1;
                        if (STATIC_UPDATES == 0)
                            legacy_dirty_bits[request_hit_entry] <= 1'b1;
                        if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                            legacy_lru_way_mem[request_index] <= !request_hit_entry[0];
                        ack_valid_reg <= !(bypass_store_ack && dcache_store_ack_ready_i);
                    end
                    else
                        if (request_is_load && matching_found &&
                        query_matching_mshr_store &&
                        matching_store_covers_load)
                        begin
                            event_hit_o <= 1'b1;
                            resp_valid_reg <= 1'b1;
                        end
                        else
                            if (request_is_load && matching_found && matching_prefetch)
                            begin
                                event_miss_o <= 1'b1;
                            end
                            else
                                if (request_is_load && matching_found)
                                begin
                                    event_miss_o <= 1'b1;
                                end
                                else
                                    if (request_is_store && matching_found &&
                                    matching_prefetch)
                                    begin
                                        event_miss_o <= 1'b1;
                                        if (STATIC_UPDATES == 0)
                                            legacy_mshr_wdata[MSHR_ARRAY_INDEX_WIDTH'(matching_index)] <= core_req_wdata;
                                    end
                                    else
                                        if (request_is_store && matching_found &&
                                        query_matching_mshr_store)
                                        begin
                                            event_miss_o <= 1'b1;
                                            if (STATIC_UPDATES == 0)
                                                legacy_mshr_wdata[MSHR_ARRAY_INDEX_WIDTH'(matching_index)] <=
                                                merge_store(query_matching_mshr_wdata,
                                                core_req_wdata,
                                                core_req_mask);
                                        end
                                        else
                                        begin
                                            event_miss_o <= 1'b1;
                                            if (STATIC_UPDATES == 0)
                                                legacy_mshr_wdata[MSHR_ARRAY_INDEX_WIDTH'(free_index)] <= core_req_wdata;
                                            if (request_dirty_victim)
                                            begin
                                                if (TAG_SRAM == 0)
                                                begin
                                                    victim_from_sram <= 1'b1;
                                                    victim_mshr_reg <= free_index[2:0];
                                                end
                                            end
                                            if (STATIC_UPDATES == 0 && !request_writearound_new)
                                            begin
                                                legacy_valid_bits[request_victim_entry] <= 1'b0;
                                                legacy_dirty_bits[request_victim_entry] <= 1'b0;
                                            end
                                            if (STATIC_UPDATES == 0 && CACHE_WAYS == 2 && !request_writearound_new)
                                                legacy_lru_way_mem[request_index] <= !request_victim_entry[0];
                                            if ((PREFETCH != 0) && request_is_load &&
                                            second_free_found && !prefetch_cache_hit &&
                                            !prefetch_line_present &&
                                            !prefetch_index_conflict &&
                                            (prefetch_index != request_index) &&
                                            !(prefetch_victim_valid && prefetch_victim_dirty))
                                            begin
                                                if (STATIC_UPDATES == 0)
                                                    legacy_mshr_wdata[MSHR_ARRAY_INDEX_WIDTH'(second_free_index)] <= 128'd0;
                                                if (STATIC_UPDATES == 0)
                                                begin
                                                    legacy_valid_bits[prefetch_victim_entry] <= 1'b0;
                                                    legacy_dirty_bits[prefetch_victim_entry] <= 1'b0;
                                                end
                                                if (STATIC_UPDATES == 0 && CACHE_WAYS == 2)
                                                    legacy_lru_way_mem[prefetch_index] <= !prefetch_victim_entry[0];
                                            end
                                        end
                if (request_is_store && !request_writearound_new)
                begin
                    ack_valid_reg <= !(bypass_store_ack && dcache_store_ack_ready_i);
                end
            end
            if (local_array_write)
            begin
                if (STATIC_UPDATES == 0)
                begin
                    legacy_valid_bits[query_local_mshr_victim_entry] <= 1'b1;
                    legacy_dirty_bits[query_local_mshr_victim_entry] <= 1'b1;
                end
                if (TAG_SRAM == 0)
                    tag_mem[query_local_mshr_victim_entry] <=
                    query_local_mshr_addr[31:CACHE_INDEX_WIDTH+4];
                event_refill_o <= 1'b1;
            end
            if (resp_slot_free && waiter_load_ready_found &&
            !demand_response_fire)
            begin
                resp_valid_reg <= 1'b1;
            end
            if (waiter_store_consume)
            begin
                ack_valid_reg <= 1'b1;
            end
            if (mem_resp_valid_i && mem_resp_ready_o)
            begin
                if (query_response_writearound)
                begin
                    ack_valid_reg <= 1'b1;
                end
                else if (query_response_mshr_writeback &&
                !mem_resp_error_i && response_matches)
                begin
                    event_writeback_o <= 1'b1;
                end
                else
                    if (query_response_mshr_writeback)
                    begin
                        if (query_response_mshr_store)
                        begin
                            ack_valid_reg <= 1'b1;
                        end
                        else
                        begin
                            resp_valid_reg <= 1'b1;
                        end
                    end
                    else
                        if (query_response_mshr_store)
                        begin
                            if (!mem_resp_error_i && response_matches)
                            begin
                                if (STATIC_UPDATES == 0)
                                begin
                                    legacy_valid_bits[query_response_mshr_victim_entry] <= 1'b1;
                                    legacy_dirty_bits[query_response_mshr_victim_entry] <= 1'b1;
                                end
                                if (TAG_SRAM == 0)
                                    tag_mem[query_response_mshr_victim_entry] <= query_response_mshr_addr[31:CACHE_INDEX_WIDTH+4];
                                event_refill_o <= 1'b1;
                            end
                        end
                        else
                            if (query_response_mshr_prefetch)
                            begin
                                if (!mem_resp_error_i && response_matches)
                                begin
                                    if (STATIC_UPDATES == 0)
                                        legacy_valid_bits[query_response_mshr_victim_entry] <= 1'b1;
                                    if (TAG_SRAM == 0)
                                        tag_mem[query_response_mshr_victim_entry] <= query_response_mshr_addr[31:CACHE_INDEX_WIDTH+4];
                                    if (STATIC_UPDATES == 0)
                                        legacy_dirty_bits[query_response_mshr_victim_entry] <= 1'b0;
                                    event_refill_o <= 1'b1;
                                end
                            end
                            else
                            begin
                                if (!mem_resp_error_i && response_matches)
                                begin
                                    if (STATIC_UPDATES == 0)
                                        legacy_valid_bits[query_response_mshr_victim_entry] <= 1'b1;
                                    if (TAG_SRAM == 0)
                                        tag_mem[query_response_mshr_victim_entry] <= query_response_mshr_addr[31:CACHE_INDEX_WIDTH+4];
                                    if (STATIC_UPDATES == 0)
                                        legacy_dirty_bits[query_response_mshr_victim_entry] <= 1'b0;
                                    event_refill_o <= 1'b1;
                                end
                                resp_valid_reg <= 1'b1;
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
            (STORE_MERGE_POLICY != 0 && STORE_MERGE_POLICY != 1) ||
            (STORE_MISS_WRITE_AROUND != 0 && STORE_MISS_WRITE_AROUND != 1) ||
            (TAG_SRAM != 0 && TAG_SRAM != 1) ||
            (STATIC_UPDATES < 0 || STATIC_UPDATES > 2) ||
            (LOCAL_METADATA_QUERY != 0 && LOCAL_METADATA_QUERY != 1) ||
            (LOCAL_ACTION_DECODE != 0 && LOCAL_ACTION_DECODE != 1) ||
            (CACHE_LINES % CACHE_WAYS != 0) ||
            CACHE_LINES > 4096 ||
            ((CACHE_LINES & (CACHE_LINES - 1)) != 0)) begin
            $display("ERROR: invalid rv32_dcache_nonblocking parameter");
            $finish;
        end
    end
endmodule
