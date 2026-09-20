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
    parameter integer PREFETCH = 1
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
    reg valid_mem [0:255];
    reg dirty_mem [0:255];
    reg [19:0] tag_mem [0:255];
    reg [127:0] data_mem [0:255];

    reg mshr_valid [0:MSHR_ENTRIES-1];
    reg mshr_sent [0:MSHR_ENTRIES-1];
    reg mshr_store [0:MSHR_ENTRIES-1];
    reg mshr_prefetch [0:MSHR_ENTRIES-1];
    reg mshr_writeback [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_addr [0:MSHR_ENTRIES-1];
    reg [1:0] mshr_size [0:MSHR_ENTRIES-1];
    reg mshr_unsigned [0:MSHR_ENTRIES-1];
    reg [15:0] mshr_mask [0:MSHR_ENTRIES-1];
    reg [127:0] mshr_wdata [0:MSHR_ENTRIES-1];
    reg [TAG_WIDTH-1:0] mshr_lsq [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_victim_addr [0:MSHR_ENTRIES-1];
    reg [127:0] mshr_victim_data [0:MSHR_ENTRIES-1];

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
    reg ack_valid_reg;
    reg [TAG_WIDTH-1:0] ack_lsq_reg;
    reg ack_error_reg;

    wire [7:0] request_index = dcache_req_addr_i[11:4];
    wire [19:0] request_tag = dcache_req_addr_i[31:12];
    wire request_hit = valid_mem[request_index] &&
                       (tag_mem[request_index] == request_tag);
    wire resp_slot_free = !resp_valid_reg || dcache_resp_ready_i;
    wire ack_slot_free = !ack_valid_reg || dcache_store_ack_ready_i;

    integer k;
    integer free_index;
    integer second_free_index;
    integer send_index;
    integer response_index;
    integer matching_index;
    integer waiter_free_index;
    integer waiter_load_ready_index;
    integer waiter_store_ready_index;
    reg free_found;
    reg second_free_found;
    reg send_found;
    reg any_mshr;
    reg store_mshr_present;
    reg response_found;
    reg matching_found;
    reg matching_prefetch;
    reg prefetch_line_present;
    reg request_index_conflict;
    reg waiter_free_found;
    reg waiter_load_ready_found;
    reg waiter_store_ready_found;
    wire [31:0] request_line_addr = {dcache_req_addr_i[31:4], 4'b0};
    wire [31:0] prefetch_line_addr = request_line_addr + 32'd16;
    wire [7:0] prefetch_index = prefetch_line_addr[11:4];
    wire [19:0] prefetch_tag = prefetch_line_addr[31:12];
    wire prefetch_cache_hit = valid_mem[prefetch_index] &&
                              (tag_mem[prefetch_index] == prefetch_tag);
    always @* begin
        free_found = 1'b0;
        free_index = 0;
        second_free_found = 1'b0;
        second_free_index = 0;
        send_found = 1'b0;
        send_index = 0;
        any_mshr = 1'b0;
        store_mshr_present = 1'b0;
        matching_found = 1'b0;
        matching_index = 0;
        matching_prefetch = 1'b0;
        prefetch_line_present = 1'b0;
        request_index_conflict = 1'b0;
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
            if (!send_found && mshr_valid[k] && !mshr_sent[k]) begin
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
                (mshr_addr[k][11:4] == request_index))
                request_index_conflict = 1'b1;
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

    wire request_is_store = dcache_req_is_store_i && !dcache_req_is_load_i;
    wire request_is_load = dcache_req_is_load_i && !dcache_req_is_store_i;
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
    wire response_emits_store = mem_resp_valid_i && response_found &&
                                ((!mshr_writeback[response_index] &&
                                  mshr_store[response_index]) ||
                                 (response_writeback_failed &&
                                  mshr_store[response_index]));
    wire load_can_accept = (request_hit ?
                            (resp_slot_free && !waiter_load_ready_found &&
                             !response_emits_load) :
                            (matching_found ?
                             (!mshr_store[matching_index] &&
                              (matching_prefetch || waiter_free_found) &&
                              !(mem_resp_valid_i && response_found &&
                                (response_index == matching_index))) :
                             free_found));
    wire store_can_accept = request_hit ?
                            (ack_slot_free && !request_index_conflict &&
                             !waiter_store_ready_found &&
                             !response_emits_store) :
                            (matching_found ?
                             ((matching_prefetch ||
                               (mshr_store[matching_index] && waiter_free_found)) &&
                              !(mem_resp_valid_i && response_found &&
                                (response_index == matching_index))) :
                             (free_found && !request_index_conflict));
    wire request_fire = dcache_req_valid_i && dcache_req_ready_o;
    wire response_needs_output = response_found &&
                                 (mshr_store[response_index] ? !ack_slot_free :
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

    assign dcache_req_ready_o = !reset_i && !flush_i &&
                                ((request_is_load && load_can_accept) ||
                                 (request_is_store && store_can_accept));
    assign dcache_resp_valid_o = resp_valid_reg;
    assign dcache_resp_lsq_tag_o = resp_lsq_reg;
    assign dcache_resp_addr_o = resp_addr_reg;
    assign dcache_resp_line_data_o = resp_line_reg;
    assign dcache_resp_word_data_o = resp_word_reg;
    assign dcache_resp_line_valid_o = resp_line_valid_reg;
    assign dcache_resp_error_o = resp_error_reg;
    assign dcache_store_ack_valid_o = ack_valid_reg;
    assign dcache_store_ack_lsq_tag_o = ack_lsq_reg;
    assign dcache_store_ack_error_o = ack_error_reg;

    assign mem_req_valid_o = send_found;
    assign mem_req_write_o = send_found && mshr_writeback[send_index];
    assign mem_req_line_addr_o = send_found ?
                                  (mshr_writeback[send_index] ?
                                   mshr_victim_addr[send_index] :
                                   {mshr_addr[send_index][31:4], 4'b0}) : 32'd0;
    assign mem_req_wdata_o = send_found && mshr_writeback[send_index] ?
                             mshr_victim_data[send_index] : 128'd0;
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
    always @(posedge clk_i) begin
        if (reset_i) begin
            resp_valid_reg <= 1'b0;
            ack_valid_reg <= 1'b0;
            event_request_o <= 1'b0;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_writeback_o <= 1'b0;
            event_stall_o <= 1'b0;
            for (reset_index = 0; reset_index < 256; reset_index = reset_index + 1) begin
                valid_mem[reset_index] <= 1'b0;
                dirty_mem[reset_index] <= 1'b0;
                tag_mem[reset_index] <= 20'd0;
                data_mem[reset_index] <= 128'd0;
            end
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1) begin
                mshr_valid[reset_index] <= 1'b0;
                mshr_sent[reset_index] <= 1'b0;
                mshr_store[reset_index] <= 1'b0;
                mshr_prefetch[reset_index] <= 1'b0;
                mshr_writeback[reset_index] <= 1'b0;
                mshr_addr[reset_index] <= 32'd0;
                mshr_size[reset_index] <= 2'd0;
                mshr_unsigned[reset_index] <= 1'b0;
                mshr_mask[reset_index] <= 16'd0;
                mshr_wdata[reset_index] <= 128'd0;
                mshr_lsq[reset_index] <= {TAG_WIDTH{1'b0}};
                mshr_victim_addr[reset_index] <= 32'd0;
                mshr_victim_data[reset_index] <= 128'd0;
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
            event_request_o <= request_fire;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_writeback_o <= 1'b0;
            event_stall_o <= dcache_req_valid_i && !dcache_req_ready_o;
            if (resp_valid_reg && dcache_resp_ready_i)
                resp_valid_reg <= 1'b0;
            if (ack_valid_reg && dcache_store_ack_ready_i)
                ack_valid_reg <= 1'b0;

            if (request_fire) begin
                if (request_is_load && request_hit) begin
                    event_hit_o <= 1'b1;
                    resp_valid_reg <= 1'b1;
                    resp_lsq_reg <= dcache_req_lsq_tag_i;
                    resp_addr_reg <= dcache_req_addr_i;
                    resp_line_reg <= data_mem[request_index];
                    resp_word_reg <= extract_value(data_mem[request_index],
                                                   dcache_req_addr_i,
                                                   dcache_req_size_i,
                                                   dcache_req_unsigned_i);
                    resp_line_valid_reg <= 1'b1;
                    resp_error_reg <= 1'b0;
                end else if (request_is_store && request_hit) begin
                    event_hit_o <= 1'b1;
                    updated_line = merge_store(data_mem[request_index],
                                               dcache_req_wdata_i,
                                               dcache_req_mask_i);
                    data_mem[request_index] <= updated_line;
                    dirty_mem[request_index] <= 1'b1;
                    ack_valid_reg <= 1'b1;
                    ack_lsq_reg <= dcache_req_lsq_tag_i;
                    ack_error_reg <= 1'b0;
                end else if (request_is_load && matching_found && matching_prefetch) begin
                    // Turn the speculative line into the demand transaction;
                    // its memory request and ID remain unchanged.
                    event_miss_o <= 1'b1;
                    mshr_prefetch[matching_index] <= 1'b0;
                    mshr_addr[matching_index] <= dcache_req_addr_i;
                    mshr_size[matching_index] <= dcache_req_size_i;
                    mshr_unsigned[matching_index] <= dcache_req_unsigned_i;
                    mshr_lsq[matching_index] <= dcache_req_lsq_tag_i;
                end else if (request_is_load && matching_found) begin
                    // Merge a secondary demand behind the line fill instead
                    // of stalling the LSQ's oldest-request selector.
                    event_miss_o <= 1'b1;
                    waiter_valid[waiter_free_index] <= 1'b1;
                    waiter_ready[waiter_free_index] <= 1'b0;
                    waiter_store[waiter_free_index] <= 1'b0;
                    waiter_mshr[waiter_free_index] <= matching_index[2:0];
                    waiter_addr[waiter_free_index] <= dcache_req_addr_i;
                    waiter_size[waiter_free_index] <= dcache_req_size_i;
                    waiter_unsigned[waiter_free_index] <= dcache_req_unsigned_i;
                    waiter_lsq[waiter_free_index] <= dcache_req_lsq_tag_i;
                    waiter_error[waiter_free_index] <= 1'b0;
                end else if (request_is_store && matching_found &&
                             matching_prefetch) begin
                    // A committed store owns the prefetched line from now on;
                    // retain the transaction ID and turn its refill into the
                    // store miss completion.
                    event_miss_o <= 1'b1;
                    mshr_store[matching_index] <= 1'b1;
                    mshr_prefetch[matching_index] <= 1'b0;
                    mshr_addr[matching_index] <= dcache_req_addr_i;
                    mshr_size[matching_index] <= dcache_req_size_i;
                    mshr_unsigned[matching_index] <= 1'b0;
                    mshr_mask[matching_index] <= dcache_req_mask_i;
                    mshr_wdata[matching_index] <= dcache_req_wdata_i;
                    mshr_lsq[matching_index] <= dcache_req_lsq_tag_i;
                end else if (request_is_store && matching_found &&
                             mshr_store[matching_index]) begin
                    // Consecutive committed stores to one missing line share
                    // the refill.  Later bytes override earlier bytes while
                    // every LSQ entry retains its own completion ack.
                    event_miss_o <= 1'b1;
                    mshr_wdata[matching_index] <=
                        merge_store(mshr_wdata[matching_index],
                                    dcache_req_wdata_i,
                                    dcache_req_mask_i);
                    mshr_mask[matching_index] <= mshr_mask[matching_index] |
                                                 dcache_req_mask_i;
                    waiter_valid[waiter_free_index] <= 1'b1;
                    waiter_ready[waiter_free_index] <= 1'b0;
                    waiter_store[waiter_free_index] <= 1'b1;
                    waiter_mshr[waiter_free_index] <= matching_index[2:0];
                    waiter_addr[waiter_free_index] <= dcache_req_addr_i;
                    waiter_size[waiter_free_index] <= dcache_req_size_i;
                    waiter_unsigned[waiter_free_index] <= 1'b0;
                    waiter_lsq[waiter_free_index] <= dcache_req_lsq_tag_i;
                    waiter_error[waiter_free_index] <= 1'b0;
                end else begin
                    event_miss_o <= 1'b1;
                    mshr_valid[free_index] <= 1'b1;
                    mshr_sent[free_index] <= 1'b0;
                    mshr_store[free_index] <= request_is_store;
                    mshr_prefetch[free_index] <= 1'b0;
                    mshr_writeback[free_index] <= valid_mem[request_index] &&
                                                  dirty_mem[request_index];
                    mshr_addr[free_index] <= dcache_req_addr_i;
                    mshr_size[free_index] <= dcache_req_size_i;
                    mshr_unsigned[free_index] <= dcache_req_unsigned_i;
                    mshr_mask[free_index] <= request_is_store ? dcache_req_mask_i : 16'd0;
                    mshr_wdata[free_index] <= dcache_req_wdata_i;
                    mshr_lsq[free_index] <= dcache_req_lsq_tag_i;
                    mshr_victim_addr[free_index] <=
                        {tag_mem[request_index], request_index, 4'b0};
                    mshr_victim_data[free_index] <= data_mem[request_index];
                    valid_mem[request_index] <= 1'b0;
                    dirty_mem[request_index] <= 1'b0;

                    // Store streams already expose every committed address
                    // to the cache.  Prefetching after a store miss wastes a
                    // scarce external read slot (notably during BSS clear)
                    // and can delay the first real load stream.  Independent
                    // store lines may occupy separate MSHRs instead.
                    if ((PREFETCH != 0) && request_is_load &&
                        second_free_found && !prefetch_cache_hit &&
                        !prefetch_line_present &&
                        !(valid_mem[prefetch_index] && dirty_mem[prefetch_index])) begin
                        mshr_valid[second_free_index] <= 1'b1;
                        mshr_sent[second_free_index] <= 1'b0;
                        mshr_store[second_free_index] <= 1'b0;
                        mshr_prefetch[second_free_index] <= 1'b1;
                        mshr_writeback[second_free_index] <= 1'b0;
                        mshr_addr[second_free_index] <= prefetch_line_addr;
                        mshr_size[second_free_index] <= `RV32IM_MEM_WORD;
                        mshr_unsigned[second_free_index] <= 1'b1;
                        mshr_mask[second_free_index] <= 16'd0;
                        mshr_wdata[second_free_index] <= 128'd0;
                        mshr_lsq[second_free_index] <= {TAG_WIDTH{1'b0}};
                        mshr_victim_addr[second_free_index] <= 32'd0;
                        mshr_victim_data[second_free_index] <= 128'd0;
                        valid_mem[prefetch_index] <= 1'b0;
                        dirty_mem[prefetch_index] <= 1'b0;
                    end
                end
            end

            if (mem_req_valid_o && mem_req_ready_i)
                mshr_sent[send_index] <= 1'b1;

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
                    for (waiter_index = 0; waiter_index < WAITER_ENTRIES;
                         waiter_index = waiter_index + 1) begin
                        if (waiter_valid[waiter_index] &&
                            waiter_store[waiter_index] &&
                            (waiter_mshr[waiter_index] == response_index[2:0])) begin
                            waiter_ready[waiter_index] <= 1'b1;
                            waiter_error[waiter_index] <= mem_resp_error_i ||
                                                          !response_matches;
                        end
                    end
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_addr[response_index][11:4];
                        updated_line = merge_store(mem_resp_data_i,
                                                   mshr_wdata[response_index],
                                                   mshr_mask[response_index]);
                        valid_mem[line_index] <= 1'b1;
                        dirty_mem[line_index] <= 1'b1;
                        tag_mem[line_index] <= mshr_addr[response_index][31:12];
                        data_mem[line_index] <= updated_line;
                        event_refill_o <= 1'b1;
                    end
                    ack_valid_reg <= 1'b1;
                    ack_lsq_reg <= mshr_lsq[response_index];
                    ack_error_reg <= mem_resp_error_i || !response_matches;
                end else if (mshr_prefetch[response_index]) begin
                    mshr_valid[response_index] <= 1'b0;
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_addr[response_index][11:4];
                        valid_mem[line_index] <= 1'b1;
                        tag_mem[line_index] <= mshr_addr[response_index][31:12];
                        data_mem[line_index] <= mem_resp_data_i;
                        dirty_mem[line_index] <= 1'b0;
                        event_refill_o <= 1'b1;
                    end
                end else begin
                    mshr_valid[response_index] <= 1'b0;
                    for (waiter_index = 0; waiter_index < WAITER_ENTRIES;
                         waiter_index = waiter_index + 1) begin
                        if (waiter_valid[waiter_index] &&
                            !waiter_store[waiter_index] &&
                            (waiter_mshr[waiter_index] == response_index[2:0])) begin
                            waiter_ready[waiter_index] <= 1'b1;
                            waiter_line[waiter_index] <= mem_resp_data_i;
                            waiter_error[waiter_index] <= mem_resp_error_i ||
                                                          !response_matches;
                        end
                    end
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_addr[response_index][11:4];
                        valid_mem[line_index] <= 1'b1;
                        tag_mem[line_index] <= mshr_addr[response_index][31:12];
                        data_mem[line_index] <= mem_resp_data_i;
                        dirty_mem[line_index] <= 1'b0;
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
            (PREFETCH != 0 && PREFETCH != 1)) begin
            $display("ERROR: invalid rv32_dcache_nonblocking parameter");
            $finish;
        end
    end
endmodule
