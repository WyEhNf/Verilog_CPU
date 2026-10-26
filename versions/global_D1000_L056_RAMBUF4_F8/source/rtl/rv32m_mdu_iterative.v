`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Area-first unified RV32M engine.  Multiply and divide are mutually exclusive
// in the single MDU issue path, so they share one 65-bit shift state and one
// 32-bit operand register instead of retaining two complete datapaths.
module rv32m_mdu_iterative #(
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
    // One extra completion edge separates iteration from sign correction.
    // No request may replace operation/tag state while this phase is valid.
    reg finishing;
    wire [31:0] finishing_magnitude;
    wire finishing_negate,finishing_increment;
    wire mode_mul;
    reg [5:0] step;
    wire [64:0] shift_state;
    wire [31:0] operand;
    wire [OP_WIDTH-1:0] operation;
    wire result_negative;
    wire remainder_negative;
    wire divide_zero;
    wire signed_overflow;
    wire [31:0] original_a;
    wire [TAG_WIDTH-1:0] operation_tag;
    wire [PHYS_ADDR_WIDTH-1:0] operation_phys;
    wire operation_live;

    reg out_valid;
    wire [31:0] out_value;
    wire [TAG_WIDTH-1:0] out_tag;
    wire [PHYS_ADDR_WIDTH-1:0] out_phys;
    wire out_live;

    reg [64:0] next_state;
    reg [32:0] upper_sum;
    reg [31:0] result_magnitude;
    reg result_needs_negate;
    reg result_negate_increment;
    reg [31:0] corrected_result;
    reg [31:0] final_value;

    wire [2*RECOVERY_WIDTH-1:0] recovery_views;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(2)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
    assign occupied_o=busy || finishing || out_valid;
    wire operation_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) operation_cancel_guard (
        .packet_i(recovery_views[0 +: RECOVERY_WIDTH]),.active_i(busy || finishing),.tag_i(operation_tag),.cancel_o(operation_cancel));
    wire out_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) out_cancel_guard (
        .packet_i(recovery_views[RECOVERY_WIDTH +: RECOVERY_WIDTH]),.active_i(out_valid),.tag_i(out_tag),.cancel_o(out_cancel));
    wire request_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) request_cancel_guard (
        .packet_i(recovery_packet_i),.active_i(req_valid_i),.tag_i(req_rob_tag_i),.cancel_o(request_cancel));
    wire out_discard = out_valid && (out_cancel || !out_live ||
        (live_tag_valid_i && (out_tag != live_tag_i)));
    wire out_slot_ready = !out_valid || resp_ready_i || out_discard;

    // The lower-word carry also supplies the 33-bit unsigned
    // subtraction decision. u33 >= d32 iff u33[32] or low-word no-borrow.
    // The difference top bit is u33[32] XOR borrow, including u33[32]=1.
    wire [64:0] division_shifted=shift_state<<1;
    // Multiply and divide cannot execute together. Select their operands
    // before one common feedback adder; final correction stays in its own
    // registered completion interval. Each mode leaf controls 16 mux bits.
    wire [3:0] feedback_mode_views;
    rv32_frequency_control_tree #(.LEAVES(4)) feedback_mode_tree (
        .signal_i(mode_mul),.views_o(feedback_mode_views));
    wire [31:0] feedback_lhs,feedback_rhs;
    genvar feedback_word;
    generate for(feedback_word=0;feedback_word<2;feedback_word=feedback_word+1) begin:g_feedback_operands
        assign feedback_lhs[feedback_word*16 +: 16]=feedback_mode_views[feedback_word]?
            shift_state[32+feedback_word*16 +: 16]:division_shifted[32+feedback_word*16 +: 16];
        assign feedback_rhs[feedback_word*16 +: 16]=feedback_mode_views[2+feedback_word]?
            (shift_state[0]?operand[feedback_word*16 +: 16]:16'b0):~operand[feedback_word*16 +: 16];
    end endgenerate
    wire [32:0] feedback_sum=prefix_add32(feedback_lhs,feedback_rhs,!mode_mul);
    wire [32:0] multiply_upper_sum={shift_state[64]^feedback_sum[32],feedback_sum[31:0]};
    wire division_no_borrow=division_shifted[64] || feedback_sum[32];
    wire [32:0] division_difference={division_shifted[64]^!feedback_sum[32],feedback_sum[31:0]};
    wire [32:0] finishing_correction=prefix_add32(~finishing_magnitude,32'b0,finishing_increment);
    wire [31:0] finishing_corrected=finishing_negate?finishing_correction[31:0]:finishing_magnitude;
    wire operation_is_remainder=(operation==`RV32IM_OP_REM || operation==`RV32IM_OP_REMU);
    wire [31:0] finishing_value=(!mode_mul && divide_zero)?
        (operation_is_remainder?original_a:32'hffffffff):
        ((!mode_mul && signed_overflow)?
         ((operation==`RV32IM_OP_REM)?32'b0:32'h80000000):finishing_corrected);
    function [32:0] prefix_add32;
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
                prefix_add32[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
            prefix_add32[32]=carry[8];
        end
    endfunction

    always @* begin
        next_state = shift_state;
        upper_sum = 33'b0;
        if (mode_mul) begin
            upper_sum = multiply_upper_sum;
            next_state = {upper_sum, shift_state[31:0]} >> 1;
        end else begin
            next_state = division_shifted;
            if (division_no_borrow) begin
                next_state[64:32] = division_difference;
                next_state[0] = 1'b1;
            end
        end

        // All ordinary results share one 32-bit sign-correction adder.  For a
        // negative high-half multiply, the carry into bit 32 is one exactly
        // when the low magnitude word is zero:
        //   (-M)[63:32] = ~M[63:32] + (M[31:0] == 0)
        result_magnitude = next_state[31:0];
        result_needs_negate = result_negative;
        result_negate_increment = 1'b1;
        if (mode_mul && (operation != `RV32IM_OP_MUL)) begin
            result_magnitude = next_state[63:32];
            result_negate_increment = (next_state[31:0] == 0);
        end else if (!mode_mul &&
                     ((operation == `RV32IM_OP_REM) ||
                      (operation == `RV32IM_OP_REMU))) begin
            result_magnitude = next_state[63:32];
            result_needs_negate = remainder_negative;
        end
        corrected_result = result_needs_negate ?
            (~result_magnitude + {{31{1'b0}}, result_negate_increment}) :
            result_magnitude;

        final_value = 32'b0;
        if (mode_mul) begin
            final_value = corrected_result;
        end else if (divide_zero) begin
            if ((operation == `RV32IM_OP_REM) || (operation == `RV32IM_OP_REMU))
                final_value = original_a;
            else
                final_value = 32'hffffffff;
        end else if (signed_overflow) begin
            final_value = (operation == `RV32IM_OP_REM) ? 32'b0 : 32'h80000000;
        end else begin
            final_value = corrected_result;
        end
    end

    assign req_ready_o = !flush_i && !operation_cancel && !request_cancel && !busy && !finishing && out_slot_ready;
    assign resp_valid_o = out_valid && !out_cancel && out_live &&
        (!live_tag_valid_i || (out_tag == live_tag_i));
    assign resp_value_o = out_value;
    assign resp_rob_tag_o = out_tag;
    assign resp_phys_rd_o = out_phys;
    assign resp_rd_we_o = 1'b1;

    // Preserve the original capture edges and unreset payload lifetime.
    // A late launch enable formerly drove every operation/shift operand
    // state mux. Named word owners distribute write control per16 data bits.
    wire payload_normal=!reset_i && !flush_i;
    wire payload_launch=payload_normal && req_valid_i && req_ready_o;
    wire payload_iterate=payload_normal && busy && !operation_cancel;
    wire payload_finish_capture=payload_iterate && step==6'd31;
    wire payload_publish=payload_normal && finishing && !operation_cancel && out_slot_ready;
    wire [3:0] launch_views,launch_mode_views;
    rv32_frequency_control_tree #(.LEAVES(4)) launch_tree (
        .signal_i(payload_launch),.views_o(launch_views));
    rv32_frequency_control_tree #(.LEAVES(4)) launch_mode_tree (
        .signal_i(req_is_mul),.views_o(launch_mode_views));
    wire [31:0] initial_low,initial_operand;
    generate for(genvar initial_word=0;initial_word<2;initial_word=initial_word+1) begin:g_initial_word
        assign initial_low[initial_word*16 +: 16]=launch_mode_views[initial_word]?
            req_abs_b[initial_word*16 +: 16]:req_abs_a[initial_word*16 +: 16];
        assign initial_operand[initial_word*16 +: 16]=launch_mode_views[2+initial_word]?
            req_abs_a[initial_word*16 +: 16]:req_abs_b[initial_word*16 +: 16];
    end endgenerate
    wire shift_write;
    wire [64:0] shift_next;
    rv32_frequency_event_select #(.WIDTH(65),.EVENTS(2),.PRIORITY(0)) shift_selector (
        .events_i({payload_iterate,launch_views[0]}),
        .values_i({next_state,33'b0,initial_low}),.write_o(shift_write),.value_o(shift_next));
    rv32_frequency_word_bank #(.WIDTH(65)) shift_state_owner (
        .clk_i(clk_i),.write_i(shift_write),.data_i(shift_next),.data_o(shift_state));
    rv32_frequency_word_bank #(.WIDTH(32)) operand_owner (
        .clk_i(clk_i),.write_i(launch_views[1]),.data_i(initial_operand),.data_o(operand));
    rv32_frequency_word_bank #(.WIDTH(32)) original_owner (
        .clk_i(clk_i),.write_i(launch_views[2]),.data_i(req_src1_i),.data_o(original_a));
    localparam integer OPERATION_PAYLOAD_WIDTH=OP_WIDTH+TAG_WIDTH+PHYS_ADDR_WIDTH+6;
    wire [OPERATION_PAYLOAD_WIDTH-1:0] operation_payload;
    assign {mode_mul,operation,result_negative,remainder_negative,divide_zero,signed_overflow,
        operation_tag,operation_phys,operation_live}=operation_payload;
    rv32_frequency_word_bank #(.WIDTH(OPERATION_PAYLOAD_WIDTH)) operation_owner (
        .clk_i(clk_i),.write_i(launch_views[3]),
        .data_i({req_is_mul,req_op_i,req_a_negative^req_b_negative,req_a_negative,
            !req_is_mul && req_src2_i==32'b0,
            req_is_signed_div && req_src1_i==32'h80000000 && req_src2_i==32'hffffffff,
            req_rob_tag_i,req_phys_rd_i,req_target_live_i && req_rob_tag_i[0]}),.data_o(operation_payload));
    rv32_frequency_word_bank #(.WIDTH(34)) finishing_owner (
        .clk_i(clk_i),.write_i(payload_finish_capture),
        .data_i({result_magnitude,result_needs_negate,result_negate_increment}),
        .data_o({finishing_magnitude,finishing_negate,finishing_increment}));
    localparam integer OUTPUT_PAYLOAD_WIDTH=33+TAG_WIDTH+PHYS_ADDR_WIDTH;
    rv32_frequency_word_bank #(.WIDTH(OUTPUT_PAYLOAD_WIDTH)) output_owner (
        .clk_i(clk_i),.write_i(payload_publish),
        .data_i({finishing_value,operation_tag,operation_phys,operation_live}),
        .data_o({out_value,out_tag,out_phys,out_live}));

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            busy <= 1'b0;
            finishing <= 1'b0;
            out_valid <= 1'b0;
        end else begin
            if (out_slot_ready)
                out_valid <= 1'b0;

            if(operation_cancel) begin busy<=1'b0;finishing<=1'b0;end
            if (busy && !operation_cancel) begin
                if (step == 6'd31) begin
                    busy <= 1'b0;
                    finishing <= 1'b1;
                end else begin
                    step <= step + 1'b1;
                end
            end

            if(finishing && !operation_cancel && out_slot_ready) begin
                finishing<=1'b0;
                out_valid<=1'b1;
            end

            if (req_valid_i && req_ready_o) begin
                busy <= 1'b1;
                step <= 6'b0;
            end
        end
    end
endmodule
