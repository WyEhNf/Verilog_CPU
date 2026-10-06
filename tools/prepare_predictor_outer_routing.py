"""Bound cross-bank prediction routing and RAS return-address selection."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


def banked(t):
    t=change(t,'    wire [FE_WIDTH*8-1:0] bank_training_index;',
             '''    wire [FE_WIDTH*8-1:0] bank_training_index;
    wire [FE_WIDTH*38-1:0] bank_query_packets;''')
    t=change(t,'''            wire [127:0] shifted_line = query_line_i >> (word_index * 32);
            wire [31:0] inst = shifted_line[31:0];''',
             '''            wire [31:0] inst;
            rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                .rows_i(query_line_i),.index_i(word_index),.value_o(inst));
            assign bank_query_packets[bank*38 +: 38]={bank_taken[bank],bank_hit[bank],
                bank_target[bank*32 +: 32],bank_kind[bank*2 +: 2],bank_counter[bank*2 +: 2]};''')
    start=t.index('            assign pred_taken_o[lane] = bank_taken[select_bank];')
    end=t.index('            assign pred_bht_index_o',start)
    t=t[:start]+'''            wire [37:0] selected_prediction;
            rv32_frequency_array_read #(.WIDTH(38),.ENTRIES(FE_WIDTH),.INDEX_WIDTH(2)) bank_query (
                .rows_i(bank_query_packets),.index_i(select_bank),.value_o(selected_prediction));
            assign {pred_taken_o[lane],pred_btb_hit_o[lane],pred_target_o[lane*32 +: 32],
                pred_kind_o[lane*2 +: 2],pred_counter_o[lane*2 +: 2]}=selected_prediction;
'''+t[end:]
    return t


def core(t):
    t=change(t,'    reg [31:0] ras_push_address;',
             '''    wire [31:0] ras_push_address;
    reg [FE_WIDTH-1:0] ras_push_lanes;
    wire [FE_WIDTH*32-1:0] ras_return_addresses;''')
    t=change(t,'    reg [31:0] ras_pc;\n','')
    t=change(t,'            assign ras_query_words[predictor_lane*32 +: 32]=query_inst;',
             '''            assign ras_query_words[predictor_lane*32 +: 32]=query_inst;
            // Independent constant add replaces selected PC then PC+4.
            assign ras_return_addresses[predictor_lane*32 +: 32]=if_resp_pc+((predictor_lane+1)*32'd4);''')
    t=change(t,"        ras_push_address = 32'd0;","        ras_push_lanes = {FE_WIDTH{1'b0}};")
    t=change(t,"        ras_pc = 32'd0;\n",'')
    t=change(t,"                    ras_pc = if_resp_pc + (ras_lane * 32'd4);\n",'')
    t=change(t,"                        ras_push_address = ras_pc + 32'd4;",
             "                        ras_push_lanes[ras_lane] = 1'b1;")
    return change(t,'    genvar ras_row;',
                  '''    // The first accepted call wins; return/taken events close the
    // prefix even when they do not push. Each payload mask drives <=16 bits.
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FE_WIDTH),.PRIORITY(0)) ras_return_address_selector (
        .events_i(ras_push_lanes),.values_i(ras_return_addresses),.write_o(),.value_o(ras_push_address));
    genvar ras_row;''')


if __name__=='__main__':
    prepare('CD_predictor_outer_and_ras_routing',ROOT/'CC_prediction_targets_and_ras_owners',{
        'rtl/predictor/rv32_banked_predictor.v':banked,
        'rtl/cpu_core.v':core,
    },'CC plus bounded 38-bit cross-bank prediction packet routing and direct four-word instruction reads; first accepted RAS call picks precomputed PC+4*(lane+1) through 16-bit masks instead of ready/prefix-controlled 32-bit address mux and sequential additions; original call/return/taken prefix, FE 1/2/4 bank rotation and table indices retained, no extra FF/cycles, no EDA')
