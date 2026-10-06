"""Partition predictor table ownership and queries without extra cycles."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


TABLES = r'''
    wire [1:0] bht [0:BHT_ENTRIES-1];
    wire bht_trained [0:BHT_ENTRIES-1];
    wire btb_valid [0:BTB_ENTRIES-1];
    wire [23:0] btb_tag [0:BTB_ENTRIES-1];
    wire [31:0] btb_target [0:BTB_ENTRIES-1];
    wire [1:0] btb_kind [0:BTB_ENTRIES-1];
    localparam integer BHT_DOMAINS=(BHT_ENTRIES+3)/4;
    localparam integer BTB_DOMAINS=(BTB_ENTRIES+3)/4;
    localparam integer BHT_INDEX_WIDTH=8-BANK_BITS;
    localparam integer BTB_INDEX_WIDTH=6-BANK_BITS;
    wire [BHT_ENTRIES*3-1:0] bht_rows;
    wire [BTB_ENTRIES*59-1:0] btb_rows;
    wire [2:0] query_bht_word;
    wire [58:0] query_btb_word;
    wire [BHT_DOMAINS*BHT_INDEX_WIDTH-1:0] bht_write_queries;
    wire [BHT_DOMAINS-1:0] bht_write_events,bht_directions;
    wire [BTB_DOMAINS*BTB_INDEX_WIDTH-1:0] btb_write_queries;
    wire [BTB_DOMAINS*58-1:0] btb_write_payloads;
    wire [BTB_DOMAINS-1:0] btb_write_events;
    wire [BHT_ENTRIES+BTB_ENTRIES+4-1:0] reset_views;
    rv32_frequency_control_tree #(.LEAVES(BHT_ENTRIES+BTB_ENTRIES+4)) reset_tree (
        .signal_i(reset_i),.views_o(reset_views));
    rv32_frequency_control_tree #(.WIDTH(BHT_INDEX_WIDTH),.LEAVES(BHT_DOMAINS)) bht_address_tree (
        .signal_i(feedback_bht_index),.views_o(bht_write_queries));
    rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bht_event_tree (
        .signal_i(feedback_valid_i && feedback_kind_i==`RV32IM_PRED_BRANCH),.views_o(bht_write_events));
    rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bht_direction_tree (
        .signal_i(feedback_taken_i),.views_o(bht_directions));
    rv32_frequency_control_tree #(.WIDTH(BTB_INDEX_WIDTH),.LEAVES(BTB_DOMAINS)) btb_address_tree (
        .signal_i(feedback_btb_index),.views_o(btb_write_queries));
    rv32_frequency_control_tree #(.LEAVES(BTB_DOMAINS)) btb_event_tree (
        .signal_i(feedback_btb_write),.views_o(btb_write_events));
    rv32_frequency_control_tree #(.WIDTH(58),.LEAVES(BTB_DOMAINS)) btb_payload_tree (
        .signal_i({feedback_pc_i[31:8],feedback_btb_target,feedback_kind_i}),.views_o(btb_write_payloads));
    genvar predictor_row;
    generate
        for(predictor_row=0;predictor_row<BHT_ENTRIES;predictor_row=predictor_row+1) begin:g_bht_owner
            localparam integer DOMAIN=predictor_row/4;
            wire update=bht_write_events[DOMAIN] &&
                bht_write_queries[DOMAIN*BHT_INDEX_WIDTH +: BHT_INDEX_WIDTH]==predictor_row;
            rv32_predictor_bht_row row (
                .clk_i(clk_i),.reset_i(reset_views[predictor_row]),.update_i(update),
                .taken_i(bht_directions[DOMAIN]),.counter_o(bht[predictor_row]),.trained_o(bht_trained[predictor_row]));
            assign bht_rows[predictor_row*3 +: 3]={bht_trained[predictor_row],bht[predictor_row]};
        end
        for(predictor_row=0;predictor_row<BTB_ENTRIES;predictor_row=predictor_row+1) begin:g_btb_owner
            localparam integer DOMAIN=predictor_row/4;
            wire update=btb_write_events[DOMAIN] &&
                btb_write_queries[DOMAIN*BTB_INDEX_WIDTH +: BTB_INDEX_WIDTH]==predictor_row;
            rv32_predictor_btb_row row (
                .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                .payload_i(btb_write_payloads[DOMAIN*58 +: 58]),.valid_o(btb_valid[predictor_row]),
                .tag_o(btb_tag[predictor_row]),.target_o(btb_target[predictor_row]),.kind_o(btb_kind[predictor_row]));
            assign btb_rows[predictor_row*59 +: 59]={btb_valid[predictor_row],btb_tag[predictor_row],btb_target[predictor_row],btb_kind[predictor_row]};
        end
    endgenerate
    rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) bht_query (
        .rows_i(bht_rows),.index_i(query_bht_index),.value_o(query_bht_word));
    rv32_frequency_array_read #(.WIDTH(59),.ENTRIES(BTB_ENTRIES),.INDEX_WIDTH(BTB_INDEX_WIDTH)) btb_query (
        .rows_i(btb_rows),.index_i(query_btb_index),.value_o(query_btb_word));
'''


COUNTERS = r'''
    wire prediction_write=reset_i || feedback_valid_i;
    wire correct_event=feedback_valid_i && (feedback_pred_taken_i==feedback_taken_i) &&
        (!feedback_taken_i || feedback_pred_target_i==feedback_target_i);
    wire correct_write=reset_i || correct_event;
    wire [31:0] prediction_increment=prediction_count_o+32'd1;
    wire [31:0] correct_increment=correct_count_o+32'd1;
    wire [31:0] prediction_next,correct_next;
    genvar counter_word;
    generate for(counter_word=0;counter_word<2;counter_word=counter_word+1) begin:g_counter_word
        assign prediction_next[counter_word*16 +: 16]=reset_views[BHT_ENTRIES+BTB_ENTRIES+counter_word] ?
            16'b0 : prediction_increment[counter_word*16 +: 16];
        assign correct_next[counter_word*16 +: 16]=reset_views[BHT_ENTRIES+BTB_ENTRIES+2+counter_word] ?
            16'b0 : correct_increment[counter_word*16 +: 16];
    end endgenerate
    rv32_frequency_word_bank #(.WIDTH(32)) prediction_count_owner (
        .clk_i(clk_i),.write_i(prediction_write),.data_i(prediction_next),.data_o(prediction_count_o));
    rv32_frequency_word_bank #(.WIDTH(32)) correct_count_owner (
        .clk_i(clk_i),.write_i(correct_write),.data_i(correct_next),.data_o(correct_count_o));
'''


ROW_MODULES = r'''

// Saturating direction counter preserves weakly-taken reset and first
// training behavior. Every row owns three reset/update state bits.
module rv32_predictor_bht_row (
    input wire clk_i,reset_i,update_i,taken_i,
    output reg [1:0] counter_o,
    output reg trained_o
);
    always @(posedge clk_i) begin
        if(reset_i) begin counter_o<=2'b10;trained_o<=0;end
        else if(update_i) begin
            trained_o<=1;
            if(taken_i) begin
                if(counter_o!=2'b11) counter_o<=counter_o+2'b01;
            end else if(counter_o!=2'b00) counter_o<=counter_o-2'b01;
        end
    end
endmodule

// BTB payload is meaningful only while valid and tag/kind match. Reset
// invalidates it; the original single accepted feedback owns every write.
module rv32_predictor_btb_row (
    input wire clk_i,reset_i,update_i,
    input wire [57:0] payload_i,
    output reg valid_o,
    output wire [23:0] tag_o,
    output wire [31:0] target_o,
    output wire [1:0] kind_o
);
    wire [57:0] payload;
    rv32_frequency_word_bank #(.WIDTH(58)) payload_owner (
        .clk_i(clk_i),.write_i(!reset_i && update_i),.data_i(payload_i),.data_o(payload));
    assign {tag_o,target_o,kind_o}=payload;
    always @(posedge clk_i) begin
        if(reset_i) valid_o<=0;
        else if(update_i) valid_o<=1;
    end
endmodule
'''


def predictor(t):
    start=t.index('    reg [1:0] bht [0:BHT_ENTRIES-1];')
    end=t.index('\n    wire [6:0] query_opcode',start)
    t=t[:start]+TABLES+t[end:]
    t=change(t,'    output reg  [31:0] prediction_count_o,','    output wire [31:0] prediction_count_o,')
    t=change(t,'    output reg  [31:0] correct_count_o','    output wire [31:0] correct_count_o')
    start=t.index('    always @(posedge clk_i) begin')
    end=t.index('\nendmodule',start)
    t=t[:start]+COUNTERS+t[end:]
    for old,new in [
        ('bht[query_bht_index]','query_bht_word[1:0]'),
        ('bht_trained[query_bht_index]','query_bht_word[2]'),
        ('btb_valid[query_btb_index]','query_btb_word[58]'),
        ('btb_tag[query_btb_index]','query_btb_word[57:34]'),
        ('btb_target[query_btb_index]','query_btb_word[33:2]'),
        ('btb_kind[query_btb_index]','query_btb_word[1:0]'),
    ]:
        if old not in t: raise ValueError('Missing query '+old)
        t=t.replace(old,new)
    # Indexed counter sign is written as a separate expression to avoid
    # nested packed selects in conservative Verilog-2005 frontends.
    t=t.replace('query_bht_word[1:0][1]','query_bht_word[1]')
    return t+ROW_MODULES


if __name__=='__main__':
    prepare('CB_predictor_row_owners',ROOT/'CA_direct_physical_producer_wakeup',{
        'rtl/predictor/rv32_branch_predictor.v':predictor,
    },'CA plus static BHT/BTB row owners, four-row feedback/query domains, 16-bit BTB payload holds and bounded counter reset/update; exact weakly-taken BHT reset, cold trained behavior, saturation, BTB tag/kind target and single feedback edge unchanged; no table sizes/extra FF/cycles, no EDA')
