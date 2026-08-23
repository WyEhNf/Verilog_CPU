`timescale 1ns/1ps

module rv32im_priority_select #(
    parameter integer WIDTH = 4
) (
    input  wire [WIDTH-1:0] valid_i,
    output reg              grant_valid_o,
    output reg [((WIDTH <= 2) ? 1 : $clog2(WIDTH))-1:0] grant_index_o,
    output reg [WIDTH-1:0] grant_onehot_o
);
    /* verilator lint_off WIDTHTRUNC */
    integer i;
    reg found;
    always @* begin
        grant_valid_o = 1'b0;
        grant_index_o = {((WIDTH <= 2) ? 1 : $clog2(WIDTH)){1'b0}};
        grant_onehot_o = {WIDTH{1'b0}};
        found = 1'b0;
        for (i = 0; i < WIDTH; i = i + 1) begin
            if (valid_i[i] && !found) begin
                grant_valid_o = 1'b1;
                grant_index_o = i;
                grant_onehot_o[i] = 1'b1;
                found = 1'b1;
            end
        end
    end
    /* verilator lint_on WIDTHTRUNC */
endmodule
