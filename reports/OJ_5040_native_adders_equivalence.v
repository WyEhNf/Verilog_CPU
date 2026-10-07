module verify_adders(input [31:0] lhs,rhs,input carry,output equal);
    function automatic [31:0] reference_fast_add_carry;
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
                reference_fast_add_carry[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
        end
    endfunction
    function automatic [31:0] candidate_fast_add_carry;
        input [31:0] lhs;
        input [31:0] adjusted_rhs;
        input carry_in;
`ifdef CPU2026_WORD_SIM
        begin
            candidate_fast_add_carry = lhs + adjusted_rhs + {31'b0, carry_in};
        end
`else
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
                candidate_fast_add_carry[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
        end
`endif
    endfunction
    function automatic [32:0] reference_prefix_add32;
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
                reference_prefix_add32[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
            reference_prefix_add32[32]=carry[8];
        end
    endfunction
    function automatic [32:0] candidate_prefix_add32;
        input [31:0] lhs;
        input [31:0] adjusted_rhs;
        input carry_in;
`ifdef CPU2026_WORD_SIM
        begin
            candidate_prefix_add32 = {1'b0, lhs} + {1'b0, adjusted_rhs} + {32'b0, carry_in};
        end
`else
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
                candidate_prefix_add32[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
            candidate_prefix_add32[32]=carry[8];
        end
`endif
    endfunction
assign equal=(reference_fast_add_carry(lhs,rhs,carry)==candidate_fast_add_carry(lhs,rhs,carry)) && (reference_prefix_add32(lhs,rhs,carry)==candidate_prefix_add32(lhs,rhs,carry));
endmodule
