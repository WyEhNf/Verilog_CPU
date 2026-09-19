`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Non-blocking, write-through data cache for the performance profiles.
// Loads use independent MSHRs and may hit under outstanding misses. Committed
// stores remain exclusive and receive an acknowledgement only after backing
// memory completes the masked write.
module rv32_dcache_nonblocking #(
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer MSHR_ENTRIES = 4
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
    reg [19:0] tag_mem [0:255];
    reg [127:0] data_mem [0:255];

    reg mshr_valid [0:MSHR_ENTRIES-1];
    reg mshr_sent [0:MSHR_ENTRIES-1];
    reg mshr_store [0:MSHR_ENTRIES-1];
    reg mshr_cache_hit [0:MSHR_ENTRIES-1];
    reg [31:0] mshr_addr [0:MSHR_ENTRIES-1];
    reg [1:0] mshr_size [0:MSHR_ENTRIES-1];
    reg mshr_unsigned [0:MSHR_ENTRIES-1];
    reg [15:0] mshr_mask [0:MSHR_ENTRIES-1];
    reg [127:0] mshr_wdata [0:MSHR_ENTRIES-1];
    reg [TAG_WIDTH-1:0] mshr_lsq [0:MSHR_ENTRIES-1];

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
    integer send_index;
    integer response_index;
    reg free_found;
    reg send_found;
    reg any_mshr;
    reg response_found;
    always @* begin
        free_found = 1'b0;
        free_index = 0;
        send_found = 1'b0;
        send_index = 0;
        any_mshr = 1'b0;
        for (k = 0; k < MSHR_ENTRIES; k = k + 1) begin
            if (mshr_valid[k])
                any_mshr = 1'b1;
            if (!free_found && !mshr_valid[k]) begin
                free_found = 1'b1;
                free_index = k;
            end
            if (!send_found && mshr_valid[k] && !mshr_sent[k]) begin
                send_found = 1'b1;
                send_index = k;
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
    wire load_can_accept = request_hit ? resp_slot_free : free_found;
    wire store_can_accept = !any_mshr && free_found && resp_slot_free && ack_slot_free;
    wire request_fire = dcache_req_valid_i && dcache_req_ready_o;
    wire response_needs_output = response_found &&
                                 (mshr_store[response_index] ? !ack_slot_free : !resp_slot_free);
    wire response_matches = response_found &&
                            (mem_resp_line_addr_i == {mshr_addr[response_index][31:4], 4'b0});

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
    assign mem_req_write_o = send_found && mshr_store[send_index];
    assign mem_req_line_addr_o = send_found ?
                                  {mshr_addr[send_index][31:4], 4'b0} : 32'd0;
    assign mem_req_wdata_o = send_found ? mshr_wdata[send_index] : 128'd0;
    assign mem_req_wmask_o = send_found ? mshr_mask[send_index] : 16'd0;
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
                tag_mem[reset_index] <= 20'd0;
                data_mem[reset_index] <= 128'd0;
            end
            for (reset_index = 0; reset_index < MSHR_ENTRIES; reset_index = reset_index + 1) begin
                mshr_valid[reset_index] <= 1'b0;
                mshr_sent[reset_index] <= 1'b0;
                mshr_store[reset_index] <= 1'b0;
                mshr_cache_hit[reset_index] <= 1'b0;
                mshr_addr[reset_index] <= 32'd0;
                mshr_size[reset_index] <= 2'd0;
                mshr_unsigned[reset_index] <= 1'b0;
                mshr_mask[reset_index] <= 16'd0;
                mshr_wdata[reset_index] <= 128'd0;
                mshr_lsq[reset_index] <= {TAG_WIDTH{1'b0}};
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
                end else begin
                    if (request_is_load)
                        event_miss_o <= 1'b1;
                    else if (request_hit)
                        event_hit_o <= 1'b1;
                    else
                        event_miss_o <= 1'b1;
                    mshr_valid[free_index] <= 1'b1;
                    mshr_sent[free_index] <= 1'b0;
                    mshr_store[free_index] <= request_is_store;
                    mshr_cache_hit[free_index] <= request_hit;
                    mshr_addr[free_index] <= dcache_req_addr_i;
                    mshr_size[free_index] <= dcache_req_size_i;
                    mshr_unsigned[free_index] <= dcache_req_unsigned_i;
                    mshr_mask[free_index] <= request_is_store ? dcache_req_mask_i : 16'd0;
                    mshr_wdata[free_index] <= dcache_req_wdata_i;
                    mshr_lsq[free_index] <= dcache_req_lsq_tag_i;
                end
            end

            if (mem_req_valid_o && mem_req_ready_i)
                mshr_sent[send_index] <= 1'b1;

            if (mem_resp_valid_i && mem_resp_ready_o) begin
                mshr_valid[response_index] <= 1'b0;
                mshr_sent[response_index] <= 1'b0;
                if (mshr_store[response_index]) begin
                    if (!mem_resp_error_i && response_matches &&
                        mshr_cache_hit[response_index]) begin
                        line_index = mshr_addr[response_index][11:4];
                        updated_line = merge_store(data_mem[line_index],
                                                   mshr_wdata[response_index],
                                                   mshr_mask[response_index]);
                        data_mem[line_index] <= updated_line;
                    end
                    ack_valid_reg <= 1'b1;
                    ack_lsq_reg <= mshr_lsq[response_index];
                    ack_error_reg <= mem_resp_error_i || !response_matches;
                end else begin
                    if (!mem_resp_error_i && response_matches) begin
                        line_index = mshr_addr[response_index][11:4];
                        valid_mem[line_index] <= 1'b1;
                        tag_mem[line_index] <= mshr_addr[response_index][31:12];
                        data_mem[line_index] <= mem_resp_data_i;
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
        if (TAG_WIDTH < 8 || MSHR_ENTRIES < 2 || MSHR_ENTRIES > 8) begin
            $display("ERROR: invalid rv32_dcache_nonblocking parameter");
            $finish;
        end
    end
endmodule
