"""Prepare DIV payload/control distribution from CN; no HDL/EDA execution."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def owner(name, width, events, values, output):
    return f'''    wire [{width}-1:0] {name}_next;
    wire {name}_write;
    rv32_frequency_event_select #(.WIDTH({width}),.EVENTS({len(events)}),.PRIORITY(0)) {name}_selector (
        .events_i({{{','.join(reversed(events))}}}),
        .values_i({{{','.join(reversed(values))}}}),
        .write_o({name}_write),.value_o({name}_next));
    rv32_frequency_word_bank #(.WIDTH({width})) {name}_owner (
        .clk_i(clk_i),.write_i({name}_write),.data_i({name}_next),.data_o({output}));
'''


def divider(source):
    for old, new in [
        ('    reg [31:0] dividend_reg, divisor_reg, original_a_reg, original_b_reg;',
         '    wire [31:0] dividend_reg, divisor_reg, original_a_reg, original_b_reg;'),
        ('    reg [31:0] quotient_reg;', '    wire [31:0] quotient_reg;'),
        ('    reg [32:0] remainder_reg;', '    wire [32:0] remainder_reg;'),
        ('    reg [TAG_WIDTH-1:0] result_tag_reg;', '    wire [TAG_WIDTH-1:0] result_tag_reg;'),
        ('    reg [PHYS_ADDR_WIDTH-1:0] result_phys_reg;', '    wire [PHYS_ADDR_WIDTH-1:0] result_phys_reg;'),
        ('    reg [31:0] result_value_reg;', '    wire [31:0] result_value_reg;'),
        ('    reg [32:0] selected_remainder_after;', '    wire [32:0] selected_remainder_after;'),
        ('    reg [31:0] selected_quotient_after;', '    wire [31:0] selected_quotient_after;'),
        ('    reg [31:0] quotient_final, remainder_final;', '    wire [31:0] quotient_final, remainder_final;'),
        ('    reg [31:0] signed_cache_a_reg, signed_cache_b_reg;', '    wire [31:0] signed_cache_a_reg, signed_cache_b_reg;'),
        ('    reg [31:0] signed_cache_q_reg, signed_cache_r_reg;', '    wire [31:0] signed_cache_q_reg, signed_cache_r_reg;'),
        ('    reg [31:0] unsigned_cache_a_reg, unsigned_cache_b_reg;', '    wire [31:0] unsigned_cache_a_reg, unsigned_cache_b_reg;'),
        ('    reg [31:0] unsigned_cache_q_reg, unsigned_cache_r_reg;', '    wire [31:0] unsigned_cache_q_reg, unsigned_cache_r_reg;'),
    ]:
        source = change(source, old, new)

    source = change(source, '''    wire [31:0] req_abs_a = req_sign_a ? (~req_src1_i + 32'd1) : req_src1_i;
    wire [31:0] req_abs_b = req_sign_b ? (~req_src2_i + 32'd1) : req_src2_i;''', '''    wire [31:0] req_abs_a,req_abs_b;
    wire [31:0] req_neg_a=~req_src1_i+32'd1;
    wire [31:0] req_neg_b=~req_src2_i+32'd1;
    wire [3:0] req_sign_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(2)) req_sign_tree (
        .signal_i({req_sign_b,req_sign_a}),.views_o(req_sign_views));
    generate for(genvar sign_word=0;sign_word<2;sign_word=sign_word+1) begin:g_request_magnitude
        assign req_abs_a[sign_word*16 +: 16]=req_sign_views[sign_word*2]?
            req_neg_a[sign_word*16 +: 16]:req_src1_i[sign_word*16 +: 16];
        assign req_abs_b[sign_word*16 +: 16]=req_sign_views[sign_word*2+1]?
            req_neg_b[sign_word*16 +: 16]:req_src2_i[sign_word*16 +: 16];
    end endgenerate''')
    start = source.index('    wire [31:0] req_cached_quotient')
    end = source.index('    wire [5:0] prepare_skip_steps', start)
    source = source[:start] + '''    // Decode only scalar cache choice. Each one-hot leaf selects <=16 bits;
    // the previous signed/remainder controls drove four full-word muxes.
    wire [3:0] cache_value_events={
        req_signed_operation && req_want_remainder,
        req_signed_operation && !req_want_remainder,
        !req_signed_operation && req_want_remainder,
        !req_signed_operation && !req_want_remainder};
    wire [31:0] req_cached_value;
    wire unused_cache_value_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) cache_value_selector (
        .events_i(cache_value_events),
        .values_i({signed_cache_r_reg,signed_cache_q_reg,unsigned_cache_r_reg,unsigned_cache_q_reg}),
        .write_o(unused_cache_value_write),.value_o(req_cached_value));
    wire req_fast_result=req_divide_zero || req_signed_overflow || req_cache_hit;
    wire [31:0] req_fast_value;
    wire unused_fast_value_write;
    wire [4:0] fast_value_events={
        req_divide_zero && req_want_remainder,
        req_divide_zero && !req_want_remainder,
        !req_divide_zero && req_signed_overflow && req_want_remainder,
        !req_divide_zero && req_signed_overflow && !req_want_remainder,
        !req_divide_zero && !req_signed_overflow};
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(5),.PRIORITY(0)) fast_value_selector (
        .events_i(fast_value_events),
        .values_i({req_src1_i,32'hffffffff,32'b0,32'h80000000,req_cached_value}),
        .write_o(unused_fast_value_write),.value_o(req_fast_value));

    // Mutually exclusive commands mirror the original nested state machine.
    // Reset/flush still write ZERO to every former reset payload register.
    wire payload_clear=reset_i || flush_i;
    wire payload_accept=!payload_clear && !busy_reg && req_valid_i && req_ready_o;
    wire payload_prepare=!payload_clear && busy_reg && prepare_reg;
    wire magnitude_smaller=dividend_reg<divisor_reg;
    wire payload_normalize=payload_prepare && !magnitude_smaller;
    wire payload_early_result=payload_prepare && magnitude_smaller;
    wire payload_finish=!payload_clear && busy_reg && !prepare_reg && finish_reg;
    wire payload_iterate=!payload_clear && busy_reg && !prepare_reg && !finish_reg;
    wire payload_fast_result=payload_accept && req_fast_result;
    wire payload_normal_finish=payload_finish && !divide_zero_reg && !signed_overflow_reg;
    wire payload_signed_cache=payload_normal_finish && signed_mode_reg;
    wire payload_unsigned_cache=payload_normal_finish && !signed_mode_reg;
''' + source[end:]
    source = change(source, '.write_i(!reset_i && !flush_i && busy_reg && prepare_reg)',
                            '.write_i(payload_prepare)')
    start = source.index('    wire [3:0] odd_views;')
    end = source.index('    // Each 35-bit subtraction', start)
    source = source[:start] + '''    wire [9:0] odd_views;
    rv32_frequency_control_tree #(.LEAVES(10)) odd_tree (
        .signal_i(step_reg==31),.views_o(odd_views));
    wire [33:0] one_bit_trial={1'b0,remainder_reg[31:0],dividend_reg[31]};
    wire [33:0] two_bit_trial={remainder_reg[31:0],dividend_reg[31:30]};
    wire [33:0] trial;
    generate for(genvar trial_word=0;trial_word<3;trial_word=trial_word+1) begin:g_trial
        localparam integer LOW=trial_word*16;
        localparam integer BITS=(34-LOW>=16)?16:34-LOW;
        assign trial[LOW +: BITS]=odd_views[trial_word]?
            one_bit_trial[LOW +: BITS]:two_bit_trial[LOW +: BITS];
    end endgenerate
''' + source[end:]
    start = source.index('    wire [7:0] digit_views;')
    end = source.index('    wire result_discard', start)
    source = source[:start] + '''    wire [11:0] digit_views;
    rv32_frequency_control_tree #(.WIDTH(4),.LEAVES(3)) digit_tree (
        .signal_i(digit_select),.views_o(digit_views));
    wire [32:0] even_remainder;
    generate for(genvar digit_word=0;digit_word<3;digit_word=digit_word+1) begin:g_digit_remainder
        localparam integer LOW=digit_word*16;
        localparam integer BITS=(33-LOW>=16)?16:33-LOW;
        assign even_remainder[LOW +: BITS]=
            ({BITS{digit_views[digit_word*4]}} & trial[LOW +: BITS]) |
            ({BITS{digit_views[digit_word*4+1]}} & subtract_one[LOW +: BITS]) |
            ({BITS{digit_views[digit_word*4+2]}} & subtract_two[LOW +: BITS]) |
            ({BITS{digit_views[digit_word*4+3]}} & subtract_three[LOW +: BITS]);
    end endgenerate
    wire [1:0] even_digit={digit_views[10] | digit_views[11],digit_views[9] | digit_views[11]};
    wire [2:0] odd_borrow_views;
    rv32_frequency_control_tree #(.LEAVES(3)) odd_borrow_tree (
        .signal_i(subtract_one[34]),.views_o(odd_borrow_views));
    wire [32:0] odd_remainder;
    generate for(genvar odd_word=0;odd_word<3;odd_word=odd_word+1) begin:g_odd_remainder
        localparam integer LOW=odd_word*16;
        localparam integer BITS=(33-LOW>=16)?16:33-LOW;
        assign odd_remainder[LOW +: BITS]=odd_borrow_views[odd_word]?
            trial[LOW +: BITS]:subtract_one[LOW +: BITS];
        assign selected_remainder_after[LOW +: BITS]=odd_views[3+odd_word]?
            odd_remainder[LOW +: BITS]:even_remainder[LOW +: BITS];
    end endgenerate
    wire [31:0] odd_quotient={quotient_reg[30:0],!odd_borrow_views[2]};
    wire [31:0] even_quotient={quotient_reg[29:0],even_digit};
    wire [31:0] iterate_dividend;
    wire [31:0] odd_dividend={dividend_reg[30:0],1'b0};
    wire [31:0] even_dividend={dividend_reg[29:0],2'b0};
    generate for(genvar iterate_word=0;iterate_word<2;iterate_word=iterate_word+1) begin:g_iteration_choice
        assign selected_quotient_after[iterate_word*16 +: 16]=odd_views[6+iterate_word]?
            odd_quotient[iterate_word*16 +: 16]:even_quotient[iterate_word*16 +: 16];
        assign iterate_dividend[iterate_word*16 +: 16]=odd_views[8+iterate_word]?
            odd_dividend[iterate_word*16 +: 16]:even_dividend[iterate_word*16 +: 16];
    end endgenerate
''' + source[end:]

    start = source.index('    always @* begin\n        // An odd final')
    end = source.index('    always @(posedge clk_i) begin', start)
    source = source[:start] + '''    wire [31:0] negative_quotient=~quotient_reg+32'd1;
    wire [31:0] negative_remainder=~remainder_reg[31:0]+32'd1;
    wire [3:0] correction_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(2)) correction_tree (
        .signal_i({sign_a_reg,sign_a_reg ^ sign_b_reg}),.views_o(correction_views));
    generate for(genvar correction_word=0;correction_word<2;correction_word=correction_word+1) begin:g_correction
        assign quotient_final[correction_word*16 +: 16]=correction_views[correction_word*2]?
            negative_quotient[correction_word*16 +: 16]:quotient_reg[correction_word*16 +: 16];
        assign remainder_final[correction_word*16 +: 16]=correction_views[correction_word*2+1]?
            negative_remainder[correction_word*16 +: 16]:remainder_reg[correction_word*16 +: 16];
    end endgenerate
    wire [31:0] normalized_dividend,normalize_shift;
    wire [31:0] unused_normalize_right;
    wire [1:0] normalize_zero_views;
    rv32_frequency_barrel32 normalization (
        .value_i(dividend_reg),.amount_i(prepare_skip_steps[4:0]),.fill_i(1'b0),
        .left_o(normalize_shift),.right_o(unused_normalize_right));
    rv32_frequency_control_tree #(.LEAVES(2)) normalize_zero_tree (
        .signal_i(prepare_skip_steps[5]),.views_o(normalize_zero_views));
    wire [31:0] early_result_value,finish_result_value;
    wire [1:0] early_result_views;
    rv32_frequency_control_tree #(.LEAVES(2)) early_result_tree (
        .signal_i(want_remainder_reg),.views_o(early_result_views));
    generate for(genvar result_word=0;result_word<2;result_word=result_word+1) begin:g_result_choice
        assign normalized_dividend[result_word*16 +: 16]=
            {16{!normalize_zero_views[result_word]}} & normalize_shift[result_word*16 +: 16];
        assign early_result_value[result_word*16 +: 16]=early_result_views[result_word]?
            original_a_reg[result_word*16 +: 16]:16'b0;
    end endgenerate
    wire [5:0] finish_value_events={
        divide_zero_reg && want_remainder_reg,
        divide_zero_reg && !want_remainder_reg,
        !divide_zero_reg && signed_overflow_reg && want_remainder_reg,
        !divide_zero_reg && signed_overflow_reg && !want_remainder_reg,
        !divide_zero_reg && !signed_overflow_reg && want_remainder_reg,
        !divide_zero_reg && !signed_overflow_reg && !want_remainder_reg};
    wire unused_finish_value_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(6),.PRIORITY(0)) finish_value_selector (
        .events_i(finish_value_events),
        .values_i({original_a_reg,32'hffffffff,32'b0,32'h80000000,remainder_final,quotient_final}),
        .write_o(unused_finish_value_write),.value_o(finish_result_value));

    localparam integer REQUEST_PAYLOAD_WIDTH=96+TAG_WIDTH+PHYS_ADDR_WIDTH;
    wire [REQUEST_PAYLOAD_WIDTH-1:0] request_payload;
    assign {original_a_reg,original_b_reg,divisor_reg,result_tag_reg,result_phys_reg}=request_payload;
    wire [64:0] iterator_payload;
    assign {quotient_reg,remainder_reg}=iterator_payload;
    wire [127:0] signed_cache_payload,unsigned_cache_payload;
    assign {signed_cache_a_reg,signed_cache_b_reg,signed_cache_q_reg,signed_cache_r_reg}=signed_cache_payload;
    assign {unsigned_cache_a_reg,unsigned_cache_b_reg,unsigned_cache_q_reg,unsigned_cache_r_reg}=unsigned_cache_payload;
''' + owner('request_payload', 'REQUEST_PAYLOAD_WIDTH',
             ['payload_accept', 'payload_clear'],
             ['{req_src1_i,req_src2_i,req_abs_b,req_rob_tag_i,req_phys_rd_i}', "{REQUEST_PAYLOAD_WIDTH{1'b0}}"], 'request_payload') + owner(
        'dividend_payload', '32',
        ['payload_accept', 'payload_normalize', 'payload_iterate', 'payload_clear'],
        ['req_abs_a', 'normalized_dividend', 'iterate_dividend', "32'b0"], 'dividend_reg') + owner(
        'iterator_payload', '65', ['payload_accept', 'payload_iterate', 'payload_clear'],
        ["65'b0", '{selected_quotient_after,selected_remainder_after}', "65'b0"], 'iterator_payload') + owner(
        'result_payload', '32', ['payload_fast_result', 'payload_early_result', 'payload_finish', 'payload_clear'],
        ['req_fast_value', 'early_result_value', 'finish_result_value', "32'b0"], 'result_value_reg') + owner(
        'signed_cache_payload', '128', ['payload_signed_cache', 'payload_clear'],
        ['{original_a_reg,original_b_reg,quotient_final,remainder_final}', "128'b0"], 'signed_cache_payload') + owner(
        'unsigned_cache_payload', '128', ['payload_unsigned_cache', 'payload_clear'],
        ['{original_a_reg,original_b_reg,quotient_final,remainder_final}', "128'b0"], 'unsigned_cache_payload') + source[end:]

    # Replace only the original scalar-state process; payload owners above
    # retain all 504 existing payload FFs (with default tag/phys widths).
    start = source.index('    always @(posedge clk_i) begin\n        if (reset_i || flush_i)')
    source = source[:start] + '''    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            busy_reg<=1'b0; prepare_reg<=1'b0; finish_reg<=1'b0;
            result_valid_reg<=1'b0; step_reg<=0;
            signed_mode_reg<=0; want_remainder_reg<=0;
            sign_a_reg<=0; sign_b_reg<=0;
            divide_zero_reg<=0; signed_overflow_reg<=0;
            result_live_reg<=0;
            signed_cache_valid_reg<=1'b0; unsigned_cache_valid_reg<=1'b0;
        end else begin
            if(result_valid_reg && (result_discard || resp_ready_i))
                result_valid_reg<=1'b0;
            if(!busy_reg) begin
                if(req_valid_i && req_ready_o) begin
                    busy_reg<=!req_fast_result; prepare_reg<=!req_fast_result;
                    finish_reg<=1'b0; step_reg<=0;
                    signed_mode_reg<=(req_op_i==`RV32IM_OP_DIV) || (req_op_i==`RV32IM_OP_REM);
                    want_remainder_reg<=(req_op_i==`RV32IM_OP_REM) || (req_op_i==`RV32IM_OP_REMU);
                    sign_a_reg<=req_sign_a; sign_b_reg<=req_sign_b;
                    divide_zero_reg<=(req_src2_i==0);
                    signed_overflow_reg<=((req_op_i==`RV32IM_OP_DIV) &&
                        (req_src1_i==32'h80000000) && (req_src2_i==32'hffffffff));
                    result_live_reg<=req_target_live_i && req_rob_tag_i[0];
                    if(req_fast_result) result_valid_reg<=1'b1;
                end
            end else if(prepare_reg) begin
                prepare_reg<=1'b0;
                if(magnitude_smaller) begin
                    busy_reg<=1'b0; result_valid_reg<=1'b1;
                end else step_reg<=prepare_skip_steps;
            end else if(finish_reg) begin
                finish_reg<=1'b0; busy_reg<=1'b0; result_valid_reg<=1'b1;
                if(!divide_zero_reg && !signed_overflow_reg) begin
                    if(signed_mode_reg) signed_cache_valid_reg<=1'b1;
                    else unsigned_cache_valid_reg<=1'b1;
                end
            end else begin
                if(step_reg>=30) finish_reg<=1'b1;
                else step_reg<=step_reg+2'd2;
            end
        end
    end
endmodule
'''
    return source


if __name__ == '__main__':
    prepare('CO_divider_payload_distribution', ROOT/'CN_lsq_request_data_distribution', {
        'rtl/rv32m_divider.v': divider,
    }, 'CN plus mutually exclusive DIV payload commands and 16-bit word owners on existing request, normalization, iterator, result and signed/unsigned cache edges; bounded digit/borrow/odd/sign/normalization mux controls. Reset/flush zero payload and scalar/event priority, RV32M special cases, cache pairs, ready/live tags, radix-4 and cycle count preserved. No new FF/SRAM or hardware tests; source-only candidate.')
