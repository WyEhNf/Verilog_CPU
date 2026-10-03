"""Bound RS ranked-issue payload selection without changing wakeup latency."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


ISSUE = r'''
    // Rank/ready remain unchanged. A selection never drives an entire packet;
    // it is distributed into <=32-bit words before balanced payload reduction.
    localparam integer ISSUE_DATA_WIDTH=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+
        64+STORE_DATA_WIDTH+METADATA_WIDTH+SLOT_WIDTH;
    localparam integer ISSUE_DATA_WORDS=(ISSUE_DATA_WIDTH+31)/32;
    localparam integer ISSUE_DATA_LEAVES=1<<$clog2(ENTRIES);
    genvar issue_lane,issue_row,issue_word,issue_node;
    generate for(issue_lane=0;issue_lane<BE_WIDTH;issue_lane=issue_lane+1) begin:g_issue_payload
        wire [ENTRIES-1:0] selections;
        wire [ISSUE_DATA_WIDTH-1:0] payload_tree [1:2*ISSUE_DATA_LEAVES-1];
        for(issue_row=0;issue_row<ISSUE_DATA_LEAVES;issue_row=issue_row+1) begin:g_row
            if(issue_row<ENTRIES) begin:g_present
                wire [ISSUE_DATA_WORDS-1:0] selected_words;
                wire [ISSUE_DATA_WIDTH-1:0] payload={
                    op_mem[issue_row],pc_mem[issue_row],rob_tag_mem[issue_row],phys_rd_mem[issue_row],
                    src1_value_effective[issue_row],src2_value_effective[issue_row],
                    store_data_mem[issue_row],metadata_mem[issue_row],issue_row[SLOT_WIDTH-1:0]};
                assign selections[issue_row]=ready_candidates[issue_row] && ready_rank[issue_row]==issue_lane;
                rv32_frequency_control_tree #(.LEAVES(ISSUE_DATA_WORDS)) selection_tree (
                    .signal_i(selections[issue_row]),.views_o(selected_words));
                for(issue_word=0;issue_word<ISSUE_DATA_WORDS;issue_word=issue_word+1) begin:g_word
                    localparam integer LOW=issue_word*32;
                    localparam integer BITS=ISSUE_DATA_WIDTH-LOW>=32 ? 32 : ISSUE_DATA_WIDTH-LOW;
                    assign payload_tree[ISSUE_DATA_LEAVES+issue_row][LOW +: BITS]=
                        {BITS{selected_words[issue_word]}} & payload[LOW +: BITS];
                end
            end else begin:g_padding
                assign payload_tree[ISSUE_DATA_LEAVES+issue_row]=0;
            end
        end
        for(issue_node=1;issue_node<ISSUE_DATA_LEAVES;issue_node=issue_node+1) begin:g_or
            assign payload_tree[issue_node]=payload_tree[2*issue_node] | payload_tree[2*issue_node+1];
        end
        assign issue_valid_o[issue_lane]=|selections;
        assign {issue_op_o[issue_lane*OP_WIDTH +: OP_WIDTH],issue_pc_o[issue_lane*32 +: 32],
            issue_rob_tag_o[issue_lane*TAG_WIDTH +: TAG_WIDTH],issue_phys_rd_o[issue_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
            issue_src1_value_o[issue_lane*32 +: 32],issue_src2_value_o[issue_lane*32 +: 32],
            issue_store_data_o[issue_lane*STORE_DATA_WIDTH +: STORE_DATA_WIDTH],
            issue_metadata_o[issue_lane*METADATA_WIDTH +: METADATA_WIDTH],issue_slot_o[issue_lane*SLOT_WIDTH +: SLOT_WIDTH]}=payload_tree[1];
    end endgenerate

'''


def bounded_issue(t):
    names=['issue_valid_o','issue_op_o','issue_pc_o','issue_rob_tag_o','issue_phys_rd_o',
           'issue_src1_value_o','issue_src2_value_o','issue_store_data_o','issue_metadata_o','issue_slot_o']
    for name in names:
        pattern=re.compile(r'output reg(\s+\[[^\n]*\]\s+)'+name+r'\b')
        t,n=pattern.subn(r'output wire\1'+name,t)
        if n!=1:
            raise ValueError('Ambiguous issue port: '+name)
    start=t.index("        issue_valid_o = {BE_WIDTH{1'b0}};")
    stop=t.index('\n    end\n\n    // Keep issue selection',start)
    t=t[:start]+t[stop:]
    marker='    // Allocate a contiguous prefix and choose the oldest ready entries for'
    return change(t,marker,ISSUE+marker)


def initialize_scratch(t):
    return change(t,'        for(bank_default_row=0;bank_default_row<LSQ_ENTRIES;bank_default_row=bank_default_row+1) begin',
                  '        bank_retirement_slot=0;bank_retirement_lane=0;\n'
                  '        for(bank_default_row=0;bank_default_row<LSQ_ENTRIES;bank_default_row=bank_default_row+1) begin')


if __name__=='__main__':
    prepare('AI_bounded_rs_issue_payload',ROOT/'AH_lsq_local_wide_events',
            {'rtl/backend/rv32_reservation_station.v':bounded_issue,
             'rtl/backend/rv32_lsq.v':initialize_scratch},
            'AH plus bounded-word and balanced-OR RS ranked-issue payload selection; identical ready/rank, current-cycle wake bypass and downstream-independent issue valid; no added register/cycle; initialize private LSQ retirement temporaries; no EDA run')
