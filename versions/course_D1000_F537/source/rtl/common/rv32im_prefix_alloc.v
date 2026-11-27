`timescale 1ns/1ps

module rv32im_prefix_alloc #(
    parameter integer LANES = 4
) (
    input  wire [LANES-1:0] valid_i,
    input  wire [((LANES <= 1) ? 1 : $clog2(LANES + 1))-1:0] capacity_i,
    output reg  [LANES-1:0] grant_o,
    output reg  [((LANES <= 1) ? 1 : $clog2(LANES + 1))-1:0] count_o
);
    integer i;
    reg stop;
    always @* begin
        grant_o = {LANES{1'b0}};
        count_o = {((LANES <= 1) ? 1 : $clog2(LANES + 1)){1'b0}};
        stop = 1'b0;
        for (i = 0; i < LANES; i = i + 1) begin
            if (!stop && valid_i[i] && (count_o < capacity_i)) begin
                grant_o[i] = 1'b1;
                count_o = count_o + 1'b1;
            end else if (!valid_i[i]) begin
                stop = 1'b1;
            end else if (count_o >= capacity_i) begin
                stop = 1'b1;
            end
        end
    end
endmodule
