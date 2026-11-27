`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Compact radix-4 shift/add multiplier_reg.  It processes two multiplier_reg bits per
// cycle and shares one iterative datapath across all RV32M multiply variants.
module rv32m_multiplier_radix4 #(
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
    wire req_a_signed = (req_op_i == `RV32IM_OP_MUL) ||
                        (req_op_i == `RV32IM_OP_MULH) ||
                        (req_op_i == `RV32IM_OP_MULHSU);
    wire req_b_signed = (req_op_i == `RV32IM_OP_MUL) ||
                        (req_op_i == `RV32IM_OP_MULH);
    wire req_a_negative = req_a_signed && req_src1_i[31];
    wire req_b_negative = req_b_signed && req_src2_i[31];
    wire [31:0] req_abs_a = req_a_negative ? (~req_src1_i + 32'd1) : req_src1_i;
    wire [31:0] req_abs_b = req_b_negative ? (~req_src2_i + 32'd1) : req_src2_i;

    reg busy;
    reg [3:0] iteration;
    reg [63:0] accumulator;
    reg [63:0] multiplicand;
    reg [31:0] multiplier_reg;
    reg operation_negative;
    reg [OP_WIDTH-1:0] operation;
    reg [TAG_WIDTH-1:0] operation_tag;
    reg [PHYS_ADDR_WIDTH-1:0] operation_phys;
    reg operation_live;

    reg out_valid;
    reg [OP_WIDTH-1:0] out_op;
    reg [63:0] out_product;
    reg [TAG_WIDTH-1:0] out_tag;
    reg [PHYS_ADDR_WIDTH-1:0] out_phys;
    reg out_live;

    reg [63:0] radix_addend;
    reg [31:0] selected_value;
    wire [63:0] iteration_sum = accumulator + radix_addend;
    wire [2*RECOVERY_WIDTH-1:0] recovery_views;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(2)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
    assign occupied_o=busy || out_valid;
    wire operation_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) operation_cancel_guard (
        .packet_i(recovery_views[0 +: RECOVERY_WIDTH]),.active_i(busy),.tag_i(operation_tag),.cancel_o(operation_cancel));
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

    always @* begin
        case (multiplier_reg[1:0])
            2'b01: radix_addend = multiplicand;
            2'b10: radix_addend = multiplicand << 1;
            2'b11: radix_addend = multiplicand + (multiplicand << 1);
            default: radix_addend = 64'b0;
        endcase
    end

    always @* begin
        selected_value = 32'b0;
        case (out_op)
            `RV32IM_OP_MUL: selected_value = out_product[31:0];
            `RV32IM_OP_MULH, `RV32IM_OP_MULHSU, `RV32IM_OP_MULHU:
                selected_value = out_product[63:32];
            default: selected_value = 32'b0;
        endcase
    end

    assign req_ready_o = !flush_i && !operation_cancel && !request_cancel && !busy && out_slot_ready;
    assign resp_valid_o = out_valid && !out_cancel && out_live &&
        (!live_tag_valid_i || (out_tag == live_tag_i));
    assign resp_value_o = selected_value;
    assign resp_rob_tag_o = out_tag;
    assign resp_phys_rd_o = out_phys;
    assign resp_rd_we_o = 1'b1;

    always @(posedge clk_i) begin
        if (reset_i || flush_i)
        begin
            busy <= 1'b0;
            iteration <= 4'b0;
            accumulator <= 64'b0;
            multiplicand <= 64'b0;
            multiplier_reg <= 32'b0;
            operation_negative <= 1'b0;
            operation <= {OP_WIDTH{1'b0}};
            operation_tag <= {TAG_WIDTH{1'b0}};
            operation_phys <= {PHYS_ADDR_WIDTH{1'b0}};
            operation_live <= 1'b0;
            out_valid <= 1'b0;
            out_op <= {OP_WIDTH{1'b0}};
            out_product <= 64'b0;
            out_tag <= {TAG_WIDTH{1'b0}};
            out_phys <= {PHYS_ADDR_WIDTH{1'b0}};
            out_live <= 1'b0;
        end
        else
        begin
            if (out_slot_ready)
                out_valid <= 1'b0;
            if(operation_cancel)
                busy<=1'b0;
            if (busy && !operation_cancel)
            begin
                accumulator <= iteration_sum;
                multiplicand <= multiplicand << 2;
                multiplier_reg <= multiplier_reg >> 2;
                iteration <= iteration + 1'b1;
                if (iteration == 4'd15)
                begin
                    busy <= 1'b0;
                    out_valid <= 1'b1;
                    out_op <= operation;
                    out_product <= operation_negative ? (~iteration_sum + 64'd1) : iteration_sum;
                    out_tag <= operation_tag;
                    out_phys <= operation_phys;
                    out_live <= operation_live;
                end
            end
            if (req_valid_i && req_ready_o)
            begin
                busy <= 1'b1;
                iteration <= 4'b0;
                accumulator <= 64'b0;
                multiplicand <= {32'b0, req_abs_a};
                multiplier_reg <= req_abs_b;
                operation_negative <= req_a_negative ^ req_b_negative;
                operation <= req_op_i;
                operation_tag <= req_rob_tag_i;
                operation_phys <= req_phys_rd_i;
                operation_live <= req_target_live_i && req_rob_tag_i[0];
            end
        end
    end
endmodule
