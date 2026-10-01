`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Generation-qualified reorder buffer.  The interface deliberately keeps
// architectural commit separate from store visibility and branch recovery.
module rv32_rob #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES),
    parameter integer GENERATION_WIDTH = `RV32IM_ROB_GENERATION_WIDTH,
    parameter integer TAG_WIDTH = 1 + 2 + SLOT_WIDTH + GENERATION_WIDTH,
    parameter integer CHECKPOINT_WIDTH = 1024,
    parameter integer CHECKPOINT_IMPL = 0,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    // 1 retires a store after admission into the committed LSQ/store buffer;
    // 0 preserves the precise legacy behavior of waiting for cache ack.
    parameter integer STORE_BUFFERED_RETIRE = 1
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire [BE_WIDTH-1:0]           alloc_valid_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_pc_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_inst_i,
    input  wire [(BE_WIDTH*5)-1:0]       alloc_rd_i,
    input  wire [BE_WIDTH-1:0]           alloc_rd_we_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_old_phys_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_new_phys_i,
    input  wire [BE_WIDTH-1:0]           alloc_is_store_i,
    input  wire [BE_WIDTH-1:0]           alloc_is_branch_i,
    input  wire [BE_WIDTH-1:0]           alloc_is_halt_i,
    input  wire [BE_WIDTH-1:0]           alloc_is_error_i,
    input  wire [(BE_WIDTH*CHECKPOINT_WIDTH)-1:0] alloc_checkpoint_i,
    output wire                         alloc_ready_o,
    output reg  [BE_WIDTH-1:0]           alloc_fire_o,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_tag_o,
    output reg  [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] alloc_count_o,

    input  wire [BE_WIDTH-1:0]           completion_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] completion_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      completion_value_i,
    input  wire [BE_WIDTH-1:0]           completion_done_i,
    input  wire [BE_WIDTH-1:0]           completion_error_i,
    input  wire [(BE_WIDTH*32)-1:0]      completion_store_addr_i,
    input  wire [(BE_WIDTH*4)-1:0]       completion_store_mask_i,
    input  wire [(BE_WIDTH*32)-1:0]      completion_store_data_i,

    input  wire                         commit_ready_i,
    output reg  [BE_WIDTH-1:0]           commit_valid_o,
    output reg  [BE_WIDTH-1:0]           commit_rd_we_o,
    output reg  [(BE_WIDTH*5)-1:0]       commit_rd_o,
    output reg  [(BE_WIDTH*32)-1:0]      commit_pc_o,
    output reg  [(BE_WIDTH*32)-1:0]      commit_inst_o,
    output reg  [(BE_WIDTH*32)-1:0]      commit_value_o,
    output reg  [BE_WIDTH-1:0]           commit_is_store_o,
    output reg  [(BE_WIDTH*32)-1:0]      commit_store_addr_o,
    output reg  [(BE_WIDTH*16)-1:0]      commit_store_mask_o,
    output reg  [(BE_WIDTH*128)-1:0]     commit_store_data_o,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] commit_tag_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] commit_old_phys_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] commit_new_phys_o,

    output reg                          store_commit_valid_o,
    input  wire                         store_commit_ready_i,
    output reg  [TAG_WIDTH-1:0]          store_commit_tag_o,
    output reg  [31:0]                  store_commit_addr_o,
    output reg  [15:0]                  store_commit_mask_o,
    output reg  [127:0]                 store_commit_data_o,
    input  wire                         store_ack_valid_i,
    input  wire [TAG_WIDTH-1:0]          store_ack_tag_i,
    input  wire                         store_ack_error_i,

    input  wire [BE_WIDTH-1:0]           recovery_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] recovery_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      recovery_pc_i,
    output reg                          recovery_accept_o,
    output reg                          redirect_valid_o,
    output reg  [31:0]                  redirect_pc_o,
    output reg  [3:0]                   redirect_epoch_o,
    output reg                          checkpoint_restore_valid_o,
    output reg  [CHECKPOINT_WIDTH-1:0]  checkpoint_restore_o,
    output reg                          recovery_rd_we_o,
    output reg  [4:0]                   recovery_rd_o,
    output reg  [PHYS_ADDR_WIDTH-1:0]   recovery_new_phys_o,
    output reg  [PHYS_REGS-1:0]         recovery_reclaim_bitmap_o,
    output reg  [((PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS + 1))-1:0] recovery_reclaim_count_o,

    output reg                          halted_o,
    output reg                          error_o,
    output reg  [31:0]                  return_value_o,
    output wire [SLOT_WIDTH-1:0]        head_o,
    output wire [6*SLOT_WIDTH-1:0]      head_domains_o,
    output wire [SLOT_WIDTH-1:0]        tail_o,
    output wire [((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES + 1))-1:0] occupancy_o,
    output wire [ROB_ENTRIES-1:0]       entry_valid_o,
    output wire [(ROB_ENTRIES*GENERATION_WIDTH)-1:0] entry_generation_o,
    output wire [(ROB_ENTRIES*PHYS_ADDR_WIDTH)-1:0] entry_new_phys_o,
    output wire [ROB_ENTRIES-1:0] entry_rd_we_o,
    output wire [(ROB_ENTRIES*5)-1:0] entry_rd_o,
    output wire [(ROB_ENTRIES*PHYS_ADDR_WIDTH)-1:0] entry_old_phys_o
);
    localparam integer COUNT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES + 1);
    localparam integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    localparam integer VALID_LSB = 0;
    localparam integer KIND_LSB = 1;
    localparam integer SLOT_LSB = 3;
    localparam integer GEN_LSB = SLOT_LSB + SLOT_WIDTH;

    reg valid_mem [0:ROB_ENTRIES-1];
    reg ready_mem [0:ROB_ENTRIES-1];
    reg store_mem [0:ROB_ENTRIES-1];
    reg branch_mem [0:ROB_ENTRIES-1];
    reg halt_mem [0:ROB_ENTRIES-1];
    reg error_mem [0:ROB_ENTRIES-1];
    reg store_wait_mem [0:ROB_ENTRIES-1];
    reg store_sent_mem [0:ROB_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_mem [0:ROB_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_next_mem [0:ROB_ENTRIES-1];
    reg [31:0] pc_mem [0:ROB_ENTRIES-1];
    reg [31:0] inst_mem [0:ROB_ENTRIES-1];
    reg [4:0] rd_mem [0:ROB_ENTRIES-1];
    reg rd_we_mem [0:ROB_ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] old_phys_mem [0:ROB_ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] new_phys_mem [0:ROB_ENTRIES-1];
    reg [31:0] value_mem [0:ROB_ENTRIES-1];
    reg [31:0] store_addr_mem [0:ROB_ENTRIES-1];
    // Store payloads stay access-relative in the ROB.  Expand to the
    // cache-line representation only on the external commit interface.
    reg [3:0] store_mask_mem [0:ROB_ENTRIES-1];
    reg [31:0] store_data_mem [0:ROB_ENTRIES-1];
    reg [CHECKPOINT_WIDTH-1:0] checkpoint_mem [0:ROB_ENTRIES-1];

    reg [SLOT_WIDTH-1:0] head_reg;
    wire [SLOT_WIDTH-1:0] head_next;
    wire [5*SLOT_WIDTH-1:0] head_views;
    wire [SLOT_WIDTH-1:0] head_read_index = head_views[0 +: SLOT_WIDTH];
    wire [SLOT_WIDTH-1:0] head_recovery_index = head_views[SLOT_WIDTH +: SLOT_WIDTH];
    wire [SLOT_WIDTH-1:0] head_commit_index = head_views[2*SLOT_WIDTH +: SLOT_WIDTH];
    wire [SLOT_WIDTH-1:0] head_update_index = head_views[3*SLOT_WIDTH +: SLOT_WIDTH];
    generate
        if (ROB_CONTROL_REGISTER_BANKS != 0) begin : g_head_register_banks
            rv32_control_register_bank #(.WIDTH(SLOT_WIDTH), .LEAVES(5), .ENABLED(1)) local_heads(
                .clk_i(clk_i), .reset_i(reset_i), .update_en_i(1'b1),
                .value_i(head_next), .replicas_o(head_views));
            rv32_control_register_bank #(.WIDTH(SLOT_WIDTH), .LEAVES(6), .ENABLED(1)) exported_heads(
                .clk_i(clk_i), .reset_i(reset_i), .update_en_i(1'b1),
                .value_i(head_next), .replicas_o(head_domains_o));
        end else if (ASAP7_FANOUT_BUFFERS != 0) begin : g_head_fanout
            rv32_asap7_fanout #(.WIDTH(SLOT_WIDTH), .LEAVES(5), .ENABLED(1)) tree(
                .signal_i(head_reg), .replicas_o(head_views));
            assign head_domains_o = {6{head_reg}};
        end else begin : g_head_wires
            assign head_views = {5{head_reg}};
            assign head_domains_o = {6{head_reg}};
        end
    endgenerate
    reg [SLOT_WIDTH-1:0] tail_reg;
    reg [COUNT_WIDTH-1:0] occupancy_reg;
    reg [3:0] epoch_reg;
    integer alloc_lane;
    integer complete_lane;
    integer commit_lane;
    integer recovery_lane;
    integer reset_slot;
    integer slot_index;
    integer age;
    integer chosen_age;
    integer chosen_slot;
    integer branch_age;
    integer pop_count;
    integer allocation_count;
    integer free_entries;
    integer alloc_slot;
    integer commit_slot;
    integer younger_age;
    integer recovery_slot;
    reg recovery_found;
    reg prefix_open;
    reg commit_break;
    reg [GENERATION_WIDTH-1:0] next_generation;
    initial begin
        if ((ROB_CONTROL_REGISTER_BANKS != 0 && ROB_CONTROL_REGISTER_BANKS != 1) ||
            (ROB_CONTROL_REGISTER_BANKS != 0 && ASAP7_FANOUT_BUFFERS != 0))
            $fatal(1, "invalid or conflicting ROB control-register configuration");
    end

    // Every open commit lane has already accepted all preceding lanes, so
    // its row is head+lane, not a mux address dependent on pop_count. Decode
    // the head once and read each full, access-relative packet in parallel.
    // The ordered prefix below still controls which packets are observable.
    localparam integer COMMIT_READ_WIDTH = 8 + GENERATION_WIDTH + 5 +
        5*32 + 4 + 2*PHYS_ADDR_WIDTH;
    wire [ROB_ENTRIES-1:0] head_row_select;
    localparam integer READ_GROUPS = 4;
    localparam integer READ_GROUP_WIDTH = (COMMIT_READ_WIDTH + READ_GROUPS - 1) / READ_GROUPS;
    wire [ROB_ENTRIES*BE_WIDTH*READ_GROUPS-1:0] head_read_select;
    wire [ROB_ENTRIES-1:0] next_head_row_select;
    function [COMMIT_READ_WIDTH-1:0] read_mask;
        input [READ_GROUPS-1:0] selections;
        integer bit_id;
        begin
            for (bit_id = 0; bit_id < COMMIT_READ_WIDTH; bit_id = bit_id + 1)
                read_mask[bit_id] = selections[bit_id / READ_GROUP_WIDTH];
        end
    endfunction
    wire [COMMIT_READ_WIDTH-1:0] head_packet [0:BE_WIDTH-1];
    wire head_valid [0:BE_WIDTH-1], head_ready [0:BE_WIDTH-1];
    wire head_store [0:BE_WIDTH-1], head_halt [0:BE_WIDTH-1];
    wire head_error [0:BE_WIDTH-1], head_store_wait [0:BE_WIDTH-1];
    wire head_store_sent [0:BE_WIDTH-1], head_rd_we [0:BE_WIDTH-1];
    wire [GENERATION_WIDTH-1:0] head_generation [0:BE_WIDTH-1];
    wire [4:0] head_rd [0:BE_WIDTH-1];
    wire [31:0] head_pc [0:BE_WIDTH-1], head_inst [0:BE_WIDTH-1];
    wire [31:0] head_value [0:BE_WIDTH-1], head_store_addr [0:BE_WIDTH-1];
    wire [3:0] head_store_mask [0:BE_WIDTH-1];
    wire [31:0] head_store_data [0:BE_WIDTH-1];
    wire [PHYS_ADDR_WIDTH-1:0] head_old_phys [0:BE_WIDTH-1];
    wire [PHYS_ADDR_WIDTH-1:0] head_new_phys [0:BE_WIDTH-1];
    genvar head_row, read_lane, read_group;
    generate
        if (ROB_CONTROL_REGISTER_BANKS != 0 && ROB_ENTRIES >= BE_WIDTH) begin : g_read_register_banks
            wire [ROB_ENTRIES*BE_WIDTH*READ_GROUPS-1:0] registered_head_rows;
            // Register the next decoded head on the SAME edge as head_reg.
            // The read path therefore sees the current head with no extra
            // pipeline latency. Each lane/chunk has real bounded-fanout FFs.
            rv32_control_register_bank #(.WIDTH(ROB_ENTRIES),
                .LEAVES(BE_WIDTH*READ_GROUPS), .ENABLED(1), .RESET_VALUE(1)) rows(
                .clk_i(clk_i), .reset_i(reset_i), .update_en_i(1'b1),
                .value_i(next_head_row_select), .replicas_o(registered_head_rows));
        end
        for (head_row = 0; head_row < ROB_ENTRIES; head_row = head_row + 1) begin : g_head_decode
            assign head_row_select[head_row] = (head_read_index == head_row);
            assign next_head_row_select[head_row] = (head_next == head_row);
            if (ROB_CONTROL_REGISTER_BANKS != 0 && ROB_ENTRIES >= BE_WIDTH) begin : g_row_registers
                for (read_lane = 0; read_lane < BE_WIDTH; read_lane = read_lane + 1) begin : g_lane
                    for (read_group = 0; read_group < READ_GROUPS; read_group = read_group + 1) begin : g_group
                        assign head_read_select[(head_row*BE_WIDTH+read_lane)*READ_GROUPS+read_group] =
                            g_read_register_banks.registered_head_rows[
                                (read_lane*READ_GROUPS+read_group)*ROB_ENTRIES+head_row];
                    end
                end
            end else if (ASAP7_FANOUT_BUFFERS != 0 && ROB_ENTRIES >= BE_WIDTH) begin : g_row_fanout
                rv32_asap7_fanout #(.WIDTH(1), .LEAVES(BE_WIDTH*READ_GROUPS), .ENABLED(1)) tree(
                    .signal_i(head_row_select[head_row]),
                    .replicas_o(head_read_select[head_row*BE_WIDTH*READ_GROUPS +: BE_WIDTH*READ_GROUPS]));
            end else begin : g_row_wires
                assign head_read_select[head_row*BE_WIDTH*READ_GROUPS +: BE_WIDTH*READ_GROUPS] =
                    {BE_WIDTH*READ_GROUPS{head_row_select[head_row]}};
            end
        end
        for (read_lane = 0; read_lane < BE_WIDTH; read_lane = read_lane + 1) begin : g_commit_read
            if (ROB_ENTRIES >= BE_WIDTH) begin : g_parallel
                reg [COMMIT_READ_WIDTH-1:0] packet;
                integer row;
                always @* begin
                    packet = {COMMIT_READ_WIDTH{1'b0}};
                    for (row = 0; row < ROB_ENTRIES; row = row + 1) begin
                        packet = packet | (read_mask(head_read_select[
                            (((row+ROB_ENTRIES-read_lane)%ROB_ENTRIES)*BE_WIDTH+read_lane)*READ_GROUPS +: READ_GROUPS]) &
                            {valid_mem[row], ready_mem[row], store_mem[row], halt_mem[row],
                             error_mem[row], store_wait_mem[row], store_sent_mem[row],
                             generation_mem[row], rd_we_mem[row], rd_mem[row], pc_mem[row],
                             inst_mem[row], value_mem[row], store_addr_mem[row],
                             store_mask_mem[row], store_data_mem[row], old_phys_mem[row],
                             new_phys_mem[row]});
                    end
                end
                assign head_packet[read_lane] = packet;
            end else begin : g_narrow_depth
                // Preserve the original single-wrap indexing semantics for
                // the exceptional configuration with more lanes than rows.
                wire [31:0] offset = head_read_index + read_lane;
                wire [31:0] row_index = (offset >= ROB_ENTRIES) ? offset-ROB_ENTRIES : offset;
                assign head_packet[read_lane] =
                    {valid_mem[row_index], ready_mem[row_index], store_mem[row_index],
                     halt_mem[row_index], error_mem[row_index], store_wait_mem[row_index],
                     store_sent_mem[row_index], generation_mem[row_index], rd_we_mem[row_index],
                     rd_mem[row_index], pc_mem[row_index], inst_mem[row_index], value_mem[row_index],
                     store_addr_mem[row_index], store_mask_mem[row_index], store_data_mem[row_index],
                     old_phys_mem[row_index], new_phys_mem[row_index]};
            end
            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane],
                    head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane],
                    head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane],
                    head_rd[read_lane], head_pc[read_lane], head_inst[read_lane], head_value[read_lane],
                    head_store_addr[read_lane], head_store_mask[read_lane], head_store_data[read_lane],
                    head_old_phys[read_lane], head_new_phys[read_lane]} = head_packet[read_lane];
        end
    endgenerate

    function [SLOT_WIDTH-1:0] advance_slot;
        input [SLOT_WIDTH-1:0] start;
        input integer amount;
        integer p;
        integer n;
        begin
            p = start;
            for (n = 0; n < ROB_ENTRIES; n = n + 1) begin
                if (n < amount) begin
                    if (p == ROB_ENTRIES - 1) p = 0;
                    else p = p + 1;
                end
            end
            advance_slot = p[SLOT_WIDTH-1:0];
        end
    endfunction

    // Recovery holds the architectural head exactly as in the legacy ROB.
    // All real replicated state uses this same transition, including stalls.
    assign head_next = recovery_accept_o ? head_reg :
        advance_slot(head_update_index, (commit_ready_i ? pop_count : 0));

    function [TAG_WIDTH-1:0] make_tag;
        input integer slot;
        input [GENERATION_WIDTH-1:0] generation;
        begin
            make_tag = {generation, slot[SLOT_WIDTH-1:0], 2'b00, 1'b1};
        end
    endfunction

    function [15:0] line_mask_from_relative;
        input [3:0] relative_mask;
        input [31:0] address;
        begin
            line_mask_from_relative = {12'b0, relative_mask} << address[3:0];
        end
    endfunction

    function [127:0] line_data_from_relative;
        input [31:0] relative_data;
        input [31:0] address;
        begin
            line_data_from_relative = {96'b0, relative_data} << (address[3:0] * 8);
        end
    endfunction

    function tag_matches;
        input [TAG_WIDTH-1:0] tag;
        input integer slot;
        begin
            tag_matches = tag[VALID_LSB] && valid_mem[slot] &&
                (tag[SLOT_LSB +: SLOT_WIDTH] == slot[SLOT_WIDTH-1:0]) &&
                (tag[GEN_LSB +: GENERATION_WIDTH] == generation_mem[slot]);
        end
    endfunction

    assign head_o = head_views[4*SLOT_WIDTH +: SLOT_WIDTH];
    assign tail_o = tail_reg;
    assign occupancy_o = occupancy_reg;
    assign alloc_ready_o = (alloc_count_o != 0) && !recovery_accept_o;

    genvar entry_index;
    generate
        for (entry_index = 0; entry_index < ROB_ENTRIES; entry_index = entry_index + 1) begin : g_entry_state
            assign entry_valid_o[entry_index] = valid_mem[entry_index];
            assign entry_generation_o[(entry_index*GENERATION_WIDTH) +: GENERATION_WIDTH] =
                generation_mem[entry_index];
            assign entry_new_phys_o[(entry_index*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] =
                new_phys_mem[entry_index];
            assign entry_rd_we_o[entry_index] = rd_we_mem[entry_index];
            assign entry_rd_o[(entry_index*5) +: 5] = rd_mem[entry_index];
            assign entry_old_phys_o[(entry_index*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] =
                old_phys_mem[entry_index];
        end
    endgenerate

    // Decode killed destinations in parallel. Counting distinct bits after
    // the OR reduction preserves duplicate-destination handling without a
    // serial bitmap lookup/update and increment chain across ROB_ENTRIES.
    localparam integer RECLAIM_COUNT_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS + 1);
    localparam integer RECLAIM_LEAVES = 2 ** ((PHYS_REGS <= 1) ? 0 : $clog2(PHYS_REGS));
    wire [ROB_ENTRIES-1:0] reclaim_eligible;
    wire [PHYS_REGS-1:0] reclaim_bitmap;
    wire [RECLAIM_COUNT_WIDTH-1:0] reclaim_count_tree [1:2*RECLAIM_LEAVES-1];
    genvar reclaim_entry, reclaim_phys, reclaim_match, reclaim_node;
    generate
        for (reclaim_entry = 0; reclaim_entry < ROB_ENTRIES; reclaim_entry = reclaim_entry + 1) begin : g_reclaim_age
            wire [SLOT_WIDTH-1:0] relative_age = reclaim_entry - head_recovery_index;
            assign reclaim_eligible[reclaim_entry] = recovery_found && valid_mem[reclaim_entry] &&
                rd_we_mem[reclaim_entry] && (relative_age > chosen_age) && (relative_age < occupancy_reg);
        end
        for (reclaim_phys = 0; reclaim_phys < RECLAIM_LEAVES; reclaim_phys = reclaim_phys + 1) begin : g_reclaim_phys
            if (reclaim_phys > 0 && reclaim_phys < PHYS_REGS) begin : g_register
                wire [ROB_ENTRIES-1:0] destination_matches;
                for (reclaim_match = 0; reclaim_match < ROB_ENTRIES; reclaim_match = reclaim_match + 1) begin : g_match
                    assign destination_matches[reclaim_match] = reclaim_eligible[reclaim_match] &&
                        (new_phys_mem[reclaim_match] == reclaim_phys);
                end
                assign reclaim_bitmap[reclaim_phys] = |destination_matches;
                assign reclaim_count_tree[RECLAIM_LEAVES+reclaim_phys] = |destination_matches;
            end else begin : g_zero
                if (reclaim_phys == 0) assign reclaim_bitmap[0] = 1'b0;
                assign reclaim_count_tree[RECLAIM_LEAVES+reclaim_phys] = 0;
            end
        end
        for (reclaim_node = 1; reclaim_node < RECLAIM_LEAVES; reclaim_node = reclaim_node + 1) begin : g_reclaim_sum
            assign reclaim_count_tree[reclaim_node] = reclaim_count_tree[2*reclaim_node] + reclaim_count_tree[2*reclaim_node+1];
        end
    endgenerate

    initial begin
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid ROB BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if ((ROB_ENTRIES < 2) || ((ROB_ENTRIES & (ROB_ENTRIES - 1)) != 0)) begin
            $display("ERROR: invalid ROB_ENTRIES=%0d; expected a power of two", ROB_ENTRIES);
            $finish;
        end
    end

    // Allocation and all observable outputs are evaluated from old state.
    always @* begin
        commit_lane = 0;
        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        prefix_open = 1'b1;
        allocation_count = 0;
        free_entries = ROB_ENTRIES - occupancy_reg;
        alloc_slot = 0;
        for (alloc_lane = 0; alloc_lane < BE_WIDTH; alloc_lane = alloc_lane + 1) begin
            if (prefix_open && alloc_valid_i[alloc_lane] && (allocation_count < free_entries)) begin
                alloc_fire_o[alloc_lane] = 1'b1;
                alloc_slot = tail_reg + allocation_count;
                if (alloc_slot >= ROB_ENTRIES) alloc_slot = alloc_slot - ROB_ENTRIES;
                alloc_tag_o[(alloc_lane*TAG_WIDTH) +: TAG_WIDTH] = make_tag(alloc_slot, generation_next_mem[alloc_slot]);
                allocation_count = allocation_count + 1;
                alloc_count_o = allocation_count;
            end else if (alloc_valid_i[alloc_lane]) begin
                prefix_open = 1'b0;
            end
        end

        // Recoveries are selected oldest-first using distance from head.
        recovery_found = 1'b0;
        chosen_age = ROB_ENTRIES + 1;
        chosen_slot = 0;
        for (recovery_lane = 0; recovery_lane < BE_WIDTH; recovery_lane = recovery_lane + 1) begin
            // A generation-qualified ROB tag already carries its slot.  Use
            // that slot directly and compare only the BE_WIDTH candidates.
            recovery_slot = recovery_tag_i[(recovery_lane*TAG_WIDTH) + SLOT_LSB +: SLOT_WIDTH];
            age = recovery_slot - head_recovery_index;
            if (age < 0) age = age + ROB_ENTRIES;
            if (recovery_valid_i[recovery_lane] &&
                tag_matches(recovery_tag_i[(recovery_lane*TAG_WIDTH) +: TAG_WIDTH], recovery_slot) &&
                (age < occupancy_reg) && (!recovery_found || age < chosen_age)) begin
                recovery_found = 1'b1;
                chosen_age = age;
                chosen_slot = recovery_slot;
            end
        end
        recovery_accept_o = recovery_found;
        redirect_valid_o = recovery_found;
        redirect_pc_o = 32'b0;
        redirect_epoch_o = epoch_reg + 1'b1;
        checkpoint_restore_valid_o = recovery_found;
        checkpoint_restore_o = {CHECKPOINT_WIDTH{1'b0}};
        recovery_rd_we_o = 1'b0;
        recovery_rd_o = 5'b0;
        recovery_new_phys_o = {PHYS_ADDR_WIDTH{1'b0}};
        recovery_reclaim_bitmap_o = reclaim_bitmap;
        recovery_reclaim_count_o = reclaim_count_tree[1];
        if (recovery_found) begin
            redirect_pc_o = recovery_pc_i[0 +: 32];
            if (CHECKPOINT_IMPL == 0)
                checkpoint_restore_o = checkpoint_mem[chosen_slot];
            recovery_rd_we_o = rd_we_mem[chosen_slot];
            recovery_rd_o = rd_mem[chosen_slot];
            recovery_new_phys_o = new_phys_mem[chosen_slot];
        end

        commit_valid_o = {BE_WIDTH{1'b0}};
        commit_rd_we_o = {BE_WIDTH{1'b0}};
        commit_rd_o = {(BE_WIDTH*5){1'b0}};
        commit_pc_o = {(BE_WIDTH*32){1'b0}};
        commit_inst_o = {(BE_WIDTH*32){1'b0}};
        commit_value_o = {(BE_WIDTH*32){1'b0}};
        commit_is_store_o = {BE_WIDTH{1'b0}};
        commit_store_addr_o = {(BE_WIDTH*32){1'b0}};
        commit_store_mask_o = {(BE_WIDTH*16){1'b0}};
        commit_store_data_o = {(BE_WIDTH*128){1'b0}};
        commit_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        commit_old_phys_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        commit_new_phys_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        store_commit_valid_o = 1'b0;
        store_commit_tag_o = {TAG_WIDTH{1'b0}};
        store_commit_addr_o = 32'b0;
        store_commit_mask_o = 16'b0;
        store_commit_data_o = 128'b0;
        pop_count = 0;
        commit_slot = 0;
        commit_break = 1'b0;
        if (!recovery_found && !halted_o && !error_o) begin
            for (commit_lane = 0; commit_lane < BE_WIDTH; commit_lane = commit_lane + 1) begin
                if (!commit_break) begin
                    commit_slot = head_commit_index + commit_lane;
                    if (commit_slot >= ROB_ENTRIES) commit_slot = commit_slot - ROB_ENTRIES;
                    if (head_valid[commit_lane] && head_ready[commit_lane]) begin
                        commit_valid_o[commit_lane] = 1'b1;
                        commit_rd_we_o[commit_lane] = head_rd_we[commit_lane];
                        commit_rd_o[(commit_lane*5) +: 5] = head_rd[commit_lane];
                        commit_pc_o[(commit_lane*32) +: 32] = head_pc[commit_lane];
                        commit_inst_o[(commit_lane*32) +: 32] = head_inst[commit_lane];
                        commit_value_o[(commit_lane*32) +: 32] = head_value[commit_lane];
                        commit_is_store_o[commit_lane] = head_store[commit_lane];
                        commit_store_addr_o[(commit_lane*32) +: 32] = head_store_addr[commit_lane];
                        commit_store_mask_o[(commit_lane*16) +: 16] =
                            line_mask_from_relative(head_store_mask[commit_lane], head_store_addr[commit_lane]);
                        commit_store_data_o[(commit_lane*128) +: 128] =
                            line_data_from_relative(head_store_data[commit_lane], head_store_addr[commit_lane]);
                        commit_tag_o[(commit_lane*TAG_WIDTH) +: TAG_WIDTH] = make_tag(commit_slot, head_generation[commit_lane]);
                        commit_old_phys_o[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = head_old_phys[commit_lane];
                        commit_new_phys_o[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = head_new_phys[commit_lane];
                        // Stores must become the actual ROB head before they
                        // enter the committed portion of the LSQ.  Admission
                        // to that queue is the retirement point; the LSQ then
                        // retains and drains the store like a store buffer.
                        // A store behind another lane is retried as lane zero
                        // because there is one store-admission port.
                        if (head_store[commit_lane]) begin
                            if (commit_lane == 0) begin
                                if ((STORE_BUFFERED_RETIRE != 0) &&
                                    !((head_store_addr[commit_lane] == 32'h80000000) &&
                                      (head_store_mask[commit_lane] == 4'hf)))
                                    // Admission is recorded in store_sent_mem
                                    // on the preceding edge.  Retire from that
                                    // registered state to avoid a ROB<->LSQ
                                    // combinational ready/tag loop.
                                    commit_valid_o[commit_lane] = head_store_sent[commit_lane];
                                else
                                    commit_valid_o[commit_lane] = head_store_wait[commit_lane];
                            end
                            else
                                commit_valid_o[commit_lane] = 1'b0;
                        end
                        if (commit_lane == 0 && head_store[commit_lane] &&
                            !head_store_sent[commit_lane] &&
                            ((STORE_BUFFERED_RETIRE != 0) || !head_store_wait[commit_lane])) begin
                            store_commit_valid_o = 1'b1;
                            store_commit_tag_o = make_tag(commit_slot, head_generation[commit_lane]);
                            store_commit_addr_o = head_store_addr[commit_lane];
                            store_commit_mask_o = line_mask_from_relative(
                                head_store_mask[commit_lane], head_store_addr[commit_lane]);
                            store_commit_data_o = line_data_from_relative(
                                head_store_data[commit_lane], head_store_addr[commit_lane]);
                        end
                        if (commit_valid_o[commit_lane]) begin
                            pop_count = pop_count + 1;
                            // HALT/error are precise terminal events.  A wide
                            // commit bundle must not expose younger lanes after
                            // either reaches the architectural head.
                            if (head_halt[commit_lane] || head_error[commit_lane] ||
                                (head_store[commit_lane] &&
                                 (head_store_addr[commit_lane] == 32'h80000000) &&
                                 (head_store_mask[commit_lane] == 4'hf)))
                                commit_break = 1'b1;
                        end else commit_break = 1'b1;
                    end else begin
                        commit_break = 1'b1;
                    end
                end
            end
        end
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            occupancy_reg <= 0;
            epoch_reg <= 0;
            halted_o <= 1'b0;
            error_o <= 1'b0;
            return_value_o <= 0;
            for (reset_slot = 0; reset_slot < ROB_ENTRIES; reset_slot = reset_slot + 1) begin
                valid_mem[reset_slot] <= 1'b0;
                ready_mem[reset_slot] <= 1'b0;
                store_wait_mem[reset_slot] <= 1'b0;
                store_sent_mem[reset_slot] <= 1'b0;
                error_mem[reset_slot] <= 1'b0;
                generation_mem[reset_slot] <= {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                generation_next_mem[reset_slot] <= {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
            end
        end else if (recovery_accept_o) begin
            // Keep the branch itself and all older entries; kill strict young entries.
            branch_age = chosen_age;
            for (reset_slot = 0; reset_slot < ROB_ENTRIES; reset_slot = reset_slot + 1) begin
                younger_age = reset_slot - head_update_index;
                if (younger_age < 0) younger_age = younger_age + ROB_ENTRIES;
                if (valid_mem[reset_slot] && (younger_age > branch_age) && (younger_age < occupancy_reg)) begin
                    valid_mem[reset_slot] <= 1'b0;
                    ready_mem[reset_slot] <= 1'b0;
                    store_wait_mem[reset_slot] <= 1'b0;
                    store_sent_mem[reset_slot] <= 1'b0;
                end
            end
            // Recovery and the resolving branch completion normally arrive
            // together.  Retained entries must still observe matching
            // completions or the branch can become a permanently unready
            // ROB head after its younger suffix is removed.
            for (complete_lane = 0; complete_lane < BE_WIDTH; complete_lane = complete_lane + 1) begin
                if (completion_valid_i[complete_lane] && completion_done_i[complete_lane]) begin
                    for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin
                        age = slot_index - head_update_index;
                        if (age < 0) age = age + ROB_ENTRIES;
                        if ((age <= branch_age) &&
                            tag_matches(completion_tag_i[(complete_lane*TAG_WIDTH) +: TAG_WIDTH], slot_index)) begin
                            ready_mem[slot_index] <= 1'b1;
                            value_mem[slot_index] <= completion_value_i[(complete_lane*32) +: 32];
                            if (completion_error_i[complete_lane]) error_mem[slot_index] <= 1'b1;
                            store_addr_mem[slot_index] <= completion_store_addr_i[(complete_lane*32) +: 32];
                            store_mask_mem[slot_index] <= completion_store_mask_i[(complete_lane*4) +: 4];
                            store_data_mem[slot_index] <= completion_store_data_i[(complete_lane*32) +: 32];
                        end
                    end
                end
            end
            tail_reg <= advance_slot(chosen_slot[SLOT_WIDTH-1:0], 1);
            occupancy_reg <= branch_age + 1;
            epoch_reg <= epoch_reg + 1'b1;
        end else begin
            // Tagged completion and store ack only update live generations.
            for (complete_lane = 0; complete_lane < BE_WIDTH; complete_lane = complete_lane + 1) begin
                if (completion_valid_i[complete_lane] && completion_done_i[complete_lane]) begin
                    for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin
                        if (tag_matches(completion_tag_i[(complete_lane*TAG_WIDTH) +: TAG_WIDTH], slot_index)) begin
                            ready_mem[slot_index] <= 1'b1;
                            value_mem[slot_index] <= completion_value_i[(complete_lane*32) +: 32];
                            if (completion_error_i[complete_lane]) error_mem[slot_index] <= 1'b1;
                            store_addr_mem[slot_index] <= completion_store_addr_i[(complete_lane*32) +: 32];
                            store_mask_mem[slot_index] <= completion_store_mask_i[(complete_lane*4) +: 4];
                            store_data_mem[slot_index] <= completion_store_data_i[(complete_lane*32) +: 32];
                        end
                    end
                end
            end
            for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin
                if (store_ack_valid_i && tag_matches(store_ack_tag_i, slot_index)) begin
                    store_wait_mem[slot_index] <= 1'b1;
                    if (store_ack_error_i) error_mem[slot_index] <= 1'b1;
                end
            end
            if (store_commit_valid_o && store_commit_ready_i) begin
                store_sent_mem[head_commit_index] <= 1'b1;
            end
            // Precise architectural side effects occur only on popped head entries.
            for (commit_lane = 0; commit_lane < BE_WIDTH; commit_lane = commit_lane + 1) begin
                if (commit_valid_o[commit_lane] && commit_ready_i) begin
                    commit_slot = head_commit_index + commit_lane;
                    if (commit_slot >= ROB_ENTRIES) commit_slot = commit_slot - ROB_ENTRIES;
                    if (head_store[commit_lane] &&
                        (head_store_addr[commit_lane] == 32'h80000000) &&
                        (head_store_mask[commit_lane] == 4'hf)) begin
                        halted_o <= 1'b1;
                        return_value_o <= head_store_data[commit_lane];
                    end else if (head_halt[commit_lane]) begin
                        halted_o <= 1'b1;
                        return_value_o <= head_value[commit_lane];
                    end
                    if (head_error[commit_lane]) error_o <= 1'b1;
                    valid_mem[commit_slot] <= 1'b0;
                    ready_mem[commit_slot] <= 1'b0;
                    store_wait_mem[commit_slot] <= 1'b0;
                    store_sent_mem[commit_slot] <= 1'b0;
                end
            end
            // Allocate the accepted contiguous prefix at tail.
            for (alloc_lane = 0; alloc_lane < BE_WIDTH; alloc_lane = alloc_lane + 1) begin
                if (alloc_fire_o[alloc_lane]) begin
                    alloc_slot = tail_reg + alloc_lane;
                    if (alloc_slot >= ROB_ENTRIES) alloc_slot = alloc_slot - ROB_ENTRIES;
                    next_generation = generation_next_mem[alloc_slot];
                    if (next_generation == {GENERATION_WIDTH{1'b0}})
                        next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                    generation_mem[alloc_slot] <= next_generation;
                    generation_next_mem[alloc_slot] <= (next_generation == {GENERATION_WIDTH{1'b1}}) ? {{(GENERATION_WIDTH-1){1'b0}}, 1'b1} : next_generation + 1'b1;
                    valid_mem[alloc_slot] <= 1'b1;
                    ready_mem[alloc_slot] <= 1'b0;
                    store_wait_mem[alloc_slot] <= 1'b0;
                    store_sent_mem[alloc_slot] <= 1'b0;
                    store_mem[alloc_slot] <= alloc_is_store_i[alloc_lane];
                    branch_mem[alloc_slot] <= alloc_is_branch_i[alloc_lane];
                    halt_mem[alloc_slot] <= alloc_is_halt_i[alloc_lane];
                    error_mem[alloc_slot] <= alloc_is_error_i[alloc_lane];
                    pc_mem[alloc_slot] <= alloc_pc_i[(alloc_lane*32) +: 32];
                    inst_mem[alloc_slot] <= alloc_inst_i[(alloc_lane*32) +: 32];
                    rd_mem[alloc_slot] <= alloc_rd_i[(alloc_lane*5) +: 5];
                    rd_we_mem[alloc_slot] <= alloc_rd_we_i[alloc_lane];
                    old_phys_mem[alloc_slot] <= alloc_old_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    new_phys_mem[alloc_slot] <= alloc_new_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    if (CHECKPOINT_IMPL == 0)
                        checkpoint_mem[alloc_slot] <= alloc_checkpoint_i[(alloc_lane*CHECKPOINT_WIDTH) +: CHECKPOINT_WIDTH];
                end
            end
            head_reg <= head_next;
            tail_reg <= advance_slot(tail_reg, allocation_count);
            occupancy_reg <= occupancy_reg - (commit_ready_i ? pop_count : 0) + allocation_count;
        end
    end
endmodule
