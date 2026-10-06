"""Bound frontend queue payload read/write selectors; no EDA or cycle change."""
from prepare_staged_frequency_candidate import ROOT, prepare


READS = r'''
    localparam integer READ_DATA_WIDTH=PACKET_WIDTH+16;
    localparam integer READ_WORDS=(READ_DATA_WIDTH+31)/32;
    localparam integer READ_LEAVES=1<<$clog2(FQ_DEPTH);
    wire [FQ_DEPTH*FE_WIDTH*READ_WORDS-1:0] head_word_select;
    genvar read_row,read_lane,read_word,read_node;
    generate
        for(read_row=0;read_row<FQ_DEPTH;read_row=read_row+1) begin:g_head_decode
            localparam [PTR_WIDTH-1:0] ROW=read_row;
            assign head_row_select[read_row]=head_reg==ROW;
            rv32_frequency_control_tree #(.LEAVES(FE_WIDTH*READ_WORDS)) selection_tree (
                .signal_i(head_row_select[read_row]),
                .views_o(head_word_select[read_row*FE_WIDTH*READ_WORDS +: FE_WIDTH*READ_WORDS]));
        end
        for(read_lane=0;read_lane<FE_WIDTH;read_lane=read_lane+1) begin:g_packet_read
            wire [READ_DATA_WIDTH-1:0] payload_tree [1:2*READ_LEAVES-1];
            for(read_row=0;read_row<READ_LEAVES;read_row=read_row+1) begin:g_row
                if(read_row<FQ_DEPTH) begin:g_present
                    localparam integer HEAD_ROW=(read_row+FQ_DEPTH-read_lane)%FQ_DEPTH;
                    wire [READ_DATA_WIDTH-1:0] payload={
                        `RV32IM_FETCH_PACKET_PACK(fq_pc[read_row],fq_inst[read_row],
                            fq_pred_taken[read_row],fq_pred_target[read_row],fq_pred_kind[read_row],
                            fq_pred_btb_hit[read_row],fq_epoch[read_row]),
                        ((PREDICTOR_META!=0)?fq_pred_metadata[read_row]:16'b0)};
                    for(read_word=0;read_word<READ_WORDS;read_word=read_word+1) begin:g_word
                        localparam integer LOW=read_word*32;
                        localparam integer BITS=READ_DATA_WIDTH-LOW>=32 ? 32 : READ_DATA_WIDTH-LOW;
                        assign payload_tree[READ_LEAVES+read_row][LOW +: BITS]=
                            {BITS{head_word_select[(HEAD_ROW*FE_WIDTH+read_lane)*READ_WORDS+read_word]}} & payload[LOW +: BITS];
                    end
                end else begin:g_padding
                    assign payload_tree[READ_LEAVES+read_row]=0;
                end
            end
            for(read_node=1;read_node<READ_LEAVES;read_node=read_node+1) begin:g_or
                assign payload_tree[read_node]=payload_tree[2*read_node] | payload_tree[2*read_node+1];
            end
            assign {queue_read_packets[read_lane*PACKET_WIDTH +: PACKET_WIDTH],
                queue_read_metadata[read_lane*16 +: 16]}=payload_tree[1];
        end
    endgenerate
'''


BANK = r'''
// Functional payload state remains visible to pruning. Local event selection
// and word ownership bound the actual payload consumers of every control leaf.
module rv32_frontend_queue_payload_bank #(
    parameter integer WIDTH=32,FE_WIDTH=4,PTR_WIDTH=4,ROW_ID=0
) (
    input wire clk_i,reset_i,redirect_i,
    input wire [FE_WIDTH-1:0] write_valid_i,
    input wire [FE_WIDTH*PTR_WIDTH-1:0] write_slots_i,
    input wire [FE_WIDTH*WIDTH-1:0] write_data_i,
    output wire [WIDTH-1:0] data_o
);
    wire [FE_WIDTH-1:0] selected;
    wire write_qualified;
    wire [WIDTH-1:0] payload;
    genvar lane;
    generate for(lane=0;lane<FE_WIDTH;lane=lane+1) begin:g_lane
        assign selected[lane]=write_valid_i[lane] && write_slots_i[lane*PTR_WIDTH +: PTR_WIDTH]==ROW_ID;
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(WIDTH),.EVENTS(FE_WIDTH)) selector (
        .events_i(selected),.values_i(write_data_i),.write_o(write_qualified),.value_o(payload));
    // Occupancy owns reset/redirect invalidation. Each newly valid row has
    // a complete payload write, matching the existing frontend contract.
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) state_owner (
        .clk_i(clk_i),.write_i(write_qualified),.data_i(payload),.data_o(data_o));
endmodule
'''


def bounded(t):
    start=t.index('    genvar read_row, read_lane;')
    stop=t.index('\n    localparam integer PAYLOAD_WIDTH',start)
    t=t[:start]+READS+t[stop:]
    start=t.index('module rv32_frontend_queue_payload_bank #(')
    return t[:start]+BANK


if __name__=='__main__':
    prepare('AJ_bounded_frontend_payload',ROOT/'AI_bounded_rs_issue_payload',
            {'rtl/frontend/rv32_fetch_frontend.v':bounded},
            'AI plus frontend queue head selection distributed per output lane/32-bit word, balanced packet OR trees, bounded last-lane write event selection and word-owned storage; same state/redirect/throughput/cycle behavior, no EDA run')
