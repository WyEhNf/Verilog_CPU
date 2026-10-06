"""Prepare bounded launch/completion payload domains from CP; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def mdu(source):
    for old,new in [
        ('    reg [`RV32IM_OP_WIDTH-1:0] pending_op;', '    wire [`RV32IM_OP_WIDTH-1:0] pending_op;'),
        ('    reg [31:0] pending_src1, pending_src2;', '    wire [31:0] pending_src1, pending_src2;'),
        ('    reg [TAG_WIDTH-1:0] pending_tag;', '    wire [TAG_WIDTH-1:0] pending_tag;'),
        ('    reg [PHYS_ADDR_WIDTH-1:0] pending_phys;', '    wire [PHYS_ADDR_WIDTH-1:0] pending_phys;'),
        ('    reg pending_live;', '    wire pending_live;'),
    ]:
        source=change(source,old,new)
    source=change(source,'''    assign completion_value_o = mul_resp_valid ? mul_resp_value : div_resp_value;
    assign completion_rob_tag_o = mul_resp_valid ? mul_resp_tag : div_resp_tag;
    assign completion_phys_rd_o = mul_resp_valid ? mul_resp_phys : div_resp_phys;
    assign completion_rd_we_o = mul_resp_valid ? mul_resp_rd_we : div_resp_rd_we;''','''    localparam integer COMPLETION_PAYLOAD_WIDTH=33+TAG_WIDTH+PHYS_ADDR_WIDTH;
    localparam integer COMPLETION_WORDS=(COMPLETION_PAYLOAD_WIDTH+15)/16;
    wire [COMPLETION_PAYLOAD_WIDTH-1:0] mul_payload,div_payload,completion_payload;
    wire [COMPLETION_WORDS-1:0] completion_source_views;
    assign mul_payload={mul_resp_value,mul_resp_tag,mul_resp_phys,mul_resp_rd_we};
    assign div_payload={div_resp_value,div_resp_tag,div_resp_phys,div_resp_rd_we};
    assign {completion_value_o,completion_rob_tag_o,completion_phys_rd_o,completion_rd_we_o}=completion_payload;
    rv32_frequency_control_tree #(.LEAVES(COMPLETION_WORDS)) completion_source_tree (
        .signal_i(mul_resp_valid),.views_o(completion_source_views));
    generate for(genvar completion_word=0;completion_word<COMPLETION_WORDS;completion_word=completion_word+1) begin:g_completion_word
        localparam integer LOW=completion_word*16;
        localparam integer BITS=(COMPLETION_PAYLOAD_WIDTH-LOW>=16)?16:COMPLETION_PAYLOAD_WIDTH-LOW;
        assign completion_payload[LOW +: BITS]=completion_source_views[completion_word]?
            mul_payload[LOW +: BITS]:div_payload[LOW +: BITS];
    end endgenerate''')
    source=change(source,'''    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin''','''    // The existing one-entry buffer refills on the original issue edge.
    // Clear and capture are mutually exclusive, with payload reset retained.
    localparam integer LAUNCH_PAYLOAD_WIDTH=`RV32IM_OP_WIDTH+65+TAG_WIDTH+PHYS_ADDR_WIDTH;
    wire launch_clear=reset_i || flush_i;
    wire launch_capture=!launch_clear && issue_valid_i && issue_ready_o;
    wire launch_write;
    wire [LAUNCH_PAYLOAD_WIDTH-1:0] launch_next,launch_payload;
    assign {pending_op,pending_src1,pending_src2,pending_tag,pending_phys,pending_live}=launch_payload;
    rv32_frequency_event_select #(.WIDTH(LAUNCH_PAYLOAD_WIDTH),.EVENTS(2),.PRIORITY(0)) launch_selector (
        .events_i({launch_clear,launch_capture}),
        .values_i({{LAUNCH_PAYLOAD_WIDTH{1'b0}},
                   {issue_op_i,issue_src1_i,issue_src2_i,issue_rob_tag_i,issue_phys_rd_i,issue_target_live_i}}),
        .write_o(launch_write),.value_o(launch_next));
    rv32_frequency_word_bank #(.WIDTH(LAUNCH_PAYLOAD_WIDTH)) launch_owner (
        .clk_i(clk_i),.write_i(launch_write),.data_i(launch_next),.data_o(launch_payload));

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin''')
    for name in ['pending_op','pending_src1','pending_src2','pending_tag','pending_phys','pending_live']:
        source=change(source,f'            {name} <= 0;','')
    for name,value in [
        ('pending_op','issue_op_i'),('pending_src1','issue_src1_i'),('pending_src2','issue_src2_i'),
        ('pending_tag','issue_rob_tag_i'),('pending_phys','issue_phys_rd_i'),('pending_live','issue_target_live_i'),
    ]:
        source=change(source,f'                {name} <= {value};','')
    return source


if __name__=='__main__':
    prepare('CQ_mdu_launch_distribution',ROOT/'CP_rob_recovery_distribution',{
        'rtl/backend/rv32m_mdu_reservation_station.v':mdu,
    }, 'CP plus 16-bit MDU launch-buffer payload write/reset domains and 16-bit MUL/DIV completion source selection. Same one-entry refill edge, pending valid/inflight priority and counts, zero-reset fields, scalar ready/fire, multiplier-first arbitration and cancellation preserved for all MUL_IMPL values. No extra FF/SRAM/cycles or hardware tests; source-only candidate.')
