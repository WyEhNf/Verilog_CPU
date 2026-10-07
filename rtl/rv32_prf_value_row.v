`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Highest valid lane wins. Value payload has no later reset mux; the final
// write enable already excludes reset before its priced local driver.
module rv32_prf_value_row #(parameter integer LANES=4) (
    input wire clk_i,reset_i,alloc_i,
    input wire [LANES-1:0] write_matches_i,
    input wire [LANES*32-1:0] write_values_i,
    output reg [31:0] value_o,
    output reg ready_o
);
    wire [1:0] write_views;
    wire write_event;
    wire [31:0] next_value;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(LANES)) value_selector (
        .events_i(write_matches_i),.values_i(write_values_i),.write_o(write_event),.value_o(next_value));
    rv32_frequency_control_tree #(.LEAVES(2)) write_tree (
        .signal_i(!reset_i && write_event),.views_o(write_views));
    always @(posedge clk_i) if(write_views[0])
        value_o[15:0]<=next_value[15:0];
    always @(posedge clk_i) if(write_views[1])
        value_o[31:16]<=next_value[31:16];
    always @(posedge clk_i) begin
        if(reset_i)
            ready_o<=0;
        else
            if(|write_matches_i)
                ready_o<=1;
            else
                if(alloc_i)
                    ready_o<=0;
    end
endmodule
