`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Single-register RV32M multiplier.  The datapath uses 32 magnitude partial
// products, vector 3:2 carry-save compressors, a Wallace reduction tree, and
// one final carry-propagate addition.  No behavioral multiply operator is
// used.  Keeping the whole tree before the result register removes two cycles
// of dependency latency and also removes the former intermediate registers.
module rv32m_multiplier #(
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
    function [63:0] csa_sum3;
        input [63:0] operand_a;
        input [63:0] operand_b;
        input [63:0] operand_c;
        begin
            csa_sum3 = operand_a ^ operand_b ^ operand_c;
        end
    endfunction

    function [63:0] csa_carry3;
        input [63:0] operand_a;
        input [63:0] operand_b;
        input [63:0] operand_c;
        begin
            csa_carry3 = ((operand_a & operand_b) |
                          (operand_a & operand_c) |
                          (operand_b & operand_c)) << 1;
        end
    endfunction

    wire req_a_signed = (req_op_i == `RV32IM_OP_MUL) ||
                        (req_op_i == `RV32IM_OP_MULH) ||
                        (req_op_i == `RV32IM_OP_MULHSU);
    wire req_b_signed = (req_op_i == `RV32IM_OP_MUL) ||
                        (req_op_i == `RV32IM_OP_MULH);
    wire req_a_negative = req_a_signed && req_src1_i[31];
    wire req_b_negative = req_b_signed && req_src2_i[31];
    wire req_product_negative = req_a_negative ^ req_b_negative;
    wire [31:0] req_abs_a = req_a_negative ? (~req_src1_i + 32'd1) : req_src1_i;
    wire [31:0] req_abs_b = req_b_negative ? (~req_src2_i + 32'd1) : req_src2_i;

    wire [63:0] partial_product [0:31];
    wire [63:0] wallace_l1 [0:21];
    wire [63:0] wallace_l2 [0:14];
    wire [63:0] wallace_l3 [0:9];
    genvar partial_index;
    genvar reduce_index;
    generate
        for (partial_index = 0; partial_index < 32; partial_index = partial_index + 1) begin : gen_partial
            assign partial_product[partial_index] = req_abs_b[partial_index] ?
                ({32'b0, req_abs_a} << partial_index) : 64'b0;
        end
        for (reduce_index = 0; reduce_index < 10; reduce_index = reduce_index + 1) begin : gen_wallace_l1
            assign wallace_l1[2*reduce_index] = csa_sum3(
                partial_product[3*reduce_index], partial_product[3*reduce_index+1],
                partial_product[3*reduce_index+2]);
            assign wallace_l1[2*reduce_index+1] = csa_carry3(
                partial_product[3*reduce_index], partial_product[3*reduce_index+1],
                partial_product[3*reduce_index+2]);
        end
        for (reduce_index = 0; reduce_index < 7; reduce_index = reduce_index + 1) begin : gen_wallace_l2
            assign wallace_l2[2*reduce_index] = csa_sum3(
                wallace_l1[3*reduce_index], wallace_l1[3*reduce_index+1],
                wallace_l1[3*reduce_index+2]);
            assign wallace_l2[2*reduce_index+1] = csa_carry3(
                wallace_l1[3*reduce_index], wallace_l1[3*reduce_index+1],
                wallace_l1[3*reduce_index+2]);
        end
        for (reduce_index = 0; reduce_index < 5; reduce_index = reduce_index + 1) begin : gen_wallace_l3
            assign wallace_l3[2*reduce_index] = csa_sum3(
                wallace_l2[3*reduce_index], wallace_l2[3*reduce_index+1],
                wallace_l2[3*reduce_index+2]);
            assign wallace_l3[2*reduce_index+1] = csa_carry3(
                wallace_l2[3*reduce_index], wallace_l2[3*reduce_index+1],
                wallace_l2[3*reduce_index+2]);
        end
    endgenerate
    assign wallace_l1[20] = partial_product[30];
    assign wallace_l1[21] = partial_product[31];
    assign wallace_l2[14] = wallace_l1[21];

    wire [63:0] wallace_l4 [0:6];
    wire [63:0] wallace_l5 [0:4];
    wire [63:0] wallace_l6 [0:3];
    wire [63:0] wallace_l7 [0:2];
    wire [63:0] wallace_sum;
    wire [63:0] wallace_carry;
    generate
        for (reduce_index = 0; reduce_index < 3; reduce_index = reduce_index + 1) begin : gen_wallace_l4
            assign wallace_l4[2*reduce_index] = csa_sum3(
                wallace_l3[3*reduce_index], wallace_l3[3*reduce_index+1],
                wallace_l3[3*reduce_index+2]);
            assign wallace_l4[2*reduce_index+1] = csa_carry3(
                wallace_l3[3*reduce_index], wallace_l3[3*reduce_index+1],
                wallace_l3[3*reduce_index+2]);
        end
        for (reduce_index = 0; reduce_index < 2; reduce_index = reduce_index + 1) begin : gen_wallace_l5
            assign wallace_l5[2*reduce_index] = csa_sum3(
                wallace_l4[3*reduce_index], wallace_l4[3*reduce_index+1],
                wallace_l4[3*reduce_index+2]);
            assign wallace_l5[2*reduce_index+1] = csa_carry3(
                wallace_l4[3*reduce_index], wallace_l4[3*reduce_index+1],
                wallace_l4[3*reduce_index+2]);
        end
    endgenerate
    assign wallace_l4[6] = wallace_l3[9];
    assign wallace_l5[4] = wallace_l4[6];
    assign wallace_l6[0] = csa_sum3(wallace_l5[0], wallace_l5[1], wallace_l5[2]);
    assign wallace_l6[1] = csa_carry3(wallace_l5[0], wallace_l5[1], wallace_l5[2]);
    assign wallace_l6[2] = wallace_l5[3];
    assign wallace_l6[3] = wallace_l5[4];
    assign wallace_l7[0] = csa_sum3(wallace_l6[0], wallace_l6[1], wallace_l6[2]);
    assign wallace_l7[1] = csa_carry3(wallace_l6[0], wallace_l6[1], wallace_l6[2]);
    assign wallace_l7[2] = wallace_l6[3];
    assign wallace_sum = csa_sum3(wallace_l7[0], wallace_l7[1], wallace_l7[2]);
    assign wallace_carry = csa_carry3(wallace_l7[0], wallace_l7[1], wallace_l7[2]);

    wire [63:0] request_magnitude = wallace_sum + wallace_carry;
    wire [63:0] request_product = req_product_negative ?
                                  (~request_magnitude + 64'd1) :
                                  request_magnitude;

    reg out_valid;
    reg [OP_WIDTH-1:0] out_op;
    reg [63:0] out_product;
    reg [TAG_WIDTH-1:0] out_tag;
    reg [PHYS_ADDR_WIDTH-1:0] out_phys;
    reg out_live;

    wire out_discard = out_valid && (!out_live ||
        (live_tag_valid_i && (out_tag != live_tag_i)));
    wire out_slot_ready = !out_valid || resp_ready_i || out_discard;
    reg [31:0] selected_value;

    assign req_ready_o = !flush_i && out_slot_ready;
    assign resp_valid_o = out_valid && out_live &&
        (!live_tag_valid_i || (out_tag == live_tag_i));
    assign resp_value_o = selected_value;
    assign resp_rob_tag_o = out_tag;
    assign resp_phys_rd_o = out_phys;
    assign resp_rd_we_o = 1'b1;

    always @* begin
        selected_value = 32'b0;
        case (out_op)
            `RV32IM_OP_MUL: selected_value = out_product[31:0];
            `RV32IM_OP_MULH, `RV32IM_OP_MULHSU, `RV32IM_OP_MULHU:
                selected_value = out_product[63:32];
            default: selected_value = 32'b0;
        endcase
    end

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            out_valid <= 1'b0;
            out_op <= {OP_WIDTH{1'b0}};
            out_product <= 64'b0;
            out_tag <= {TAG_WIDTH{1'b0}};
            out_phys <= {PHYS_ADDR_WIDTH{1'b0}};
            out_live <= 1'b0;
        end else begin
            if (out_slot_ready) begin
                out_valid <= req_valid_i;
                if (req_valid_i) begin
                    out_op <= req_op_i;
                    out_product <= request_product;
                    out_tag <= req_rob_tag_i;
                    out_phys <= req_phys_rd_i;
                    out_live <= req_target_live_i && req_rob_tag_i[0];
                end
            end
        end
    end
endmodule
