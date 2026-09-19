`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Small non-blocking instruction cache used by the performance profiles.
// The cache remains direct mapped, but independent MSHRs allow the demand
// line and several sequential prefetches to overlap the backing-memory delay.
module rv32_icache_nonblocking #(
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    parameter integer MSHR_ENTRIES = 4,
    parameter integer NEXT_LINE_PREFETCH = 1,
    parameter integer PREFETCH_DISTANCE = 3
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
    reg valid_mem [0:63];
    reg [21:0] tag_mem [0:63];
    reg [127:0] data_mem [0:63];

    reg mshr_valid [0:MSHR_ENTRIES-1];
    reg mshr_sent [0:MSHR_ENTRIES-1];
    reg mshr_prefetch [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_pc [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_line [0:MSHR_ENTRIES-1];
    reg [EPOCH_WIDTH-1:0] mshr_demand_epoch [0:MSHR_ENTRIES-1];
    reg [EPOCH_WIDTH-1:0] mshr_txn_epoch [0:MSHR_ENTRIES-1];

    reg resp_valid_reg;
    reg [31:0] resp_pc_reg;
    reg [31:0] resp_line_reg;
    reg [127:0] resp_data_reg;
    reg [EPOCH_WIDTH-1:0] resp_epoch_reg;
    reg resp_error_reg;

    reg prefetch_active;
    reg [31:0] prefetch_next_line;
    reg [EPOCH_WIDTH-1:0] prefetch_epoch;
    integer prefetch_remaining;

    wire [31:0] request_line = {if_req_pc_i[31:4], 4'b0000};
    wire [5:0] request_index = if_req_pc_i[9:4];
    wire [21:0] request_tag = if_req_pc_i[31:10];
    wire request_hit = valid_mem[request_index] &&
                       (tag_mem[request_index] == request_tag);
    wire response_live = resp_valid_reg && (resp_epoch_reg == current_epoch_i);
    wire response_slot_free = !resp_valid_reg || !response_live || if_resp_ready_i;

    integer k;
    integer request_match_index;
    integer free_index;
    integer send_index;
    integer response_index;
    integer prefetch_match_index;
    reg request_match_found;
    reg free_found;
    reg send_found;
    reg response_target_found;
    reg prefetch_match_found;

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
                (mshr_line[k] == request_line)) begin
                request_match_found = 1'b1;
                request_match_index = k;
            end
            if (!free_found && !mshr_valid[k]) begin
                free_found = 1'b1;
                free_index = k;
            end
            if (!send_found && mshr_valid[k] && !mshr_sent[k]) begin
                send_found = 1'b1;
                send_index = k;
            end
            if (!prefetch_match_found && mshr_valid[k] &&
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
    wire request_fire = if_req_valid_i && if_req_ready_o;
    wire request_allocates = request_fire && !request_hit && !request_match_found;
    wire response_matches = response_target_found &&
                            (mshr_line[response_index] == mem_resp_line_addr_i);
    wire response_needs_slot = response_target_found &&
                               (!mshr_prefetch[response_index] ||
                                (request_fire && request_match_found &&
                                 (request_match_index == response_index))) &&
                               ((mshr_demand_epoch[response_index] == current_epoch_i) ||
                                (request_fire && (if_req_epoch_i == current_epoch_i)));
    wire prefetch_line_resident = valid_mem[prefetch_next_line[9:4]] &&
                                  (tag_mem[prefetch_next_line[9:4]] ==
                                   prefetch_next_line[31:10]);

    assign if_req_ready_o = !reset_i && response_slot_free &&
                            !request_would_conflict &&
                            (request_hit || request_match_found || free_found);
    assign if_resp_valid_o = response_live;
    assign if_resp_pc_o = resp_pc_reg;
    assign if_resp_line_addr_o = resp_line_reg;
    assign if_resp_line_data_o = resp_data_reg;
    assign if_resp_epoch_o = resp_epoch_reg;
    assign if_resp_error_o = resp_error_reg;

    assign mem_req_valid_o = send_found;
    assign mem_req_line_addr_o = send_found ? mshr_line[send_index] : 32'd0;
    assign mem_req_id_o = send_found ?
        ((send_index << EPOCH_WIDTH) | mshr_txn_epoch[send_index]) : 8'd0;
    assign mem_resp_ready_o = response_target_found &&
                              (!response_needs_slot || response_slot_free);

    integer reset_index;
    integer prefetch_count;
    always @(posedge clk_i) begin
        if (reset_i) begin
            resp_valid_reg <= 1'b0;
            resp_pc_reg <= 32'd0;
            resp_line_reg <= 32'd0;
            resp_data_reg <= 128'd0;
            resp_epoch_reg <= {EPOCH_WIDTH{1'b0}};
            resp_error_reg <= 1'b0;
            prefetch_active <= 1'b0;
            prefetch_next_line <= 32'd0;
            prefetch_epoch <= {EPOCH_WIDTH{1'b0}};
            prefetch_remaining <= 0;
            event_request_o <= 1'b0;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= 1'b0;
            for (reset_index = 0; reset_index < 64; reset_index = reset_index + 1) begin
                valid_mem[reset_index] <= 1'b0;
                tag_mem[reset_index] <= 22'd0;
                data_mem[reset_index] <= 128'd0;
            end
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1) begin
                mshr_valid[reset_index] <= 1'b0;
                mshr_sent[reset_index] <= 1'b0;
                mshr_prefetch[reset_index] <= 1'b0;
                mshr_pc[reset_index] <= 32'd0;
                mshr_line[reset_index] <= 32'd0;
                mshr_demand_epoch[reset_index] <= {EPOCH_WIDTH{1'b0}};
                mshr_txn_epoch[reset_index] <= {EPOCH_WIDTH{1'b0}};
            end
        end else begin
            event_request_o <= request_fire;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= if_req_valid_i && !if_req_ready_o;

            if (response_slot_free)
                resp_valid_reg <= 1'b0;

            if (request_fire) begin
                if (request_hit) begin
                    event_hit_o <= 1'b1;
                    if (if_req_epoch_i == current_epoch_i) begin
                        resp_valid_reg <= 1'b1;
                        resp_pc_reg <= if_req_pc_i;
                        resp_line_reg <= request_line;
                        resp_data_reg <= data_mem[request_index];
                        resp_epoch_reg <= if_req_epoch_i;
                        resp_error_reg <= 1'b0;
                    end
                end else begin
                    event_miss_o <= 1'b1;
                    if (request_match_found) begin
                        mshr_prefetch[request_match_index] <= 1'b0;
                        mshr_pc[request_match_index] <= if_req_pc_i;
                        mshr_demand_epoch[request_match_index] <= if_req_epoch_i;
                    end else begin
                        mshr_valid[free_index] <= 1'b1;
                        mshr_sent[free_index] <= 1'b0;
                        mshr_prefetch[free_index] <= 1'b0;
                        mshr_pc[free_index] <= if_req_pc_i;
                        mshr_line[free_index] <= request_line;
                        mshr_demand_epoch[free_index] <= if_req_epoch_i;
                        mshr_txn_epoch[free_index] <= if_req_epoch_i;
                    end
                    if ((NEXT_LINE_PREFETCH != 0) && (PREFETCH_DISTANCE > 0) &&
                        (MSHR_ENTRIES > 1)) begin
                        prefetch_active <= 1'b1;
                        prefetch_next_line <= request_line + 32'd16;
                        prefetch_epoch <= if_req_epoch_i;
                        prefetch_count = PREFETCH_DISTANCE;
                        if (prefetch_count > MSHR_ENTRIES-1)
                            prefetch_count = MSHR_ENTRIES-1;
                        prefetch_remaining <= prefetch_count;
                    end
                end
            end

            // Allocate at most one background stream line per cycle so the
            // request port can issue the MSHRs on consecutive cycles.
            if (prefetch_active && (prefetch_remaining > 0) &&
                !request_allocates) begin
                if (prefetch_line_resident || prefetch_match_found) begin
                    prefetch_next_line <= prefetch_next_line + 32'd16;
                    prefetch_remaining <= prefetch_remaining - 1;
                    if (prefetch_remaining == 1)
                        prefetch_active <= 1'b0;
                end else if (free_found) begin
                    mshr_valid[free_index] <= 1'b1;
                    mshr_sent[free_index] <= 1'b0;
                    mshr_prefetch[free_index] <= 1'b1;
                    mshr_pc[free_index] <= prefetch_next_line;
                    mshr_line[free_index] <= prefetch_next_line;
                    mshr_demand_epoch[free_index] <= prefetch_epoch;
                    mshr_txn_epoch[free_index] <= prefetch_epoch;
                    prefetch_next_line <= prefetch_next_line + 32'd16;
                    prefetch_remaining <= prefetch_remaining - 1;
                    if (prefetch_remaining == 1)
                        prefetch_active <= 1'b0;
                end
            end

            if (mem_req_valid_o && mem_req_ready_i)
                mshr_sent[send_index] <= 1'b1;

            if (mem_resp_valid_i && mem_resp_ready_o) begin
                mshr_valid[response_index] <= 1'b0;
                mshr_sent[response_index] <= 1'b0;
                event_refill_o <= !mem_resp_error_i && response_matches;
                if (!mem_resp_error_i && response_matches) begin
                    valid_mem[mem_resp_line_addr_i[9:4]] <= 1'b1;
                    tag_mem[mem_resp_line_addr_i[9:4]] <= mem_resp_line_addr_i[31:10];
                    data_mem[mem_resp_line_addr_i[9:4]] <= mem_resp_data_i;
                end

                if (request_fire && request_match_found &&
                    (request_match_index == response_index)) begin
                    if (if_req_epoch_i == current_epoch_i) begin
                        resp_valid_reg <= 1'b1;
                        resp_pc_reg <= if_req_pc_i;
                        resp_line_reg <= mem_resp_line_addr_i;
                        resp_data_reg <= mem_resp_data_i;
                        resp_epoch_reg <= if_req_epoch_i;
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
        end
    end

    initial begin
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
