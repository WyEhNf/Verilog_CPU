"""Bound memory error response and MDU issue routing; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


MDU = r'''
    localparam integer MDU_ISSUE_PAYLOAD_WIDTH=`RV32IM_OP_WIDTH+64+TAG_WIDTH+PAW;
    localparam integer MDU_LANE_WIDTH=(BE_WIDTH<=1)?1:$clog2(BE_WIDTH);
    wire [BE_WIDTH-1:0] mdu_candidates=rs_issue_valid & rs_issue_is_mdu;
    wire mdu_found;
    wire [MDU_LANE_WIDTH-1:0] mdu_lane;
    wire [BE_WIDTH*MDU_ISSUE_PAYLOAD_WIDTH-1:0] mdu_values;
    rv32_frequency_first_two #(.ENTRIES(BE_WIDTH),.INDEX_WIDTH(MDU_LANE_WIDTH)) mdu_first_selector (
        .candidates_i(mdu_candidates),.first_valid_o(mdu_found),.first_index_o(mdu_lane),
        .second_valid_o(),.second_index_o());
    genvar mdu_route_lane;
    generate for(mdu_route_lane=0;mdu_route_lane<BE_WIDTH;mdu_route_lane=mdu_route_lane+1) begin:g_mdu_route
        assign mdu_select[mdu_route_lane]=mdu_found && mdu_lane==mdu_route_lane;
        assign mdu_values[mdu_route_lane*MDU_ISSUE_PAYLOAD_WIDTH +: MDU_ISSUE_PAYLOAD_WIDTH]={
            rs_issue_op[mdu_route_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH],
            rs_issue_src1[mdu_route_lane*32 +: 32],rs_issue_src2[mdu_route_lane*32 +: 32],
            rs_issue_tag[mdu_route_lane*TAG_WIDTH +: TAG_WIDTH],rs_issue_phys[mdu_route_lane*PAW +: PAW]};
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(MDU_ISSUE_PAYLOAD_WIDTH),.EVENTS(BE_WIDTH)) mdu_payload_selector (
        .events_i(mdu_select),.values_i(mdu_values),.write_o(),
        .value_o({mdu_issue_op,mdu_issue_src1,mdu_issue_src2,mdu_issue_tag,mdu_issue_phys}));
'''


def mdu(t):
    for d in ['[BE_WIDTH-1:0] mdu_select','[`RV32IM_OP_WIDTH-1:0] mdu_issue_op',
              '[31:0] mdu_issue_src1, mdu_issue_src2','[TAG_WIDTH-1:0] mdu_issue_tag',
              '[PAW-1:0] mdu_issue_phys']:
        t=change(t,'    reg '+d+';','    wire '+d+';')
    t=change(t,'    integer issue_lane;\n','')
    t=change(t,'    integer mdu_taken;\n','')
    a=t.index('    always @* begin\n        mdu_select =')
    b=t.index('    assign mdu_issue_valid',a)
    return t[:a]+MDU+t[b:]


MEMORY = r'''
    wire [11:0] i_error_views,d_error_views;
    rv32_frequency_control_tree #(.LEAVES(12)) instruction_error_tree (
        .signal_i(i_local_error),.views_o(i_error_views));
    rv32_frequency_control_tree #(.LEAVES(12)) data_error_tree (
        .signal_i(d_local_error),.views_o(d_error_views));
    rv32_frequency_word_bank #(.WIDTH(40)) instruction_error_record (
        .clk_i(clk_i),.write_i(!reset_i && i_cache_req_fire),
        .data_i({cache_i_req_line_addr_i,cache_i_req_id_i}),.data_o({i_line_addr,i_id}));
    rv32_frequency_word_bank #(.WIDTH(40)) data_error_record (
        .clk_i(clk_i),.write_i(!reset_i && d_cache_req_fire),
        .data_i({cache_d_req_line_addr_i,cache_d_req_id_i}),.data_o({d_line_addr,d_id}));
    genvar response_word;
    generate
        for(response_word=0;response_word<2;response_word=response_word+1) begin:g_response_address
            assign cache_i_resp_line_addr_o[response_word*16 +: 16]=i_error_views[response_word]?
                i_line_addr[response_word*16 +: 16]:mem_i_resp_line_addr_i[response_word*16 +: 16];
            assign cache_d_resp_line_addr_o[response_word*16 +: 16]=d_error_views[response_word]?
                d_line_addr[response_word*16 +: 16]:mem_d_resp_line_addr_i[response_word*16 +: 16];
        end
        for(response_word=0;response_word<8;response_word=response_word+1) begin:g_response_data
            assign cache_i_resp_data_o[response_word*16 +: 16]={16{!i_error_views[response_word+2]}} & mem_i_resp_data_i[response_word*16 +: 16];
            assign cache_d_resp_data_o[response_word*16 +: 16]={16{!d_error_views[response_word+2]}} & mem_d_resp_data_i[response_word*16 +: 16];
        end
    endgenerate
    assign cache_i_resp_valid_o=i_error_views[11] || mem_i_resp_valid_i;
    assign cache_i_resp_id_o=i_error_views[10]?i_id:mem_i_resp_id_i;
    assign cache_i_resp_error_o=i_error_views[11] || mem_i_resp_error_i;
    assign mem_i_resp_ready_o=!i_error_views[11] && cache_i_resp_ready_i;
    assign cache_d_resp_valid_o=d_error_views[11] || mem_d_resp_valid_i;
    assign cache_d_resp_id_o=d_error_views[10]?d_id:mem_d_resp_id_i;
    assign cache_d_resp_error_o=d_error_views[11] || mem_d_resp_error_i;
    assign mem_d_resp_ready_o=!d_error_views[11] && cache_d_resp_ready_i;
'''


def memory(t):
    t=change(t,'''// Transaction bridge between the caches and the independent line ports.  The
// instruction side is deliberately transparent so a non-blocking I-cache can
// keep several tagged reads in flight.  The data side retains its one-entry
// ordered transaction buffer until the D-cache grows multiple MSHRs.''',
        '''// Both cache sides pass tagged line transactions directly to memory.
// Invalid addresses create a retained local error response; response payload
// selection is distributed without adding a transaction or pipeline stage.''')
    for d in ['[31:0] i_line_addr','[7:0] i_id','[31:0] d_line_addr','[7:0] d_id']:
        t=change(t,'    reg '+d+';','    wire '+d+';')
    a=t.index('    assign cache_i_resp_valid_o =')
    b=t.index('    assign event_i_mem_request_o',a)
    t=t[:a]+MEMORY+'\n'+t[b:]
    for old in ["            i_line_addr <= 32'd0;\n","            i_id <= 8'd0;\n",
                "            d_line_addr <= 32'd0;\n","            d_id <= 8'd0;\n",
                '                i_line_addr <= cache_i_req_line_addr_i;\n','                i_id <= cache_i_req_id_i;\n',
                '                d_line_addr <= cache_d_req_line_addr_i;\n','                d_id <= cache_d_req_id_i;\n']:
        t=change(t,old,'')
    return t


if __name__=='__main__':
    prepare('BN_memory_and_mdu_bounded_routing',ROOT/'BM_axi_bounded_transaction_queries',{
        'rtl/backend/rv32_backend_joint.v':mdu,'rtl/memory/rv32_memory_bridge.v':memory,
    },'BM plus balanced first-live-MDU lane and sixteen-bit one-hot issue payload, memory local-error record and bounded address/data/id response selection; preserve MDU ready/lowest-lane priority and memory error-valid/backpressure, remove invalid payload reset; no added FF/cycles and no EDA')
