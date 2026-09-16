`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Minimal one-outstanding-request adapters for the area-first core profile.
// The external interface is already split into instruction and data channels,
// so no cache bridge or arbitration is needed.  Architectural behaviour is
// unchanged; only locality/performance is traded for substantially less area.
module rv32_uncached_memory #(
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT
) (
    input  wire                     clk_i,
    input  wire                     reset_i,

    input  wire                     if_req_valid_i,
    output wire                     if_req_ready_o,
    input  wire [31:0]              if_req_pc_i,
    input  wire [EPOCH_WIDTH-1:0]   if_req_epoch_i,
    input  wire [EPOCH_WIDTH-1:0]   current_epoch_i,
    output wire                     if_resp_valid_o,
    input  wire                     if_resp_ready_i,
    output wire [31:0]              if_resp_pc_o,
    output wire [31:0]              if_resp_line_addr_o,
    output wire [127:0]             if_resp_line_data_o,
    output wire [EPOCH_WIDTH-1:0]   if_resp_epoch_o,
    output wire                     if_resp_error_o,

    input  wire                     d_req_valid_i,
    output wire                     d_req_ready_o,
    input  wire                     d_req_is_load_i,
    input  wire                     d_req_is_store_i,
    input  wire [31:0]              d_req_addr_i,
    input  wire [1:0]               d_req_size_i,
    input  wire                     d_req_unsigned_i,
    input  wire [15:0]              d_req_mask_i,
    input  wire [127:0]             d_req_wdata_i,
    input  wire [TAG_WIDTH-1:0]     d_req_lsq_tag_i,
    output wire                     d_resp_valid_o,
    input  wire                     d_resp_ready_i,
    output wire [TAG_WIDTH-1:0]     d_resp_lsq_tag_o,
    output wire [31:0]              d_resp_addr_o,
    output wire [127:0]             d_resp_line_data_o,
    output wire [31:0]              d_resp_word_data_o,
    output wire                     d_resp_line_valid_o,
    output wire                     d_resp_error_o,
    output wire                     d_store_ack_valid_o,
    input  wire                     d_store_ack_ready_i,
    output wire [TAG_WIDTH-1:0]     d_store_ack_lsq_tag_o,
    output wire                     d_store_ack_error_o,

    output wire                     mem_i_req_valid_o,
    input  wire                     mem_i_req_ready_i,
    output wire [31:0]              mem_i_req_line_addr_o,
    output wire [7:0]               mem_i_req_id_o,
    input  wire                     mem_i_resp_valid_i,
    output wire                     mem_i_resp_ready_o,
    input  wire [31:0]              mem_i_resp_line_addr_i,
    input  wire [127:0]             mem_i_resp_data_i,
    input  wire [7:0]               mem_i_resp_id_i,
    input  wire                     mem_i_resp_error_i,

    output wire                     mem_d_req_valid_o,
    input  wire                     mem_d_req_ready_i,
    output wire                     mem_d_req_write_o,
    output wire [31:0]              mem_d_req_line_addr_o,
    output wire [127:0]             mem_d_req_wdata_o,
    output wire [15:0]              mem_d_req_wmask_o,
    output wire [7:0]               mem_d_req_id_o,
    input  wire                     mem_d_resp_valid_i,
    output wire                     mem_d_resp_ready_o,
    input  wire [31:0]              mem_d_resp_line_addr_i,
    input  wire [127:0]             mem_d_resp_data_i,
    input  wire [7:0]               mem_d_resp_id_i,
    input  wire                     mem_d_resp_error_i
);
    reg i_pending;
    reg [31:0] i_pc;
    reg [EPOCH_WIDTH-1:0] i_epoch;

    reg d_pending;
    reg d_store;
    reg [31:0] d_addr;
    reg [1:0] d_size;
    reg d_unsigned;
    reg [TAG_WIDTH-1:0] d_lsq_tag;

    wire i_request_fire = mem_i_req_valid_o && mem_i_req_ready_i;
    wire i_response_fire = mem_i_resp_valid_i && mem_i_resp_ready_o;
    wire d_request_fire = mem_d_req_valid_o && mem_d_req_ready_i;
    wire d_response_fire = mem_d_resp_valid_i && mem_d_resp_ready_o;

    assign mem_i_req_valid_o = if_req_valid_i && !i_pending;
    assign if_req_ready_o = !i_pending && mem_i_req_ready_i;
    assign mem_i_req_line_addr_o = {if_req_pc_i[31:4], 4'b0};
    assign mem_i_req_id_o = {{(8-EPOCH_WIDTH){1'b0}}, if_req_epoch_i};
    wire i_response_live = (i_epoch == current_epoch_i);
    assign mem_i_resp_ready_o = i_pending &&
        (!i_response_live || if_resp_ready_i);
    assign if_resp_valid_o = i_pending && i_response_live && mem_i_resp_valid_i;
    assign if_resp_pc_o = i_pc;
    assign if_resp_line_addr_o = mem_i_resp_line_addr_i;
    assign if_resp_line_data_o = mem_i_resp_data_i;
    assign if_resp_epoch_o = i_epoch;
    assign if_resp_error_o = mem_i_resp_error_i;

    assign mem_d_req_valid_o = d_req_valid_i && !d_pending &&
        (d_req_is_load_i || d_req_is_store_i);
    assign d_req_ready_o = !d_pending && mem_d_req_ready_i;
    assign mem_d_req_write_o = d_req_is_store_i;
    assign mem_d_req_line_addr_o = {d_req_addr_i[31:4], 4'b0};
    assign mem_d_req_wdata_o = d_req_wdata_i;
    assign mem_d_req_wmask_o = d_req_is_store_i ? d_req_mask_i : 16'b0;
    assign mem_d_req_id_o = d_req_lsq_tag_i;
    assign mem_d_resp_ready_o = d_pending &&
        (d_store ? d_store_ack_ready_i : d_resp_ready_i);

    assign d_resp_valid_o = d_pending && !d_store && mem_d_resp_valid_i;
    assign d_resp_lsq_tag_o = d_lsq_tag;
    assign d_resp_addr_o = d_addr;
    assign d_resp_line_data_o = mem_d_resp_data_i;
    assign d_resp_word_data_o = extract_value(
        mem_d_resp_data_i, d_addr, d_size, d_unsigned);
    assign d_resp_line_valid_o = !mem_d_resp_error_i;
    assign d_resp_error_o = mem_d_resp_error_i;
    assign d_store_ack_valid_o = d_pending && d_store && mem_d_resp_valid_i;
    assign d_store_ack_lsq_tag_o = d_lsq_tag;
    assign d_store_ack_error_o = mem_d_resp_error_i;

    // Response IDs are informational here: each split channel permits exactly
    // one outstanding request, so the stored epoch/tag is authoritative.
    wire _unused_ids = ^{mem_i_resp_id_i, mem_d_resp_id_i,
                         mem_d_resp_line_addr_i};

    function [31:0] extract_value;
        input [127:0] line_data;
        input [31:0] address;
        input [1:0] size;
        input unsigned_load;
        reg [31:0] shifted;
        begin
            shifted = line_data >> (address[3:0] * 8);
            case (size)
                `RV32IM_MEM_BYTE: extract_value = unsigned_load ?
                    {24'b0, shifted[7:0]} : {{24{shifted[7]}}, shifted[7:0]};
                `RV32IM_MEM_HALF: extract_value = unsigned_load ?
                    {16'b0, shifted[15:0]} : {{16{shifted[15]}}, shifted[15:0]};
                default: extract_value = shifted;
            endcase
        end
    endfunction

    always @(posedge clk_i) begin
        if (reset_i) begin
            i_pending <= 1'b0;
            d_pending <= 1'b0;
        end else begin
            if (i_request_fire) begin
                i_pending <= 1'b1;
                i_pc <= if_req_pc_i;
                i_epoch <= if_req_epoch_i;
            end else if (i_response_fire) begin
                i_pending <= 1'b0;
            end

            if (d_request_fire) begin
                d_pending <= 1'b1;
                d_store <= d_req_is_store_i;
                d_addr <= d_req_addr_i;
                d_size <= d_req_size_i;
                d_unsigned <= d_req_unsigned_i;
                d_lsq_tag <= d_req_lsq_tag_i;
            end else if (d_response_fire) begin
                d_pending <= 1'b0;
            end
        end
    end
endmodule
