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
    parameter integer STORE_DATA_WIDTH = 32,
    parameter integer SLOT_WIDTH = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES),
    parameter integer AGE_WIDTH = 32
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire [BE_WIDTH-1:0]           alloc_valid_i,
    input  wire [(BE_WIDTH*OP_WIDTH)-1:0] alloc_op_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_pc_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_imm_i,
    input  wire [BE_WIDTH-1:0]           alloc_pred_taken_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_pred_target_i,
    input  wire [(BE_WIDTH*2)-1:0]       alloc_pred_kind_i,
    input  wire [(BE_WIDTH*2)-1:0]       alloc_mem_size_i,
    input  wire [BE_WIDTH-1:0]           alloc_mem_unsigned_i,
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
    output wire                         alloc_ready_o,
    output reg  [BE_WIDTH-1:0]           alloc_fire_o,
    output reg  [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] alloc_count_o,

    input  wire [BE_WIDTH-1:0]           wake_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] wake_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      wake_value_i,

    input  wire [BE_WIDTH-1:0]           issue_ready_i,
    output reg  [BE_WIDTH-1:0]           issue_valid_o,
    output reg  [(BE_WIDTH*OP_WIDTH)-1:0] issue_op_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_pc_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_imm_o,
    output reg  [BE_WIDTH-1:0]           issue_pred_taken_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_pred_target_o,
    output reg  [(BE_WIDTH*2)-1:0]       issue_pred_kind_o,
    output reg  [(BE_WIDTH*2)-1:0]       issue_mem_size_o,
    output reg  [BE_WIDTH-1:0]           issue_mem_unsigned_o,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] issue_rob_tag_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] issue_phys_rd_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_src1_value_o,
    output reg  [(BE_WIDTH*32)-1:0]      issue_src2_value_o,
    output reg  [(BE_WIDTH*STORE_DATA_WIDTH)-1:0] issue_store_data_o,
    output reg  [(BE_WIDTH*SLOT_WIDTH)-1:0] issue_slot_o,

    input  wire                         flush_valid_i,
    input  wire [ENTRIES-1:0]            flush_kill_mask_i,
    output wire [ENTRIES-1:0]            entry_valid_o,
    output wire [(ENTRIES*TAG_WIDTH)-1:0] entry_rob_tag_o,
    output wire [((ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1))-1:0] occupancy_o
);
    localparam integer COUNT_WIDTH = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1);
    localparam integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);

    reg valid_mem [0:ENTRIES-1];
    reg target_live_mem [0:ENTRIES-1];
    reg [OP_WIDTH-1:0] op_mem [0:ENTRIES-1];
    reg [31:0] pc_mem [0:ENTRIES-1];
    reg [31:0] imm_mem [0:ENTRIES-1];
    reg pred_taken_mem [0:ENTRIES-1];
    reg [31:0] pred_target_mem [0:ENTRIES-1];
    reg [1:0] pred_kind_mem [0:ENTRIES-1];
    reg [1:0] mem_size_mem [0:ENTRIES-1];
    reg mem_unsigned_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] rob_tag_mem [0:ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] phys_rd_mem [0:ENTRIES-1];
    reg [31:0] src1_value_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] src1_tag_mem [0:ENTRIES-1];
    reg src1_ready_mem [0:ENTRIES-1];
    reg [31:0] src2_value_mem [0:ENTRIES-1];
    reg [TAG_WIDTH-1:0] src2_tag_mem [0:ENTRIES-1];
    reg src2_ready_mem [0:ENTRIES-1];
    reg [STORE_DATA_WIDTH-1:0] store_data_mem [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_mem [0:ENTRIES-1];
    reg [AGE_WIDTH-1:0] age_counter;
    reg [COUNT_WIDTH-1:0] occupancy_reg;

    integer slot;
    integer lane;
    integer alloc_slot;
    integer allocation_count;
    integer free_entries;
    integer reset_slot;
    integer wake_slot;
    integer issue_slot;
    integer issue_fire_lane;
    integer alloc_cursor;
    integer alloc_search;
    integer flush_count;
    integer remaining_count;
    integer selected_count;
    integer issue_fire_count;
    integer chosen_slot;
    reg prefix_open;
    reg found;
    reg alloc_found;
    reg [ENTRIES-1:0] selected_mask;
    reg [AGE_WIDTH-1:0] chosen_age;
    reg [AGE_WIDTH-1:0] next_age;

    assign occupancy_o = occupancy_reg;
    assign alloc_ready_o = (alloc_count_o != 0) && !flush_valid_i;

    genvar entry_index;
    generate
        for (entry_index = 0; entry_index < ENTRIES; entry_index = entry_index + 1) begin : g_entry_state
            assign entry_valid_o[entry_index] = valid_mem[entry_index];
            assign entry_rob_tag_o[(entry_index*TAG_WIDTH) +: TAG_WIDTH] = rob_tag_mem[entry_index];
        end
    endgenerate

    // Allocate a contiguous prefix and choose the oldest ready entries for
    // each issue lane. Wakeups intentionally update state on the edge, so a
    // CDB result accepted in cycle N can issue starting in cycle N+1.
    always @* begin
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
        issue_imm_o = {(BE_WIDTH*32){1'b0}};
        issue_pred_taken_o = {BE_WIDTH{1'b0}};
        issue_pred_target_o = {(BE_WIDTH*32){1'b0}};
        issue_pred_kind_o = {(BE_WIDTH*2){1'b0}};
        issue_mem_size_o = {(BE_WIDTH*2){1'b0}};
        issue_mem_unsigned_o = {BE_WIDTH{1'b0}};
        issue_rob_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        issue_phys_rd_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        issue_src1_value_o = {(BE_WIDTH*32){1'b0}};
        issue_src2_value_o = {(BE_WIDTH*32){1'b0}};
        issue_store_data_o = {(BE_WIDTH*STORE_DATA_WIDTH){1'b0}};
        issue_slot_o = {(BE_WIDTH*SLOT_WIDTH){1'b0}};
        selected_mask = {ENTRIES{1'b0}};
        selected_count = 0;
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            found = 1'b0;
            chosen_slot = 0;
            chosen_age = {AGE_WIDTH{1'b1}};
            for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                if (valid_mem[slot] && target_live_mem[slot] && src1_ready_mem[slot] && src2_ready_mem[slot] &&
                    !selected_mask[slot] && (!found || (age_mem[slot] < chosen_age))) begin
                    found = 1'b1;
                    chosen_slot = slot;
                    chosen_age = age_mem[slot];
                end
            end
            if (found) begin
                issue_valid_o[lane] = 1'b1;
                issue_op_o[(lane*OP_WIDTH) +: OP_WIDTH] = op_mem[chosen_slot];
                issue_pc_o[(lane*32) +: 32] = pc_mem[chosen_slot];
                issue_imm_o[(lane*32) +: 32] = imm_mem[chosen_slot];
                issue_pred_taken_o[lane] = pred_taken_mem[chosen_slot];
                issue_pred_target_o[(lane*32) +: 32] = pred_target_mem[chosen_slot];
                issue_pred_kind_o[(lane*2) +: 2] = pred_kind_mem[chosen_slot];
                issue_mem_size_o[(lane*2) +: 2] = mem_size_mem[chosen_slot];
                issue_mem_unsigned_o[lane] = mem_unsigned_mem[chosen_slot];
                issue_rob_tag_o[(lane*TAG_WIDTH) +: TAG_WIDTH] = rob_tag_mem[chosen_slot];
                issue_phys_rd_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = phys_rd_mem[chosen_slot];
                issue_src1_value_o[(lane*32) +: 32] = src1_value_mem[chosen_slot];
                issue_src2_value_o[(lane*32) +: 32] = src2_value_mem[chosen_slot];
                issue_store_data_o[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH] = store_data_mem[chosen_slot];
                issue_slot_o[(lane*SLOT_WIDTH) +: SLOT_WIDTH] = chosen_slot[SLOT_WIDTH-1:0];
                selected_mask[chosen_slot] = 1'b1;
                selected_count = selected_count + 1;
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
                    for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                        if (!src1_ready_mem[reset_slot] && wake_valid_i[lane] &&
                            wake_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem[reset_slot] &&
                            wake_tag_i[(lane*TAG_WIDTH)] && src1_tag_mem[reset_slot][0]) begin
                            src1_ready_mem[reset_slot] <= 1'b1;
                            src1_value_mem[reset_slot] <= wake_value_i[(lane*32) +: 32];
                        end
                        if (!src2_ready_mem[reset_slot] && wake_valid_i[lane] &&
                            wake_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem[reset_slot] &&
                            wake_tag_i[(lane*TAG_WIDTH)] && src2_tag_mem[reset_slot][0]) begin
                            src2_ready_mem[reset_slot] <= 1'b1;
                            src2_value_mem[reset_slot] <= wake_value_i[(lane*32) +: 32];
                        end
                    end
                end
            end
            occupancy_reg <= remaining_count;
        end else begin
            for (wake_slot = 0; wake_slot < ENTRIES; wake_slot = wake_slot + 1) begin
                if (valid_mem[wake_slot]) begin
                    for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                        if (!src1_ready_mem[wake_slot] && wake_valid_i[lane] && wake_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH] == src1_tag_mem[wake_slot] && wake_tag_i[(lane*TAG_WIDTH)] && src1_tag_mem[wake_slot][0]) begin
                            src1_ready_mem[wake_slot] <= 1'b1;
                            src1_value_mem[wake_slot] <= wake_value_i[(lane*32) +: 32];
                        end
                        if (!src2_ready_mem[wake_slot] && wake_valid_i[lane] && wake_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH] == src2_tag_mem[wake_slot] && wake_tag_i[(lane*TAG_WIDTH)] && src2_tag_mem[wake_slot][0]) begin
                            src2_ready_mem[wake_slot] <= 1'b1;
                            src2_value_mem[wake_slot] <= wake_value_i[(lane*32) +: 32];
                        end
                    end
                end
            end
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
                    imm_mem[alloc_slot] <= alloc_imm_i[(lane*32) +: 32];
                    pred_taken_mem[alloc_slot] <= alloc_pred_taken_i[lane];
                    pred_target_mem[alloc_slot] <= alloc_pred_target_i[(lane*32) +: 32];
                    pred_kind_mem[alloc_slot] <= alloc_pred_kind_i[(lane*2) +: 2];
                    mem_size_mem[alloc_slot] <= alloc_mem_size_i[(lane*2) +: 2];
                    mem_unsigned_mem[alloc_slot] <= alloc_mem_unsigned_i[lane];
                    rob_tag_mem[alloc_slot] <= alloc_rob_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    phys_rd_mem[alloc_slot] <= alloc_phys_rd_i[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    src1_value_mem[alloc_slot] <= alloc_src1_value_i[(lane*32) +: 32];
                    src1_tag_mem[alloc_slot] <= alloc_src1_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    src1_ready_mem[alloc_slot] <= alloc_src1_ready_i[lane];
                    src2_value_mem[alloc_slot] <= alloc_src2_value_i[(lane*32) +: 32];
                    src2_tag_mem[alloc_slot] <= alloc_src2_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH];
                    src2_ready_mem[alloc_slot] <= alloc_src2_ready_i[lane];
                    store_data_mem[alloc_slot] <= alloc_store_data_i[(lane*STORE_DATA_WIDTH) +: STORE_DATA_WIDTH];
                    age_mem[alloc_slot] <= age_counter + lane;
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
