`timescale 1ns/1ps
`include "rv32im_defs.vh"

// BTB payload is meaningful only while valid and tag/kind match. Reset
// invalidates it; the original single accepted feedback owns every write.
module rv32_predictor_btb_row (
    input wire clk_i,reset_i,update_i,
    input wire [57:0] payload_i,
    output reg valid_o,
    output wire [23:0] tag_o,
    output wire [31:0] target_o,
    output wire [1:0] kind_o
);
    wire [57:0] payload;
    rv32_frequency_word_bank #(.WIDTH(58)) payload_owner (
        .clk_i(clk_i),.write_i(!reset_i && update_i),.data_i(payload_i),.data_o(payload));
    assign {tag_o,target_o,kind_o}=payload;
    always @(posedge clk_i) begin
        if(reset_i)
            valid_o<=0;
        else
            if(update_i)
                valid_o<=1;
    end
endmodule
