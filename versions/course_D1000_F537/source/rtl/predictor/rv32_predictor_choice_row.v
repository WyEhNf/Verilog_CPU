`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Preference saturates toward the predictor that was actually right at fetch.
// With equal predictions, the parent never updates this row. Cold preference
// is weakly bimodal; both direction tables still learn every accepted branch.
module rv32_predictor_choice_row (
    input wire clk_i,reset_i,update_i,global_correct_i,
    output reg [1:0] counter_o
);
    always @(posedge clk_i) begin
        if(reset_i)
            counter_o<=2'b01;
        else
            if(update_i)
            begin
                if(global_correct_i)
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
