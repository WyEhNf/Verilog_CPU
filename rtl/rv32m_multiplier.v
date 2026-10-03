`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Two genuinely split arithmetic stages; one request per cycle when unstalled.
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
        input [63:0] a,b,c;
        begin csa_sum3=a^b^c; end
    endfunction
    function [63:0] csa_carry3;
        input [63:0] a,b,c;
        begin csa_carry3=((a&b)|(a&c)|(b&c))<<1; end
    endfunction

    // Signed high halves are corrected in carry-save form, modulo 2^64:
    // U=A*B; signed correction is -(Anegative*B + Bnegative*A)<<32.
    // Each negative term is {~operand,0} plus 1<<32. No absolute-value
    // carry-propagate adder precedes the partial-product tree.
    wire neg_a=((req_op_i==`RV32IM_OP_MULH)||
                (req_op_i==`RV32IM_OP_MULHSU)) && req_src1_i[31];
    wire neg_b=(req_op_i==`RV32IM_OP_MULH) && req_src2_i[31];
    wire [63:0] pp [0:35];
    genvar row;
    generate for(row=0;row<32;row=row+1) begin:g_pp
        assign pp[row]=req_src2_i[row]?({32'b0,req_src1_i}<<row):64'b0;
    end endgenerate
    assign pp[32]=neg_a?{~req_src2_i,32'b0}:64'b0;
    assign pp[33]=neg_a?64'h0000000100000000:64'b0;
    assign pp[34]=neg_b?{~req_src1_i,32'b0}:64'b0;
    assign pp[35]=neg_b?64'h0000000100000000:64'b0;
    wire [63:0] l1 [0:23];
    assign l1[0]=csa_sum3(pp[0],pp[1],pp[2]);
    assign l1[1]=csa_carry3(pp[0],pp[1],pp[2]);
    assign l1[2]=csa_sum3(pp[3],pp[4],pp[5]);
    assign l1[3]=csa_carry3(pp[3],pp[4],pp[5]);
    assign l1[4]=csa_sum3(pp[6],pp[7],pp[8]);
    assign l1[5]=csa_carry3(pp[6],pp[7],pp[8]);
    assign l1[6]=csa_sum3(pp[9],pp[10],pp[11]);
    assign l1[7]=csa_carry3(pp[9],pp[10],pp[11]);
    assign l1[8]=csa_sum3(pp[12],pp[13],pp[14]);
    assign l1[9]=csa_carry3(pp[12],pp[13],pp[14]);
    assign l1[10]=csa_sum3(pp[15],pp[16],pp[17]);
    assign l1[11]=csa_carry3(pp[15],pp[16],pp[17]);
    assign l1[12]=csa_sum3(pp[18],pp[19],pp[20]);
    assign l1[13]=csa_carry3(pp[18],pp[19],pp[20]);
    assign l1[14]=csa_sum3(pp[21],pp[22],pp[23]);
    assign l1[15]=csa_carry3(pp[21],pp[22],pp[23]);
    assign l1[16]=csa_sum3(pp[24],pp[25],pp[26]);
    assign l1[17]=csa_carry3(pp[24],pp[25],pp[26]);
    assign l1[18]=csa_sum3(pp[27],pp[28],pp[29]);
    assign l1[19]=csa_carry3(pp[27],pp[28],pp[29]);
    assign l1[20]=csa_sum3(pp[30],pp[31],pp[32]);
    assign l1[21]=csa_carry3(pp[30],pp[31],pp[32]);
    assign l1[22]=csa_sum3(pp[33],pp[34],pp[35]);
    assign l1[23]=csa_carry3(pp[33],pp[34],pp[35]);
    wire [63:0] l2 [0:15];
    assign l2[0]=csa_sum3(l1[0],l1[1],l1[2]);
    assign l2[1]=csa_carry3(l1[0],l1[1],l1[2]);
    assign l2[2]=csa_sum3(l1[3],l1[4],l1[5]);
    assign l2[3]=csa_carry3(l1[3],l1[4],l1[5]);
    assign l2[4]=csa_sum3(l1[6],l1[7],l1[8]);
    assign l2[5]=csa_carry3(l1[6],l1[7],l1[8]);
    assign l2[6]=csa_sum3(l1[9],l1[10],l1[11]);
    assign l2[7]=csa_carry3(l1[9],l1[10],l1[11]);
    assign l2[8]=csa_sum3(l1[12],l1[13],l1[14]);
    assign l2[9]=csa_carry3(l1[12],l1[13],l1[14]);
    assign l2[10]=csa_sum3(l1[15],l1[16],l1[17]);
    assign l2[11]=csa_carry3(l1[15],l1[16],l1[17]);
    assign l2[12]=csa_sum3(l1[18],l1[19],l1[20]);
    assign l2[13]=csa_carry3(l1[18],l1[19],l1[20]);
    assign l2[14]=csa_sum3(l1[21],l1[22],l1[23]);
    assign l2[15]=csa_carry3(l1[21],l1[22],l1[23]);
    wire [63:0] l3 [0:10];
    assign l3[0]=csa_sum3(l2[0],l2[1],l2[2]);
    assign l3[1]=csa_carry3(l2[0],l2[1],l2[2]);
    assign l3[2]=csa_sum3(l2[3],l2[4],l2[5]);
    assign l3[3]=csa_carry3(l2[3],l2[4],l2[5]);
    assign l3[4]=csa_sum3(l2[6],l2[7],l2[8]);
    assign l3[5]=csa_carry3(l2[6],l2[7],l2[8]);
    assign l3[6]=csa_sum3(l2[9],l2[10],l2[11]);
    assign l3[7]=csa_carry3(l2[9],l2[10],l2[11]);
    assign l3[8]=csa_sum3(l2[12],l2[13],l2[14]);
    assign l3[9]=csa_carry3(l2[12],l2[13],l2[14]);
    assign l3[10]=l2[15];
    wire [63:0] l4 [0:7];
    assign l4[0]=csa_sum3(l3[0],l3[1],l3[2]);
    assign l4[1]=csa_carry3(l3[0],l3[1],l3[2]);
    assign l4[2]=csa_sum3(l3[3],l3[4],l3[5]);
    assign l4[3]=csa_carry3(l3[3],l3[4],l3[5]);
    assign l4[4]=csa_sum3(l3[6],l3[7],l3[8]);
    assign l4[5]=csa_carry3(l3[6],l3[7],l3[8]);
    assign l4[6]=l3[9];
    assign l4[7]=l3[10];
    reg s1_valid;
    reg [63:0] s1_rows [0:7];
    reg [OP_WIDTH-1:0] s1_op;
    reg [TAG_WIDTH-1:0] s1_tag;
    reg [PHYS_ADDR_WIDTH-1:0] s1_phys;
    reg s1_live;
    reg out_valid;
    reg [31:0] out_value;
    reg [TAG_WIDTH-1:0] out_tag;
    reg [PHYS_ADDR_WIDTH-1:0] out_phys;
    reg out_live;
    wire s1_discard=s1_valid && (!s1_live ||
        (live_tag_valid_i && s1_tag!=live_tag_i));
    wire out_discard=out_valid && (!out_live ||
        (live_tag_valid_i && out_tag!=live_tag_i));
    wire out_ready=!out_valid || resp_ready_i || out_discard;
    wire s1_ready=!s1_valid || out_ready || s1_discard;
    wire [8:0] s1_write_domains;
    wire [1:0] out_write_domains;
    // A single ready/valid gate must not directly drive 512 payload hold muxes.
    rv32_frequency_control_tree #(.LEAVES(9)) s1_write_tree (
        .signal_i(req_valid_i && req_ready_o),.views_o(s1_write_domains));
    rv32_frequency_control_tree #(.LEAVES(2)) out_write_tree (
        .signal_i(out_ready && s1_valid && !s1_discard),.views_o(out_write_domains));
    assign req_ready_o=!flush_i && s1_ready;
    assign resp_valid_o=out_valid && out_live &&
        (!live_tag_valid_i || out_tag==live_tag_i);
    assign resp_value_o=out_value;
    assign resp_rob_tag_o=out_tag;
    assign resp_phys_rd_o=out_phys;
    assign resp_rd_we_o=1'b1;
    wire [63:0] l5 [0:5];
    assign l5[0]=csa_sum3(s1_rows[0],s1_rows[1],s1_rows[2]);
    assign l5[1]=csa_carry3(s1_rows[0],s1_rows[1],s1_rows[2]);
    assign l5[2]=csa_sum3(s1_rows[3],s1_rows[4],s1_rows[5]);
    assign l5[3]=csa_carry3(s1_rows[3],s1_rows[4],s1_rows[5]);
    assign l5[4]=s1_rows[6];
    assign l5[5]=s1_rows[7];
    wire [63:0] l6 [0:3];
    assign l6[0]=csa_sum3(l5[0],l5[1],l5[2]);
    assign l6[1]=csa_carry3(l5[0],l5[1],l5[2]);
    assign l6[2]=csa_sum3(l5[3],l5[4],l5[5]);
    assign l6[3]=csa_carry3(l5[3],l5[4],l5[5]);
    wire [63:0] l7 [0:2];
    assign l7[0]=csa_sum3(l6[0],l6[1],l6[2]);
    assign l7[1]=csa_carry3(l6[0],l6[1],l6[2]);
    assign l7[2]=l6[3];
    wire [63:0] l8 [0:1];
    assign l8[0]=csa_sum3(l7[0],l7[1],l7[2]);
    assign l8[1]=csa_carry3(l7[0],l7[1],l7[2]);
    wire [63:0] product=l8[0]+l8[1];
    // Invalid payload may be overwritten even on a reset edge. Valid bits
    // below discard it; each newly valid transaction has all fields written.
    generate for(row=0;row<8;row=row+1) begin:g_s1_storage
        always @(posedge clk_i) if(s1_write_domains[row])
            s1_rows[row]<=l4[row];
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            s1_valid<=1'b0;
            out_valid<=1'b0;
        end else begin
            if(s1_ready) begin
                s1_valid<=req_valid_i && req_ready_o;
                if(s1_write_domains[8]) begin
                    s1_op<=req_op_i;
                    s1_tag<=req_rob_tag_i;
                    s1_phys<=req_phys_rd_i;
                    s1_live<=req_target_live_i && req_rob_tag_i[0];
                end
            end
            if(out_ready) begin
                out_valid<=s1_valid && !s1_discard;
            end
            if(out_write_domains[0]) begin
                    case(s1_op)
                        `RV32IM_OP_MUL: out_value<=product[31:0];
                        `RV32IM_OP_MULH,`RV32IM_OP_MULHSU,`RV32IM_OP_MULHU:
                            out_value<=product[63:32];
                        default: out_value<=32'b0;
                    endcase
            end
            if(out_write_domains[1]) begin
                    out_tag<=s1_tag;
                    out_phys<=s1_phys;
                    out_live<=s1_live;
            end
        end
    end
endmodule
