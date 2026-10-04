`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parameterized reservation station used for INT, MUL and DIV classes.
// The class-specific instances share this state/selection contract.
module rv32_reservation_station #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer ENTRIES = 8,
    parameter integer OP_WIDTH = `RV32IM_OP_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer WAKE_WIDTH = BE_WIDTH,
    parameter integer STORE_DATA_WIDTH = 32,
    parameter integer METADATA_WIDTH = 1,
    parameter integer WAKE_MUX_IMPL = 0,
    parameter integer ALLOC_STATIC_WRITE = 0,
    // 0: numeric comparison, 1: cached numeric comparison,
    // 2: relative allocation-order matrix (requires static allocation).
    parameter integer AGE_ORDER_MATRIX = 0,
    parameter integer LOCAL_PAYLOAD_ROWS = 0,
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
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_src1_tag_i,
    input  wire [BE_WIDTH-1:0]           alloc_src1_ready_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_src2_value_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_src2_tag_i,
    input  wire [BE_WIDTH-1:0]           alloc_src2_ready_i,
    input  wire [(BE_WIDTH*STORE_DATA_WIDTH)-1:0] alloc_store_data_i,
    input  wire [(BE_WIDTH*METADATA_WIDTH)-1:0] alloc_metadata_i,
    output wire                         alloc_ready_o,
    output reg  [BE_WIDTH-1:0]           alloc_fire_o,
    output reg  [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] alloc_count_o,

    input  wire [WAKE_WIDTH-1:0]           wake_valid_i,
    input  wire [(WAKE_WIDTH*TAG_WIDTH)-1:0] wake_tag_i,
    input  wire [(WAKE_WIDTH*32)-1:0]      wake_value_i,

    input  wire [BE_WIDTH-1:0]           issue_ready_i,
    output wire  [BE_WIDTH-1:0]           issue_valid_o,
    output wire  [(BE_WIDTH*OP_WIDTH)-1:0] issue_op_o,
    output wire  [(BE_WIDTH*32)-1:0]      issue_pc_o,
    output wire  [(BE_WIDTH*TAG_WIDTH)-1:0] issue_rob_tag_o,
    output wire  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] issue_phys_rd_o,
    output wire  [(BE_WIDTH*32)-1:0]      issue_src1_value_o,
    output wire  [(BE_WIDTH*32)-1:0]      issue_src2_value_o,
    output wire  [(BE_WIDTH*STORE_DATA_WIDTH)-1:0] issue_store_data_o,
    output wire  [(BE_WIDTH*METADATA_WIDTH)-1:0] issue_metadata_o,
    output wire  [(BE_WIDTH*SLOT_WIDTH)-1:0] issue_slot_o,

    input  wire                         flush_valid_i,
    input  wire [ENTRIES-1:0]            flush_kill_mask_i,
    output wire [ENTRIES-1:0]            entry_valid_o,
    output wire [(ENTRIES*TAG_WIDTH)-1:0] entry_rob_tag_o,
    // A read-only view of the existing base operand, including CDB bypass.
    // Store address probing does not consume an issue slot or dequeue work.
    output wire [ENTRIES-1:0]            entry_base_ready_o,
    output wire [(ENTRIES*32)-1:0]       entry_base_value_o,
    output wire [(ENTRIES*METADATA_WIDTH)-1:0] entry_metadata_o,
    output wire [((ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1))-1:0] occupancy_o
);
    localparam integer COUNT_WIDTH = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1);
    localparam integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);

    reg valid_mem [0:ENTRIES-1];
    wire target_live_mem [0:ENTRIES-1];
    reg target_live_mem_legacy [0:ENTRIES-1];
    wire [OP_WIDTH-1:0] op_mem [0:ENTRIES-1];
    reg [OP_WIDTH-1:0] op_mem_legacy [0:ENTRIES-1];
    wire [31:0] pc_mem [0:ENTRIES-1];
    reg [31:0] pc_mem_legacy [0:ENTRIES-1];
    wire [TAG_WIDTH-1:0] rob_tag_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] rob_tag_mem_legacy [0:ENTRIES-1];
    wire [PHYS_ADDR_WIDTH-1:0] phys_rd_mem [0:ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] phys_rd_mem_legacy [0:ENTRIES-1];
    wire [31:0] src1_value_mem [0:ENTRIES-1];
    reg [31:0] src1_value_mem_legacy [0:ENTRIES-1];
    wire [TAG_WIDTH-1:0] src1_tag_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] src1_tag_mem_legacy [0:ENTRIES-1];
    wire src1_ready_mem [0:ENTRIES-1];
    reg src1_ready_mem_legacy [0:ENTRIES-1];
    wire [31:0] src2_value_mem [0:ENTRIES-1];
    reg [31:0] src2_value_mem_legacy [0:ENTRIES-1];
    wire [TAG_WIDTH-1:0] src2_tag_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] src2_tag_mem_legacy [0:ENTRIES-1];
    wire src2_ready_mem [0:ENTRIES-1];
    reg src2_ready_mem_legacy [0:ENTRIES-1];
    wire [STORE_DATA_WIDTH-1:0] store_data_mem [0:ENTRIES-1];
    reg [STORE_DATA_WIDTH-1:0] store_data_mem_legacy [0:ENTRIES-1];
    // Opaque dispatch information follows the same allocation, selection and
    // recovery ownership as the operands. Invalid entry payload is undefined.
    wire [METADATA_WIDTH-1:0] metadata_mem [0:ENTRIES-1];
    reg [METADATA_WIDTH-1:0] metadata_mem_legacy [0:ENTRIES-1];
    wire [AGE_WIDTH-1:0] age_mem [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_mem_legacy [0:ENTRIES-1];
    reg src1_ready_effective [0:ENTRIES-1];
    reg [31:0] src1_value_effective [0:ENTRIES-1];
    reg src2_ready_effective [0:ENTRIES-1];
    reg [31:0] src2_value_effective [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_counter;
    reg [COUNT_WIDTH-1:0] occupancy_reg;

    integer slot;
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
    integer flush_count;
    integer remaining_count;
    integer issue_fire_count;
    reg prefix_open;
    reg alloc_found;
    wire [ENTRIES-1:0] ready_candidates;
    wire [COUNT_WIDTH-1:0] ready_rank [0:ENTRIES-1];
    wire [ENTRIES-1:0] cached_age_precedes [0:ENTRIES-1];

    assign occupancy_o = occupancy_reg;
    assign alloc_ready_o = (alloc_count_o != 0) && !flush_valid_i;

    genvar entry_index;
    generate
        for (entry_index = 0; entry_index < ENTRIES; entry_index = entry_index + 1) begin : g_entry_state
            assign entry_valid_o[entry_index] = valid_mem[entry_index];
            assign entry_rob_tag_o[(entry_index*TAG_WIDTH) +: TAG_WIDTH] = rob_tag_mem[entry_index];
            assign entry_base_ready_o[entry_index] = valid_mem[entry_index] &&
                target_live_mem[entry_index] && src1_ready_effective[entry_index] &&
                !flush_valid_i;
            assign entry_base_value_o[(entry_index*32) +: 32] = src1_value_effective[entry_index];
            assign entry_metadata_o[(entry_index*METADATA_WIDTH) +: METADATA_WIDTH] = metadata_mem[entry_index];
            assign ready_candidates[entry_index] = valid_mem[entry_index] &&
                target_live_mem[entry_index] && src1_ready_effective[entry_index] &&
                src2_ready_effective[entry_index];
        end
    endgenerate

    // Compare ages independently of the late wakeup/ready signals. Each ready
    // entry's rank is the number of older ready entries, with slot order as a
    // deterministic tie breaker. A balanced popcount avoids serial oldest-
    // search muxes across both ENTRIES and BE_WIDTH. Rank k feeds issue lane k;
    // downstream ready cannot change the selected instruction.
    localparam integer RANK_LEAVES = 2 ** SLOT_WIDTH;
    genvar rank_slot, rank_other, rank_node;
    generate
        for (rank_slot = 0; rank_slot < ENTRIES; rank_slot = rank_slot + 1) begin : g_rank
            wire [COUNT_WIDTH-1:0] count_tree [1:2*RANK_LEAVES-1];
            for (rank_other = 0; rank_other < RANK_LEAVES; rank_other = rank_other + 1) begin : g_leaf
                if (rank_other < ENTRIES && rank_other != rank_slot) begin : g_compare
                    wire older = ((AGE_ORDER_MATRIX != 0) && (ALLOC_STATIC_WRITE != 0)) ?
                        cached_age_precedes[rank_other][rank_slot] :
                        ((age_mem[rank_other] < age_mem[rank_slot]) ||
                         ((rank_other < rank_slot) && (age_mem[rank_other] == age_mem[rank_slot])));
                    assign count_tree[RANK_LEAVES+rank_other] =
                        ready_candidates[rank_other] && older;
                end else begin : g_zero
                    assign count_tree[RANK_LEAVES+rank_other] = 0;
                end
            end
            for (rank_node = 1; rank_node < RANK_LEAVES; rank_node = rank_node + 1) begin : g_sum
                assign count_tree[rank_node] = count_tree[2*rank_node] + count_tree[2*rank_node+1];
            end
            assign ready_rank[rank_slot] = count_tree[1];
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
        wire [WAKE_DOMAINS*WAKE_WIDTH*TAG_WIDTH-1:0] tag_views;
        wire [WAKE_DOMAINS*WAKE_WIDTH*32-1:0] value_views;
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH),.LEAVES(WAKE_DOMAINS)) valid_tree (
            .signal_i(wake_valid_i),.views_o(valid_views));
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH*TAG_WIDTH),.LEAVES(WAKE_DOMAINS)) tag_tree (
            .signal_i(wake_tag_i),.views_o(tag_views));
        rv32_frequency_control_tree #(.WIDTH(WAKE_WIDTH*32),.LEAVES(WAKE_DOMAINS)) value_tree (
            .signal_i(wake_value_i),.views_o(value_views));
        for (wr = 0; wr < ENTRIES; wr = wr + 1) begin : g_entry
            localparam integer DOMAIN=wr/4;
            wire [WAKE_WIDTH-1:0] first1, last1, first2, last2;
            wire [WAKE_WIDTH-1:0] local_valid=valid_views[DOMAIN*WAKE_WIDTH +: WAKE_WIDTH];
            wire [WAKE_WIDTH*TAG_WIDTH-1:0] local_tags=tag_views[DOMAIN*WAKE_WIDTH*TAG_WIDTH +: WAKE_WIDTH*TAG_WIDTH];
            wire [WAKE_WIDTH*32-1:0] local_values=value_views[DOMAIN*WAKE_WIDTH*32 +: WAKE_WIDTH*32];
            for (wl = 0; wl < WAKE_WIDTH; wl = wl + 1) begin : g_lane
                assign wake1_match[wr][wl] = local_valid[wl] && local_tags[wl*TAG_WIDTH] &&
                    src1_tag_mem[wr][0] && local_tags[wl*TAG_WIDTH +: TAG_WIDTH] == src1_tag_mem[wr];
                assign wake2_match[wr][wl] = local_valid[wl] && local_tags[wl*TAG_WIDTH] &&
                    src2_tag_mem[wr][0] && local_tags[wl*TAG_WIDTH +: TAG_WIDTH] == src2_tag_mem[wr];
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
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) first1_selector (
                .events_i(first1),.values_i(local_values),.write_o(),.value_o(wake1_first[wr]));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) last1_selector (
                .events_i(last1),.values_i(local_values),.write_o(),.value_o(wake1_last[wr]));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) first2_selector (
                .events_i(first2),.values_i(local_values),.write_o(),.value_o(wake2_first[wr]));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH)) last2_selector (
                .events_i(last2),.values_i(local_values),.write_o(),.value_o(wake2_last[wr]));
        end

    end endgenerate

    // Select allocation slots exactly as the legacy cursor walk, then decode
    // per-row write ownership before selecting the wide payload. A last-lane
    // grant retains NBA priority even for otherwise inconsistent queue state.
    localparam integer ALLOC_PAYLOAD_WIDTH = 1 + OP_WIDTH + 32 + TAG_WIDTH +
        PHYS_ADDR_WIDTH + 32 + TAG_WIDTH + 1 + 32 + TAG_WIDTH + 1 +
        STORE_DATA_WIDTH + METADATA_WIDTH + AGE_WIDTH;
    wire [SLOT_WIDTH-1:0] allocation_slots [0:BE_WIDTH-1];
    wire [ALLOC_PAYLOAD_WIDTH-1:0] alloc_lane_payload [0:BE_WIDTH-1];
    wire [ALLOC_PAYLOAD_WIDTH-1:0] alloc_row_payload [0:ENTRIES-1];
    wire [ENTRIES-1:0] alloc_row_write;
    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];
    integer pick_lane, pick_search, pick_cursor, pick_slot;
    integer alloc_static_row;
    reg pick_found;
    genvar ar, al, alloc_word;
    generate if (ALLOC_STATIC_WRITE != 0) begin : g_static_allocation
        localparam integer SLOT_LEAVES=1<<$clog2(ENTRIES);
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
        for (al = 0; al < BE_WIDTH; al = al + 1) begin : g_payload
            wire [AGE_WIDTH-1:0] lane_age = (AGE_ORDER_MATRIX==2) ? 0 : age_counter + al;
            assign alloc_lane_payload[al] = {
                alloc_target_live_i[al] && alloc_rob_tag_i[al*TAG_WIDTH],
                alloc_op_i[al*OP_WIDTH +: OP_WIDTH], alloc_pc_i[al*32 +: 32],
                alloc_rob_tag_i[al*TAG_WIDTH +: TAG_WIDTH],
                alloc_phys_rd_i[al*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                alloc_src1_value_i[al*32 +: 32], alloc_src1_tag_i[al*TAG_WIDTH +: TAG_WIDTH],
                alloc_src1_ready_i[al], alloc_src2_value_i[al*32 +: 32],
                alloc_src2_tag_i[al*TAG_WIDTH +: TAG_WIDTH], alloc_src2_ready_i[al],
                alloc_store_data_i[al*STORE_DATA_WIDTH +: STORE_DATA_WIDTH],
                alloc_metadata_i[al*METADATA_WIDTH +: METADATA_WIDTH], lane_age};
        end
        for (ar = 0; ar < ENTRIES; ar = ar + 1) begin : g_row
            wire [BE_WIDTH-1:0] allocation_match_bits, grants;
            for (al = 0; al < BE_WIDTH; al = al + 1) begin : g_grant
                assign allocation_match_bits[al] = slot_grants[ar][al];
                if (al == BE_WIDTH-1) assign grants[al] = allocation_match_bits[al];
                else assign grants[al] = allocation_match_bits[al] && !(|allocation_match_bits[BE_WIDTH-1:al+1]);
            end
            localparam integer WORDS=(ALLOC_PAYLOAD_WIDTH+15)/16;
            wire [BE_WIDTH*WORDS-1:0] payload_grants;
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(WORDS)) grant_tree (
                .signal_i(grants),.views_o(payload_grants));
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
                    assign match1[owner_lane]=wake_valid_i[owner_lane] && wake_tag_i[owner_lane*TAG_WIDTH] &&
                        src1_tag_mem[owner_row][0] && wake_tag_i[owner_lane*TAG_WIDTH +: TAG_WIDTH]==src1_tag_mem[owner_row];
                    assign match2[owner_lane]=wake_valid_i[owner_lane] && wake_tag_i[owner_lane*TAG_WIDTH] &&
                        src2_tag_mem[owner_row][0] && wake_tag_i[owner_lane*TAG_WIDTH +: TAG_WIDTH]==src2_tag_mem[owner_row];
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
            rv32_rs_payload_row #(.OP_WIDTH(OP_WIDTH),.TAG_WIDTH(TAG_WIDTH),
                .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH),.STORE_DATA_WIDTH(STORE_DATA_WIDTH),
                .METADATA_WIDTH(METADATA_WIDTH),.AGE_WIDTH(AGE_WIDTH),
                .PAYLOAD_WIDTH(ALLOC_PAYLOAD_WIDTH)) row (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_valid_i),
                .kill_i(flush_kill_mask_i[owner_row]),.valid_i(valid_mem[owner_row]),.issue_i(|issued_here),
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


    // Rank/ready remain unchanged. A selection never drives an entire packet;
    // it is distributed into <=32-bit words before balanced payload reduction.
    localparam integer ISSUE_DATA_WIDTH=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+
        64+STORE_DATA_WIDTH+METADATA_WIDTH+SLOT_WIDTH;
    localparam integer ISSUE_DATA_WORDS=(ISSUE_DATA_WIDTH+15)/16;
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
        assign issue_valid_o[issue_lane]=|selections;
        assign {issue_op_o[issue_lane*OP_WIDTH +: OP_WIDTH],issue_pc_o[issue_lane*32 +: 32],
            issue_rob_tag_o[issue_lane*TAG_WIDTH +: TAG_WIDTH],issue_phys_rd_o[issue_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
            issue_src1_value_o[issue_lane*32 +: 32],issue_src2_value_o[issue_lane*32 +: 32],
            issue_store_data_o[issue_lane*STORE_DATA_WIDTH +: STORE_DATA_WIDTH],
            issue_metadata_o[issue_lane*METADATA_WIDTH +: METADATA_WIDTH],issue_slot_o[issue_lane*SLOT_WIDTH +: SLOT_WIDTH]}=payload_tree[1];
    end endgenerate

    // Allocate a contiguous prefix and choose the oldest ready entries for
    // each issue lane.  Fold current-cycle CDB wakeups into selection and the
    // operand mux.  State is still updated on the edge, but a dependent entry
    // no longer spends an otherwise idle cycle waiting for the ready bit to
    // become visible.
    always @* begin
        for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
            src1_ready_effective[slot] = src1_ready_mem[slot];
            src1_value_effective[slot] = src1_value_mem[slot];
            src2_ready_effective[slot] = src2_ready_mem[slot];
            src2_value_effective[slot] = src2_value_mem[slot];
            if (WAKE_MUX_IMPL != 0) begin
                    if (!src1_ready_effective[slot] && (|wake1_match[slot])) begin
                        src1_ready_effective[slot] = 1'b1;
                        src1_value_effective[slot] = wake1_first[slot];
                    end
                    if (!src2_ready_effective[slot] && (|wake2_match[slot])) begin
                        src2_ready_effective[slot] = 1'b1;
                        src2_value_effective[slot] = wake2_first[slot];
                    end
                end else begin
for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1) begin
                if (!src1_ready_effective[slot] && wake_valid_i[wake_lane] &&
                    wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem[slot] &&
                    wake_tag_i[wake_lane*TAG_WIDTH] && src1_tag_mem[slot][0]) begin
                    src1_ready_effective[slot] = 1'b1;
                    src1_value_effective[slot] = wake_value_i[(wake_lane*32) +: 32];
                end
                if (!src2_ready_effective[slot] && wake_valid_i[wake_lane] &&
                    wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem[slot] &&
                    wake_tag_i[wake_lane*TAG_WIDTH] && src2_tag_mem[slot][0]) begin
                    src2_ready_effective[slot] = 1'b1;
                    src2_value_effective[slot] = wake_value_i[(wake_lane*32) +: 32];
                end
            end
                end
        end

        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        allocation_count = 0;
        free_entries = ENTRIES - occupancy_reg;
        prefix_open = 1'b1;
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            if (prefix_open && alloc_valid_i[lane] && (allocation_count < free_entries)) begin
                alloc_fire_o[lane] = 1'b1;
                allocation_count = allocation_count + 1;
                alloc_count_o = allocation_count;
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

    always @(posedge clk_i) begin
        if (reset_i) begin
            occupancy_reg <= 0;
            age_counter <= 0;
            for (reset_slot = 0; reset_slot < ENTRIES; reset_slot = reset_slot + 1) begin
                valid_mem[reset_slot] <= 1'b0;
                target_live_mem_legacy[reset_slot] <= 1'b0;
                src1_ready_mem_legacy[reset_slot] <= 1'b0;
                src2_ready_mem_legacy[reset_slot] <= 1'b0;
                age_mem_legacy[reset_slot] <= 0;
            end
        end else if (flush_valid_i) begin
            flush_count = 0;
            remaining_count = 0;
            for (reset_slot = 0; reset_slot < ENTRIES; reset_slot = reset_slot + 1) begin
                if (flush_kill_mask_i[reset_slot]) begin
                    valid_mem[reset_slot] <= 1'b0;
                    target_live_mem_legacy[reset_slot] <= 1'b0;
                    flush_count = flush_count + 1;
                end else if (valid_mem[reset_slot]) begin
                    remaining_count = remaining_count + 1;
                    if (WAKE_MUX_IMPL != 0) begin
                    if (!src1_ready_mem_legacy[reset_slot] && (|wake1_match[reset_slot])) begin
                        src1_ready_mem_legacy[reset_slot] <= 1'b1;
                        src1_value_mem_legacy[reset_slot] <= wake1_last[reset_slot];
                    end
                    if (!src2_ready_mem_legacy[reset_slot] && (|wake2_match[reset_slot])) begin
                        src2_ready_mem_legacy[reset_slot] <= 1'b1;
                        src2_value_mem_legacy[reset_slot] <= wake2_last[reset_slot];
                    end
                end else begin
for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1) begin
                        if (!src1_ready_mem_legacy[reset_slot] && wake_valid_i[wake_lane] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem_legacy[reset_slot] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH)] && src1_tag_mem_legacy[reset_slot][0]) begin
                            src1_ready_mem_legacy[reset_slot] <= 1'b1;
                            src1_value_mem_legacy[reset_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                        if (!src2_ready_mem_legacy[reset_slot] && wake_valid_i[wake_lane] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem_legacy[reset_slot] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH)] && src2_tag_mem_legacy[reset_slot][0]) begin
                            src2_ready_mem_legacy[reset_slot] <= 1'b1;
                            src2_value_mem_legacy[reset_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                    end
                end
                end
            end
            occupancy_reg <= remaining_count;
        end else begin
            for (wake_slot = 0; wake_slot < ENTRIES; wake_slot = wake_slot + 1) begin
                if (valid_mem[wake_slot]) begin
                    if (WAKE_MUX_IMPL != 0) begin
                    if (!src1_ready_mem_legacy[wake_slot] && (|wake1_match[wake_slot])) begin
                        src1_ready_mem_legacy[wake_slot] <= 1'b1;
                        src1_value_mem_legacy[wake_slot] <= wake1_last[wake_slot];
                    end
                    if (!src2_ready_mem_legacy[wake_slot] && (|wake2_match[wake_slot])) begin
                        src2_ready_mem_legacy[wake_slot] <= 1'b1;
                        src2_value_mem_legacy[wake_slot] <= wake2_last[wake_slot];
                    end
                end else begin
for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1) begin
                        if (!src1_ready_mem_legacy[wake_slot] && wake_valid_i[wake_lane] && wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem_legacy[wake_slot] && wake_tag_i[(wake_lane*TAG_WIDTH)] && src1_tag_mem_legacy[wake_slot][0]) begin
                            src1_ready_mem_legacy[wake_slot] <= 1'b1;
                            src1_value_mem_legacy[wake_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                        if (!src2_ready_mem_legacy[wake_slot] && wake_valid_i[wake_lane] && wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem_legacy[wake_slot] && wake_tag_i[(wake_lane*TAG_WIDTH)] && src2_tag_mem_legacy[wake_slot][0]) begin
                            src2_ready_mem_legacy[wake_slot] <= 1'b1;
                            src2_value_mem_legacy[wake_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                    end
                end
                end
            end
            if (ALLOC_STATIC_WRITE != 0) begin
                for (alloc_static_row = 0; alloc_static_row < ENTRIES; alloc_static_row = alloc_static_row + 1) begin
                    if (alloc_row_write[alloc_static_row]) begin
                        valid_mem[alloc_static_row] <= 1'b1;
                        {target_live_mem_legacy[alloc_static_row], op_mem_legacy[alloc_static_row],
                         pc_mem_legacy[alloc_static_row], rob_tag_mem_legacy[alloc_static_row], phys_rd_mem_legacy[alloc_static_row],
                         src1_value_mem_legacy[alloc_static_row], src1_tag_mem_legacy[alloc_static_row], src1_ready_mem_legacy[alloc_static_row],
                         src2_value_mem_legacy[alloc_static_row], src2_tag_mem_legacy[alloc_static_row], src2_ready_mem_legacy[alloc_static_row],
                         store_data_mem_legacy[alloc_static_row], metadata_mem_legacy[alloc_static_row], age_mem_legacy[alloc_static_row]}
                            <= alloc_row_payload[alloc_static_row];
                    end
                end
            end else begin
            alloc_cursor = 0;
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                if (alloc_fire_o[lane]) begin
                    alloc_slot = 0;
                    alloc_found = 1'b0;
                    for (alloc_search = 0; alloc_search < ENTRIES; alloc_search = alloc_search + 1) begin
                        if (!alloc_found && (alloc_search >= alloc_cursor) && !valid_mem[alloc_search]) begin
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
                    src1_tag_mem_legacy[alloc_slot] <= alloc_src1_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    src1_ready_mem_legacy[alloc_slot] <= alloc_src1_ready_i[lane];
                    src2_value_mem_legacy[alloc_slot] <= alloc_src2_value_i[(lane*32) +: 32];
                    src2_tag_mem_legacy[alloc_slot] <= alloc_src2_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    src2_ready_mem_legacy[alloc_slot] <= alloc_src2_ready_i[lane];
                    store_data_mem_legacy[alloc_slot] <= alloc_store_data_i[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH];
                    metadata_mem_legacy[alloc_slot] <= alloc_metadata_i[(lane*METADATA_WIDTH) +: METADATA_WIDTH];
                    age_mem_legacy[alloc_slot] <= age_counter + lane;
                end
            end
            end
            for (issue_slot = 0; issue_slot < BE_WIDTH; issue_slot = issue_slot + 1) begin
                if (issue_valid_o[issue_slot] && issue_ready_i[issue_slot]) begin
                    valid_mem[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]] <= 1'b0;
                    target_live_mem_legacy[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]] <= 1'b0;
                end
            end
            age_counter <= age_counter + allocation_count;
            occupancy_reg <= occupancy_reg + allocation_count - issue_fire_count;
        end
    end
endmodule

// Each row owns its final data writes. Wide metadata has no reset/flush
// feedback mux after its qualified and priced local write driver.
module rv32_rs_payload_row #(
    parameter integer OP_WIDTH=6,TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,
    parameter integer STORE_DATA_WIDTH=32,METADATA_WIDTH=70,AGE_WIDTH=8,
    parameter integer PAYLOAD_WIDTH=272
) (
    input wire clk_i,reset_i,flush_i,kill_i,valid_i,issue_i,alloc_i,
    input wire [PAYLOAD_WIDTH-1:0] payload_i,
    input wire wake1_i,wake2_i,
    input wire [31:0] wake1_value_i,wake2_value_i,
    output reg target_live_o,
    output wire [OP_WIDTH-1:0] op_o,
    output wire [31:0] pc_o,
    output reg [31:0] src1_value_o,src2_value_o,
    output wire [TAG_WIDTH-1:0] rob_tag_o,
    output reg [TAG_WIDTH-1:0] src1_tag_o,src2_tag_o,
    output wire [PHYS_ADDR_WIDTH-1:0] phys_rd_o,
    output reg src1_ready_o,src2_ready_o,
    output wire [STORE_DATA_WIDTH-1:0] store_data_o,
    output wire [METADATA_WIDTH-1:0] metadata_o,
    output reg [AGE_WIDTH-1:0] age_o
);
    wire new_live,new_ready1,new_ready2;
    wire [OP_WIDTH-1:0] new_op;
    wire [31:0] new_pc,new_value1,new_value2;
    wire [TAG_WIDTH-1:0] new_tag,new_tag1,new_tag2;
    wire [PHYS_ADDR_WIDTH-1:0] new_phys;
    wire [STORE_DATA_WIDTH-1:0] new_store;
    wire [METADATA_WIDTH-1:0] new_metadata;
    wire [AGE_WIDTH-1:0] new_age;
    assign {new_live,new_op,new_pc,new_tag,new_phys,new_value1,new_tag1,new_ready1,
            new_value2,new_tag2,new_ready2,new_store,new_metadata,new_age}=payload_i;
    wire allocation=!reset_i && !flush_i && alloc_i;
    wire wake_allowed=!reset_i && valid_i && (!flush_i || !kill_i);
    wire wake1_write=wake_allowed && !src1_ready_o && wake1_i;
    wire wake2_write=wake_allowed && !src2_ready_o && wake2_i;
    wire [5:0] alloc_views;
    wire src1_write,src2_write;
    rv32_frequency_control_tree #(.LEAVES(6)) allocation_tree (
        .signal_i(allocation),.views_o(alloc_views));
    rv32_frequency_control_tree #(.LEAVES(1)) value1_tree (
        .signal_i(allocation || wake1_write),.views_o(src1_write));
    rv32_frequency_control_tree #(.LEAVES(1)) value2_tree (
        .signal_i(allocation || wake2_write),.views_o(src2_write));
    localparam integer META_BITS=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+STORE_DATA_WIDTH+METADATA_WIDTH;
    wire [META_BITS-1:0] metadata_payload;
    assign {op_o,pc_o,rob_tag_o,phys_rd_o,store_data_o,metadata_o}=metadata_payload;
    rv32_frequency_word_bank #(.WIDTH(META_BITS)) metadata_owner (
        .clk_i(clk_i),.write_i(alloc_views[0]),
        .data_i({new_op,new_pc,new_tag,new_phys,new_store,new_metadata}),
        .data_o(metadata_payload));
    // Allocation wins over a simultaneous wake, exactly as the old NBA order.
    always @(posedge clk_i) begin
        if(alloc_views[1]) src1_tag_o<=new_tag1;
        if(alloc_views[2]) src2_tag_o<=new_tag2;
        if(src1_write) src1_value_o<=alloc_views[3]?new_value1:wake1_value_i;
        if(src2_write) src2_value_o<=alloc_views[4]?new_value2:wake2_value_i;
        if(reset_i) begin
            target_live_o<=0;src1_ready_o<=0;src2_ready_o<=0;age_o<=0;
        end else begin
            if(alloc_views[5]) begin
                target_live_o<=new_live;src1_ready_o<=new_ready1;src2_ready_o<=new_ready2;age_o<=new_age;
            end else begin
                if(wake1_write) src1_ready_o<=1;
                if(wake2_write) src2_ready_o<=1;
            end
            if((flush_i && kill_i) || (!flush_i && issue_i)) target_live_o<=0;
        end
    end
endmodule
