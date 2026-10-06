`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parallel radix-4 trial subtraction with separate normalization and final correction, so
// the worst case is 16 iterations rather than 32.  A request holds the unit
// busy until the quotient/remainder is complete; the response register then
// applies normal valid/ready backpressure and live-tag/flush cancellation.
module rv32m_divider #(
    parameter integer OP_WIDTH = `RV32IM_OP_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer SELECTIVE_RECOVERY = 0,
    parameter integer RECOVERY_WIDTH = 1+2*((ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES))+$clog2(ROB_ENTRIES+1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire [RECOVERY_WIDTH-1:0]    recovery_packet_i,
    input  wire                         req_valid_i,
    output wire                         req_ready_o,
    input  wire [OP_WIDTH-1:0]          req_op_i,
    input  wire [31:0]                  req_src1_i,
    input  wire [31:0]                  req_src2_i,
    input  wire [TAG_WIDTH-1:0]         req_rob_tag_i,
    input  wire [PHYS_ADDR_WIDTH-1:0]   req_phys_rd_i,
    input  wire                         req_target_live_i,
    output wire                         occupied_o,
    output wire                         resp_valid_o,
    input  wire                         resp_ready_i,
    output wire [31:0]                  resp_value_o,
    output wire [TAG_WIDTH-1:0]         resp_rob_tag_o,
    output wire [PHYS_ADDR_WIDTH-1:0]   resp_phys_rd_o,
    output wire                         resp_rd_we_o,
    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i
);
    reg busy_reg, result_valid_reg;
    reg prepare_reg, finish_reg;
    reg [5:0] step_reg;
    wire [31:0] dividend_reg, divisor_reg, original_a_reg, original_b_reg;
    wire [31:0] quotient_reg;
    wire [32:0] remainder_reg;
    reg signed_mode_reg, want_remainder_reg, sign_a_reg, sign_b_reg;
    reg divide_zero_reg, signed_overflow_reg;
    wire [TAG_WIDTH-1:0] result_tag_reg;
    wire [PHYS_ADDR_WIDTH-1:0] result_phys_reg;
    reg result_live_reg;
    wire [31:0] result_value_reg;
    wire [32:0] selected_remainder_after;
    wire [31:0] selected_quotient_after;
    wire [31:0] quotient_final, remainder_final;

    // A quotient/remainder pair is computed together by the restoring
    // datapath.  Keep one signed and one unsigned pair so a compiler-emitted
    // DIV/REM pair with identical operands only runs the iterator once.
    reg signed_cache_valid_reg, unsigned_cache_valid_reg;
    wire [31:0] signed_cache_a_reg, signed_cache_b_reg;
    wire [31:0] signed_cache_q_reg, signed_cache_r_reg;
    wire [31:0] unsigned_cache_a_reg, unsigned_cache_b_reg;
    wire [31:0] unsigned_cache_q_reg, unsigned_cache_r_reg;

    // Hierarchical 16/8/4/2/1 priority selection, rather than a 32-bit
    // serial found-one chain. Zero has an explicit 32 result.
    function [5:0] count_leading_zeros;
        input [31:0] value;
        reg [31:0] shifted;
        reg [5:0] count;
        begin
            shifted=value; count=0;
            if(shifted[31:16]==0) begin count=count+16;shifted=shifted<<16;end
            if(shifted[31:24]==0) begin count=count+8;shifted=shifted<<8;end
            if(shifted[31:28]==0) begin count=count+4;shifted=shifted<<4;end
            if(shifted[31:30]==0) begin count=count+2;shifted=shifted<<2;end
            if(!shifted[31]) count=count+1;
            count_leading_zeros=(value==0)?6'd32:count;
        end
    endfunction

    wire req_want_remainder = (req_op_i == `RV32IM_OP_REM) ||
                              (req_op_i == `RV32IM_OP_REMU);
    wire req_signed_operation = (req_op_i == `RV32IM_OP_DIV) ||
                                (req_op_i == `RV32IM_OP_REM);
    wire req_divide_zero = (req_src2_i == 0);
    wire req_signed_overflow = req_signed_operation &&
        (req_src1_i == 32'h80000000) && (req_src2_i == 32'hffffffff);
    wire req_sign_a = req_signed_operation && req_src1_i[31];
    wire req_sign_b = req_signed_operation && req_src2_i[31];
    wire [31:0] req_abs_a,req_abs_b;
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
    end endgenerate
    wire req_signed_cache_hit = req_signed_operation &&
                                signed_cache_valid_reg &&
                                (signed_cache_a_reg == req_src1_i) &&
                                (signed_cache_b_reg == req_src2_i);
    wire req_unsigned_cache_hit = !req_signed_operation &&
                                  unsigned_cache_valid_reg &&
                                  (unsigned_cache_a_reg == req_src1_i) &&
                                  (unsigned_cache_b_reg == req_src2_i);
    wire req_cache_hit = req_signed_cache_hit || req_unsigned_cache_hit;
    // Decode only scalar cache choice. Each one-hot leaf selects <=16 bits;
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
    wire operation_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) operation_cancel_guard (
        .packet_i(recovery_packet_i),.active_i(busy_reg || result_valid_reg),.tag_i(result_tag_reg),.cancel_o(operation_cancel));
    wire request_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) request_cancel_guard (
        .packet_i(recovery_packet_i),.active_i(req_valid_i),.tag_i(req_rob_tag_i),.cancel_o(request_cancel));
    assign occupied_o=busy_reg || result_valid_reg;
    wire payload_clear=reset_i || flush_i;
    wire payload_active=!payload_clear && !operation_cancel;
    wire payload_accept=payload_active && !busy_reg && req_valid_i && req_ready_o;
    wire payload_prepare=payload_active && busy_reg && prepare_reg;
    wire magnitude_smaller=dividend_reg<divisor_reg;
    wire payload_normalize=payload_prepare && !magnitude_smaller;
    wire payload_early_result=payload_prepare && magnitude_smaller;
    wire payload_finish=payload_active && busy_reg && !prepare_reg && finish_reg;
    wire payload_iterate=payload_active && busy_reg && !prepare_reg && !finish_reg;
    wire payload_fast_result=payload_accept && req_fast_result;
    wire payload_normal_finish=payload_finish && !divide_zero_reg && !signed_overflow_reg;
    wire payload_signed_cache=payload_normal_finish && signed_mode_reg;
    wire payload_unsigned_cache=payload_normal_finish && !signed_mode_reg;
    wire [5:0] prepare_skip_steps = count_leading_zeros(dividend_reg);
    // 3D is formed during the EXISTING prepare edge. It is valid before
    // any iteration and is never consumed by a fast/bypassed transaction.
    wire [33:0] divisor_triple;
    wire [33:0] triple_value={2'b0,divisor_reg}+{1'b0,divisor_reg,1'b0};
    rv32_frequency_word_bank #(.WIDTH(34)) triple_owner (
        .clk_i(clk_i),.write_i(payload_prepare),
        .data_i(triple_value),.data_o(divisor_triple));
    wire [9:0] odd_views;
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
    wire [11:0] digit_views;
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
    wire result_discard = result_valid_reg && (operation_cancel || !result_live_reg ||
        (live_tag_valid_i && (result_tag_reg != live_tag_i)));

    assign req_ready_o = !flush_i && !operation_cancel && !request_cancel && !busy_reg &&
        (!result_valid_reg || resp_ready_i || result_discard);
    assign resp_valid_o = result_valid_reg && !operation_cancel && result_live_reg &&
        (!live_tag_valid_i || (result_tag_reg == live_tag_i));
    assign resp_value_o = result_value_reg;
    assign resp_rob_tag_o = result_tag_reg;
    assign resp_phys_rd_o = result_phys_reg;
    assign resp_rd_we_o = 1'b1;

    wire [31:0] negative_quotient=~quotient_reg+32'd1;
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
    wire [REQUEST_PAYLOAD_WIDTH-1:0] request_payload_next;
    wire request_payload_write;
    rv32_frequency_event_select #(.WIDTH(REQUEST_PAYLOAD_WIDTH),.EVENTS(2),.PRIORITY(0)) request_payload_selector (
        .events_i({payload_clear,payload_accept}),
        .values_i({{REQUEST_PAYLOAD_WIDTH{1'b0}},{req_src1_i,req_src2_i,req_abs_b,req_rob_tag_i,req_phys_rd_i}}),
        .write_o(request_payload_write),.value_o(request_payload_next));
    rv32_frequency_word_bank #(.WIDTH(REQUEST_PAYLOAD_WIDTH)) request_payload_owner (
        .clk_i(clk_i),.write_i(request_payload_write),.data_i(request_payload_next),.data_o(request_payload));
    wire [32-1:0] dividend_payload_next;
    wire dividend_payload_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) dividend_payload_selector (
        .events_i({payload_clear,payload_iterate,payload_normalize,payload_accept}),
        .values_i({32'b0,iterate_dividend,normalized_dividend,req_abs_a}),
        .write_o(dividend_payload_write),.value_o(dividend_payload_next));
    rv32_frequency_word_bank #(.WIDTH(32)) dividend_payload_owner (
        .clk_i(clk_i),.write_i(dividend_payload_write),.data_i(dividend_payload_next),.data_o(dividend_reg));
    wire [65-1:0] iterator_payload_next;
    wire iterator_payload_write;
    rv32_frequency_event_select #(.WIDTH(65),.EVENTS(3),.PRIORITY(0)) iterator_payload_selector (
        .events_i({payload_clear,payload_iterate,payload_accept}),
        .values_i({65'b0,{selected_quotient_after,selected_remainder_after},65'b0}),
        .write_o(iterator_payload_write),.value_o(iterator_payload_next));
    rv32_frequency_word_bank #(.WIDTH(65)) iterator_payload_owner (
        .clk_i(clk_i),.write_i(iterator_payload_write),.data_i(iterator_payload_next),.data_o(iterator_payload));
    wire [32-1:0] result_payload_next;
    wire result_payload_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) result_payload_selector (
        .events_i({payload_clear,payload_finish,payload_early_result,payload_fast_result}),
        .values_i({32'b0,finish_result_value,early_result_value,req_fast_value}),
        .write_o(result_payload_write),.value_o(result_payload_next));
    rv32_frequency_word_bank #(.WIDTH(32)) result_payload_owner (
        .clk_i(clk_i),.write_i(result_payload_write),.data_i(result_payload_next),.data_o(result_value_reg));
    wire [128-1:0] signed_cache_payload_next;
    wire signed_cache_payload_write;
    rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2),.PRIORITY(0)) signed_cache_payload_selector (
        .events_i({payload_clear,payload_signed_cache}),
        .values_i({128'b0,{original_a_reg,original_b_reg,quotient_final,remainder_final}}),
        .write_o(signed_cache_payload_write),.value_o(signed_cache_payload_next));
    rv32_frequency_word_bank #(.WIDTH(128)) signed_cache_payload_owner (
        .clk_i(clk_i),.write_i(signed_cache_payload_write),.data_i(signed_cache_payload_next),.data_o(signed_cache_payload));
    wire [128-1:0] unsigned_cache_payload_next;
    wire unsigned_cache_payload_write;
    rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2),.PRIORITY(0)) unsigned_cache_payload_selector (
        .events_i({payload_clear,payload_unsigned_cache}),
        .values_i({128'b0,{original_a_reg,original_b_reg,quotient_final,remainder_final}}),
        .write_o(unsigned_cache_payload_write),.value_o(unsigned_cache_payload_next));
    rv32_frequency_word_bank #(.WIDTH(128)) unsigned_cache_payload_owner (
        .clk_i(clk_i),.write_i(unsigned_cache_payload_write),.data_i(unsigned_cache_payload_next),.data_o(unsigned_cache_payload));
    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            busy_reg<=1'b0; prepare_reg<=1'b0; finish_reg<=1'b0;
            result_valid_reg<=1'b0; step_reg<=0;
            signed_mode_reg<=0; want_remainder_reg<=0;
            sign_a_reg<=0; sign_b_reg<=0;
            divide_zero_reg<=0; signed_overflow_reg<=0;
            result_live_reg<=0;
            signed_cache_valid_reg<=1'b0; unsigned_cache_valid_reg<=1'b0;
        end else if(operation_cancel) begin
            // Payload/cache history is pure data; clear transaction ownership.
            // No canceled prepare/finish/iteration may publish a new result.
            busy_reg<=1'b0; prepare_reg<=1'b0; finish_reg<=1'b0;
            result_valid_reg<=1'b0; result_live_reg<=1'b0;
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
