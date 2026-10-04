"""Bound frontend packet/next-PC routing and separate invalid payload work."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


ROUTE = r'''
    // Only bundle_count authorizes enqueue; computing unused later lanes
    // cannot publish them. Keep all public empty queue outputs zero below.
    wire [FE_WIDTH-1:0] next_pc_classes;
    wire [FE_WIDTH*32-1:0] next_pc_values;
    wire [FE_WIDTH*32-1:0] response_words;
    wire [31:0] default_next_pc=if_resp_pc_i+32'd4;
    genvar response_lane,response_half,public_lane;
    generate
        for(response_lane=0;response_lane<FE_WIDTH;response_lane=response_lane+1) begin:g_response_lane
            wire [2:0] index={1'b0,if_resp_pc_i[3:2]}+response_lane;
            wire [1:0] predicted_views;
            wire [31:0] sequential_pc=if_resp_pc_i+((response_lane+1)*32'd4);
            assign bundle_pc[response_lane*32 +: 32]=if_resp_pc_i+(response_lane*32'd4);
            assign bundle_inst[response_lane*32 +: 32]=response_words[response_lane*32 +: 32];
            assign bundle_pred_taken[response_lane]=if_resp_pred_taken_i[response_lane];
            assign bundle_pred_btb_hit[response_lane]=if_resp_pred_btb_hit_i[response_lane];
            assign bundle_pred_target[response_lane*32 +: 32]=if_resp_pred_target_i[response_lane*32 +: 32];
            assign bundle_pred_kind[response_lane*2 +: 2]=if_resp_pred_kind_i[response_lane*2 +: 2];
            rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_word_reader (
                .rows_i(if_resp_line_data_i),.index_i(index),.value_o(response_words[response_lane*32 +: 32]));
            rv32_frequency_control_tree #(.LEAVES(2)) predicted_tree (
                .signal_i(if_resp_pred_taken_i[response_lane]),.views_o(predicted_views));
            for(response_half=0;response_half<2;response_half=response_half+1) begin:g_half
                assign next_pc_values[response_lane*32+response_half*16 +: 16]=predicted_views[response_half]?
                    if_resp_pred_target_i[response_lane*32+response_half*16 +: 16]:sequential_pc[response_half*16 +: 16];
            end
            assign next_pc_classes[response_lane]=bundle_count==response_lane+1;
        end
        for(public_lane=0;public_lane<FE_WIDTH;public_lane=public_lane+1) begin:g_public_packet
            rv32_frequency_event_select #(.WIDTH(READ_DATA_WIDTH),.EVENTS(1)) packet_selector (
                .events_i(public_lane<count_reg),
                .values_i({queue_read_packets[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                           queue_read_metadata[public_lane*16 +: 16]}),.write_o(),
                .value_o({fetch_packet_o[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                          fetch_pred_metadata_o[public_lane*16 +: 16]}));
        end
    endgenerate
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FE_WIDTH+1),.PRIORITY(0)) next_pc_selector (
        .events_i({(bundle_count==0),next_pc_classes}),
        .values_i({default_next_pc,next_pc_values}),.write_o(),.value_o(next_pc_comb));
'''


def route(t):
    for old in ['    output reg  [FE_WIDTH*16-1:0]       fetch_pred_metadata_o,',
                '    output reg  [FE_WIDTH*`RV32IM_FETCH_PACKET_WIDTH-1:0] fetch_packet_o,',
                '    reg [FE_WIDTH-1:0] bundle_pred_taken;',
                '    reg [FE_WIDTH-1:0] bundle_pred_btb_hit;',
                '    reg [FE_WIDTH*32-1:0] bundle_pred_target;',
                '    reg [FE_WIDTH*2-1:0] bundle_pred_kind;',
                '    reg [FE_WIDTH*32-1:0] bundle_inst;',
                '    reg [FE_WIDTH*32-1:0] bundle_pc;',
                '    reg [31:0] next_pc_comb;']:
        t=change(t,old,old.replace('reg ','wire ',1))
    a=t.index('    assign current_epoch_o = epoch_reg;')
    t=t[:a]+ROUTE+'\n'+t[a:]
    for old in [
        "        bundle_pred_taken = {FE_WIDTH{1'b0}};\n",
        "        bundle_pred_btb_hit = {FE_WIDTH{1'b0}};\n",
        "        bundle_pred_target = {FE_WIDTH*32{1'b0}};\n",
        "        bundle_pred_kind = {FE_WIDTH*2{1'b0}};\n",
        "        bundle_inst = {FE_WIDTH*32{1'b0}};\n",
        "        bundle_pc = {FE_WIDTH*32{1'b0}};\n",
        "        next_pc_comb = if_resp_pc_i + 32'd4;\n",
        '                bundle_inst[b*32 +: 32] = if_resp_line_data_i >> ((word_index+b)*32);\n',
        "                bundle_pc[b*32 +: 32] = if_resp_pc_i + (b*32'd4);\n",
        '                bundle_pred_taken[b] = if_resp_pred_taken_i[b];\n',
        '                bundle_pred_btb_hit[b] = if_resp_pred_btb_hit_i[b];\n',
        '                bundle_pred_target[b*32 +: 32] = if_resp_pred_target_i[b*32 +: 32];\n',
        '                bundle_pred_kind[b*2 +: 2] = if_resp_pred_kind_i[b*2 +: 2];\n',
        "                next_pc_comb = if_resp_pc_i + ((b+1)*32'd4);\n",
        '                    next_pc_comb = if_resp_pred_target_i[b*32 +: 32];\n',
        "        fetch_packet_o = {(FE_WIDTH*PACKET_WIDTH){1'b0}};\n",
        "        fetch_pred_metadata_o = {FE_WIDTH*16{1'b0}};\n",
        '''                fetch_packet_o[j*PACKET_WIDTH +: PACKET_WIDTH] =
                    queue_read_packets[j*PACKET_WIDTH +: PACKET_WIDTH];
''',
        '                fetch_pred_metadata_o[j*16 +: 16] = queue_read_metadata[j*16 +: 16];\n',
    ]:
        t=change(t,old,'')
    return change(t,'((if_resp_line_data_i >> ((word_index+b)*32)) == 32\'h0ff00513)',
                  '(response_words[b*32 +: 32] == 32\'h0ff00513)')


if __name__=='__main__':
    prepare('BV_bounded_frontend_combination',ROOT/'BU_bounded_rs_effective_operands',
            {'rtl/frontend/rv32_fetch_frontend.v':route},
            'BU plus unconditional unconsumed lane payload computation, full-range four-word instruction query, bundle-count one-hot next-PC selection and bounded predicted target mux; preserve first-taken/sentinel/end-of-line bundle_count, response error default PC+4 and public invalid packet zeros with sixteen-bit select leaves; no new FF/cycles, no EDA')
