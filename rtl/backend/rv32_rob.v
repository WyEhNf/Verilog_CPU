`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Generation-qualified reorder buffer.  The interface deliberately keeps
// architectural commit separate from store visibility and branch recovery.
module rv32_rob #(
    parameter integer RELEASE_CREDITS = 0,
    parameter integer SINGLE_GENERATION_OWNER = 0,
    parameter integer COMPLETION_COMMIT_BYPASS = 0,
    parameter integer STORE_RETIRE_ADMISSION_BYPASS = 0,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES),
    parameter integer GENERATION_WIDTH = `RV32IM_ROB_GENERATION_WIDTH,
    parameter integer TAG_WIDTH = 1 + 2 + SLOT_WIDTH + GENERATION_WIDTH,
    parameter integer CHECKPOINT_WIDTH = 1024,
    parameter integer MMIO_PREDECODE = 0,
    // Enable only when commit PC/instruction and store payload outputs are
    // unconnected. Authority, error, terminal data and full tags stay intact.
    // MMIO_PREDECODE=0 retains address/mask storage for terminal detection.
    parameter integer LIGHT_RETIRE_PAYLOAD = 0,
    // Set to zero only when the caller cannot allocate a legacy HALT.
    // MMIO terminal data remains in store_data_mem in every mode.
    parameter integer LEGACY_HALT_PAYLOAD = 1,
    // In light mode the caller may omit this unconnected diagnostic value.
    // LSQ store payload and the MMIO side effect do not use this owner.
    parameter integer RETURN_VALUE_ENABLE = 1,
    parameter integer CHECKPOINT_IMPL = 0,
    // Caller guarantees distinct nonzero physical destinations for all live
    // rd-writing entries. Default preserves arbitrary duplicate-input handling.
    parameter integer RECLAIM_UNIQUE_DESTINATIONS = 0,
    // Preview captures a recovery transaction; apply is a later clock edge.
    // Default 0 preserves the standalone legacy interface behavior.
    parameter STAGED_RECOVERY = 0,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    // One read per physical modulo-BE bank, then rotate into strict commit order.
    // Pure combinational layout; original state, writes and fallback remain.
    parameter integer COMMIT_BANKED_READ = 0,
    // Select one complete allocation payload per modulo-BE bank, then decode
    // its destination row. Keeps all allocation and completion write priority.
    parameter integer ALLOC_BANKED_WRITE = 0,
    // Caller offers at most one already-allocated ordinary RAM store event.
    // Only light local-row command profiles can consume this extra event.
    parameter FAST_STORE_COMPLETE = 0,
    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,
    parameter FAST_STORE_BATCH = 0,
    // Publish at most one following ordinary store when every older lane
    // actually retires on this edge; its own retirement still uses saved sent.
    parameter integer STORE_PREFIX_ADMISSION = 0,
    parameter integer RECOVERY_ROW_LIVE_QUALIFY = 0,
    // Private caller guarantees every asserted recovery valid retains the
    // exact live ROB row until apply/reset. Generic callers keep mode zero.
    parameter integer RECOVERY_CALLER_OWNED = 0,
    // Private live-row ownership also certifies membership in the ROB window.
    // Only removes a repeated acceptance guard; real ages/kill data are kept.
    parameter integer RECOVERY_WINDOW_OWNED = 0,
    parameter integer OCCUPANCY_DISTRIBUTE = 0,
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
    output wire [((BE_WIDTH<=1)?1:$clog2(BE_WIDTH+1))-1:0] allocation_release_count_o,
    output wire                         alloc_ready_o,
    output reg  [BE_WIDTH-1:0]           alloc_fire_o,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_tag_o,
    output reg  [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] alloc_count_o,

    input  wire [BE_WIDTH-1:0]           fast_store_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] fast_store_tag_i,
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
    output wire [TAG_WIDTH-1:0]          store_commit_tag_o,
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
    wire unused_fast_store_valid_i_bits = &{1'b0, fast_store_valid_i};

    wire unused_fast_store_tag_i_bits = &{1'b0, fast_store_tag_i};

    wire unused_completion_value_i_bits = &{1'b0, completion_value_i};

    wire unused_completion_store_data_i_bits = &{1'b0, completion_store_data_i};

    wire unused_recovery_pc_i_bits = &{1'b0, recovery_pc_i};

    localparam integer COUNT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES + 1);
    localparam integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    localparam integer VALID_LSB = 0;

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
    // Invalid rows start at MAX only in the single-owner policy, so the first
    // allocation derives generation 1. Live generation comparisons stay direct.
    localparam [GENERATION_WIDTH-1:0] GENERATION_RESET =
        (SINGLE_GENERATION_OWNER!=0) ? {GENERATION_WIDTH{1'b1}} :
        {{(GENERATION_WIDTH-1){1'b0}},1'b1};
    initial if(SINGLE_GENERATION_OWNER!=0 && SINGLE_GENERATION_OWNER!=1)
        $fatal(1,"SINGLE_GENERATION_OWNER must be 0 or 1");
    wire [GENERATION_WIDTH-1:0] generation_mem [0:ROB_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_mem_write_data [0:ROB_ENTRIES-1];
    reg generation_mem_write_enable [0:ROB_ENTRIES-1];
    wire [GENERATION_WIDTH-1:0] generation_next_mem [0:ROB_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_next_mem_write_data [0:ROB_ENTRIES-1];
    reg generation_next_mem_write_enable [0:ROB_ENTRIES-1];
    wire [31:0] pc_mem [0:ROB_ENTRIES-1];
    for (genvar unused_pc_mem_row=0; unused_pc_mem_row<=ROB_ENTRIES-1; unused_pc_mem_row=unused_pc_mem_row+1) begin : g_unused_pc_mem
        wire unused_pc_mem_bits = &{1'b0, pc_mem[unused_pc_mem_row]};
    end

    reg [31:0] pc_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_pc_mem_write_data_row=0; unused_pc_mem_write_data_row<=ROB_ENTRIES-1; unused_pc_mem_write_data_row=unused_pc_mem_write_data_row+1) begin : g_unused_pc_mem_write_data
        wire unused_pc_mem_write_data_bits = &{1'b0, pc_mem_write_data[unused_pc_mem_write_data_row]};
    end

    reg pc_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_pc_mem_write_enable_row=0; unused_pc_mem_write_enable_row<=ROB_ENTRIES-1; unused_pc_mem_write_enable_row=unused_pc_mem_write_enable_row+1) begin : g_unused_pc_mem_write_enable
        wire unused_pc_mem_write_enable_bits = &{1'b0, pc_mem_write_enable[unused_pc_mem_write_enable_row]};
    end

    wire [31:0] inst_mem [0:ROB_ENTRIES-1];
    for (genvar unused_inst_mem_row=0; unused_inst_mem_row<=ROB_ENTRIES-1; unused_inst_mem_row=unused_inst_mem_row+1) begin : g_unused_inst_mem
        wire unused_inst_mem_bits = &{1'b0, inst_mem[unused_inst_mem_row]};
    end

    reg [31:0] inst_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_inst_mem_write_data_row=0; unused_inst_mem_write_data_row<=ROB_ENTRIES-1; unused_inst_mem_write_data_row=unused_inst_mem_write_data_row+1) begin : g_unused_inst_mem_write_data
        wire unused_inst_mem_write_data_bits = &{1'b0, inst_mem_write_data[unused_inst_mem_write_data_row]};
    end

    reg inst_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_inst_mem_write_enable_row=0; unused_inst_mem_write_enable_row<=ROB_ENTRIES-1; unused_inst_mem_write_enable_row=unused_inst_mem_write_enable_row+1) begin : g_unused_inst_mem_write_enable
        wire unused_inst_mem_write_enable_bits = &{1'b0, inst_mem_write_enable[unused_inst_mem_write_enable_row]};
    end

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
    for (genvar unused_value_mem_row=0; unused_value_mem_row<=ROB_ENTRIES-1; unused_value_mem_row=unused_value_mem_row+1) begin : g_unused_value_mem
        wire unused_value_mem_bits = &{1'b0, value_mem[unused_value_mem_row]};
    end

    reg [31:0] value_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_value_mem_write_data_row=0; unused_value_mem_write_data_row<=ROB_ENTRIES-1; unused_value_mem_write_data_row=unused_value_mem_write_data_row+1) begin : g_unused_value_mem_write_data
        wire unused_value_mem_write_data_bits = &{1'b0, value_mem_write_data[unused_value_mem_write_data_row]};
    end

    reg value_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_value_mem_write_enable_row=0; unused_value_mem_write_enable_row<=ROB_ENTRIES-1; unused_value_mem_write_enable_row=unused_value_mem_write_enable_row+1) begin : g_unused_value_mem_write_enable
        wire unused_value_mem_write_enable_bits = &{1'b0, value_mem_write_enable[unused_value_mem_write_enable_row]};
    end

    wire [31:0] store_addr_mem [0:ROB_ENTRIES-1];
    for (genvar unused_store_addr_mem_row=0; unused_store_addr_mem_row<=ROB_ENTRIES-1; unused_store_addr_mem_row=unused_store_addr_mem_row+1) begin : g_unused_store_addr_mem
        wire unused_store_addr_mem_bits = &{1'b0, store_addr_mem[unused_store_addr_mem_row]};
    end

    reg [31:0] store_addr_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_store_addr_mem_write_data_row=0; unused_store_addr_mem_write_data_row<=ROB_ENTRIES-1; unused_store_addr_mem_write_data_row=unused_store_addr_mem_write_data_row+1) begin : g_unused_store_addr_mem_write_data
        wire unused_store_addr_mem_write_data_bits = &{1'b0, store_addr_mem_write_data[unused_store_addr_mem_write_data_row]};
    end

    reg store_addr_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_store_addr_mem_write_enable_row=0; unused_store_addr_mem_write_enable_row<=ROB_ENTRIES-1; unused_store_addr_mem_write_enable_row=unused_store_addr_mem_write_enable_row+1) begin : g_unused_store_addr_mem_write_enable
        wire unused_store_addr_mem_write_enable_bits = &{1'b0, store_addr_mem_write_enable[unused_store_addr_mem_write_enable_row]};
    end

    // Updated with exactly the same completion enable/priority as address and
    // mask. Payload remains observable; only retirement classification moves.
    wire mmio_word_mem [0:ROB_ENTRIES-1];
    reg mmio_word_mem_write_data [0:ROB_ENTRIES-1];
    reg mmio_word_mem_write_enable [0:ROB_ENTRIES-1];
    // Store payloads stay access-relative in the ROB.  Expand to the
    // cache-line representation only on the external commit interface.
    wire [3:0] store_mask_mem [0:ROB_ENTRIES-1];
    for (genvar unused_store_mask_mem_row=0; unused_store_mask_mem_row<=ROB_ENTRIES-1; unused_store_mask_mem_row=unused_store_mask_mem_row+1) begin : g_unused_store_mask_mem
        wire unused_store_mask_mem_bits = &{1'b0, store_mask_mem[unused_store_mask_mem_row]};
    end

    reg [3:0] store_mask_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_store_mask_mem_write_data_row=0; unused_store_mask_mem_write_data_row<=ROB_ENTRIES-1; unused_store_mask_mem_write_data_row=unused_store_mask_mem_write_data_row+1) begin : g_unused_store_mask_mem_write_data
        wire unused_store_mask_mem_write_data_bits = &{1'b0, store_mask_mem_write_data[unused_store_mask_mem_write_data_row]};
    end

    reg store_mask_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_store_mask_mem_write_enable_row=0; unused_store_mask_mem_write_enable_row<=ROB_ENTRIES-1; unused_store_mask_mem_write_enable_row=unused_store_mask_mem_write_enable_row+1) begin : g_unused_store_mask_mem_write_enable
        wire unused_store_mask_mem_write_enable_bits = &{1'b0, store_mask_mem_write_enable[unused_store_mask_mem_write_enable_row]};
    end

    wire [31:0] store_data_mem [0:ROB_ENTRIES-1];
    for (genvar unused_store_data_mem_row=0; unused_store_data_mem_row<=ROB_ENTRIES-1; unused_store_data_mem_row=unused_store_data_mem_row+1) begin : g_unused_store_data_mem
        wire unused_store_data_mem_bits = &{1'b0, store_data_mem[unused_store_data_mem_row]};
    end

    reg [31:0] store_data_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_store_data_mem_write_data_row=0; unused_store_data_mem_write_data_row<=ROB_ENTRIES-1; unused_store_data_mem_write_data_row=unused_store_data_mem_write_data_row+1) begin : g_unused_store_data_mem_write_data
        wire unused_store_data_mem_write_data_bits = &{1'b0, store_data_mem_write_data[unused_store_data_mem_write_data_row]};
    end

    reg store_data_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_store_data_mem_write_enable_row=0; unused_store_data_mem_write_enable_row<=ROB_ENTRIES-1; unused_store_data_mem_write_enable_row=unused_store_data_mem_write_enable_row+1) begin : g_unused_store_data_mem_write_enable
        wire unused_store_data_mem_write_enable_bits = &{1'b0, store_data_mem_write_enable[unused_store_data_mem_write_enable_row]};
    end

    wire [CHECKPOINT_WIDTH-1:0] checkpoint_mem [0:ROB_ENTRIES-1];
    for (genvar unused_checkpoint_mem_row=0; unused_checkpoint_mem_row<=ROB_ENTRIES-1; unused_checkpoint_mem_row=unused_checkpoint_mem_row+1) begin : g_unused_checkpoint_mem
        wire unused_checkpoint_mem_bits = &{1'b0, checkpoint_mem[unused_checkpoint_mem_row]};
    end

    reg [CHECKPOINT_WIDTH-1:0] checkpoint_mem_write_data [0:ROB_ENTRIES-1];
    for (genvar unused_checkpoint_mem_write_data_row=0; unused_checkpoint_mem_write_data_row<=ROB_ENTRIES-1; unused_checkpoint_mem_write_data_row=unused_checkpoint_mem_write_data_row+1) begin : g_unused_checkpoint_mem_write_data
        wire unused_checkpoint_mem_write_data_bits = &{1'b0, checkpoint_mem_write_data[unused_checkpoint_mem_write_data_row]};
    end

    reg checkpoint_mem_write_enable [0:ROB_ENTRIES-1];
    for (genvar unused_checkpoint_mem_write_enable_row=0; unused_checkpoint_mem_write_enable_row<=ROB_ENTRIES-1; unused_checkpoint_mem_write_enable_row=unused_checkpoint_mem_write_enable_row+1) begin : g_unused_checkpoint_mem_write_enable
        wire unused_checkpoint_mem_write_enable_bits = &{1'b0, checkpoint_mem_write_enable[unused_checkpoint_mem_write_enable_row]};
    end

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
    // The count remains this one original state owner. Isolate its row
    // recovery comparators and three separate public/query/lane consumers.
    localparam integer OCCUPANCY_ROW_DOMAINS=(ROB_ENTRIES+3)/4;
    localparam integer OCCUPANCY_DOMAINS=OCCUPANCY_ROW_DOMAINS+3;
    wire [OCCUPANCY_DOMAINS*COUNT_WIDTH-1:0] occupancy_views;
    generate if(OCCUPANCY_DISTRIBUTE!=0) begin:g_occupancy_domains
        rv32_frequency_control_tree #(.WIDTH(COUNT_WIDTH),.LEAVES(OCCUPANCY_DOMAINS)) tree (
            .signal_i(occupancy_reg),.views_o(occupancy_views));
    end else begin:g_occupancy_direct
        assign occupancy_views={OCCUPANCY_DOMAINS{occupancy_reg}};
    end endgenerate
    reg [3:0] epoch_reg;
    integer alloc_lane;

    integer commit_lane;
    integer recovery_lane;

    reg [SLOT_WIDTH-1:0] age;
    integer chosen_age;
    integer chosen_slot;
    wire [31:0] branch_age = 32'(apply_age);
    integer pop_count;
    integer allocation_count;
    integer free_entries;
    integer alloc_slot;
    integer commit_slot;

    integer recovery_slot;

    // Procedural scratch belongs to one process. Sharing these integers with
    // the combinational allocation/commit decoder creates multiple RTL drivers
    // when the complete ROB is synthesized as an observable component.
    integer update_alloc_lane;
    integer update_alloc_slot;
    integer update_commit_lane;

    integer update_alloc_entry;

    reg recovery_found;
    reg recovery_saved_valid;
    wire [SLOT_WIDTH-1:0] recovery_saved_slot, recovery_saved_age;
    wire [ROB_ENTRIES-1:0] recovery_saved_kill;
    wire [ROB_ENTRIES-1:0] recovery_preview_kill;
    wire [SLOT_WIDTH-1:0] apply_slot = SLOT_WIDTH'((STAGED_RECOVERY != 0) ? 32'(recovery_saved_slot) : chosen_slot);
    wire [SLOT_WIDTH-1:0] apply_age = SLOT_WIDTH'((STAGED_RECOVERY != 0) ? 32'(recovery_saved_age) : chosen_age);
    wire recovery_apply = (STAGED_RECOVERY != 0) ?
        (recovery_apply_i && recovery_saved_valid) : recovery_found;
    wire recovery_hold = (STAGED_RECOVERY != 0) && recovery_hold_i;
    wire [5:0] recovery_domains;
    wire unused_recovery_domains_bits = &{1'b0, recovery_domains};

    wire [2:0] recovery_preview_domains;
    rv32_frequency_control_tree #(.LEAVES(6)) recovery_tree (
        .signal_i(recovery_apply),.views_o(recovery_domains));
    rv32_frequency_control_tree #(.LEAVES(3)) recovery_preview_tree (
        .signal_i(recovery_found),.views_o(recovery_preview_domains));
    assign recovery_preview_valid_o=recovery_preview_domains[0];
    assign recovery_accept_o=recovery_domains[0];
    assign redirect_valid_o=(STAGED_RECOVERY != 0) ? recovery_preview_domains[1] : recovery_domains[1];
    assign checkpoint_restore_valid_o=recovery_domains[2];
    // chosen_age is either a slot distance or ROB_ENTRIES+1 (no match).
    // COUNT_WIDTH retains that sentinel; SLOT_WIDTH alone would truncate it.
    localparam integer RECOVERY_QUERY_WIDTH=SLOT_WIDTH+2*COUNT_WIDTH+1;
    localparam integer RECOVERY_QUERY_DOMAINS=(ROB_ENTRIES+3)/4;
    wire [RECOVERY_QUERY_DOMAINS*RECOVERY_QUERY_WIDTH-1:0] recovery_query_views;
    wire [ROB_ENTRIES-1:0] recovery_row_preview;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_QUERY_WIDTH),.LEAVES(RECOVERY_QUERY_DOMAINS)) recovery_query_tree (
        .signal_i({recovery_preview_domains[2],head_recovery_index,COUNT_WIDTH'(chosen_age),occupancy_views[(OCCUPANCY_ROW_DOMAINS+2)*COUNT_WIDTH +: COUNT_WIDTH]}),
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
            COUNT_WIDTH'(relative_age)>local_branch_age && COUNT_WIDTH'(relative_age)<local_occupancy;
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

    initial begin
        if((RECOVERY_WINDOW_OWNED!=0 && RECOVERY_WINDOW_OWNED!=1) ||
            (RECOVERY_WINDOW_OWNED!=0 && RECOVERY_CALLER_OWNED==0))
            $fatal(1,"ROB window ownership requires private live-row ownership");
        if(RECOVERY_CALLER_OWNED!=0 && RECOVERY_CALLER_OWNED!=1)
            $fatal(1,"ROB recovery caller ownership must be 0 or 1");
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
    // Match the enabled field owners instead of routing constant trace words.
    localparam integer COMMIT_READ_WIDTH = 8 + GENERATION_WIDTH + 5 +
        2*PHYS_ADDR_WIDTH + ((LIGHT_RETIRE_PAYLOAD==0) ? 5*32+4 :
        (((MMIO_PREDECODE==0) ? 32+4 : 0) + ((RETURN_VALUE_ENABLE!=0)?32:0) +
         ((LEGACY_HALT_PAYLOAD!=0)?32:0)));
    wire [ROB_ENTRIES-1:0] head_row_select;
    localparam integer READ_GROUPS = 4;
    localparam integer READ_GROUP_WIDTH = (COMMIT_READ_WIDTH + READ_GROUPS - 1) / READ_GROUPS;
    wire [ROB_ENTRIES*BE_WIDTH*READ_GROUPS-1:0] head_read_select;
    wire unused_head_read_select_bits = &{1'b0, head_read_select};

    wire [ROB_ENTRIES-1:0] next_head_row_select;
    wire unused_next_head_row_select_bits = &{1'b0, next_head_row_select};

    function automatic [COMMIT_READ_WIDTH-1:0] read_mask;
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
        wire [31:0] raw_slot = 32'(head_commit_index) + mmio_lane;
        wire [31:0] selected_slot = (raw_slot >= ROB_ENTRIES) ? raw_slot - ROB_ENTRIES : raw_slot;
        wire unused_selected_slot_bits = &{1'b0, selected_slot};

        assign head_mmio_word[mmio_lane] = (MMIO_PREDECODE != 0) ?
            mmio_word_mem[selected_slot] :
            ((head_store_addr[mmio_lane] == 32'h80000000) &&
             (head_store_mask[mmio_lane] == 4'hf));
    end endgenerate

    wire [COMMIT_READ_WIDTH-1:0] commit_row_packet [0:ROB_ENTRIES-1];
    generate for(genvar packet_row=0;packet_row<ROB_ENTRIES;packet_row=packet_row+1) begin:g_commit_packet
        if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full
            assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], pc_mem[packet_row], inst_mem[packet_row], value_mem[packet_row], store_addr_mem[packet_row], store_mask_mem[packet_row], store_data_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
        end else begin:g_light
            if(MMIO_PREDECODE==0) begin:g_mmio_0
                if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], value_mem[packet_row], store_addr_mem[packet_row], store_mask_mem[packet_row], store_data_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                    else begin:g_return_0
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], value_mem[packet_row], store_addr_mem[packet_row], store_mask_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                end
                else begin:g_halt_0
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], store_addr_mem[packet_row], store_mask_mem[packet_row], store_data_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                    else begin:g_return_0
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], store_addr_mem[packet_row], store_mask_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                end
            end
            else begin:g_mmio_1
                if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], value_mem[packet_row], store_data_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                    else begin:g_return_0
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], value_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                end
                else begin:g_halt_0
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], store_data_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                    else begin:g_return_0
                        assign commit_row_packet[packet_row]={valid_mem[packet_row], ready_mem[packet_row], store_mem[packet_row], halt_mem[packet_row], error_mem[packet_row], store_wait_mem[packet_row], store_sent_mem[packet_row], generation_mem[packet_row], rd_we_mem[packet_row], rd_mem[packet_row], old_phys_mem[packet_row], new_phys_mem[packet_row]};
                    end
                end
            end
        end
    end endgenerate

    wire [COMMIT_READ_WIDTH-1:0] bank_packet [0:BE_WIDTH-1];
    localparam integer BANK_ROWS = (ROB_ENTRIES >= BE_WIDTH) ? ROB_ENTRIES / BE_WIDTH : 1;
    genvar commit_bank, bank_row, bank_offset;
    generate
        if (COMMIT_BANKED_READ != 0 && ROB_ENTRIES >= BE_WIDTH &&
            ROB_CONTROL_REGISTER_BANKS == 0 && ASAP7_FANOUT_BUFFERS == 0) begin : g_banked_commit
            for (commit_bank = 0; commit_bank < BE_WIDTH; commit_bank = commit_bank + 1) begin : g_bank
                wire [BANK_ROWS-1:0] row_select;
                wire [BANK_ROWS*COMMIT_READ_WIDTH-1:0] row_packets;
                for (bank_row = 0; bank_row < BANK_ROWS; bank_row = bank_row + 1) begin : g_row
                    wire [BE_WIDTH-1:0] possible_heads;
                    // Preserve the original four-consecutive-heads query,
                    // including the exact modulo indexing for every bank.
                    for (bank_offset = 0; bank_offset < BE_WIDTH; bank_offset = bank_offset + 1) begin : g_head
                        assign possible_heads[bank_offset] = head_row_select[
                            (bank_row*BE_WIDTH+commit_bank+ROB_ENTRIES-bank_offset)%ROB_ENTRIES];
                    end
                    assign row_select[bank_row] = |possible_heads;
                    assign row_packets[bank_row*COMMIT_READ_WIDTH +: COMMIT_READ_WIDTH]=
                        commit_row_packet[bank_row*BE_WIDTH+commit_bank];
                end
                // PRIORITY=0 is the same bitwise OR of masked row packets
                // as the old loop, even for multiple asserted row_select bits.
                // Its existing control trees bound each final data group.
                wire  unused_packet_selector_write_o;
                rv32_frequency_event_select #(.WIDTH(COMMIT_READ_WIDTH),.EVENTS(BANK_ROWS),.PRIORITY(0)) packet_selector (
                    .events_i(row_select),.values_i(row_packets),.write_o(unused_packet_selector_write_o),
                    .value_o(bank_packet[commit_bank]));
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
                assign head_packet[read_lane] = bank_packet[(32'(head_read_index)+read_lane)%BE_WIDTH];
            end else if (ROB_ENTRIES >= BE_WIDTH) begin : g_parallel
                reg [COMMIT_READ_WIDTH-1:0] packet;
                integer row;
                always @* begin
                    packet = {COMMIT_READ_WIDTH{1'b0}};
                    for (row = 0; row < ROB_ENTRIES; row = row + 1) begin
                        packet = packet | (read_mask(head_read_select[
                            (((row+ROB_ENTRIES-read_lane)%ROB_ENTRIES)*BE_WIDTH+read_lane)*READ_GROUPS +: READ_GROUPS]) &
                            commit_row_packet[row]);
                    end
                end
                assign head_packet[read_lane] = packet;
            end else begin : g_narrow_depth
                // Preserve the original single-wrap indexing semantics for
                // the exceptional configuration with more lanes than rows.
                wire [31:0] offset = head_read_index + read_lane;
                wire [31:0] row_index = (offset >= ROB_ENTRIES) ? offset-ROB_ENTRIES : offset;
                assign head_packet[read_lane] = commit_row_packet[row_index];
            end
            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_packet
                assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_pc[read_lane], head_inst[read_lane], head_value[read_lane], head_store_addr[read_lane], head_store_mask[read_lane], head_store_data[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
            end else begin:g_light_packet
                assign head_pc[read_lane]=32'b0;
                assign head_inst[read_lane]=32'b0;
                if(MMIO_PREDECODE==0) begin:g_mmio_0
                    if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                        if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_value[read_lane], head_store_addr[read_lane], head_store_mask[read_lane], head_store_data[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                        else begin:g_return_0
                            assign head_store_data[read_lane]=32'b0;
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_value[read_lane], head_store_addr[read_lane], head_store_mask[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                    end
                    else begin:g_halt_0
                        assign head_value[read_lane]=32'b0;
                        if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_store_addr[read_lane], head_store_mask[read_lane], head_store_data[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                        else begin:g_return_0
                            assign head_store_data[read_lane]=32'b0;
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_store_addr[read_lane], head_store_mask[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                    end
                end
                else begin:g_mmio_1
                    assign head_store_addr[read_lane]=32'b0;
                    assign head_store_mask[read_lane]=4'b0;
                    if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                        if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_value[read_lane], head_store_data[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                        else begin:g_return_0
                            assign head_store_data[read_lane]=32'b0;
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_value[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                    end
                    else begin:g_halt_0
                        assign head_value[read_lane]=32'b0;
                        if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_store_data[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                        else begin:g_return_0
                            assign head_store_data[read_lane]=32'b0;
                            assign {head_valid[read_lane], head_ready[read_lane], head_store[read_lane], head_halt[read_lane], head_error[read_lane], head_store_wait[read_lane], head_store_sent[read_lane], head_generation[read_lane], head_rd_we[read_lane], head_rd[read_lane], head_old_phys[read_lane], head_new_phys[read_lane]}=head_packet[read_lane];
                        end
                    end
                end
            end
        end
    endgenerate

    localparam integer ALLOC_PACKET_WIDTH = 4 + 32 + 32 + 5 + 1 +
                                             2*PHYS_ADDR_WIDTH + CHECKPOINT_WIDTH;
    wire [BE_WIDTH-1:0] bank_alloc_fire;
    wire [SLOT_WIDTH-1:0] bank_alloc_slot [0:BE_WIDTH-1];
    wire [ALLOC_PACKET_WIDTH-1:0] bank_alloc_packet [0:BE_WIDTH-1];

    genvar alloc_bank,alloc_source,alloc_word,alloc_node;
    localparam integer ALLOC_DATA_WIDTH=ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH+
        ((CHECKPOINT_IMPL==0)?CHECKPOINT_WIDTH:0)-((LIGHT_RETIRE_PAYLOAD!=0)?64:0);
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
                            ((LIGHT_RETIRE_PAYLOAD==0)?alloc_pc_i[alloc_source*32 +: 32]:32'b0),
                            ((LIGHT_RETIRE_PAYLOAD==0)?alloc_inst_i[alloc_source*32 +: 32]:32'b0),
                            alloc_rd_i[alloc_source*5 +: 5],alloc_rd_we_i[alloc_source],
                            alloc_old_phys_i[alloc_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                            alloc_new_phys_i[alloc_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                            alloc_checkpoint_i[alloc_source*CHECKPOINT_WIDTH +: CHECKPOINT_WIDTH]};
    wire unused_full_payload_bits = &{1'b0, full_payload};

                        wire [ALLOC_DATA_WIDTH-1:0] active_payload;
                        wire [ALLOC_DATA_WORDS-1:0] selected_words;
                        if(LIGHT_RETIRE_PAYLOAD!=0) begin:g_light_payload
                            if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                                assign active_payload={full_payload[ALLOC_PACKET_WIDTH-1 -: 4],
                                    full_payload[0 +: CHECKPOINT_WIDTH+6+2*PHYS_ADDR_WIDTH]};
                            end else begin:g_without_checkpoint
                                assign active_payload={full_payload[ALLOC_PACKET_WIDTH-1 -: 4],
                                    full_payload[CHECKPOINT_WIDTH +: 6+2*PHYS_ADDR_WIDTH]};
                            end
                        end else if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                            assign active_payload=full_payload;
                        end else begin:g_without_checkpoint
                            assign active_payload=full_payload[CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
                        end
                        assign row_match_mask[alloc_source]=alloc_fire_o[alloc_source] &&
                            ((32'(tail_reg)+alloc_source)%BE_WIDTH)==alloc_bank;
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
                if(LIGHT_RETIRE_PAYLOAD!=0) begin:g_light_result
                    // Reinsert constant trace slots at the original offsets. All
                    // allocation writes and priority still see the same full packet.
                    if(CHECKPOINT_IMPL==0) begin:g_full_result
                        assign bank_alloc_packet[alloc_bank]={packets[1][ALLOC_DATA_WIDTH-1 -: 4],
                            64'b0,packets[1][0 +: ALLOC_DATA_WIDTH-4]};
                    end else begin:g_compact_result
                        assign bank_alloc_packet[alloc_bank]={packets[1][ALLOC_DATA_WIDTH-1 -: 4],
                            64'b0,packets[1][0 +: ALLOC_DATA_WIDTH-4],{CHECKPOINT_WIDTH{1'b0}}};
                    end
                end else if(CHECKPOINT_IMPL==0) begin:g_full_result
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

    function automatic [SLOT_WIDTH-1:0] advance_slot;
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
                advance_slot = SLOT_WIDTH'(32'(start) + amount);
        end
    endfunction

    // Recovery holds the architectural head exactly as in the legacy ROB.
    // All real replicated state uses this same transition, including stalls.
    assign head_next = (recovery_domains[3] || recovery_hold) ? head_reg :
        advance_slot(head_update_index, (commit_ready_i ? pop_count : 0));

    function automatic [TAG_WIDTH-1:0] make_tag;
        input integer slot;
        input [GENERATION_WIDTH-1:0] generation;
        reg unused_slot;
        begin
            unused_slot = &{1'b0, slot};
            make_tag = {generation, slot[SLOT_WIDTH-1:0], 2'b00, 1'b1};
        end
    endfunction

    function automatic [15:0] line_mask_from_relative;
        input [3:0] relative_mask;
        input [31:0] address;
        reg unused_address;
        begin
            unused_address = &{1'b0, address};
            line_mask_from_relative = {12'b0, relative_mask} << address[3:0];
        end
    endfunction

    function automatic [127:0] line_data_from_relative;
        input [31:0] relative_data;
        input [31:0] address;
        reg unused_address;
        begin
            unused_address = &{1'b0, address};
            line_data_from_relative = {96'b0, relative_data} << (address[3:0] * 8);
        end
    endfunction

    function automatic tag_matches;
        input [TAG_WIDTH-1:0] tag;
        input integer slot;
        reg unused_slot;
        begin
            unused_slot = &{1'b0, slot};
            tag_matches = tag[VALID_LSB] && valid_mem[slot] &&
                (tag[SLOT_LSB +: SLOT_WIDTH] == slot[SLOT_WIDTH-1:0]) &&
                (tag[GEN_LSB +: GENERATION_WIDTH] == generation_mem[slot]);
        end
    endfunction

    assign head_o = head_views[4*SLOT_WIDTH +: SLOT_WIDTH];
    assign tail_o = tail_reg;
    assign occupancy_o = occupancy_views[(OCCUPANCY_ROW_DOMAINS+1)*COUNT_WIDTH +: COUNT_WIDTH];
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

    wire [RECLAIM_COUNT_WIDTH-1:0] reclaim_count_tree [1:2*RECLAIM_LEAVES-1];
    genvar reclaim_entry, reclaim_phys, reclaim_match, reclaim_node;
    generate
        for (reclaim_entry = 0; reclaim_entry < ROB_ENTRIES; reclaim_entry = reclaim_entry + 1) begin : g_reclaim_age
            // Share the exact per-row interval predicate with the saved mask.
            assign reclaim_eligible[reclaim_entry]=recovery_row_preview[reclaim_entry] &&
                rd_we_mem[reclaim_entry] && recovery_preview_kill[reclaim_entry];
        end
`ifdef CPU2026_WORD_SIM
        // Native word view of the exact destination set. The default geometry
        // avoids the ROB x physical-register match matrix; other configurations
        // retain the original decoder below. Zero/illegal IDs contribute no bit,
        // and duplicate destinations naturally merge in the bitmap.
        if(ROB_ENTRIES==32 && PHYS_REGS==56 && PHYS_ADDR_WIDTH==6) begin:g_word_reclaim
            reg [PHYS_REGS-1:0] destinations;
            integer row;
            always @* begin
                destinations=0;
                row=0;
                if(|reclaim_eligible)
                    for(row=0;row<ROB_ENTRIES;row=row+1)
                        if(reclaim_eligible[row] && new_phys_mem[row]!=0 && 32'(new_phys_mem[row])<PHYS_REGS)
                            destinations=destinations | (PHYS_REGS'(1)<<new_phys_mem[row]);
            end
            assign reclaim_bitmap=destinations;
            for(reclaim_phys=0;reclaim_phys<RECLAIM_LEAVES;reclaim_phys=reclaim_phys+1) begin:g_count
                if(reclaim_phys<PHYS_REGS)
                    begin : g_named_798_20
assign reclaim_count_tree[RECLAIM_LEAVES+reclaim_phys]=RECLAIM_COUNT_WIDTH'(destinations[reclaim_phys]);
end
                else begin : g_named_799_21
assign reclaim_count_tree[RECLAIM_LEAVES+reclaim_phys]=0;
end
            end
        end else begin:g_original_reclaim
`endif
    wire [ROB_ENTRIES*PHYS_REGS-1:0] reclaim_row_destinations;
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
                if (reclaim_phys == 0) begin : g_named_845_39
assign reclaim_bitmap[0] = 1'b0;
end
                assign reclaim_count_tree[RECLAIM_LEAVES+reclaim_phys] = 0;
            end
        end
`ifdef CPU2026_WORD_SIM
        end
`endif
        for (reclaim_node = 1; reclaim_node < RECLAIM_LEAVES; reclaim_node = reclaim_node + 1) begin : g_reclaim_sum
            assign reclaim_count_tree[reclaim_node] = reclaim_count_tree[2*reclaim_node] + reclaim_count_tree[2*reclaim_node+1];
        end
    endgenerate

    wire [RECLAIM_COUNT_WIDTH-1:0] recovery_reclaim_count;
    generate if(RECLAIM_UNIQUE_DESTINATIONS!=0) begin:g_unique_reclaim_count
        // Bitmap decode and count are parallel. Each qualified ROB owner
        // contributes one; no late physical decoder/OR feeds the count tree.
        localparam integer ROW_LEAVES=1<<SLOT_WIDTH;
        wire [RECLAIM_COUNT_WIDTH-1:0] counts [1:2*ROW_LEAVES-1];
        for(genvar row=0;row<ROW_LEAVES;row=row+1) begin:g_leaf
            if(row<ROB_ENTRIES) begin:g_present
                wire [PHYS_ADDR_WIDTH-1:0] destination=new_phys_mem[row];
                assign counts[ROW_LEAVES+row]=RECLAIM_COUNT_WIDTH'(reclaim_eligible[row] &&
                    destination!=0 && 32'(destination)<PHYS_REGS);
            end else begin:g_padding
                assign counts[ROW_LEAVES+row]=0;
            end
        end
        for(genvar node=1;node<ROW_LEAVES;node=node+1) begin:g_sum
            assign counts[node]=counts[2*node]+counts[2*node+1];
        end
        assign recovery_reclaim_count=counts[1];
    end else begin:g_distinct_bitmap_reclaim_count
        assign recovery_reclaim_count=reclaim_count_tree[1];
    end endgenerate

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
    wire [BE_WIDTH-1:0] recovery_lane_in_window;
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
            wire [SLOT_WIDTH-1:0] original_age=tag[SLOT_LSB +: SLOT_WIDTH]-head_recovery_index;
            wire original_in_window=COUNT_WIDTH'(original_age)<
                occupancy_views[OCCUPANCY_ROW_DOMAINS*COUNT_WIDTH +: COUNT_WIDTH];
            if(RECOVERY_WINDOW_OWNED!=0) begin:g_owned_window
                // Acquisition uses the original full ROB identity. A redirect
                // cannot retire ordinarily before its pending owner clears.
                assign recovery_lane_in_window[recovery_query_lane]=1'b1;
`ifdef VERILATOR
                always @(posedge clk_i) if(!reset_i && recovery_valid_i[recovery_query_lane])
                    assert(original_in_window)
                        else $fatal(1,"Private pending recovery left the original ROB window");
`endif
            end else begin:g_original_window
                assign recovery_lane_in_window[recovery_query_lane]=original_in_window;
            end
            if(RECOVERY_CALLER_OWNED!=0) begin:g_caller_owned
                // Validity is a private caller's ownership certificate. Keep
                // tag-valid and slot/range. Window ownership is independent.
                assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] &&
                    32'(tag[SLOT_LSB +: SLOT_WIDTH])<ROB_ENTRIES;
`ifdef VERILATOR
                wire [RECOVERY_LIVE_WIDTH-1:0] original_state;
                rv32_frequency_array_read #(.WIDTH(RECOVERY_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) original_reader (
                    .rows_i(recovery_live_rows),.index_i(tag[SLOT_LSB +: SLOT_WIDTH]),.value_o(original_state));
                wire original_live=tag[VALID_LSB] && original_state[GENERATION_WIDTH] &&
                    tag[GEN_LSB +: GENERATION_WIDTH]==original_state[0 +: GENERATION_WIDTH];
                always @(posedge clk_i) if(!reset_i && recovery_valid_i[recovery_query_lane])
                    assert(original_live)
                        else $fatal(1,"Caller-owned recovery lost its full ROB identity");
`endif
            end else if(RECOVERY_ROW_LIVE_QUALIFY!=0) begin:g_row_live
                localparam integer QUERY_WIDTH=SLOT_WIDTH+GENERATION_WIDTH;
                localparam integer DOMAINS=(ROB_ENTRIES+3)/4;
                localparam integer LEAVES=1<<$clog2(ROB_ENTRIES);
                wire [DOMAINS*QUERY_WIDTH-1:0] query_views;
                wire live_tree [1:2*LEAVES-1];
                // Compare every saved row's complete GEN before selecting it.
                // No selected GEN bus followed by a late equality comparison.
                rv32_frequency_control_tree #(.WIDTH(QUERY_WIDTH),.LEAVES(DOMAINS)) query_tree (
                    .signal_i({tag[GEN_LSB +: GENERATION_WIDTH],tag[SLOT_LSB +: SLOT_WIDTH]}),
                    .views_o(query_views));
                for(genvar live_row=0;live_row<LEAVES;live_row=live_row+1) begin:g_row
                    if(live_row<ROB_ENTRIES) begin:g_present
                        wire [QUERY_WIDTH-1:0] query=query_views[(live_row/4)*QUERY_WIDTH +: QUERY_WIDTH];
                        wire [RECOVERY_LIVE_WIDTH-1:0] state=recovery_live_rows[live_row*RECOVERY_LIVE_WIDTH +: RECOVERY_LIVE_WIDTH];
                        wire generation_matches=query[SLOT_WIDTH +: GENERATION_WIDTH]==state[0 +: GENERATION_WIDTH];
                        wire slot_matches=query[0 +: SLOT_WIDTH]==live_row;
                        assign live_tree[LEAVES+live_row]=slot_matches && state[GENERATION_WIDTH] && generation_matches;
                    end else begin:g_padding
                        assign live_tree[LEAVES+live_row]=1'b0;
                    end
                end
                for(genvar live_node=1;live_node<LEAVES;live_node=live_node+1) begin:g_reduce
                    rv32_rob_recovery_live_or pair (
                        .left_i(live_tree[2*live_node]),.right_i(live_tree[2*live_node+1]),
                        .value_o(live_tree[live_node]));
                end
                assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] && live_tree[1];
            end else begin:g_original_live_read
            wire [RECOVERY_LIVE_WIDTH-1:0] live_state;
            rv32_frequency_array_read #(.WIDTH(RECOVERY_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) live_reader (
                .rows_i(recovery_live_rows),.index_i(tag[SLOT_LSB +: SLOT_WIDTH]),.value_o(live_state));
            assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] && live_state[GENERATION_WIDTH] &&
                tag[GEN_LSB +: GENERATION_WIDTH]==live_state[0 +: GENERATION_WIDTH];
            end
        end
    endgenerate
    rv32_frequency_array_read #(.WIDTH(RECOVERY_DEST_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) recovery_dest_reader (
        .rows_i(recovery_dest_rows),.index_i(SLOT_WIDTH'(chosen_slot)),.value_o(recovery_selected_dest));

    localparam STORE_PREFIX_ADMISSION_ACTIVE=(STORE_PREFIX_ADMISSION!=0) &&
        (BE_WIDTH>1) && (ROB_ENTRIES>=BE_WIDTH) && (ALLOC_BANKED_WRITE!=0) &&
        (STORE_BUFFERED_RETIRE!=0) && (LIGHT_RETIRE_PAYLOAD!=0) &&
        (MMIO_PREDECODE!=0) && (LEGACY_HALT_PAYLOAD==0) && (RETURN_VALUE_ENABLE==0);
    wire [TAG_WIDTH-1:0] prefix_admission_tag;
    reg [TAG_WIDTH-1:0] store_commit_tag_legacy;
    // Query identity comes from saved owners before the ready/retire handshake.
    // Invalid payload tags are unobservable; only valid architectural offers fire.
    assign store_commit_tag_o=(STORE_RETIRE_ADMISSION_BYPASS!=0) ?
        ((STORE_PREFIX_ADMISSION_ACTIVE!=0) ? prefix_admission_tag :
         make_tag(32'(head_commit_index),head_generation[0])) : store_commit_tag_legacy;
    initial if(STORE_RETIRE_ADMISSION_BYPASS!=0 && STORE_RETIRE_ADMISSION_BYPASS!=1)
        $fatal(1,"STORE_RETIRE_ADMISSION_BYPASS must be 0 or 1");
    generate if(STORE_PREFIX_ADMISSION_ACTIVE!=0) begin:g_store_prefix_identity
        wire [BE_WIDTH-1:0] potential,grants;
        wire [BE_WIDTH*TAG_WIDTH-1:0] tags;
        for(genvar admission_lane=0;admission_lane<BE_WIDTH;admission_lane=admission_lane+1) begin:g_lane
            wire [31:0] raw_slot=32'(head_commit_index)+admission_lane;
            wire [31:0] slot=(raw_slot>=ROB_ENTRIES) ? raw_slot-ROB_ENTRIES : raw_slot;
            // Identity depends only on saved head fields, before the late
            // true-retirement prefix and LSQ admission-ready qualification.
            assign potential[admission_lane]=head_valid[admission_lane] &&
                head_store[admission_lane] && !head_store_sent[admission_lane];
            if(admission_lane==0) begin:g_first
                assign grants[admission_lane]=potential[admission_lane];
            end else begin:g_later
                assign grants[admission_lane]=potential[admission_lane] && !(|potential[admission_lane-1:0]);
            end
            assign tags[admission_lane*TAG_WIDTH +: TAG_WIDTH]=make_tag(slot,head_generation[admission_lane]);
        end
        wire  unused_identity_selector_write_o;
        rv32_frequency_event_select #(.WIDTH(TAG_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) identity_selector (
            .events_i(grants),.values_i(tags),.write_o(unused_identity_selector_write_o),.value_o(prefix_admission_tag));
    end else begin:g_original_store_identity
        assign prefix_admission_tag=0;
    end endgenerate

    // A ready non-store head prefix is guaranteed to retire on this edge.
    // Do not borrow stores, terminals, current completion, or recovery edges.
    // In particular this certificate has no allocation or LSQ ready input.
    wire [BE_WIDTH:0] release_prefix;
    assign release_prefix[0]=(RELEASE_CREDITS!=0) && !reset_i && commit_ready_i &&
        !halted_o && !error_o && !recovery_hold_i && !recovery_hold &&
        !(|recovery_valid_i) && !recovery_apply_i;
    wire [ALLOC_COUNT_WIDTH-1:0] release_count_tree [0:BE_WIDTH];
    assign release_count_tree[0]=0;
    for(genvar release_lane=0;release_lane<BE_WIDTH;release_lane=release_lane+1) begin:g_release_credit
        assign release_prefix[release_lane+1]=release_prefix[release_lane] &&
            head_valid[release_lane] && head_ready[release_lane] &&
            !head_store[release_lane] && !head_halt[release_lane] && !head_error[release_lane];
        assign release_count_tree[release_lane+1]=release_count_tree[release_lane]+
            ALLOC_COUNT_WIDTH'(release_prefix[release_lane+1]);
    end
    assign allocation_release_count_o=release_count_tree[BE_WIDTH];
`ifdef VERILATOR
    always @(posedge clk_i) if(!reset_i && RELEASE_CREDITS!=0)
        assert(32'(allocation_release_count_o)<= (commit_ready_i ? pop_count : 0))
            else $fatal(1,"ROB release credit exceeds actual retirement");
`endif

    // Accepted ordinary completions may retire on the same edge. Retain
    // full slot/generation authority, ordered prefix and precise terminals.
    wire [BE_WIDTH-1:0] completion_commit_bypass;
    wire [31:0] completion_commit_value [0:BE_WIDTH-1];
    generate for(genvar bypass_lane=0;bypass_lane<BE_WIDTH;bypass_lane=bypass_lane+1) begin:g_commit_bypass
        if(COMPLETION_COMMIT_BYPASS!=0) begin:g_enabled
            wire [SLOT_WIDTH-1:0] slot=advance_slot(head_commit_index,bypass_lane);
            wire [ROB_ENTRIES-1:0] branch_rows;
            wire head_branch;
            for(genvar bypass_row=0;bypass_row<ROB_ENTRIES;bypass_row=bypass_row+1) begin:g_branch_row
                assign branch_rows[bypass_row]=branch_mem[bypass_row];
            end
            rv32_frequency_array_read #(.WIDTH(1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) branch_reader (
                .rows_i(branch_rows),.index_i(slot),.value_o(head_branch));
            reg matched,error_match;
            reg [31:0] value;
            integer source;
            reg [TAG_WIDTH-1:0] tag;
            always @* begin
                matched=0;error_match=0;value=0;tag=0;
                for(source=0;source<BE_WIDTH;source=source+1) begin
                    tag=completion_tag_i[source*TAG_WIDTH +: TAG_WIDTH];
                    if(completion_valid_i[source] && completion_done_i[source] && tag[VALID_LSB] &&
                       tag[SLOT_LSB +: SLOT_WIDTH]==slot &&
                       tag[GEN_LSB +: GENERATION_WIDTH]==head_generation[bypass_lane]) begin
                        matched=1;
                        error_match=error_match || completion_error_i[source];
                        value=completion_value_i[source*32 +: 32];
                    end
                end
            end
            assign completion_commit_bypass[bypass_lane]=!reset_i && head_valid[bypass_lane] &&
                !head_ready[bypass_lane] && !head_store[bypass_lane] && !head_halt[bypass_lane] &&
                !head_error[bypass_lane] && !head_branch && matched && !error_match;
            assign completion_commit_value[bypass_lane]=value;
        end else begin:g_disabled
            assign completion_commit_bypass[bypass_lane]=1'b0;
            assign completion_commit_value[bypass_lane]=32'b0;
        end
    end endgenerate
    initial if(COMPLETION_COMMIT_BYPASS!=0 && COMPLETION_COMMIT_BYPASS!=1)
        $fatal(1,"COMPLETION_COMMIT_BYPASS must be 0 or 1");

    // Allocation and all observable outputs are evaluated from old state.
    always @* begin
        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        prefix_open = !recovery_hold;
        allocation_count = 0;
        free_entries = ROB_ENTRIES - 32'(occupancy_reg) + 32'(allocation_release_count_o);
        alloc_slot = 0;
        for (alloc_lane = 0; alloc_lane < BE_WIDTH; alloc_lane = alloc_lane + 1) begin
            if (prefix_open && alloc_valid_i[alloc_lane] && (allocation_count < free_entries)) begin
                alloc_fire_o[alloc_lane] = 1'b1;
                alloc_slot = 32'(tail_reg) + allocation_count;
                if (alloc_slot >= ROB_ENTRIES) alloc_slot = alloc_slot - ROB_ENTRIES;
                alloc_tag_o[(alloc_lane*TAG_WIDTH) +: TAG_WIDTH] = make_tag(alloc_slot, generation_next_mem[alloc_slot]);
                allocation_count = allocation_count + 1;
                alloc_count_o = ((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))'(allocation_count);
            end else if (alloc_valid_i[alloc_lane]) begin
                prefix_open = 1'b0;
            end
        end

    end

    always @* begin
        // Recoveries are selected oldest-first using distance from head.
        recovery_found = 1'b0;
        chosen_age = ROB_ENTRIES + 1;
        chosen_slot = 0;
        for (recovery_lane = 0; recovery_lane < BE_WIDTH; recovery_lane = recovery_lane + 1) begin
            // A generation-qualified ROB tag already carries its slot.  Use
            // that slot directly and compare only the BE_WIDTH candidates.
            recovery_slot = 32'(recovery_tag_i[(recovery_lane*TAG_WIDTH) + SLOT_LSB +: SLOT_WIDTH]);
            age = SLOT_WIDTH'(recovery_slot - 32'(head_recovery_index));
            if (recovery_valid_i[recovery_lane] &&
                recovery_lane_live[recovery_lane] &&
                recovery_lane_in_window[recovery_lane] && (!recovery_found || 32'(age) < chosen_age)) begin
                recovery_found = 1'b1;
                chosen_age = 32'(age);
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
        recovery_reclaim_count_o = recovery_reclaim_count;
        if (recovery_preview_domains[2]) begin
            redirect_pc_o = recovery_pc_i[0 +: 32];
            if (CHECKPOINT_IMPL == 0)
                checkpoint_restore_o = recovery_selected_checkpoint;
            recovery_rd_we_o = recovery_selected_rd_we;
            recovery_rd_o = recovery_selected_rd;
            recovery_new_phys_o = recovery_selected_phys;
        end

    end

    always @* begin
        commit_lane=0;
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
        store_commit_tag_legacy = {TAG_WIDTH{1'b0}};
        store_commit_addr_o = 32'b0;
        store_commit_mask_o = 16'b0;
        store_commit_data_o = 128'b0;
        pop_count = 0;
        commit_slot = 0;
        commit_break = 1'b0;
        if (!recovery_domains[5] && !recovery_hold && !halted_o && !error_o) begin
            for (commit_lane = 0; commit_lane < BE_WIDTH; commit_lane = commit_lane + 1) begin
                if (!commit_break) begin
                    commit_slot = 32'(head_commit_index) + commit_lane;
                    if (commit_slot >= ROB_ENTRIES) commit_slot = commit_slot - ROB_ENTRIES;
                    if (head_valid[commit_lane] && (head_ready[commit_lane] || completion_commit_bypass[commit_lane])) begin
                        commit_valid_o[commit_lane] = 1'b1;
                        commit_rd_we_o[commit_lane] = head_rd_we[commit_lane];
                        commit_rd_o[(commit_lane*5) +: 5] = head_rd[commit_lane];
                        commit_pc_o[(commit_lane*32) +: 32] = head_pc[commit_lane];
                        commit_inst_o[(commit_lane*32) +: 32] = head_inst[commit_lane];
                        commit_value_o[(commit_lane*32) +: 32] = completion_commit_bypass[commit_lane] ?
                            completion_commit_value[commit_lane] : head_value[commit_lane];
                        commit_is_store_o[commit_lane] = head_store[commit_lane];
                        commit_store_addr_o[(commit_lane*32) +: 32] = head_store_addr[commit_lane];
                        commit_store_mask_o[(commit_lane*16) +: 16] =
                            line_mask_from_relative(head_store_mask[commit_lane], head_store_addr[commit_lane]);
                        commit_store_data_o[(commit_lane*128) +: 128] =
                            line_data_from_relative(head_store_data[commit_lane], head_store_addr[commit_lane]);
                        commit_tag_o[(commit_lane*TAG_WIDTH) +: TAG_WIDTH] = make_tag(commit_slot, head_generation[commit_lane]);
                        commit_old_phys_o[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = head_old_phys[commit_lane];
                        commit_new_phys_o[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = head_new_phys[commit_lane];
                        // A store retires only from its registered admission
                        // state as actual head. Optional prefix admission may
                        // publish a following ordinary store on the same edge
                        // that all preceding lanes truly retire; no younger
                        // store retires here and there is still only one port.
                        if (head_store[commit_lane]) begin
                            if (commit_lane == 0) begin
                                if ((STORE_BUFFERED_RETIRE != 0) &&
                                    !(head_mmio_word[commit_lane]))
                                    // Default retires from saved admission. The optional
                                    // exact-tag query has independent saved identity, so
                                    // an actual head admission may retire on this edge.
                                    commit_valid_o[commit_lane] = head_store_sent[commit_lane] ||
                                        ((STORE_RETIRE_ADMISSION_BYPASS!=0) && store_commit_ready_i &&
                                         !head_halt[commit_lane] && !head_error[commit_lane]);
                                else
                                    commit_valid_o[commit_lane] = head_store_wait[commit_lane];
                            end
                            else
                                commit_valid_o[commit_lane] = 1'b0;
                        end
                        if ((commit_lane == 0 ||
                             (STORE_PREFIX_ADMISSION_ACTIVE!=0 && commit_ready_i &&
                              !head_mmio_word[commit_lane] && !head_halt[commit_lane] && !head_error[commit_lane])) &&
                            head_store[commit_lane] && !head_store_sent[commit_lane] &&
                            !store_commit_valid_o &&
                            ((STORE_BUFFERED_RETIRE != 0) || !head_store_wait[commit_lane])) begin
                            store_commit_valid_o = 1'b1;
                            store_commit_tag_legacy = (STORE_PREFIX_ADMISSION_ACTIVE!=0) ?
                                prefix_admission_tag : make_tag(commit_slot, head_generation[commit_lane]);
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
    // Removed field owners must also leave their broadcast/mux lanes.
    localparam COMPLETION_KEEP_VALUE=(LIGHT_RETIRE_PAYLOAD==0) || (LEGACY_HALT_PAYLOAD!=0);
    localparam COMPLETION_KEEP_ADDRESS=(LIGHT_RETIRE_PAYLOAD==0) || (MMIO_PREDECODE==0);
    localparam COMPLETION_KEEP_DATA=(LIGHT_RETIRE_PAYLOAD==0) || (RETURN_VALUE_ENABLE!=0);
    localparam integer LOCAL_COMPLETION_DATA_WIDTH=1+
        (COMPLETION_KEEP_VALUE?32:0)+(COMPLETION_KEEP_ADDRESS?36:0)+(COMPLETION_KEEP_DATA?32:0);
    localparam integer LOCAL_COMPLETION_WIDTH=3+TAG_WIDTH+LOCAL_COMPLETION_DATA_WIDTH;
    localparam integer LOCAL_COMPLETION_LEAVES=1<<$clog2(BE_WIDTH);
    wire [BE_WIDTH*LOCAL_COMPLETION_WIDTH-1:0] local_completion_input;
    wire [WRITE_DOMAINS*BE_WIDTH*LOCAL_COMPLETION_WIDTH-1:0] local_completion_domains;
    wire [2*ROB_ENTRIES-1:0] local_modes;
    wire [WRITE_DOMAINS*3*SLOT_WIDTH-1:0] local_indexes;
    wire [WRITE_DOMAINS*BE_WIDTH-1:0] local_commits;
    wire [WRITE_DOMAINS-1:0] local_store_sends;
    wire [WRITE_DOMAINS*SLOT_WIDTH-1:0] local_store_send_slots;
    generate if(STORE_PREFIX_ADMISSION_ACTIVE!=0) begin:g_prefix_send_slots
        rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(WRITE_DOMAINS)) slot_tree (
            .signal_i(prefix_admission_tag[SLOT_LSB +: SLOT_WIDTH]),.views_o(local_store_send_slots));
    end else begin:g_original_send_slots
        assign local_store_send_slots=0;
    end endgenerate
    wire [WRITE_DOMAINS*(TAG_WIDTH+2)-1:0] local_acks;
    localparam FAST_STORE_OWNER_ACTIVE=(FAST_STORE_COMPLETE!=0) &&
        (ALLOC_BANKED_WRITE!=0) && (ROB_ENTRIES>=BE_WIDTH) &&
        (LIGHT_RETIRE_PAYLOAD!=0) && (MMIO_PREDECODE!=0) &&
        (LEGACY_HALT_PAYLOAD==0) && (RETURN_VALUE_ENABLE==0);
    // Preselected mode carries one early saved identity and one late
    // accepted event, retaining the complete current row/GEN/valid check.
    localparam integer FAST_STORE_OWNER_LANES=
        ((FAST_STORE_IDENTITY_PRESELECT!=0) && (FAST_STORE_BATCH==0)) ? 1 : BE_WIDTH;
    localparam integer FAST_STORE_DOMAINS=(ROB_ENTRIES+3)/4;
    wire [FAST_STORE_DOMAINS*FAST_STORE_OWNER_LANES-1:0] fast_store_valid_views;
    wire [FAST_STORE_DOMAINS*FAST_STORE_OWNER_LANES*TAG_WIDTH-1:0] fast_store_tag_views;
    generate if(FAST_STORE_OWNER_ACTIVE!=0) begin:g_fast_store_owner_inputs
        rv32_frequency_control_tree #(.WIDTH(FAST_STORE_OWNER_LANES),.LEAVES(FAST_STORE_DOMAINS)) valid_tree (
            .signal_i(fast_store_valid_i[FAST_STORE_OWNER_LANES-1:0]),.views_o(fast_store_valid_views));
        rv32_frequency_control_tree #(.WIDTH(FAST_STORE_OWNER_LANES*TAG_WIDTH),.LEAVES(FAST_STORE_DOMAINS)) tag_tree (
            .signal_i(fast_store_tag_i[FAST_STORE_OWNER_LANES*TAG_WIDTH-1:0]),.views_o(fast_store_tag_views));
    end else begin:g_no_fast_store_owner_inputs
        assign fast_store_valid_views=0;
        assign fast_store_tag_views=0;
    end endgenerate

    genvar command_row,command_lane,command_node;
    generate
    if(ALLOC_BANKED_WRITE!=0 && ROB_ENTRIES>=BE_WIDTH) begin:g_local_row_commands
        for(command_lane=0;command_lane<BE_WIDTH;command_lane=command_lane+1) begin:g_input
            wire mmio=(completion_store_addr_i[command_lane*32 +: 32]==32'h80000000) &&
                (completion_store_mask_i[command_lane*4 +: 4]==4'hf);
            wire [LOCAL_COMPLETION_DATA_WIDTH-1:0] compact_data;
            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_completion
                assign compact_data={completion_value_i[command_lane*32 +: 32],completion_store_addr_i[command_lane*32 +: 32],completion_store_data_i[command_lane*32 +: 32],completion_store_mask_i[command_lane*4 +: 4],mmio};
            end else begin:g_light_completion
            if(MMIO_PREDECODE==0) begin:g_mmio_0
                if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign compact_data={completion_value_i[command_lane*32 +: 32],completion_store_addr_i[command_lane*32 +: 32],completion_store_data_i[command_lane*32 +: 32],completion_store_mask_i[command_lane*4 +: 4],mmio};
                    end
                    else begin:g_return_0
                        assign compact_data={completion_value_i[command_lane*32 +: 32],completion_store_addr_i[command_lane*32 +: 32],completion_store_mask_i[command_lane*4 +: 4],mmio};
                    end
                end
                else begin:g_halt_0
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign compact_data={completion_store_addr_i[command_lane*32 +: 32],completion_store_data_i[command_lane*32 +: 32],completion_store_mask_i[command_lane*4 +: 4],mmio};
                    end
                    else begin:g_return_0
                        assign compact_data={completion_store_addr_i[command_lane*32 +: 32],completion_store_mask_i[command_lane*4 +: 4],mmio};
                    end
                end
            end
            else begin:g_mmio_1
                if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign compact_data={completion_value_i[command_lane*32 +: 32],completion_store_data_i[command_lane*32 +: 32],mmio};
                    end
                    else begin:g_return_0
                        assign compact_data={completion_value_i[command_lane*32 +: 32],mmio};
                    end
                end
                else begin:g_halt_0
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign compact_data={completion_store_data_i[command_lane*32 +: 32],mmio};
                    end
                    else begin:g_return_0
                        assign compact_data={mmio};
                    end
                end
            end
            end
            assign local_completion_input[command_lane*LOCAL_COMPLETION_WIDTH +: LOCAL_COMPLETION_WIDTH]={
                completion_valid_i[command_lane],completion_done_i[command_lane],
                completion_error_i[command_lane],completion_tag_i[command_lane*TAG_WIDTH +: TAG_WIDTH],compact_data};
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
                ((STAGED_RECOVERY != 0) ? recovery_saved_kill[command_row] :
                 (valid_mem[command_row] && row_age>row_branch_age && COUNT_WIDTH'(row_age)<occupancy_views[(command_row/4)*COUNT_WIDTH +: COUNT_WIDTH]));
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
                    wire [31:0] commit_offset=32'(row_commit_head)+command_lane;
                    wire [31:0] local_commit_slot=(commit_offset>=ROB_ENTRIES)?commit_offset-ROB_ENTRIES:commit_offset;
                    assign retire_match[command_lane]=normal &&
                        local_commits[DOMAIN*BE_WIDTH+command_lane] && local_commit_slot==command_row;
                end else begin:g_padding
                    assign completion_mux[LOCAL_COMPLETION_LEAVES+command_lane]=0;
                end
            end
            for(command_node=1;command_node<LOCAL_COMPLETION_LEAVES;command_node=command_node+1) begin:g_or
                assign completion_mux[command_node]=completion_mux[2*command_node] | completion_mux[2*command_node+1];
            end
            // Full current ROB identity is checked independently per D
            // lane before late allocation-valid qualification. No shortened
            // generation, selected-tag lookup or ordinary CDB ready is used.
            wire [FAST_STORE_OWNER_LANES-1:0] fast_store_matches;
            for(genvar fast_lane=0;fast_lane<FAST_STORE_OWNER_LANES;fast_lane=fast_lane+1) begin:g_fast_store_match
                if(FAST_STORE_OWNER_ACTIVE!=0) begin:g_enabled
                    wire [TAG_WIDTH-1:0] tag=
                        fast_store_tag_views[((command_row/4)*FAST_STORE_OWNER_LANES+fast_lane)*TAG_WIDTH +: TAG_WIDTH];
                    wire target=tag_matches(tag,command_row) && store_mem[command_row] &&
                        !rd_we_mem[command_row] && !branch_mem[command_row] && !halt_mem[command_row];
                    assign fast_store_matches[fast_lane]=normal && target &&
                        fast_store_valid_views[(command_row/4)*FAST_STORE_OWNER_LANES+fast_lane];
                end else begin:g_disabled
                    assign fast_store_matches[fast_lane]=1'b0;
                end
            end
            wire fast_store_completed=|fast_store_matches;
            wire completed=|completion_match;
            wire retire=|retire_match;
            wire ack_valid,ack_error;
            wire [TAG_WIDTH-1:0] ack_tag;
            assign {ack_valid,ack_error,ack_tag}=local_acks[DOMAIN*(TAG_WIDTH+2) +: TAG_WIDTH+2];
            wire acknowledged=normal && ack_valid && tag_matches(ack_tag,command_row);
            wire [SLOT_WIDTH-1:0] row_send_slot=(STORE_PREFIX_ADMISSION_ACTIVE!=0) ?
                local_store_send_slots[DOMAIN*SLOT_WIDTH +: SLOT_WIDTH] : row_commit_head;
            wire sent=normal && local_store_sends[DOMAIN] && row_send_slot==command_row;
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
            if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_completed_fields
                assign {completed_value,completed_addr,completed_data,completed_mask,completed_mmio}=completion_mux[1];
            end else begin:g_light_completed_fields
            if(MMIO_PREDECODE==0) begin:g_mmio_0
                if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign {completed_value,completed_addr,completed_data,completed_mask,completed_mmio}=completion_mux[1];
                    end
                    else begin:g_return_0
                        assign {completed_value,completed_addr,completed_mask,completed_mmio}=completion_mux[1];
                        assign completed_data=32'b0;
                    end
                end
                else begin:g_halt_0
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign {completed_addr,completed_data,completed_mask,completed_mmio}=completion_mux[1];
                        assign completed_value=32'b0;
                    end
                    else begin:g_return_0
                        assign {completed_addr,completed_mask,completed_mmio}=completion_mux[1];
                        assign completed_value=32'b0;
                        assign completed_data=32'b0;
                    end
                end
            end
            else begin:g_mmio_1
                if(LEGACY_HALT_PAYLOAD!=0) begin:g_halt_1
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign {completed_value,completed_data,completed_mmio}=completion_mux[1];
                        assign completed_addr=32'b0;
                        assign completed_mask=4'b0;
                    end
                    else begin:g_return_0
                        assign {completed_value,completed_mmio}=completion_mux[1];
                        assign completed_addr=32'b0;
                        assign completed_data=32'b0;
                        assign completed_mask=4'b0;
                    end
                end
                else begin:g_halt_0
                    if(RETURN_VALUE_ENABLE!=0) begin:g_return_1
                        assign {completed_data,completed_mmio}=completion_mux[1];
                        assign completed_value=32'b0;
                        assign completed_addr=32'b0;
                        assign completed_mask=4'b0;
                    end
                    else begin:g_return_0
                        assign {completed_mmio}=completion_mux[1];
                        assign completed_value=32'b0;
                        assign completed_addr=32'b0;
                        assign completed_data=32'b0;
                        assign completed_mask=4'b0;
                    end
                end
            end
            end
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
                ready_mem_write_enable[command_row]=row_reset || killed || completed || fast_store_completed || retire || allocate;
                ready_mem_write_data[command_row]=!row_reset && !allocate && !retire && (completed || fast_store_completed);
                store_wait_mem_write_enable[command_row]=row_reset || killed || acknowledged || retire || allocate;
                store_wait_mem_write_data[command_row]=!row_reset && !allocate && !retire && acknowledged;
                store_sent_mem_write_enable[command_row]=row_reset || killed || sent || retire || allocate;
                store_sent_mem_write_data[command_row]=!row_reset && !allocate && !retire && sent;
                error_mem_write_enable[command_row]=row_reset || allocate ||
                    (|completion_errors) || (acknowledged && ack_error);
                error_mem_write_data[command_row]=row_reset ? 1'b0 : (allocate ? allocation_error : 1'b1);
                generation_mem_write_enable[command_row]=row_reset || allocate;
                generation_mem_write_data[command_row]=row_reset ? GENERATION_RESET : next_generation_local;
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
                mmio_word_mem_write_enable[command_row]=(MMIO_PREDECODE!=0) && (completed || fast_store_completed);
                // The extra event is exclusively ordinary RAM. Original CDB
                // data wins if a caller offers both events for the same tag.
                mmio_word_mem_write_data[command_row]=completed ? completed_mmio : 1'b0;
                checkpoint_mem_write_enable[command_row]=(CHECKPOINT_IMPL==0) && allocate;
                checkpoint_mem_write_data[command_row]=bank_alloc_packet[command_row%BE_WIDTH][0 +: CHECKPOINT_WIDTH];
            end
        end
    end else begin:g_legacy_field_commands
    always @* begin : g_state_commands
        reg [GENERATION_WIDTH-1:0] bank_bank_next_generation;
        integer bank_branch_age;
        integer bank_complete_lane;
        reg [GENERATION_WIDTH-1:0] local_bank_next_generation;
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
        local_bank_next_generation=0;
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
                begin generation_mem_write_data[bank_reset_slot] = GENERATION_RESET; generation_mem_write_enable[bank_reset_slot] = 1'b1; end
                begin generation_next_mem_write_data[bank_reset_slot] = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1}; generation_next_mem_write_enable[bank_reset_slot] = 1'b1; end
            end
        end else if (recovery_domains[5]) begin

            bank_branch_age = apply_age;
            for (bank_reset_slot = 0; bank_reset_slot < ROB_ENTRIES; bank_reset_slot = bank_reset_slot + 1) begin
                bank_younger_age = bank_reset_slot - head_update_index;
                if (STAGED_RECOVERY ? recovery_saved_kill[bank_reset_slot] :
                    (valid_mem[bank_reset_slot] && (bank_younger_age > bank_branch_age) && (bank_younger_age < occupancy_views[(bank_reset_slot/4)*COUNT_WIDTH +: COUNT_WIDTH]))) begin
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
                    local_bank_next_generation = generation_next_mem[bank_update_alloc_slot];
                    if (local_bank_next_generation == {GENERATION_WIDTH{1'b0}})
                        local_bank_next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                    begin generation_mem_write_data[bank_update_alloc_slot] = local_bank_next_generation; generation_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
                    begin generation_next_mem_write_data[bank_update_alloc_slot] = (local_bank_next_generation == {GENERATION_WIDTH{1'b1}}) ? {{(GENERATION_WIDTH-1){1'b0}}, 1'b1} : local_bank_next_generation + 1'b1; generation_next_mem_write_enable[bank_update_alloc_slot] = 1'b1; end
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
        if (reset_i)
        begin
            head_reg <= 0;
            tail_reg <= 0;
            occupancy_reg <= 0;
            epoch_reg <= 0;
            halted_o <= 1'b0;
            error_o <= 1'b0;
            return_value_o <= 0;
        end
        else
            if (recovery_domains[5])
            begin
                tail_reg <= advance_slot(apply_slot, 1);
                occupancy_reg <= COUNT_WIDTH'(branch_age + 1);
                epoch_reg <= epoch_reg + 1'b1;
            end
            else
            begin
                for (update_commit_lane = 0; update_commit_lane < BE_WIDTH; update_commit_lane = update_commit_lane + 1)
                begin
                    if (commit_valid_o[update_commit_lane] && commit_ready_i)
                    begin
                        if (head_store[update_commit_lane] &&
                        head_mmio_word[update_commit_lane])
                        begin
                            halted_o <= 1'b1;
                            return_value_o <= head_store_data[update_commit_lane];
                        end
                        else
                            if (head_halt[update_commit_lane])
                            begin
                                halted_o <= 1'b1;
                                return_value_o <= head_value[update_commit_lane];
                            end
                        if (head_error[update_commit_lane])
                            error_o <= 1'b1;
                    end
                end
                if ((ALLOC_BANKED_WRITE != 0) && (ROB_ENTRIES >= BE_WIDTH))
                begin
                    for (update_alloc_entry = 0; update_alloc_entry < ROB_ENTRIES;
                    update_alloc_entry = update_alloc_entry + 1)
                    begin
                        if (bank_alloc_fire[update_alloc_entry % BE_WIDTH] &&
                        32'(bank_alloc_slot[update_alloc_entry % BE_WIDTH]) == update_alloc_entry)
                        begin

                        end
                    end
                end
                else
                begin
                    for (update_alloc_lane = 0; update_alloc_lane < BE_WIDTH; update_alloc_lane = update_alloc_lane + 1)
                    begin
                        if (alloc_fire_o[update_alloc_lane])
                        begin
                            update_alloc_slot = 32'(tail_reg) + update_alloc_lane;
                            if (update_alloc_slot >= ROB_ENTRIES)
                                update_alloc_slot = update_alloc_slot - ROB_ENTRIES;
                            next_generation = generation_next_mem[update_alloc_slot];
                            if (next_generation == {GENERATION_WIDTH{1'b0}})
                                next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                        end
                    end
                end
                head_reg <= head_next;
                tail_reg <= advance_slot(tail_reg, allocation_count);
                occupancy_reg <= COUNT_WIDTH'(32'(occupancy_reg) - (commit_ready_i ? pop_count : 0) + allocation_count);
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
        if(SINGLE_GENERATION_OWNER!=0) begin:g_single_generation
            assign generation_next_mem[storage_row] =
                (generation_mem[storage_row]=={GENERATION_WIDTH{1'b1}}) ?
                {{(GENERATION_WIDTH-1){1'b0}},1'b1} : generation_mem[storage_row]+1'b1;
        end else begin:g_dual_generation
        rv32_rob_owned_field #(.WIDTH(GENERATION_WIDTH-1+1)) generation_next_mem_owner (
            .clk_i(clk_i),.write_i(generation_next_mem_write_enable[storage_row]),
            .data_i(generation_next_mem_write_data[storage_row]),.data_o(generation_next_mem[storage_row]));
        end
        if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_pc
        rv32_rob_owned_field #(.WIDTH(31+1)) pc_mem_owner (
            .clk_i(clk_i),.write_i(pc_mem_write_enable[storage_row]),
            .data_i(pc_mem_write_data[storage_row]),.data_o(pc_mem[storage_row]));
        end else begin:g_unobserved_pc
            assign pc_mem[storage_row]=32'b0;
        end
        if(LIGHT_RETIRE_PAYLOAD==0) begin:g_full_inst
        rv32_rob_owned_field #(.WIDTH(31+1)) inst_mem_owner (
            .clk_i(clk_i),.write_i(inst_mem_write_enable[storage_row]),
            .data_i(inst_mem_write_data[storage_row]),.data_o(inst_mem[storage_row]));
        end else begin:g_unobserved_inst
            assign inst_mem[storage_row]=32'b0;
        end
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
        if(LIGHT_RETIRE_PAYLOAD==0 || LEGACY_HALT_PAYLOAD!=0) begin:g_full_value
        rv32_rob_owned_field #(.WIDTH(31+1)) value_mem_owner (
            .clk_i(clk_i),.write_i(value_mem_write_enable[storage_row]),
            .data_i(value_mem_write_data[storage_row]),.data_o(value_mem[storage_row]));
        end else begin:g_unobserved_value
            assign value_mem[storage_row]=32'b0;
        end
        if((LIGHT_RETIRE_PAYLOAD==0) || (MMIO_PREDECODE==0)) begin:g_full_store_addr
        rv32_rob_owned_field #(.WIDTH(31+1)) store_addr_mem_owner (
            .clk_i(clk_i),.write_i(store_addr_mem_write_enable[storage_row]),
            .data_i(store_addr_mem_write_data[storage_row]),.data_o(store_addr_mem[storage_row]));
        end else begin:g_unobserved_store_addr
            assign store_addr_mem[storage_row]=32'b0;
        end
        rv32_rob_owned_field #(.WIDTH(1)) mmio_word_mem_owner (
            .clk_i(clk_i),.write_i(mmio_word_mem_write_enable[storage_row]),
            .data_i(mmio_word_mem_write_data[storage_row]),.data_o(mmio_word_mem[storage_row]));
        if((LIGHT_RETIRE_PAYLOAD==0) || (MMIO_PREDECODE==0)) begin:g_full_store_mask
        rv32_rob_owned_field #(.WIDTH(3+1)) store_mask_mem_owner (
            .clk_i(clk_i),.write_i(store_mask_mem_write_enable[storage_row]),
            .data_i(store_mask_mem_write_data[storage_row]),.data_o(store_mask_mem[storage_row]));
        end else begin:g_unobserved_store_mask
            assign store_mask_mem[storage_row]=4'b0;
        end
        if(LIGHT_RETIRE_PAYLOAD==0 || RETURN_VALUE_ENABLE!=0) begin:g_full_store_data
        rv32_rob_owned_field #(.WIDTH(31+1)) store_data_mem_owner (
            .clk_i(clk_i),.write_i(store_data_mem_write_enable[storage_row]),
            .data_i(store_data_mem_write_data[storage_row]),.data_o(store_data_mem[storage_row]));
        end else begin:g_unobserved_store_data
            assign store_data_mem[storage_row]=32'b0;
        end
        if(CHECKPOINT_IMPL==0) begin:g_array_checkpoint
        rv32_rob_owned_field #(.WIDTH(CHECKPOINT_WIDTH-1+1)) checkpoint_mem_owner (
            .clk_i(clk_i),.write_i(checkpoint_mem_write_enable[storage_row]),
            .data_i(checkpoint_mem_write_data[storage_row]),.data_o(checkpoint_mem[storage_row]));
        end else begin:g_unused_array_checkpoint
            assign checkpoint_mem[storage_row]={CHECKPOINT_WIDTH{1'b0}};
        end
    end endgenerate

endmodule
