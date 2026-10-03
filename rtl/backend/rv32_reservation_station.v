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
    parameter integer AGE_ORDER_MATRIX = 0,
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
    output reg  [BE_WIDTH-1:0]           issue_valid_o,
    output reg  [(BE_WIDTH*OP_WIDTH)-1:0] issue_op_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_pc_o,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] issue_rob_tag_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] issue_phys_rd_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_src1_value_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_src2_value_o,
    output reg  [(BE_WIDTH*STORE_DATA_WIDTH)-1:0] issue_store_data_o,
    output reg  [(BE_WIDTH*METADATA_WIDTH)-1:0] issue_metadata_o,
    output reg  [(BE_WIDTH*SLOT_WIDTH)-1:0] issue_slot_o,

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
    reg target_live_mem [0:ENTRIES-1];
    reg [OP_WIDTH-1:0] op_mem [0:ENTRIES-1];
    reg [31:0] pc_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] rob_tag_mem [0:ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] phys_rd_mem [0:ENTRIES-1];
    reg [31:0] src1_value_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] src1_tag_mem [0:ENTRIES-1];
    reg src1_ready_mem [0:ENTRIES-1];
    reg [31:0] src2_value_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] src2_tag_mem [0:ENTRIES-1];
    reg src2_ready_mem [0:ENTRIES-1];
    reg [STORE_DATA_WIDTH-1:0] store_data_mem [0:ENTRIES-1];
    // Opaque dispatch information follows the same allocation, selection and
    // recovery ownership as the operands. Invalid entry payload is undefined.
    reg [METADATA_WIDTH-1:0] metadata_mem [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_mem [0:ENTRIES-1];
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
        for (wr = 0; wr < ENTRIES; wr = wr + 1) begin : g_entry
            wire [WAKE_WIDTH-1:0] first1, last1, first2, last2;
            for (wl = 0; wl < WAKE_WIDTH; wl = wl + 1) begin : g_lane
                assign wake1_match[wr][wl] = wake_valid_i[wl] && wake_tag_i[wl*TAG_WIDTH] &&
                    src1_tag_mem[wr][0] && wake_tag_i[wl*TAG_WIDTH +: TAG_WIDTH] == src1_tag_mem[wr];
                assign wake2_match[wr][wl] = wake_valid_i[wl] && wake_tag_i[wl*TAG_WIDTH] &&
                    src2_tag_mem[wr][0] && wake_tag_i[wl*TAG_WIDTH +: TAG_WIDTH] == src2_tag_mem[wr];
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
            reg [31:0] f1, l1, f2, l2;
            integer k;
            always @* begin
                f1 = 0; l1 = 0; f2 = 0; l2 = 0;
                for (k = 0; k < WAKE_WIDTH; k = k + 1) begin
                    f1 = f1 | ({32{first1[k]}} & wake_value_i[k*32 +: 32]);
                    l1 = l1 | ({32{last1[k]}} & wake_value_i[k*32 +: 32]);
                    f2 = f2 | ({32{first2[k]}} & wake_value_i[k*32 +: 32]);
                    l2 = l2 | ({32{last2[k]}} & wake_value_i[k*32 +: 32]);
                end
            end
            assign wake1_first[wr] = f1;
            assign wake1_last[wr] = l1;
            assign wake2_first[wr] = f2;
            assign wake2_last[wr] = l2;
        end
    end endgenerate

    // Select allocation slots exactly as the legacy cursor walk, then decode
    // per-row write ownership before selecting the wide payload. A last-lane
    // grant retains NBA priority even for otherwise inconsistent queue state.
    localparam integer ALLOC_PAYLOAD_WIDTH = 1 + OP_WIDTH + 32 + TAG_WIDTH +
        PHYS_ADDR_WIDTH + 32 + TAG_WIDTH + 1 + 32 + TAG_WIDTH + 1 +
        STORE_DATA_WIDTH + METADATA_WIDTH + AGE_WIDTH;
    reg [SLOT_WIDTH-1:0] allocation_slots [0:BE_WIDTH-1];
    wire [ALLOC_PAYLOAD_WIDTH-1:0] alloc_lane_payload [0:BE_WIDTH-1];
    wire [ALLOC_PAYLOAD_WIDTH-1:0] alloc_row_payload [0:ENTRIES-1];
    wire [ENTRIES-1:0] alloc_row_write;
    wire [BE_WIDTH-1:0] alloc_row_grants [0:ENTRIES-1];
    integer pick_lane, pick_search, pick_cursor, pick_slot;
    integer alloc_static_row;
    reg pick_found;
    genvar ar, al;
    generate if (ALLOC_STATIC_WRITE != 0) begin : g_static_allocation
        always @* begin
            pick_cursor = 0;
            pick_slot = 0;
            pick_found = 0;
            for (pick_lane = 0; pick_lane < BE_WIDTH; pick_lane = pick_lane + 1) begin
                allocation_slots[pick_lane] = 0;
                if (alloc_fire_o[pick_lane]) begin
                    pick_slot = 0;
                    pick_found = 0;
                    for (pick_search = 0; pick_search < ENTRIES; pick_search = pick_search + 1) begin
                        if (!pick_found && pick_search >= pick_cursor && !valid_mem[pick_search]) begin
                            pick_slot = pick_search;
                            pick_found = 1;
                        end
                    end
                    allocation_slots[pick_lane] = pick_slot;
                    pick_cursor = pick_slot + 1;
                end
            end
        end
        for (al = 0; al < BE_WIDTH; al = al + 1) begin : g_payload
            wire [AGE_WIDTH-1:0] lane_age = age_counter + al;
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
                assign allocation_match_bits[al] = alloc_fire_o[al] && allocation_slots[al] == ar;
                if (al == BE_WIDTH-1) assign grants[al] = allocation_match_bits[al];
                else assign grants[al] = allocation_match_bits[al] && !(|allocation_match_bits[BE_WIDTH-1:al+1]);
            end
            reg [ALLOC_PAYLOAD_WIDTH-1:0] payload;
            integer mux_lane;
            always @* begin
                payload = 0;
                for (mux_lane = 0; mux_lane < BE_WIDTH; mux_lane = mux_lane + 1)
                    payload = payload | ({ALLOC_PAYLOAD_WIDTH{grants[mux_lane]}} & alloc_lane_payload[mux_lane]);
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
    generate if ((AGE_ORDER_MATRIX != 0) && (ALLOC_STATIC_WRITE != 0)) begin : g_age_order_matrix
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

        issue_valid_o = {BE_WIDTH{1'b0}};
        issue_op_o = {(BE_WIDTH*OP_WIDTH){1'b0}};
        issue_pc_o = {(BE_WIDTH*32){1'b0}};
        issue_rob_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        issue_phys_rd_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        issue_src1_value_o = {(BE_WIDTH*32){1'b0}};
        issue_src2_value_o = {(BE_WIDTH*32){1'b0}};
        issue_store_data_o = {(BE_WIDTH*STORE_DATA_WIDTH){1'b0}};
        issue_metadata_o = {(BE_WIDTH*METADATA_WIDTH){1'b0}};
        issue_slot_o = {(BE_WIDTH*SLOT_WIDTH){1'b0}};
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                if (ready_candidates[slot] && (ready_rank[slot] == lane)) begin
                    issue_valid_o[lane] = 1'b1;
                    issue_op_o[(lane*OP_WIDTH) +: OP_WIDTH] = issue_op_o[(lane*OP_WIDTH) +: OP_WIDTH] | op_mem[slot];
                    issue_pc_o[(lane*32) +: 32] = issue_pc_o[(lane*32) +: 32] | pc_mem[slot];
                    issue_rob_tag_o[(lane*TAG_WIDTH) +: TAG_WIDTH] = issue_rob_tag_o[(lane*TAG_WIDTH) +: TAG_WIDTH] | rob_tag_mem[slot];
                    issue_phys_rd_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = issue_phys_rd_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] | phys_rd_mem[slot];
                    issue_src1_value_o[(lane*32) +: 32] = issue_src1_value_o[(lane*32) +: 32] | src1_value_effective[slot];
                    issue_src2_value_o[(lane*32) +: 32] = issue_src2_value_o[(lane*32) +: 32] | src2_value_effective[slot];
                    issue_store_data_o[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH] = issue_store_data_o[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH] | store_data_mem[slot];
                    issue_metadata_o[(lane*METADATA_WIDTH) +: METADATA_WIDTH] = issue_metadata_o[(lane*METADATA_WIDTH) +: METADATA_WIDTH] | metadata_mem[slot];
                    issue_slot_o[(lane*SLOT_WIDTH) +: SLOT_WIDTH] = issue_slot_o[(lane*SLOT_WIDTH) +: SLOT_WIDTH] | slot[SLOT_WIDTH-1:0];
                end
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
                target_live_mem[reset_slot] <= 1'b0;
                src1_ready_mem[reset_slot] <= 1'b0;
                src2_ready_mem[reset_slot] <= 1'b0;
                age_mem[reset_slot] <= 0;
            end
        end else if (flush_valid_i) begin
            flush_count = 0;
            remaining_count = 0;
            for (reset_slot = 0; reset_slot < ENTRIES; reset_slot = reset_slot + 1) begin
                if (flush_kill_mask_i[reset_slot]) begin
                    valid_mem[reset_slot] <= 1'b0;
                    target_live_mem[reset_slot] <= 1'b0;
                    flush_count = flush_count + 1;
                end else if (valid_mem[reset_slot]) begin
                    remaining_count = remaining_count + 1;
                    if (WAKE_MUX_IMPL != 0) begin
                    if (!src1_ready_mem[reset_slot] && (|wake1_match[reset_slot])) begin
                        src1_ready_mem[reset_slot] <= 1'b1;
                        src1_value_mem[reset_slot] <= wake1_last[reset_slot];
                    end
                    if (!src2_ready_mem[reset_slot] && (|wake2_match[reset_slot])) begin
                        src2_ready_mem[reset_slot] <= 1'b1;
                        src2_value_mem[reset_slot] <= wake2_last[reset_slot];
                    end
                end else begin
for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1) begin
                        if (!src1_ready_mem[reset_slot] && wake_valid_i[wake_lane] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem[reset_slot] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH)] && src1_tag_mem[reset_slot][0]) begin
                            src1_ready_mem[reset_slot] <= 1'b1;
                            src1_value_mem[reset_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                        if (!src2_ready_mem[reset_slot] && wake_valid_i[wake_lane] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem[reset_slot] &&
                            wake_tag_i[(wake_lane*TAG_WIDTH)] && src2_tag_mem[reset_slot][0]) begin
                            src2_ready_mem[reset_slot] <= 1'b1;
                            src2_value_mem[reset_slot] <= wake_value_i[(wake_lane*32) +: 32];
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
                    if (!src1_ready_mem[wake_slot] && (|wake1_match[wake_slot])) begin
                        src1_ready_mem[wake_slot] <= 1'b1;
                        src1_value_mem[wake_slot] <= wake1_last[wake_slot];
                    end
                    if (!src2_ready_mem[wake_slot] && (|wake2_match[wake_slot])) begin
                        src2_ready_mem[wake_slot] <= 1'b1;
                        src2_value_mem[wake_slot] <= wake2_last[wake_slot];
                    end
                end else begin
for (wake_lane = 0; wake_lane < WAKE_WIDTH; wake_lane = wake_lane + 1) begin
                        if (!src1_ready_mem[wake_slot] && wake_valid_i[wake_lane] && wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem[wake_slot] && wake_tag_i[(wake_lane*TAG_WIDTH)] && src1_tag_mem[wake_slot][0]) begin
                            src1_ready_mem[wake_slot] <= 1'b1;
                            src1_value_mem[wake_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                        if (!src2_ready_mem[wake_slot] && wake_valid_i[wake_lane] && wake_tag_i[(wake_lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem[wake_slot] && wake_tag_i[(wake_lane*TAG_WIDTH)] && src2_tag_mem[wake_slot][0]) begin
                            src2_ready_mem[wake_slot] <= 1'b1;
                            src2_value_mem[wake_slot] <= wake_value_i[(wake_lane*32) +: 32];
                        end
                    end
                end
                end
            end
            if (ALLOC_STATIC_WRITE != 0) begin
                for (alloc_static_row = 0; alloc_static_row < ENTRIES; alloc_static_row = alloc_static_row + 1) begin
                    if (alloc_row_write[alloc_static_row]) begin
                        valid_mem[alloc_static_row] <= 1'b1;
                        {target_live_mem[alloc_static_row], op_mem[alloc_static_row],
                         pc_mem[alloc_static_row], rob_tag_mem[alloc_static_row], phys_rd_mem[alloc_static_row],
                         src1_value_mem[alloc_static_row], src1_tag_mem[alloc_static_row], src1_ready_mem[alloc_static_row],
                         src2_value_mem[alloc_static_row], src2_tag_mem[alloc_static_row], src2_ready_mem[alloc_static_row],
                         store_data_mem[alloc_static_row], metadata_mem[alloc_static_row], age_mem[alloc_static_row]}
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
                    target_live_mem[alloc_slot] <= alloc_target_live_i[lane] && alloc_rob_tag_i[(lane*TAG_WIDTH)];
                    op_mem[alloc_slot] <= alloc_op_i[(lane*OP_WIDTH) +: OP_WIDTH];
                    pc_mem[alloc_slot] <= alloc_pc_i[(lane*32) +: 32];
                    rob_tag_mem[alloc_slot] <= alloc_rob_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    phys_rd_mem[alloc_slot] <= alloc_phys_rd_i[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    src1_value_mem[alloc_slot] <= alloc_src1_value_i[(lane*32) +: 32];
                    src1_tag_mem[alloc_slot] <= alloc_src1_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    src1_ready_mem[alloc_slot] <= alloc_src1_ready_i[lane];
                    src2_value_mem[alloc_slot] <= alloc_src2_value_i[(lane*32) +: 32];
                    src2_tag_mem[alloc_slot] <= alloc_src2_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    src2_ready_mem[alloc_slot] <= alloc_src2_ready_i[lane];
                    store_data_mem[alloc_slot] <= alloc_store_data_i[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH];
                    metadata_mem[alloc_slot] <= alloc_metadata_i[(lane*METADATA_WIDTH) +: METADATA_WIDTH];
                    age_mem[alloc_slot] <= age_counter + lane;
                end
            end
            end
            for (issue_slot = 0; issue_slot < BE_WIDTH; issue_slot = issue_slot + 1) begin
                if (issue_valid_o[issue_slot] && issue_ready_i[issue_slot]) begin
                    valid_mem[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]] <= 1'b0;
                    target_live_mem[issue_slot_o[(issue_slot*SLOT_WIDTH) +: SLOT_WIDTH]] <= 1'b0;
                end
            end
            age_counter <= age_counter + allocation_count;
            occupancy_reg <= occupancy_reg + allocation_count - issue_fire_count;
        end
    end
endmodule
