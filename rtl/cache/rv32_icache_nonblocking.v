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
    wire lookup_req_valid,lookup_req_ready;
    wire [31:0] lookup_req_pc;
    wire [EPOCH_WIDTH-1:0] lookup_req_epoch;
    generate if(REQUEST_PIPELINE!=0) begin:g_request_pipeline
        rv32_icache_query_queue #(.EPOCH_WIDTH(EPOCH_WIDTH)) requests (
            .clk_i(clk_i),.reset_i(reset_i),.current_epoch_i(current_epoch_i),
            .valid_i(if_req_valid_i),.ready_o(if_req_ready_o),.pc_i(if_req_pc_i),.epoch_i(if_req_epoch_i),
            .valid_o(lookup_req_valid),.ready_i(lookup_req_ready),.pc_o(lookup_req_pc),.epoch_o(lookup_req_epoch));
    end else begin:g_direct_request
        assign lookup_req_valid=if_req_valid_i;assign if_req_ready_o=lookup_req_ready;
        assign lookup_req_pc=if_req_pc_i;assign lookup_req_epoch=if_req_epoch_i;
    end endgenerate

    reg [CACHE_LINES-1:0] valid_bits;
    reg [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];
    reg lru_mem [0:CACHE_SETS-1];

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
    reg [31:0] resp_pc_reg;
    reg [31:0] resp_line_reg;
    reg [127:0] resp_data_reg;
    // A synchronous hit and its metadata become valid after the same edge.
    // Capture the macro result before idle/write makes rdata undefined.
    reg resp_from_sram;
    wire [127:0] data_rdata;
    reg [EPOCH_WIDTH-1:0] resp_epoch_reg;
    reg resp_error_reg;

    reg prefetch_active;
    reg [31:0] prefetch_next_line;
    reg [EPOCH_WIDTH-1:0] prefetch_epoch;
    integer prefetch_remaining;
    reg prefetch_control_stream;
    reg last_demand_valid;
    reg [31:0] last_demand_line;

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
    wire response_slot_free = !resp_valid_reg || !response_live || if_resp_ready_i;

    integer k;
    integer request_match_index;
    integer free_index;
    integer send_index;
    integer response_index;
    integer prefetch_match_index;
    integer control_word;
    integer control_check;
    integer control_way;
    reg request_match_found;
    reg free_found;
    reg send_found;
    reg response_target_found;
    reg prefetch_match_found;
    reg control_target_valid;
    reg control_target_present;
    reg [31:0] control_inst;
    reg [31:0] control_pc;
    reg [31:0] control_target;
    reg [31:0] control_candidate;
    reg control_target_forward;

    function [31:0] jal_immediate;
        input [31:0] inst;
        begin
            jal_immediate = {{11{inst[31]}}, inst[31], inst[19:12],
                             inst[20], inst[30:21], 1'b0};
        end
    endfunction

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

    // Inspect every returned line, including ordinary sequential prefetches,
    // for a direct jump whose target is outside that line.  Reusing the
    // completing MSHR starts fetching a cold call target before the jump is
    // reached by demand fetch (e.g. startup code entering main).
    always @* begin
        control_target_valid = 1'b0;
        control_target_present = 1'b0;
        control_inst = 32'd0;
        control_pc = mem_resp_line_addr_i;
        control_target = 32'd0;
        control_candidate = 32'd0;
        control_target_forward = 1'b0;
        for (control_word = 0; control_word < 4;
             control_word = control_word + 1) begin
            control_inst = mem_resp_data_i >> (control_word * 32);
            control_pc = mem_resp_line_addr_i + (control_word * 32'd4);
            if (control_inst[6:0] == 7'b1101111) begin
                control_candidate = control_pc + jal_immediate(control_inst);
                if ((control_candidate[31:4] !=
                     mem_resp_line_addr_i[31:4]) &&
                    (!control_target_valid ||
                     (!control_target_forward &&
                      (control_candidate > control_pc)))) begin
                    control_target = control_candidate;
                    control_target_valid = 1'b1;
                    control_target_forward = control_candidate > control_pc;
                end
            end
        end
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
    assign if_resp_valid_o = response_live;
    assign if_resp_pc_o = resp_pc_reg;
    assign if_resp_line_addr_o = resp_line_reg;
    assign if_resp_line_data_o = resp_from_sram ? data_rdata : resp_data_reg;
    assign if_resp_epoch_o = resp_epoch_reg;
    assign if_resp_error_o = resp_error_reg;

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

    integer reset_index;
    integer prefetch_count;
    always @(posedge clk_i) begin
        if (reset_i) begin
            resp_valid_reg <= 1'b0;
            resp_from_sram <= 1'b0;
            resp_pc_reg <= 32'd0;
            resp_line_reg <= 32'd0;
            resp_data_reg <= 128'd0;
            resp_epoch_reg <= {EPOCH_WIDTH{1'b0}};
            resp_error_reg <= 1'b0;
            prefetch_active <= 1'b0;
            prefetch_next_line <= 32'd0;
            prefetch_epoch <= {EPOCH_WIDTH{1'b0}};
            prefetch_remaining <= 0;
            prefetch_control_stream <= 1'b0;
            last_demand_valid <= 1'b0;
            last_demand_line <= 32'd0;
            event_request_o <= 1'b0;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= 1'b0;
            valid_bits <= {CACHE_LINES{1'b0}};
            for (reset_index = 0; reset_index < CACHE_SETS; reset_index = reset_index + 1)
                lru_mem[reset_index] <= 1'b0;
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
            if (resp_from_sram && resp_valid_reg)
                resp_data_reg <= data_rdata;
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
                        resp_pc_reg <= lookup_req_pc;
                        resp_line_reg <= request_line;
                        resp_from_sram <= 1'b1;
                        resp_epoch_reg <= lookup_req_epoch;
                        resp_error_reg <= 1'b0;
                        if (CACHE_WAYS == 2)
                            lru_mem[request_set] <= ~request_entry[0];
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
                prefetch_next_line <= prefetch_next_line + 32'd16;
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
                last_demand_line <= request_line;
                if (stream_reset) begin
                    prefetch_active <= 1'b1;
                    prefetch_next_line <= request_line + 32'd16;
                    prefetch_epoch <= lookup_req_epoch;
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
                if (!mem_resp_error_i && response_matches) begin
                    valid_bits[refill_entry] <= 1'b1;
                    tag_mem[refill_entry] <=
                        mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4];
                    if (CACHE_WAYS == 2)
                        lru_mem[refill_set] <= ~refill_entry[0];
                end

                if (request_fire && request_match_found &&
                    (request_match_index == response_index)) begin
                    if (lookup_req_epoch == current_epoch_i) begin
                        resp_valid_reg <= 1'b1;
                        resp_pc_reg <= lookup_req_pc;
                        resp_line_reg <= mem_resp_line_addr_i;
                        resp_data_reg <= mem_resp_data_i;
                        resp_epoch_reg <= lookup_req_epoch;
                        resp_error_reg <= mem_resp_error_i || !response_matches;
                    end
                end else if (!mshr_prefetch[response_index] &&
                             (mshr_demand_epoch[response_index] == current_epoch_i)) begin
                    resp_valid_reg <= 1'b1;
                    resp_pc_reg <= mshr_pc[response_index];
                    resp_line_reg <= mshr_line[response_index];
                    resp_data_reg <= mem_resp_data_i;
                    resp_epoch_reg <= mshr_demand_epoch[response_index];
                    resp_error_reg <= mem_resp_error_i || !response_matches;
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
                prefetch_next_line <=
                    {control_target[31:4], 4'b0} + 32'd16;
                prefetch_epoch <= current_epoch_i;
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
(* keep_hierarchy = 1 *)
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
    output reg [31:0] pc_o,
    output reg [31:0] line_o,
    output reg [EPOCH_WIDTH-1:0] demand_epoch_o,
    output reg [EPOCH_WIDTH-1:0] txn_epoch_o
);
    always @(posedge clk_i) begin
        if (reset_i) begin
            valid_o <= 1'b0;
            sent_o <= 1'b0;
            prefetch_o <= 1'b0;
            control_prefetch_o <= 1'b0;
            pc_o <= 32'd0;
            line_o <= 32'd0;
            demand_epoch_o <= {EPOCH_WIDTH{1'b0}};
            txn_epoch_o <= {EPOCH_WIDTH{1'b0}};
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
                        pc_o <= if_req_pc_i;
                        demand_epoch_o <= if_req_epoch_i;
                    end
                end else if (free_index_i == ROW) begin
                    valid_o <= 1'b1;
                    sent_o <= 1'b0;
                    prefetch_o <= 1'b0;
                    control_prefetch_o <= 1'b0;
                    pc_o <= if_req_pc_i;
                    line_o <= request_line_i;
                    demand_epoch_o <= if_req_epoch_i;
                    txn_epoch_o <= if_req_epoch_i;
                end
            end
            if (prefetch_step_allocates_i && (free_index_i == ROW)) begin
                valid_o <= 1'b1;
                sent_o <= 1'b0;
                prefetch_o <= 1'b1;
                control_prefetch_o <= prefetch_control_stream_i;
                pc_o <= prefetch_next_line_i;
                line_o <= prefetch_next_line_i;
                demand_epoch_o <= prefetch_epoch_i;
                txn_epoch_o <= prefetch_epoch_i;
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
                pc_o <= control_target_i;
                line_o <= {control_target_i[31:4], 4'b0};
                demand_epoch_o <= current_epoch_i;
                txn_epoch_o <= current_epoch_i;
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
    reg [32+EPOCH_WIDTH-1:0] payload [0:1];
    wire read_local;
    rv32_frequency_control_tree #(.LEAVES(1)) read_tree (
        .signal_i(read_slot),.views_o(read_local));
    assign {pc_o,epoch_o}=read_local?payload[1]:payload[0];
    wire stale=count!=0 && epoch_o!=current_epoch_i;
    assign ready_o=!reset_i && count<2;
    assign valid_o=!reset_i && count!=0 && !stale;
    wire push=valid_i && ready_o;
    wire pop=!reset_i && (stale || (valid_o && ready_i));
    genvar queue_row;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        wire write_local;
        rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
            .signal_i(push && write_slot==queue_row),.views_o(write_local));
        always @(posedge clk_i) if(write_local) payload[queue_row]<={pc_i,epoch_i};
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
