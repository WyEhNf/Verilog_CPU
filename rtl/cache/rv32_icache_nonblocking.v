`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Small non-blocking instruction cache used by the performance profiles.
// The cache remains direct mapped, but independent MSHRs allow the demand
// line and several sequential prefetches to overlap the backing-memory delay.
module rv32_icache_nonblocking #(
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    parameter integer MSHR_ENTRIES = 4,
    parameter integer MSHR_STATE_BANKS = 0,
    parameter integer MSHR_STATIC_WRITES = 0,
    parameter integer TAG_MATCH_PARALLEL = 0,
    parameter integer LOCAL_RESPONSE_READY = 0,
    parameter integer REQUEST_PIPELINE = 0,
    parameter integer LOOP_BUFFER_LINES = 0,
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
        rv32_instruction_line_filter #(.LINES(LOOP_BUFFER_LINES),.EPOCH_WIDTH(EPOCH_WIDTH)) lines (
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
    wire lru_mem [0:CACHE_SETS-1];

    function [CACHE_ENTRY_WIDTH-1:0] cache_entry;
        input [CACHE_SET_WIDTH-1:0] set_index;
        input integer way;
        begin
            cache_entry = set_index * CACHE_WAYS + way;
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
    integer send_index;
    integer response_index;
    integer prefetch_match_index;
    integer control_check;
    integer control_way;
    reg request_match_found;
    reg free_found;
    reg send_found;
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
        send_found = 1'b0;
        send_index = 0;
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
                (!send_found ||
                 (mshr_prefetch[send_index] && !mshr_prefetch[k]) ||
                 (mshr_prefetch[send_index] && mshr_prefetch[k] &&
                  !mshr_control_prefetch[send_index] &&
                  mshr_control_prefetch[k]))) begin
                // Priority is demand, then a decoded direct-control target,
                // then ordinary sequential traffic.  The target line used
                // to sit behind a stale fall-through prefetch at startup.
                send_found = 1'b1;
                send_index = k;
            end
            if (!prefetch_match_found && mshr_valid[k] &&
                (mshr_txn_epoch[k] == current_epoch_i) &&
                (mshr_line[k] == prefetch_next_line)) begin
                prefetch_match_found = 1'b1;
                prefetch_match_index = k;
            end
        end

        response_index = mem_resp_id_i >> EPOCH_WIDTH;
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
        wire [31:0] base=control_base_views[control_lane*32 +: 32];
        // A J-immediate is signed21 bits with bit0=0. Adding 0/4/8/12
        // fits signed22 bits, including the positive-limit carry. This moves
        // the word displacement off the shared full-width PC carry path.
        wire [21:0] displaced_immediate=
            {inst[31],inst[31],inst[19:12],inst[20],inst[30:21],1'b0}+22'(control_lane*4);
        wire [31:0] candidate=base+{{10{displaced_immediate[21]}},displaced_immediate};
        wire [31:0] pc=base+32'(control_lane*4);
        assign control_candidates[control_lane*32 +: 32]=candidate;
        assign control_outside[control_lane]=(inst[6:0]==7'b1101111) && candidate[31:4]!=base[31:4];
        // Preserve the original UNSIGNED comparison, including address wrap.
        assign control_forward[control_lane]=control_outside[control_lane] && candidate>pc;
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
    wire [4*32-1:0] demand_pc_views,prefetch_pc_views,control_pc_views;
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) demand_query_tree (
        .signal_i(lookup_req_pc),.views_o(demand_pc_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) prefetch_query_tree (
        .signal_i(prefetch_next_line),.views_o(prefetch_pc_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) control_query_tree (
        .signal_i(control_target),.views_o(control_pc_views));
    genvar match_row;
    generate for (match_row=0; match_row<CACHE_LINES; match_row=match_row+1) begin:g_match_row
        if (TAG_MATCH_PARALLEL != 0) begin:g_parallel
            localparam integer DOMAIN=(match_row*4)/CACHE_LINES;
            wire [31:0] demand_pc=demand_pc_views[DOMAIN*32 +: 32];
            wire [31:0] prefetch_pc=prefetch_pc_views[DOMAIN*32 +: 32];
            wire [31:0] control_pc=control_pc_views[DOMAIN*32 +: 32];
            wire demand_hit=valid_bits[match_row] &&
                demand_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                tag_mem[match_row]==demand_pc[31:CACHE_SET_WIDTH+4];
            assign demand_match_way0[match_row]=(match_row%CACHE_WAYS==0) && demand_hit;
            assign demand_match_way1[match_row]=(match_row%CACHE_WAYS==1) && demand_hit;
            assign prefetch_match_rows[match_row]=valid_bits[match_row] &&
                prefetch_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                tag_mem[match_row]==prefetch_pc[31:CACHE_SET_WIDTH+4];
            assign control_match_rows[match_row]=valid_bits[match_row] &&
                control_pc[CACHE_SET_WIDTH+3:4]==(match_row/CACHE_WAYS) &&
                tag_mem[match_row]==control_pc[31:CACHE_SET_WIDTH+4];
        end else begin:g_disabled
            assign demand_match_way0[match_row] = 1'b0;
            assign demand_match_way1[match_row] = 1'b0;
            assign prefetch_match_rows[match_row] = 1'b0;
            assign control_match_rows[match_row] = 1'b0;
        end
    end endgenerate
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
                                cache_entry(refill_set, !request_entry[0]) :
                                cache_entry(refill_set, lru_mem[refill_set]))));

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

    assign mem_req_valid_o = send_found;
    assign mem_req_line_addr_o = send_found ? mshr_line[send_index] : 32'd0;
    assign mem_req_id_o = send_found ?
        ((send_index << EPOCH_WIDTH) | mshr_txn_epoch[send_index]) : 8'd0;
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
    wire [CACHE_LINES-1:0] metadata_refill;
    wire [CACHE_SETS-1:0] metadata_hit_lru,metadata_refill_lru;
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
    localparam integer TAG_WRITE_WIDTH=CACHE_ENTRY_WIDTH+CACHE_TAG_WIDTH;
    wire [TAG_WRITE_DOMAINS*TAG_WRITE_WIDTH-1:0] tag_write_views;
    rv32_frequency_control_tree #(.WIDTH(TAG_WRITE_WIDTH),.LEAVES(TAG_WRITE_DOMAINS)) tag_write_tree (
        .signal_i({refill_entry,mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4]}),
        .views_o(tag_write_views));
    localparam integer LRU_QUERY_DOMAINS=(CACHE_SETS+3)/4;
    localparam integer LRU_QUERY_WIDTH=2*CACHE_SET_WIDTH+2;
    wire [LRU_QUERY_DOMAINS*LRU_QUERY_WIDTH-1:0] lru_query_views;
    rv32_frequency_control_tree #(.WIDTH(LRU_QUERY_WIDTH),.LEAVES(LRU_QUERY_DOMAINS)) lru_query_tree (
        .signal_i({refill_set,refill_entry[0],request_set,request_entry[0]}),
        .views_o(lru_query_views));
    genvar metadata_entry,metadata_set;
    generate
        for(metadata_entry=0;metadata_entry<CACHE_LINES;metadata_entry=metadata_entry+1) begin:g_valid_owner
            reg valid_q;
            wire [CACHE_ENTRY_WIDTH-1:0] local_refill_entry;
            wire [CACHE_TAG_WIDTH-1:0] local_refill_tag;
            wire tag_write;
            assign {local_refill_entry,local_refill_tag}=tag_write_views[(metadata_entry/4)*TAG_WRITE_WIDTH +: TAG_WRITE_WIDTH];
            assign tag_write=metadata_refill[metadata_entry] && local_refill_entry==metadata_entry;
            assign valid_bits[metadata_entry]=valid_q;
            always @(posedge clk_i) begin
                if(metadata_reset[metadata_entry]) valid_q<=1'b0;
                else if(tag_write) valid_q<=1'b1;
            end
            // Allocation writes all tag bits before valid exposes them.
            // The old unreset dynamic write has the same qualified edge.
            rv32_frequency_word_bank #(.WIDTH(CACHE_TAG_WIDTH)) tag_owner (
                .clk_i(clk_i),.write_i(tag_write),.data_i(local_refill_tag),.data_o(tag_mem[metadata_entry]));
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
    endgenerate

    integer reset_index;
    integer prefetch_count;

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
        if (reset_i) begin
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
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1) begin
                if (MSHR_STATIC_WRITES == 0) begin
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
        end else begin
            resp_from_sram <= 1'b0;
            event_request_o <= request_fire;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= lookup_req_valid && !lookup_req_ready;

            if (response_slot_free)
                resp_valid_reg <= 1'b0;

            // Redirects advance current_epoch_i.  Wrong-path demand and
            // prefetch MSHRs are immediately reusable; the transaction ID
            // carries the old epoch so any late response is rejected above.
            for (k = 0; k < MSHR_ENTRIES; k = k + 1) begin
                if (mshr_valid[k] &&
                    (mshr_txn_epoch[k] != current_epoch_i) &&
                    !mshr_control_prefetch[k]) begin
                    if (MSHR_STATIC_WRITES == 0) begin
                        mshr_valid[k] <= 1'b0;
                        mshr_sent[k] <= 1'b0;
                        mshr_control_prefetch[k] <= 1'b0;
                    end
                end
            end
            if (prefetch_active && (prefetch_epoch != current_epoch_i) &&
                !prefetch_control_stream) begin
                prefetch_active <= 1'b0;
                prefetch_remaining <= 0;
                last_demand_valid <= 1'b0;
            end

            if (request_fire) begin
                if (request_hit) begin
                    event_hit_o <= 1'b1;
                    if (lookup_req_epoch == current_epoch_i) begin
                        resp_valid_reg <= 1'b1;
                        resp_from_sram <= 1'b1;
                    end
                end else begin
                    event_miss_o <= 1'b1;
                    if (request_match_found) begin
                        if (MSHR_STATIC_WRITES == 0) begin
                            mshr_prefetch[request_match_index] <= 1'b0;
                            mshr_pc[request_match_index] <= lookup_req_pc;
                            mshr_demand_epoch[request_match_index] <= lookup_req_epoch;
                        end
                    end else begin
                        if (MSHR_STATIC_WRITES == 0) begin
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

            // Keep a bounded sliding window in front of the most recent
            // demand line.  Advancing sequentially earns exactly one new
            // prefetch credit; a non-sequential request (taken branch/jump)
            // discards the old direction and seeds a fresh bounded window.
            // This preserves memory-level parallelism on long straight-line
            // regions without issuing an unbounded wrong-path stream.
            if (prefetch_step) begin
                if (!stream_sequential)
                    prefetch_remaining <= prefetch_remaining - 1;
            end
            if (prefetch_step_allocates) begin
                if (MSHR_STATIC_WRITES == 0) begin
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

            if (stream_request) begin
                last_demand_valid <= 1'b1;
                if (stream_reset) begin
                    prefetch_active <= 1'b1;
                    prefetch_control_stream <= 1'b0;
                    prefetch_count = PREFETCH_DISTANCE;
                    if (prefetch_count > MSHR_ENTRIES-1)
                        prefetch_count = MSHR_ENTRIES-1;
                    prefetch_remaining <= prefetch_count;
                end else if (!prefetch_step &&
                             (prefetch_remaining < PREFETCH_DISTANCE) &&
                             (prefetch_remaining < MSHR_ENTRIES-1)) begin
                    prefetch_remaining <= prefetch_remaining + 1;
                end
            end

            if (mem_req_valid_o && mem_req_ready_i)
                if (MSHR_STATIC_WRITES == 0) begin
                    mshr_sent[send_index] <= 1'b1;
                end

            if (mem_resp_valid_i && mem_resp_ready_o &&
                response_target_found) begin
                if (MSHR_STATIC_WRITES == 0) begin
                    mshr_valid[response_index] <= 1'b0;
                    mshr_sent[response_index] <= 1'b0;
                    mshr_control_prefetch[response_index] <= 1'b0;
                end
                event_refill_o <= !mem_resp_error_i && response_matches;
                // Tag payload belongs to the static row owners above.

                if (request_fire && request_match_found &&
                    (request_match_index == response_index)) begin
                    if (lookup_req_epoch == current_epoch_i) begin
                        resp_valid_reg <= 1'b1;
                    end
                end else if (!mshr_prefetch[response_index] &&
                             (mshr_demand_epoch[response_index] == current_epoch_i)) begin
                    resp_valid_reg <= 1'b1;
                end
            end

            if (control_target_allocate) begin
                if (MSHR_STATIC_WRITES == 0) begin
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
                prefetch_count = PREFETCH_DISTANCE;
                if (prefetch_count > MSHR_ENTRIES-1)
                    prefetch_count = MSHR_ENTRIES-1;
                prefetch_remaining <= prefetch_count;
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
                    .primary_if_req_pc(lookup_req_pc),
                    .request_line_i(request_line),
                    .primary_if_req_epoch(lookup_req_epoch),
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

// Functional storage row: owns all MSHR state and decodes updates locally.
module rv32_icache_mshr_state_bank #(
    parameter integer EPOCH_WIDTH = 4,
    parameter integer ROW = 0
) (
    input wire clk_i,
    input wire reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire request_fire_i,
    input wire request_hit_i,
    input wire request_match_found_i,
    input wire [31:0] request_match_index_i,
    input wire [31:0] free_index_i,
    input wire [31:0] if_req_pc_i,
    input wire [31:0] request_line_i,
    input wire [EPOCH_WIDTH-1:0] if_req_epoch_i,
    input wire prefetch_step_allocates_i,
    input wire prefetch_control_stream_i,
    input wire [31:0] prefetch_next_line_i,
    input wire [EPOCH_WIDTH-1:0] prefetch_epoch_i,
    input wire mem_req_valid_i,
    input wire mem_req_ready_i,
    input wire [31:0] send_index_i,
    input wire mem_resp_valid_i,
    input wire mem_resp_ready_i,
    input wire response_target_found_i,
    input wire [31:0] response_index_i,
    input wire control_target_allocate_i,
    input wire [31:0] control_target_i,
    output reg valid_o,
    output reg sent_o,
    output reg prefetch_o,
    output reg control_prefetch_o,
    output wire [31:0] pc_o,
    output wire [31:0] line_o,
    output wire [EPOCH_WIDTH-1:0] demand_epoch_o,
    output wire [EPOCH_WIDTH-1:0] txn_epoch_o
);

    localparam integer MSHR_PAYLOAD_WIDTH=32+EPOCH_WIDTH;
    wire enabled=!reset_i;
    wire demand=enabled && request_fire_i && !request_hit_i;
    wire demand_match=demand && request_match_found_i && request_match_index_i==ROW;
    wire demand_new=demand && !request_match_found_i && free_index_i==ROW;
    wire prefetch_allocate=enabled && prefetch_step_allocates_i && free_index_i==ROW;
    wire control_allocate=enabled && control_target_allocate_i && response_index_i==ROW;
    wire [2:0] pc_events={control_allocate,prefetch_allocate,demand_match || demand_new};
    wire [2:0] line_events={control_allocate,prefetch_allocate,demand_new};
    wire [3*MSHR_PAYLOAD_WIDTH-1:0] pc_values={
        current_epoch_i,control_target_i,prefetch_epoch_i,prefetch_next_line_i,if_req_epoch_i,if_req_pc_i};
    wire [3*MSHR_PAYLOAD_WIDTH-1:0] line_values={
        current_epoch_i,control_target_i[31:4],4'b0,prefetch_epoch_i,prefetch_next_line_i,if_req_epoch_i,request_line_i};
    wire pc_write,line_write;
    wire [MSHR_PAYLOAD_WIDTH-1:0] next_pc,next_line,saved_pc,saved_line;
    rv32_frequency_event_select #(.WIDTH(MSHR_PAYLOAD_WIDTH),.EVENTS(3)) pc_selector (
        .events_i(pc_events),.values_i(pc_values),.write_o(pc_write),.value_o(next_pc));
    rv32_frequency_event_select #(.WIDTH(MSHR_PAYLOAD_WIDTH),.EVENTS(3)) line_selector (
        .events_i(line_events),.values_i(line_values),.write_o(line_write),.value_o(next_line));
    rv32_frequency_word_bank #(.WIDTH(MSHR_PAYLOAD_WIDTH)) pc_owner (
        .clk_i(clk_i),.write_i(pc_write),.data_i(next_pc),.data_o(saved_pc));
    rv32_frequency_word_bank #(.WIDTH(MSHR_PAYLOAD_WIDTH)) line_owner (
        .clk_i(clk_i),.write_i(line_write),.data_i(next_line),.data_o(saved_line));
    assign {demand_epoch_o,pc_o}=saved_pc;
    assign {txn_epoch_o,line_o}=saved_line;

    always @(posedge clk_i) begin
        if (reset_i) begin
            valid_o <= 1'b0;
            sent_o <= 1'b0;
            prefetch_o <= 1'b0;
            control_prefetch_o <= 1'b0;
        end else begin
            if (valid_o &&
                (txn_epoch_o != current_epoch_i) &&
                !control_prefetch_o) begin
                valid_o <= 1'b0;
                sent_o <= 1'b0;
                control_prefetch_o <= 1'b0;
            end
            if (request_fire_i && !request_hit_i) begin
                if (request_match_found_i) begin
                    if (request_match_index_i == ROW) begin
                        prefetch_o <= 1'b0;
                    end
                end else if (free_index_i == ROW) begin
                    valid_o <= 1'b1;
                    sent_o <= 1'b0;
                    prefetch_o <= 1'b0;
                    control_prefetch_o <= 1'b0;
                end
            end
            if (prefetch_step_allocates_i && (free_index_i == ROW)) begin
                valid_o <= 1'b1;
                sent_o <= 1'b0;
                prefetch_o <= 1'b1;
                control_prefetch_o <= prefetch_control_stream_i;
            end
            if (mem_req_valid_i && mem_req_ready_i && (send_index_i == ROW))
                sent_o <= 1'b1;
            if (mem_resp_valid_i && mem_resp_ready_i &&
                response_target_found_i && (response_index_i == ROW)) begin
                valid_o <= 1'b0;
                sent_o <= 1'b0;
                control_prefetch_o <= 1'b0;
            end
            if (control_target_allocate_i && (response_index_i == ROW)) begin
                valid_o <= 1'b1;
                sent_o <= 1'b0;
                prefetch_o <= 1'b1;
                control_prefetch_o <= 1'b1;
            end
        end
    end
endmodule

// Two request slots decouple front-end ready from tag/MSHR/response logic.
// Epoch-stale requests drain independently of lookup readiness.
module rv32_icache_query_queue #(parameter integer EPOCH_WIDTH=4) (
    input wire clk_i,reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire valid_i,
    output wire ready_o,
    input wire [31:0] pc_i,
    input wire [EPOCH_WIDTH-1:0] epoch_i,
    output wire valid_o,
    input wire ready_i,
    output wire [31:0] pc_o,
    output wire [EPOCH_WIDTH-1:0] epoch_o
);
    reg [1:0] count;
    reg read_slot,write_slot;
    localparam integer PAYLOAD_WIDTH=32+EPOCH_WIDTH;
    localparam integer PAYLOAD_WORDS=(PAYLOAD_WIDTH+15)/16;
    wire [PAYLOAD_WIDTH-1:0] payload [0:1];
    wire [PAYLOAD_WORDS-1:0] read_views;
    wire [PAYLOAD_WIDTH-1:0] read_payload;
    rv32_frequency_control_tree #(.LEAVES(PAYLOAD_WORDS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    assign {pc_o,epoch_o}=read_payload;
    genvar read_word;
    generate for(read_word=0;read_word<PAYLOAD_WORDS;read_word=read_word+1) begin:g_read_word
        localparam integer LOW=read_word*16;
        localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
        assign read_payload[LOW +: BITS]=read_views[read_word]?
            payload[1][LOW +: BITS]:payload[0][LOW +: BITS];
    end endgenerate
    wire stale=count!=0 && epoch_o!=current_epoch_i;
    assign ready_o=!reset_i && count<2;
    assign valid_o=!reset_i && count!=0 && !stale;
    wire push=valid_i && ready_o;
    wire pop=!reset_i && (stale || (valid_o && ready_i));
    genvar queue_row;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        // Preserve the same two unreset payload slots and write edge.
        // Each write leaf now owns at most sixteen existing hold muxes.
        rv32_frequency_word_bank #(.WIDTH(PAYLOAD_WIDTH)) owner (
            .clk_i(clk_i),.write_i(push && write_slot==queue_row),
            .data_i({pc_i,epoch_i}),.data_o(payload[queue_row]));
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i) begin count<=0;read_slot<=0;write_slot<=0;end
        else begin
            count<=count+push-pop;
            if(pop) read_slot<=!read_slot;
            if(push) write_slot<=!write_slot;
        end
    end
endmodule

// A small direct-mapped L0 over the immutable instruction-line interface.
// It has one registered response, at most one primary miss in flight, and
// accepts a replacement request on the same edge as a consumed response.
// There is no combinational path from a new request to response validity.
module rv32_instruction_line_filter #(
    parameter integer LINES=16,EPOCH_WIDTH=4,
    parameter integer INDEX_WIDTH=$clog2(LINES),
    parameter integer TAG_BITS=28-INDEX_WIDTH
) (
    input wire clk_i,reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire if_req_valid_i,
    output wire if_req_ready_o,
    input wire [31:0] if_req_pc_i,
    input wire [EPOCH_WIDTH-1:0] if_req_epoch_i,
    output wire if_resp_valid_o,
    input wire if_resp_ready_i,
    output wire [31:0] if_resp_pc_o,if_resp_line_addr_o,
    output wire [127:0] if_resp_line_data_o,
    output wire [EPOCH_WIDTH-1:0] if_resp_epoch_o,
    output wire if_resp_error_o,
    output wire primary_req_valid_o,
    input wire primary_req_ready_i,
    output wire [31:0] primary_req_pc_o,
    output wire [EPOCH_WIDTH-1:0] primary_req_epoch_o,
    input wire primary_resp_valid_i,
    output wire primary_resp_ready_o,
    input wire [31:0] primary_resp_pc_i,primary_resp_line_addr_i,
    input wire [127:0] primary_resp_line_data_i,
    input wire [EPOCH_WIDTH-1:0] primary_resp_epoch_i,
    input wire primary_resp_error_i
);
    reg [LINES-1:0] valid;
    wire [TAG_BITS+128-1:0] row_payload [0:LINES-1];
    wire [LINES*128-1:0] row_lines;
    wire [LINES-1:0] hits;
    wire [LINES*28-1:0] request_line_views;
    rv32_frequency_control_tree #(.WIDTH(28),.LEAVES(LINES)) request_views (
        .signal_i(if_req_pc_i[31:4]),.views_o(request_line_views));
    wire [127:0] hit_line;
    rv32_frequency_event_select #(.WIDTH(128),.EVENTS(LINES),.PRIORITY(0)) line_select (
        .events_i(hits),.values_i(row_lines),.write_o(),.value_o(hit_line));
    wire hit=|hits;

    reg fast_valid,miss_pending;
    wire [31:0] fast_pc,pending_pc;
    wire [EPOCH_WIDTH-1:0] fast_epoch,pending_epoch;
    wire [127:0] fast_line;
    wire fast_live=fast_valid && fast_epoch==current_epoch_i;
    wire miss_live=miss_pending && pending_epoch==current_epoch_i;
    wire primary_live=miss_live && primary_resp_valid_i &&
        primary_resp_epoch_i==pending_epoch && primary_resp_pc_i==pending_pc;
    wire release_miss=primary_live && if_resp_ready_i;
    wire fast_slot_free=!fast_valid || !fast_live || if_resp_ready_i;
    wire can_start=!reset_i && (!miss_live || release_miss) && fast_slot_free;
    assign if_req_ready_o=can_start && (hit || primary_req_ready_i);
    wire request_fire=if_req_valid_i && if_req_ready_o;
    wire accept_hit=request_fire && hit && if_req_epoch_i==current_epoch_i;
    wire accept_miss=request_fire && !hit;
    assign primary_req_valid_o=if_req_valid_i && can_start && !hit;
    assign primary_req_pc_o=if_req_pc_i;
    assign primary_req_epoch_o=if_req_epoch_i;
    // Unexpected or epoch-stale primary outputs drain without publishing.
    // A live primary response obeys the original frontend backpressure.
    assign primary_resp_ready_o=!reset_i && (!primary_live || if_resp_ready_i);
    assign if_resp_valid_o=!reset_i && (fast_live || primary_live);
    localparam integer RESPONSE_WIDTH=65+128+EPOCH_WIDTH;
    rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2),.PRIORITY(0)) response_select (
        .events_i({fast_live,primary_live}),
        .values_i({fast_pc,{fast_pc[31:4],4'b0},fast_line,fast_epoch,1'b0,
            primary_resp_pc_i,primary_resp_line_addr_i,primary_resp_line_data_i,
            primary_resp_epoch_i,primary_resp_error_i}),.write_o(),
        .value_o({if_resp_pc_o,if_resp_line_addr_o,if_resp_line_data_o,if_resp_epoch_o,if_resp_error_o}));
    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH+128)) fast_response (
        .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i,hit_line}),
        .data_o({fast_pc,fast_epoch,fast_line}));
    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH)) miss_identity (
        .clk_i(clk_i),.write_i(accept_miss),.data_i({if_req_pc_i,if_req_epoch_i}),
        .data_o({pending_pc,pending_epoch}));
    wire fill=!reset_i && primary_live && if_resp_ready_i && !primary_resp_error_i &&
        primary_resp_line_addr_i=={primary_resp_pc_i[31:4],4'b0};
    genvar row;
    generate for(row=0;row<LINES;row=row+1) begin:g_row
        localparam [INDEX_WIDTH-1:0] ROW=row;
        wire [27:0] request_line=request_line_views[row*28 +: 28];
        wire [TAG_BITS-1:0] row_tag=row_payload[row][128 +: TAG_BITS];
        assign hits[row]=valid[row] && request_line[INDEX_WIDTH-1:0]==ROW &&
            request_line[27:INDEX_WIDTH]==row_tag;
        assign row_lines[row*128 +: 128]=row_payload[row][127:0];
        wire row_write=fill && primary_resp_line_addr_i[4 +: INDEX_WIDTH]==ROW;
        rv32_frequency_word_bank #(.WIDTH(TAG_BITS+128)) payload (
            .clk_i(clk_i),.write_i(row_write),
            .data_i({primary_resp_line_addr_i[31:4+INDEX_WIDTH],primary_resp_line_data_i}),
            .data_o(row_payload[row]));
        always @(posedge clk_i) begin
            if(reset_i) valid[row]<=1'b0;
            else if(row_write) valid[row]<=1'b1;
        end
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i) begin fast_valid<=1'b0;miss_pending<=1'b0;end
        else begin
            if(fast_slot_free) fast_valid<=1'b0;
            if(accept_hit) fast_valid<=1'b1;
            if(!miss_live || release_miss) miss_pending<=1'b0;
            if(accept_miss) miss_pending<=1'b1;
        end
    end
    initial begin
        if(LINES<2 || LINES>32 || (LINES & (LINES-1))!=0)
            $fatal(1,"Instruction line filter needs a power-of-two line count in 2..32");
    end
endmodule
