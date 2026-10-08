`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Actual in-flight store/RFO write-data state, retaining original byte masks
// and zero > write > merge priority. This is not the cache's data array.
(* keep_hierarchy = 1 *)
module rv32_dcache_mshr_data_bank #(
    parameter integer MSHR_ID = 0,
    parameter integer STORE_MISS_WRITE_AROUND = 0
) (
    input wire clk_i,
    input wire reset_i,
    input wire [3:0] request_action_i,
    input wire prefetch_allocate_i,
    input wire [2:0] second_free_i,
    input wire [2:0] free_i,
    input wire [2:0] matching_i,
    input wire [15:0] write_mask_i,
    input wire [127:0] write_data_i,
    output wire [127:0] data_o
);
    wire write_zero = prefetch_allocate_i && 32'(second_free_i) == MSHR_ID;
    wire write_word = ((request_action_i == 4'd8 ||
                       (STORE_MISS_WRITE_AROUND != 0 && request_action_i == 4'd9)) && 32'(free_i) == MSHR_ID) ||
                      (request_action_i == 4'd6 && 32'(matching_i) == MSHR_ID);
    wire merge_word = request_action_i == 4'd7 && 32'(matching_i) == MSHR_ID;
    wire [15:0] zero_views;
    rv32_frequency_control_tree #(.LEAVES(16)) zero_tree (
        .signal_i(reset_i || write_zero),.views_o(zero_views));
    genvar byte_id;
    generate for(byte_id=0;byte_id<16;byte_id=byte_id+1) begin:g_byte
        wire write_enable;
        wire [7:0] next_byte,saved_byte;
        wire update=write_word || (merge_word && write_mask_i[byte_id]);
        rv32_frequency_event_select #(.WIDTH(8),.EVENTS(2)) selector (
            .events_i({zero_views[byte_id],update}),
            .values_i({8'b0,write_data_i[byte_id*8 +: 8]}),
            .write_o(write_enable),.value_o(next_byte));
        rv32_frequency_word_bank #(.WIDTH(8)) owner (
            .clk_i(clk_i),.write_i(write_enable),.data_i(next_byte),.data_o(saved_byte));
        assign data_o[byte_id*8 +: 8]=saved_byte;
    end endgenerate
    initial begin
        if (MSHR_ID < 0 || MSHR_ID > 7) begin
            $display("ERROR: invalid D-cache MSHR data bank id");
            $finish;
        end
    end
endmodule
