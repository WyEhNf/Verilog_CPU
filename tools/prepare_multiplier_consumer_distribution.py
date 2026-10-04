"""Bound MUL partial-product consumers and existing storage edges; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def multiplier(source):
    source=change(source,'''    genvar row;
    generate for(row=0;row<32;row=row+1) begin:g_pp
        assign pp[row]=req_src2_i[row]?({32'b0,req_src1_i}<<row):64'b0;
    end endgenerate
    assign pp[32]=neg_a?{~req_src2_i,32'b0}:64'b0;
    assign pp[33]=neg_a?64'h0000000100000000:64'b0;
    assign pp[34]=neg_b?{~req_src1_i,32'b0}:64'b0;
    assign pp[35]=neg_b?64'h0000000100000000:64'b0;''','''    wire [127:0] multiplicand_views;
    wire [5:0] negative_views;
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) multiplicand_tree (
        .signal_i(req_src1_i),.views_o(multiplicand_views));
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(3)) negative_tree (
        .signal_i({neg_b,neg_a}),.views_o(negative_views));
    genvar row;
    generate for(row=0;row<32;row=row+1) begin:g_pp
        wire [1:0] multiplier_views;
        wire [31:0] relative_product;
        rv32_frequency_control_tree #(.LEAVES(2)) multiplier_bit_tree (
            .signal_i(req_src2_i[row]),.views_o(multiplier_views));
        for(genvar product_word=0;product_word<2;product_word=product_word+1) begin:g_word
            assign relative_product[product_word*16 +: 16]=
                {16{multiplier_views[product_word]}} & multiplicand_views[(row/8)*32+product_word*16 +: 16];
        end
        assign pp[row]={32'b0,relative_product}<<row;
    end endgenerate
    assign pp[32]={({16{negative_views[2]}} & ~req_src2_i[31:16]),
                   ({16{negative_views[0]}} & ~req_src2_i[15:0]),32'b0};
    assign pp[33]={31'b0,negative_views[4],32'b0};
    assign pp[34]={({16{negative_views[3]}} & ~req_src1_i[31:16]),
                   ({16{negative_views[1]}} & ~req_src1_i[15:0]),32'b0};
    assign pp[35]={31'b0,negative_views[5],32'b0};''')
    for prefix in ['s1','s2']:
        for width,name in [('OP_WIDTH','op'),('TAG_WIDTH','tag'),('PHYS_ADDR_WIDTH','phys')]:
            source=change(source,f'    reg [{width}-1:0] {prefix}_{name};',f'    wire [{width}-1:0] {prefix}_{name};')
        source=change(source,f'    reg {prefix}_live;',f'    wire {prefix}_live;')
    for old,new in [
        ('    reg [31:0] out_value;', '    wire [31:0] out_value;'),
        ('    reg [TAG_WIDTH-1:0] out_tag;', '    wire [TAG_WIDTH-1:0] out_tag;'),
        ('    reg [PHYS_ADDR_WIDTH-1:0] out_phys;', '    wire [PHYS_ADDR_WIDTH-1:0] out_phys;'),
        ('    reg out_live;', '    wire out_live;'),
        ('    wire [4:0] s2_write_domains;', '    wire [8:0] s2_write_domains;'),
        ('rv32_frequency_control_tree #(.LEAVES(5)) s2_write_tree', 'rv32_frequency_control_tree #(.LEAVES(9)) s2_write_tree'),
        ('    wire [16:0] s1_write_domains;', '    wire [32:0] s1_write_domains;'),
        ('    wire [1:0] out_write_domains;\n',''),
        ('rv32_frequency_control_tree #(.LEAVES(17)) s1_write_tree', 'rv32_frequency_control_tree #(.LEAVES(33)) s1_write_tree'),
    ]:
        source=change(source,old,new)
    source=change(source,'''    rv32_frequency_control_tree #(.LEAVES(2)) out_write_tree (
        .signal_i(out_ready && s2_valid && !s2_discard),.views_o(out_write_domains));''','''    wire payload_active=!reset_i && !flush_i;
    wire out_write=payload_active && out_ready && s2_valid && !s2_discard;''')
    source=change(source,'''            if(s2_write_domains[2*row]) s2_rows[row][31:0]<=l8[row][31:0];
            if(s2_write_domains[2*row+1]) s2_rows[row][63:32]<=l8[row][63:32];''','''            if(s2_write_domains[4*row]) s2_rows[row][15:0]<=l8[row][15:0];
            if(s2_write_domains[4*row+1]) s2_rows[row][31:16]<=l8[row][31:16];
            if(s2_write_domains[4*row+2]) s2_rows[row][47:32]<=l8[row][47:32];
            if(s2_write_domains[4*row+3]) s2_rows[row][63:48]<=l8[row][63:48];''')
    source=change(source,'''            if(s1_write_domains[2*row]) s1_rows[row][31:0]<=l4[row][31:0];
            if(s1_write_domains[2*row+1]) s1_rows[row][63:32]<=l4[row][63:32];''','''            if(s1_write_domains[4*row]) s1_rows[row][15:0]<=l4[row][15:0];
            if(s1_write_domains[4*row+1]) s1_rows[row][31:16]<=l4[row][31:16];
            if(s1_write_domains[4*row+2]) s1_rows[row][47:32]<=l4[row][47:32];
            if(s1_write_domains[4*row+3]) s1_rows[row][63:48]<=l4[row][63:48];''')
    source=change(source,'''                if(s1_write_domains[16]) begin
                    s1_op<=req_op_i;
                    s1_tag<=req_rob_tag_i;
                    s1_phys<=req_phys_rd_i;
                    s1_live<=req_target_live_i && req_rob_tag_i[0];
                end''','                // Metadata owner below captures on this same qualified edge.')
    source=change(source,'''            if(s2_write_domains[4]) begin
                s2_op<=s1_op;s2_tag<=s1_tag;s2_phys<=s1_phys;s2_live<=s1_live;
            end''','            // Metadata owner below captures on the original transfer edge.')
    start=source.index('            if(out_write_domains[0]) begin')
    end=source.index('        end\n    end\nendmodule',start)
    source=source[:start]+source[end:]
    source=change(source,'    always @(posedge clk_i) begin\n        if(reset_i || flush_i) begin','''    localparam integer MUL_META_WIDTH=OP_WIDTH+TAG_WIDTH+PHYS_ADDR_WIDTH+1;
    wire [MUL_META_WIDTH-1:0] s1_metadata,s2_metadata;
    assign {s1_op,s1_tag,s1_phys,s1_live}=s1_metadata;
    assign {s2_op,s2_tag,s2_phys,s2_live}=s2_metadata;
    rv32_frequency_word_bank #(.WIDTH(MUL_META_WIDTH)) s1_metadata_owner (
        .clk_i(clk_i),.write_i(payload_active && s1_ready && s1_write_domains[32]),
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
        if(reset_i || flush_i) begin''')
    return source


if __name__=='__main__':
    prepare('CS_multiplier_consumer_distribution',ROOT/'CR_icache_control_scan',{
        'rtl/rv32m_multiplier.v':multiplier,
    }, 'CR plus four eight-row multiplicand domains, two16-bit partial-product enable domains per multiplier bit, bounded signed correction, 16-bit existing CSA stage writes and metadata/output ownership. Original modulo64 CSA/CPA arithmetic, two existing arithmetic boundaries, valid/ready/discard, reset-edge data overwrite versus metadata hold, invalid-op zero result and cycle/throughput preserved. No new FF/SRAM or hardware tests; source-only candidate.')
