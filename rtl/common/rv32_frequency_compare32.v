`timescale 1ns/1ps
// Balanced nibble comparison; the original ALU comparison network.
module rv32_frequency_compare32 (
    input wire [31:0] lhs_i, rhs_i,
    output wire [2:0] value_o
);
    wire [7:0] eq0,lt0;
    wire [3:0] eq1,lt1;
    wire [1:0] eq2,lt2;
    wire equal,unsigned_lt,signed_lt;
    for(genvar n=0;n<8;n=n+1) begin:g_nibble
        assign eq0[n]=lhs_i[n*4 +: 4]==rhs_i[n*4 +: 4];
        assign lt0[n]=lhs_i[n*4 +: 4]<rhs_i[n*4 +: 4];
    end
    for(genvar n=0;n<4;n=n+1) begin:g_pair
        assign eq1[n]=eq0[2*n+1] && eq0[2*n];
        assign lt1[n]=lt0[2*n+1] || (eq0[2*n+1] && lt0[2*n]);
    end
    for(genvar n=0;n<2;n=n+1) begin:g_quad
        assign eq2[n]=eq1[2*n+1] && eq1[2*n];
        assign lt2[n]=lt1[2*n+1] || (eq1[2*n+1] && lt1[2*n]);
    end
    assign equal=eq2[1] && eq2[0];
    assign unsigned_lt=lt2[1] || (eq2[1] && lt2[0]);
    assign signed_lt=(lhs_i[31]^rhs_i[31]) ? lhs_i[31] : unsigned_lt;
    assign value_o={signed_lt,unsigned_lt,equal};
endmodule
