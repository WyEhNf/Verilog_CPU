`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parameterized reservation station used for INT, MUL and DIV classes.
// The class-specific instances share this state/selection contract.
module rv32_reservation_station #(
    parameter integer RELEASE_CREDITS = 0,
    // 0: saved rows only; 1: empty queue fallthrough; 2: fill unused issue lanes.
    parameter integer ALLOC_EMPTY_BYPASS = 0,
    // A fresh invalid packet may show lane 0. Actual grants still own validity.
    parameter integer FRESH_DEFAULT_LANE_DATA = 0,
    // metadata[31:0] is the exact immediate of this allocated instruction.
    parameter integer ARITHMETIC_PRECOMPUTE = 0,
    parameter integer COMPARISON_PRECOMPUTE = 0,
    parameter integer PC_PRECOMPUTE = 0,
    parameter integer OCCUPANCY_DELTA_SELECT = 0,
    parameter integer QUALIFIED_OPERAND_WRITE = 0,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer ENTRIES = 8,
    parameter integer OP_WIDTH = `RV32IM_OP_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer SOURCE_TAG_WIDTH = TAG_WIDTH,
    // Only select this for a bus containing one live producer per physical
    // destination; generic callers retain first/last duplicate-tag priority.
    parameter WAKE_UNIQUE_OWNER = 0,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer WAKE_WIDTH = BE_WIDTH,
    parameter integer STORE_DATA_WIDTH = 32,
    parameter integer METADATA_WIDTH = 1,
    parameter integer WAKE_MUX_IMPL = 0,
    // Only the read-only store-address probe uses saved operands. Ordinary
    // issue continues to fold current-cycle wakeups into both operands.
    parameter REGISTERED_BASE_PROBE = 0,
    parameter integer ALLOC_STATIC_WRITE = 0,
    // 0: numeric comparison, 1: cached numeric comparison,
    // 2: relative allocation-order matrix (requires static allocation).
    parameter integer AGE_ORDER_MATRIX = 0,
    parameter integer LOCAL_PAYLOAD_ROWS = 0,
    // Caller filters recovery-edge issue to retained, live older rows.
    // Allocation stays blocked; accepted retained rows must leave exactly once.
    parameter RECOVERY_ISSUE_RELEASE = 0,
    // Combinational row predicate selected with the original issue payload.
    // This does not filter ready candidates or change their age/rank policy.
    parameter ISSUE_RECOVERY_QUALIFICATION = 0,
    parameter ISSUE_RECOVERY_CANCEL = 0,
    parameter integer SLOT_WIDTH = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES),
    parameter integer AGE_WIDTH = 32
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire [BE_WIDTH-1:0]           alloc_valid_i,
    input  wire [(BE_WIDTH*OP_WIDTH)-1:0] alloc_op_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_pc_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_rob_tag_i,
    input  wire [BE_WIDTH-1:0]           alloc_target_live_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_phys_rd_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_src1_value_i,
    input  wire [(BE_WIDTH*SOURCE_TAG_WIDTH)-1:0] alloc_src1_tag_i,
    input  wire [BE_WIDTH-1:0]           alloc_src1_ready_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_src2_value_i,
    input  wire [(BE_WIDTH*SOURCE_TAG_WIDTH)-1:0] alloc_src2_tag_i,
    input  wire [BE_WIDTH-1:0]           alloc_src2_ready_i,
    input  wire [(BE_WIDTH*STORE_DATA_WIDTH)-1:0] alloc_store_data_i,
    input  wire [(BE_WIDTH*METADATA_WIDTH)-1:0] alloc_metadata_i,
    output wire [((BE_WIDTH<=1)?1:$clog2(BE_WIDTH+1))-1:0] allocation_release_count_o,
    output wire                         alloc_ready_o,
    output reg  [BE_WIDTH-1:0]           alloc_fire_o,
    output reg  [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] alloc_count_o,

    input  wire [WAKE_WIDTH-1:0]           wake_valid_i,
    input  wire [(WAKE_WIDTH*SOURCE_TAG_WIDTH)-1:0] wake_tag_i,
    input  wire [(WAKE_WIDTH*32)-1:0]      wake_value_i,

    input  wire [BE_WIDTH-1:0]           issue_ready_i,
    input  wire [ENTRIES-1:0]            entry_recovery_qualified_i,
    output wire [BE_WIDTH-1:0]           issue_recovery_qualified_o,
    input  wire [ENTRIES-1:0]            entry_issue_cancel_i,
    output wire [BE_WIDTH-1:0]           issue_cancel_o,
    output wire  [BE_WIDTH-1:0]           issue_valid_o,
    output wire  [(BE_WIDTH*OP_WIDTH)-1:0] issue_op_o,
    output wire  [(BE_WIDTH*32)-1:0]      issue_pc_o,
    output wire  [(BE_WIDTH*TAG_WIDTH)-1:0] issue_rob_tag_o,
    output wire  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] issue_phys_rd_o,
    output wire  [(BE_WIDTH*32)-1:0]      issue_src1_value_o,
    output wire  [(BE_WIDTH*32)-1:0]      issue_src2_value_o,
    output wire  [(BE_WIDTH*STORE_DATA_WIDTH)-1:0] issue_store_data_o,
    output wire  [(BE_WIDTH*METADATA_WIDTH)-1:0] issue_metadata_o,
    output wire [BE_WIDTH*32-1:0] issue_arithmetic_o,
    output wire [BE_WIDTH*3-1:0] issue_comparison_o,
    output wire [BE_WIDTH*64-1:0] issue_pc_arithmetic_o,
    output wire  [(BE_WIDTH*SLOT_WIDTH)-1:0] issue_slot_o,

    input  wire                         flush_valid_i,
    input  wire [ENTRIES-1:0]            flush_kill_mask_i,
    output wire [ENTRIES-1:0]            entry_valid_o,
    output wire [(ENTRIES*TAG_WIDTH)-1:0] entry_rob_tag_o,
    // A read-only base operand view. REGISTERED_BASE_PROBE separates
    // the opportunistic address probe from current-cycle CDB bypass.

    // Store address probing does not consume an issue slot or dequeue work.
    output wire [ENTRIES-1:0]            entry_base_ready_o,
    output wire [(ENTRIES*32)-1:0]       entry_base_value_o,
    output wire [(ENTRIES*METADATA_WIDTH)-1:0] entry_metadata_o,
    output wire [((ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1))-1:0] occupancy_o,
    // Read-only identities/events of existing state changes. No new RS state.
    output wire [BE_WIDTH*SLOT_WIDTH-1:0] alloc_slot_o,
    output wire [ENTRIES-1:0] entry_release_o
);
    localparam integer COUNT_WIDTH = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1);
    localparam integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);

    reg valid_mem [0:ENTRIES-1];
    wire target_live_mem [0:ENTRIES-1];
    reg target_live_mem_legacy [0:ENTRIES-1];
    for (genvar unused_target_live_mem_legacy_row=0; unused_target_live_mem_legacy_row<=ENTRIES-1; unused_target_live_mem_legacy_row=unused_target_live_mem_legacy_row+1) begin : g_unused_target_live_mem_legacy
        wire unused_target_live_mem_legacy_bits = &{1'b0, target_live_mem_legacy[unused_target_live_mem_legacy_row]};
    end

    wire [OP_WIDTH-1:0] op_mem [0:ENTRIES-1];
    reg [OP_WIDTH-1:0] op_mem_legacy [0:ENTRIES-1];
    for (genvar unused_op_mem_legacy_row=0; unused_op_mem_legacy_row<=ENTRIES-1; unused_op_mem_legacy_row=unused_op_mem_legacy_row+1) begin : g_unused_op_mem_legacy
        wire unused_op_mem_legacy_bits = &{1'b0, op_mem_legacy[unused_op_mem_legacy_row]};
    end

    wire [31:0] pc_mem [0:ENTRIES-1];
    reg [31:0] pc_mem_legacy [0:ENTRIES-1];
    for (genvar unused_pc_mem_legacy_row=0; unused_pc_mem_legacy_row<=ENTRIES-1; unused_pc_mem_legacy_row=unused_pc_mem_legacy_row+1) begin : g_unused_pc_mem_legacy
        wire unused_pc_mem_legacy_bits = &{1'b0, pc_mem_legacy[unused_pc_mem_legacy_row]};
    end

    wire [TAG_WIDTH-1:0] rob_tag_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] rob_tag_mem_legacy [0:ENTRIES-1];
    for (genvar unused_rob_tag_mem_legacy_row=0; unused_rob_tag_mem_legacy_row<=ENTRIES-1; unused_rob_tag_mem_legacy_row=unused_rob_tag_mem_legacy_row+1) begin : g_unused_rob_tag_mem_legacy
        wire unused_rob_tag_mem_legacy_bits = &{1'b0, rob_tag_mem_legacy[unused_rob_tag_mem_legacy_row]};
    end

    wire [PHYS_ADDR_WIDTH-1:0] phys_rd_mem [0:ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] phys_rd_mem_legacy [0:ENTRIES-1];
    for (genvar unused_phys_rd_mem_legacy_row=0; unused_phys_rd_mem_legacy_row<=ENTRIES-1; unused_phys_rd_mem_legacy_row=unused_phys_rd_mem_legacy_row+1) begin : g_unused_phys_rd_mem_legacy
        wire unused_phys_rd_mem_legacy_bits = &{1'b0, phys_rd_mem_legacy[unused_phys_rd_mem_legacy_row]};
    end

    wire [31:0] src1_value_mem [0:ENTRIES-1];
    reg [31:0] src1_value_mem_legacy [0:ENTRIES-1];
    for (genvar unused_src1_value_mem_legacy_row=0; unused_src1_value_mem_legacy_row<=ENTRIES-1; unused_src1_value_mem_legacy_row=unused_src1_value_mem_legacy_row+1) begin : g_unused_src1_value_mem_legacy
        wire unused_src1_value_mem_legacy_bits = &{1'b0, src1_value_mem_legacy[unused_src1_value_mem_legacy_row]};
    end

    wire [SOURCE_TAG_WIDTH-1:0] src1_tag_mem [0:ENTRIES-1];
    reg [SOURCE_TAG_WIDTH-1:0] src1_tag_mem_legacy [0:ENTRIES-1];
    wire src1_ready_mem [0:ENTRIES-1];
    reg src1_ready_mem_legacy [0:ENTRIES-1];
    wire [31:0] src2_value_mem [0:ENTRIES-1];
    reg [31:0] src2_value_mem_legacy [0:ENTRIES-1];
    for (genvar unused_src2_value_mem_legacy_row=0; unused_src2_value_mem_legacy_row<=ENTRIES-1; unused_src2_value_mem_legacy_row=unused_src2_value_mem_legacy_row+1) begin : g_unused_src2_value_mem_legacy
        wire unused_src2_value_mem_legacy_bits = &{1'b0, src2_value_mem_legacy[unused_src2_value_mem_legacy_row]};
    end

    wire [SOURCE_TAG_WIDTH-1:0] src2_tag_mem [0:ENTRIES-1];
    reg [SOURCE_TAG_WIDTH-1:0] src2_tag_mem_legacy [0:ENTRIES-1];
    wire src2_ready_mem [0:ENTRIES-1];
    reg src2_ready_mem_legacy [0:ENTRIES-1];
    wire [STORE_DATA_WIDTH-1:0] store_data_mem [0:ENTRIES-1];
    reg [STORE_DATA_WIDTH-1:0] store_data_mem_legacy [0:ENTRIES-1];
    for (genvar unused_store_data_mem_legacy_row=0; unused_store_data_mem_legacy_row<=ENTRIES-1; unused_store_data_mem_legacy_row=unused_store_data_mem_legacy_row+1) begin : g_unused_store_data_mem_legacy
        wire unused_store_data_mem_legacy_bits = &{1'b0, store_data_mem_legacy[unused_store_data_mem_legacy_row]};
    end

    // Opaque dispatch information follows the same allocation, selection and
    // recovery ownership as the operands. Invalid entry payload is undefined.
    wire [METADATA_WIDTH-1:0] metadata_mem [0:ENTRIES-1];
    reg [METADATA_WIDTH-1:0] metadata_mem_legacy [0:ENTRIES-1];
    for (genvar unused_metadata_mem_legacy_row=0; unused_metadata_mem_legacy_row<=ENTRIES-1; unused_metadata_mem_legacy_row=unused_metadata_mem_legacy_row+1) begin : g_unused_metadata_mem_legacy
        wire unused_metadata_mem_legacy_bits = &{1'b0, metadata_mem_legacy[unused_metadata_mem_legacy_row]};
    end

    wire [AGE_WIDTH-1:0] age_mem [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_mem_legacy [0:ENTRIES-1];
    for (genvar unused_age_mem_legacy_row=0; unused_age_mem_legacy_row<=ENTRIES-1; unused_age_mem_legacy_row=unused_age_mem_legacy_row+1) begin : g_unused_age_mem_legacy
        wire unused_age_mem_legacy_bits = &{1'b0, age_mem_legacy[unused_age_mem_legacy_row]};
    end

    wire src1_ready_effective [0:ENTRIES-1];
    wire [31:0] src1_value_effective [0:ENTRIES-1];
    wire src2_ready_effective [0:ENTRIES-1];
    wire [31:0] src2_value_effective [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_counter;
    reg [COUNT_WIDTH-1:0] occupancy_reg;

    integer lane;
    integer alloc_slot;
    integer allocation_count;
    integer free_entries;
    integer reset_slot;
    integer wake_slot;
    integer wake_lane;
    integer issue_slot;
    integer issue_fire_lane;
    integer alloc_cursor;
    integer alloc_search;

    wire [COUNT_WIDTH-1:0] remaining_count;
    wire [ENTRIES-1:0] valid_entries;
    generate for (genvar remaining_row=0; remaining_row<ENTRIES; remaining_row=remaining_row+1) begin : g_remaining_entry
        assign valid_entries[remaining_row] = valid_mem[remaining_row];
    end endgenerate
    assign remaining_count = count_remaining_bits(valid_entries &
        ~(flush_kill_mask_i | ((RECOVERY_ISSUE_RELEASE != 0) ? issue_release_mask : {ENTRIES{1'b0}})));
    integer issue_fire_count;
    reg prefix_open;
    reg alloc_found;
    wire [ENTRIES-1:0] ready_candidates;
    wire [BE_WIDTH-1:0] ready_rank_match [0:ENTRIES-1];
    wire [ENTRIES-1:0] cached_age_precedes [0:ENTRIES-1];

    assign occupancy_o = occupancy_reg;
    assign alloc_ready_o = (alloc_count_o != 0) && !flush_valid_i;

    genvar entry_index;
    generate
        for (entry_index = 0; entry_index < ENTRIES; entry_index = entry_index + 1) begin : g_entry_state
            assign entry_valid_o[entry_index] = valid_mem[entry_index];
            assign entry_rob_tag_o[(entry_index*TAG_WIDTH) +: TAG_WIDTH] = rob_tag_mem[entry_index];
            wire probe_base_ready=(REGISTERED_BASE_PROBE!=0) ?
                src1_ready_mem[entry_index] : src1_ready_effective[entry_index];
            assign entry_base_ready_o[entry_index] = valid_mem[entry_index] &&
                target_live_mem[entry_index] && probe_base_ready && !flush_valid_i;
            assign entry_base_value_o[(entry_index*32) +: 32] =
                (REGISTERED_BASE_PROBE!=0) ? src1_value_mem[entry_index] :
                    src1_value_effective[entry_index];
            assign entry_metadata_o[(entry_index*METADATA_WIDTH) +: METADATA_WIDTH] = metadata_mem[entry_index];
            assign ready_candidates[entry_index] = valid_mem[entry_index] &&
                target_live_mem[entry_index] && src1_ready_effective[entry_index] &&
                src2_ready_effective[entry_index];
        end
    endgenerate

    // The policy still counts older ready instructions. For up to four
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
                            begin : g_named_205_28
assign count_match[RANK_LEAVES+rank_other][rank_lane]=older_ready[rank_other];
end
                        else begin : g_named_206_29
assign count_match[RANK_LEAVES+rank_other][rank_lane]=1'b0;
end
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

    // Share tag comparisons and predecode first/last lane priority once per
    // operand. Preserve the original first-lane combinational bypass and
    // last-lane sequential write even for conflicting duplicate wake tags.
    wire [WAKE_WIDTH-1:0] wake1_match [0:ENTRIES-1];
    wire [WAKE_WIDTH-1:0] wake2_match [0:ENTRIES-1];
    wire [31:0] wake1_first [0:ENTRIES-1], wake1_last [0:ENTRIES-1];
    wire [31:0] wake2_first [0:ENTRIES-1], wake2_last [0:ENTRIES-1];
    genvar wr, wl;
    generate if (WAKE_MUX_IMPL != 0) begin : g_parallel_wake
        localparam integer WAKE_DOMAINS=(ENTRIES+3)/4;
        wire [WAKE_DOMAINS*WAKE_WIDTH-1:0] valid_views;
        wire [WAKE_DOMAINS*WAKE_WIDTH*SOURCE_TAG_WIDTH-1:0] tag_views;
        wire [WAKE_DOMAINS*WAKE_WIDTH*32-1:0] value_views;
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH),.LEAVES(WAKE_DOMAINS)) valid_tree (
            .signal_i(wake_valid_i),.views_o(valid_views));
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH*SOURCE_TAG_WIDTH),.LEAVES(WAKE_DOMAINS)) tag_tree (
            .signal_i(wake_tag_i),.views_o(tag_views));
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH*32),.LEAVES(WAKE_DOMAINS)) value_tree (
            .signal_i(wake_value_i),.views_o(value_views));
        for (wr = 0; wr < ENTRIES; wr = wr + 1) begin : g_entry
            localparam integer DOMAIN=wr/4;
            wire [WAKE_WIDTH-1:0] first1, last1, first2, last2;
            wire unused_last1_bits = &{1'b0, last1};

            wire unused_last2_bits = &{1'b0, last2};

            wire [WAKE_WIDTH-1:0] local_valid=valid_views[DOMAIN*WAKE_WIDTH +: WAKE_WIDTH];
            wire [WAKE_WIDTH*SOURCE_TAG_WIDTH-1:0] local_tags=tag_views[DOMAIN*WAKE_WIDTH*SOURCE_TAG_WIDTH +: WAKE_WIDTH*SOURCE_TAG_WIDTH];
            wire [WAKE_WIDTH*32-1:0] local_values=value_views[DOMAIN*WAKE_WIDTH*32 +: WAKE_WIDTH*32];
            for (wl = 0; wl < WAKE_WIDTH; wl = wl + 1) begin : g_lane
                assign wake1_match[wr][wl] = local_valid[wl] && local_tags[wl*SOURCE_TAG_WIDTH] &&
                    src1_tag_mem[wr][0] && local_tags[wl*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH] == src1_tag_mem[wr];
                assign wake2_match[wr][wl] = local_valid[wl] && local_tags[wl*SOURCE_TAG_WIDTH] &&
                    src2_tag_mem[wr][0] && local_tags[wl*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH] == src2_tag_mem[wr];
                if(WAKE_UNIQUE_OWNER!=0) begin:g_unique_owner
                    assign first1[wl]=wake1_match[wr][wl];
                    assign last1[wl]=wake1_match[wr][wl];
                    assign first2[wl]=wake2_match[wr][wl];
                    assign last2[wl]=wake2_match[wr][wl];
                end else begin:g_ordered_duplicates
                if (wl == 0) begin : g_first
                    assign first1[wl] = wake1_match[wr][wl];
                    assign first2[wl] = wake2_match[wr][wl];
                end else begin : g_not_first
                    assign first1[wl] = wake1_match[wr][wl] && !(|wake1_match[wr][wl-1:0]);
                    assign first2[wl] = wake2_match[wr][wl] && !(|wake2_match[wr][wl-1:0]);
                end
                if (wl == WAKE_WIDTH-1) begin : g_last
                    assign last1[wl] = wake1_match[wr][wl];
                    assign last2[wl] = wake2_match[wr][wl];
                end else begin : g_not_last
                    assign last1[wl] = wake1_match[wr][wl] && !(|wake1_match[wr][WAKE_WIDTH-1:wl+1]);
                    assign last2[wl] = wake2_match[wr][wl] && !(|wake2_match[wr][WAKE_WIDTH-1:wl+1]);
                end
                end
            end
            wire  unused_first1_selector_write_o;
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) first1_selector (
                .events_i(first1),.values_i(local_values),.write_o(unused_first1_selector_write_o),.value_o(wake1_first[wr]));

            wire  unused_first2_selector_write_o;
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) first2_selector (
                .events_i(first2),.values_i(local_values),.write_o(unused_first2_selector_write_o),.value_o(wake2_first[wr]));
            if(WAKE_UNIQUE_OWNER!=0) begin:g_shared_wake_word
                assign wake1_last[wr]=wake1_first[wr];
                assign wake2_last[wr]=wake2_first[wr];
            end else begin:g_last_wake_word
            wire  unused_last1_selector_write_o;
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) last1_selector (
                .events_i(last1),.values_i(local_values),.write_o(unused_last1_selector_write_o),.value_o(wake1_last[wr]));
            wire  unused_last2_selector_write_o;
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) last2_selector (
                .events_i(last2),.values_i(local_values),.write_o(unused_last2_selector_write_o),.value_o(wake2_last[wr]));
            end
        end

    end endgenerate

    // Select allocation slots exactly as the legacy cursor walk, then decode
    // per-row write ownership before selecting the wide payload. A last-lane
    // grant retains NBA priority even for otherwise inconsistent queue state.
    localparam integer ALLOC_PAYLOAD_WIDTH = 1 + OP_WIDTH + 32 + TAG_WIDTH +
        PHYS_ADDR_WIDTH + 32 + SOURCE_TAG_WIDTH + 1 + 32 + SOURCE_TAG_WIDTH + 1 +
        STORE_DATA_WIDTH + METADATA_WIDTH + AGE_WIDTH;
    wire [SLOT_WIDTH-1:0] allocation_slots [0:BE_WIDTH-1];
    wire [ALLOC_PAYLOAD_WIDTH-1:0] alloc_lane_payload [0:BE_WIDTH-1];
    wire [ALLOC_PAYLOAD_WIDTH-1:0] alloc_row_payload [0:ENTRIES-1];
    wire [ENTRIES-1:0] alloc_row_write;
    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];
    for (genvar unused_alloc_row_grants_row=0; unused_alloc_row_grants_row<=ENTRIES-1; unused_alloc_row_grants_row=unused_alloc_row_grants_row+1) begin : g_unused_alloc_row_grants
        wire unused_alloc_row_grants_bits = &{1'b0, alloc_row_grants[unused_alloc_row_grants_row]};
    end

    wire [ENTRIES-1:0] issue_release_mask;
    wire [ENTRIES-1:0] allocation_available_rows;
    wire [ENTRIES-1:0] allocation_released_rows=valid_entries & issue_release_mask &
        {ENTRIES{(RELEASE_CREDITS!=0) && !reset_i && !flush_valid_i}};
    assign allocation_release_count_o=ALLOC_COUNT_WIDTH'(count_remaining_bits(allocation_released_rows));
    assign allocation_available_rows=~valid_entries | allocation_released_rows;
    initial if(RELEASE_CREDITS!=0 && ALLOC_STATIC_WRITE==0)
        $fatal(1,"RS release credits require static row allocation");
    initial if((QUALIFIED_OPERAND_WRITE!=0 && QUALIFIED_OPERAND_WRITE!=1) ||
        (QUALIFIED_OPERAND_WRITE!=0 && (RELEASE_CREDITS!=0 ||
         ALLOC_STATIC_WRITE==0 || LOCAL_PAYLOAD_ROWS==0)))
        $fatal(1,"Qualified RS operands require static local no-release rows");
    genvar export_lane,export_row;
    generate
        for(export_lane=0;export_lane<BE_WIDTH;export_lane=export_lane+1) begin:g_allocation_identity
            if(ALLOC_STATIC_WRITE!=0)
                begin : g_named_325_16
assign alloc_slot_o[export_lane*SLOT_WIDTH +: SLOT_WIDTH]=allocation_slots[export_lane];
end
            else begin : g_named_326_17
assign alloc_slot_o[export_lane*SLOT_WIDTH +: SLOT_WIDTH]=0;
end
        end
        for(export_row=0;export_row<ENTRIES;export_row=export_row+1) begin:g_release_identity
            wire [BE_WIDTH-1:0] issued_here;
            for(export_lane=0;export_lane<BE_WIDTH;export_lane=export_lane+1) begin:g_lane
                assign issued_here[export_lane]=issue_valid_o[export_lane] && issue_ready_i[export_lane] &&
                    issue_slot_o[export_lane*SLOT_WIDTH +: SLOT_WIDTH]==export_row;
            end
            assign issue_release_mask[export_row]=|issued_here;
            // Mirrors valid/occupancy ownership, including retained issue on
            // a selective flush. Kill and accepted issue clear a row only once.
            assign entry_release_o[export_row]=reset_i ||
                (flush_valid_i ? (flush_kill_mask_i[export_row] ||
                 ((RECOVERY_ISSUE_RELEASE!=0) && issue_release_mask[export_row])) :
                 issue_release_mask[export_row]);
        end
    endgenerate

    integer alloc_static_row;

    genvar ar, al, alloc_word;
    generate if (ALLOC_STATIC_WRITE != 0) begin : g_static_allocation
        localparam integer SLOT_LEAVES=1<<$clog2(ENTRIES);
        localparam integer LANE_LEAVES=(BE_WIDTH<=1)?1:(1<<$clog2(BE_WIDTH));
        wire [COUNT_WIDTH-1:0] free_before [0:ENTRIES-1];
        wire [COUNT_WIDTH-1:0] accepted_before [0:BE_WIDTH-1];
        wire [BE_WIDTH-1:0] slot_grants [0:ENTRIES-1];
        genvar rank_row,local_rank_lane,rank_source,local_rank_node;
        // The kth accepted lane owns the kth free physical row. Both counts
        // use balanced population-count trees; no lane waits for another
        // lane's encoded slot or search cursor.
        for(rank_row=0;rank_row<ENTRIES;rank_row=rank_row+1) begin:g_free_rank
            wire [COUNT_WIDTH-1:0] tree [1:2*SLOT_LEAVES-1];
            for(rank_source=0;rank_source<SLOT_LEAVES;rank_source=rank_source+1) begin:g_leaf
                if(rank_source<rank_row) begin : g_named_360_41
assign tree[SLOT_LEAVES+rank_source]=COUNT_WIDTH'(allocation_available_rows[rank_source]);
end
                else begin : g_named_361_21
assign tree[SLOT_LEAVES+rank_source]=0;
end
            end
            for(local_rank_node=1;local_rank_node<SLOT_LEAVES;local_rank_node=local_rank_node+1) begin:g_sum
                assign tree[local_rank_node]=tree[2*local_rank_node]+tree[2*local_rank_node+1];
            end
            assign free_before[rank_row]=tree[1];
            for(local_rank_lane=0;local_rank_lane<BE_WIDTH;local_rank_lane=local_rank_lane+1) begin:g_grant
                assign slot_grants[rank_row][local_rank_lane]=allocation_available_rows[rank_row] &&
                    alloc_fire_o[local_rank_lane] && free_before[rank_row]==accepted_before[local_rank_lane];
            end
        end
        for(local_rank_lane=0;local_rank_lane<BE_WIDTH;local_rank_lane=local_rank_lane+1) begin:g_lane_rank
            wire [COUNT_WIDTH-1:0] count_tree [1:2*LANE_LEAVES-1];
            wire [SLOT_WIDTH-1:0] slot_tree [1:2*SLOT_LEAVES-1];
            for(rank_source=0;rank_source<LANE_LEAVES;rank_source=rank_source+1) begin:g_count_leaf
                if(rank_source<local_rank_lane) begin : g_named_376_42
assign count_tree[LANE_LEAVES+rank_source]=COUNT_WIDTH'(alloc_fire_o[rank_source]);
end
                else begin : g_named_377_21
assign count_tree[LANE_LEAVES+rank_source]=0;
end
            end
            for(local_rank_node=1;local_rank_node<LANE_LEAVES;local_rank_node=local_rank_node+1) begin:g_count_sum
                assign count_tree[local_rank_node]=count_tree[2*local_rank_node]+count_tree[2*local_rank_node+1];
            end
            assign accepted_before[local_rank_lane]=count_tree[1];
            for(rank_source=0;rank_source<SLOT_LEAVES;rank_source=rank_source+1) begin:g_slot_leaf
                if(rank_source<ENTRIES)
                    begin : g_named_385_20
assign slot_tree[SLOT_LEAVES+rank_source]={SLOT_WIDTH{slot_grants[rank_source][local_rank_lane]}} &
                        rank_source[SLOT_WIDTH-1:0];
end
                else begin : g_named_387_21
assign slot_tree[SLOT_LEAVES+rank_source]=0;
end
            end
            for(local_rank_node=1;local_rank_node<SLOT_LEAVES;local_rank_node=local_rank_node+1) begin:g_slot_or
                assign slot_tree[local_rank_node]=slot_tree[2*local_rank_node] | slot_tree[2*local_rank_node+1];
            end
            assign allocation_slots[local_rank_lane]=slot_tree[1];
        end
        for (al = 0; al < BE_WIDTH; al = al + 1) begin : g_payload
            wire [AGE_WIDTH-1:0] lane_age = (AGE_ORDER_MATRIX==2) ? 0 : age_counter + al;
            assign alloc_lane_payload[al] = {
                alloc_target_live_i[al] && alloc_rob_tag_i[al*TAG_WIDTH],
                alloc_op_i[al*OP_WIDTH +: OP_WIDTH], alloc_pc_i[al*32 +: 32],
                alloc_rob_tag_i[al*TAG_WIDTH +: TAG_WIDTH],
                alloc_phys_rd_i[al*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                alloc_src1_value_i[al*32 +: 32], alloc_src1_tag_i[al*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH],
                alloc_src1_ready_i[al], alloc_src2_value_i[al*32 +: 32],
                alloc_src2_tag_i[al*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH], alloc_src2_ready_i[al],
                alloc_store_data_i[al*STORE_DATA_WIDTH +: STORE_DATA_WIDTH],
                alloc_metadata_i[al*METADATA_WIDTH +: METADATA_WIDTH], lane_age};
        end
        for (ar = 0; ar < ENTRIES; ar = ar + 1) begin : g_row
            wire [BE_WIDTH-1:0] allocation_match_bits, grants;
            for (al = 0; al < BE_WIDTH; al = al + 1) begin : g_grant
                assign allocation_match_bits[al] = slot_grants[ar][al];
                if (al == BE_WIDTH-1) begin : g_named_411_38
assign grants[al] = allocation_match_bits[al];
end
                else begin : g_named_412_21
assign grants[al] = allocation_match_bits[al] && !(|allocation_match_bits[BE_WIDTH-1:al+1]);
end
            end
            localparam integer WORDS=(ALLOC_PAYLOAD_WIDTH+15)/16;
            wire [BE_WIDTH*WORDS-1:0] payload_grants;
            wire [BE_WIDTH-1:0] payload_events=(QUALIFIED_OPERAND_WRITE!=0) ?
                (grants & {BE_WIDTH{!reset_i && !flush_valid_i}}) : grants;
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(WORDS)) grant_tree (
                .signal_i(payload_events),.views_o(payload_grants));
            wire [ALLOC_PAYLOAD_WIDTH-1:0] payload;
            for(alloc_word=0;alloc_word<WORDS;alloc_word=alloc_word+1) begin:g_word
                localparam integer LOW=alloc_word*16;
                localparam integer BITS=ALLOC_PAYLOAD_WIDTH-LOW>=16 ? 16 : ALLOC_PAYLOAD_WIDTH-LOW;
                reg [BITS-1:0] selected_word;
                integer mux_lane;
                always @* begin
                    selected_word=0;
                    for(mux_lane=0;mux_lane<BE_WIDTH;mux_lane=mux_lane+1)
                        selected_word=selected_word |
                            ({BITS{payload_grants[alloc_word*BE_WIDTH+mux_lane]}} &
                             alloc_lane_payload[mux_lane][LOW +: BITS]);
                end
                assign payload[LOW +: BITS]=selected_word;
            end
            assign alloc_row_grants[ar] = grants;
            assign alloc_row_write[ar] = |allocation_match_bits;
            assign alloc_row_payload[ar] = payload;
        end
    end endgenerate

    // Cache the exact unsigned numeric comparison, including age-counter
    // wrap and equal-age slot tie breaks. Only allocation changes an age;
    // flush and issue preserve both age words and their derived relation.
    // Shared new-age/old-age comparisons are computed once per lane/row.
    genvar age_lane, age_row, age_peer, pair_low, pair_high;
    generate if ((AGE_ORDER_MATRIX == 1) && (ALLOC_STATIC_WRITE != 0)) begin : g_age_order_matrix
        wire [AGE_WIDTH-1:0] new_age [0:BE_WIDTH-1];
        wire [BE_WIDTH-1:0] new_le_old [0:ENTRIES-1];
        wire [BE_WIDTH-1:0] new_lt_old [0:ENTRIES-1];
        wire [BE_WIDTH-1:0] new_le_new [0:BE_WIDTH-1];
        for (age_lane = 0; age_lane < BE_WIDTH; age_lane = age_lane + 1) begin : g_new_age
            assign new_age[age_lane] = age_counter + age_lane;
            for (age_row = 0; age_row < ENTRIES; age_row = age_row + 1) begin : g_old_age
                assign new_le_old[age_row][age_lane] = new_age[age_lane] <= age_mem[age_row];
                assign new_lt_old[age_row][age_lane] = new_age[age_lane] < age_mem[age_row];
            end
            for (age_peer = 0; age_peer < BE_WIDTH; age_peer = age_peer + 1) begin : g_peer_age
                assign new_le_new[age_lane][age_peer] = new_age[age_lane] <= new_age[age_peer];
            end
        end
        for (pair_low = 0; pair_low < ENTRIES; pair_low = pair_low + 1) begin : g_low
            assign cached_age_precedes[pair_low][pair_low] = 1'b0;
            for (pair_high = pair_low + 1; pair_high < ENTRIES; pair_high = pair_high + 1) begin : g_high
                reg low_precedes_high;
                reg left_new_order, right_new_order, both_new_order;
                integer left_lane, right_lane;
                always @* begin
                    left_new_order = 1'b0;
                    right_new_order = 1'b0;
                    both_new_order = 1'b0;
                    for (left_lane = 0; left_lane < BE_WIDTH; left_lane = left_lane + 1) begin
                        left_new_order = left_new_order |
                            (alloc_row_grants[pair_low][left_lane] && new_le_old[pair_high][left_lane]);
                        right_new_order = right_new_order |
                            (alloc_row_grants[pair_high][left_lane] && !new_lt_old[pair_low][left_lane]);
                        for (right_lane = 0; right_lane < BE_WIDTH; right_lane = right_lane + 1)
                            both_new_order = both_new_order | (alloc_row_grants[pair_low][left_lane] &&
                                alloc_row_grants[pair_high][right_lane] && new_le_new[left_lane][right_lane]);
                    end
                end
                always @(posedge clk_i) begin
                    if (reset_i)
                        low_precedes_high <= 1'b1;
                    else if (!flush_valid_i) begin
                        if (alloc_row_write[pair_low])
                            low_precedes_high <= alloc_row_write[pair_high] ? both_new_order : left_new_order;
                        else if (alloc_row_write[pair_high])
                            low_precedes_high <= right_new_order;
                    end
                end
                assign cached_age_precedes[pair_low][pair_high] = low_precedes_high;
                assign cached_age_precedes[pair_high][pair_low] = !low_precedes_high;
            end
        end
    end endgenerate

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

    genvar owner_row, owner_lane;
    generate for(owner_row=0;owner_row<ENTRIES;owner_row=owner_row+1) begin:g_payload_owner
        if(LOCAL_PAYLOAD_ROWS!=0 && ALLOC_STATIC_WRITE!=0) begin:g_local
            wire [BE_WIDTH-1:0] issued_here;
            for(owner_lane=0;owner_lane<BE_WIDTH;owner_lane=owner_lane+1) begin:g_issue
                assign issued_here[owner_lane]=issue_valid_o[owner_lane] && issue_ready_i[owner_lane] &&
                    issue_slot_o[owner_lane*SLOT_WIDTH +: SLOT_WIDTH]==owner_row;
            end
            wire [WAKE_WIDTH-1:0] match1,match2;
            wire [31:0] last1,last2;
            if(WAKE_MUX_IMPL!=0) begin:g_shared_wake
                assign match1=wake1_match[owner_row];assign match2=wake2_match[owner_row];
                assign last1=wake1_last[owner_row];assign last2=wake2_last[owner_row];
            end else begin:g_legacy_wake
                reg [31:0] value1,value2;
                integer wake_port;
                for(owner_lane=0;owner_lane<WAKE_WIDTH;owner_lane=owner_lane+1) begin:g_match
                    assign match1[owner_lane]=wake_valid_i[owner_lane] && wake_tag_i[owner_lane*SOURCE_TAG_WIDTH] &&
                        src1_tag_mem[owner_row][0] && wake_tag_i[owner_lane*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH]==src1_tag_mem[owner_row];
                    assign match2[owner_lane]=wake_valid_i[owner_lane] && wake_tag_i[owner_lane*SOURCE_TAG_WIDTH] &&
                        src2_tag_mem[owner_row][0] && wake_tag_i[owner_lane*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH]==src2_tag_mem[owner_row];
                end
                always @* begin
                    value1=0;value2=0;
                    for(wake_port=0;wake_port<WAKE_WIDTH;wake_port=wake_port+1) begin
                        if(match1[wake_port]) value1=wake_value_i[wake_port*32 +: 32];
                        if(match2[wake_port]) value2=wake_value_i[wake_port*32 +: 32];
                    end
                end
                assign last1=value1;assign last2=value2;
            end
            rv32_rs_payload_row #(.OP_WIDTH(OP_WIDTH),.TAG_WIDTH(TAG_WIDTH),.SOURCE_TAG_WIDTH(SOURCE_TAG_WIDTH),
                .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH),.STORE_DATA_WIDTH(STORE_DATA_WIDTH),
                .METADATA_WIDTH(METADATA_WIDTH),.AGE_WIDTH(AGE_WIDTH),
                .PAYLOAD_WIDTH(ALLOC_PAYLOAD_WIDTH),.ALLOC_ISSUE_REPLACE(RELEASE_CREDITS),
                .QUALIFIED_OPERAND_WRITE(QUALIFIED_OPERAND_WRITE)) row (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_valid_i),
                .kill_i(flush_kill_mask_i[owner_row] ||
                    ((RECOVERY_ISSUE_RELEASE!=0) && issue_release_mask[owner_row])),
                .valid_i(valid_mem[owner_row]),.issue_i(|issued_here),
                .alloc_i(alloc_row_write[owner_row]),.payload_i(alloc_row_payload[owner_row]),
                .wake1_i(|match1),.wake2_i(|match2),.wake1_value_i(last1),.wake2_value_i(last2),
                .target_live_o(target_live_mem[owner_row]),.op_o(op_mem[owner_row]),.pc_o(pc_mem[owner_row]),
                .rob_tag_o(rob_tag_mem[owner_row]),.phys_rd_o(phys_rd_mem[owner_row]),
                .src1_value_o(src1_value_mem[owner_row]),.src1_tag_o(src1_tag_mem[owner_row]),.src1_ready_o(src1_ready_mem[owner_row]),
                .src2_value_o(src2_value_mem[owner_row]),.src2_tag_o(src2_tag_mem[owner_row]),.src2_ready_o(src2_ready_mem[owner_row]),
                .store_data_o(store_data_mem[owner_row]),.metadata_o(metadata_mem[owner_row]),.age_o(age_mem[owner_row]));
        end else begin:g_legacy
            assign target_live_mem[owner_row]=target_live_mem_legacy[owner_row];
            assign op_mem[owner_row]=op_mem_legacy[owner_row];
            assign pc_mem[owner_row]=pc_mem_legacy[owner_row];
            assign rob_tag_mem[owner_row]=rob_tag_mem_legacy[owner_row];
            assign phys_rd_mem[owner_row]=phys_rd_mem_legacy[owner_row];
            assign src1_value_mem[owner_row]=src1_value_mem_legacy[owner_row];
            assign src1_tag_mem[owner_row]=src1_tag_mem_legacy[owner_row];
            assign src1_ready_mem[owner_row]=src1_ready_mem_legacy[owner_row];
            assign src2_value_mem[owner_row]=src2_value_mem_legacy[owner_row];
            assign src2_tag_mem[owner_row]=src2_tag_mem_legacy[owner_row];
            assign src2_ready_mem[owner_row]=src2_ready_mem_legacy[owner_row];
            assign store_data_mem[owner_row]=store_data_mem_legacy[owner_row];
            assign metadata_mem[owner_row]=metadata_mem_legacy[owner_row];
            assign age_mem[owner_row]=age_mem_legacy[owner_row];
        end
    end endgenerate

    // Rank policy and ready remain unchanged. Each selection controls
    // <=16-bit words before balanced payload reduction.
    localparam integer ISSUE_ORIGINAL_DATA_WIDTH=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+
        64+STORE_DATA_WIDTH+METADATA_WIDTH+SLOT_WIDTH;
    localparam integer ISSUE_ARITHMETIC_DATA_WIDTH=ISSUE_ORIGINAL_DATA_WIDTH+
        ((ARITHMETIC_PRECOMPUTE!=0)?32:0);
    localparam integer ISSUE_COMPARISON_DATA_WIDTH=ISSUE_ARITHMETIC_DATA_WIDTH+
        ((COMPARISON_PRECOMPUTE!=0)?3:0);
    localparam integer ISSUE_BASE_DATA_WIDTH=ISSUE_COMPARISON_DATA_WIDTH+
        ((PC_PRECOMPUTE!=0)?64:0);
    localparam integer ISSUE_QUALIFIED_DATA_WIDTH=ISSUE_BASE_DATA_WIDTH+
        ((ISSUE_RECOVERY_QUALIFICATION!=0)?1:0);
    localparam integer ISSUE_DATA_WIDTH=ISSUE_QUALIFIED_DATA_WIDTH+
        ((ISSUE_RECOVERY_CANCEL!=0)?1:0);
    localparam integer ISSUE_DATA_WORDS=(ISSUE_DATA_WIDTH+15)/16;
    localparam integer ISSUE_DATA_LEAVES=1<<$clog2(ENTRIES);
    // Empty queue fallthrough consumes only actual accepted allocations.
    // Unissued rows are still captured normally, so a stalled first offer
    // transitions to the original registered owner with identical payload.
    wire empty_allocation_issue=(ALLOC_EMPTY_BYPASS!=0) && !reset_i &&
        !flush_valid_i && occupancy_reg==0;
    wire [COUNT_WIDTH-1:0] stored_ready_count;
    generate if(ALLOC_EMPTY_BYPASS==2) begin:g_ready_lane_capacity
        assign stored_ready_count=count_remaining_bits(ready_candidates);
    end else begin:g_empty_lane_capacity
        assign stored_ready_count=0;
    end endgenerate
    wire [BE_WIDTH-1:0] incoming_ready;
    wire [ALLOC_COUNT_WIDTH-1:0] incoming_rank [0:BE_WIDTH];
    assign incoming_rank[0]=0;
    for(genvar incoming_lane=0;incoming_lane<BE_WIDTH;incoming_lane=incoming_lane+1) begin:g_incoming_ready
        assign incoming_ready[incoming_lane]=(ALLOC_EMPTY_BYPASS!=0) && alloc_fire_o[incoming_lane] &&
            alloc_target_live_i[incoming_lane] && alloc_rob_tag_i[incoming_lane*TAG_WIDTH] &&
            alloc_src1_ready_i[incoming_lane] && alloc_src2_ready_i[incoming_lane];
        assign incoming_rank[incoming_lane+1]=incoming_rank[incoming_lane]+ALLOC_COUNT_WIDTH'(incoming_ready[incoming_lane]);
    end
    initial if(ALLOC_EMPTY_BYPASS<0 || ALLOC_EMPTY_BYPASS>2 ||
        (ALLOC_EMPTY_BYPASS!=0 && (ALLOC_STATIC_WRITE==0 || RELEASE_CREDITS!=0)))
        $fatal(1,"Empty RS bypass requires static allocation without release credits");
    initial if(FRESH_DEFAULT_LANE_DATA<0 || FRESH_DEFAULT_LANE_DATA>1 ||
        (FRESH_DEFAULT_LANE_DATA!=0 && ALLOC_EMPTY_BYPASS==0))
        $fatal(1,"Fresh default-lane data requires allocation issue bypass");
    initial if((ARITHMETIC_PRECOMPUTE!=0 && ARITHMETIC_PRECOMPUTE!=1) ||
        (ARITHMETIC_PRECOMPUTE!=0 && (METADATA_WIDTH<32 || OP_WIDTH<`RV32IM_OP_WIDTH)))
        $fatal(1,"RS arithmetic precompute requires full opcode and immediate metadata");
    wire [31:0] row_arithmetic [0:ENTRIES-1];
    wire [31:0] incoming_arithmetic [0:BE_WIDTH-1];
    generate if(ARITHMETIC_PRECOMPUTE!=0) begin:g_arithmetic_precompute
        for(genvar row=0;row<ENTRIES;row=row+1) begin:g_row
            wire register_rhs=op_mem[row]==`RV32IM_OP_ADD || op_mem[row]==`RV32IM_OP_SUB;
            rv32_frequency_addsub32 arithmetic (
                .lhs_i(src1_value_effective[row]),
                .rhs_i(register_rhs ? src2_value_effective[row] : metadata_mem[row][31:0]),
                .subtract_i(op_mem[row]==`RV32IM_OP_SUB),.value_o(row_arithmetic[row]));
        end
        for(genvar lane=0;lane<BE_WIDTH;lane=lane+1) begin:g_incoming
            wire [OP_WIDTH-1:0] op=alloc_op_i[lane*OP_WIDTH +: OP_WIDTH];
            wire register_rhs=op==`RV32IM_OP_ADD || op==`RV32IM_OP_SUB;
            rv32_frequency_addsub32 arithmetic (
                .lhs_i(alloc_src1_value_i[lane*32 +: 32]),
                .rhs_i(register_rhs ? alloc_src2_value_i[lane*32 +: 32] :
                    alloc_metadata_i[lane*METADATA_WIDTH +: 32]),
                .subtract_i(op==`RV32IM_OP_SUB),.value_o(incoming_arithmetic[lane]));
        end
    end else begin:g_original_arithmetic
        for(genvar row=0;row<ENTRIES;row=row+1) assign row_arithmetic[row]=0;
        for(genvar lane=0;lane<BE_WIDTH;lane=lane+1) assign incoming_arithmetic[lane]=0;
    end endgenerate
    initial if((COMPARISON_PRECOMPUTE!=0 && COMPARISON_PRECOMPUTE!=1) ||
        (COMPARISON_PRECOMPUTE!=0 && (METADATA_WIDTH<32 || OP_WIDTH<`RV32IM_OP_WIDTH)))
        $fatal(1,"RS comparison precompute requires full opcode and immediate metadata");
    wire [2:0] row_comparison [0:ENTRIES-1];
    wire [2:0] incoming_comparison [0:BE_WIDTH-1];
    generate if(COMPARISON_PRECOMPUTE!=0) begin:g_comparison_precompute
        for(genvar row=0;row<ENTRIES;row=row+1) begin:g_row
            wire immediate_rhs=op_mem[row]==`RV32IM_OP_SLTI || op_mem[row]==`RV32IM_OP_SLTIU;
            rv32_frequency_compare32 comparison (
                .lhs_i(src1_value_effective[row]),
                .rhs_i(immediate_rhs ? metadata_mem[row][31:0] : src2_value_effective[row]),
                .value_o(row_comparison[row]));
        end
        for(genvar lane=0;lane<BE_WIDTH;lane=lane+1) begin:g_incoming
            wire [OP_WIDTH-1:0] op=alloc_op_i[lane*OP_WIDTH +: OP_WIDTH];
            wire immediate_rhs=op==`RV32IM_OP_SLTI || op==`RV32IM_OP_SLTIU;
            rv32_frequency_compare32 comparison (
                .lhs_i(alloc_src1_value_i[lane*32 +: 32]),
                .rhs_i(immediate_rhs ? alloc_metadata_i[lane*METADATA_WIDTH +: 32] :
                    alloc_src2_value_i[lane*32 +: 32]),.value_o(incoming_comparison[lane]));
        end
    end else begin:g_original_comparison
        for(genvar row=0;row<ENTRIES;row=row+1) assign row_comparison[row]=0;
        for(genvar lane=0;lane<BE_WIDTH;lane=lane+1) assign incoming_comparison[lane]=0;
    end endgenerate
    initial if((PC_PRECOMPUTE!=0 && PC_PRECOMPUTE!=1) ||
        (PC_PRECOMPUTE!=0 && (METADATA_WIDTH<32 || OP_WIDTH<`RV32IM_OP_WIDTH)))
        $fatal(1,"RS PC precompute requires full opcode and immediate metadata");
    wire [63:0] row_pc_arithmetic [0:ENTRIES-1];
    wire [63:0] incoming_pc_arithmetic [0:BE_WIDTH-1];
    generate if(PC_PRECOMPUTE!=0) begin:g_pc_precompute
        for(genvar row=0;row<ENTRIES;row=row+1) begin:g_row
            wire [31:0] relative_pc,link_pc;
            rv32_frequency_addsub32 relative (
                .lhs_i(pc_mem[row]),.rhs_i(metadata_mem[row][31:0]),
                .subtract_i(1'b0),.value_o(relative_pc));
            assign link_pc=pc_mem[row]+32'd4;
            assign row_pc_arithmetic[row]={link_pc,relative_pc};
        end
        for(genvar lane=0;lane<BE_WIDTH;lane=lane+1) begin:g_incoming
            wire [31:0] relative_pc,link_pc;
            rv32_frequency_addsub32 relative (
                .lhs_i(alloc_pc_i[lane*32 +: 32]),.rhs_i(alloc_metadata_i[lane*METADATA_WIDTH +: 32]),
                .subtract_i(1'b0),.value_o(relative_pc));
            assign link_pc=alloc_pc_i[lane*32 +: 32]+32'd4;
            assign incoming_pc_arithmetic[lane]={link_pc,relative_pc};
        end
    end else begin:g_original_pc_arithmetic
        for(genvar row=0;row<ENTRIES;row=row+1) assign row_pc_arithmetic[row]=0;
        for(genvar lane=0;lane<BE_WIDTH;lane=lane+1) assign incoming_pc_arithmetic[lane]=0;
    end endgenerate
    genvar issue_lane,issue_row,issue_word,issue_node;
    generate for(issue_lane=0;issue_lane<BE_WIDTH;issue_lane=issue_lane+1) begin:g_issue_payload
        wire [ENTRIES-1:0] selections;
        wire [ISSUE_DATA_WIDTH-1:0] payload_tree [1:2*ISSUE_DATA_LEAVES-1];
        for(issue_row=0;issue_row<ISSUE_DATA_LEAVES;issue_row=issue_row+1) begin:g_row
            if(issue_row<ENTRIES) begin:g_present
                wire [ISSUE_DATA_WORDS-1:0] selected_words;
                wire [ISSUE_ORIGINAL_DATA_WIDTH-1:0] original_base_payload={
                    op_mem[issue_row],pc_mem[issue_row],rob_tag_mem[issue_row],phys_rd_mem[issue_row],
                    src1_value_effective[issue_row],src2_value_effective[issue_row],
                    store_data_mem[issue_row],metadata_mem[issue_row],issue_row[SLOT_WIDTH-1:0]};
                wire [ISSUE_BASE_DATA_WIDTH-1:0] base_payload;
                wire [ISSUE_ARITHMETIC_DATA_WIDTH-1:0] arithmetic_payload;
                wire [ISSUE_COMPARISON_DATA_WIDTH-1:0] comparison_payload;
                if(ARITHMETIC_PRECOMPUTE!=0) begin:g_arithmetic_packet
                    assign arithmetic_payload={row_arithmetic[issue_row],original_base_payload};
                end else begin:g_original_packet
                    assign arithmetic_payload=original_base_payload;
                end
                if(COMPARISON_PRECOMPUTE!=0) begin:g_comparison_packet
                    assign comparison_payload={row_comparison[issue_row],arithmetic_payload};
                end else begin:g_original_comparison_packet
                    assign comparison_payload=arithmetic_payload;
                end
                if(PC_PRECOMPUTE!=0) begin:g_pc_packet
                    assign base_payload={row_pc_arithmetic[issue_row],comparison_payload};
                end else begin:g_original_pc_packet
                    assign base_payload=comparison_payload;
                end
                wire [ISSUE_QUALIFIED_DATA_WIDTH-1:0] qualified_payload;
                if(ISSUE_RECOVERY_QUALIFICATION!=0) begin:g_qualification
                    assign qualified_payload={entry_recovery_qualified_i[issue_row],base_payload};
                end else begin:g_original_payload
                    assign qualified_payload=base_payload;
                end
                wire [ISSUE_DATA_WIDTH-1:0] payload;
                if(ISSUE_RECOVERY_CANCEL!=0) begin:g_cancel_sideband
                    assign payload={entry_issue_cancel_i[issue_row],qualified_payload};
                end else begin:g_no_cancel_sideband
                    assign payload=qualified_payload;
                end
                assign selections[issue_row]=ready_candidates[issue_row] && ready_rank_match[issue_row][issue_lane];
                rv32_frequency_control_tree #(.LEAVES(ISSUE_DATA_WORDS)) selection_tree (
                    .signal_i(selections[issue_row]),.views_o(selected_words));
                for(issue_word=0;issue_word<ISSUE_DATA_WORDS;issue_word=issue_word+1) begin:g_word
                    localparam integer LOW=issue_word*16;
                    localparam integer BITS=ISSUE_DATA_WIDTH-LOW>=16 ? 16 : ISSUE_DATA_WIDTH-LOW;
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
        wire [ISSUE_DATA_WIDTH-1:0] selected_issue_payload;
        if(ALLOC_EMPTY_BYPASS!=0) begin:g_empty_fallthrough
            wire [BE_WIDTH-1:0] grants;
            wire [BE_WIDTH*ISSUE_BASE_DATA_WIDTH-1:0] values;
            wire fresh_valid;
            wire [ISSUE_BASE_DATA_WIDTH-1:0] fresh_payload;
            for(genvar fresh_lane=0;fresh_lane<BE_WIDTH;fresh_lane=fresh_lane+1) begin:g_lane
                assign grants[fresh_lane]=incoming_ready[fresh_lane] &&
                    32'(incoming_rank[fresh_lane])+32'(stored_ready_count)==issue_lane;
                wire [ISSUE_ORIGINAL_DATA_WIDTH-1:0] original_fresh_payload={
                    alloc_op_i[fresh_lane*OP_WIDTH +: OP_WIDTH],alloc_pc_i[fresh_lane*32 +: 32],
                    alloc_rob_tag_i[fresh_lane*TAG_WIDTH +: TAG_WIDTH],alloc_phys_rd_i[fresh_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    alloc_src1_value_i[fresh_lane*32 +: 32],alloc_src2_value_i[fresh_lane*32 +: 32],
                    alloc_store_data_i[fresh_lane*STORE_DATA_WIDTH +: STORE_DATA_WIDTH],
                    alloc_metadata_i[fresh_lane*METADATA_WIDTH +: METADATA_WIDTH],allocation_slots[fresh_lane]};
                wire [ISSUE_ARITHMETIC_DATA_WIDTH-1:0] arithmetic_payload;
                if(ARITHMETIC_PRECOMPUTE!=0) begin:g_arithmetic_packet
                    assign arithmetic_payload={incoming_arithmetic[fresh_lane],original_fresh_payload};
                end else begin:g_original_packet
                    assign arithmetic_payload=original_fresh_payload;
                end
                wire [ISSUE_COMPARISON_DATA_WIDTH-1:0] comparison_payload;
                if(COMPARISON_PRECOMPUTE!=0) begin:g_comparison_packet
                    assign comparison_payload={incoming_comparison[fresh_lane],arithmetic_payload};
                end else begin:g_original_comparison_packet
                    assign comparison_payload=arithmetic_payload;
                end
                if(PC_PRECOMPUTE!=0) begin:g_pc_packet
                    assign values[fresh_lane*ISSUE_BASE_DATA_WIDTH +: ISSUE_BASE_DATA_WIDTH]=
                        {incoming_pc_arithmetic[fresh_lane],comparison_payload};
                end else begin:g_original_pc_packet
                    assign values[fresh_lane*ISSUE_BASE_DATA_WIDTH +: ISSUE_BASE_DATA_WIDTH]=comparison_payload;
                end
            end
            if(FRESH_DEFAULT_LANE_DATA!=0) begin:g_default_lane_data
                // Grants are one-hot for this issue rank. Selecting lane 0
                // when no other grant exists preserves every valid packet,
                // without waiting for allocation acceptance to zero idle data.
                // With one lane the payload is simply the candidate input.
                assign fresh_valid=|grants;
                if(BE_WIDTH==1) begin:g_one_lane
                    assign fresh_payload=values;
                end else begin:g_many_lanes
                    wire [BE_WIDTH-1:0] data_grants;
                    wire unused_data_write;
                    assign data_grants={grants[BE_WIDTH-1:1],!(|grants[BE_WIDTH-1:1])};
                    rv32_frequency_event_select #(.WIDTH(ISSUE_BASE_DATA_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) fresh_select (
                        .events_i(data_grants),.values_i(values),.write_o(unused_data_write),.value_o(fresh_payload));
                end
`ifdef VERILATOR
                wire [ISSUE_BASE_DATA_WIDTH-1:0] original_payload;
                wire original_valid;
                rv32_frequency_event_select #(.WIDTH(ISSUE_BASE_DATA_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) reference_select (
                    .events_i(grants),.values_i(values),.write_o(original_valid),.value_o(original_payload));
                always @(posedge clk_i) if(!reset_i) begin
                    assert ((grants & (grants-BE_WIDTH'(1)))==0)
                        else $fatal(1,"Fresh issue rank has multiple owners");
                    assert (fresh_valid==original_valid && (!fresh_valid || fresh_payload==original_payload))
                        else $fatal(1,"Fresh default-lane data changed a valid packet");
                end
`endif
            end else begin:g_original_fresh_data
                rv32_frequency_event_select #(.WIDTH(ISSUE_BASE_DATA_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) fresh_select (
                    .events_i(grants),.values_i(values),.write_o(fresh_valid),.value_o(fresh_payload));
            end
            // Allocation is inhibited during recovery. Fresh rows have no
            // old-row recovery qualification/cancel sidebands to inherit.
            // Saved ready rows always occupy the earlier issue lanes. Fresh
            // ready allocations may use only a lane left empty by that set.
            // No downstream ready signal changes either arbitration rank.
            wire fresh_lane_allowed=(ALLOC_EMPTY_BYPASS==2) ?
                (!reset_i && !flush_valid_i && !(|selections)) : empty_allocation_issue;
            assign selected_issue_payload=fresh_lane_allowed ?
                ISSUE_DATA_WIDTH'(fresh_payload) : payload_tree[1];
            assign issue_valid_o[issue_lane]=fresh_lane_allowed ? fresh_valid : (|selections);
        end else begin:g_original_registered_issue
            assign selected_issue_payload=payload_tree[1];
            assign issue_valid_o[issue_lane]=|selections;
        end
        if(ISSUE_RECOVERY_CANCEL!=0) begin:g_selected_cancel
            assign issue_cancel_o[issue_lane]=selected_issue_payload[ISSUE_QUALIFIED_DATA_WIDTH];
        end else begin:g_no_cancel
            assign issue_cancel_o[issue_lane]=1'b0;
        end
        if(ISSUE_RECOVERY_QUALIFICATION!=0) begin:g_selected_qualification
            assign issue_recovery_qualified_o[issue_lane]=selected_issue_payload[ISSUE_BASE_DATA_WIDTH];
        end else begin:g_no_qualification
            assign issue_recovery_qualified_o[issue_lane]=1'b0;
        end
        assign {issue_op_o[issue_lane*OP_WIDTH +: OP_WIDTH],issue_pc_o[issue_lane*32 +: 32],
            issue_rob_tag_o[issue_lane*TAG_WIDTH +: TAG_WIDTH],issue_phys_rd_o[issue_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
            issue_src1_value_o[issue_lane*32 +: 32],issue_src2_value_o[issue_lane*32 +: 32],
            issue_store_data_o[issue_lane*STORE_DATA_WIDTH +: STORE_DATA_WIDTH],
            issue_metadata_o[issue_lane*METADATA_WIDTH +: METADATA_WIDTH],issue_slot_o[issue_lane*SLOT_WIDTH +: SLOT_WIDTH]}=selected_issue_payload[0 +: ISSUE_ORIGINAL_DATA_WIDTH];
        if(PC_PRECOMPUTE!=0) begin:g_selected_pc_arithmetic
            assign issue_pc_arithmetic_o[issue_lane*64 +: 64]=selected_issue_payload[ISSUE_COMPARISON_DATA_WIDTH +: 64];
`ifdef VERILATOR
            wire [31:0] selected_pc=issue_pc_o[issue_lane*32 +: 32];
            wire [31:0] selected_imm=issue_metadata_o[issue_lane*METADATA_WIDTH +: 32];
            wire [31:0] relative_pc=selected_pc+selected_imm,link_pc=selected_pc+32'd4;
            always @(posedge clk_i) if(!reset_i && issue_valid_o[issue_lane])
                assert(issue_pc_arithmetic_o[issue_lane*64 +: 64]=={link_pc,relative_pc})
                    else $fatal(1,"RS PC arithmetic differs from selected complete issue packet");
`endif
        end else begin:g_original_selected_pc_arithmetic
            assign issue_pc_arithmetic_o[issue_lane*64 +: 64]=0;
        end
        if(COMPARISON_PRECOMPUTE!=0) begin:g_selected_comparison
            assign issue_comparison_o[issue_lane*3 +: 3]=selected_issue_payload[ISSUE_ARITHMETIC_DATA_WIDTH +: 3];
`ifdef VERILATOR
            wire [OP_WIDTH-1:0] selected_op=issue_op_o[issue_lane*OP_WIDTH +: OP_WIDTH];
            wire [31:0] lhs=issue_src1_value_o[issue_lane*32 +: 32];
            wire [31:0] rhs=(selected_op==`RV32IM_OP_SLTI || selected_op==`RV32IM_OP_SLTIU) ?
                issue_metadata_o[issue_lane*METADATA_WIDTH +: 32] : issue_src2_value_o[issue_lane*32 +: 32];
            always @(posedge clk_i) if(!reset_i && issue_valid_o[issue_lane])
                assert(issue_comparison_o[issue_lane*3 +: 3]=={($signed(lhs)<$signed(rhs)),(lhs<rhs),(lhs==rhs)})
                    else $fatal(1,"RS comparison differs from selected complete issue packet");
`endif
        end else begin:g_original_selected_comparison
            assign issue_comparison_o[issue_lane*3 +: 3]=0;
        end
        if(ARITHMETIC_PRECOMPUTE!=0) begin:g_selected_arithmetic
            assign issue_arithmetic_o[issue_lane*32 +: 32]=
                selected_issue_payload[ISSUE_ORIGINAL_DATA_WIDTH +: 32];
`ifdef VERILATOR
            wire [OP_WIDTH-1:0] selected_op=issue_op_o[issue_lane*OP_WIDTH +: OP_WIDTH];
            wire [31:0] selected_lhs=issue_src1_value_o[issue_lane*32 +: 32];
            wire [31:0] selected_rhs=(selected_op==`RV32IM_OP_ADD || selected_op==`RV32IM_OP_SUB) ?
                issue_src2_value_o[issue_lane*32 +: 32] : issue_metadata_o[issue_lane*METADATA_WIDTH +: 32];
            wire [31:0] original_sum=(selected_op==`RV32IM_OP_SUB) ?
                selected_lhs-selected_rhs : selected_lhs+selected_rhs;
            always @(posedge clk_i) if(!reset_i && issue_valid_o[issue_lane])
                assert(issue_arithmetic_o[issue_lane*32 +: 32]==original_sum)
                    else $fatal(1,"RS arithmetic word differs from its selected complete packet");
`endif
        end else begin:g_original_selected_arithmetic
            assign issue_arithmetic_o[issue_lane*32 +: 32]=0;
        end
    end endgenerate

    // Allocate a contiguous prefix and choose the oldest ready entries for
    // each issue lane.  Fold current-cycle CDB wakeups into selection and the
    // operand mux.  State is still updated on the edge, but a dependent entry
    // no longer spends an otherwise idle cycle waiting for the ready bit to
    // become visible.

    genvar effective_row,effective_word;
    generate for(effective_row=0;effective_row<ENTRIES;effective_row=effective_row+1) begin:g_effective_operand
        if(WAKE_MUX_IMPL!=0) begin:g_parallel
            wire wake1=(|wake1_match[effective_row]);
            wire wake2=(|wake2_match[effective_row]);
            wire [1:0] select1,select2;
            rv32_frequency_control_tree #(.LEAVES(2)) select1_tree (
                .signal_i(!src1_ready_mem[effective_row] && wake1),.views_o(select1));
            rv32_frequency_control_tree #(.LEAVES(2)) select2_tree (
                .signal_i(!src2_ready_mem[effective_row] && wake2),.views_o(select2));
            assign src1_ready_effective[effective_row]=src1_ready_mem[effective_row] || wake1;
            assign src2_ready_effective[effective_row]=src2_ready_mem[effective_row] || wake2;
            for(effective_word=0;effective_word<2;effective_word=effective_word+1) begin:g_word
                assign src1_value_effective[effective_row][effective_word*16 +: 16]=select1[effective_word]?
                    wake1_first[effective_row][effective_word*16 +: 16]:src1_value_mem[effective_row][effective_word*16 +: 16];
                assign src2_value_effective[effective_row][effective_word*16 +: 16]=select2[effective_word]?
                    wake2_first[effective_row][effective_word*16 +: 16]:src2_value_mem[effective_row][effective_word*16 +: 16];
            end
        end else begin:g_legacy
            reg ready1,ready2;
            reg [31:0] value1,value2;
            integer source;
            always @* begin
                ready1=src1_ready_mem[effective_row];value1=src1_value_mem[effective_row];
                ready2=src2_ready_mem[effective_row];value2=src2_value_mem[effective_row];
                for(source=0;source<WAKE_WIDTH;source=source+1) begin
                    if(!ready1 && wake_valid_i[source] && wake_tag_i[source*SOURCE_TAG_WIDTH] &&
                        src1_tag_mem[effective_row][0] &&
                        wake_tag_i[source*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH]==src1_tag_mem[effective_row]) begin
                        ready1=1'b1;value1=wake_value_i[source*32 +: 32];
                    end
                    if(!ready2 && wake_valid_i[source] && wake_tag_i[source*SOURCE_TAG_WIDTH] &&
                        src2_tag_mem[effective_row][0] &&
                        wake_tag_i[source*SOURCE_TAG_WIDTH +: SOURCE_TAG_WIDTH]==src2_tag_mem[effective_row]) begin
                        ready2=1'b1;value2=wake_value_i[source*32 +: 32];
                    end
                end
            end
            assign src1_ready_effective[effective_row]=ready1;
            assign src2_ready_effective[effective_row]=ready2;
            assign src1_value_effective[effective_row]=value1;
            assign src2_value_effective[effective_row]=value2;
        end
    end endgenerate

    always @* begin
        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        allocation_count = 0;
        free_entries = ENTRIES - 32'(occupancy_reg) + 32'(allocation_release_count_o);
        prefix_open = 1'b1;
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            if (prefix_open && alloc_valid_i[lane] && (allocation_count < free_entries)) begin
                alloc_fire_o[lane] = 1'b1;
                allocation_count = allocation_count + 1;
                alloc_count_o = ALLOC_COUNT_WIDTH'(allocation_count);
            end else if (alloc_valid_i[lane]) begin
                prefix_open = 1'b0;
            end
        end

    end

    // Keep issue selection independent from the downstream ready feedback.
    // This also makes the selected operation safe to use for functional-unit
    // routing in an integration wrapper without introducing a combinational
    // ready/valid cycle.
    always @* begin
        issue_fire_count = 0;
        for (issue_fire_lane = 0; issue_fire_lane < BE_WIDTH; issue_fire_lane = issue_fire_lane + 1)
            if (issue_valid_o[issue_fire_lane] && issue_ready_i[issue_fire_lane])
                issue_fire_count = issue_fire_count + 1;
    end

    wire [COUNT_WIDTH-1:0] normal_occupancy_next;
    initial if(OCCUPANCY_DELTA_SELECT!=0 && OCCUPANCY_DELTA_SELECT!=1)
        $fatal(1,"RS occupancy delta selection must be 0 or 1");
    generate if(OCCUPANCY_DELTA_SELECT!=0) begin:g_occupancy_delta
        localparam integer LEAVES=1<<$clog2(BE_WIDTH);
        wire [BE_WIDTH:0] count_matches [1:2*LEAVES-1];
        wire [BE_WIDTH-1:0] fires=issue_valid_o & issue_ready_i;
        for(genvar lane_id=0;lane_id<LEAVES;lane_id=lane_id+1) begin:g_leaf
            for(genvar count_id=0;count_id<=BE_WIDTH;count_id=count_id+1) begin:g_count
                if(count_id==0) begin:g_zero
                    if(lane_id<BE_WIDTH) assign count_matches[LEAVES+lane_id][count_id]=!fires[lane_id];
                    else assign count_matches[LEAVES+lane_id][count_id]=1'b1;
                end else if(count_id==1 && lane_id<BE_WIDTH) begin:g_one
                    assign count_matches[LEAVES+lane_id][count_id]=fires[lane_id];
                end else begin:g_other
                    assign count_matches[LEAVES+lane_id][count_id]=1'b0;
                end
            end
        end
        for(genvar node=1;node<LEAVES;node=node+1) begin:g_sum
            for(genvar count_id=0;count_id<=BE_WIDTH;count_id=count_id+1) begin:g_count
                wire [count_id:0] terms;
                for(genvar lhs=0;lhs<=count_id;lhs=lhs+1) begin:g_term
                    assign terms[lhs]=count_matches[2*node][lhs] && count_matches[2*node+1][count_id-lhs];
                end
                assign count_matches[node][count_id]=|terms;
            end
        end
        wire [(BE_WIDTH+1)*COUNT_WIDTH-1:0] candidates;
        for(genvar count_id=0;count_id<=BE_WIDTH;count_id=count_id+1) begin:g_delta
            assign candidates[count_id*COUNT_WIDTH +: COUNT_WIDTH]=
                COUNT_WIDTH'(32'(occupancy_reg)+allocation_count-count_id);
        end
        wire selection_valid;
        rv32_frequency_event_select #(.WIDTH(COUNT_WIDTH),.EVENTS(BE_WIDTH+1),.PRIORITY(0)) count_selector (
            .events_i(count_matches[1]),.values_i(candidates),.write_o(selection_valid),.value_o(normal_occupancy_next));
        // synthesis translate_off
        always @(posedge clk_i) if(!reset_i && !flush_valid_i) begin
            if(!selection_valid || normal_occupancy_next!==
               COUNT_WIDTH'(32'(occupancy_reg)+allocation_count-issue_fire_count))
                $fatal(1,"RS selected count delta differs from original full arithmetic");
        end
        // synthesis translate_on
    end else begin:g_original_occupancy_delta
        assign normal_occupancy_next=COUNT_WIDTH'(32'(occupancy_reg)+allocation_count-issue_fire_count);
    end endgenerate

    always @(posedge clk_i) begin
        if (reset_i)
        begin
            occupancy_reg <= 0;
            age_counter <= 0;
            for (reset_slot = 0; reset_slot < ENTRIES; reset_slot = reset_slot + 1)
            begin
                valid_mem[reset_slot] <= 1'b0;
                target_live_mem_legacy[reset_slot] <= 1'b0;
                src1_ready_mem_legacy[reset_slot] <= 1'b0;
                src2_ready_mem_legacy[reset_slot] <= 1'b0;
                age_mem_legacy[reset_slot] <= 0;
            end
        end
        else
            if (flush_valid_i)
            begin
                for (reset_slot = 0; reset_slot < ENTRIES; reset_slot = reset_slot + 1)
                begin
                    if (flush_kill_mask_i[reset_slot] ||
                    ((RECOVERY_ISSUE_RELEASE!=0) && issue_release_mask[reset_slot]))
                    begin
                        valid_mem[reset_slot] <= 1'b0;
                        target_live_mem_legacy[reset_slot] <= 1'b0;
                    end
                    else
                        if (valid_mem[reset_slot])
                        begin
                            if (WAKE_MUX_IMPL != 0)
                            begin
                                if (!src1_ready_mem_legacy[reset_slot] && (|wake1_match[reset_slot]))
                                begin
                                    src1_ready_mem_legacy[reset_slot] <= 1'b1;
                                    src1_value_mem_legacy[reset_slot] <= wake1_last[reset_slot];
                                end
                                if (!src2_ready_mem_legacy[reset_slot] && (|wake2_match[reset_slot]))
                                begin
                                    src2_ready_mem_legacy[reset_slot] <= 1'b1;
                                    src2_value_mem_legacy[reset_slot] <= wake2_last[reset_slot];
                                end
                            end
                            else
                            begin
                                for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1)
                                begin
                                    if (!src1_ready_mem_legacy[reset_slot] && wake_valid_i[wake_lane] &&
                                    wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH) +: SOURCE_TAG_WIDTH] == src1_tag_mem_legacy[reset_slot] &&
                                    wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH)] && src1_tag_mem_legacy[reset_slot][0])
                                    begin
                                        src1_ready_mem_legacy[reset_slot] <= 1'b1;
                                        src1_value_mem_legacy[reset_slot] <= wake_value_i[(wake_lane*32) +: 32];
                                    end
                                    if (!src2_ready_mem_legacy[reset_slot] && wake_valid_i[wake_lane] &&
                                    wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH) +: SOURCE_TAG_WIDTH] == src2_tag_mem_legacy[reset_slot] &&
                                    wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH)] && src2_tag_mem_legacy[reset_slot][0])
                                    begin
                                        src2_ready_mem_legacy[reset_slot] <= 1'b1;
                                        src2_value_mem_legacy[reset_slot] <= wake_value_i[(wake_lane*32) +: 32];
                                    end
                                end
                            end
                        end
                end
                occupancy_reg <= COUNT_WIDTH'(remaining_count);
            end
            else
            begin
                for (wake_slot = 0; wake_slot < ENTRIES; wake_slot = wake_slot + 1)
                begin
                    if (valid_mem[wake_slot])
                    begin
                        if (WAKE_MUX_IMPL != 0)
                        begin
                            if (!src1_ready_mem_legacy[wake_slot] && (|wake1_match[wake_slot]))
                            begin
                                src1_ready_mem_legacy[wake_slot] <= 1'b1;
                                src1_value_mem_legacy[wake_slot] <= wake1_last[wake_slot];
                            end
                            if (!src2_ready_mem_legacy[wake_slot] && (|wake2_match[wake_slot]))
                            begin
                                src2_ready_mem_legacy[wake_slot] <= 1'b1;
                                src2_value_mem_legacy[wake_slot] <= wake2_last[wake_slot];
                            end
                        end
                        else
                        begin
                            for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1)
                            begin
                                if (!src1_ready_mem_legacy[wake_slot] && wake_valid_i[wake_lane] && wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH) +: SOURCE_TAG_WIDTH] == src1_tag_mem_legacy[wake_slot] && wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH)] && src1_tag_mem_legacy[wake_slot][0])
                                begin
                                    src1_ready_mem_legacy[wake_slot] <= 1'b1;
                                    src1_value_mem_legacy[wake_slot] <= wake_value_i[(wake_lane*32) +: 32];
                                end
                                if (!src2_ready_mem_legacy[wake_slot] && wake_valid_i[wake_lane] && wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH) +: SOURCE_TAG_WIDTH] == src2_tag_mem_legacy[wake_slot] && wake_tag_i[(wake_lane*SOURCE_TAG_WIDTH)] && src2_tag_mem_legacy[wake_slot][0])
                                begin
                                    src2_ready_mem_legacy[wake_slot] <= 1'b1;
                                    src2_value_mem_legacy[wake_slot] <= wake_value_i[(wake_lane*32) +: 32];
                                end
                            end
                        end
                    end
                end
                if (ALLOC_STATIC_WRITE != 0)
                begin
                    for (alloc_static_row = 0; alloc_static_row < ENTRIES; alloc_static_row = alloc_static_row + 1)
                    begin
                        if (alloc_row_write[alloc_static_row])
                        begin
                            valid_mem[alloc_static_row] <= 1'b1;
                            {target_live_mem_legacy[alloc_static_row], op_mem_legacy[alloc_static_row],
                            pc_mem_legacy[alloc_static_row], rob_tag_mem_legacy[alloc_static_row], phys_rd_mem_legacy[alloc_static_row],
                            src1_value_mem_legacy[alloc_static_row], src1_tag_mem_legacy[alloc_static_row], src1_ready_mem_legacy[alloc_static_row],
                            src2_value_mem_legacy[alloc_static_row], src2_tag_mem_legacy[alloc_static_row], src2_ready_mem_legacy[alloc_static_row],
                            store_data_mem_legacy[alloc_static_row], metadata_mem_legacy[alloc_static_row], age_mem_legacy[alloc_static_row]}
                            <= alloc_row_payload[alloc_static_row];
                        end
                    end
                end
                else
                begin
                    alloc_cursor = 0;
                    for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                    begin
                        if (alloc_fire_o[lane])
                        begin
                            alloc_slot = 0;
                            alloc_found = 1'b0;
                            for (alloc_search = 0; alloc_search < ENTRIES; alloc_search = alloc_search + 1)
                            begin
                                if (!alloc_found && (alloc_search >= alloc_cursor) && !valid_mem[alloc_search])
                                begin
                                    alloc_slot = alloc_search;
                                    alloc_found = 1'b1;
                                end
                            end
                            alloc_cursor = alloc_slot + 1;
                            valid_mem[alloc_slot] <= 1'b1;
                            target_live_mem_legacy[alloc_slot] <= alloc_target_live_i[lane] && alloc_rob_tag_i[(lane*TAG_WIDTH)];
                            op_mem_legacy[alloc_slot] <= alloc_op_i[(lane*OP_WIDTH) +: OP_WIDTH];
                            pc_mem_legacy[alloc_slot] <= alloc_pc_i[(lane*32) +: 32];
                            rob_tag_mem_legacy[alloc_slot] <= alloc_rob_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                            phys_rd_mem_legacy[alloc_slot] <= alloc_phys_rd_i[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                            src1_value_mem_legacy[alloc_slot] <= alloc_src1_value_i[(lane*32) +: 32];
                            src1_tag_mem_legacy[alloc_slot] <= alloc_src1_tag_i[(lane*SOURCE_TAG_WIDTH) +: SOURCE_TAG_WIDTH];
                            src1_ready_mem_legacy[alloc_slot] <= alloc_src1_ready_i[lane];
                            src2_value_mem_legacy[alloc_slot] <= alloc_src2_value_i[(lane*32) +: 32];
                            src2_tag_mem_legacy[alloc_slot] <= alloc_src2_tag_i[(lane*SOURCE_TAG_WIDTH) +: SOURCE_TAG_WIDTH];
                            src2_ready_mem_legacy[alloc_slot] <= alloc_src2_ready_i[lane];
                            store_data_mem_legacy[alloc_slot] <= alloc_store_data_i[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH];
                            metadata_mem_legacy[alloc_slot] <= alloc_metadata_i[(lane*METADATA_WIDTH) +: METADATA_WIDTH];
                            age_mem_legacy[alloc_slot] <= AGE_WIDTH'(32'(age_counter) + lane);
                        end
                    end
                end
                for (issue_slot = 0; issue_slot < BE_WIDTH; issue_slot = issue_slot + 1)
                begin
                    if (issue_valid_o[issue_slot] && issue_ready_i[issue_slot] &&
                        !((RELEASE_CREDITS!=0) && alloc_row_write[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]]))
                    begin
                        valid_mem[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]] <= 1'b0;
                        target_live_mem_legacy[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]] <= 1'b0;
                    end
                end
                age_counter <= AGE_WIDTH'(32'(age_counter) + allocation_count);
                occupancy_reg <= normal_occupancy_next;
            end
    end

    function automatic [COUNT_WIDTH-1:0] count_remaining_bits;
        input [ENTRIES-1:0] mask;
        integer bit_index;
        begin
            count_remaining_bits = 0;
            for (bit_index=0; bit_index<ENTRIES; bit_index=bit_index+1)
                count_remaining_bits = count_remaining_bits + COUNT_WIDTH'(mask[bit_index]);
        end
    endfunction
endmodule
