"""Bound the actual payload consumers of each RTL distribution leaf.

Source transformation only. Transaction validity, recovery, and clock edges
are unchanged. No compiler, simulation, synthesis, or STA is called.
"""
from prepare_staged_frequency_candidate import change, prepare, ROOT


WORD_BANK = r'''
// Write ownership is distributed AFTER qualification. Each last driver
// controls at most 32 existing payload hold muxes, with no payload reset.
module rv32_frequency_word_bank #(parameter integer WIDTH=32) (
    input wire clk_i, write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    localparam integer WORDS=(WIDTH+31)/32;
    wire [WORDS-1:0] write_words;
    rv32_frequency_control_tree #(.LEAVES(WORDS)) write_tree (
        .signal_i(write_i), .views_o(write_words));
    genvar word_id;
    generate for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
        localparam integer LOW=word_id*32;
        localparam integer BITS=WIDTH-LOW>=32 ? 32 : WIDTH-LOW;
        always @(posedge clk_i) if(write_words[word_id])
            data_o[LOW +: BITS]<=data_i[LOW +: BITS];
    end endgenerate
endmodule
'''


def rs_words(t):
    t=change(t,'    genvar ar, al;', '    genvar ar, al, alloc_word;')
    t=change(t,'''            wire [BE_WIDTH-1:0] payload_grants;
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(1)) grant_tree (
                .signal_i(grants),.views_o(payload_grants));
            reg [ALLOC_PAYLOAD_WIDTH-1:0] payload;
            integer mux_lane;
            always @* begin
                payload = 0;
                for (mux_lane = 0; mux_lane < BE_WIDTH; mux_lane = mux_lane + 1)
                    payload = payload | ({ALLOC_PAYLOAD_WIDTH{payload_grants[mux_lane]}} & alloc_lane_payload[mux_lane]);
            end''', '''            localparam integer WORDS=(ALLOC_PAYLOAD_WIDTH+31)/32;
            wire [BE_WIDTH*WORDS-1:0] payload_grants;
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(WORDS)) grant_tree (
                .signal_i(grants),.views_o(payload_grants));
            wire [ALLOC_PAYLOAD_WIDTH-1:0] payload;
            for(alloc_word=0;alloc_word<WORDS;alloc_word=alloc_word+1) begin:g_word
                localparam integer LOW=alloc_word*32;
                localparam integer BITS=ALLOC_PAYLOAD_WIDTH-LOW>=32 ? 32 : ALLOC_PAYLOAD_WIDTH-LOW;
                reg [BITS-1:0] selected_word;
                integer mux_lane;
                always @* begin
                    selected_word=0;
                    for(mux_lane=0;mux_lane<BE_WIDTH;mux_lane=mux_lane+1)
                        selected_word=selected_word |
                            ({BITS{payload_grants[alloc_word*BE_WIDTH+mux_lane]}} &
                             alloc_lane_payload[mux_lane][LOW +: BITS]);
                end
                assign payload[LOW +: BITS]=selected_word;
            end''')
    old,new=t.split('module rv32_rs_payload_row #(',1)
    new=change(new,'    output reg [OP_WIDTH-1:0] op_o,','    output wire [OP_WIDTH-1:0] op_o,')
    new=change(new,'    output reg [31:0] pc_o,src1_value_o,src2_value_o,',
               '    output wire [31:0] pc_o,\n    output reg [31:0] src1_value_o,src2_value_o,')
    new=change(new,'    output reg [TAG_WIDTH-1:0] rob_tag_o,src1_tag_o,src2_tag_o,',
               '    output wire [TAG_WIDTH-1:0] rob_tag_o,\n    output reg [TAG_WIDTH-1:0] src1_tag_o,src2_tag_o,')
    for width,name in [('PHYS_ADDR_WIDTH','phys_rd_o'),('STORE_DATA_WIDTH','store_data_o'),('METADATA_WIDTH','metadata_o')]:
        new=change(new,f'    output reg [{width}-1:0] {name},',f'    output wire [{width}-1:0] {name},')
    new=change(new,'''    // Allocation wins over a simultaneous wake, exactly as the old NBA order.
    always @(posedge clk_i) begin
        if(alloc_views[0]) {op_o,pc_o,rob_tag_o,phys_rd_o,store_data_o,metadata_o}<=
            {new_op,new_pc,new_tag,new_phys,new_store,new_metadata};''', '''    localparam integer META_BITS=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+STORE_DATA_WIDTH+METADATA_WIDTH;
    wire [META_BITS-1:0] metadata_payload;
    assign {op_o,pc_o,rob_tag_o,phys_rd_o,store_data_o,metadata_o}=metadata_payload;
    rv32_frequency_word_bank #(.WIDTH(META_BITS)) metadata_owner (
        .clk_i(clk_i),.write_i(alloc_views[0]),
        .data_i({new_op,new_pc,new_tag,new_phys,new_store,new_metadata}),
        .data_o(metadata_payload));
    // Allocation wins over a simultaneous wake, exactly as the old NBA order.
    always @(posedge clk_i) begin''')
    return old+'module rv32_rs_payload_row #('+new


def multiplier_words(t):
    t=change(t,'    wire [8:0] s1_write_domains;','    wire [16:0] s1_write_domains;')
    t=change(t,'#(.LEAVES(9)) s1_write_tree','#(.LEAVES(17)) s1_write_tree')
    t=change(t,'''        always @(posedge clk_i) if(s1_write_domains[row])
            s1_rows[row]<=l4[row];''', '''        always @(posedge clk_i) begin
            if(s1_write_domains[2*row]) s1_rows[row][31:0]<=l4[row][31:0];
            if(s1_write_domains[2*row+1]) s1_rows[row][63:32]<=l4[row][63:32];
        end''')
    return change(t,'if(s1_write_domains[8]) begin','if(s1_write_domains[16]) begin')


def completion_words(t):
    t=change(t,'                wire [3:0] selected_views;','                wire [4:0] selected_views;')
    t=change(t,'#(.LEAVES(4)) select_tree','#(.LEAVES(5)) select_tree')
    t=change(t,'''                assign memory_tree[RANK_LEAVES+payload_source]={64{selected_views[2]}} &
                    {producer_addr_i[payload_source*32 +: 32],producer_store_data_i[payload_source*32 +: 32]};''', '''                assign memory_tree[RANK_LEAVES+payload_source]={
                    {32{selected_views[2]}} & producer_addr_i[payload_source*32 +: 32],
                    {32{selected_views[3]}} & producer_store_data_i[payload_source*32 +: 32]};''')
    return change(t,'{32{selected_views[3]}} &\n                    producer_branch_target_i',
                    '{32{selected_views[4]}} &\n                    producer_branch_target_i')


def descriptor_words(t):
    t=change(t,'    reg [CHECK_RAT_WIDTH-1:0] recovery_descriptor_rat;',
               '    wire [CHECK_RAT_WIDTH-1:0] recovery_descriptor_rat;')
    t=change(t,'    reg [PHYS_REGS-1:0] recovery_descriptor_reclaim;',
               '    wire [PHYS_REGS-1:0] recovery_descriptor_reclaim;')
    t=change(t,'        if(recovery_capture_domains[1]) recovery_descriptor_rat<=recovery_rat_state;\n','')
    t=change(t,'            recovery_descriptor_reclaim<=rob_recovery_reclaim_bitmap;\n','')
    return change(t,'''    always @(posedge clk_i) begin
        if(reset_i || flush_i) recovery_descriptor_valid<=1'b0;''', '''    rv32_frequency_word_bank #(.WIDTH(CHECK_RAT_WIDTH)) rat_descriptor_owner (
        .clk_i(clk_i),.write_i(recovery_capture_domains[1]),
        .data_i(recovery_rat_state),.data_o(recovery_descriptor_rat));
    rv32_frequency_word_bank #(.WIDTH(PHYS_REGS)) reclaim_descriptor_owner (
        .clk_i(clk_i),.write_i(recovery_capture_domains[2]),
        .data_i(rob_recovery_reclaim_bitmap),.data_o(recovery_descriptor_reclaim));
    always @(posedge clk_i) begin
        if(reset_i || flush_i) recovery_descriptor_valid<=1'b0;''')


if __name__=='__main__':
    prepare('T_bounded_payload_consumers', ROOT/'S_functional_rtl_control_distribution',
            {'rtl/common/rv32_asap7_fanout.v': lambda t:t+WORD_BANK,
             'rtl/backend/rv32_reservation_station.v':rs_words,
             'rtl/backend/rv32_completion_network.v':completion_words,
             'rtl/backend/rv32_backend_joint.v':descriptor_words,
             'rtl/rv32m_multiplier.v':multiplier_words},
            'S plus 32-bit RS allocation selection and metadata write ownership, split 64-bit completion/multiplier consumers and word-owned RAT/reclaim descriptors; unchanged clock boundaries and logical payload values, no EDA run')
