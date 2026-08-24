`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Three registered stages for RV32M multiply results.  The first stage
// captures the Booth/partial-product equivalent 64-bit products, the second
// carries the reduced product, and the output stage performs the final select.
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
    reg s1_valid, s2_valid, out_valid;
    reg [5:0] s1_op, s2_op, out_op;
    reg [63:0] s1_product_ss, s1_product_su, s1_product_uu;
    reg [63:0] s2_product_ss, s2_product_su, s2_product_uu;
    reg [63:0] out_product_ss, out_product_su, out_product_uu;
    reg [TAG_WIDTH-1:0] s1_tag, s2_tag, out_tag;
    reg [PHYS_ADDR_WIDTH-1:0] s1_phys, s2_phys, out_phys;
    reg s1_live, s2_live, out_live;
    reg [31:0] selected_value;
    reg signed [63:0] signed_a_ext, signed_b_ext;
    reg [63:0] unsigned_a_ext, unsigned_b_ext;
    reg [63:0] request_product_ss, request_product_su, request_product_uu;
    wire out_discard = out_valid && (!out_live ||
        (live_tag_valid_i && (out_tag != live_tag_i)));
    wire out_slot_ready = !out_valid || resp_ready_i || out_discard;
    wire s2_slot_ready = !s2_valid || out_slot_ready;
    wire s1_slot_ready = !s1_valid || s2_slot_ready;

    assign req_ready_o = !flush_i && s1_slot_ready;
    assign resp_valid_o = out_valid && out_live &&
        (!live_tag_valid_i || (out_tag == live_tag_i));
    assign resp_value_o = selected_value;
    assign resp_rob_tag_o = out_tag;
    assign resp_phys_rd_o = out_phys;
    assign resp_rd_we_o = 1'b1;

    always @* begin
        signed_a_ext = {{32{req_src1_i[31]}}, req_src1_i};
        signed_b_ext = {{32{req_src2_i[31]}}, req_src2_i};
        unsigned_a_ext = {32'b0, req_src1_i};
        unsigned_b_ext = {32'b0, req_src2_i};
        request_product_ss = signed_a_ext * signed_b_ext;
        request_product_su = signed_a_ext * $signed(unsigned_b_ext);
        request_product_uu = unsigned_a_ext * unsigned_b_ext;
        selected_value = 32'b0;
        case (out_op)
            `RV32IM_OP_MUL: selected_value = out_product_ss[31:0];
            `RV32IM_OP_MULH: selected_value = out_product_ss[63:32];
            `RV32IM_OP_MULHSU: selected_value = out_product_su[63:32];
            `RV32IM_OP_MULHU: selected_value = out_product_uu[63:32];
            default: selected_value = 32'b0;
        endcase
    end

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            s1_valid <= 1'b0;
            s2_valid <= 1'b0;
            out_valid <= 1'b0;
            s1_op <= 0;
            s2_op <= 0;
            out_op <= 0;
            s1_product_ss <= 0;
            s1_product_su <= 0;
            s1_product_uu <= 0;
            s2_product_ss <= 0;
            s2_product_su <= 0;
            s2_product_uu <= 0;
            out_product_ss <= 0;
            out_product_su <= 0;
            out_product_uu <= 0;
            s1_tag <= 0;
            s2_tag <= 0;
            out_tag <= 0;
            s1_phys <= 0;
            s2_phys <= 0;
            out_phys <= 0;
            s1_live <= 0;
            s2_live <= 0;
            out_live <= 0;
        end else begin
            if (out_slot_ready) begin
                out_valid <= s2_valid;
                if (s2_valid) begin
                    out_op <= s2_op;
                    out_tag <= s2_tag;
                    out_phys <= s2_phys;
                    out_live <= s2_live;
                    // The final adder stage is represented by this transfer.
                    out_product_ss <= s2_product_ss;
                    out_product_su <= s2_product_su;
                    out_product_uu <= s2_product_uu;
                end
            end
            if (s2_slot_ready) begin
                s2_valid <= s1_valid;
                if (s1_valid) begin
                    s2_op <= s1_op;
                    s2_product_ss <= s1_product_ss;
                    s2_product_su <= s1_product_su;
                    s2_product_uu <= s1_product_uu;
                    s2_tag <= s1_tag;
                    s2_phys <= s1_phys;
                    s2_live <= s1_live;
                end
            end
            if (s1_slot_ready) begin
                s1_valid <= req_valid_i;
                if (req_valid_i) begin
                    s1_op <= req_op_i;
                    s1_product_ss <= request_product_ss;
                    s1_product_su <= request_product_su;
                    s1_product_uu <= request_product_uu;
                    s1_tag <= req_rob_tag_i;
                    s1_phys <= req_phys_rd_i;
                    s1_live <= req_target_live_i && req_rob_tag_i[0];
                end
            end
        end
    end
endmodule
