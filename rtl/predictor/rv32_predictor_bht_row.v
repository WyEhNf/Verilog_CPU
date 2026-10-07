`timescale 1ns/1ps
`include "rv32im_defs.vh"

/* verilator lint_on UNUSEDSIGNAL */

// Saturating direction counter preserves weakly-taken reset and first
// training behavior. Every row owns three reset/update state bits.
module rv32_predictor_bht_row (
    input wire clk_i,reset_i,update_i,taken_i,
    output reg [1:0] counter_o,
    output reg trained_o
);
    always @(posedge clk_i) begin
        if(reset_i)
        begin
            counter_o<=2'b10;
            trained_o<=0;
        end
        else
            if(update_i)
            begin
                trained_o<=1;
                if(taken_i)
                begin
                    if(counter_o!=2'b11)
                        counter_o<=counter_o+2'b01;
                end
                else
                    if(counter_o!=2'b00)
                        counter_o<=counter_o-2'b01;
            end
    end
endmodule
