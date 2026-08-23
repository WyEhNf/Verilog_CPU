`timescale 1ns/1ps

module rv32im_skid_buffer #(
    parameter integer WIDTH = 32
) (
    input  wire             clk_i,
    input  wire             reset_i,
    input  wire             flush_i,
    input  wire             in_valid_i,
    output wire             in_ready_o,
    input  wire [WIDTH-1:0] in_payload_i,
    output wire             out_valid_o,
    input  wire             out_ready_i,
    output wire [WIDTH-1:0] out_payload_o
);
    reg full_reg;
    reg [WIDTH-1:0] payload_reg;
    assign in_ready_o = !full_reg || out_ready_i;
    assign out_valid_o = full_reg;
    assign out_payload_o = payload_reg;

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            full_reg <= 1'b0;
            payload_reg <= {WIDTH{1'b0}};
        end else if (out_ready_i) begin
            full_reg <= in_valid_i;
            if (in_valid_i)
                payload_reg <= in_payload_i;
        end else if (!full_reg && in_valid_i) begin
            full_reg <= 1'b1;
            payload_reg <= in_payload_i;
        end
    end
endmodule
