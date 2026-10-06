"""Replace dependent restoring subtractions with parallel radix-4 trials.

Pure source preparation. No RTL execution or hardware tool is called.
For R<D, X=4R+b (b is the next two dividend bits) satisfies X<4D;
the unique quotient digit is the largest q in {0,1,2,3} with X>=qD.
"""
from prepare_staged_frequency_candidate import change, prepare, ROOT


def parallel_division(t):
    t=change(t,'// Two restoring digit steps per cycle with separate normalization and final correction, so',
               '// Parallel radix-4 trial subtraction with separate normalization and final correction, so')
    for line in (
        '    reg [32:0] remainder_shift;\n','    reg [32:0] remainder_after;\n',
        '    reg [31:0] quotient_after;\n','    reg [32:0] remainder_shift_second;\n',
        '    reg [32:0] remainder_after_second;\n','    reg [31:0] quotient_after_second;\n'):
        t=change(t,line,'')
    t=change(t,'''    wire [33:0] first_subtract={1'b0,remainder_shift}-{2'b0,divisor_reg};
    wire [33:0] second_subtract={1'b0,remainder_shift_second}-{2'b0,divisor_reg};''',r'''    // 3D is formed during the EXISTING prepare edge. It is valid before
    // any iteration and is never consumed by a fast/bypassed transaction.
    wire [33:0] divisor_triple;
    wire [33:0] triple_value={2'b0,divisor_reg}+{1'b0,divisor_reg,1'b0};
    rv32_frequency_word_bank #(.WIDTH(34)) triple_owner (
        .clk_i(clk_i),.write_i(!reset_i && !flush_i && busy_reg && prepare_reg),
        .data_i(triple_value),.data_o(divisor_triple));
    wire [3:0] odd_views;
    rv32_frequency_control_tree #(.LEAVES(4)) odd_tree (
        .signal_i(step_reg==31),.views_o(odd_views));
    wire [33:0] one_bit_trial={1'b0,remainder_reg[31:0],dividend_reg[31]};
    wire [33:0] two_bit_trial={remainder_reg[31:0],dividend_reg[31:30]};
    wire [33:0] trial;
    assign trial[31:0]=odd_views[0]?one_bit_trial[31:0]:two_bit_trial[31:0];
    assign trial[33:32]=odd_views[1]?one_bit_trial[33:32]:two_bit_trial[33:32];
    // Each 35-bit subtraction supplies a borrow without a separate compare.
    // The three trials start from the same register word, not one another.
    wire [34:0] subtract_one={1'b0,trial}-{3'b0,divisor_reg};
    wire [34:0] subtract_two={1'b0,trial}-{2'b0,divisor_reg,1'b0};
    wire [34:0] subtract_three={1'b0,trial}-{1'b0,divisor_triple};
    wire [3:0] digit_select;
    assign digit_select[0]=subtract_one[34];
    assign digit_select[1]=!subtract_one[34] && subtract_two[34];
    assign digit_select[2]=!subtract_two[34] && subtract_three[34];
    assign digit_select[3]=!subtract_three[34];
    wire [7:0] digit_views;
    rv32_frequency_control_tree #(.WIDTH(4),.LEAVES(2)) digit_tree (
        .signal_i(digit_select),.views_o(digit_views));
    wire [32:0] even_remainder;
    assign even_remainder[31:0]=
        ({32{digit_views[0]}} & trial[31:0]) |
        ({32{digit_views[1]}} & subtract_one[31:0]) |
        ({32{digit_views[2]}} & subtract_two[31:0]) |
        ({32{digit_views[3]}} & subtract_three[31:0]);
    assign even_remainder[32]=
        (digit_views[4] && trial[32]) |
        (digit_views[5] && subtract_one[32]) |
        (digit_views[6] && subtract_two[32]) |
        (digit_views[7] && subtract_three[32]);
    wire [1:0] even_digit={digit_views[6] | digit_views[7],digit_views[5] | digit_views[7]};
    wire [32:0] odd_remainder=subtract_one[34]?trial[32:0]:subtract_one[32:0];
    wire [31:0] odd_quotient={quotient_reg[30:0],!subtract_one[34]};
    wire [31:0] even_quotient={quotient_reg[29:0],even_digit};''')
    start=t.index('        remainder_shift = {remainder_reg[31:0], dividend_reg[31]};')
    stop=t.index('        if (sign_a_reg ^ sign_b_reg)',start)
    t=t[:start]+'''        // An odd final significant bit uses q in {0,1}; otherwise consume
        // two bits and append the parallel radix-4 digit. Remainder and
        // quotient update on the same existing edge as the former iterator.
        selected_remainder_after=odd_views[2]?odd_remainder:even_remainder;
        selected_quotient_after=odd_views[3]?odd_quotient:even_quotient;
'''+t[stop:]
    return t


if __name__=='__main__':
    prepare('AA_parallel_radix4_divider', ROOT/'Z_parallel_free_pool_refill',
            {'rtl/rv32m_divider.v':parallel_division},
            'Z plus parallel X-D/X-2D/X-3D radix-4 trials, 3D captured during existing prepare stage; unchanged two-bits-per-cycle iteration count, odd final digit, signs, caches, flush/live-tag and fast ISA results; 34 payload bits added, no new cycle, no EDA run')
