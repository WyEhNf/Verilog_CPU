"""Prepare decoded low-rank issue selectors without HDL/EDA invocation."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def rs(source):
    source=change(source,
        '    wire [COUNT_WIDTH-1:0] ready_rank [0:ENTRIES-1];',
        '    wire [BE_WIDTH-1:0] ready_rank_match [0:ENTRIES-1];')
    begin=source.index('    // Compare ages independently of the late wakeup/ready signals.')
    end=source.index('    // Share tag comparisons and predecode first/last lane priority once per',begin)
    source=source[:begin]+'''    // The policy still counts older ready instructions. For up to four
    // issue lanes, propagate exact decoded counts 0..BE_WIDTH-1 instead of
    // a binary popcount followed by a late equality decoder. Overflow is
    // represented by ALL ZERO bits, never by a wrapping binary low slice.
    // A balanced convolution composes disjoint subtree count predicates.
    // Wider parameterizations keep the former binary implementation.
    localparam integer RANK_LEAVES = 2 ** SLOT_WIDTH;
    genvar rank_slot,rank_other,rank_node,rank_lane,rank_term;
    generate
        for(rank_slot=0;rank_slot<ENTRIES;rank_slot=rank_slot+1) begin:g_rank
            wire [RANK_LEAVES-1:0] older_ready;
            for(rank_other=0;rank_other<RANK_LEAVES;rank_other=rank_other+1) begin:g_leaf
                if(rank_other<ENTRIES && rank_other!=rank_slot) begin:g_compare
                    wire older=((AGE_ORDER_MATRIX!=0) && (ALLOC_STATIC_WRITE!=0)) ?
                        cached_age_precedes[rank_other][rank_slot] :
                        ((age_mem[rank_other]<age_mem[rank_slot]) ||
                         ((rank_other<rank_slot) && (age_mem[rank_other]==age_mem[rank_slot])));
                    assign older_ready[rank_other]=ready_candidates[rank_other] && older;
                end else begin:g_zero
                    assign older_ready[rank_other]=1'b0;
                end
            end
            if(BE_WIDTH<=4) begin:g_decoded_count
                wire [BE_WIDTH-1:0] count_match [1:2*RANK_LEAVES-1];
                for(rank_other=0;rank_other<RANK_LEAVES;rank_other=rank_other+1) begin:g_leaf
                    assign count_match[RANK_LEAVES+rank_other][0]=!older_ready[rank_other];
                    for(rank_lane=1;rank_lane<BE_WIDTH;rank_lane=rank_lane+1) begin:g_nonzero
                        if(rank_lane==1)
                            assign count_match[RANK_LEAVES+rank_other][rank_lane]=older_ready[rank_other];
                        else assign count_match[RANK_LEAVES+rank_other][rank_lane]=1'b0;
                    end
                end
                for(rank_node=1;rank_node<RANK_LEAVES;rank_node=rank_node+1) begin:g_combine
                    for(rank_lane=0;rank_lane<BE_WIDTH;rank_lane=rank_lane+1) begin:g_count
                        wire [rank_lane:0] alternatives;
                        for(rank_term=0;rank_term<=rank_lane;rank_term=rank_term+1) begin:g_split
                            assign alternatives[rank_term]=count_match[2*rank_node][rank_term] &&
                                count_match[2*rank_node+1][rank_lane-rank_term];
                        end
                        assign count_match[rank_node][rank_lane]=|alternatives;
                    end
                end
                assign ready_rank_match[rank_slot]=count_match[1];
            end else begin:g_binary_count
                wire [COUNT_WIDTH-1:0] count_tree [1:2*RANK_LEAVES-1];
                for(rank_other=0;rank_other<RANK_LEAVES;rank_other=rank_other+1) begin:g_leaf
                    assign count_tree[RANK_LEAVES+rank_other]=older_ready[rank_other];
                end
                for(rank_node=1;rank_node<RANK_LEAVES;rank_node=rank_node+1) begin:g_sum
                    assign count_tree[rank_node]=count_tree[2*rank_node]+count_tree[2*rank_node+1];
                end
                for(rank_lane=0;rank_lane<BE_WIDTH;rank_lane=rank_lane+1) begin:g_decode
                    assign ready_rank_match[rank_slot][rank_lane]=count_tree[1]==rank_lane;
                end
            end
        end
    endgenerate

'''+source[end:]
    source=change(source,
        '                assign selections[issue_row]=ready_candidates[issue_row] && ready_rank[issue_row]==issue_lane;',
        '                assign selections[issue_row]=ready_candidates[issue_row] && ready_rank_match[issue_row][issue_lane];')
    return source


if __name__=='__main__':
    prepare('CW_rs_decoded_low_rank', ROOT/'CV_lsq_parallel_report_destination',
            {'rtl/backend/rv32_reservation_station.v':rs},
            'Exact decoded older-ready counts for issue widths 1..4; overflow excluded, age order/ready/FF/latency unchanged; wider widths retain binary rank; no HDL/EDA tests')
