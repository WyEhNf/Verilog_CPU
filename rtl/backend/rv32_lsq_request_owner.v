`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Construct one LSQ request with local control loads. Admission and partial
// forwarding predicates never directly qualify a wide packet or barrel shift.
// Each externally visible payload still equals zero when no request is sent.
// Forwarding temporaries also retain their original admission/load gating.
(* keep_hierarchy = 1 *)
module rv32_lsq_request_owner #(
    parameter integer TAG_WIDTH=17,ROB_TAG_WIDTH=17
) (
    input wire flush_i,recovery_i,found_i,wait_i,load_i,ready_i,
    input wire [1:0] size_i,
    input wire unsigned_i,
    input wire [31:0] address_i,store_data_i,forward_data_i,
    input wire [3:0] store_mask_i,forward_mask_i,
    input wire [ROB_TAG_WIDTH-1:0] rob_tag_i,
    input wire [TAG_WIDTH-1:0] lsq_tag_i,
    output wire valid_o,load_o,store_o,unsigned_o,fire_o,
    output wire [1:0] size_o,
    output wire [15:0] mask_o,
    output wire [127:0] data_o,
    output wire [ROB_TAG_WIDTH-1:0] rob_tag_o,
    output wire [TAG_WIDTH-1:0] lsq_tag_o,
    output wire [3:0] target_mask_o,forward_mask_o,
    output wire [31:0] forward_data_o
);
    wire unused_address_i_bits = &{1'b0, address_i};

    localparam integer ROB_WORDS=(ROB_TAG_WIDTH+15)/16;
    localparam integer LSQ_WORDS=(TAG_WIDTH+15)/16;
    localparam integer ROB_START=3,LSQ_START=ROB_START+ROB_WORDS;
    localparam integer DATA_START=LSQ_START+LSQ_WORDS;
    localparam integer VALID_LEAVES=DATA_START+8;
    wire admitted=!flush_i && !recovery_i && found_i && !wait_i;
    wire admitted_load=admitted && load_i;
    function automatic [3:0] decode_access_mask;
        input [1:0] size;
        begin
            case(size)
                2'd0: decode_access_mask=4'b0001;
                2'd1: decode_access_mask=4'b0011;
                default: decode_access_mask=4'b1111;
            endcase
        end
    endfunction
    wire [3:0] access_mask=decode_access_mask(size_i);
    wire incomplete_forward=(forward_mask_i & access_mask)!=access_mask;
    wire request_valid=admitted && (!load_i || incomplete_forward);
    wire [2:0] forward_enable;
    wire [VALID_LEAVES-1:0] valid_views;
    wire [3:0] load_views;
    wire [31:0] relative_data;
    wire [127:0] inserted_data;
    wire [3:0] relative_mask=load_views[0]?
        (access_mask & ~forward_mask_i):store_mask_i;
    wire [15:0] inserted_mask={12'b0,relative_mask} << address_i[3:0];
    rv32_frequency_control_tree #(.LEAVES(3)) forward_tree (
        .signal_i(admitted_load),.views_o(forward_enable));
    rv32_frequency_control_tree #(.LEAVES(VALID_LEAVES)) valid_tree (
        .signal_i(request_valid),.views_o(valid_views));
    rv32_frequency_control_tree #(.LEAVES(4)) source_tree (
        .signal_i(load_i),.views_o(load_views));
    // A leaf owns eight mask bits, sixteen data bits, or at most five flags.
    assign target_mask_o={4{forward_enable[0]}} & access_mask;
    assign forward_mask_o={4{forward_enable[0]}} & forward_mask_i;
    assign valid_o=request_valid;
    assign fire_o=valid_views[0] && ready_i;
    assign load_o=valid_views[1] && load_views[3];
    assign store_o=valid_views[1] && !load_views[3];
    assign size_o={2{valid_views[1]}} & size_i;
    assign unsigned_o=valid_views[1] && load_views[3] && unsigned_i;
    assign mask_o={16{valid_views[2]}} & inserted_mask;
    genvar word;
    generate
        for(word=0;word<2;word=word+1) begin:g_relative
            assign forward_data_o[word*16 +: 16]=
                {16{forward_enable[word+1]}} & forward_data_i[word*16 +: 16];
            assign relative_data[word*16 +: 16]=load_views[word+1]?
                forward_data_i[word*16 +: 16]:store_data_i[word*16 +: 16];
        end
        for(word=0;word<ROB_WORDS;word=word+1) begin:g_rob_tag
            localparam integer LOW=word*16;
            localparam integer BITS=(ROB_TAG_WIDTH-LOW>=16)?16:ROB_TAG_WIDTH-LOW;
            assign rob_tag_o[LOW +: BITS]={BITS{valid_views[ROB_START+word]}} & rob_tag_i[LOW +: BITS];
        end
        for(word=0;word<LSQ_WORDS;word=word+1) begin:g_lsq_tag
            localparam integer LOW=word*16;
            localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
            assign lsq_tag_o[LOW +: BITS]={BITS{valid_views[LSQ_START+word]}} & lsq_tag_i[LOW +: BITS];
        end
        for(word=0;word<8;word=word+1) begin:g_line
            assign data_o[word*16 +: 16]=
                {16{valid_views[DATA_START+word]}} & inserted_data[word*16 +: 16];
        end
    endgenerate
    rv32_frequency_line_insert32 insertion (
        .value_i(relative_data),.offset_i(address_i[3:0]),.line_o(inserted_data));
endmodule
