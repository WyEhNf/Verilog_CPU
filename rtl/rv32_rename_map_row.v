`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_rename_map_row #(parameter integer LANES=4,PAW=6) (
    input wire clk_i,reset_i,restore_i,
    input wire [PAW-1:0] restore_value_i,
    input wire [LANES-1:0] match_i,
    input wire [LANES*PAW-1:0] values_i,
    output reg [PAW-1:0] value_o
);
    reg [PAW-1:0] selected;
    integer lane;
    always @* begin
        selected=0;
        for(lane=0;lane<LANES;lane=lane+1)
            if(match_i[lane]) selected=values_i[lane*PAW +: PAW];
    end
    always @(posedge clk_i) begin
        if(reset_i)
            value_o<=0;
        else
            if(restore_i)
                value_o<=restore_value_i;
            else
                if(|match_i)
                    value_o<=selected;
    end
endmodule
