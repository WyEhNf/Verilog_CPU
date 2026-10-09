`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Same nibble carry-select/prefix arithmetic as the integer ALU. Keep opcode
// control local to a stable RS row, before the original issue payload selector.
// The actual prefix implementation is also simulated in WORD_SIM builds.
module rv32_frequency_addsub32 (
    input wire [31:0] lhs_i,rhs_i,
    input wire subtract_i,
    output wire [31:0] value_o
);
    wire [2:0] subtract_views;
    wire [31:0] adjusted_rhs;
    rv32_frequency_control_tree #(.LEAVES(3)) subtract_tree (
        .signal_i(subtract_i),.views_o(subtract_views));
    assign adjusted_rhs[15:0]=rhs_i[15:0] ^ {16{subtract_views[0]}};
    assign adjusted_rhs[31:16]=rhs_i[31:16] ^ {16{subtract_views[1]}};
    assign value_o=fast_add_carry(lhs_i,adjusted_rhs,subtract_views[2]);

    function automatic [31:0] fast_add_carry;
        input [31:0] lhs;
        input [31:0] adjusted_rhs;
        input carry_in;
        reg [7:0] g0, p0, g1, p1, g2, p2, g3, p3;
        reg [8:0] carry;
        reg [4:0] chunk_sum;
        reg [31:0] sum_zero,sum_one;
        integer chunk;
        begin
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                chunk_sum = {1'b0, lhs[chunk*4 +: 4]} +
                            {1'b0, adjusted_rhs[chunk*4 +: 4]};
                // Both nibble results precede the group carry tree.
                // A late carry selects four bits; it does not start an adder.
                sum_zero[chunk*4 +: 4] = chunk_sum[3:0];
                sum_one[chunk*4 +: 4] = chunk_sum[3:0] + 4'd1;
                g0[chunk] = chunk_sum[4];
                p0[chunk] = &(lhs[chunk*4 +: 4] ^ adjusted_rhs[chunk*4 +: 4]);
            end
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                g1[chunk] = g0[chunk]; p1[chunk] = p0[chunk];
                if (chunk >= 1) begin
                    g1[chunk] = g0[chunk] | (p0[chunk] & g0[chunk-1]);
                    p1[chunk] = p0[chunk] & p0[chunk-1];
                end
            end
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                g2[chunk] = g1[chunk]; p2[chunk] = p1[chunk];
                if (chunk >= 2) begin
                    g2[chunk] = g1[chunk] | (p1[chunk] & g1[chunk-2]);
                    p2[chunk] = p1[chunk] & p1[chunk-2];
                end
            end
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                g3[chunk] = g2[chunk]; p3[chunk] = p2[chunk];
                if (chunk >= 4) begin
                    g3[chunk] = g2[chunk] | (p2[chunk] & g2[chunk-4]);
                    p3[chunk] = p2[chunk] & p2[chunk-4];
                end
            end
            carry[0] = carry_in;
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                carry[chunk+1] = g3[chunk] | (p3[chunk] & carry_in);
                fast_add_carry[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
        end
    endfunction
endmodule
