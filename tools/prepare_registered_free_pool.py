"""Prepare a separate reserved physical-register pool; no EDA or tests."""
from prepare_staged_frequency_candidate import change,prepare,ROOT


def reserved_pool(t):
    t=change(t,'    parameter integer RAT_READ_BYPASS = 0,',
             '    parameter integer RAT_READ_BYPASS = 0,\n    parameter integer REGISTERED_FREE_POOL = 0,')
    t=change(t,'    output wire [COUNT_WIDTH-1:0]         free_count_o,', '''    output wire [COUNT_WIDTH-1:0]         free_count_o,
    output wire [((BE_WIDTH<=1)?1:$clog2(BE_WIDTH+1))-1:0] allocatable_count_o,''')
    t=change(t,'    reg [PHYS_ADDR_WIDTH-1:0] free_candidate [0:BE_WIDTH-1];', '''    reg [PHYS_ADDR_WIDTH-1:0] raw_candidate [0:BE_WIDTH-1];
    wire [PHYS_ADDR_WIDTH-1:0] free_candidate [0:BE_WIDTH-1];
    reg [PHYS_ADDR_WIDTH-1:0] pool_candidate [0:BE_WIDTH-1];
    reg [RENAME_COUNT_WIDTH-1:0] pool_count;
    wire [PHYS_REGS-1:0] pool_bitmap;
    reg [PHYS_REGS-1:0] pool_reserve_mask;
    reg [RENAME_COUNT_WIDTH-1:0] pool_next_count;
    reg [BE_WIDTH*PHYS_ADDR_WIDTH-1:0] pool_next_payload;
    reg [BE_WIDTH-1:0] pool_write;
    integer pool_retained,pool_refilled,pool_row,pool_source;
    wire [COUNT_WIDTH-1:0] available_for_rename=(REGISTERED_FREE_POOL!=0)?pool_count:free_count;
    assign allocatable_count_o=(available_for_rename>BE_WIDTH)?BE_WIDTH:available_for_rename;
    genvar pool_index,pool_phys;
    generate for(pool_index=0;pool_index<BE_WIDTH;pool_index=pool_index+1) begin:g_pool_slot
        assign free_candidate[pool_index]=(REGISTERED_FREE_POOL!=0)?pool_candidate[pool_index]:raw_candidate[pool_index];
        wire local_write;
        rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
            .signal_i(REGISTERED_FREE_POOL!=0 && !reset_i && !restore_valid_i && pool_write[pool_index]),
            .views_o(local_write));
        always @(posedge clk_i) if(local_write)
            pool_candidate[pool_index]<=pool_next_payload[pool_index*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
    end
    for(pool_phys=0;pool_phys<PHYS_REGS;pool_phys=pool_phys+1) begin:g_pool_bitmap
        wire [BE_WIDTH-1:0] matches;
        for(pool_index=0;pool_index<BE_WIDTH;pool_index=pool_index+1) begin:g_match
            assign matches[pool_index]=(pool_index<pool_count) && pool_candidate[pool_index]==pool_phys;
        end
        assign pool_bitmap[pool_phys]=(pool_phys!=0) && (|matches);
    end endgenerate
    // The pool is not architectural allocation. Expose both unreserved and
    // reserved-but-unused registers as free so recovery never leaks them.
    always @* begin
        pool_retained=pool_count-alloc_count_comb;
        pool_refilled=0;
        pool_reserve_mask=0;pool_next_payload=0;pool_write=0;
        for(pool_row=0;pool_row<BE_WIDTH;pool_row=pool_row+1) begin
            if(pool_row<pool_retained) begin
                pool_source=pool_row+alloc_count_comb;
                pool_next_payload[pool_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]=pool_candidate[pool_source];
                pool_write[pool_row]=(alloc_count_comb!=0);
            end else begin
                pool_source=pool_row-pool_retained;
                if(pool_source>=0 && pool_source<BE_WIDTH && raw_candidate[pool_source]!=0) begin
                    pool_next_payload[pool_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]=raw_candidate[pool_source];
                    pool_reserve_mask[raw_candidate[pool_source]]=1'b1;
                    pool_write[pool_row]=1'b1;
                    pool_refilled=pool_refilled+1;
                end
            end
        end
        pool_next_count=pool_retained+pool_refilled;
    end
    always @(posedge clk_i) begin
        // Restore receives the complete logical free bitmap, including all
        // previous pool entries. Return them and refill from that new bitmap.
        if(reset_i || restore_valid_i || REGISTERED_FREE_POOL==0) pool_count<=0;
        else pool_count<=pool_next_count;
    end''')
    t=change(t,'    assign free_bitmap_state_o = free_bitmap;',
             '    assign free_bitmap_state_o = (REGISTERED_FREE_POOL!=0)?(free_bitmap | pool_bitmap):free_bitmap;')
    t=change(t,'            free_candidate[candidate_lane] =', '            raw_candidate[candidate_lane] =')
    t=change(t,'((alloc_used + 1) <= free_count)', '((alloc_used + 1) <= available_for_rename)')
    t=change(t,'            // Rename allocation advances RAT and the free-list head.', '''            if(REGISTERED_FREE_POOL!=0) free_bitmap<=free_bitmap & ~pool_reserve_mask;
            // Rename allocation advances RAT and consumes reserved entries.''')
    t=change(t,"                    free_bitmap[rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b0;", "                    if(REGISTERED_FREE_POOL==0)\n                        free_bitmap[rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b0;")
    return t


def enable_pool(t):
    t=change(t,'    reg [CREDIT_WIDTH-1:0] rob_credit, rs_credit, lsq_credit, phys_credit;', '''    reg [CREDIT_WIDTH-1:0] rob_credit, rs_credit, lsq_credit;
    // A registered reservoir count is already a ready boundary. Do not add
    // another conservative lag that would halve full-width allocation.
    wire [CREDIT_WIDTH-1:0] phys_credit;''')
    t=change(t,'rob_credit<=0;rs_credit<=0;lsq_credit<=0;phys_credit<=0;',
             'rob_credit<=0;rs_credit<=0;lsq_credit<=0;')
    t=change(t,"            phys_credit<=bounded_credit({{(16-FREE_COUNT_WIDTH){1'b0}},free_count},used_phys_credit);\n",'')
    t=change(t,'.RAT_READ_BYPASS(RAT_READ_BYPASS)) rename (',
             '.RAT_READ_BYPASS(RAT_READ_BYPASS), .REGISTERED_FREE_POOL(1)) rename (')
    t=change(t,'.free_bitmap_state_o(free_bitmap_state), .free_count_o(free_count),',
             '.free_bitmap_state_o(free_bitmap_state), .free_count_o(free_count), .allocatable_count_o(phys_credit),')
    return t


if __name__=='__main__':
    prepare('M_registered_free_pool',ROOT/'L1_repaired_icache_ports',
            {'rtl/rv32_rename_unit.v':reserved_pool,'rtl/backend/rv32_backend_joint.v':enable_pool},
            'Separate untested alternative: L1 plus four-slot reserved physical-register pool, registered allocation IDs/count, logical free bitmap including unused reservations and recovery return; no instruction stage added')
