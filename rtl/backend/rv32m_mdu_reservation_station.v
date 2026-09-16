`timescale 1ns/1ps
`include "rv32im_defs.vh"

// One-entry MDU reservation station.  It holds a tagged multiply/divide
// issue packet until the selected unit accepts it, while the units retain
// their own in-flight and completion state.
module rv32m_mdu_reservation_station #(
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer MUL_IMPL = 0
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire                         issue_valid_i,
    output wire                         issue_ready_o,
    input  wire [`RV32IM_OP_WIDTH-1:0]  issue_op_i,
    input  wire [31:0]                  issue_src1_i,
    input  wire [31:0]                  issue_src2_i,
    input  wire [TAG_WIDTH-1:0]         issue_rob_tag_i,
    input  wire [PHYS_ADDR_WIDTH-1:0]   issue_phys_rd_i,
    input  wire                         issue_target_live_i,
    output wire                         completion_valid_o,
    input  wire                         completion_ready_i,
    output wire [31:0]                  completion_value_o,
    output wire [TAG_WIDTH-1:0]         completion_rob_tag_o,
    output wire [PHYS_ADDR_WIDTH-1:0]   completion_phys_rd_o,
    output wire                         completion_rd_we_o,
    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i
);
    reg pending_valid;
    reg [`RV32IM_OP_WIDTH-1:0] pending_op;
    reg [31:0] pending_src1, pending_src2;
    reg [TAG_WIDTH-1:0] pending_tag;
    reg [PHYS_ADDR_WIDTH-1:0] pending_phys;
    reg pending_live;
    wire issue_is_mul = (issue_op_i == `RV32IM_OP_MUL) || (issue_op_i == `RV32IM_OP_MULH) ||
        (issue_op_i == `RV32IM_OP_MULHSU) || (issue_op_i == `RV32IM_OP_MULHU);
    wire issue_is_div = (issue_op_i == `RV32IM_OP_DIV) || (issue_op_i == `RV32IM_OP_DIVU) ||
        (issue_op_i == `RV32IM_OP_REM) || (issue_op_i == `RV32IM_OP_REMU);
    wire mul_req_valid = pending_valid && ((pending_op == `RV32IM_OP_MUL) || (pending_op == `RV32IM_OP_MULH) ||
        (pending_op == `RV32IM_OP_MULHSU) || (pending_op == `RV32IM_OP_MULHU));
    wire div_req_valid = pending_valid && ((pending_op == `RV32IM_OP_DIV) || (pending_op == `RV32IM_OP_DIVU) ||
        (pending_op == `RV32IM_OP_REM) || (pending_op == `RV32IM_OP_REMU));
    wire mul_req_ready, div_req_ready;
    wire mul_resp_valid, div_resp_valid;
    wire [31:0] mul_resp_value, div_resp_value;
    wire [TAG_WIDTH-1:0] mul_resp_tag, div_resp_tag;
    wire [PHYS_ADDR_WIDTH-1:0] mul_resp_phys, div_resp_phys;
    wire mul_resp_rd_we, div_resp_rd_we;
    wire mul_resp_ready = completion_ready_i;
    wire div_resp_ready = completion_ready_i && !mul_resp_valid;

    assign issue_ready_o = !flush_i && !pending_valid && (issue_is_mul || issue_is_div);
    assign completion_valid_o = mul_resp_valid || div_resp_valid;
    assign completion_value_o = mul_resp_valid ? mul_resp_value : div_resp_value;
    assign completion_rob_tag_o = mul_resp_valid ? mul_resp_tag : div_resp_tag;
    assign completion_phys_rd_o = mul_resp_valid ? mul_resp_phys : div_resp_phys;
    assign completion_rd_we_o = mul_resp_valid ? mul_resp_rd_we : div_resp_rd_we;

    generate
        if (MUL_IMPL == 0) begin : gen_wallace_multiplier
            rv32m_multiplier #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH)) multiplier (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .req_valid_i(mul_req_valid), .req_ready_o(mul_req_ready),
                .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2), .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys), .req_target_live_i(pending_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_resp_ready), .resp_value_o(mul_resp_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_resp_rd_we), .live_tag_valid_i(live_tag_valid_i), .live_tag_i(live_tag_i)
            );
        end else begin : gen_radix4_multiplier
            rv32m_multiplier_radix4 #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH)) multiplier (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .req_valid_i(mul_req_valid), .req_ready_o(mul_req_ready),
                .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2), .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys), .req_target_live_i(pending_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_resp_ready), .resp_value_o(mul_resp_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_resp_rd_we), .live_tag_valid_i(live_tag_valid_i), .live_tag_i(live_tag_i)
            );
        end
    endgenerate
    rv32m_divider #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH)) divider (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .req_valid_i(div_req_valid), .req_ready_o(div_req_ready),
        .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2), .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys), .req_target_live_i(pending_live),
        .resp_valid_o(div_resp_valid), .resp_ready_i(div_resp_ready), .resp_value_o(div_resp_value), .resp_rob_tag_o(div_resp_tag), .resp_phys_rd_o(div_resp_phys), .resp_rd_we_o(div_resp_rd_we), .live_tag_valid_i(live_tag_valid_i), .live_tag_i(live_tag_i)
    );

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            pending_valid <= 1'b0;
            pending_op <= 0;
            pending_src1 <= 0;
            pending_src2 <= 0;
            pending_tag <= 0;
            pending_phys <= 0;
            pending_live <= 0;
        end else begin
            if (pending_valid && ((mul_req_valid && mul_req_ready) || (div_req_valid && div_req_ready)))
                pending_valid <= 1'b0;
            if (issue_valid_i && issue_ready_o) begin
                pending_valid <= 1'b1;
                pending_op <= issue_op_i;
                pending_src1 <= issue_src1_i;
                pending_src2 <= issue_src2_i;
                pending_tag <= issue_rob_tag_i;
                pending_phys <= issue_phys_rd_i;
                pending_live <= issue_target_live_i;
            end
        end
    end
endmodule
