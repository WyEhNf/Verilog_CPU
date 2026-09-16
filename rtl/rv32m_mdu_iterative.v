`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Area-first unified RV32M engine.  Multiply and divide are mutually exclusive
// in the single MDU issue path, so they share one 65-bit shift state and one
// 32-bit operand register instead of retaining two complete datapaths.
module rv32m_mdu_iterative #(
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
    wire req_is_mul = (req_op_i == `RV32IM_OP_MUL) ||
        (req_op_i == `RV32IM_OP_MULH) ||
        (req_op_i == `RV32IM_OP_MULHSU) ||
        (req_op_i == `RV32IM_OP_MULHU);
    wire req_is_signed_div = (req_op_i == `RV32IM_OP_DIV) ||
        (req_op_i == `RV32IM_OP_REM);
    wire req_a_signed = req_is_signed_div ||
        (req_op_i == `RV32IM_OP_MUL) ||
        (req_op_i == `RV32IM_OP_MULH) ||
        (req_op_i == `RV32IM_OP_MULHSU);
    wire req_b_signed = req_is_signed_div ||
        (req_op_i == `RV32IM_OP_MUL) ||
        (req_op_i == `RV32IM_OP_MULH);
    wire req_a_negative = req_a_signed && req_src1_i[31];
    wire req_b_negative = req_b_signed && req_src2_i[31];
    wire [31:0] req_abs_a = req_a_negative ? (~req_src1_i + 32'd1) : req_src1_i;
    wire [31:0] req_abs_b = req_b_negative ? (~req_src2_i + 32'd1) : req_src2_i;

    reg busy;
    reg mode_mul;
    reg [5:0] step;
    reg [64:0] shift_state;
    reg [31:0] operand;
    reg [OP_WIDTH-1:0] operation;
    reg result_negative;
    reg remainder_negative;
    reg divide_zero;
    reg signed_overflow;
    reg [31:0] original_a;
    reg [TAG_WIDTH-1:0] operation_tag;
    reg [PHYS_ADDR_WIDTH-1:0] operation_phys;
    reg operation_live;

    reg out_valid;
    reg [31:0] out_value;
    reg [TAG_WIDTH-1:0] out_tag;
    reg [PHYS_ADDR_WIDTH-1:0] out_phys;
    reg out_live;

    reg [64:0] next_state;
    reg [32:0] upper_sum;
    reg [63:0] product_magnitude;
    reg [63:0] product_signed;
    reg [31:0] quotient_magnitude;
    reg [31:0] remainder_magnitude;
    reg [31:0] quotient_signed;
    reg [31:0] remainder_signed;
    reg [31:0] final_value;

    wire out_discard = out_valid && (!out_live ||
        (live_tag_valid_i && (out_tag != live_tag_i)));
    wire out_slot_ready = !out_valid || resp_ready_i || out_discard;

    always @* begin
        next_state = shift_state;
        upper_sum = 33'b0;
        if (mode_mul) begin
            upper_sum = shift_state[64:32] +
                (shift_state[0] ? {1'b0, operand} : 33'b0);
            next_state = {upper_sum, shift_state[31:0]} >> 1;
        end else begin
            next_state = shift_state << 1;
            if (next_state[64:32] >= {1'b0, operand}) begin
                next_state[64:32] = next_state[64:32] - {1'b0, operand};
                next_state[0] = 1'b1;
            end
        end

        product_magnitude = next_state[63:0];
        product_signed = result_negative ?
            (~product_magnitude + 64'd1) : product_magnitude;
        quotient_magnitude = next_state[31:0];
        remainder_magnitude = next_state[63:32];
        quotient_signed = result_negative ?
            (~quotient_magnitude + 32'd1) : quotient_magnitude;
        remainder_signed = remainder_negative ?
            (~remainder_magnitude + 32'd1) : remainder_magnitude;

        final_value = 32'b0;
        if (mode_mul) begin
            case (operation)
                `RV32IM_OP_MUL: final_value = product_signed[31:0];
                default: final_value = product_signed[63:32];
            endcase
        end else if (divide_zero) begin
            if ((operation == `RV32IM_OP_REM) || (operation == `RV32IM_OP_REMU))
                final_value = original_a;
            else
                final_value = 32'hffffffff;
        end else if (signed_overflow) begin
            final_value = (operation == `RV32IM_OP_REM) ? 32'b0 : 32'h80000000;
        end else if ((operation == `RV32IM_OP_REM) || (operation == `RV32IM_OP_REMU)) begin
            final_value = remainder_signed;
        end else begin
            final_value = quotient_signed;
        end
    end

    assign req_ready_o = !flush_i && !busy && out_slot_ready;
    assign resp_valid_o = out_valid && out_live &&
        (!live_tag_valid_i || (out_tag == live_tag_i));
    assign resp_value_o = out_value;
    assign resp_rob_tag_o = out_tag;
    assign resp_phys_rd_o = out_phys;
    assign resp_rd_we_o = 1'b1;

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            busy <= 1'b0;
            out_valid <= 1'b0;
        end else begin
            if (out_slot_ready)
                out_valid <= 1'b0;

            if (busy) begin
                shift_state <= next_state;
                if (step == 6'd31) begin
                    busy <= 1'b0;
                    out_valid <= 1'b1;
                    out_value <= final_value;
                    out_tag <= operation_tag;
                    out_phys <= operation_phys;
                    out_live <= operation_live;
                end else begin
                    step <= step + 1'b1;
                end
            end

            if (req_valid_i && req_ready_o) begin
                busy <= 1'b1;
                mode_mul <= req_is_mul;
                step <= 6'b0;
                shift_state <= req_is_mul ? {33'b0, req_abs_b} : {33'b0, req_abs_a};
                operand <= req_is_mul ? req_abs_a : req_abs_b;
                operation <= req_op_i;
                result_negative <= req_a_negative ^ req_b_negative;
                remainder_negative <= req_a_negative;
                divide_zero <= !req_is_mul && (req_src2_i == 0);
                signed_overflow <= req_is_signed_div &&
                    (req_src1_i == 32'h80000000) && (req_src2_i == 32'hffffffff);
                original_a <= req_src1_i;
                operation_tag <= req_rob_tag_i;
                operation_phys <= req_phys_rd_i;
                operation_live <= req_target_live_i && req_rob_tag_i[0];
            end
        end
    end
endmodule
