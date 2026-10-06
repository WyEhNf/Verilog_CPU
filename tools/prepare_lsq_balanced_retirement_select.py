"""Balanced LSQ load report, store admission and ACK selection, no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare


SELECTORS = r'''
    // Load reporting follows queue age; store admission preserves the former
    // lowest physical-slot priority. Neither selection is a serial scan.
    localparam integer REPORT_ROWS=(LSQ_ENTRIES<=1)?1:(1<<$clog2(LSQ_ENTRIES));
    localparam integer REPORT_WIDTH=ROB_TAG_WIDTH+TAG_WIDTH+33;
    localparam integer ACK_WIDTH=ROB_TAG_WIDTH+TAG_WIDTH+1;
    localparam integer REPORT_WORDS=(REPORT_WIDTH+31)/32;
    localparam integer ACK_WORDS=(ACK_WIDTH+31)/32;
    wire report_valid_tree [1:2*REPORT_ROWS-1];
    wire [SLOT_WIDTH-1:0] report_slot_tree [1:2*REPORT_ROWS-1],report_age_tree [1:2*REPORT_ROWS-1];
    wire commit_valid_tree [1:2*REPORT_ROWS-1];
    wire [SLOT_WIDTH-1:0] commit_slot_tree [1:2*REPORT_ROWS-1];
    wire [REPORT_WIDTH-1:0] report_payload_tree [1:2*REPORT_ROWS-1];
    wire [ACK_WIDTH-1:0] ack_payload_tree [1:2*REPORT_ROWS-1];
    wire ack_valid_tree [1:2*REPORT_ROWS-1];
    genvar report_row,report_word,report_node;
    generate
        for(report_row=0;report_row<REPORT_ROWS;report_row=report_row+1) begin:g_report_row
            if(report_row<LSQ_ENTRIES) begin:g_present
                wire [REPORT_WORDS-1:0] report_select;
                wire [ACK_WORDS-1:0] ack_select;
                wire [REPORT_WIDTH-1:0] report_payload={complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};
                wire [ACK_WIDTH-1:0] ack_payload={store_ack_error_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};
                assign report_valid_tree[REPORT_ROWS+report_row]=entry_age[report_row]<occupancy_reg &&
                    valid_mem[report_row] && load_mem[report_row] && complete_mem[report_row] && !load_reported_mem[report_row];
                assign report_slot_tree[REPORT_ROWS+report_row]=report_row;
                assign report_age_tree[REPORT_ROWS+report_row]=entry_age[report_row];
                assign commit_valid_tree[REPORT_ROWS+report_row]=valid_mem[report_row] && store_mem[report_row] &&
                    addr_ready_mem[report_row] && data_ready_mem[report_row] && !store_commit_mem[report_row] &&
                    rob_tag_mem[report_row]==store_commit_rob_tag_i;
                assign commit_slot_tree[REPORT_ROWS+report_row]=report_row;
                assign ack_valid_tree[REPORT_ROWS+report_row]=occupancy_reg!=0 && head_reg==report_row &&
                    valid_mem[report_row] && store_mem[report_row] && store_ack_mem[report_row];
                rv32_frequency_control_tree #(.LEAVES(REPORT_WORDS)) report_selection_tree (
                    .signal_i(report_valid_tree[1] && report_slot_tree[1]==report_row),.views_o(report_select));
                rv32_frequency_control_tree #(.LEAVES(ACK_WORDS)) ack_selection_tree (
                    .signal_i(ack_valid_tree[REPORT_ROWS+report_row]),.views_o(ack_select));
                for(report_word=0;report_word<REPORT_WORDS;report_word=report_word+1) begin:g_result_word
                    localparam integer LOW=report_word*32;
                    localparam integer BITS=REPORT_WIDTH-LOW>=32?32:REPORT_WIDTH-LOW;
                    assign report_payload_tree[REPORT_ROWS+report_row][LOW +: BITS]=
                        {BITS{report_select[report_word]}} & report_payload[LOW +: BITS];
                end
                for(report_word=0;report_word<ACK_WORDS;report_word=report_word+1) begin:g_ack_word
                    localparam integer LOW=report_word*32;
                    localparam integer BITS=ACK_WIDTH-LOW>=32?32:ACK_WIDTH-LOW;
                    assign ack_payload_tree[REPORT_ROWS+report_row][LOW +: BITS]=
                        {BITS{ack_select[report_word]}} & ack_payload[LOW +: BITS];
                end
            end else begin:g_padding
                assign report_valid_tree[REPORT_ROWS+report_row]=0;
                assign report_slot_tree[REPORT_ROWS+report_row]=0;
                assign report_age_tree[REPORT_ROWS+report_row]=0;
                assign commit_valid_tree[REPORT_ROWS+report_row]=0;
                assign commit_slot_tree[REPORT_ROWS+report_row]=0;
                assign report_payload_tree[REPORT_ROWS+report_row]=0;
                assign ack_payload_tree[REPORT_ROWS+report_row]=0;
                assign ack_valid_tree[REPORT_ROWS+report_row]=0;
            end
        end
        for(report_node=1;report_node<REPORT_ROWS;report_node=report_node+1) begin:g_report_merge
            wire choose_left=report_valid_tree[2*report_node] &&
                (!report_valid_tree[2*report_node+1] || report_age_tree[2*report_node]<=report_age_tree[2*report_node+1]);
            assign report_valid_tree[report_node]=report_valid_tree[2*report_node] || report_valid_tree[2*report_node+1];
            assign report_slot_tree[report_node]=choose_left?report_slot_tree[2*report_node]:report_slot_tree[2*report_node+1];
            assign report_age_tree[report_node]=choose_left?report_age_tree[2*report_node]:report_age_tree[2*report_node+1];
            assign commit_valid_tree[report_node]=commit_valid_tree[2*report_node] || commit_valid_tree[2*report_node+1];
            assign commit_slot_tree[report_node]=commit_valid_tree[2*report_node]?
                commit_slot_tree[2*report_node]:commit_slot_tree[2*report_node+1];
            assign report_payload_tree[report_node]=report_payload_tree[2*report_node] | report_payload_tree[2*report_node+1];
            assign ack_payload_tree[report_node]=ack_payload_tree[2*report_node] | ack_payload_tree[2*report_node+1];
            assign ack_valid_tree[report_node]=ack_valid_tree[2*report_node] || ack_valid_tree[2*report_node+1];
        end
    endgenerate
'''


def balanced(t):
    start=t.index('        // ROB presents stores in architectural order.')
    stop=t.index('\n        // The eligibility bits above',start)
    admission='''        // Preserve lowest physical-slot matching priority, with a balanced selector.
        commit_slot_found=!flush_i && occupancy_reg!=0 && commit_valid_tree[1];
        store_commit_ready_o=commit_slot_found;
        commit_slot_select=commit_slot_found?commit_slot_tree[1]:0;
'''
    t=t[:start]+admission+t[stop:]
    start=t.index('    always @* begin\n        load_complete_valid_o')
    stop=t.index('\n\n    // Wide payload fields',start)
    outputs='''
    always @* begin
        complete_slot_found=report_valid_tree[1];
        complete_slot_select=complete_slot_found?report_slot_tree[1]:head_reg;
        load_complete_valid_o=complete_slot_found;
        {load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];
        store_ack_valid_o=ack_valid_tree[1];
        {store_ack_error_o,store_ack_lsq_tag_o,store_ack_rob_tag_o}=ack_payload_tree[1];
    end
'''
    return t[:start]+SELECTORS+outputs+t[stop:]


if __name__=='__main__':
    prepare('AS_lsq_balanced_report_and_admission',ROOT/'AR_producer_validity_owned_payload',
            {'rtl/backend/rv32_lsq.v':balanced},
            'AR plus balanced oldest-age completed-load report and lowest-physical-slot store-admission trees; report/ACK payloads use qualified per-word selections and balanced OR, invalid outputs remain zero; preserves bypass over waiting committed stores, head ACK, head pop and no extra FF/cycles; no EDA')
