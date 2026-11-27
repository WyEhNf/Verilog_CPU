`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Two genuinely split arithmetic stages; one request per cycle when unstalled.
module rv32m_multiplier #(
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
    function automatic [63:0] csa_sum3;
        input [63:0] a,b,c;
        begin csa_sum3=a^b^c; end
    endfunction
    function automatic [63:0] csa_carry3;
        input [63:0] a,b,c;
        begin csa_carry3=((a&b)|(a&c)|(b&c))<<1; end
    endfunction

    // A and B are signed only where the requested high half requires it.
    // The 33rd sign bit also represents every unsigned 32-bit operand.
    // Seventeen radix-4 digits cover B. Negative rows use bitwise complement
    // plus one shared correction vector, avoiding per-row negate adders.
    wire signed_a=(req_op_i==`RV32IM_OP_MULH || req_op_i==`RV32IM_OP_MULHSU);
    wire signed_b=(req_op_i==`RV32IM_OP_MULH);
    wire [32:0] extended_a={signed_a && req_src1_i[31],req_src1_i};
    wire [34:0] booth_bits={{2{signed_b && req_src2_i[31]}},req_src2_i,1'b0};
    wire [5*33-1:0] multiplicand_views;
    rv32_frequency_control_tree #(.WIDTH(33),.LEAVES(5)) multiplicand_tree (
        .signal_i(extended_a),.views_o(multiplicand_views));
    wire [63:0] pp [0:17];
    wire [16:0] negative_corrections;
    genvar row;
    generate for(row=0;row<17;row=row+1) begin:g_booth_row
        wire [2:0] code=booth_bits[2*row +: 3];
        wire one=code[0] ^ code[1];
        wire two=(code[0]==code[1]) && (code[2]!=code[1]);
        wire negative=code[2] && (one || two);
        wire [2:0] one_views,two_views;
        wire [3:0] negative_views;
        wire [32:0] local_a=multiplicand_views[(row/4)*33 +: 33];
        wire [33:0] once={local_a[32],local_a};
        wire [33:0] twice={local_a,1'b0};
        wire [33:0] relative_row;
        localparam integer EXTENDED_BITS=(30-2*row>0)?30-2*row:0;
        localparam integer SIGN_DOMAINS=(EXTENDED_BITS+7)/8;
        rv32_frequency_control_tree #(.LEAVES(3)) one_tree (
            .signal_i(one),.views_o(one_views));
        rv32_frequency_control_tree #(.LEAVES(3)) two_tree (
            .signal_i(two),.views_o(two_views));
        rv32_frequency_control_tree #(.LEAVES(4)) negative_tree (
            .signal_i(negative),.views_o(negative_views));
        assign negative_corrections[row]=negative_views[3];
        for(genvar relative_bit=0;relative_bit<34;relative_bit=relative_bit+1) begin:g_relative_bit
            assign relative_row[relative_bit]=
                ((one_views[relative_bit/16] && once[relative_bit]) |
                 (two_views[relative_bit/16] && twice[relative_bit])) ^ negative_views[relative_bit/16];
        end
        if(SIGN_DOMAINS>0) begin:g_sign_extension
            wire [SIGN_DOMAINS-1:0] sign_views;
            // Each repeated sign feeds <=8 row bits, each used in CSA logic.
            rv32_frequency_control_tree #(.LEAVES(SIGN_DOMAINS)) sign_tree (
                .signal_i(relative_row[33]),.views_o(sign_views));
            for(genvar product_bit=0;product_bit<64;product_bit=product_bit+1) begin:g_bit
                if(product_bit<2*row) begin : g_named_89_38
assign pp[row][product_bit]=1'b0;
end
                else if(product_bit<2*row+34)
                    begin : g_named_91_20
assign pp[row][product_bit]=relative_row[product_bit-2*row];
end
                else begin : g_named_92_21
assign pp[row][product_bit]=sign_views[(product_bit-2*row-34)/8];
end
            end
        end else begin:g_no_sign_extension
            for(genvar product_bit=0;product_bit<64;product_bit=product_bit+1) begin:g_bit
                if(product_bit<2*row) begin : g_named_96_38
assign pp[row][product_bit]=1'b0;
end
                else begin : g_named_97_21
assign pp[row][product_bit]=relative_row[product_bit-2*row];
end
            end
        end
    end endgenerate
    generate for(genvar correction_bit=0;correction_bit<64;correction_bit=correction_bit+1) begin:g_correction_bit
        if(correction_bit<=32 && correction_bit%2==0)
            begin : g_named_103_12
assign pp[17][correction_bit]=negative_corrections[correction_bit/2];
end
        else begin : g_named_104_13
assign pp[17][correction_bit]=1'b0;
end
    end endgenerate
    wire [63:0] first_reduce1 [0:11];
    assign first_reduce1[0]=csa_sum3(pp[0],pp[1],pp[2]);
    assign first_reduce1[1]=csa_carry3(pp[0],pp[1],pp[2]);
    assign first_reduce1[2]=csa_sum3(pp[3],pp[4],pp[5]);
    assign first_reduce1[3]=csa_carry3(pp[3],pp[4],pp[5]);
    assign first_reduce1[4]=csa_sum3(pp[6],pp[7],pp[8]);
    assign first_reduce1[5]=csa_carry3(pp[6],pp[7],pp[8]);
    assign first_reduce1[6]=csa_sum3(pp[9],pp[10],pp[11]);
    assign first_reduce1[7]=csa_carry3(pp[9],pp[10],pp[11]);
    assign first_reduce1[8]=csa_sum3(pp[12],pp[13],pp[14]);
    assign first_reduce1[9]=csa_carry3(pp[12],pp[13],pp[14]);
    assign first_reduce1[10]=csa_sum3(pp[15],pp[16],pp[17]);
    assign first_reduce1[11]=csa_carry3(pp[15],pp[16],pp[17]);
    wire [63:0] first_reduce2 [0:7];
    assign first_reduce2[0]=csa_sum3(first_reduce1[0],first_reduce1[1],first_reduce1[2]);
    assign first_reduce2[1]=csa_carry3(first_reduce1[0],first_reduce1[1],first_reduce1[2]);
    assign first_reduce2[2]=csa_sum3(first_reduce1[3],first_reduce1[4],first_reduce1[5]);
    assign first_reduce2[3]=csa_carry3(first_reduce1[3],first_reduce1[4],first_reduce1[5]);
    assign first_reduce2[4]=csa_sum3(first_reduce1[6],first_reduce1[7],first_reduce1[8]);
    assign first_reduce2[5]=csa_carry3(first_reduce1[6],first_reduce1[7],first_reduce1[8]);
    assign first_reduce2[6]=csa_sum3(first_reduce1[9],first_reduce1[10],first_reduce1[11]);
    assign first_reduce2[7]=csa_carry3(first_reduce1[9],first_reduce1[10],first_reduce1[11]);
    wire [63:0] first_rows [0:5];
    assign first_rows[0]=csa_sum3(first_reduce2[0],first_reduce2[1],first_reduce2[2]);
    assign first_rows[1]=csa_carry3(first_reduce2[0],first_reduce2[1],first_reduce2[2]);
    assign first_rows[2]=csa_sum3(first_reduce2[3],first_reduce2[4],first_reduce2[5]);
    assign first_rows[3]=csa_carry3(first_reduce2[3],first_reduce2[4],first_reduce2[5]);
    assign first_rows[4]=first_reduce2[6];
    assign first_rows[5]=first_reduce2[7];
    reg s1_valid;
    reg [63:0] s1_rows [0:5];
    wire [OP_WIDTH-1:0] s1_op;
    wire [TAG_WIDTH-1:0] s1_tag;
    wire [PHYS_ADDR_WIDTH-1:0] s1_phys;
    wire s1_live;
    reg s2_valid;
    reg [63:0] s2_rows [0:1];
    wire [OP_WIDTH-1:0] s2_op;
    wire [TAG_WIDTH-1:0] s2_tag;
    wire [PHYS_ADDR_WIDTH-1:0] s2_phys;
    wire s2_live;
    reg out_valid;
    wire [31:0] out_value;
    wire [TAG_WIDTH-1:0] out_tag;
    wire [PHYS_ADDR_WIDTH-1:0] out_phys;
    wire out_live;
    wire [3*RECOVERY_WIDTH-1:0] recovery_views;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(3)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
    assign occupied_o=s1_valid || s2_valid || out_valid;
    wire s1_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) s1_cancel_guard (
        .packet_i(recovery_views[0*RECOVERY_WIDTH +: RECOVERY_WIDTH]),.active_i(s1_valid),.tag_i(s1_tag),.cancel_o(s1_cancel));
    wire s2_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) s2_cancel_guard (
        .packet_i(recovery_views[1*RECOVERY_WIDTH +: RECOVERY_WIDTH]),.active_i(s2_valid),.tag_i(s2_tag),.cancel_o(s2_cancel));
    wire out_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) out_cancel_guard (
        .packet_i(recovery_views[2*RECOVERY_WIDTH +: RECOVERY_WIDTH]),.active_i(out_valid),.tag_i(out_tag),.cancel_o(out_cancel));
    wire request_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) request_cancel_guard (
        .packet_i(recovery_packet_i),.active_i(req_valid_i),.tag_i(req_rob_tag_i),.cancel_o(request_cancel));
    wire s1_discard=s1_valid && (s1_cancel || !s1_live ||
        (live_tag_valid_i && s1_tag!=live_tag_i));
    wire out_discard=out_valid && (out_cancel || !out_live ||
        (live_tag_valid_i && out_tag!=live_tag_i));
    wire out_ready=!out_valid || resp_ready_i || out_discard;
    wire s2_discard=s2_valid && (s2_cancel || !s2_live ||
        (live_tag_valid_i && s2_tag!=live_tag_i));
    wire s2_ready=!s2_valid || out_ready || s2_discard;
    wire s1_ready=!s1_valid || s2_ready || s1_discard;
    wire [8:0] s2_write_domains;
    rv32_frequency_control_tree #(.LEAVES(9)) s2_write_tree (
        .signal_i(s2_ready && s1_valid && !s1_discard),.views_o(s2_write_domains));
    wire [24:0] s1_write_domains;
    // A single ready/valid gate must not directly drive 384 payload hold muxes.
    rv32_frequency_control_tree #(.LEAVES(25)) s1_write_tree (
        .signal_i(req_valid_i && req_ready_o),.views_o(s1_write_domains));
    wire payload_active=!reset_i && !flush_i;
    wire out_write=payload_active && out_ready && s2_valid && !s2_discard;
    assign req_ready_o=!flush_i && !request_cancel && s1_ready;
    assign resp_valid_o=out_valid && !out_cancel && out_live &&
        (!live_tag_valid_i || out_tag==live_tag_i);
    assign resp_value_o=out_value;
    assign resp_rob_tag_o=out_tag;
    assign resp_phys_rd_o=out_phys;
    assign resp_rd_we_o=1'b1;
    wire [63:0] second_reduce1 [0:3];
    assign second_reduce1[0]=csa_sum3(s1_rows[0],s1_rows[1],s1_rows[2]);
    assign second_reduce1[1]=csa_carry3(s1_rows[0],s1_rows[1],s1_rows[2]);
    assign second_reduce1[2]=csa_sum3(s1_rows[3],s1_rows[4],s1_rows[5]);
    assign second_reduce1[3]=csa_carry3(s1_rows[3],s1_rows[4],s1_rows[5]);
    wire [63:0] second_reduce2 [0:2];
    assign second_reduce2[0]=csa_sum3(second_reduce1[0],second_reduce1[1],second_reduce1[2]);
    assign second_reduce2[1]=csa_carry3(second_reduce1[0],second_reduce1[1],second_reduce1[2]);
    assign second_reduce2[2]=second_reduce1[3];
    wire [63:0] second_rows [0:1];
    assign second_rows[0]=csa_sum3(second_reduce2[0],second_reduce2[1],second_reduce2[2]);
    assign second_rows[1]=csa_carry3(second_reduce2[0],second_reduce2[1],second_reduce2[2]);
    // The final CPA starts from two registered rows, never from the same
    // cycle's three CSA layers. Both rows retain the exact modulo-2^64 sum.
    wire [63:0] product;
    rv32_frequency_add64_select final_add (
        .lhs_i(s2_rows[0]),.rhs_i(s2_rows[1]),.sum_o(product));
    generate for(row=0;row<2;row=row+1) begin:g_s2_storage
        always @(posedge clk_i) begin
            if(s2_write_domains[4*row]) s2_rows[row][15:0]<=second_rows[row][15:0];
            if(s2_write_domains[4*row+1]) s2_rows[row][31:16]<=second_rows[row][31:16];
            if(s2_write_domains[4*row+2]) s2_rows[row][47:32]<=second_rows[row][47:32];
            if(s2_write_domains[4*row+3]) s2_rows[row][63:48]<=second_rows[row][63:48];
        end
    end endgenerate
    // Invalid payload may be overwritten even on a reset edge. Valid bits
    // below discard it; each newly valid transaction has all fields written.
    generate for(row=0;row<6;row=row+1) begin:g_s1_storage
        always @(posedge clk_i) begin
            if(s1_write_domains[4*row]) s1_rows[row][15:0]<=first_rows[row][15:0];
            if(s1_write_domains[4*row+1]) s1_rows[row][31:16]<=first_rows[row][31:16];
            if(s1_write_domains[4*row+2]) s1_rows[row][47:32]<=first_rows[row][47:32];
            if(s1_write_domains[4*row+3]) s1_rows[row][63:48]<=first_rows[row][63:48];
        end
    end endgenerate
    localparam integer MUL_META_WIDTH=OP_WIDTH+TAG_WIDTH+PHYS_ADDR_WIDTH+1;
    wire [MUL_META_WIDTH-1:0] s1_metadata,s2_metadata;
    assign {s1_op,s1_tag,s1_phys,s1_live}=s1_metadata;
    assign {s2_op,s2_tag,s2_phys,s2_live}=s2_metadata;
    rv32_frequency_word_bank #(.WIDTH(MUL_META_WIDTH)) s1_metadata_owner (
        .clk_i(clk_i),.write_i(payload_active && s1_ready && s1_write_domains[24]),
        .data_i({req_op_i,req_rob_tag_i,req_phys_rd_i,req_target_live_i && req_rob_tag_i[0]}),
        .data_o(s1_metadata));
    rv32_frequency_word_bank #(.WIDTH(MUL_META_WIDTH)) s2_metadata_owner (
        .clk_i(clk_i),.write_i(payload_active && s2_write_domains[8]),
        .data_i(s1_metadata),.data_o(s2_metadata));
    wire [TAG_WIDTH+PHYS_ADDR_WIDTH:0] out_metadata;
    assign {out_tag,out_phys,out_live}=out_metadata;
    rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH+PHYS_ADDR_WIDTH+1)) out_metadata_owner (
        .clk_i(clk_i),.write_i(out_write),.data_i({s2_tag,s2_phys,s2_live}),.data_o(out_metadata));
    wire [31:0] out_next_value;
    wire unused_result_select_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2),.PRIORITY(0)) out_value_selector (
        .events_i({(s2_op==`RV32IM_OP_MULH || s2_op==`RV32IM_OP_MULHSU || s2_op==`RV32IM_OP_MULHU),
                   (s2_op==`RV32IM_OP_MUL)}),
        .values_i({product[63:32],product[31:0]}),
        .write_o(unused_result_select_write),.value_o(out_next_value));
    rv32_frequency_word_bank #(.WIDTH(32)) out_value_owner (
        .clk_i(clk_i),.write_i(out_write),.data_i(out_next_value),.data_o(out_value));

    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            s1_valid<=1'b0;
            s2_valid<=1'b0;
            out_valid<=1'b0;
        end else begin
            if(s1_ready) begin
                s1_valid<=req_valid_i && req_ready_o;
                // Metadata owner below captures on this same qualified edge.
            end
            if(s2_ready) s2_valid<=s1_valid && !s1_discard;
            // Metadata owner below captures on the original transfer edge.
            if(out_ready) begin
                out_valid<=s2_valid && !s2_discard;
            end
        end
    end
endmodule
