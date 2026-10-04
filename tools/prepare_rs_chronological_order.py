"""Maintain RS chronology directly on allocation instead of age arithmetic."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


ORDER = r'''
    // Mode 2 tracks relative allocation order, independent of a wrapping
    // numeric counter. Allocation maps accepted lanes in order to increasing
    // free row numbers: when both rows are new, the lower row is older.
    // If only one row is new, every still-valid old row precedes it.
    // Pair bits need no reset: before two rows can both be valid, allocation
    // has written their relation. Ready filtering excludes invalid rows.
    generate if(AGE_ORDER_MATRIX==2 && ALLOC_STATIC_WRITE!=0) begin:g_chronological_order
        localparam integer ORDER_DOMAINS=(ENTRIES+3)/4;
        wire [ENTRIES-1:0] row_allocations;
        wire [ORDER_DOMAINS*ENTRIES-1:0] allocation_views;
        rv32_frequency_control_tree #(.WIDTH(ENTRIES),.LEAVES(ORDER_DOMAINS)) allocation_tree (
            .signal_i(row_allocations),.views_o(allocation_views));
        for(pair_low=0;pair_low<ENTRIES;pair_low=pair_low+1) begin:g_low
            assign row_allocations[pair_low]=!reset_i && !flush_valid_i && alloc_row_write[pair_low];
            assign cached_age_precedes[pair_low][pair_low]=1'b0;
            for(pair_high=pair_low+1;pair_high<ENTRIES;pair_high=pair_high+1) begin:g_high
                // Choose each source's view by the other row's group, so a
                // leaf allocation control updates at most four pair bits.
                wire low_new=allocation_views[(pair_high/4)*ENTRIES+pair_low];
                wire high_new=allocation_views[(pair_low/4)*ENTRIES+pair_high];
                wire low_precedes_high;
                rv32_frequency_word_bank #(.WIDTH(1)) order_owner (
                    .clk_i(clk_i),.write_i(low_new || high_new),.data_i(high_new),.data_o(low_precedes_high));
                assign cached_age_precedes[pair_low][pair_high]=low_precedes_high;
                assign cached_age_precedes[pair_high][pair_low]=!low_precedes_high;
            end
        end
    end endgenerate
'''


def station(t):
    t=change(t,'    parameter integer AGE_ORDER_MATRIX = 0,',
             '''    // 0: numeric comparison, 1: cached numeric comparison,
    // 2: relative allocation-order matrix (requires static allocation).
    parameter integer AGE_ORDER_MATRIX = 0,''')
    t=change(t,'wire [AGE_WIDTH-1:0] lane_age = age_counter + al;',
             'wire [AGE_WIDTH-1:0] lane_age = (AGE_ORDER_MATRIX==2) ? 0 : age_counter + al;')
    t=change(t,'generate if ((AGE_ORDER_MATRIX != 0) && (ALLOC_STATIC_WRITE != 0)) begin : g_age_order_matrix',
             'generate if ((AGE_ORDER_MATRIX == 1) && (ALLOC_STATIC_WRITE != 0)) begin : g_age_order_matrix')
    return change(t,'    genvar owner_row, owner_lane;',ORDER+'\n    genvar owner_row, owner_lane;')


def backend(t):
    return change(t,'.AGE_ORDER_MATRIX(1), .LOCAL_PAYLOAD_ROWS(1)',
                  '.AGE_ORDER_MATRIX(2), .LOCAL_PAYLOAD_ROWS(1)')


if __name__=='__main__':
    prepare('BR_rs_chronological_order',ROOT/'BQ_bounded_branch_feedback',{
        'rtl/backend/rv32_reservation_station.v':station,
        'rtl/backend/rv32_backend_joint.v':backend,
    },'BQ plus direct allocation-order RS age matrix: reuse the current 66 pair bits at twelve rows, update pairs with which row is new rather than numeric age arithmetic/comparators; both-new order follows proven increasing-free-row/accepted-lane allocation, old survivors retain relation; pair flags unreset and valid-qualified, controls grouped by four peer rows; current numeric age payload/counter no longer consumed and can prune; no new FF/cycles, scheduling differs at numeric wrap/ties and IPC remains unmeasured; no EDA')
