`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Owns one real SRAM word lane and decodes competing commands locally.
// Store-hit addresses never traverse the unrelated victim-way selection.
(* keep_hierarchy = 1 *)
module rv32_dcache_command_word #(
    parameter integer SETS=512, WAYS=2, WAY=0,
    parameter integer IW=$clog2(SETS), EW=$clog2(SETS*WAYS)
) (
    input wire clk_i, reset_i,
    input wire refill_i, local_i, store_i, input_read_i, deferred_read_i,
    input wire [EW-1:0] refill_entry_i, local_entry_i, hit_entry_i,
    input wire [IW-1:0] input_index_i, deferred_index_i,
    input wire [31:0] response_data_i, response_store_data_i,
    input wire response_store_i,
    input wire [3:0] response_mask_i,
    input wire [31:0] local_data_i, store_data_i,
    input wire [3:0] store_mask_i,
    output wire [31:0] data_o
);
    wire refill_way = refill_i && ((refill_entry_i % WAYS)==WAY);
    wire local_way = !refill_i && local_i && ((local_entry_i % WAYS)==WAY);
    wire store_way = !refill_i && !local_i && store_i && ((hit_entry_i % WAYS)==WAY);
    wire writing = refill_way || local_way || store_way;
    wire [IW-1:0] address = refill_way ? refill_entry_i/WAYS :
        local_way ? local_entry_i/WAYS : store_way ? hit_entry_i/WAYS :
        deferred_read_i ? deferred_index_i : input_index_i;
    wire [3:0] mask = (refill_way || local_way) ? 4'hf : store_mask_i;
    wire [31:0] refill_data;
    genvar byte_id;
    generate for(byte_id=0;byte_id<4;byte_id=byte_id+1) begin:g_merge
        assign refill_data[byte_id*8 +: 8] = response_store_i && response_mask_i[byte_id] ?
            response_store_data_i[byte_id*8 +: 8] : response_data_i[byte_id*8 +: 8];
    end endgenerate
    wire [31:0] write_data = refill_way ? refill_data : local_way ? local_data_i : store_data_i;
    sram_fakeram #(.DEPTH(SETS),.WIDTH(32),.WRITE_GRANULARITY(8)) storage (
        .clk(clk_i),.en(!reset_i && (writing || input_read_i || deferred_read_i)),
        .we(writing),.wmask(mask),.addr(address),.wdata(write_data),.rdata(data_o));
endmodule
