"""Select all pool refill IDs concurrently using grouped ranks; no EDA."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


def parallel_refill(t):
    t=change(t,'    reg [PHYS_ADDR_WIDTH-1:0] raw_candidate [0:BE_WIDTH-1];',
               '    wire [PHYS_ADDR_WIDTH-1:0] raw_candidate [0:BE_WIDTH-1];')
    start=t.index('    always @* begin\n        candidate_free_bitmap = free_bitmap;')
    stop=t.index('    // Work on a temporary RAT',start)
    return t[:start]+r'''    localparam integer REFILL_GROUP_LEAVES=(FREE_GROUPS<=1)?1:(1<<$clog2(FREE_GROUPS));
    localparam integer REFILL_PHYS_LEAVES=(PHYS_REGS<=1)?1:(1<<$clog2(PHYS_REGS));
    wire [3:0] refill_group_count [0:FREE_GROUPS-1];
    wire [COUNT_WIDTH-1:0] refill_group_before [0:FREE_GROUPS-1];
    wire [2:0] refill_local_before [0:PHYS_REGS-1];
    wire [COUNT_WIDTH-1:0] refill_rank [0:PHYS_REGS-1];
    genvar refill_group,refill_row,refill_bit,refill_node,refill_lane;
    generate
        for(refill_group=0;refill_group<FREE_GROUPS;refill_group=refill_group+1) begin:g_refill_group
            wire [3:0] group_tree [1:15];
            wire [COUNT_WIDTH-1:0] prefix_tree [1:2*REFILL_GROUP_LEAVES-1];
            for(refill_bit=0;refill_bit<8;refill_bit=refill_bit+1) begin:g_leaf
                if(refill_group*8+refill_bit<PHYS_REGS)
                    assign group_tree[8+refill_bit]=free_bitmap[refill_group*8+refill_bit];
                else assign group_tree[8+refill_bit]=0;
            end
            for(refill_node=1;refill_node<8;refill_node=refill_node+1) begin:g_sum
                assign group_tree[refill_node]=group_tree[2*refill_node]+group_tree[2*refill_node+1];
            end
            assign refill_group_count[refill_group]=group_tree[1];
            for(refill_bit=0;refill_bit<REFILL_GROUP_LEAVES;refill_bit=refill_bit+1) begin:g_prefix_leaf
                if(refill_bit<refill_group)
                    assign prefix_tree[REFILL_GROUP_LEAVES+refill_bit]=refill_group_count[refill_bit];
                else assign prefix_tree[REFILL_GROUP_LEAVES+refill_bit]=0;
            end
            for(refill_node=1;refill_node<REFILL_GROUP_LEAVES;refill_node=refill_node+1) begin:g_prefix_sum
                assign prefix_tree[refill_node]=prefix_tree[2*refill_node]+prefix_tree[2*refill_node+1];
            end
            assign refill_group_before[refill_group]=prefix_tree[1];
        end
        for(refill_row=0;refill_row<PHYS_REGS;refill_row=refill_row+1) begin:g_refill_rank
            localparam integer GROUP=refill_row/8;
            localparam integer OFFSET=refill_row%8;
            wire [2:0] local_tree [1:15];
            for(refill_bit=0;refill_bit<8;refill_bit=refill_bit+1) begin:g_leaf
                if(refill_bit<OFFSET) assign local_tree[8+refill_bit]=free_bitmap[GROUP*8+refill_bit];
                else assign local_tree[8+refill_bit]=0;
            end
            for(refill_node=1;refill_node<8;refill_node=refill_node+1) begin:g_sum
                assign local_tree[refill_node]=local_tree[2*refill_node]+local_tree[2*refill_node+1];
            end
            assign refill_local_before[refill_row]=local_tree[1];
            assign refill_rank[refill_row]=refill_group_before[GROUP]+refill_local_before[refill_row];
        end
        for(refill_lane=0;refill_lane<BE_WIDTH;refill_lane=refill_lane+1) begin:g_refill_select
            wire [PHYS_ADDR_WIDTH-1:0] encoded [1:2*REFILL_PHYS_LEAVES-1];
            for(refill_row=0;refill_row<REFILL_PHYS_LEAVES;refill_row=refill_row+1) begin:g_leaf
                if(refill_row<PHYS_REGS) begin:g_present
                    wire selected=free_bitmap[refill_row] && refill_rank[refill_row]==refill_lane;
                    assign encoded[REFILL_PHYS_LEAVES+refill_row]={PHYS_ADDR_WIDTH{selected}} &
                        refill_row[PHYS_ADDR_WIDTH-1:0];
                end else begin:g_padding
                    assign encoded[REFILL_PHYS_LEAVES+refill_row]=0;
                end
            end
            for(refill_node=1;refill_node<REFILL_PHYS_LEAVES;refill_node=refill_node+1) begin:g_or
                assign encoded[refill_node]=encoded[2*refill_node] | encoded[2*refill_node+1];
            end
            // No hit gives the existing zero sentinel. A hit is unique:
            // it is precisely the kth lowest free bit, as in the old chain.
            assign raw_candidate[refill_lane]=encoded[1];
        end
    endgenerate

''' +t[stop:]


if __name__=='__main__':
    prepare('Z_parallel_free_pool_refill', ROOT/'Y_parallel_rs_vacancy_allocation',
            {'rtl/rv32_rename_unit.v':parallel_refill},
            'Y plus grouped population counts and concurrent kth-free ID encoding for all refill lanes; same lowest-free order and zero sentinel, removes serial candidate-mask dependency, no register bits or cycles added; no EDA run')
