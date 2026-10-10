`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Small non-blocking instruction cache used by the performance profiles.
// The cache remains direct mapped, but independent MSHRs allow the demand
// line and several sequential prefetches to overlap the backing-memory delay.
module rv32_icache_nonblocking #(
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    parameter integer MSHR_ENTRIES = 4,
    parameter integer MSHR_STATE_BANKS = 0,
    parameter integer CLASS_SEND_SELECT = 0,
    parameter integer CONTROL_TARGET_PREFIX = 0,
    parameter integer CONTROL_REGION_PREQUERY = 0,
    parameter integer QUERY_DOMAINS = 4,
    parameter integer MSHR_STATIC_WRITES = 0,
    parameter integer TAG_MATCH_PARALLEL = 0,
    parameter integer TAG_REGION_BITS = 0,
    parameter integer LOCAL_RESPONSE_READY = 0,
    parameter integer REQUEST_PIPELINE = 0,
    parameter integer OWNER_PAYLOAD_SELECT = 0,
    parameter integer LOOP_BUFFER_LINES = 0,
    parameter integer LOOP_BUFFER_SRAM = 0,
    parameter integer REFILL_PROTECT_PENDING_HIT = 1,
    parameter integer NEXT_LINE_PREFETCH = 1,
    parameter integer PREFETCH_DISTANCE = 3,
    parameter integer CACHE_LINES = 64,
    parameter integer CACHE_WAYS = 2,
    parameter integer CACHE_SETS = CACHE_LINES / CACHE_WAYS,
    parameter integer CACHE_SET_WIDTH = $clog2(CACHE_SETS),
    parameter integer CACHE_ENTRY_WIDTH = $clog2(CACHE_LINES),
    parameter integer CACHE_TAG_WIDTH = 32 - 4 - CACHE_SET_WIDTH
) (
    input  wire                       clk_i,
    input  wire                       reset_i,
    input  wire [EPOCH_WIDTH-1:0]     current_epoch_i,

    input  wire                       if_req_valid_i,
    output wire                       if_req_ready_o,
    input  wire [31:0]                if_req_pc_i,
    input  wire [EPOCH_WIDTH-1:0]     if_req_epoch_i,

    output wire                       if_resp_valid_o,
    input  wire                       if_resp_ready_i,
    output wire [31:0]                if_resp_pc_o,
    output wire [31:0]                if_resp_line_addr_o,
    output wire [127:0]               if_resp_line_data_o,
    output wire [EPOCH_WIDTH-1:0]     if_resp_epoch_o,
    output wire                       if_resp_error_o,

    output wire                       mem_req_valid_o,
    input  wire                       mem_req_ready_i,
    output wire [31:0]                mem_req_line_addr_o,
    output wire [7:0]                 mem_req_id_o,
    input  wire                       mem_resp_valid_i,
    output wire                       mem_resp_ready_o,
    input  wire [31:0]                mem_resp_line_addr_i,
    input  wire [127:0]               mem_resp_data_i,
    input  wire [7:0]                 mem_resp_id_i,
    input  wire                       mem_resp_error_i,

    output reg                        event_request_o,
    output reg                        event_hit_o,
    output reg                        event_miss_o,
    output reg                        event_refill_o,
    output reg                        event_stall_o
);
    wire  primary_if_req_valid;
    wire  primary_if_req_ready;
    wire [31:0] primary_if_req_pc;
    wire [EPOCH_WIDTH-1:0] primary_if_req_epoch;
    wire  primary_if_resp_valid;
    wire  primary_if_resp_ready;
    wire [31:0] primary_if_resp_pc;
    wire [31:0] primary_if_resp_line_addr;
    wire [127:0] primary_if_resp_line_data;
    wire [EPOCH_WIDTH-1:0] primary_if_resp_epoch;
    wire  primary_if_resp_error;
    // Cached instruction bytes survive redirects exactly as the primary
    // I-cache does. Only transaction validity is qualified by the epoch.
    generate if(LOOP_BUFFER_LINES!=0) begin:g_instruction_line_filter
        rv32_instruction_line_filter #(.OWNER_PAYLOAD_SELECT(OWNER_PAYLOAD_SELECT),.LINES(LOOP_BUFFER_LINES),.DATA_SRAM(LOOP_BUFFER_SRAM),.EPOCH_WIDTH(EPOCH_WIDTH)) lines (
            .clk_i(clk_i),.reset_i(reset_i),.current_epoch_i(current_epoch_i),
            .if_req_valid_i(if_req_valid_i),
            .primary_req_valid_o(primary_if_req_valid),
            .if_req_ready_o(if_req_ready_o),
            .primary_req_ready_i(primary_if_req_ready),
            .if_req_pc_i(if_req_pc_i),
            .primary_req_pc_o(primary_if_req_pc),
            .if_req_epoch_i(if_req_epoch_i),
            .primary_req_epoch_o(primary_if_req_epoch),
            .if_resp_valid_o(if_resp_valid_o),
            .primary_resp_valid_i(primary_if_resp_valid),
            .if_resp_ready_i(if_resp_ready_i),
            .primary_resp_ready_o(primary_if_resp_ready),
            .if_resp_pc_o(if_resp_pc_o),
            .primary_resp_pc_i(primary_if_resp_pc),
            .if_resp_line_addr_o(if_resp_line_addr_o),
            .primary_resp_line_addr_i(primary_if_resp_line_addr),
            .if_resp_line_data_o(if_resp_line_data_o),
            .primary_resp_line_data_i(primary_if_resp_line_data),
            .if_resp_epoch_o(if_resp_epoch_o),
            .primary_resp_epoch_i(primary_if_resp_epoch),
            .if_resp_error_o(if_resp_error_o),
            .primary_resp_error_i(primary_if_resp_error));
    end else begin:g_no_instruction_line_filter
        assign primary_if_req_valid=if_req_valid_i;
        assign if_req_ready_o=primary_if_req_ready;
        assign primary_if_req_pc=if_req_pc_i;
        assign primary_if_req_epoch=if_req_epoch_i;
        assign if_resp_valid_o=primary_if_resp_valid;
        assign primary_if_resp_ready=if_resp_ready_i;
        assign if_resp_pc_o=primary_if_resp_pc;
        assign if_resp_line_addr_o=primary_if_resp_line_addr;
        assign if_resp_line_data_o=primary_if_resp_line_data;
        assign if_resp_epoch_o=primary_if_resp_epoch;
        assign if_resp_error_o=primary_if_resp_error;
    end endgenerate

    wire lookup_req_valid,lookup_req_ready;
    wire [31:0] lookup_req_pc;
    wire [EPOCH_WIDTH-1:0] lookup_req_epoch;
    generate if(REQUEST_PIPELINE!=0) begin:g_request_pipeline
        rv32_icache_query_queue #(.EPOCH_WIDTH(EPOCH_WIDTH)) requests (
            .clk_i(clk_i),.reset_i(reset_i),.current_epoch_i(current_epoch_i),
            .valid_i(primary_if_req_valid),.ready_o(primary_if_req_ready),.pc_i(primary_if_req_pc),.epoch_i(primary_if_req_epoch),
            .valid_o(lookup_req_valid),.ready_i(lookup_req_ready),.pc_o(lookup_req_pc),.epoch_o(lookup_req_epoch));
    end else begin:g_direct_request
        assign lookup_req_valid=primary_if_req_valid;assign primary_if_req_ready=lookup_req_ready;
        assign lookup_req_pc=primary_if_req_pc;assign lookup_req_epoch=primary_if_req_epoch;
    end endgenerate

    wire [CACHE_LINES-1:0] valid_bits;
    wire [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];
    localparam integer TAG_STORED_WIDTH=CACHE_TAG_WIDTH-TAG_REGION_BITS;
    localparam integer REGION_STORAGE_WIDTH=(TAG_REGION_BITS>0)?TAG_REGION_BITS:1;
    wire [CACHE_WAYS*REGION_STORAGE_WIDTH-1:0] tag_regions;
    wire [CACHE_LINES-1:0] region_invalidate;
    wire [CACHE_LINES*3-1:0] region_match_views;
    wire unused_region_match_views_bits = &{1'b0, region_match_views};

    genvar region_way;
    generate if(TAG_REGION_BITS!=0) begin:g_region_owners
        for(region_way=0;region_way<CACHE_WAYS;region_way=region_way+1) begin:g_way
            wire region_write=refill_array_write && ((32'(refill_entry)%CACHE_WAYS)==region_way);
            wire [REGION_STORAGE_WIDTH-1:0] prefix;
            wire region_change=region_write && prefix!=mem_resp_line_addr_i[31 -: REGION_STORAGE_WIDTH];
            wire [CACHE_SETS-1:0] invalidations;
            rv32_frequency_word_bank #(.WIDTH(REGION_STORAGE_WIDTH)) region_owner (
                .clk_i(clk_i),.write_i(region_write),
                .data_i(mem_resp_line_addr_i[31 -: REGION_STORAGE_WIDTH]),.data_o(prefix));
            assign tag_regions[region_way*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH]=prefix;
            rv32_frequency_control_tree #(.LEAVES(CACHE_SETS)) invalidate_tree (
                .signal_i(region_change),.views_o(invalidations));
            for(genvar region_set=0;region_set<CACHE_SETS;region_set=region_set+1) begin:g_set
                assign region_invalidate[region_set*CACHE_WAYS+region_way]=invalidations[region_set];
            end
        end
    end else begin:g_no_regions
        assign tag_regions=0;
        assign region_invalidate=0;
    end endgenerate
    wire lru_mem [0:CACHE_SETS-1];

    function automatic [CACHE_ENTRY_WIDTH-1:0] cache_entry;
        input [CACHE_SET_WIDTH-1:0] set_index;
        input integer way;
        begin
            cache_entry = CACHE_ENTRY_WIDTH'(set_index * CACHE_WAYS + way);
        end
    endfunction

    reg mshr_valid [0:MSHR_ENTRIES-1];
    reg mshr_sent [0:MSHR_ENTRIES-1];
    reg mshr_prefetch [0:MSHR_ENTRIES-1];
    reg mshr_control_prefetch [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_pc [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_line [0:MSHR_ENTRIES-1];
    reg [EPOCH_WIDTH-1:0] mshr_demand_epoch [0:MSHR_ENTRIES-1];
    reg [EPOCH_WIDTH-1:0] mshr_txn_epoch [0:MSHR_ENTRIES-1];

    reg resp_valid_reg;
    wire [31:0] resp_pc_reg;
    wire [31:0] resp_line_reg;
    reg [127:0] resp_data_reg;
    // A synchronous hit and its metadata become valid after the same edge.
    // Capture the macro result before idle/write makes rdata undefined.
    reg resp_from_sram;
    wire [127:0] data_rdata;
    wire [EPOCH_WIDTH-1:0] resp_epoch_reg;
    wire resp_error_reg;

    reg prefetch_active;
    wire [31:0] prefetch_next_line;
    wire [EPOCH_WIDTH-1:0] prefetch_epoch;
    // Positive stream occupancy is bounded by both parameters. The
    // extra sign bit preserves old signed comparisons; unsupported negative
    // distances keep the original 32-bit signed behavior rather than wrap.
    localparam integer STREAM_MAX=(PREFETCH_DISTANCE<MSHR_ENTRIES-1)?PREFETCH_DISTANCE:MSHR_ENTRIES-1;
    localparam integer STREAM_COUNT_WIDTH=(STREAM_MAX<0)?32:((STREAM_MAX<1)?2:$clog2(STREAM_MAX+1)+1);
    reg signed [STREAM_COUNT_WIDTH-1:0] prefetch_remaining;
    reg prefetch_control_stream;
    reg last_demand_valid;
    wire [31:0] last_demand_line;

    wire [31:0] request_line = {lookup_req_pc[31:4], 4'b0000};
    wire [CACHE_SET_WIDTH-1:0] request_set = lookup_req_pc[CACHE_SET_WIDTH+3:4];
    wire [CACHE_TAG_WIDTH-1:0] request_tag = lookup_req_pc[31:CACHE_SET_WIDTH+4];
    wire [CACHE_ENTRY_WIDTH-1:0] request_way0 = cache_entry(request_set, 0);
    wire [CACHE_ENTRY_WIDTH-1:0] request_way1 = cache_entry(request_set, 1);
    wire [CACHE_LINES-1:0] demand_match_way0, demand_match_way1;
    wire [CACHE_LINES-1:0] prefetch_match_rows, control_match_rows;
    wire request_hit_way0 = (TAG_MATCH_PARALLEL != 0) ? (|demand_match_way0) :
                            (valid_bits[request_way0] &&
                             (tag_mem[request_way0] == request_tag));
    wire request_hit_way1 = (CACHE_WAYS == 2) && ((TAG_MATCH_PARALLEL != 0) ?
                            (|demand_match_way1) : (valid_bits[request_way1] &&
                             (tag_mem[request_way1] == request_tag)));
    wire request_hit = request_hit_way0 || request_hit_way1;
    wire [CACHE_ENTRY_WIDTH-1:0] request_entry =
        request_hit_way1 ? request_way1 : request_way0;
    wire response_live = resp_valid_reg && (resp_epoch_reg == current_epoch_i);
    wire response_slot_free = !resp_valid_reg || !response_live || primary_if_resp_ready;

    integer k;
    integer request_match_index;
    integer free_index;
    integer original_send_index;
    integer response_index;
    integer prefetch_match_index;
    wire unused_prefetch_match_index_bits = &{1'b0, prefetch_match_index};

    integer control_check;
    integer control_way;
    reg request_match_found;
    reg free_found;
    reg original_send_found;
    reg response_target_found;
    reg prefetch_match_found;
    wire control_target_valid;
    reg control_target_present;
    wire [31:0] control_target;

    always @* begin
        request_match_found = 1'b0;
        request_match_index = 0;
        free_found = 1'b0;
        free_index = 0;
        original_send_found = 1'b0;
        original_send_index = 0;
        prefetch_match_found = 1'b0;
        prefetch_match_index = 0;
        for (k = 0; k < MSHR_ENTRIES; k = k + 1) begin
            if (!request_match_found && mshr_valid[k] &&
                ((mshr_txn_epoch[k] == current_epoch_i) ||
                 mshr_control_prefetch[k]) &&
                (mshr_line[k] == request_line)) begin
                request_match_found = 1'b1;
                request_match_index = k;
            end
            // A redirect makes the previous epoch's slots immediately
            // reusable.  Treating them as live for one extra cycle can make
            // the first redirected request merge into a slot that the
            // sequential cleanup clears on the same edge.
            if (!free_found &&
                (!mshr_valid[k] ||
                 ((mshr_txn_epoch[k] != current_epoch_i) &&
                  !mshr_control_prefetch[k]))) begin
                free_found = 1'b1;
                free_index = k;
            end
            if (mshr_valid[k] &&
                ((mshr_txn_epoch[k] == current_epoch_i) ||
                 mshr_control_prefetch[k]) &&
                !mshr_sent[k] &&
                (!original_send_found ||
                 (mshr_prefetch[original_send_index] && !mshr_prefetch[k]) ||
                 (mshr_prefetch[original_send_index] && mshr_prefetch[k] &&
                  !mshr_control_prefetch[original_send_index] &&
                  mshr_control_prefetch[k]))) begin
                // Priority is demand, then a decoded direct-control target,
                // then ordinary sequential traffic.  The target line used
                // to sit behind a stale fall-through prefetch at startup.
                original_send_found = 1'b1;
                original_send_index = k;
            end
            if (!prefetch_match_found && mshr_valid[k] &&
                (mshr_txn_epoch[k] == current_epoch_i) &&
                (mshr_line[k] == prefetch_next_line)) begin
                prefetch_match_found = 1'b1;
                prefetch_match_index = k;
            end
        end

        response_index = 32'(mem_resp_id_i) >> EPOCH_WIDTH;
        response_target_found = (response_index >= 0) &&
                                (response_index < MSHR_ENTRIES) &&
                                mshr_valid[response_index] &&
                                mshr_sent[response_index] &&
                                ((mshr_txn_epoch[response_index] ==
                                  current_epoch_i) ||
                                 mshr_control_prefetch[response_index]) &&
                                (mshr_txn_epoch[response_index] ==
                                 mem_resp_id_i[EPOCH_WIDTH-1:0]);
    end

    wire incoming_live_demand = mem_resp_valid_i && response_target_found &&
                                !mshr_prefetch[response_index] &&
                                (mshr_demand_epoch[response_index] == current_epoch_i);
    wire request_promotes_incoming = request_match_found &&
                                     response_target_found &&
                                     (request_match_index == response_index);
    wire request_would_conflict = incoming_live_demand && request_hit &&
                                  !request_promotes_incoming;
    wire request_fire = lookup_req_valid && lookup_req_ready;
    wire request_allocates = request_fire && !request_hit && !request_match_found;
    wire prefetch_enabled = (NEXT_LINE_PREFETCH != 0) &&
                            (PREFETCH_DISTANCE > 0) &&
                            (MSHR_ENTRIES > 1);
    wire stream_request = request_fire && prefetch_enabled &&
                          (lookup_req_epoch == current_epoch_i);
    wire stream_sequential = stream_request && prefetch_active &&
                             last_demand_valid &&
                             (prefetch_epoch == lookup_req_epoch) &&
                             (request_line == (last_demand_line + 32'd16));
    wire stream_reset = stream_request && !stream_sequential;
    wire response_matches = response_target_found &&
                            (mshr_line[response_index] == mem_resp_line_addr_i);

    // The former scan chooses the earliest forward outside-line JAL,
    // otherwise the earliest outside-line JAL. Four independent candidates
    // and scalar prefix grants retain that exact word priority.
    // Distribute the shared response address before its arithmetic/comparators.
    wire [127:0] control_base_views,control_candidates;
    wire [3:0] control_outside,control_forward,control_preferred,control_grants;
    wire control_has_forward=|control_forward;
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) control_base_tree (
        .signal_i(mem_resp_line_addr_i),.views_o(control_base_views));
    generate for(genvar control_lane=0;control_lane<4;control_lane=control_lane+1) begin:g_control_candidate
        wire [31:0] inst=mem_resp_data_i[control_lane*32 +: 32];
        wire unused_inst_bits = &{1'b0, inst};

        wire [31:0] base=control_base_views[control_lane*32 +: 32];
        // A J-immediate is signed21 bits with bit0=0. Adding 0/4/8/12
        // fits signed22 bits, including the positive-limit carry. This moves
        // the word displacement off the shared full-width PC carry path.
        wire [21:0] displaced_immediate=
            {inst[31],inst[31],inst[19:12],inst[20],inst[30:21],1'b0}+22'(control_lane*4);
        wire [31:0] displaced_word={{10{displaced_immediate[21]}},displaced_immediate};
        wire [31:0] pc=base+32'(control_lane*4);
        wire [31:0] candidate;
        wire candidate_forward;
        if(CONTROL_TARGET_PREFIX!=0) begin:g_prefix_target
            wire [2:0] comparison;
            rv32_frequency_addsub32 target_add (
                .lhs_i(base),.rhs_i(displaced_word),.subtract_i(1'b0),.value_o(candidate));
            rv32_frequency_compare32 forward_compare (
                .lhs_i(pc),.rhs_i(candidate),.value_o(comparison));
            assign candidate_forward=comparison[1];
            // synthesis translate_off
            always @(posedge clk_i) if(!reset_i) begin
                if(candidate!==(base+displaced_word) || candidate_forward!==(candidate>pc))
                    $fatal(1,"I-cache prefix target differs from original full arithmetic/comparison");
            end
            // synthesis translate_on
        end else begin:g_original_target
            assign candidate=base+displaced_word;
            assign candidate_forward=candidate>pc;
        end
        assign control_candidates[control_lane*32 +: 32]=candidate;
        assign control_outside[control_lane]=(inst[6:0]==7'b1101111) && candidate[31:4]!=base[31:4];
        // Preserve the original UNSIGNED comparison, including address wrap.
        assign control_forward[control_lane]=control_outside[control_lane] && candidate_forward;
        assign control_preferred[control_lane]=control_has_forward?
            control_forward[control_lane]:control_outside[control_lane];
        if(control_lane==0) begin:g_first
            assign control_grants[control_lane]=control_preferred[control_lane];
        end else begin:g_following
            assign control_grants[control_lane]=control_preferred[control_lane] && !(|control_preferred[control_lane-1:0]);
        end
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) control_target_selector (
        .events_i(control_grants),.values_i(control_candidates),
        .write_o(control_target_valid),.value_o(control_target));
    always @* begin
        control_target_present=1'b0;
        if (control_target_valid) begin
            control_target_present = request_fire &&
                (request_line == {control_target[31:4], 4'b0});
            if (TAG_MATCH_PARALLEL != 0) begin
                if (|control_match_rows)
                    control_target_present = 1'b1;
            end else begin
                for (control_way = 0; control_way < CACHE_WAYS;
                     control_way = control_way + 1)
                    if (valid_bits[cache_entry(
                            control_target[CACHE_SET_WIDTH+3:4], control_way)] &&
                        (tag_mem[cache_entry(
                            control_target[CACHE_SET_WIDTH+3:4], control_way)] ==
                         control_target[31:CACHE_SET_WIDTH+4]))
                        control_target_present = 1'b1;
            end
            for (control_check = 0; control_check < MSHR_ENTRIES;
                 control_check = control_check + 1)
                if (mshr_valid[control_check] &&
                    (mshr_line[control_check] ==
                     {control_target[31:4], 4'b0}))
                    control_target_present = 1'b1;
        end
    end
    wire control_target_allocate = mem_resp_valid_i && mem_resp_ready_o &&
                                   response_target_found && response_matches &&
                                   !mem_resp_error_i && control_target_valid &&
                                   !control_target_present;
    wire response_needs_slot = response_target_found &&
                               (!mshr_prefetch[response_index] ||
                                (request_fire && request_match_found &&
                                 (request_match_index == response_index))) &&
                               ((mshr_demand_epoch[response_index] == current_epoch_i) ||
                                (request_fire && (lookup_req_epoch == current_epoch_i)));
    wire [CACHE_SET_WIDTH-1:0] prefetch_set =
        prefetch_next_line[CACHE_SET_WIDTH+3:4];
    wire [CACHE_TAG_WIDTH-1:0] prefetch_tag =
        prefetch_next_line[31:CACHE_SET_WIDTH+4];
    wire [CACHE_ENTRY_WIDTH-1:0] prefetch_way0 = cache_entry(prefetch_set, 0);
    wire [CACHE_ENTRY_WIDTH-1:0] prefetch_way1 = cache_entry(prefetch_set, 1);
    // Each row owns a fixed stored tag. Query indices qualify a one-bit
    // match instead of steering every stored tag bit through a large mux.
    // This changes only combinational layout, with no additional state.
    wire [QUERY_DOMAINS*32-1:0] demand_pc_views,prefetch_pc_views,control_pc_views;
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(QUERY_DOMAINS)) demand_query_tree (
        .signal_i(lookup_req_pc),.views_o(demand_pc_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(QUERY_DOMAINS)) prefetch_query_tree (
        .signal_i(prefetch_next_line),.views_o(prefetch_pc_views));
    localparam integer CONTROL_QUERY_WIDTH=(CONTROL_REGION_PREQUERY!=0) ? 32-TAG_REGION_BITS : 32;
    wire [QUERY_DOMAINS*CONTROL_QUERY_WIDTH-1:0] control_low_views;
    wire [CACHE_WAYS*QUERY_DOMAINS-1:0] control_region_views;
    rv32_frequency_control_tree #(.WIDTH(CONTROL_QUERY_WIDTH),.LEAVES(QUERY_DOMAINS)) control_query_tree (
        .signal_i(control_target[CONTROL_QUERY_WIDTH-1:0]),.views_o(control_low_views));
    for(genvar control_domain=0;control_domain<QUERY_DOMAINS;control_domain=control_domain+1) begin:g_control_low_query
        // The upper region is checked independently. Every set/low-tag bit
        // remains complete; default0 retains the original full query word.
        assign control_pc_views[control_domain*32 +: 32]=
            {{(32-CONTROL_QUERY_WIDTH){1'b0}},control_low_views[control_domain*CONTROL_QUERY_WIDTH +: CONTROL_QUERY_WIDTH]};
    end
    generate if(CONTROL_REGION_PREQUERY!=0) begin:g_control_region_prequery
        rv32_icache_control_region_query #(.REGION_BITS(REGION_STORAGE_WIDTH),.WAYS(CACHE_WAYS),
            .DOMAINS(QUERY_DOMAINS)) query (
            .candidates_i(control_candidates),.grants_i(control_grants),.prefixes_i(tag_regions),
            .matches_o(control_region_views));
`ifndef SYNTHESIS
        always @(posedge clk_i) if(!reset_i) begin
            assert($onehot0(control_grants)) else $fatal(1,"Original control priority grants are not onehot0");
        end
        for(genvar way=0;way<CACHE_WAYS;way=way+1) begin:g_original_region_shadow
            wire original_match=tag_regions[way*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH]==
                control_target[31 -: REGION_STORAGE_WIDTH];
            always @(posedge clk_i) if(!reset_i)
                assert(control_region_views[way*QUERY_DOMAINS +: QUERY_DOMAINS]==={QUERY_DOMAINS{original_match}})
                    else $fatal(1,"Early control region query changed original raw region equality");
        end
`endif
    end else begin:g_original_control_region_unused
        assign control_region_views=0;
    end endgenerate

    generate if(TAG_REGION_BITS!=0 && TAG_MATCH_PARALLEL!=0) begin:g_region_queries
        localparam integer DOMAIN_SETS=CACHE_SETS/QUERY_DOMAINS;
        for(genvar query_way=0;query_way<CACHE_WAYS;query_way=query_way+1) begin:g_way
            wire [QUERY_DOMAINS*REGION_STORAGE_WIDTH-1:0] prefixes;
            rv32_frequency_control_tree #(.WIDTH(REGION_STORAGE_WIDTH),.LEAVES(QUERY_DOMAINS)) prefix_tree (
                .signal_i(tag_regions[query_way*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH]),
                .views_o(prefixes));
            for(genvar query_domain=0;query_domain<QUERY_DOMAINS;query_domain=query_domain+1) begin:g_domain
                wire [REGION_STORAGE_WIDTH-1:0] prefix=prefixes[query_domain*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH];
                wire [31:0] demand=demand_pc_views[query_domain*32 +: 32];
                wire unused_demand_bits = &{1'b0, demand};

                wire [31:0] prefetch=prefetch_pc_views[query_domain*32 +: 32];
                wire unused_prefetch_bits = &{1'b0, prefetch};

                wire [31:0] control=control_pc_views[query_domain*32 +: 32];
                wire unused_control_bits = &{1'b0, control};

                wire [DOMAIN_SETS*3-1:0] region_query_matches;
                rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(DOMAIN_SETS)) match_tree (
                    .signal_i({(CONTROL_REGION_PREQUERY!=0) ? control_region_views[query_way*QUERY_DOMAINS+query_domain] : (prefix==control[31 -: REGION_STORAGE_WIDTH]),
                        prefix==prefetch[31 -: REGION_STORAGE_WIDTH],
                        prefix==demand[31 -: REGION_STORAGE_WIDTH]}),.views_o(region_query_matches));
                for(genvar query_row=0;query_row<DOMAIN_SETS;query_row=query_row+1) begin:g_row
                    localparam integer ROW=(query_domain*DOMAIN_SETS+query_row)*CACHE_WAYS+query_way;
                    assign region_match_views[ROW*3 +: 3]=region_query_matches[query_row*3 +: 3];
                end
            end
        end
    end else begin:g_no_region_queries
        assign region_match_views={CACHE_LINES*3{1'b1}};
    end endgenerate
    genvar match_row;
    generate
`ifdef CPU2026_WORD_SIM
    if(CACHE_LINES==128 && CACHE_WAYS==2 && CACHE_SET_WIDTH==6 &&
       CACHE_ENTRY_WIDTH==7 && CACHE_TAG_WIDTH==22 && TAG_MATCH_PARALLEL!=0 && CONTROL_REGION_PREQUERY==0) begin:g_word_tag_query
        reg [127:0] demand0,demand1,prefetch_matches,control_matches;
        wire [6:0] control0={control_target[9:4],1'b0};
        wire [6:0] control1={control_target[9:4],1'b1};
        always @* begin
            demand0=0;demand1=0;prefetch_matches=0;control_matches=0;
            demand0[request_way0]=valid_bits[request_way0] && tag_mem[request_way0]==request_tag;
            demand1[request_way1]=valid_bits[request_way1] && tag_mem[request_way1]==request_tag;
            prefetch_matches[prefetch_way0]=valid_bits[prefetch_way0] && tag_mem[prefetch_way0]==prefetch_tag;
            prefetch_matches[prefetch_way1]=valid_bits[prefetch_way1] && tag_mem[prefetch_way1]==prefetch_tag;
            control_matches[control0]=valid_bits[control0] && tag_mem[control0]==control_target[31:10];
            control_matches[control1]=valid_bits[control1] && tag_mem[control1]==control_target[31:10];
        end
        assign demand_match_way0=demand0;
        assign demand_match_way1=demand1;
        assign prefetch_match_rows=prefetch_matches;
        assign control_match_rows=control_matches;
    end else begin:g_original_tag_query
`endif
        for (match_row=0; match_row<CACHE_LINES; match_row=match_row+1) begin:g_match_row
        if (TAG_MATCH_PARALLEL != 0) begin:g_parallel
            localparam integer DOMAIN=(match_row*QUERY_DOMAINS)/CACHE_LINES;
            wire [31:0] demand_pc=demand_pc_views[DOMAIN*32 +: 32];
            wire [31:0] prefetch_pc=prefetch_pc_views[DOMAIN*32 +: 32];
            wire [31:0] control_pc=control_pc_views[DOMAIN*32 +: 32];
            wire demand_hit=valid_bits[match_row] &&
                demand_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                region_match_views[match_row*3] &&
                 tag_mem[match_row][TAG_STORED_WIDTH-1:0]==demand_pc[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];
            assign demand_match_way0[match_row]=(match_row%CACHE_WAYS==0) && demand_hit;
            assign demand_match_way1[match_row]=(match_row%CACHE_WAYS==1) && demand_hit;
            assign prefetch_match_rows[match_row]=valid_bits[match_row] &&
                prefetch_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                region_match_views[match_row*3+1] &&
                 tag_mem[match_row][TAG_STORED_WIDTH-1:0]==prefetch_pc[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];
            assign control_match_rows[match_row]=valid_bits[match_row] &&
                control_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                region_match_views[match_row*3+2] &&
                 tag_mem[match_row][TAG_STORED_WIDTH-1:0]==control_pc[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];
        end else begin:g_disabled
            assign demand_match_way0[match_row] = 1'b0;
            assign demand_match_way1[match_row] = 1'b0;
            assign prefetch_match_rows[match_row] = 1'b0;
            assign control_match_rows[match_row] = 1'b0;
        end
        end
`ifdef CPU2026_WORD_SIM
    end
`endif
    endgenerate
    wire prefetch_line_resident = (TAG_MATCH_PARALLEL != 0) ? (|prefetch_match_rows) :
        ((valid_bits[prefetch_way0] &&
          (tag_mem[prefetch_way0] == prefetch_tag)) ||
         ((CACHE_WAYS == 2) && valid_bits[prefetch_way1] &&
          (tag_mem[prefetch_way1] == prefetch_tag)));
    wire prefetch_step = prefetch_active && (prefetch_remaining > 0) &&
                         !request_allocates && !stream_reset &&
                         (prefetch_line_resident || prefetch_match_found ||
                          free_found);
    wire prefetch_step_allocates = prefetch_step &&
                                    !prefetch_line_resident &&
                                    !prefetch_match_found;

    wire [CACHE_SET_WIDTH-1:0] refill_set =
        mem_resp_line_addr_i[CACHE_SET_WIDTH+3:4];
    wire [CACHE_ENTRY_WIDTH-1:0] refill_way0 = cache_entry(refill_set, 0);
    wire [CACHE_ENTRY_WIDTH-1:0] refill_way1 = cache_entry(refill_set, 1);
    // Protect a pending hit even when a refill owns the single SRAM port.
    wire refill_conflicts_with_hit = (REFILL_PROTECT_PENDING_HIT != 0) &&
                                     lookup_req_valid && request_hit &&
                                     (request_set == refill_set);
    wire [CACHE_ENTRY_WIDTH-1:0] refill_entry =
                              (CACHE_WAYS == 1) ? refill_way0 :
                              (!valid_bits[refill_way0] ? refill_way0 :
                              (!valid_bits[refill_way1] ? refill_way1 :
                               (refill_conflicts_with_hit ?
                                cache_entry(refill_set, 32'(!request_entry[0])) :
                                cache_entry(refill_set, 32'(lru_mem[refill_set])))));

    // Do not derive arbitration from mem_resp_ready_o: response-slot logic
    // itself uses request_fire for same-cycle prefetch promotion.
    wire refill_array_candidate = mem_resp_valid_i && response_target_found &&
                                   response_matches && !mem_resp_error_i;
    wire refill_array_write = !reset_i && refill_array_candidate && mem_resp_ready_o;
    wire hit_array_read = request_fire && request_hit &&
                          (lookup_req_epoch == current_epoch_i);
    sram_fakeram #(.DEPTH(CACHE_LINES), .WIDTH(128), .WRITE_GRANULARITY(128)) data_array (
        .clk(clk_i), .en(!reset_i && (refill_array_write || hit_array_read)),
        .we(refill_array_write), .wmask(1'b1),
        .addr(refill_array_write ? refill_entry : request_entry),
        .wdata(mem_resp_data_i), .rdata(data_rdata)
    );

    assign lookup_req_ready = !reset_i && response_slot_free &&
                            !(refill_array_candidate && request_hit) &&
                            !request_would_conflict &&
                            (request_hit || request_match_found || free_found);
    assign primary_if_resp_valid = response_live;
    assign primary_if_resp_pc = resp_pc_reg;
    assign primary_if_resp_line_addr = resp_line_reg;
    wire [7:0] response_line_views;
    rv32_frequency_control_tree #(.LEAVES(8)) response_line_tree (
        .signal_i(resp_from_sram),.views_o(response_line_views));
    generate for(genvar output_word=0;output_word<8;output_word=output_word+1) begin:g_response_line
        assign primary_if_resp_line_data[output_word*16 +: 16]=response_line_views[output_word]?
            data_rdata[output_word*16 +: 16]:resp_data_reg[output_word*16 +: 16];
    end endgenerate
    assign primary_if_resp_epoch = resp_epoch_reg;
    assign primary_if_resp_error = resp_error_reg;

    // Preserve demand > decoded control target > sequential prefetch, with
    // the lowest row winning inside a class. Full epoch eligibility is shared
    // by all three classes; only the old serial winner feedback is replaced.
    wire send_found;
    wire signed [31:0] send_index;
    wire [31:0] original_send_address=original_send_found ?
        mshr_line[original_send_index] : 32'd0;
    wire [7:0] original_send_id=8'(original_send_found ?
        ((original_send_index << EPOCH_WIDTH) |
         32'(mshr_txn_epoch[original_send_index])) : 32'd0);
    generate if(CLASS_SEND_SELECT!=0) begin:g_class_send
        localparam integer INDEX_WIDTH=$clog2(MSHR_ENTRIES);
        localparam integer PACKET_WIDTH=40+INDEX_WIDTH;
        wire [MSHR_ENTRIES-1:0] eligible,demand,control,sequential,preferred,grants;
        wire has_demand=|demand;
        wire has_control=|control;
        wire [MSHR_ENTRIES*PACKET_WIDTH-1:0] packets;
        wire [PACKET_WIDTH-1:0] selected;
        wire packet_valid;
        for(genvar row=0;row<MSHR_ENTRIES;row=row+1) begin:g_row
            assign eligible[row]=mshr_valid[row] && !mshr_sent[row] &&
                ((mshr_txn_epoch[row]==current_epoch_i) || mshr_control_prefetch[row]);
            assign demand[row]=eligible[row] && !mshr_prefetch[row];
            assign control[row]=eligible[row] && mshr_prefetch[row] && mshr_control_prefetch[row];
            assign sequential[row]=eligible[row] && mshr_prefetch[row] && !mshr_control_prefetch[row];
            assign preferred[row]=demand[row] || (control[row] && !has_demand) ||
                (sequential[row] && !has_demand && !has_control);
            if(row==0) begin:g_first
                assign grants[row]=preferred[row];
            end else begin:g_following
                assign grants[row]=preferred[row] && !(|preferred[row-1:0]);
            end
            // Keep the original full line and eight-bit slot/epoch ID together.
            assign packets[row*PACKET_WIDTH +: PACKET_WIDTH]={INDEX_WIDTH'(row),
                mshr_line[row],8'((row << EPOCH_WIDTH) | 32'(mshr_txn_epoch[row]))};
        end
        rv32_frequency_event_select #(.WIDTH(PACKET_WIDTH),.EVENTS(MSHR_ENTRIES),.PRIORITY(0)) packet_selector (
            .events_i(grants),.values_i(packets),.write_o(packet_valid),.value_o(selected));
        // Valid does not wait for the late class and payload selection.
        assign send_found=|eligible;
        assign send_index=32'(selected[40 +: INDEX_WIDTH]);
        assign mem_req_line_addr_o=selected[8 +: 32];
        assign mem_req_id_o=selected[7:0];
        // synthesis translate_off
        always @(posedge clk_i) if(!reset_i) begin
            if(send_found!==original_send_found || packet_valid!==original_send_found ||
               send_index!==original_send_index ||
               mem_req_line_addr_o!==original_send_address || mem_req_id_o!==original_send_id)
                $fatal(1,"I-cache parallel class send differs from original full packet");
        end
        // synthesis translate_on
    end else begin:g_original_send
        assign send_found=original_send_found;
        assign send_index=original_send_index;
        assign mem_req_line_addr_o=original_send_address;
        assign mem_req_id_o=original_send_id;
    end endgenerate
    assign mem_req_valid_o = send_found;
    // Responses from a cancelled epoch have no live MSHR.  Consume and drop
    // them so a stale transaction cannot block the memory response channel.
    // request_fire implies response_slot_free through lookup_req_ready.
    // With no response slot, same-cycle promotion cannot be accepted; only
    // the demand already stored in the MSHR can require an output slot.
    assign mem_resp_ready_o = (LOCAL_RESPONSE_READY != 0) ?
                              (response_slot_free || !response_target_found ||
                               mshr_prefetch[response_index] ||
                               (mshr_demand_epoch[response_index] != current_epoch_i)) :
                              (!response_target_found ||
                               (!response_needs_slot || response_slot_free));

    // Preserve the old NBA priority: a live memory response overwrites
    // copying the previous SRAM response. Invalid payload need not reset.
    wire response_promoted=request_fire && request_match_found && request_match_index==response_index;
    wire response_memory_write=!reset_i && mem_resp_valid_i && mem_resp_ready_o && response_target_found &&
        ((response_promoted && lookup_req_epoch==current_epoch_i) ||
         (!response_promoted && !mshr_prefetch[response_index] && mshr_demand_epoch[response_index]==current_epoch_i));
    wire response_sram_copy=!reset_i && resp_from_sram && resp_valid_reg;
    wire [7:0] response_data_write,response_data_memory;
    rv32_frequency_control_tree #(.LEAVES(8)) response_write_tree (
        .signal_i(response_memory_write || response_sram_copy),.views_o(response_data_write));
    rv32_frequency_control_tree #(.LEAVES(8)) response_select_tree (
        .signal_i(response_memory_write),.views_o(response_data_memory));
    genvar response_word;
    generate for(response_word=0;response_word<8;response_word=response_word+1) begin:g_response_data
        always @(posedge clk_i) if(response_data_write[response_word])
            resp_data_reg[response_word*16 +: 16]<=response_data_memory[response_word]?
                mem_resp_data_i[response_word*16 +: 16]:data_rdata[response_word*16 +: 16];
    end endgenerate

    wire [CACHE_LINES+CACHE_SETS-1:0] metadata_reset;
    wire unused_metadata_reset_bits = &{1'b0, metadata_reset};

    wire [CACHE_LINES-1:0] metadata_refill;
    wire unused_metadata_refill_bits = &{1'b0, metadata_refill};

    wire [CACHE_SETS-1:0] metadata_hit_lru,metadata_refill_lru;
    wire unused_metadata_hit_lru_bits = &{1'b0, metadata_hit_lru};

    wire unused_metadata_refill_lru_bits = &{1'b0, metadata_refill_lru};

    rv32_frequency_control_tree #(.LEAVES(CACHE_LINES+CACHE_SETS)) metadata_reset_tree (
        .signal_i(reset_i),.views_o(metadata_reset));
    rv32_frequency_control_tree #(.LEAVES(CACHE_LINES)) metadata_refill_tree (
        .signal_i(refill_array_write),.views_o(metadata_refill));
    rv32_frequency_control_tree #(.LEAVES(CACHE_SETS)) metadata_hit_lru_tree (
        .signal_i(hit_array_read),.views_o(metadata_hit_lru));
    rv32_frequency_control_tree #(.LEAVES(CACHE_SETS)) metadata_refill_lru_tree (
        .signal_i(refill_array_write),.views_o(metadata_refill_lru));
    // Final qualified write leaves alone did not bound the raw shared
    // entry/way inputs. Each query packet feeds only four existing rows.
    localparam integer TAG_WRITE_DOMAINS=(CACHE_LINES+3)/4;
    localparam integer TAG_WRITE_WIDTH=CACHE_ENTRY_WIDTH+TAG_STORED_WIDTH;
    wire [TAG_WRITE_DOMAINS*TAG_WRITE_WIDTH-1:0] tag_write_views;
    wire unused_tag_write_views_bits = &{1'b0, tag_write_views};

    rv32_frequency_control_tree #(.WIDTH(TAG_WRITE_WIDTH),.LEAVES(TAG_WRITE_DOMAINS)) tag_write_tree (
        .signal_i({refill_entry,mem_resp_line_addr_i[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4]}),
        .views_o(tag_write_views));
    localparam integer LRU_QUERY_DOMAINS=(CACHE_SETS+3)/4;
    localparam integer LRU_QUERY_WIDTH=2*CACHE_SET_WIDTH+2;
    wire [LRU_QUERY_DOMAINS*LRU_QUERY_WIDTH-1:0] lru_query_views;
    wire unused_lru_query_views_bits = &{1'b0, lru_query_views};

    rv32_frequency_control_tree #(.WIDTH(LRU_QUERY_WIDTH),.LEAVES(LRU_QUERY_DOMAINS)) lru_query_tree (
        .signal_i({refill_set,refill_entry[0],request_set,request_entry[0]}),
        .views_o(lru_query_views));
    genvar metadata_entry,metadata_set;
    generate
`ifdef CPU2026_WORD_SIM
    if(CACHE_LINES==128 && CACHE_WAYS==2 && CACHE_SET_WIDTH==6 &&
       CACHE_ENTRY_WIDTH==7 && CACHE_TAG_WIDTH==22) begin:g_word_metadata
        reg [31:0] valid_words [0:3];
        reg [TAG_STORED_WIDTH-1:0] stored_tags [0:127];
        reg [63:0] lru_bits;
        for(genvar word=0;word<4;word=word+1) begin:g_valid_word
            wire [31:0] install=(refill_array_write && refill_entry[6:5]==word) ?
                (32'b1 << refill_entry[4:0]) : 32'b0;
            wire [31:0] invalidate=region_invalidate[word*32+:32];
            assign valid_bits[word*32+:32]=valid_words[word];
            always @(posedge clk_i) begin
                if(reset_i) valid_words[word]<=0;
                else if(|(install|invalidate))
                    valid_words[word]<=(valid_words[word]&~invalidate)|install;
            end
        end
        // Original tag writes have no reset, and only the qualified refill
        // entry is written. Per-way exact prefixes retain their state owners.
        always @(posedge clk_i) if(refill_array_write)
            stored_tags[refill_entry]<=mem_resp_line_addr_i[31-TAG_REGION_BITS:CACHE_SET_WIDTH+4];
        for(metadata_entry=0;metadata_entry<128;metadata_entry=metadata_entry+1) begin:g_tag_view
            if(TAG_REGION_BITS!=0) begin:g_prefix
                assign tag_mem[metadata_entry]={
                    tag_regions[(metadata_entry%2)*REGION_STORAGE_WIDTH+:REGION_STORAGE_WIDTH],
                    stored_tags[metadata_entry]};
            end else begin:g_full
                assign tag_mem[metadata_entry]=stored_tags[metadata_entry];
            end
        end
        for(metadata_set=0;metadata_set<64;metadata_set=metadata_set+1) begin:g_lru_view
            assign lru_mem[metadata_set]=lru_bits[metadata_set];
        end
        always @(posedge clk_i) begin
            if(reset_i) lru_bits<=0;
            else begin
                if(hit_array_read) lru_bits[request_set]<=~request_entry[0];
                if(refill_array_write) lru_bits[refill_set]<=~refill_entry[0];
            end
        end
    end else begin:g_original_metadata
`endif
        for(metadata_entry=0;metadata_entry<CACHE_LINES;metadata_entry=metadata_entry+1) begin:g_valid_owner
            reg valid_q;
            wire [CACHE_ENTRY_WIDTH-1:0] local_refill_entry;
            wire [TAG_STORED_WIDTH-1:0] local_refill_tag;
            wire tag_write;
            assign {local_refill_entry,local_refill_tag}=tag_write_views[(metadata_entry/4)*TAG_WRITE_WIDTH +: TAG_WRITE_WIDTH];
            assign tag_write=metadata_refill[metadata_entry] && local_refill_entry==metadata_entry;
            assign valid_bits[metadata_entry]=valid_q;
            always @(posedge clk_i) begin
                if(metadata_reset[metadata_entry]) valid_q<=1'b0;
                else if(tag_write) valid_q<=1'b1;
                // New fill remains valid; all other rows in the changed way
                // lose validity on the same edge as its new exact prefix.
                else if(region_invalidate[metadata_entry]) valid_q<=1'b0;
            end
            // Allocation writes all tag bits before valid exposes them.
            // The old unreset dynamic write has the same qualified edge.
            wire [TAG_STORED_WIDTH-1:0] stored_tag;
            rv32_frequency_word_bank #(.WIDTH(TAG_STORED_WIDTH)) tag_owner (
                .clk_i(clk_i),.write_i(tag_write),.data_i(local_refill_tag),.data_o(stored_tag));
            if(TAG_REGION_BITS!=0) begin:g_exact_region_tag
                assign tag_mem[metadata_entry]={
                    tag_regions[(metadata_entry%CACHE_WAYS)*REGION_STORAGE_WIDTH +: REGION_STORAGE_WIDTH],stored_tag};
            end else begin:g_full_tag
                assign tag_mem[metadata_entry]=stored_tag;
            end
        end
        for(metadata_set=0;metadata_set<CACHE_SETS;metadata_set=metadata_set+1) begin:g_lru_owner
            reg lru_q;
            wire [CACHE_SET_WIDTH-1:0] local_refill_set,local_request_set;
            wire local_refill_way,local_request_way;
            assign {local_refill_set,local_refill_way,local_request_set,local_request_way}=
                lru_query_views[(metadata_set/4)*LRU_QUERY_WIDTH +: LRU_QUERY_WIDTH];
            assign lru_mem[metadata_set]=lru_q;
            always @(posedge clk_i) begin
                if(metadata_reset[CACHE_LINES+metadata_set]) lru_q<=1'b0;
                else if(CACHE_WAYS==2) begin
                    // Successful refill is later than same-edge hit in the
                    // original process and therefore retains higher priority.
                    if(metadata_refill_lru[metadata_set] && local_refill_set==metadata_set) lru_q<=~local_refill_way;
                    else if(metadata_hit_lru[metadata_set] && local_request_set==metadata_set) lru_q<=~local_request_way;
                end
            end
        end

`ifdef CPU2026_WORD_SIM
    end
`endif
    endgenerate

    integer reset_index;
    localparam integer PREFETCH_LIMIT = (PREFETCH_DISTANCE < MSHR_ENTRIES-1) ? PREFETCH_DISTANCE : MSHR_ENTRIES-1;

    localparam integer RESPONSE_META_WIDTH=65+EPOCH_WIDTH;
    wire response_hit_write=!reset_i && hit_array_read;
    // Same-cycle promotion selects one completed metadata packet. Each
    // select leaf owns at most sixteen mux bits, rather than one condition
    // driving all epoch/PC/line-address bits after global mapping.
    localparam integer PROMOTED_META_WIDTH=64+EPOCH_WIDTH;
    localparam integer PROMOTED_META_WORDS=(PROMOTED_META_WIDTH+15)/16;
    wire [PROMOTED_META_WORDS-1:0] promoted_meta_views;
    wire [PROMOTED_META_WIDTH-1:0] promoted_meta_packet={
        lookup_req_epoch,mem_resp_line_addr_i,lookup_req_pc};
    wire [PROMOTED_META_WIDTH-1:0] stored_meta_packet={
        mshr_demand_epoch[response_index],mshr_line[response_index],mshr_pc[response_index]};
    wire [PROMOTED_META_WIDTH-1:0] memory_meta_packet;
    rv32_frequency_control_tree #(.LEAVES(PROMOTED_META_WORDS)) promoted_meta_tree (
        .signal_i(response_promoted),.views_o(promoted_meta_views));
    genvar promoted_meta_word;
    generate for(promoted_meta_word=0;promoted_meta_word<PROMOTED_META_WORDS;
                 promoted_meta_word=promoted_meta_word+1) begin:g_promoted_meta_word
        localparam integer LOW=promoted_meta_word*16;
        localparam integer BITS=(PROMOTED_META_WIDTH-LOW>=16)?16:PROMOTED_META_WIDTH-LOW;
        assign memory_meta_packet[LOW +: BITS]=promoted_meta_views[promoted_meta_word]?
            promoted_meta_packet[LOW +: BITS]:stored_meta_packet[LOW +: BITS];
    end endgenerate
    wire [2*RESPONSE_META_WIDTH-1:0] response_metadata_values={
        mem_resp_error_i || !response_matches,memory_meta_packet,
        1'b0,lookup_req_epoch,request_line,lookup_req_pc};
    wire response_metadata_write;
    wire [RESPONSE_META_WIDTH-1:0] response_metadata_next,response_metadata_saved;
    rv32_frequency_event_select #(.WIDTH(RESPONSE_META_WIDTH),.EVENTS(2)) response_metadata_selector (
        .events_i({response_memory_write,response_hit_write}),.values_i(response_metadata_values),
        .write_o(response_metadata_write),.value_o(response_metadata_next));
    rv32_frequency_word_bank #(.WIDTH(RESPONSE_META_WIDTH)) response_metadata_owner (
        .clk_i(clk_i),.write_i(response_metadata_write),.data_i(response_metadata_next),.data_o(response_metadata_saved));
    assign {resp_error_reg,resp_epoch_reg,resp_line_reg,resp_pc_reg}=response_metadata_saved;

    wire stream_start=!reset_i && stream_reset;
    wire stream_control_start=!reset_i && control_target_allocate;
    wire stream_line_write;
    wire [31:0] stream_line_next;
    wire [3*32-1:0] stream_line_values={
        ({control_target[31:4],4'b0}+32'd16),request_line+32'd16,prefetch_next_line+32'd16};
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(3)) stream_line_selector (
        .events_i({stream_control_start,stream_start,!reset_i && prefetch_step}),.values_i(stream_line_values),
        .write_o(stream_line_write),.value_o(stream_line_next));
    rv32_frequency_word_bank #(.WIDTH(32)) stream_line_owner (
        .clk_i(clk_i),.write_i(stream_line_write),.data_i(stream_line_next),.data_o(prefetch_next_line));
    wire stream_epoch_write;
    wire [EPOCH_WIDTH-1:0] stream_epoch_next;
    rv32_frequency_event_select #(.WIDTH(EPOCH_WIDTH),.EVENTS(2)) stream_epoch_selector (
        .events_i({stream_control_start,stream_start}),.values_i({current_epoch_i,lookup_req_epoch}),
        .write_o(stream_epoch_write),.value_o(stream_epoch_next));
    rv32_frequency_word_bank #(.WIDTH(EPOCH_WIDTH)) stream_epoch_owner (
        .clk_i(clk_i),.write_i(stream_epoch_write),.data_i(stream_epoch_next),.data_o(prefetch_epoch));
    rv32_frequency_word_bank #(.WIDTH(32)) demand_line_owner (
        .clk_i(clk_i),.write_i(!reset_i && stream_request),.data_i(request_line),.data_o(last_demand_line));

    always @(posedge clk_i) begin
        if (reset_i)
        begin
            resp_valid_reg <= 1'b0;
            resp_from_sram <= 1'b0;
            prefetch_active <= 1'b0;
            prefetch_remaining <= 0;
            prefetch_control_stream <= 1'b0;
            last_demand_valid <= 1'b0;
            event_request_o <= 1'b0;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= 1'b0;
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1)
            begin
                if (MSHR_STATIC_WRITES == 0)
                begin
                    mshr_valid[reset_index] <= 1'b0;
                    mshr_sent[reset_index] <= 1'b0;
                    mshr_prefetch[reset_index] <= 1'b0;
                    mshr_control_prefetch[reset_index] <= 1'b0;
                    mshr_pc[reset_index] <= 32'd0;
                    mshr_line[reset_index] <= 32'd0;
                    mshr_demand_epoch[reset_index] <= {EPOCH_WIDTH{1'b0}};
                    mshr_txn_epoch[reset_index] <= {EPOCH_WIDTH{1'b0}};
                end
            end
        end
        else
        begin
            resp_from_sram <= 1'b0;
            event_request_o <= request_fire;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= lookup_req_valid && !lookup_req_ready;
            if (response_slot_free)
                resp_valid_reg <= 1'b0;
            for (k = 0; k < MSHR_ENTRIES; k = k + 1)
            begin
                if (mshr_valid[k] &&
                (mshr_txn_epoch[k] != current_epoch_i) &&
                !mshr_control_prefetch[k])
                begin
                    if (MSHR_STATIC_WRITES == 0)
                    begin
                        mshr_valid[k] <= 1'b0;
                        mshr_sent[k] <= 1'b0;
                        mshr_control_prefetch[k] <= 1'b0;
                    end
                end
            end
            if (prefetch_active && (prefetch_epoch != current_epoch_i) &&
            !prefetch_control_stream)
            begin
                prefetch_active <= 1'b0;
                prefetch_remaining <= 0;
                last_demand_valid <= 1'b0;
            end
            if (request_fire)
            begin
                if (request_hit)
                begin
                    event_hit_o <= 1'b1;
                    if (lookup_req_epoch == current_epoch_i)
                    begin
                        resp_valid_reg <= 1'b1;
                        resp_from_sram <= 1'b1;
                    end
                end
                else
                begin
                    event_miss_o <= 1'b1;
                    if (request_match_found)
                    begin
                        if (MSHR_STATIC_WRITES == 0)
                        begin
                            mshr_prefetch[request_match_index] <= 1'b0;
                            mshr_pc[request_match_index] <= lookup_req_pc;
                            mshr_demand_epoch[request_match_index] <= lookup_req_epoch;
                        end
                    end
                    else
                    begin
                        if (MSHR_STATIC_WRITES == 0)
                        begin
                            mshr_valid[free_index] <= 1'b1;
                            mshr_sent[free_index] <= 1'b0;
                            mshr_prefetch[free_index] <= 1'b0;
                            mshr_control_prefetch[free_index] <= 1'b0;
                            mshr_pc[free_index] <= lookup_req_pc;
                            mshr_line[free_index] <= request_line;
                            mshr_demand_epoch[free_index] <= lookup_req_epoch;
                            mshr_txn_epoch[free_index] <= lookup_req_epoch;
                        end
                    end
                end
            end
            if (prefetch_step)
            begin
                if (!stream_sequential)
                    prefetch_remaining <= prefetch_remaining - 1;
            end
            if (prefetch_step_allocates)
            begin
                if (MSHR_STATIC_WRITES == 0)
                begin
                    mshr_valid[free_index] <= 1'b1;
                    mshr_sent[free_index] <= 1'b0;
                    mshr_prefetch[free_index] <= 1'b1;
                    mshr_control_prefetch[free_index] <= prefetch_control_stream;
                    mshr_pc[free_index] <= prefetch_next_line;
                    mshr_line[free_index] <= prefetch_next_line;
                    mshr_demand_epoch[free_index] <= prefetch_epoch;
                    mshr_txn_epoch[free_index] <= prefetch_epoch;
                end
            end
            if (stream_request)
            begin
                last_demand_valid <= 1'b1;
                if (stream_reset)
                begin
                    prefetch_active <= 1'b1;
                    prefetch_control_stream <= 1'b0;
                    prefetch_remaining <= STREAM_COUNT_WIDTH'(PREFETCH_LIMIT);
                end
                else
                    if (!prefetch_step &&
                    (32'(prefetch_remaining) < PREFETCH_DISTANCE) &&
                    (32'(prefetch_remaining) < MSHR_ENTRIES-1))
                    begin
                        prefetch_remaining <= prefetch_remaining + 1;
                    end
            end
            if (mem_req_valid_o && mem_req_ready_i)
                if (MSHR_STATIC_WRITES == 0)
                begin
                    mshr_sent[send_index] <= 1'b1;
                end
            if (mem_resp_valid_i && mem_resp_ready_o &&
            response_target_found)
            begin
                if (MSHR_STATIC_WRITES == 0)
                begin
                    mshr_valid[response_index] <= 1'b0;
                    mshr_sent[response_index] <= 1'b0;
                    mshr_control_prefetch[response_index] <= 1'b0;
                end
                event_refill_o <= !mem_resp_error_i && response_matches;
                if (request_fire && request_match_found &&
                (request_match_index == response_index))
                begin
                    if (lookup_req_epoch == current_epoch_i)
                    begin
                        resp_valid_reg <= 1'b1;
                    end
                end
                else
                    if (!mshr_prefetch[response_index] &&
                    (mshr_demand_epoch[response_index] == current_epoch_i))
                    begin
                        resp_valid_reg <= 1'b1;
                    end
            end
            if (control_target_allocate)
            begin
                if (MSHR_STATIC_WRITES == 0)
                begin
                    mshr_valid[response_index] <= 1'b1;
                    mshr_sent[response_index] <= 1'b0;
                    mshr_prefetch[response_index] <= 1'b1;
                    mshr_control_prefetch[response_index] <= 1'b1;
                    mshr_pc[response_index] <= control_target;
                    mshr_line[response_index] <=
                    {control_target[31:4], 4'b0};
                    mshr_demand_epoch[response_index] <= current_epoch_i;
                    mshr_txn_epoch[response_index] <= current_epoch_i;
                end
                prefetch_active <= 1'b1;
                prefetch_control_stream <= 1'b1;
                prefetch_remaining <= STREAM_COUNT_WIDTH'(PREFETCH_LIMIT);
            end
        end
    end

    // Constant row indices avoid steering wide update payloads through
    // variable memory write ports. Later clauses retain the original priority:
    // cleanup, demand, sequential prefetch, send, response, control prefetch.
    genvar mshr_row;
    generate if (MSHR_STATIC_WRITES != 0) begin:g_static_mshr
        for (mshr_row=0; mshr_row<MSHR_ENTRIES; mshr_row=mshr_row+1) begin:g_row
            if (MSHR_STATE_BANKS != 0) begin:g_owned
                wire bank_valid;
                wire bank_sent;
                wire bank_prefetch;
                wire bank_control_prefetch;
                wire [31:0] bank_pc;
                wire [31:0] bank_line;
                wire [EPOCH_WIDTH-1:0] bank_demand_epoch;
                wire [EPOCH_WIDTH-1:0] bank_txn_epoch;
                rv32_icache_mshr_state_bank #(.EPOCH_WIDTH(EPOCH_WIDTH), .ROW(mshr_row)) state_bank (
                    .clk_i(clk_i),
                    .reset_i(reset_i),
                    .current_epoch_i(current_epoch_i),
                    .request_fire_i(request_fire),
                    .request_hit_i(request_hit),
                    .request_match_found_i(request_match_found),
                    .request_match_index_i(request_match_index),
                    .free_index_i(free_index),
                    .if_req_pc_i(lookup_req_pc),
                    .request_line_i(request_line),
                    .if_req_epoch_i(lookup_req_epoch),
                    .prefetch_step_allocates_i(prefetch_step_allocates),
                    .prefetch_control_stream_i(prefetch_control_stream),
                    .prefetch_next_line_i(prefetch_next_line),
                    .prefetch_epoch_i(prefetch_epoch),
                    .mem_req_valid_i(mem_req_valid_o),
                    .mem_req_ready_i(mem_req_ready_i),
                    .send_index_i(send_index),
                    .mem_resp_valid_i(mem_resp_valid_i),
                    .mem_resp_ready_i(mem_resp_ready_o),
                    .response_target_found_i(response_target_found),
                    .response_index_i(response_index),
                    .control_target_allocate_i(control_target_allocate),
                    .control_target_i(control_target),
                    .valid_o(bank_valid),
                    .sent_o(bank_sent),
                    .prefetch_o(bank_prefetch),
                    .control_prefetch_o(bank_control_prefetch),
                    .pc_o(bank_pc),
                    .line_o(bank_line),
                    .demand_epoch_o(bank_demand_epoch),
                    .txn_epoch_o(bank_txn_epoch)
                );
                always @* begin
                    mshr_valid[mshr_row] = bank_valid;
                    mshr_sent[mshr_row] = bank_sent;
                    mshr_prefetch[mshr_row] = bank_prefetch;
                    mshr_control_prefetch[mshr_row] = bank_control_prefetch;
                    mshr_pc[mshr_row] = bank_pc;
                    mshr_line[mshr_row] = bank_line;
                    mshr_demand_epoch[mshr_row] = bank_demand_epoch;
                    mshr_txn_epoch[mshr_row] = bank_txn_epoch;
                end
            end else begin:g_flat
                always @(posedge clk_i) begin
                    if (reset_i) begin
                        mshr_valid[mshr_row] <= 1'b0;
                        mshr_sent[mshr_row] <= 1'b0;
                        mshr_prefetch[mshr_row] <= 1'b0;
                        mshr_control_prefetch[mshr_row] <= 1'b0;
                        mshr_pc[mshr_row] <= 32'd0;
                        mshr_line[mshr_row] <= 32'd0;
                        mshr_demand_epoch[mshr_row] <= {EPOCH_WIDTH{1'b0}};
                        mshr_txn_epoch[mshr_row] <= {EPOCH_WIDTH{1'b0}};
                    end else begin
                        if (mshr_valid[mshr_row] &&
                            (mshr_txn_epoch[mshr_row] != current_epoch_i) &&
                            !mshr_control_prefetch[mshr_row]) begin
                            mshr_valid[mshr_row] <= 1'b0;
                            mshr_sent[mshr_row] <= 1'b0;
                            mshr_control_prefetch[mshr_row] <= 1'b0;
                        end
                        if (request_fire && !request_hit) begin
                            if (request_match_found) begin
                                if (request_match_index == mshr_row) begin
                                    mshr_prefetch[mshr_row] <= 1'b0;
                                    mshr_pc[mshr_row] <= lookup_req_pc;
                                    mshr_demand_epoch[mshr_row] <= lookup_req_epoch;
                                end
                            end else if (free_index == mshr_row) begin
                                mshr_valid[mshr_row] <= 1'b1;
                                mshr_sent[mshr_row] <= 1'b0;
                                mshr_prefetch[mshr_row] <= 1'b0;
                                mshr_control_prefetch[mshr_row] <= 1'b0;
                                mshr_pc[mshr_row] <= lookup_req_pc;
                                mshr_line[mshr_row] <= request_line;
                                mshr_demand_epoch[mshr_row] <= lookup_req_epoch;
                                mshr_txn_epoch[mshr_row] <= lookup_req_epoch;
                            end
                        end
                        if (prefetch_step_allocates && (free_index == mshr_row)) begin
                            mshr_valid[mshr_row] <= 1'b1;
                            mshr_sent[mshr_row] <= 1'b0;
                            mshr_prefetch[mshr_row] <= 1'b1;
                            mshr_control_prefetch[mshr_row] <= prefetch_control_stream;
                            mshr_pc[mshr_row] <= prefetch_next_line;
                            mshr_line[mshr_row] <= prefetch_next_line;
                            mshr_demand_epoch[mshr_row] <= prefetch_epoch;
                            mshr_txn_epoch[mshr_row] <= prefetch_epoch;
                        end
                        if (mem_req_valid_o && mem_req_ready_i && (send_index == mshr_row))
                            mshr_sent[mshr_row] <= 1'b1;
                        if (mem_resp_valid_i && mem_resp_ready_o &&
                            response_target_found && (response_index == mshr_row)) begin
                            mshr_valid[mshr_row] <= 1'b0;
                            mshr_sent[mshr_row] <= 1'b0;
                            mshr_control_prefetch[mshr_row] <= 1'b0;
                        end
                        if (control_target_allocate && (response_index == mshr_row)) begin
                            mshr_valid[mshr_row] <= 1'b1;
                            mshr_sent[mshr_row] <= 1'b0;
                            mshr_prefetch[mshr_row] <= 1'b1;
                            mshr_control_prefetch[mshr_row] <= 1'b1;
                            mshr_pc[mshr_row] <= control_target;
                            mshr_line[mshr_row] <= {control_target[31:4], 4'b0};
                            mshr_demand_epoch[mshr_row] <= current_epoch_i;
                            mshr_txn_epoch[mshr_row] <= current_epoch_i;
                        end
                    end
                end
            end
        end
    end endgenerate

    initial begin
        if((CONTROL_REGION_PREQUERY!=0 && CONTROL_REGION_PREQUERY!=1) ||
            (CONTROL_REGION_PREQUERY!=0 && (TAG_MATCH_PARALLEL==0 || TAG_REGION_BITS<1 ||
             TAG_REGION_BITS>=CACHE_TAG_WIDTH)))
            $fatal(1,"Control region prequery requires complete original region/low tags");
        if(CONTROL_TARGET_PREFIX!=0 && CONTROL_TARGET_PREFIX!=1)
            $fatal(1,"I-cache prefix target policy must be 0 or 1");
        if(QUERY_DOMAINS<1 || QUERY_DOMAINS>CACHE_SETS ||
           (QUERY_DOMAINS & (QUERY_DOMAINS-1))!=0 || CACHE_SETS%QUERY_DOMAINS!=0)
            $fatal(1,"I-cache query domains must divide the power-of-two cache sets");
        if(CLASS_SEND_SELECT!=0 && CLASS_SEND_SELECT!=1)
            $fatal(1,"I-cache class send selection must be 0 or 1");
        if(TAG_REGION_BITS<0 || TAG_REGION_BITS>=CACHE_TAG_WIDTH)
            $fatal(1,"Instruction cache region bits must be0..CACHE_TAG_WIDTH-1");
        if ((MSHR_STATE_BANKS != 0) && (MSHR_STATIC_WRITES == 0))
            $fatal(1, "MSHR_STATE_BANKS requires fixed-slot writes");
        if (CACHE_LINES < 16 || CACHE_LINES > 4096 ||
            ((CACHE_LINES & (CACHE_LINES - 1)) != 0) ||
            ((CACHE_WAYS != 1) && (CACHE_WAYS != 2)) ||
            (CACHE_LINES % CACHE_WAYS != 0)) begin
            $display("ERROR: invalid rv32_icache_nonblocking cache geometry");
            $finish;
        end
        if (MSHR_ENTRIES < 2 || MSHR_ENTRIES > 16) begin
            $display("ERROR: rv32_icache_nonblocking MSHR_ENTRIES must be 2..16");
            $finish;
        end
        if (EPOCH_WIDTH > 4) begin
            $display("ERROR: rv32_icache_nonblocking requires EPOCH_WIDTH <= 4");
            $finish;
        end
    end
endmodule
