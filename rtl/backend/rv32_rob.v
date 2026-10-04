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
    parameter integer MMIO_PREDECODE = 0,
    parameter integer CHECKPOINT_IMPL = 0,
    // Preview captures a recovery transaction; apply is a later clock edge.
    // Default 0 preserves the standalone legacy interface behavior.
    parameter integer STAGED_RECOVERY = 0,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    // One read per physical modulo-BE bank, then rotate into strict commit order.
    // Pure combinational layout; original state, writes and fallback remain.
    parameter integer COMMIT_BANKED_READ = 0,
    // Select one complete allocation payload per modulo-BE bank, then decode
    // its destination row. Keeps all allocation and completion write priority.
    parameter integer ALLOC_BANKED_WRITE = 0,
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
    input  wire                         recovery_apply_i,
    input  wire                         recovery_hold_i,
    output wire                         recovery_preview_valid_o,
    output wire                         recovery_accept_o,
    output wire                         redirect_valid_o,
    output reg  [31:0]                  redirect_pc_o,
    output reg  [3:0]                   redirect_epoch_o,
    output wire                         checkpoint_restore_valid_o,
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

    wire valid_mem [0:ROB_ENTRIES-1];
    reg valid_mem_write_data [0:ROB_ENTRIES-1];
    reg valid_mem_write_enable [0:ROB_ENTRIES-1];
    wire ready_mem [0:ROB_ENTRIES-1];
    reg ready_mem_write_data [0:ROB_ENTRIES-1];
    reg ready_mem_write_enable [0:ROB_ENTRIES-1];
    wire store_mem [0:ROB_ENTRIES-1];
    reg store_mem_write_data [0:ROB_ENTRIES-1];
    reg store_mem_write_enable [0:ROB_ENTRIES-1];
    wire branch_mem [0:ROB_ENTRIES-1];
    reg branch_mem_write_data [0:ROB_ENTRIES-1];
    reg branch_mem_write_enable [0:ROB_ENTRIES-1];
    wire halt_mem [0:ROB_ENTRIES-1];
    reg halt_mem_write_data [0:ROB_ENTRIES-1];
    reg halt_mem_write_enable [0:ROB_ENTRIES-1];
    wire error_mem [0:ROB_ENTRIES-1];
    reg error_mem_write_data [0:ROB_ENTRIES-1];
    reg error_mem_write_enable [0:ROB_ENTRIES-1];
    wire store_wait_mem [0:ROB_ENTRIES-1];
    reg store_wait_mem_write_data [0:ROB_ENTRIES-1];
    reg store_wait_mem_write_enable [0:ROB_ENTRIES-1];
    wire store_sent_mem [0:ROB_ENTRIES-1];
    reg store_sent_mem_write_data [0:ROB_ENTRIES-1];
    reg store_sent_mem_write_enable [0:ROB_ENTRIES-1];
    wire [GENERATION_WIDTH-1:0] generation_mem [0:ROB_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_mem_write_data [0:ROB_ENTRIES-1];
    reg generation_mem_write_enable [0:ROB_ENTRIES-1];
    wire [GENERATION_WIDTH-1:0] generation_next_mem [0:ROB_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_next_mem_write_data [0:ROB_ENTRIES-1];
    reg generation_next_mem_write_enable [0:ROB_ENTRIES-1];
    wire [31:0] pc_mem [0:ROB_ENTRIES-1];
    reg [31:0] pc_mem_write_data [0:ROB_ENTRIES-1];
    reg pc_mem_write_enable [0:ROB_ENTRIES-1];
    wire [31:0] inst_mem [0:ROB_ENTRIES-1];
    reg [31:0] inst_mem_write_data [0:ROB_ENTRIES-1];
    reg inst_mem_write_enable [0:ROB_ENTRIES-1];
    wire [4:0] rd_mem [0:ROB_ENTRIES-1];
    reg [4:0] rd_mem_write_data [0:ROB_ENTRIES-1];
    reg rd_mem_write_enable [0:ROB_ENTRIES-1];
    wire rd_we_mem [0:ROB_ENTRIES-1];
    reg rd_we_mem_write_data [0:ROB_ENTRIES-1];
    reg rd_we_mem_write_enable [0:ROB_ENTRIES-1];
    wire [PHYS_ADDR_WIDTH-1:0] old_phys_mem [0:ROB_ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] old_phys_mem_write_data [0:ROB_ENTRIES-1];
    reg old_phys_mem_write_enable [0:ROB_ENTRIES-1];
    wire [PHYS_ADDR_WIDTH-1:0] new_phys_mem [0:ROB_ENTRIES-1];
    reg [PHYS_ADDR_WIDTH-1:0] new_phys_mem_write_data [0:ROB_ENTRIES-1];
    reg new_phys_mem_write_enable [0:ROB_ENTRIES-1];
    wire [31:0] value_mem [0:ROB_ENTRIES-1];
    reg [31:0] value_mem_write_data [0:ROB_ENTRIES-1];
    reg value_mem_write_enable [0:ROB_ENTRIES-1];
    wire [31:0] store_addr_mem [0:ROB_ENTRIES-1];
    reg [31:0] store_addr_mem_write_data [0:ROB_ENTRIES-1];
    reg store_addr_mem_write_enable [0:ROB_ENTRIES-1];
    // Updated with exactly the same completion enable/priority as address and
    // mask. Payload remains observable; only retirement classification moves.
    wire mmio_word_mem [0:ROB_ENTRIES-1];
    reg mmio_word_mem_write_data [0:ROB_ENTRIES-1];
    reg mmio_word_mem_write_enable [0:ROB_ENTRIES-1];
    // Store payloads stay access-relative in the ROB.  Expand to the
    // cache-line representation only on the external commit interface.
    wire [3:0] store_mask_mem [0:ROB_ENTRIES-1];
    reg [3:0] store_mask_mem_write_data [0:ROB_ENTRIES-1];
    reg store_mask_mem_write_enable [0:ROB_ENTRIES-1];
    wire [31:0] store_data_mem [0:ROB_ENTRIES-1];
    reg [31:0] store_data_mem_write_data [0:ROB_ENTRIES-1];
    reg store_data_mem_write_enable [0:ROB_ENTRIES-1];
    wire [CHECKPOINT_WIDTH-1:0] checkpoint_mem [0:ROB_ENTRIES-1];
    reg [CHECKPOINT_WIDTH-1:0] checkpoint_mem_write_data [0:ROB_ENTRIES-1];
    reg checkpoint_mem_write_enable [0:ROB_ENTRIES-1];

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
            rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(5)) tree (
                .signal_i(head_reg),.views_o(head_views));
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
    reg [SLOT_WIDTH-1:0] age;
    integer chosen_age;
    integer chosen_slot;
    integer branch_age;
    integer pop_count;
    integer allocation_count;
    integer free_entries;
    integer alloc_slot;
    integer commit_slot;
    reg [SLOT_WIDTH-1:0] younger_age;
    integer recovery_slot;
    // Procedural scratch belongs to one process. Sharing these integers with
    // the combinational allocation/commit decoder creates multiple RTL drivers
    // when the complete ROB is synthesized as an observable component.
    integer update_alloc_lane;
    integer update_alloc_slot;
    integer update_commit_lane;
    integer update_commit_slot;
    reg [SLOT_WIDTH-1:0] update_completion_age;
    integer update_alloc_entry;
    reg recovery_found;
    reg recovery_saved_valid;
    wire [SLOT_WIDTH-1:0] recovery_saved_slot, recovery_saved_age;
    wire [ROB_ENTRIES-1:0] recovery_saved_kill;
    wire [ROB_ENTRIES-1:0] recovery_preview_kill;
    wire [SLOT_WIDTH-1:0] apply_slot = STAGED_RECOVERY ? recovery_saved_slot : chosen_slot;
    wire [SLOT_WIDTH-1:0] apply_age = STAGED_RECOVERY ? recovery_saved_age : chosen_age;
    wire recovery_apply = STAGED_RECOVERY ?
        (recovery_apply_i && recovery_saved_valid) : recovery_found;
    wire recovery_hold = STAGED_RECOVERY && recovery_hold_i;
    wire [5:0] recovery_domains;
    wire [2:0] recovery_preview_domains;
    rv32_frequency_control_tree #(.LEAVES(6)) recovery_tree (
        .signal_i(recovery_apply),.views_o(recovery_domains));
    rv32_frequency_control_tree #(.LEAVES(3)) recovery_preview_tree (
        .signal_i(recovery_found),.views_o(recovery_preview_domains));
    assign recovery_preview_valid_o=recovery_preview_domains[0];
    assign recovery_accept_o=recovery_domains[0];
    assign redirect_valid_o=STAGED_RECOVERY ? recovery_preview_domains[1] : recovery_domains[1];
    assign checkpoint_restore_valid_o=recovery_domains[2];
    // chosen_age is either a slot distance or ROB_ENTRIES+1 (no match).
    // COUNT_WIDTH retains that sentinel; SLOT_WIDTH alone would truncate it.
    localparam integer RECOVERY_QUERY_WIDTH=SLOT_WIDTH+2*COUNT_WIDTH+1;
    localparam integer RECOVERY_QUERY_DOMAINS=(ROB_ENTRIES+3)/4;
    wire [RECOVERY_QUERY_DOMAINS*RECOVERY_QUERY_WIDTH-1:0] recovery_query_views;
    wire [ROB_ENTRIES-1:0] recovery_row_preview;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_QUERY_WIDTH),.LEAVES(RECOVERY_QUERY_DOMAINS)) recovery_query_tree (
        .signal_i({recovery_preview_domains[2],head_recovery_index,COUNT_WIDTH'(chosen_age),occupancy_reg}),
        .views_o(recovery_query_views));
    genvar recovery_row;
    generate for(recovery_row=0;recovery_row<ROB_ENTRIES;recovery_row=recovery_row+1) begin:g_recovery_descriptor
        wire preview;
        wire [SLOT_WIDTH-1:0] local_head;
        wire [COUNT_WIDTH-1:0] local_branch_age,local_occupancy;
        assign {preview,local_head,local_branch_age,local_occupancy}=
            recovery_query_views[(recovery_row/4)*RECOVERY_QUERY_WIDTH +: RECOVERY_QUERY_WIDTH];
        wire [SLOT_WIDTH-1:0] relative_age=recovery_row-local_head;
        assign recovery_preview_kill[recovery_row]=valid_mem[recovery_row] &&
            relative_age>local_branch_age && relative_age<local_occupancy;
        assign recovery_row_preview[recovery_row]=preview;
    end endgenerate
    localparam integer RECOVERY_SAVED_WIDTH=ROB_ENTRIES+2*SLOT_WIDTH;
    wire [RECOVERY_SAVED_WIDTH-1:0] recovery_saved_payload;
    wire recovery_save_payload=!reset_i && !recovery_domains[5] && recovery_hold &&
        recovery_preview_domains[0] && !recovery_saved_valid;
    assign {recovery_saved_slot,recovery_saved_age,recovery_saved_kill}=recovery_saved_payload;
    // Same preview edge and unreset payload as the original descriptor.
    rv32_frequency_word_bank #(.WIDTH(RECOVERY_SAVED_WIDTH)) recovery_saved_owner (
        .clk_i(clk_i),.write_i(recovery_save_payload),
        .data_i({SLOT_WIDTH'(chosen_slot),SLOT_WIDTH'(chosen_age),recovery_preview_kill}),
        .data_o(recovery_saved_payload));
    // Allocation and commit are held between preview and apply, so these
    // physical slot identities cannot be reused while the mask is pending.
    always @(posedge clk_i) begin
        if(reset_i) recovery_saved_valid<=1'b0;
        else if(recovery_domains[5] || !recovery_hold) recovery_saved_valid<=1'b0;
        else if(recovery_preview_domains[0] && !recovery_saved_valid) begin
            recovery_saved_valid<=1'b1;
            // Payload is captured by the bounded owner on this same edge.
        end
    end
    reg prefix_open;
    reg commit_break;
    reg [GENERATION_WIDTH-1:0] next_generation;
    // This scratch is evaluated in physical-row order, not legacy lane order.
    // Do not conflate the two nonarchitectural temporaries in name-based proof.
    reg [GENERATION_WIDTH-1:0] bank_next_generation;
    initial begin
        if ((COMMIT_BANKED_READ != 0 && COMMIT_BANKED_READ != 1) ||
            (ALLOC_BANKED_WRITE != 0 && ALLOC_BANKED_WRITE != 1) ||
            (ROB_CONTROL_REGISTER_BANKS != 0 && ROB_CONTROL_REGISTER_BANKS != 1) ||
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
    wire [BE_WIDTH-1:0] head_mmio_word;
    genvar mmio_lane;
    generate for (mmio_lane=0; mmio_lane<BE_WIDTH; mmio_lane=mmio_lane+1) begin:g_mmio_read
        wire [31:0] raw_slot = head_commit_index + mmio_lane;
        wire [31:0] selected_slot = (raw_slot >= ROB_ENTRIES) ? raw_slot - ROB_ENTRIES : raw_slot;
        assign head_mmio_word[mmio_lane] = (MMIO_PREDECODE != 0) ?
            mmio_word_mem[selected_slot] :
            ((head_store_addr[mmio_lane] == 32'h80000000) &&
             (head_store_mask[mmio_lane] == 4'hf));
    end endgenerate

    wire [COMMIT_READ_WIDTH-1:0] bank_packet [0:BE_WIDTH-1];
    localparam integer BANK_ROWS = (ROB_ENTRIES >= BE_WIDTH) ? ROB_ENTRIES / BE_WIDTH : 1;
    genvar commit_bank, bank_row, bank_offset;
    generate
        if (COMMIT_BANKED_READ != 0 && ROB_ENTRIES >= BE_WIDTH &&
            ROB_CONTROL_REGISTER_BANKS == 0 && ASAP7_FANOUT_BUFFERS == 0) begin : g_banked_commit
            for (commit_bank = 0; commit_bank < BE_WIDTH; commit_bank = commit_bank + 1) begin : g_bank
                wire [BANK_ROWS-1:0] row_select;
                for (bank_row = 0; bank_row < BANK_ROWS; bank_row = bank_row + 1) begin : g_row
                    wire [BE_WIDTH-1:0] possible_heads;
                    // A window of BE_WIDTH consecutive rows contains exactly
                    // one row of each bank, even across the ROB wrap boundary.
                    for (bank_offset = 0; bank_offset < BE_WIDTH; bank_offset = bank_offset + 1) begin : g_head
                        assign possible_heads[bank_offset] = head_row_select[
                            (bank_row*BE_WIDTH+commit_bank+ROB_ENTRIES-bank_offset)%ROB_ENTRIES];
                    end
                    assign row_select[bank_row] = |possible_heads;
                end
                reg [COMMIT_READ_WIDTH-1:0] packet;
                integer row;
                always @* begin
                    packet = {COMMIT_READ_WIDTH{1'b0}};
                    for (row = 0; row < BANK_ROWS; row = row + 1) begin
                        packet = packet | ({COMMIT_READ_WIDTH{row_select[row]}} &
                            {valid_mem[row*BE_WIDTH+commit_bank], ready_mem[row*BE_WIDTH+commit_bank],
                             store_mem[row*BE_WIDTH+commit_bank], halt_mem[row*BE_WIDTH+commit_bank],
                             error_mem[row*BE_WIDTH+commit_bank], store_wait_mem[row*BE_WIDTH+commit_bank],
                             store_sent_mem[row*BE_WIDTH+commit_bank], generation_mem[row*BE_WIDTH+commit_bank],
                             rd_we_mem[row*BE_WIDTH+commit_bank], rd_mem[row*BE_WIDTH+commit_bank],
                             pc_mem[row*BE_WIDTH+commit_bank], inst_mem[row*BE_WIDTH+commit_bank],
                             value_mem[row*BE_WIDTH+commit_bank], store_addr_mem[row*BE_WIDTH+commit_bank],
                             store_mask_mem[row*BE_WIDTH+commit_bank], store_data_mem[row*BE_WIDTH+commit_bank],
                             old_phys_mem[row*BE_WIDTH+commit_bank], new_phys_mem[row*BE_WIDTH+commit_bank]});
                    end
                end
                assign bank_packet[commit_bank] = packet;
            end
        end
    endgenerate
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
            if (COMMIT_BANKED_READ != 0 && ROB_ENTRIES >= BE_WIDTH &&
                ROB_CONTROL_REGISTER_BANKS == 0 && ASAP7_FANOUT_BUFFERS == 0) begin : g_bank_rotation
                assign head_packet[read_lane] = bank_packet[(head_read_index+read_lane)%BE_WIDTH];
            end else if (ROB_ENTRIES >= BE_WIDTH) begin : g_parallel
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

    localparam integer ALLOC_PACKET_WIDTH = 4 + 32 + 32 + 5 + 1 +
                                             2*PHYS_ADDR_WIDTH + CHECKPOINT_WIDTH;
    wire [BE_WIDTH-1:0] bank_alloc_fire;
    wire [SLOT_WIDTH-1:0] bank_alloc_slot [0:BE_WIDTH-1];
    wire [ALLOC_PACKET_WIDTH-1:0] bank_alloc_packet [0:BE_WIDTH-1];

    genvar alloc_bank,alloc_source,alloc_word,alloc_node;
    localparam integer ALLOC_DATA_WIDTH=ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH+
        ((CHECKPOINT_IMPL==0)?CHECKPOINT_WIDTH:0);
    localparam integer ALLOC_DATA_WORDS=(ALLOC_DATA_WIDTH+15)/16;
    localparam integer ALLOC_DATA_LEAVES=1<<$clog2(BE_WIDTH);
    generate
        for(alloc_bank=0;alloc_bank<BE_WIDTH;alloc_bank=alloc_bank+1) begin:g_bank_allocation
            if(ALLOC_BANKED_WRITE!=0 && ROB_ENTRIES>=BE_WIDTH) begin:g_enabled
                wire [BE_WIDTH-1:0] row_match_mask,grants;
                wire [SLOT_WIDTH-1:0] slots [1:2*ALLOC_DATA_LEAVES-1];
                wire [ALLOC_DATA_WIDTH-1:0] packets [1:2*ALLOC_DATA_LEAVES-1];
                for(alloc_source=0;alloc_source<ALLOC_DATA_LEAVES;alloc_source=alloc_source+1) begin:g_source
                    if(alloc_source<BE_WIDTH) begin:g_present
                        wire [SLOT_WIDTH-1:0] target_slot=tail_reg+alloc_source;
                        wire [ALLOC_PACKET_WIDTH-1:0] full_payload={
                            alloc_is_store_i[alloc_source],alloc_is_branch_i[alloc_source],
                            alloc_is_halt_i[alloc_source],alloc_is_error_i[alloc_source],
                            alloc_pc_i[alloc_source*32 +: 32],alloc_inst_i[alloc_source*32 +: 32],
                            alloc_rd_i[alloc_source*5 +: 5],alloc_rd_we_i[alloc_source],
                            alloc_old_phys_i[alloc_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                            alloc_new_phys_i[alloc_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                            alloc_checkpoint_i[alloc_source*CHECKPOINT_WIDTH +: CHECKPOINT_WIDTH]};
                        wire [ALLOC_DATA_WIDTH-1:0] active_payload;
                        wire [ALLOC_DATA_WORDS-1:0] selected_words;
                        if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                            assign active_payload=full_payload;
                        end else begin:g_without_checkpoint
                            assign active_payload=full_payload[CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
                        end
                        assign row_match_mask[alloc_source]=alloc_fire_o[alloc_source] &&
                            ((tail_reg+alloc_source)%BE_WIDTH)==alloc_bank;
                        if(alloc_source==BE_WIDTH-1) begin:g_last
                            assign grants[alloc_source]=row_match_mask[alloc_source];
                        end else begin:g_priority
                            assign grants[alloc_source]=row_match_mask[alloc_source] &&
                                !(|row_match_mask[BE_WIDTH-1:alloc_source+1]);
                        end
                        rv32_frequency_control_tree #(.LEAVES(ALLOC_DATA_WORDS)) selection_tree (
                            .signal_i(grants[alloc_source]),.views_o(selected_words));
                        assign slots[ALLOC_DATA_LEAVES+alloc_source]={SLOT_WIDTH{grants[alloc_source]}} & target_slot;
                        for(alloc_word=0;alloc_word<ALLOC_DATA_WORDS;alloc_word=alloc_word+1) begin:g_word
                            localparam integer LOW=alloc_word*16;
                            localparam integer BITS=ALLOC_DATA_WIDTH-LOW>=16 ? 16 : ALLOC_DATA_WIDTH-LOW;
                            assign packets[ALLOC_DATA_LEAVES+alloc_source][LOW +: BITS]=
                                {BITS{selected_words[alloc_word]}} & active_payload[LOW +: BITS];
                        end
                    end else begin:g_padding
                        assign slots[ALLOC_DATA_LEAVES+alloc_source]=0;
                        assign packets[ALLOC_DATA_LEAVES+alloc_source]=0;
                    end
                end
                for(alloc_node=1;alloc_node<ALLOC_DATA_LEAVES;alloc_node=alloc_node+1) begin:g_or
                    assign slots[alloc_node]=slots[2*alloc_node] | slots[2*alloc_node+1];
                    assign packets[alloc_node]=packets[2*alloc_node] | packets[2*alloc_node+1];
                end
                assign bank_alloc_fire[alloc_bank]=|row_match_mask;
                assign bank_alloc_slot[alloc_bank]=slots[1];
                if(CHECKPOINT_IMPL==0) begin:g_full_result
                    assign bank_alloc_packet[alloc_bank]=packets[1];
                end else begin:g_compact_result
                    assign bank_alloc_packet[alloc_bank]={packets[1],{CHECKPOINT_WIDTH{1'b0}}};
                end
            end else begin:g_disabled
                assign bank_alloc_fire[alloc_bank]=0;
                assign bank_alloc_slot[alloc_bank]=0;
                assign bank_alloc_packet[alloc_bank]=0;
            end
        end
    endgenerate

    function [SLOT_WIDTH-1:0] advance_slot;
        input [SLOT_WIDTH-1:0] start;
        input integer amount;
        begin
            // The original loop performs clamp(amount,0,ROB_ENTRIES)
            // increments. Power-of-two depth makes one complete traversal
            // return to start; preserve this even for BE_WIDTH > depth.
            // Otherwise the SLOT_WIDTH result supplies exact modulo wrap.
            if (amount <= 0 || amount >= ROB_ENTRIES)
                advance_slot = start;
            else
                advance_slot = start + amount;
        end
    endfunction

    // Recovery holds the architectural head exactly as in the legacy ROB.
    // All real replicated state uses this same transition, including stalls.
    assign head_next = (recovery_domains[3] || recovery_hold) ? head_reg :
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
    assign alloc_ready_o = (alloc_count_o != 0) && !recovery_domains[3] && !recovery_hold;

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
    localparam integer RECLAIM_LOW_WIDTH=(PHYS_ADDR_WIDTH/2<1)?1:PHYS_ADDR_WIDTH/2;
    localparam integer RECLAIM_HIGH_WIDTH=PHYS_ADDR_WIDTH-RECLAIM_LOW_WIDTH;
    localparam integer RECLAIM_HIGH_SLICE_WIDTH=(RECLAIM_HIGH_WIDTH<1)?1:RECLAIM_HIGH_WIDTH;
    localparam integer RECLAIM_LOW_CODES=1<<RECLAIM_LOW_WIDTH;
    localparam integer RECLAIM_HIGH_CODES=1<<RECLAIM_HIGH_WIDTH;
    wire [ROB_ENTRIES*PHYS_REGS-1:0] reclaim_row_destinations;
    wire [RECLAIM_COUNT_WIDTH-1:0] reclaim_count_tree [1:2*RECLAIM_LEAVES-1];
    genvar reclaim_entry, reclaim_phys, reclaim_match, reclaim_node;
    generate
        for (reclaim_entry = 0; reclaim_entry < ROB_ENTRIES; reclaim_entry = reclaim_entry + 1) begin : g_reclaim_age
            // Share the exact per-row interval predicate with the saved mask.
            assign reclaim_eligible[reclaim_entry]=recovery_row_preview[reclaim_entry] &&
                rd_we_mem[reclaim_entry] && recovery_preview_kill[reclaim_entry];
        end
        // Qualify the small high predecode before the cross-product. With
        // PHYS64 each eligibility source owns eight decode consumers rather
        // than one comparison/qualification gate for every physical register.
        // Kept inversion boundaries retain the two predecode domains through
        // course ABC; each current predecode bit has <=eight final consumers.
        for(genvar reclaim_decode_row=0;reclaim_decode_row<ROB_ENTRIES;reclaim_decode_row=reclaim_decode_row+1) begin:g_reclaim_destination_row
            wire [PHYS_ADDR_WIDTH-1:0] destination=new_phys_mem[reclaim_decode_row];
            wire [RECLAIM_HIGH_SLICE_WIDTH-1:0] high_destination=destination>>RECLAIM_LOW_WIDTH;
            wire [RECLAIM_LOW_CODES-1:0] low_decode,low_views;
            wire [RECLAIM_HIGH_CODES-1:0] high_decode,high_views;
            for(genvar low_code=0;low_code<RECLAIM_LOW_CODES;low_code=low_code+1) begin:g_low_code
                assign low_decode[low_code]=destination[0 +: RECLAIM_LOW_WIDTH]==RECLAIM_LOW_WIDTH'(low_code);
            end
            for(genvar high_code=0;high_code<RECLAIM_HIGH_CODES;high_code=high_code+1) begin:g_high_code
                // No zero-width part-select/cast even at PHYS_ADDR_WIDTH=1.
                // In that case the sole high_destination/code is constant0.
                assign high_decode[high_code]=reclaim_eligible[reclaim_decode_row] &&
                    high_destination==RECLAIM_HIGH_SLICE_WIDTH'(high_code);
            end
            rv32_frequency_control_tree #(.WIDTH(RECLAIM_LOW_CODES),.LEAVES(1)) low_decode_tree (
                .signal_i(low_decode),.views_o(low_views));
            rv32_frequency_control_tree #(.WIDTH(RECLAIM_HIGH_CODES),.LEAVES(1)) high_decode_tree (
                .signal_i(high_decode),.views_o(high_views));
            for(genvar destination_phys=0;destination_phys<PHYS_REGS;destination_phys=destination_phys+1) begin:g_destination
                if(destination_phys==0) begin:g_zero
                    assign reclaim_row_destinations[reclaim_decode_row*PHYS_REGS+destination_phys]=1'b0;
                end else begin:g_register
                    assign reclaim_row_destinations[reclaim_decode_row*PHYS_REGS+destination_phys]=
                        low_views[destination_phys%RECLAIM_LOW_CODES] && high_views[destination_phys/RECLAIM_LOW_CODES];
                end
            end
        end
        for (reclaim_phys = 0; reclaim_phys < RECLAIM_LEAVES; reclaim_phys = reclaim_phys + 1) begin : g_reclaim_phys
            if (reclaim_phys > 0 && reclaim_phys < PHYS_REGS) begin : g_register
                wire [ROB_ENTRIES-1:0] destination_matches;
                for (reclaim_match = 0; reclaim_match < ROB_ENTRIES; reclaim_match = reclaim_match + 1) begin : g_match
                    assign destination_matches[reclaim_match]=
                        reclaim_row_destinations[reclaim_match*PHYS_REGS+reclaim_phys];
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

    // Recovery lane tags query only live/generation metadata. Qualified
    // destination/checkpoint payload has a separate selected-slot read.
    localparam integer RECOVERY_LIVE_WIDTH=GENERATION_WIDTH+1;
    localparam integer RECOVERY_DEST_WIDTH=6+PHYS_ADDR_WIDTH+CHECKPOINT_WIDTH;
    wire [ROB_ENTRIES*RECOVERY_LIVE_WIDTH-1:0] recovery_live_rows;
    wire [ROB_ENTRIES*RECOVERY_DEST_WIDTH-1:0] recovery_dest_rows;
    wire [BE_WIDTH-1:0] recovery_lane_live;
    wire [RECOVERY_DEST_WIDTH-1:0] recovery_selected_dest;
    wire recovery_selected_rd_we;
    wire [4:0] recovery_selected_rd;
    wire [PHYS_ADDR_WIDTH-1:0] recovery_selected_phys;
    wire [CHECKPOINT_WIDTH-1:0] recovery_selected_checkpoint;
    assign {recovery_selected_checkpoint,recovery_selected_rd_we,recovery_selected_rd,recovery_selected_phys}=
        recovery_selected_dest;
    generate
        for(genvar recovery_query_row=0;recovery_query_row<ROB_ENTRIES;recovery_query_row=recovery_query_row+1) begin:g_recovery_query_row
            assign recovery_live_rows[recovery_query_row*RECOVERY_LIVE_WIDTH +: RECOVERY_LIVE_WIDTH]=
                {valid_mem[recovery_query_row],generation_mem[recovery_query_row]};
            if(CHECKPOINT_IMPL==0) begin:g_checkpoint
                assign recovery_dest_rows[recovery_query_row*RECOVERY_DEST_WIDTH +: RECOVERY_DEST_WIDTH]=
                    {checkpoint_mem[recovery_query_row],rd_we_mem[recovery_query_row],rd_mem[recovery_query_row],new_phys_mem[recovery_query_row]};
            end else begin:g_no_checkpoint
                assign recovery_dest_rows[recovery_query_row*RECOVERY_DEST_WIDTH +: RECOVERY_DEST_WIDTH]=
                    {{CHECKPOINT_WIDTH{1'b0}},rd_we_mem[recovery_query_row],rd_mem[recovery_query_row],new_phys_mem[recovery_query_row]};
            end
        end
        for(genvar recovery_query_lane=0;recovery_query_lane<BE_WIDTH;recovery_query_lane=recovery_query_lane+1) begin:g_recovery_lane_query
            wire [TAG_WIDTH-1:0] tag=recovery_tag_i[recovery_query_lane*TAG_WIDTH +: TAG_WIDTH];
            wire [RECOVERY_LIVE_WIDTH-1:0] live_state;
            rv32_frequency_array_read #(.WIDTH(RECOVERY_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) live_reader (
                .rows_i(recovery_live_rows),.index_i(tag[SLOT_LSB +: SLOT_WIDTH]),.value_o(live_state));
            assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] && live_state[GENERATION_WIDTH] &&
                tag[GEN_LSB +: GENERATION_WIDTH]==live_state[0 +: GENERATION_WIDTH];
        end
    endgenerate
    rv32_frequency_array_read #(.WIDTH(RECOVERY_DEST_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) recovery_dest_reader (
        .rows_i(recovery_dest_rows),.index_i(SLOT_WIDTH'(chosen_slot)),.value_o(recovery_selected_dest));

    // Allocation and all observable outputs are evaluated from old state.
    always @* begin
        commit_lane = 0;
        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        prefix_open = !recovery_hold;
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
            if (recovery_valid_i[recovery_lane] &&
                recovery_lane_live[recovery_lane] &&
                (age < occupancy_reg) && (!recovery_found || age < chosen_age)) begin
                recovery_found = 1'b1;
                chosen_age = age;
                chosen_slot = recovery_slot;
            end
        end
        redirect_pc_o = 32'b0;
        redirect_epoch_o = epoch_reg + 1'b1;
        checkpoint_restore_o = {CHECKPOINT_WIDTH{1'b0}};
        recovery_rd_we_o = 1'b0;
        recovery_rd_o = 5'b0;
        recovery_new_phys_o = {PHYS_ADDR_WIDTH{1'b0}};
        recovery_reclaim_bitmap_o = reclaim_bitmap;
        recovery_reclaim_count_o = reclaim_count_tree[1];
        if (recovery_preview_domains[2]) begin
            redirect_pc_o = recovery_pc_i[0 +: 32];
            if (CHECKPOINT_IMPL == 0)
                checkpoint_restore_o = recovery_selected_checkpoint;
            recovery_rd_we_o = recovery_selected_rd_we;
            recovery_rd_o = recovery_selected_rd;
            recovery_new_phys_o = recovery_selected_phys;
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
        if (!recovery_domains[5] && !recovery_hold && !halted_o && !error_o) begin
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
                                    !(head_mmio_word[commit_lane]))
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
                                 head_mmio_word[commit_lane]))
                                commit_break = 1'b1;
                        end else commit_break = 1'b1;
                    end else begin
                        commit_break = 1'b1;
                    end
                end
            end
        end
    end


    // Broadcast small metadata and data through bounded domains. Every row
    // qualifies its own updates before the final payload selection drivers.
    localparam integer WRITE_DOMAINS=4;
    localparam integer LOCAL_COMPLETION_DATA_WIDTH=101;
    localparam integer LOCAL_COMPLETION_WIDTH=3+TAG_WIDTH+LOCAL_COMPLETION_DATA_WIDTH;
    localparam integer LOCAL_COMPLETION_LEAVES=1<<$clog2(BE_WIDTH);
    wire [BE_WIDTH*LOCAL_COMPLETION_WIDTH-1:0] local_completion_input;
    wire [WRITE_DOMAINS*BE_WIDTH*LOCAL_COMPLETION_WIDTH-1:0] local_completion_domains;
    wire [2*ROB_ENTRIES-1:0] local_modes;
    wire [WRITE_DOMAINS*3*SLOT_WIDTH-1:0] local_indexes;
    wire [WRITE_DOMAINS*BE_WIDTH-1:0] local_commits;
    wire [WRITE_DOMAINS-1:0] local_store_sends;
    wire [WRITE_DOMAINS*(TAG_WIDTH+2)-1:0] local_acks;
    genvar command_row,command_lane,command_node;
    generate
    if(ALLOC_BANKED_WRITE!=0 && ROB_ENTRIES>=BE_WIDTH) begin:g_local_row_commands
        for(command_lane=0;command_lane<BE_WIDTH;command_lane=command_lane+1) begin:g_input
            wire mmio=(completion_store_addr_i[command_lane*32 +: 32]==32'h80000000) &&
                (completion_store_mask_i[command_lane*4 +: 4]==4'hf);
            assign local_completion_input[command_lane*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH]={
                completion_valid_i[command_lane],completion_done_i[command_lane],
                completion_error_i[command_lane],completion_tag_i[command_lane*TAG_WIDTH +: TAG_WIDTH],
                completion_value_i[command_lane*32 +: 32],
                completion_store_addr_i[command_lane*32 +: 32],
                completion_store_data_i[command_lane*32 +: 32],
                completion_store_mask_i[command_lane*4 +: 4],mmio};
        end
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*LOCAL_COMPLETION_WIDTH),.LEAVES(WRITE_DOMAINS)) completion_tree (
            .signal_i(local_completion_input),.views_o(local_completion_domains));
        rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(ROB_ENTRIES)) mode_tree (
            .signal_i({recovery_domains[5],reset_i}),.views_o(local_modes));
        rv32_frequency_control_tree #(.WIDTH(3*SLOT_WIDTH),.LEAVES(WRITE_DOMAINS)) index_tree (
            .signal_i({apply_age,head_commit_index,head_update_index}),.views_o(local_indexes));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(WRITE_DOMAINS)) commit_tree (
            .signal_i(commit_valid_o & {BE_WIDTH{commit_ready_i}}),.views_o(local_commits));
        rv32_frequency_control_tree #(.LEAVES(WRITE_DOMAINS)) store_send_tree (
            .signal_i(store_commit_valid_o && store_commit_ready_i),.views_o(local_store_sends));
        rv32_frequency_control_tree #(.WIDTH(TAG_WIDTH+2),.LEAVES(WRITE_DOMAINS)) ack_tree (
            .signal_i({store_ack_valid_i,store_ack_error_i,store_ack_tag_i}),.views_o(local_acks));
        for(command_row=0;command_row<ROB_ENTRIES;command_row=command_row+1) begin:g_row
            localparam integer DOMAIN=(command_row*WRITE_DOMAINS)/ROB_ENTRIES;
            wire row_reset=local_modes[command_row*2];
            wire row_recovery=local_modes[command_row*2+1];
            wire normal=!row_reset && !row_recovery;
            wire [SLOT_WIDTH-1:0] row_head,row_commit_head,row_branch_age;
            assign {row_branch_age,row_commit_head,row_head}=
                local_indexes[DOMAIN*3*SLOT_WIDTH +: 3*SLOT_WIDTH];
            wire [SLOT_WIDTH-1:0] row_age=command_row-row_head;
            wire killed=!row_reset && row_recovery &&
                (STAGED_RECOVERY ? recovery_saved_kill[command_row] :
                 (valid_mem[command_row] && row_age>row_branch_age && row_age<occupancy_reg));
            wire allocate=normal && bank_alloc_fire[command_row%BE_WIDTH] &&
                bank_alloc_slot[command_row%BE_WIDTH]==command_row;
            wire [BE_WIDTH-1:0] completion_match,completion_grant,completion_errors,retire_match;
            wire [LOCAL_COMPLETION_DATA_WIDTH-1:0] completion_mux [1:2*LOCAL_COMPLETION_LEAVES-1];
            for(command_lane=0;command_lane<LOCAL_COMPLETION_LEAVES;command_lane=command_lane+1) begin:g_complete
                if(command_lane<BE_WIDTH) begin:g_present
                    wire c_valid,c_done,c_error;
                    wire [TAG_WIDTH-1:0] c_tag;
                    wire [LOCAL_COMPLETION_DATA_WIDTH-1:0] c_data;
                    wire [(LOCAL_COMPLETION_DATA_WIDTH+15)/16-1:0] c_select;
                    assign {c_valid,c_done,c_error,c_tag,c_data}=
                        local_completion_domains[(DOMAIN*BE_WIDTH+command_lane)*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH];
                    assign completion_match[command_lane]=!row_reset && c_valid && c_done &&
                        tag_matches(c_tag,command_row) && (!row_recovery || row_age<=row_branch_age);
                    if(command_lane==BE_WIDTH-1) begin:g_last
                        assign completion_grant[command_lane]=completion_match[command_lane];
                    end else begin:g_priority
                        assign completion_grant[command_lane]=completion_match[command_lane] &&
                            !(|completion_match[BE_WIDTH-1:command_lane+1]);
                    end
                    assign completion_errors[command_lane]=completion_match[command_lane] && c_error;
                    rv32_frequency_control_tree #(.LEAVES((LOCAL_COMPLETION_DATA_WIDTH+15)/16)) select_tree (
                        .signal_i(completion_grant[command_lane]),.views_o(c_select));
                    for(genvar completion_word=0;completion_word<(LOCAL_COMPLETION_DATA_WIDTH+15)/16;
                        completion_word=completion_word+1) begin:g_word
                        localparam integer LOW=completion_word*16;
                        localparam integer BITS=LOCAL_COMPLETION_DATA_WIDTH-LOW>=16?16:LOCAL_COMPLETION_DATA_WIDTH-LOW;
                        assign completion_mux[LOCAL_COMPLETION_LEAVES+command_lane][LOW +: BITS]=
                            {BITS{c_select[completion_word]}} & c_data[LOW +: BITS];
                    end
                    wire [31:0] commit_offset=row_commit_head+command_lane;
                    wire [31:0] commit_slot=(commit_offset>=ROB_ENTRIES)?commit_offset-ROB_ENTRIES:commit_offset;
                    assign retire_match[command_lane]=normal &&
                        local_commits[DOMAIN*BE_WIDTH+command_lane] && commit_slot==command_row;
                end else begin:g_padding
                    assign completion_mux[LOCAL_COMPLETION_LEAVES+command_lane]=0;
                end
            end
            for(command_node=1;command_node<LOCAL_COMPLETION_LEAVES;command_node=command_node+1) begin:g_or
                assign completion_mux[command_node]=completion_mux[2*command_node] | completion_mux[2*command_node+1];
            end
            wire completed=|completion_match;
            wire retire=|retire_match;
            wire ack_valid,ack_error;
            wire [TAG_WIDTH-1:0] ack_tag;
            assign {ack_valid,ack_error,ack_tag}=local_acks[DOMAIN*(TAG_WIDTH+2) +: TAG_WIDTH+2];
            wire acknowledged=normal && ack_valid && tag_matches(ack_tag,command_row);
            wire sent=normal && local_store_sends[DOMAIN] && row_commit_head==command_row;
            wire [GENERATION_WIDTH-1:0] next_generation_local=
                (generation_next_mem[command_row]==0) ? {{(GENERATION_WIDTH-1){1'b0}},1'b1} : generation_next_mem[command_row];
            wire [GENERATION_WIDTH-1:0] generation_after_allocate=
                (next_generation_local=={GENERATION_WIDTH{1'b1}}) ?
                {{(GENERATION_WIDTH-1){1'b0}},1'b1} : next_generation_local+1'b1;
            wire allocation_error;
            wire [ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH-1:0] raw_allocation=
                bank_alloc_packet[command_row%BE_WIDTH][CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
            wire [31:0] completed_value,completed_addr,completed_data;
            wire [3:0] completed_mask;
            wire completed_mmio;
            assign {completed_value,completed_addr,completed_data,completed_mask,completed_mmio}=completion_mux[1];
            assign allocation_error=raw_allocation[ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH-4];
            always @* begin:g_commands
                // Wide D inputs have no global mode mux. Only local WE and
                // bounded select leaves consume the qualified update controls.
                {store_mem_write_data[command_row],branch_mem_write_data[command_row],
                 halt_mem_write_data[command_row],error_mem_write_data[command_row],
                 pc_mem_write_data[command_row],inst_mem_write_data[command_row],
                 rd_mem_write_data[command_row],rd_we_mem_write_data[command_row],
                 old_phys_mem_write_data[command_row],new_phys_mem_write_data[command_row]}=raw_allocation;
                store_mem_write_enable[command_row]=allocate;
                branch_mem_write_enable[command_row]=allocate;
                halt_mem_write_enable[command_row]=allocate;
                pc_mem_write_enable[command_row]=allocate;
                inst_mem_write_enable[command_row]=allocate;
                rd_mem_write_enable[command_row]=allocate;
                rd_we_mem_write_enable[command_row]=allocate;
                old_phys_mem_write_enable[command_row]=allocate;
                new_phys_mem_write_enable[command_row]=allocate;
                valid_mem_write_enable[command_row]=row_reset || killed || retire || allocate;
                valid_mem_write_data[command_row]=allocate;
                ready_mem_write_enable[command_row]=row_reset || killed || completed || retire || allocate;
                ready_mem_write_data[command_row]=!row_reset && !allocate && !retire && completed;
                store_wait_mem_write_enable[command_row]=row_reset || killed || acknowledged || retire || allocate;
                store_wait_mem_write_data[command_row]=!row_reset && !allocate && !retire && acknowledged;
                store_sent_mem_write_enable[command_row]=row_reset || killed || sent || retire || allocate;
                store_sent_mem_write_data[command_row]=!row_reset && !allocate && !retire && sent;
                error_mem_write_enable[command_row]=row_reset || allocate ||
                    (|completion_errors) || (acknowledged && ack_error);
                error_mem_write_data[command_row]=row_reset ? 1'b0 : (allocate ? allocation_error : 1'b1);
                generation_mem_write_enable[command_row]=row_reset || allocate;
                generation_mem_write_data[command_row]=row_reset ? {{(GENERATION_WIDTH-1){1'b0}},1'b1} : next_generation_local;
                generation_next_mem_write_enable[command_row]=row_reset || allocate;
                generation_next_mem_write_data[command_row]=row_reset ? {{(GENERATION_WIDTH-1){1'b0}},1'b1} : generation_after_allocate;
                value_mem_write_enable[command_row]=completed;
                value_mem_write_data[command_row]=completed_value;
                store_addr_mem_write_enable[command_row]=completed;
                store_addr_mem_write_data[command_row]=completed_addr;
                store_data_mem_write_enable[command_row]=completed;
                store_data_mem_write_data[command_row]=completed_data;
                store_mask_mem_write_enable[command_row]=completed;
                store_mask_mem_write_data[command_row]=completed_mask;
                mmio_word_mem_write_enable[command_row]=(MMIO_PREDECODE!=0) && completed;
                mmio_word_mem_write_data[command_row]=completed_mmio;
                checkpoint_mem_write_enable[command_row]=(CHECKPOINT_IMPL==0) && allocate;
                checkpoint_mem_write_data[command_row]=bank_alloc_packet[command_row%BE_WIDTH][0 +: CHECKPOINT_WIDTH];
            end
        end
    end else begin:g_legacy_field_commands
    always @* begin : g_state_commands
        reg [GENERATION_WIDTH-1:0] bank_bank_next_generation;
        integer bank_branch_age;
        integer bank_complete_lane;
        reg [GENERATION_WIDTH-1:0] bank_next_generation;
        integer bank_reset_slot;
        integer bank_slot_index;
        integer bank_update_alloc_entry;
        integer bank_update_alloc_lane;
        integer bank_update_alloc_slot;
        integer bank_update_commit_lane;
        integer bank_update_commit_slot;
        reg [SLOT_WIDTH-1:0] bank_update_completion_age;
        reg [SLOT_WIDTH-1:0] bank_younger_age;
        integer bank_default_row;
        for(bank_default_row=0;bank_default_row<ROB_ENTRIES;bank_default_row=bank_default_row+1) begin
            valid_mem_write_data[bank_default_row]=0; valid_mem_write_enable[bank_default_row]=0;
            ready_mem_write_data[bank_default_row]=0; ready_mem_write_enable[bank_default_row]=0;
            store_mem_write_data[bank_default_row]=0; store_mem_write_enable[bank_default_row]=0;
            branch_mem_write_data[bank_default_row]=0; branch_mem_write_enable[bank_default_row]=0;
            halt_mem_write_data[bank_default_row]=0; halt_mem_write_enable[bank_default_row]=0;
            error_mem_write_data[bank_default_row]=0; error_mem_write_enable[bank_default_row]=0;
            store_wait_mem_write_data[bank_default_row]=0; store_wait_mem_write_enable[bank_default_row]=0;
            store_sent_mem_write_data[bank_default_row]=0; store_sent_mem_write_enable[bank_default_row]=0;
            generation_mem_write_data[bank_default_row]=0; generation_mem_write_enable[bank_default_row]=0;
            generation_next_mem_write_data[bank_default_row]=0; generation_next_mem_write_enable[bank_default_row]=0;
            pc_mem_write_data[bank_default_row]=0; pc_mem_write_enable[bank_default_row]=0;
            inst_mem_write_data[bank_default_row]=0; inst_mem_write_enable[bank_default_row]=0;
            rd_mem_write_data[bank_default_row]=0; rd_mem_write_enable[bank_default_row]=0;
            rd_we_mem_write_data[bank_default_row]=0; rd_we_mem_write_enable[bank_default_row]=0;
            old_phys_mem_write_data[bank_default_row]=0; old_phys_mem_write_enable[bank_default_row]=0;
            new_phys_mem_write_data[bank_default_row]=0; new_phys_mem_write_enable[bank_default_row]=0;
            value_mem_write_data[bank_default_row]=0; value_mem_write_enable[bank_default_row]=0;
            store_addr_mem_write_data[bank_default_row]=0; store_addr_mem_write_enable[bank_default_row]=0;
            mmio_word_mem_write_data[bank_default_row]=0; mmio_word_mem_write_enable[bank_default_row]=0;
            store_mask_mem_write_data[bank_default_row]=0; store_mask_mem_write_enable[bank_default_row]=0;
            store_data_mem_write_data[bank_default_row]=0; store_data_mem_write_enable[bank_default_row]=0;
            checkpoint_mem_write_data[bank_default_row]=0; checkpoint_mem_write_enable[bank_default_row]=0;
        end
        bank_bank_next_generation=0;
        bank_branch_age=0;
        bank_complete_lane=0;
        bank_next_generation=0;
        bank_reset_slot=0;
        bank_slot_index=0;
        bank_update_alloc_entry=0;
        bank_update_alloc_lane=0;
        bank_update_alloc_slot=0;
        bank_update_commit_lane=0;
        bank_update_commit_slot=0;
        bank_update_completion_age=0;
        bank_younger_age=0;

        if (reset_i) begin
            ;
            ;
            ;
            ;
            ;
            ;
            ;
            for (bank_reset_slot = 0; bank_reset_slot < ROB_ENTRIES; bank_reset_slot = bank_reset_slot + 1) begin
                begin valid_mem_write_data[bank_reset_slot] = 1'b0; valid_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin ready_mem_write_data[bank_reset_slot] = 1'b0; ready_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin store_wait_mem_write_data[bank_reset_slot] = 1'b0; store_wait_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin store_sent_mem_write_data[bank_reset_slot] = 1'b0; store_sent_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin error_mem_write_data[bank_reset_slot] = 1'b0; error_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin generation_mem_write_data[bank_reset_slot] = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1}; generation_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin generation_next_mem_write_data[bank_reset_slot] = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1}; generation_next_mem_write_enable[bank_reset_slot] = 1'b1; end
            end
        end else if (recovery_domains[5]) begin
            
            bank_branch_age = apply_age;
            for (bank_reset_slot = 0; bank_reset_slot < ROB_ENTRIES; bank_reset_slot = bank_reset_slot + 1) begin
                bank_younger_age = bank_reset_slot - head_update_index;
                if (STAGED_RECOVERY ? recovery_saved_kill[bank_reset_slot] :
                    (valid_mem[bank_reset_slot] && (bank_younger_age > bank_branch_age) && (bank_younger_age < occupancy_reg))) begin
                    begin valid_mem_write_data[bank_reset_slot] = 1'b0; valid_mem_write_enable[bank_reset_slot] = 1'b1; end
                    begin ready_mem_write_data[bank_reset_slot] = 1'b0; ready_mem_write_enable[bank_reset_slot] = 1'b1; end
                    begin store_wait_mem_write_data[bank_reset_slot] = 1'b0; store_wait_mem_write_enable[bank_reset_slot] = 1'b1; end
                    begin store_sent_mem_write_data[bank_reset_slot] = 1'b0; store_sent_mem_write_enable[bank_reset_slot] = 1'b1; end
                end
            end
            
            
            
            
            for (bank_complete_lane = 0; bank_complete_lane < BE_WIDTH; bank_complete_lane = bank_complete_lane + 1) begin
                if (completion_valid_i[bank_complete_lane] && completion_done_i[bank_complete_lane]) begin
                    for (bank_slot_index = 0; bank_slot_index < ROB_ENTRIES; bank_slot_index = bank_slot_index + 1) begin
                        bank_update_completion_age = bank_slot_index - head_update_index;
                        if ((bank_update_completion_age <= bank_branch_age) &&
                            tag_matches(completion_tag_i[(bank_complete_lane*TAG_WIDTH) +: TAG_WIDTH], bank_slot_index)) begin
                            begin ready_mem_write_data[bank_slot_index] = 1'b1; ready_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin value_mem_write_data[bank_slot_index] = completion_value_i[(bank_complete_lane*32) +: 32]; value_mem_write_enable[bank_slot_index] = 1'b1; end
                            if (completion_error_i[bank_complete_lane]) begin error_mem_write_data[bank_slot_index] = 1'b1; error_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin store_addr_mem_write_data[bank_slot_index] = completion_store_addr_i[(bank_complete_lane*32) +: 32]; store_addr_mem_write_enable[bank_slot_index] = 1'b1; end
                            if (MMIO_PREDECODE != 0)
                                begin mmio_word_mem_write_data[bank_slot_index] = (completion_store_addr_i[(bank_complete_lane*32) +: 32] == 32'h80000000) &&
                                    (completion_store_mask_i[(bank_complete_lane*4) +: 4] == 4'hf); mmio_word_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin store_mask_mem_write_data[bank_slot_index] = completion_store_mask_i[(bank_complete_lane*4) +: 4]; store_mask_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin store_data_mem_write_data[bank_slot_index] = completion_store_data_i[(bank_complete_lane*32) +: 32]; store_data_mem_write_enable[bank_slot_index] = 1'b1; end
                        end
                    end
                end
            end
            ;
            ;
            ;
        end else begin
            
            for (bank_complete_lane = 0; bank_complete_lane < BE_WIDTH; bank_complete_lane = bank_complete_lane + 1) begin
                if (completion_valid_i[bank_complete_lane] && completion_done_i[bank_complete_lane]) begin
                    for (bank_slot_index = 0; bank_slot_index < ROB_ENTRIES; bank_slot_index = bank_slot_index + 1) begin
                        if (tag_matches(completion_tag_i[(bank_complete_lane*TAG_WIDTH) +: TAG_WIDTH], bank_slot_index)) begin
                            begin ready_mem_write_data[bank_slot_index] = 1'b1; ready_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin value_mem_write_data[bank_slot_index] = completion_value_i[(bank_complete_lane*32) +: 32]; value_mem_write_enable[bank_slot_index] = 1'b1; end
                            if (completion_error_i[bank_complete_lane]) begin error_mem_write_data[bank_slot_index] = 1'b1; error_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin store_addr_mem_write_data[bank_slot_index] = completion_store_addr_i[(bank_complete_lane*32) +: 32]; store_addr_mem_write_enable[bank_slot_index] = 1'b1; end
                            if (MMIO_PREDECODE != 0)
                                begin mmio_word_mem_write_data[bank_slot_index] = (completion_store_addr_i[(bank_complete_lane*32) +: 32] == 32'h80000000) &&
                                    (completion_store_mask_i[(bank_complete_lane*4) +: 4] == 4'hf); mmio_word_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin store_mask_mem_write_data[bank_slot_index] = completion_store_mask_i[(bank_complete_lane*4) +: 4]; store_mask_mem_write_enable[bank_slot_index] = 1'b1; end
                            begin store_data_mem_write_data[bank_slot_index] = completion_store_data_i[(bank_complete_lane*32) +: 32]; store_data_mem_write_enable[bank_slot_index] = 1'b1; end
                        end
                    end
                end
            end
            for (bank_slot_index = 0; bank_slot_index < ROB_ENTRIES; bank_slot_index = bank_slot_index + 1) begin
                if (store_ack_valid_i && tag_matches(store_ack_tag_i, bank_slot_index)) begin
                    begin store_wait_mem_write_data[bank_slot_index] = 1'b1; store_wait_mem_write_enable[bank_slot_index] = 1'b1; end
                    if (store_ack_error_i) begin error_mem_write_data[bank_slot_index] = 1'b1; error_mem_write_enable[bank_slot_index] = 1'b1; end
                end
            end
            if (store_commit_valid_o && store_commit_ready_i) begin
                begin store_sent_mem_write_data[head_commit_index] = 1'b1; store_sent_mem_write_enable[head_commit_index] = 1'b1; end
            end
            
            for (bank_update_commit_lane = 0; bank_update_commit_lane < BE_WIDTH; bank_update_commit_lane = bank_update_commit_lane + 1) begin
                if (commit_valid_o[bank_update_commit_lane] && commit_ready_i) begin
                    bank_update_commit_slot = head_commit_index + bank_update_commit_lane;
                    if (bank_update_commit_slot >= ROB_ENTRIES)
                        bank_update_commit_slot = bank_update_commit_slot - ROB_ENTRIES;
                    if (head_store[bank_update_commit_lane] &&
                        head_mmio_word[bank_update_commit_lane]) begin
                        ;
                        ;
                    end else if (head_halt[bank_update_commit_lane]) begin
                        ;
                        ;
                    end
                    if (head_error[bank_update_commit_lane]) ;
                    begin valid_mem_write_data[bank_update_commit_slot] = 1'b0; valid_mem_write_enable[bank_update_commit_slot] = 1'b1; end
                    begin ready_mem_write_data[bank_update_commit_slot] = 1'b0; ready_mem_write_enable[bank_update_commit_slot] = 1'b1; end
                    begin store_wait_mem_write_data[bank_update_commit_slot] = 1'b0; store_wait_mem_write_enable[bank_update_commit_slot] = 1'b1; end
                    begin store_sent_mem_write_data[bank_update_commit_slot] = 1'b0; store_sent_mem_write_enable[bank_update_commit_slot] = 1'b1; end
                end
            end
            
            if ((ALLOC_BANKED_WRITE != 0) && (ROB_ENTRIES >= BE_WIDTH)) begin
                for (bank_update_alloc_entry = 0; bank_update_alloc_entry < ROB_ENTRIES;
                     bank_update_alloc_entry = bank_update_alloc_entry + 1) begin
                    if (bank_alloc_fire[bank_update_alloc_entry % BE_WIDTH] &&
                        bank_alloc_slot[bank_update_alloc_entry % BE_WIDTH] == bank_update_alloc_entry) begin
                        bank_bank_next_generation = generation_next_mem[bank_update_alloc_entry];
                        if (bank_bank_next_generation == {GENERATION_WIDTH{1'b0}})
                            bank_bank_next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                        begin generation_mem_write_data[bank_update_alloc_entry] = bank_bank_next_generation; generation_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        begin generation_next_mem_write_data[bank_update_alloc_entry] = (bank_bank_next_generation == {GENERATION_WIDTH{1'b1}}) ?
                            {{(GENERATION_WIDTH-1){1'b0}}, 1'b1} : bank_bank_next_generation + 1'b1; generation_next_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        begin valid_mem_write_data[bank_update_alloc_entry] = 1'b1; valid_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        begin ready_mem_write_data[bank_update_alloc_entry] = 1'b0; ready_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        begin store_wait_mem_write_data[bank_update_alloc_entry] = 1'b0; store_wait_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        begin store_sent_mem_write_data[bank_update_alloc_entry] = 1'b0; store_sent_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        begin {store_mem_write_data[bank_update_alloc_entry], branch_mem_write_data[bank_update_alloc_entry],
                         halt_mem_write_data[bank_update_alloc_entry], error_mem_write_data[bank_update_alloc_entry],
                         pc_mem_write_data[bank_update_alloc_entry], inst_mem_write_data[bank_update_alloc_entry],
                         rd_mem_write_data[bank_update_alloc_entry], rd_we_mem_write_data[bank_update_alloc_entry],
                         old_phys_mem_write_data[bank_update_alloc_entry], new_phys_mem_write_data[bank_update_alloc_entry]} = bank_alloc_packet[bank_update_alloc_entry % BE_WIDTH]
                                [CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH]; store_mem_write_enable[bank_update_alloc_entry] = 1'b1; branch_mem_write_enable[bank_update_alloc_entry] = 1'b1; halt_mem_write_enable[bank_update_alloc_entry] = 1'b1; error_mem_write_enable[bank_update_alloc_entry] = 1'b1; pc_mem_write_enable[bank_update_alloc_entry] = 1'b1; inst_mem_write_enable[bank_update_alloc_entry] = 1'b1; rd_mem_write_enable[bank_update_alloc_entry] = 1'b1; rd_we_mem_write_enable[bank_update_alloc_entry] = 1'b1; old_phys_mem_write_enable[bank_update_alloc_entry] = 1'b1; new_phys_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                        if (CHECKPOINT_IMPL == 0)
                            begin checkpoint_mem_write_data[bank_update_alloc_entry] = bank_alloc_packet[bank_update_alloc_entry % BE_WIDTH][0 +: CHECKPOINT_WIDTH]; checkpoint_mem_write_enable[bank_update_alloc_entry] = 1'b1; end
                    end
                end
            end else begin
            for (bank_update_alloc_lane = 0; bank_update_alloc_lane < BE_WIDTH; bank_update_alloc_lane = bank_update_alloc_lane + 1) begin
                if (alloc_fire_o[bank_update_alloc_lane]) begin
                    bank_update_alloc_slot = tail_reg + bank_update_alloc_lane;
                    if (bank_update_alloc_slot >= ROB_ENTRIES)
                        bank_update_alloc_slot = bank_update_alloc_slot - ROB_ENTRIES;
                    bank_next_generation = generation_next_mem[bank_update_alloc_slot];
                    if (bank_next_generation == {GENERATION_WIDTH{1'b0}})
                        bank_next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                    begin generation_mem_write_data[bank_update_alloc_slot] = bank_next_generation; generation_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin generation_next_mem_write_data[bank_update_alloc_slot] = (bank_next_generation == {GENERATION_WIDTH{1'b1}}) ? {{(GENERATION_WIDTH-1){1'b0}}, 1'b1} : bank_next_generation + 1'b1; generation_next_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin valid_mem_write_data[bank_update_alloc_slot] = 1'b1; valid_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin ready_mem_write_data[bank_update_alloc_slot] = 1'b0; ready_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin store_wait_mem_write_data[bank_update_alloc_slot] = 1'b0; store_wait_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin store_sent_mem_write_data[bank_update_alloc_slot] = 1'b0; store_sent_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin store_mem_write_data[bank_update_alloc_slot] = alloc_is_store_i[bank_update_alloc_lane]; store_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin branch_mem_write_data[bank_update_alloc_slot] = alloc_is_branch_i[bank_update_alloc_lane]; branch_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin halt_mem_write_data[bank_update_alloc_slot] = alloc_is_halt_i[bank_update_alloc_lane]; halt_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin error_mem_write_data[bank_update_alloc_slot] = alloc_is_error_i[bank_update_alloc_lane]; error_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin pc_mem_write_data[bank_update_alloc_slot] = alloc_pc_i[(bank_update_alloc_lane*32) +: 32]; pc_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin inst_mem_write_data[bank_update_alloc_slot] = alloc_inst_i[(bank_update_alloc_lane*32) +: 32]; inst_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin rd_mem_write_data[bank_update_alloc_slot] = alloc_rd_i[(bank_update_alloc_lane*5) +: 5]; rd_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin rd_we_mem_write_data[bank_update_alloc_slot] = alloc_rd_we_i[bank_update_alloc_lane]; rd_we_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin old_phys_mem_write_data[bank_update_alloc_slot] = alloc_old_phys_i[(bank_update_alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]; old_phys_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin new_phys_mem_write_data[bank_update_alloc_slot] = alloc_new_phys_i[(bank_update_alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]; new_phys_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    if (CHECKPOINT_IMPL == 0)
                        begin checkpoint_mem_write_data[bank_update_alloc_slot] = alloc_checkpoint_i[(bank_update_alloc_lane*CHECKPOINT_WIDTH) +: CHECKPOINT_WIDTH]; checkpoint_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                end
            end
            end
            ;
            ;
            ;
        end
    end
    end
    endgenerate

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
                ;
                ;
                ;
                ;
                ;
                ;
                ;
            end
        end else if (recovery_domains[5]) begin
            
            branch_age = apply_age;
            for (reset_slot = 0; reset_slot < ROB_ENTRIES; reset_slot = reset_slot + 1) begin
                younger_age = reset_slot - head_update_index;
                if (STAGED_RECOVERY ? recovery_saved_kill[reset_slot] :
                    (valid_mem[reset_slot] && (younger_age > branch_age) && (younger_age < occupancy_reg))) begin
                    ;
                    ;
                    ;
                    ;
                end
            end
            
            
            
            
            for (complete_lane = 0; complete_lane < BE_WIDTH; complete_lane = complete_lane + 1) begin
                if (completion_valid_i[complete_lane] && completion_done_i[complete_lane]) begin
                    for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin
                        update_completion_age = slot_index - head_update_index;
                        if ((update_completion_age <= branch_age) &&
                            tag_matches(completion_tag_i[(complete_lane*TAG_WIDTH) +: TAG_WIDTH], slot_index)) begin
                            ;
                            ;
                            if (completion_error_i[complete_lane]) ;
                            ;
                            if (MMIO_PREDECODE != 0)
                                ;
                            ;
                            ;
                        end
                    end
                end
            end
            tail_reg <= advance_slot(apply_slot, 1);
            occupancy_reg <= branch_age + 1;
            epoch_reg <= epoch_reg + 1'b1;
        end else begin
            
            for (complete_lane = 0; complete_lane < BE_WIDTH; complete_lane = complete_lane + 1) begin
                if (completion_valid_i[complete_lane] && completion_done_i[complete_lane]) begin
                    for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin
                        if (tag_matches(completion_tag_i[(complete_lane*TAG_WIDTH) +: TAG_WIDTH], slot_index)) begin
                            ;
                            ;
                            if (completion_error_i[complete_lane]) ;
                            ;
                            if (MMIO_PREDECODE != 0)
                                ;
                            ;
                            ;
                        end
                    end
                end
            end
            for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin
                if (store_ack_valid_i && tag_matches(store_ack_tag_i, slot_index)) begin
                    ;
                    if (store_ack_error_i) ;
                end
            end
            if (store_commit_valid_o && store_commit_ready_i) begin
                ;
            end
            
            for (update_commit_lane = 0; update_commit_lane < BE_WIDTH; update_commit_lane = update_commit_lane + 1) begin
                if (commit_valid_o[update_commit_lane] && commit_ready_i) begin
                    update_commit_slot = head_commit_index + update_commit_lane;
                    if (update_commit_slot >= ROB_ENTRIES)
                        update_commit_slot = update_commit_slot - ROB_ENTRIES;
                    if (head_store[update_commit_lane] &&
                        head_mmio_word[update_commit_lane]) begin
                        halted_o <= 1'b1;
                        return_value_o <= head_store_data[update_commit_lane];
                    end else if (head_halt[update_commit_lane]) begin
                        halted_o <= 1'b1;
                        return_value_o <= head_value[update_commit_lane];
                    end
                    if (head_error[update_commit_lane]) error_o <= 1'b1;
                    ;
                    ;
                    ;
                    ;
                end
            end
            
            if ((ALLOC_BANKED_WRITE != 0) && (ROB_ENTRIES >= BE_WIDTH)) begin
                for (update_alloc_entry = 0; update_alloc_entry < ROB_ENTRIES;
                     update_alloc_entry = update_alloc_entry + 1) begin
                    if (bank_alloc_fire[update_alloc_entry % BE_WIDTH] &&
                        bank_alloc_slot[update_alloc_entry % BE_WIDTH] == update_alloc_entry) begin
                        bank_next_generation = generation_next_mem[update_alloc_entry];
                        if (bank_next_generation == {GENERATION_WIDTH{1'b0}})
                            bank_next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                        ;
                        ;
                        ;
                        ;
                        ;
                        ;
                        ;
                        if (CHECKPOINT_IMPL == 0)
                            ;
                    end
                end
            end else begin
            for (update_alloc_lane = 0; update_alloc_lane < BE_WIDTH; update_alloc_lane = update_alloc_lane + 1) begin
                if (alloc_fire_o[update_alloc_lane]) begin
                    update_alloc_slot = tail_reg + update_alloc_lane;
                    if (update_alloc_slot >= ROB_ENTRIES)
                        update_alloc_slot = update_alloc_slot - ROB_ENTRIES;
                    next_generation = generation_next_mem[update_alloc_slot];
                    if (next_generation == {GENERATION_WIDTH{1'b0}})
                        next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    if (CHECKPOINT_IMPL == 0)
                        ;
                end
            end
            end
            head_reg <= head_next;
            tail_reg <= advance_slot(tail_reg, allocation_count);
            occupancy_reg <= occupancy_reg - (commit_ready_i ? pop_count : 0) + allocation_count;
        end
    end
    genvar storage_row;
    generate for(storage_row=0;storage_row<ROB_ENTRIES;storage_row=storage_row+1) begin:g_state_row
        rv32_rob_owned_field #(.WIDTH(1)) valid_mem_owner (
            .clk_i(clk_i),.write_i(valid_mem_write_enable[storage_row]),
            .data_i(valid_mem_write_data[storage_row]),.data_o(valid_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) ready_mem_owner (
            .clk_i(clk_i),.write_i(ready_mem_write_enable[storage_row]),
            .data_i(ready_mem_write_data[storage_row]),.data_o(ready_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) store_mem_owner (
            .clk_i(clk_i),.write_i(store_mem_write_enable[storage_row]),
            .data_i(store_mem_write_data[storage_row]),.data_o(store_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) branch_mem_owner (
            .clk_i(clk_i),.write_i(branch_mem_write_enable[storage_row]),
            .data_i(branch_mem_write_data[storage_row]),.data_o(branch_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) halt_mem_owner (
            .clk_i(clk_i),.write_i(halt_mem_write_enable[storage_row]),
            .data_i(halt_mem_write_data[storage_row]),.data_o(halt_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) error_mem_owner (
            .clk_i(clk_i),.write_i(error_mem_write_enable[storage_row]),
            .data_i(error_mem_write_data[storage_row]),.data_o(error_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) store_wait_mem_owner (
            .clk_i(clk_i),.write_i(store_wait_mem_write_enable[storage_row]),
            .data_i(store_wait_mem_write_data[storage_row]),.data_o(store_wait_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) store_sent_mem_owner (
            .clk_i(clk_i),.write_i(store_sent_mem_write_enable[storage_row]),
            .data_i(store_sent_mem_write_data[storage_row]),.data_o(store_sent_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(GENERATION_WIDTH-1+1)) generation_mem_owner (
            .clk_i(clk_i),.write_i(generation_mem_write_enable[storage_row]),
            .data_i(generation_mem_write_data[storage_row]),.data_o(generation_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(GENERATION_WIDTH-1+1)) generation_next_mem_owner (
            .clk_i(clk_i),.write_i(generation_next_mem_write_enable[storage_row]),
            .data_i(generation_next_mem_write_data[storage_row]),.data_o(generation_next_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(31+1)) pc_mem_owner (
            .clk_i(clk_i),.write_i(pc_mem_write_enable[storage_row]),
            .data_i(pc_mem_write_data[storage_row]),.data_o(pc_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(31+1)) inst_mem_owner (
            .clk_i(clk_i),.write_i(inst_mem_write_enable[storage_row]),
            .data_i(inst_mem_write_data[storage_row]),.data_o(inst_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(4+1)) rd_mem_owner (
            .clk_i(clk_i),.write_i(rd_mem_write_enable[storage_row]),
            .data_i(rd_mem_write_data[storage_row]),.data_o(rd_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) rd_we_mem_owner (
            .clk_i(clk_i),.write_i(rd_we_mem_write_enable[storage_row]),
            .data_i(rd_we_mem_write_data[storage_row]),.data_o(rd_we_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(PHYS_ADDR_WIDTH-1+1)) old_phys_mem_owner (
            .clk_i(clk_i),.write_i(old_phys_mem_write_enable[storage_row]),
            .data_i(old_phys_mem_write_data[storage_row]),.data_o(old_phys_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(PHYS_ADDR_WIDTH-1+1)) new_phys_mem_owner (
            .clk_i(clk_i),.write_i(new_phys_mem_write_enable[storage_row]),
            .data_i(new_phys_mem_write_data[storage_row]),.data_o(new_phys_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(31+1)) value_mem_owner (
            .clk_i(clk_i),.write_i(value_mem_write_enable[storage_row]),
            .data_i(value_mem_write_data[storage_row]),.data_o(value_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(31+1)) store_addr_mem_owner (
            .clk_i(clk_i),.write_i(store_addr_mem_write_enable[storage_row]),
            .data_i(store_addr_mem_write_data[storage_row]),.data_o(store_addr_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(1)) mmio_word_mem_owner (
            .clk_i(clk_i),.write_i(mmio_word_mem_write_enable[storage_row]),
            .data_i(mmio_word_mem_write_data[storage_row]),.data_o(mmio_word_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(3+1)) store_mask_mem_owner (
            .clk_i(clk_i),.write_i(store_mask_mem_write_enable[storage_row]),
            .data_i(store_mask_mem_write_data[storage_row]),.data_o(store_mask_mem[storage_row]));
        rv32_rob_owned_field #(.WIDTH(31+1)) store_data_mem_owner (
            .clk_i(clk_i),.write_i(store_data_mem_write_enable[storage_row]),
            .data_i(store_data_mem_write_data[storage_row]),.data_o(store_data_mem[storage_row]));
        if(CHECKPOINT_IMPL==0) begin:g_array_checkpoint
        rv32_rob_owned_field #(.WIDTH(CHECKPOINT_WIDTH-1+1)) checkpoint_mem_owner (
            .clk_i(clk_i),.write_i(checkpoint_mem_write_enable[storage_row]),
            .data_i(checkpoint_mem_write_data[storage_row]),.data_o(checkpoint_mem[storage_row]));
        end else begin:g_unused_array_checkpoint
            assign checkpoint_mem[storage_row]={CHECKPOINT_WIDTH{1'b0}};
        end
    end endgenerate

endmodule

// Owns actual architectural queue fields. The enable/hold mux is local,
// so a shared write decision drives one input rather than every data bit.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.
module rv32_rob_owned_field #(parameter integer WIDTH=32) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) payload_owner (
        .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
endmodule
