`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Iterative 32-step restoring divider.  A request holds the unit busy until
// the quotient/remainder is complete; the response register then applies
// normal valid/ready backpressure and live-tag/flush cancellation.
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
    reg [31:0] quotient_final, remainder_final;
    wire req_want_remainder = (req_op_i == `RV32IM_OP_REM) ||
                              (req_op_i == `RV32IM_OP_REMU);
    wire req_signed_operation = (req_op_i == `RV32IM_OP_DIV) ||
                                (req_op_i == `RV32IM_OP_REM);
    wire req_divide_zero = (req_src2_i == 0);
    wire req_signed_overflow = req_signed_operation &&
        (req_src1_i == 32'h80000000) && (req_src2_i == 32'hffffffff);
    wire req_fast_result = req_divide_zero || req_signed_overflow;
    wire [31:0] req_fast_value = req_divide_zero ?
        (req_want_remainder ? req_src1_i : 32'hffffffff) :
        (req_want_remainder ? 32'b0 : 32'h80000000);
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
        if (sign_a_reg ^ sign_b_reg)
            quotient_final = ~quotient_after + 32'd1;
        else
            quotient_final = quotient_after;
        if (sign_a_reg)
            remainder_final = ~remainder_after[31:0] + 32'd1;
        else
            remainder_final = remainder_after[31:0];
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
        end else begin
            if (result_valid_reg && (result_discard || resp_ready_i))
                result_valid_reg <= 1'b0;
            if (!busy_reg) begin
                if (req_valid_i && req_ready_o) begin
                    // The ISA fixes divide-by-zero and signed-overflow
                    // results.  They do not need to occupy the 32-step
                    // restoring datapath.
                    busy_reg <= !req_fast_result;
                    step_reg <= 0;
                    original_a_reg <= req_src1_i;
                    original_b_reg <= req_src2_i;
                    signed_mode_reg <= (req_op_i == `RV32IM_OP_DIV) || (req_op_i == `RV32IM_OP_REM);
                    want_remainder_reg <= (req_op_i == `RV32IM_OP_REM) || (req_op_i == `RV32IM_OP_REMU);
                    sign_a_reg <= ((req_op_i == `RV32IM_OP_DIV) || (req_op_i == `RV32IM_OP_REM)) && req_src1_i[31];
                    sign_b_reg <= ((req_op_i == `RV32IM_OP_DIV) || (req_op_i == `RV32IM_OP_REM)) && req_src2_i[31];
                    divide_zero_reg <= (req_src2_i == 0);
                    signed_overflow_reg <= ((req_op_i == `RV32IM_OP_DIV) && (req_src1_i == 32'h80000000) && (req_src2_i == 32'hffffffff));
                    dividend_reg <= (((req_op_i == `RV32IM_OP_DIV) || (req_op_i == `RV32IM_OP_REM)) && req_src1_i[31]) ? (~req_src1_i + 32'd1) : req_src1_i;
                    divisor_reg <= (((req_op_i == `RV32IM_OP_DIV) || (req_op_i == `RV32IM_OP_REM)) && req_src2_i[31]) ? (~req_src2_i + 32'd1) : req_src2_i;
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
                dividend_reg <= {dividend_reg[30:0], 1'b0};
                remainder_reg <= remainder_after;
                quotient_reg <= quotient_after;
                if (step_reg == 31) begin
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
                    end
                end else begin
                    step_reg <= step_reg + 1'b1;
                end
            end
        end
    end
endmodule
