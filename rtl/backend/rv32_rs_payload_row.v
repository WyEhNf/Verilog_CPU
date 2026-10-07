`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Each row owns its final data writes. Wide metadata has no reset/flush
// feedback mux after its qualified and priced local write driver.
module rv32_rs_payload_row #(
    parameter integer OP_WIDTH=6,TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,
    parameter integer SOURCE_TAG_WIDTH=TAG_WIDTH,
    parameter integer STORE_DATA_WIDTH=32,METADATA_WIDTH=70,AGE_WIDTH=8,
    parameter integer PAYLOAD_WIDTH=272
) (
    input wire clk_i,reset_i,flush_i,kill_i,valid_i,issue_i,alloc_i,
    input wire [PAYLOAD_WIDTH-1:0] payload_i,
    input wire wake1_i,wake2_i,
    input wire [31:0] wake1_value_i,wake2_value_i,
    output reg target_live_o,
    output wire [OP_WIDTH-1:0] op_o,
    output wire [31:0] pc_o,
    output wire [31:0] src1_value_o,src2_value_o,
    output wire [TAG_WIDTH-1:0] rob_tag_o,
    output reg [SOURCE_TAG_WIDTH-1:0] src1_tag_o,src2_tag_o,
    output wire [PHYS_ADDR_WIDTH-1:0] phys_rd_o,
    output reg src1_ready_o,src2_ready_o,
    output wire [STORE_DATA_WIDTH-1:0] store_data_o,
    output wire [METADATA_WIDTH-1:0] metadata_o,
    output reg [AGE_WIDTH-1:0] age_o
);
    wire new_live,new_ready1,new_ready2;
    wire [OP_WIDTH-1:0] new_op;
    wire [31:0] new_pc,new_value1,new_value2;
    wire [TAG_WIDTH-1:0] new_tag;
    wire [SOURCE_TAG_WIDTH-1:0] new_tag1,new_tag2;
    wire [PHYS_ADDR_WIDTH-1:0] new_phys;
    wire [STORE_DATA_WIDTH-1:0] new_store;
    wire [METADATA_WIDTH-1:0] new_metadata;
    wire [AGE_WIDTH-1:0] new_age;
    assign {new_live,new_op,new_pc,new_tag,new_phys,new_value1,new_tag1,new_ready1,
            new_value2,new_tag2,new_ready2,new_store,new_metadata,new_age}=payload_i;
    wire allocation=!reset_i && !flush_i && alloc_i;
    wire wake_allowed=!reset_i && valid_i && (!flush_i || !kill_i);
    wire wake1_write=wake_allowed && !src1_ready_o && wake1_i;
    wire wake2_write=wake_allowed && !src2_ready_o && wake2_i;

    wire [7:0] alloc_views;
    wire src1_write=allocation || wake1_write;
    wire src2_write=allocation || wake2_write;
    wire [31:0] src1_write_data,src2_write_data;
    rv32_frequency_control_tree #(.LEAVES(8)) allocation_tree (
        .signal_i(allocation),.views_o(alloc_views));
    genvar operand_word;
    generate for(operand_word=0;operand_word<2;operand_word=operand_word+1) begin:g_operand_word
        // Allocation wins even if the row also observes a wake this edge.
        // Each select controls only its own 16 data bits.
        assign src1_write_data[operand_word*16 +: 16]=alloc_views[3+operand_word] ?
            new_value1[operand_word*16 +: 16] : wake1_value_i[operand_word*16 +: 16];
        assign src2_write_data[operand_word*16 +: 16]=alloc_views[5+operand_word] ?
            new_value2[operand_word*16 +: 16] : wake2_value_i[operand_word*16 +: 16];
    end endgenerate
    rv32_frequency_word_bank #(.WIDTH(32)) src1_value_owner (
        .clk_i(clk_i),.write_i(src1_write),.data_i(src1_write_data),.data_o(src1_value_o));
    rv32_frequency_word_bank #(.WIDTH(32)) src2_value_owner (
        .clk_i(clk_i),.write_i(src2_write),.data_i(src2_write_data),.data_o(src2_value_o));
    localparam integer META_BITS=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+STORE_DATA_WIDTH+METADATA_WIDTH;
    wire [META_BITS-1:0] metadata_payload;
    assign {op_o,pc_o,rob_tag_o,phys_rd_o,store_data_o,metadata_o}=metadata_payload;
    rv32_frequency_word_bank #(.WIDTH(META_BITS)) metadata_owner (
        .clk_i(clk_i),.write_i(alloc_views[0]),
        .data_i({new_op,new_pc,new_tag,new_phys,new_store,new_metadata}),
        .data_o(metadata_payload));
    // Allocation wins over a simultaneous wake, exactly as the old NBA order.
    always @(posedge clk_i) begin
        if(alloc_views[1])
            src1_tag_o<=new_tag1;
        if(alloc_views[2])
            src2_tag_o<=new_tag2;
        if(reset_i)
        begin
            target_live_o<=0;
            src1_ready_o<=0;
            src2_ready_o<=0;
            age_o<=0;
        end
        else
        begin
            if(alloc_views[7])
            begin
                target_live_o<=new_live;
                src1_ready_o<=new_ready1;
                src2_ready_o<=new_ready2;
                age_o<=new_age;
            end
            else
            begin
                if(wake1_write)
                    src1_ready_o<=1;
                if(wake2_write)
                    src2_ready_o<=1;
            end
            if((flush_i && kill_i) || (!flush_i && issue_i))
                target_live_o<=0;
        end
    end
endmodule
