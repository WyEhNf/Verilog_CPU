`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Radix-4 restoring divider.  Two quotient bits are generated per cycle, so
// the worst case is 16 iterations rather than 32.  A request holds the unit
// busy until the quotient/remainder is complete; the response register then
// applies normal valid/ready backpressure and live-tag/flush cancellation.
module rv32m_divider #(
    parameter integer OP_WIDTH = `RV32IM_OP_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire                         req_valid_i,
    output wire                         req_ready_o,
    input  wire [OP_WIDTH-1:0]          req_op_i,
    input  wire [31:0]                  req_src1_i,
    input  wire [31:0]                  req_src2_i,
    input  wire [TAG_WIDTH-1:0]         req_rob_tag_i,
    input  wire [PHYS_ADDR_WIDTH-1:0]   req_phys_rd_i,
    input  wire                         req_target_live_i,
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
    reg [5:0] step_reg;
    reg [31:0] dividend_reg, divisor_reg, original_a_reg, original_b_reg;
    reg [31:0] quotient_reg;
    reg [32:0] remainder_reg;
    reg signed_mode_reg, want_remainder_reg, sign_a_reg, sign_b_reg;
    reg divide_zero_reg, signed_overflow_reg;
    reg [TAG_WIDTH-1:0] result_tag_reg;
    reg [PHYS_ADDR_WIDTH-1:0] result_phys_reg;
    reg result_live_reg;
    reg [31:0] result_value_reg;
    reg [32:0] remainder_shift;
    reg [32:0] remainder_after;
    reg [31:0] quotient_after;
    reg [32:0] remainder_shift_second;
    reg [32:0] remainder_after_second;
    reg [31:0] quotient_after_second;
    reg [32:0] selected_remainder_after;
    reg [31:0] selected_quotient_after;
    reg [31:0] quotient_final, remainder_final;

    // A quotient/remainder pair is computed together by the restoring
    // datapath.  Keep one signed and one unsigned pair so a compiler-emitted
    // DIV/REM pair with identical operands only runs the iterator once.
    reg signed_cache_valid_reg, unsigned_cache_valid_reg;
    reg [31:0] signed_cache_a_reg, signed_cache_b_reg;
    reg [31:0] signed_cache_q_reg, signed_cache_r_reg;
    reg [31:0] unsigned_cache_a_reg, unsigned_cache_b_reg;
    reg [31:0] unsigned_cache_q_reg, unsigned_cache_r_reg;

    function [5:0] count_leading_zeros;
        input [31:0] value;
        integer bit_index;
        reg found_one;
        begin
            count_leading_zeros = 6'd32;
            found_one = 1'b0;
            for (bit_index = 31; bit_index >= 0; bit_index = bit_index - 1) begin
                if (!found_one && value[bit_index]) begin
                    count_leading_zeros = 31 - bit_index;
                    found_one = 1'b1;
                end
            end
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
    wire [31:0] req_abs_a = req_sign_a ? (~req_src1_i + 32'd1) : req_src1_i;
    wire [31:0] req_abs_b = req_sign_b ? (~req_src2_i + 32'd1) : req_src2_i;
    wire req_dividend_smaller = !req_divide_zero &&
                                !req_signed_overflow &&
                                (req_abs_a < req_abs_b);
    wire req_signed_cache_hit = req_signed_operation &&
                                signed_cache_valid_reg &&
                                (signed_cache_a_reg == req_src1_i) &&
                                (signed_cache_b_reg == req_src2_i);
    wire req_unsigned_cache_hit = !req_signed_operation &&
                                  unsigned_cache_valid_reg &&
                                  (unsigned_cache_a_reg == req_src1_i) &&
                                  (unsigned_cache_b_reg == req_src2_i);
    wire req_cache_hit = req_signed_cache_hit || req_unsigned_cache_hit;
    wire [31:0] req_cached_quotient = req_signed_operation ?
                                      signed_cache_q_reg : unsigned_cache_q_reg;
    wire [31:0] req_cached_remainder = req_signed_operation ?
                                       signed_cache_r_reg : unsigned_cache_r_reg;
    wire req_fast_result = req_divide_zero || req_signed_overflow ||
                           req_dividend_smaller || req_cache_hit;
    wire [31:0] req_fast_value = req_divide_zero ?
        (req_want_remainder ? req_src1_i : 32'hffffffff) :
        (req_signed_overflow ?
         (req_want_remainder ? 32'b0 : 32'h80000000) :
         (req_dividend_smaller ?
          (req_want_remainder ? req_src1_i : 32'b0) :
          (req_want_remainder ? req_cached_remainder : req_cached_quotient)));
    wire [5:0] req_skip_steps = count_leading_zeros(req_abs_a);
    wire result_discard = result_valid_reg && (!result_live_reg ||
        (live_tag_valid_i && (result_tag_reg != live_tag_i)));

    assign req_ready_o = !flush_i && !busy_reg &&
        (!result_valid_reg || resp_ready_i || result_discard);
    assign resp_valid_o = result_valid_reg && result_live_reg &&
        (!live_tag_valid_i || (result_tag_reg == live_tag_i));
    assign resp_value_o = result_value_reg;
    assign resp_rob_tag_o = result_tag_reg;
    assign resp_phys_rd_o = result_phys_reg;
    assign resp_rd_we_o = 1'b1;

    always @* begin
        remainder_shift = {remainder_reg[31:0], dividend_reg[31]};
        if (remainder_shift >= {1'b0, divisor_reg}) begin
            remainder_after = remainder_shift - {1'b0, divisor_reg};
            quotient_after = {quotient_reg[30:0], 1'b1};
        end else begin
            remainder_after = remainder_shift;
            quotient_after = {quotient_reg[30:0], 1'b0};
        end
        remainder_shift_second = {remainder_after[31:0], dividend_reg[30]};
        if (remainder_shift_second >= {1'b0, divisor_reg}) begin
            remainder_after_second = remainder_shift_second -
                                     {1'b0, divisor_reg};
            quotient_after_second = {quotient_after[30:0], 1'b1};
        end else begin
            remainder_after_second = remainder_shift_second;
            quotient_after_second = {quotient_after[30:0], 1'b0};
        end
        // An odd number of significant dividend bits leaves a final
        // one-bit iteration at step 31; all other cycles consume two bits.
        if (step_reg == 31) begin
            selected_remainder_after = remainder_after;
            selected_quotient_after = quotient_after;
        end else begin
            selected_remainder_after = remainder_after_second;
            selected_quotient_after = quotient_after_second;
        end
        if (sign_a_reg ^ sign_b_reg)
            quotient_final = ~selected_quotient_after + 32'd1;
        else
            quotient_final = selected_quotient_after;
        if (sign_a_reg)
            remainder_final = ~selected_remainder_after[31:0] + 32'd1;
        else
            remainder_final = selected_remainder_after[31:0];
    end

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            busy_reg <= 1'b0;
            result_valid_reg <= 1'b0;
            step_reg <= 0;
            dividend_reg <= 0;
            divisor_reg <= 0;
            original_a_reg <= 0;
            original_b_reg <= 0;
            quotient_reg <= 0;
            remainder_reg <= 0;
            signed_mode_reg <= 0;
            want_remainder_reg <= 0;
            sign_a_reg <= 0;
            sign_b_reg <= 0;
            divide_zero_reg <= 0;
            signed_overflow_reg <= 0;
            result_tag_reg <= 0;
            result_phys_reg <= 0;
            result_live_reg <= 0;
            result_value_reg <= 0;
            signed_cache_valid_reg <= 1'b0;
            unsigned_cache_valid_reg <= 1'b0;
            signed_cache_a_reg <= 32'b0;
            signed_cache_b_reg <= 32'b0;
            signed_cache_q_reg <= 32'b0;
            signed_cache_r_reg <= 32'b0;
            unsigned_cache_a_reg <= 32'b0;
            unsigned_cache_b_reg <= 32'b0;
            unsigned_cache_q_reg <= 32'b0;
            unsigned_cache_r_reg <= 32'b0;
        end else begin
            if (result_valid_reg && (result_discard || resp_ready_i))
                result_valid_reg <= 1'b0;
            if (!busy_reg) begin
                if (req_valid_i && req_ready_o) begin
                    // The ISA fixes divide-by-zero and signed-overflow
                    // results.  They do not need to occupy the 32-step
                    // restoring datapath.
                    busy_reg <= !req_fast_result;
                    step_reg <= req_skip_steps;
                    original_a_reg <= req_src1_i;
                    original_b_reg <= req_src2_i;
                    signed_mode_reg <= (req_op_i == `RV32IM_OP_DIV) || (req_op_i == `RV32IM_OP_REM);
                    want_remainder_reg <= (req_op_i == `RV32IM_OP_REM) || (req_op_i == `RV32IM_OP_REMU);
                    sign_a_reg <= req_sign_a;
                    sign_b_reg <= req_sign_b;
                    divide_zero_reg <= (req_src2_i == 0);
                    signed_overflow_reg <= ((req_op_i == `RV32IM_OP_DIV) && (req_src1_i == 32'h80000000) && (req_src2_i == 32'hffffffff));
                    dividend_reg <= req_abs_a << req_skip_steps;
                    divisor_reg <= req_abs_b;
                    quotient_reg <= 0;
                    remainder_reg <= 0;
                    result_tag_reg <= req_rob_tag_i;
                    result_phys_reg <= req_phys_rd_i;
                    result_live_reg <= req_target_live_i && req_rob_tag_i[0];
                    if (req_fast_result) begin
                        result_valid_reg <= 1'b1;
                        result_value_reg <= req_fast_value;
                    end
                end
            end else begin
                dividend_reg <= (step_reg == 31) ?
                                {dividend_reg[30:0], 1'b0} :
                                {dividend_reg[29:0], 2'b0};
                remainder_reg <= selected_remainder_after;
                quotient_reg <= selected_quotient_after;
                if (step_reg >= 30) begin
                    busy_reg <= 1'b0;
                    result_valid_reg <= 1'b1;
                    if (divide_zero_reg) begin
                        if (want_remainder_reg)
                            result_value_reg <= original_a_reg;
                        else
                            result_value_reg <= 32'hffffffff;
                    end else if (signed_overflow_reg) begin
                        result_value_reg <= want_remainder_reg ? 32'b0 : 32'h80000000;
                    end else begin
                        result_value_reg <= want_remainder_reg ? remainder_final : quotient_final;
                        if (signed_mode_reg) begin
                            signed_cache_valid_reg <= 1'b1;
                            signed_cache_a_reg <= original_a_reg;
                            signed_cache_b_reg <= original_b_reg;
                            signed_cache_q_reg <= quotient_final;
                            signed_cache_r_reg <= remainder_final;
                        end else begin
                            unsigned_cache_valid_reg <= 1'b1;
                            unsigned_cache_a_reg <= original_a_reg;
                            unsigned_cache_b_reg <= original_b_reg;
                            unsigned_cache_q_reg <= quotient_final;
                            unsigned_cache_r_reg <= remainder_final;
                        end
                    end
                end else begin
                    step_reg <= step_reg + 2'd2;
                end
            end
        end
    end
endmodule
