`timescale 1ns/1ps
`include "rv32im_defs.vh"

// In direct-target mode only JALR allocates the BTB. Its kind and target bit0
// are constants; the hash is predictor metadata, never architectural identity.
module rv32_predictor_indirect_btb_row (
    input wire clk_i,reset_i,update_i,
    input wire [38:0] payload_i,
    output reg valid_o,
    output wire [7:0] tag_o,
    output wire [31:0] target_o
);
    wire [38:0] payload;
    rv32_frequency_word_bank #(.WIDTH(39)) payload_owner (
        .clk_i(clk_i),.write_i(!reset_i && update_i),.data_i(payload_i),.data_o(payload));
    assign tag_o=payload[38:31];
    assign target_o={payload[30:0],1'b0};
    always @(posedge clk_i) begin
        if(reset_i)
            valid_o<=0;
        else
            if(update_i)
                valid_o<=1;
    end
endmodule
