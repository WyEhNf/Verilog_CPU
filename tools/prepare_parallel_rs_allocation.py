"""Replace the four serial RS vacancy walks with parallel ranks; no tests."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


def parallel_slots(t):
    t=change(t,'    reg [SLOT_WIDTH-1:0] allocation_slots [0:BE_WIDTH-1];',
               '    wire [SLOT_WIDTH-1:0] allocation_slots [0:BE_WIDTH-1];')
    start=t.index('        always @* begin\n            pick_cursor = 0;')
    stop=t.index('        for (al = 0; al < BE_WIDTH; al = al + 1) begin : g_payload',start)
    t=t[:start]+r'''        localparam integer SLOT_LEAVES=1<<$clog2(ENTRIES);
        localparam integer LANE_LEAVES=(BE_WIDTH<=1)?1:(1<<$clog2(BE_WIDTH));
        wire [COUNT_WIDTH-1:0] free_before [0:ENTRIES-1];
        wire [COUNT_WIDTH-1:0] accepted_before [0:BE_WIDTH-1];
        wire [BE_WIDTH-1:0] slot_grants [0:ENTRIES-1];
        genvar rank_row,rank_lane,rank_source,rank_node;
        // The kth accepted lane owns the kth free physical row. Both counts
        // use balanced population-count trees; no lane waits for another
        // lane's encoded slot or search cursor.
        for(rank_row=0;rank_row<ENTRIES;rank_row=rank_row+1) begin:g_free_rank
            wire [COUNT_WIDTH-1:0] tree [1:2*SLOT_LEAVES-1];
            for(rank_source=0;rank_source<SLOT_LEAVES;rank_source=rank_source+1) begin:g_leaf
                if(rank_source<rank_row) assign tree[SLOT_LEAVES+rank_source]=!valid_mem[rank_source];
                else assign tree[SLOT_LEAVES+rank_source]=0;
            end
            for(rank_node=1;rank_node<SLOT_LEAVES;rank_node=rank_node+1) begin:g_sum
                assign tree[rank_node]=tree[2*rank_node]+tree[2*rank_node+1];
            end
            assign free_before[rank_row]=tree[1];
            for(rank_lane=0;rank_lane<BE_WIDTH;rank_lane=rank_lane+1) begin:g_grant
                assign slot_grants[rank_row][rank_lane]=!valid_mem[rank_row] &&
                    alloc_fire_o[rank_lane] && free_before[rank_row]==accepted_before[rank_lane];
            end
        end
        for(rank_lane=0;rank_lane<BE_WIDTH;rank_lane=rank_lane+1) begin:g_lane_rank
            wire [COUNT_WIDTH-1:0] count_tree [1:2*LANE_LEAVES-1];
            wire [SLOT_WIDTH-1:0] slot_tree [1:2*SLOT_LEAVES-1];
            for(rank_source=0;rank_source<LANE_LEAVES;rank_source=rank_source+1) begin:g_count_leaf
                if(rank_source<rank_lane) assign count_tree[LANE_LEAVES+rank_source]=alloc_fire_o[rank_source];
                else assign count_tree[LANE_LEAVES+rank_source]=0;
            end
            for(rank_node=1;rank_node<LANE_LEAVES;rank_node=rank_node+1) begin:g_count_sum
                assign count_tree[rank_node]=count_tree[2*rank_node]+count_tree[2*rank_node+1];
            end
            assign accepted_before[rank_lane]=count_tree[1];
            for(rank_source=0;rank_source<SLOT_LEAVES;rank_source=rank_source+1) begin:g_slot_leaf
                if(rank_source<ENTRIES)
                    assign slot_tree[SLOT_LEAVES+rank_source]={SLOT_WIDTH{slot_grants[rank_source][rank_lane]}} &
                        rank_source[SLOT_WIDTH-1:0];
                else assign slot_tree[SLOT_LEAVES+rank_source]=0;
            end
            for(rank_node=1;rank_node<SLOT_LEAVES;rank_node=rank_node+1) begin:g_slot_or
                assign slot_tree[rank_node]=slot_tree[2*rank_node] | slot_tree[2*rank_node+1];
            end
            assign allocation_slots[rank_lane]=slot_tree[1];
        end
''' +t[stop:]
    t=change(t,'                assign allocation_match_bits[al] = alloc_fire_o[al] && allocation_slots[al] == ar;',
               '                assign allocation_match_bits[al] = slot_grants[ar][al];')
    return t


if __name__=='__main__':
    prepare('Y_parallel_rs_vacancy_allocation', ROOT/'X_local_rename_state',
            {'rtl/backend/rv32_reservation_station.v':parallel_slots},
            'X plus balanced parallel free-row and accepted-lane ranks, preserving kth-accepted to kth-lowest-free allocation and cached-age grants; removes serial four-lane slot search, no extra register bits or cycles, no EDA run')
