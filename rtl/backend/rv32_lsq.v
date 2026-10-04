`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Ordered load/store queue.  Addresses and store data may arrive after
// allocation; loads inspect older stores before issuing a cache request.
// Store requests are gated by the ROB commit handshake.  Committed stores may
// accumulate in the queue and drain in program order, allowing the ROB to
// retire past cache latency while the LSQ doubles as a store buffer.
module rv32_lsq #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer LSQ_ENTRIES = 8,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer ROB_TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer STORE_ADMISSION_BYPASS = 0,
    parameter integer STORE_ADDRESS_PROBE = 0,
    parameter integer REQUEST_PIPELINE = 0,
    parameter integer SLOT_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES),
    parameter integer GENERATION_WIDTH = (TAG_WIDTH > (SLOT_WIDTH + 3)) ?
                                          (TAG_WIDTH - SLOT_WIDTH - 3) : 1,
    parameter integer COUNT_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES + 1),
    parameter integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    // A branch recovery trims speculative suffix entries while retaining
    // older memory operations that the ROB still requires for commit.
    input  wire                         recovery_valid_i,
    input  wire [ROB_TAG_WIDTH-1:0]     recovery_tag_i,
    input  wire [((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES))-1:0] recovery_head_i,
    input  wire [15:0]                  recovery_occupancy_i,
    // Completed loads can remain behind a buffered store after retiring.
    // Their ROB slots may be reused before the LSQ head reaches them.
    input  wire [BE_WIDTH-1:0]           retire_valid_i,
    input  wire [(BE_WIDTH*ROB_TAG_WIDTH)-1:0] retire_rob_tag_i,

    input  wire [BE_WIDTH-1:0]           alloc_valid_i,
    output wire                         alloc_ready_o,
    output reg  [BE_WIDTH-1:0]           alloc_fire_o,
    output reg  [ALLOC_COUNT_WIDTH-1:0]  alloc_count_o,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_lsq_tag_o,
    input  wire [BE_WIDTH-1:0]           alloc_is_load_i,
    input  wire [BE_WIDTH-1:0]           alloc_is_store_i,
    input  wire [(BE_WIDTH*ROB_TAG_WIDTH)-1:0] alloc_rob_tag_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_phys_rd_i,
    input  wire [(BE_WIDTH*2)-1:0]       alloc_size_i,
    input  wire [BE_WIDTH-1:0]           alloc_unsigned_i,
    input  wire [BE_WIDTH-1:0]           alloc_addr_valid_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_addr_i,
    input  wire [BE_WIDTH-1:0]           alloc_data_valid_i,
    input  wire [(BE_WIDTH*32)-1:0]      alloc_store_data_i,
    input  wire [(BE_WIDTH*4)-1:0]       alloc_store_mask_i,

    // One shared AGU may publish an address independently of store data.
    // The full LSQ generation tag protects slot reuse. This is not a commit.
    input  wire                         early_addr_valid_i,
    input  wire [TAG_WIDTH-1:0]          early_addr_tag_i,
    input  wire [31:0]                   early_addr_i,
    output wire [LSQ_ENTRIES-1:0]        store_addr_pending_o,
    output wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] store_addr_rob_tag_o,
    output wire [LSQ_ENTRIES*TAG_WIDTH-1:0] store_addr_lsq_tag_o,

    input  wire [BE_WIDTH-1:0]           addr_update_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] addr_update_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      addr_update_i,
    input  wire [BE_WIDTH-1:0]           data_update_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] data_update_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      data_update_i,
    input  wire [(BE_WIDTH*4)-1:0]       data_mask_update_i,
    input  wire [BE_WIDTH-1:0]           wakeup_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] wakeup_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      wakeup_value_i,

    input  wire                         store_commit_valid_i,
    output reg                          store_commit_ready_o,
    input  wire [ROB_TAG_WIDTH-1:0]     store_commit_rob_tag_i,

    output reg                          dcache_req_valid_o,
    input  wire                         dcache_req_ready_i,
    output reg                          dcache_req_is_load_o,
    output reg                          dcache_req_is_store_o,
    output reg  [31:0]                  dcache_req_addr_o,
    output reg  [1:0]                   dcache_req_size_o,
    output reg                          dcache_req_unsigned_o,
    output reg  [15:0]                  dcache_req_mask_o,
    output wire [127:0]                 dcache_req_wdata_o,
    output reg  [ROB_TAG_WIDTH-1:0]     dcache_req_rob_tag_o,
    output reg  [TAG_WIDTH-1:0]         dcache_req_lsq_tag_o,

    input  wire                         dcache_resp_valid_i,
    output reg                          dcache_resp_ready_o,
    input  wire [TAG_WIDTH-1:0]         dcache_resp_lsq_tag_i,
    input  wire [31:0]                  dcache_resp_addr_i,
    input  wire [127:0]                 dcache_resp_line_data_i,
    input  wire [31:0]                  dcache_resp_word_data_i,
    input  wire                         dcache_resp_line_valid_i,
    input  wire                         dcache_resp_error_i,

    output reg                          load_complete_valid_o,
    input  wire                         load_complete_ready_i,
    output reg  [ROB_TAG_WIDTH-1:0]     load_complete_rob_tag_o,
    output reg  [TAG_WIDTH-1:0]         load_complete_lsq_tag_o,
    output reg  [31:0]                  load_complete_value_o,
    output reg  [PHYS_ADDR_WIDTH-1:0]    load_complete_phys_rd_o,
    output reg                          load_complete_unretired_o,
    output reg                          load_complete_error_o,

    input  wire                         dcache_store_ack_valid_i,
    input  wire [TAG_WIDTH-1:0]         dcache_store_ack_lsq_tag_i,
    input  wire                         dcache_store_ack_error_i,
    output reg                          store_ack_valid_o,
    input  wire                         store_ack_ready_i,
    output reg  [ROB_TAG_WIDTH-1:0]     store_ack_rob_tag_o,
    output reg  [TAG_WIDTH-1:0]         store_ack_lsq_tag_o,
    output reg                          store_ack_error_o,

    output wire [COUNT_WIDTH-1:0]       occupancy_o,
    output wire [SLOT_WIDTH-1:0]        head_o,
    output wire [SLOT_WIDTH-1:0]        tail_o
);
    localparam integer TAG_SLOT_LSB = 3;
    localparam integer TAG_GEN_LSB = TAG_SLOT_LSB + SLOT_WIDTH;
    localparam integer ROB_SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES);

    wire valid_mem [0:LSQ_ENTRIES-1];
    reg valid_mem_write_data [0:LSQ_ENTRIES-1];
    reg valid_mem_write_enable [0:LSQ_ENTRIES-1];
    wire load_mem [0:LSQ_ENTRIES-1];
    reg load_mem_write_data [0:LSQ_ENTRIES-1];
    reg load_mem_write_enable [0:LSQ_ENTRIES-1];
    wire store_mem [0:LSQ_ENTRIES-1];
    reg store_mem_write_data [0:LSQ_ENTRIES-1];
    reg store_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [ROB_TAG_WIDTH-1:0] rob_tag_mem [0:LSQ_ENTRIES-1];
    reg [ROB_TAG_WIDTH-1:0] rob_tag_mem_write_data [0:LSQ_ENTRIES-1];
    reg rob_tag_mem_write_enable [0:LSQ_ENTRIES-1];
    wire retired_mem [0:LSQ_ENTRIES-1];
    reg retired_mem_write_data [0:LSQ_ENTRIES-1];
    reg retired_mem_write_enable [0:LSQ_ENTRIES-1];
    integer retirement_slot, retirement_lane;
    wire [GENERATION_WIDTH-1:0] generation_mem [0:LSQ_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_mem_write_data [0:LSQ_ENTRIES-1];
    reg generation_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [GENERATION_WIDTH-1:0] generation_next_mem [0:LSQ_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_next_mem_write_data [0:LSQ_ENTRIES-1];
    reg generation_next_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [1:0] size_mem [0:LSQ_ENTRIES-1];
    reg [1:0] size_mem_write_data [0:LSQ_ENTRIES-1];
    reg size_mem_write_enable [0:LSQ_ENTRIES-1];
    wire unsigned_mem [0:LSQ_ENTRIES-1];
    reg unsigned_mem_write_data [0:LSQ_ENTRIES-1];
    reg unsigned_mem_write_enable [0:LSQ_ENTRIES-1];
    wire addr_ready_mem [0:LSQ_ENTRIES-1];
    reg addr_ready_mem_write_data [0:LSQ_ENTRIES-1];
    reg addr_ready_mem_write_enable [0:LSQ_ENTRIES-1];
    wire data_ready_mem [0:LSQ_ENTRIES-1];
    reg data_ready_mem_write_data [0:LSQ_ENTRIES-1];
    reg data_ready_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [31:0] addr_mem [0:LSQ_ENTRIES-1];
    reg [31:0] addr_mem_write_data [0:LSQ_ENTRIES-1];
    reg addr_mem_write_enable [0:LSQ_ENTRIES-1];
    // Store payloads are kept in access-relative form.  The cache-facing
    // 128-bit line representation is reconstructed only at the boundary.
    wire [31:0] data_mem [0:LSQ_ENTRIES-1];
    reg [31:0] data_mem_write_data [0:LSQ_ENTRIES-1];
    reg data_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [3:0] mask_mem [0:LSQ_ENTRIES-1];
    reg [3:0] mask_mem_write_data [0:LSQ_ENTRIES-1];
    reg mask_mem_write_enable [0:LSQ_ENTRIES-1];
    wire request_sent_mem [0:LSQ_ENTRIES-1];
    reg request_sent_mem_write_data [0:LSQ_ENTRIES-1];
    reg request_sent_mem_write_enable [0:LSQ_ENTRIES-1];
    wire response_wait_mem [0:LSQ_ENTRIES-1];
    reg response_wait_mem_write_data [0:LSQ_ENTRIES-1];
    reg response_wait_mem_write_enable [0:LSQ_ENTRIES-1];
    wire complete_mem [0:LSQ_ENTRIES-1];
    reg complete_mem_write_data [0:LSQ_ENTRIES-1];
    reg complete_mem_write_enable [0:LSQ_ENTRIES-1];
    // Completion may bypass an older committed store that is waiting for a
    // cache refill.  Entries still leave the circular queue in order; this
    // bit prevents the already-reported load from being sent to the ROB a
    // second time while it waits to reach the LSQ head.
    wire load_reported_mem [0:LSQ_ENTRIES-1];
    reg load_reported_mem_write_data [0:LSQ_ENTRIES-1];
    reg load_reported_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [31:0] complete_value_mem [0:LSQ_ENTRIES-1];
    reg [31:0] complete_value_mem_write_data [0:LSQ_ENTRIES-1];
    reg complete_value_mem_write_enable [0:LSQ_ENTRIES-1];
    wire complete_error_mem [0:LSQ_ENTRIES-1];
    reg complete_error_mem_write_data [0:LSQ_ENTRIES-1];
    reg complete_error_mem_write_enable [0:LSQ_ENTRIES-1];
    // Forwarded bytes are likewise relative to the waiting load rather than
    // occupying a full cache line in every LSQ entry.
    wire [3:0] forward_mask_mem [0:LSQ_ENTRIES-1];
    reg [3:0] forward_mask_mem_write_data [0:LSQ_ENTRIES-1];
    reg forward_mask_mem_write_enable [0:LSQ_ENTRIES-1];
    wire [31:0] forward_data_mem [0:LSQ_ENTRIES-1];
    reg [31:0] forward_data_mem_write_data [0:LSQ_ENTRIES-1];
    reg forward_data_mem_write_enable [0:LSQ_ENTRIES-1];
    wire store_commit_mem [0:LSQ_ENTRIES-1];
    reg store_commit_mem_write_data [0:LSQ_ENTRIES-1];
    reg store_commit_mem_write_enable [0:LSQ_ENTRIES-1];
    wire store_ack_mem [0:LSQ_ENTRIES-1];
    reg store_ack_mem_write_data [0:LSQ_ENTRIES-1];
    reg store_ack_mem_write_enable [0:LSQ_ENTRIES-1];
    wire store_ack_error_mem [0:LSQ_ENTRIES-1];
    reg store_ack_error_mem_write_data [0:LSQ_ENTRIES-1];
    reg store_ack_error_mem_write_enable [0:LSQ_ENTRIES-1];

    reg [SLOT_WIDTH-1:0] head_reg;
    // Head address had shared decoded drivers feeding ~170 mapped pins.
    // Every row owns its age/ack/pop query; non-row uses get one extra view.
    wire [(LSQ_ENTRIES+1)*SLOT_WIDTH-1:0] head_query_views;
    rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(LSQ_ENTRIES+1)) head_query_tree (
        .signal_i(head_reg),.views_o(head_query_views));
    wire [6*LSQ_ENTRIES-1:0] head_metadata_rows;
    wire head_valid,head_load,head_complete,head_reported,head_store,head_ack;
    rv32_frequency_array_read #(.WIDTH(6),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) head_metadata_read (
        .rows_i(head_metadata_rows),.index_i(head_reg),
        .value_o({head_valid,head_load,head_complete,head_reported,head_store,head_ack}));
    generate for(genvar head_row=0;head_row<LSQ_ENTRIES;head_row=head_row+1) begin:g_head_metadata
        assign head_metadata_rows[head_row*6 +: 6]={valid_mem[head_row],load_mem[head_row],
            complete_mem[head_row],load_reported_mem[head_row],store_mem[head_row],store_ack_mem[head_row]};
    end endgenerate
    reg [SLOT_WIDTH-1:0] tail_reg;
    reg [COUNT_WIDTH-1:0] occupancy_reg;

    integer i;
    integer lane;
    integer slot;
    integer scan;
    integer candidate;
    integer candidate_age;
    integer alloc_count_calc;
    integer free_count_calc;
    integer pop_count_calc;
    integer alloc_slot;
    integer update_slot;
    integer response_slot;
    integer complete_slot_select;
    integer complete_scan;
    integer complete_index;
    integer commit_slot_select;
    localparam integer RECOVERY_ARITH_WIDTH=
        ((ROB_ENTRIES & (ROB_ENTRIES-1))==0) ? ROB_SLOT_WIDTH : 32;
    reg [RECOVERY_ARITH_WIDTH-1:0] entry_rob_slot;
    reg [RECOVERY_ARITH_WIDTH-1:0] recovery_branch_slot;
    reg [RECOVERY_ARITH_WIDTH-1:0] recovery_branch_age;
    reg [RECOVERY_ARITH_WIDTH-1:0] recovery_entry_age;
    integer recovery_keep_count;
    integer recovery_first_killed;
    integer recovery_kill_found;
    reg candidate_found;
    reg [3:0] target_mask;
    reg [3:0] fwd_mask;
    reg [31:0] fwd_data;
    reg [31:0] response_word;
    reg [31:0] merged_word;
    reg request_fire;
    reg response_match;
    reg response_fire;
    reg complete_slot_found;
    reg commit_fire;
    reg commit_slot_found;
    reg [GENERATION_WIDTH-1:0] next_generation;

    function [31:0] expand_word_bytes;
        input [3:0] mask;
        begin
            expand_word_bytes = {{8{mask[3]}}, {8{mask[2]}},
                                 {8{mask[1]}}, {8{mask[0]}}};
        end
    endfunction

    function [3:0] access_mask;
        input [1:0] size;
        begin
            case (size)
                2'd0: access_mask = 4'b0001;
                2'd1: access_mask = 4'b0011;
                default: access_mask = 4'b1111;
            endcase
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

    function [31:0] relative_data_from_line;
        input [127:0] line_data;
        input [31:0] address;
        begin
            relative_data_from_line = (line_data >> (address[3:0] * 8));
        end
    endfunction

    // Return the bytes of one older store in coordinates relative to a load.
    // Accesses crossing a 16-byte cache-line boundary are outside the current
    // cache contract, matching the previous line-based implementation.
    function [3:0] relative_overlap;
        input [3:0] store_offset;
        input [3:0] store_mask;
        input [3:0] load_offset;
        input [3:0] load_mask;
        integer load_byte;
        integer store_byte;
        begin
            relative_overlap = 4'b0;
            for (load_byte = 0; load_byte < 4; load_byte = load_byte + 1)
                for (store_byte = 0; store_byte < 4; store_byte = store_byte + 1)
                    if (load_mask[load_byte] && store_mask[store_byte] &&
                        ((load_offset + load_byte) == (store_offset + store_byte)))
                        relative_overlap[load_byte] = 1'b1;
        end
    endfunction

    function [31:0] store_data_relative_to_load;
        input [31:0] store_data;
        input [3:0] store_offset;
        input [3:0] store_mask;
        input [3:0] load_offset;
        input [3:0] load_mask;
        integer load_byte;
        integer store_byte;
        begin
            store_data_relative_to_load = 32'b0;
            for (load_byte = 0; load_byte < 4; load_byte = load_byte + 1)
                for (store_byte = 0; store_byte < 4; store_byte = store_byte + 1)
                    if (load_mask[load_byte] && store_mask[store_byte] &&
                        ((load_offset + load_byte) == (store_offset + store_byte)))
                        store_data_relative_to_load[(load_byte*8) +: 8] =
                            store_data[(store_byte*8) +: 8];
        end
    endfunction

    function [31:0] format_relative_value;
        input [31:0] raw_value;
        input [1:0] size;
        input unsigned_load;
        begin
            case (size)
                2'd0: format_relative_value = unsigned_load ?
                    {24'b0, raw_value[7:0]} : {{24{raw_value[7]}}, raw_value[7:0]};
                2'd1: format_relative_value = unsigned_load ?
                    {16'b0, raw_value[15:0]} : {{16{raw_value[15]}}, raw_value[15:0]};
                default: format_relative_value = raw_value;
            endcase
        end
    endfunction

    function [TAG_WIDTH-1:0] make_lsq_tag;
        input integer tag_slot;
        input [GENERATION_WIDTH-1:0] generation;
        begin
            make_lsq_tag = {generation, tag_slot[SLOT_WIDTH-1:0], 2'b01, 1'b1};
        end
    endfunction

    function tag_matches_slot;
        input [TAG_WIDTH-1:0] tag;
        input integer tag_slot;
        begin
            tag_matches_slot = tag[0] && valid_mem[tag_slot] &&
                (tag[TAG_SLOT_LSB +: SLOT_WIDTH] == tag_slot[SLOT_WIDTH-1:0]) &&
                (tag[TAG_GEN_LSB +: GENERATION_WIDTH] == generation_mem[tag_slot]);
        end
    endfunction

    function [SLOT_WIDTH-1:0] advance_slot;
        input [SLOT_WIDTH-1:0] start;
        input integer amount;
        integer p;
        integer n;
        begin
            // Depth is a power of two; the original loop clamps amount
            // to [0,depth]. A full traversal returns to the same slot.
            if(LSQ_ENTRIES==1)
                advance_slot=(amount>0)?{SLOT_WIDTH{1'b0}}:start;
            else if(amount<=0 || amount>=LSQ_ENTRIES)
                advance_slot=start;
            else
                advance_slot=start+amount;
        end
    endfunction

    assign occupancy_o = occupancy_reg;
    assign head_o = head_reg;
    assign tail_o = tail_reg;
    assign alloc_ready_o = !flush_i && (free_count_calc != 0);

    // Physical-slot age is a narrow modulo subtraction (LSQ_ENTRIES is a
    // power of two). Hazard detection is an unordered OR, so inspect each
    // physical store directly instead of muxing the whole store array through
    // head+offset once per older age and once per candidate load.
    wire [SLOT_WIDTH-1:0] entry_age [0:LSQ_ENTRIES-1];
    // For ascending physical rows, age order is (row<head, row).
    // Only the wrap bit needs to traverse a balanced tournament: the
    // physical order of its left/right subtrees is already static.
    localparam integer CIRCULAR_ORDER_POWER2=((LSQ_ENTRIES & (LSQ_ENTRIES-1))==0);
    wire [8*LSQ_ENTRIES-1:0] circular_wrap_views;
    localparam integer HAZARD_WRAP_GROUPS=(LSQ_ENTRIES+3)/4;
    wire [LSQ_ENTRIES*HAZARD_WRAP_GROUPS-1:0] hazard_wrap_views;
    wire pick_wrap [1:2*LSQ_ENTRIES-1];
    generate for(genvar wrap_row=0;wrap_row<LSQ_ENTRIES;wrap_row=wrap_row+1) begin:g_circular_key
        wire row_wrap=wrap_row<head_query_views[wrap_row*SLOT_WIDTH +: SLOT_WIDTH];
        rv32_frequency_control_tree #(.LEAVES(8)) wrap_tree (
            .signal_i(row_wrap),.views_o(circular_wrap_views[wrap_row*8 +: 8]));
        // Each leaf serves at most four opposite rows in the hazard matrix.
        rv32_frequency_control_tree #(.LEAVES(HAZARD_WRAP_GROUPS)) hazard_wrap_tree (
            .signal_i(row_wrap),
            .views_o(hazard_wrap_views[wrap_row*HAZARD_WRAP_GROUPS +: HAZARD_WRAP_GROUPS]));
        assign pick_wrap[LSQ_ENTRIES+wrap_row]=circular_wrap_views[wrap_row*8];
    end endgenerate
    wire [LSQ_ENTRIES-1:0] request_eligible;
    wire [15:0] load_line_mask [0:LSQ_ENTRIES-1];
    wire [15:0] store_line_mask [0:LSQ_ENTRIES-1];
    wire pick_valid [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] pick_slot [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] pick_age [1:2*LSQ_ENTRIES-1];
    wire [31:0] pick_addr [1:2*LSQ_ENTRIES-1];
    wire [3:0] store_overlap [0:LSQ_ENTRIES-1];
    wire [31:0] store_forward_data [0:LSQ_ENTRIES-1];
    wire [3:0] tree_forward_mask;
    wire [31:0] tree_forward_data;
    // This is an architectural admission, not speculative store execution.
    // Only the exact ROB tag with ready address/data can obtain ready below.
    // Recovery cannot record a fresh cache request on its trimming edge.
    wire store_admission_fire = store_commit_valid_i && store_commit_ready_o &&
        !reset_i && !flush_i && !recovery_valid_i;
    // Selection and forwarding belong to separate clock stages. A stalled
    // load also retains the forwarding snapshot, rather than re-evaluating
    // its public request as older stores depart the queue.
    reg selection_valid,selection_load,selection_unsigned;
    reg [SLOT_WIDTH-1:0] selection_slot;
    reg [TAG_WIDTH-1:0] selection_lsq_tag;
    reg [ROB_TAG_WIDTH-1:0] selection_rob_tag;
    reg [31:0] selection_addr,selection_store_data;
    reg [1:0] selection_size;
    reg [3:0] selection_store_mask;
    reg forwarding_hold_valid;
    reg [3:0] forwarding_hold_mask;
    reg [31:0] forwarding_hold_data;
    localparam integer SELECT_STATE_WIDTH=GENERATION_WIDTH+8;
    localparam integer PICK_PAYLOAD_WIDTH=GENERATION_WIDTH+ROB_TAG_WIDTH+40;
    wire [LSQ_ENTRIES*SELECT_STATE_WIDTH-1:0] selection_state_rows;
    wire [LSQ_ENTRIES*PICK_PAYLOAD_WIDTH-1:0] pick_payload_rows;
    wire [LSQ_ENTRIES*4-1:0] candidate_state_rows;
    wire selection_row_valid,selection_row_sent,selection_row_complete,selection_row_wait,
        selection_row_store,selection_row_commit,selection_row_load,selection_row_retired;
    wire [GENERATION_WIDTH-1:0] selection_row_generation,pick_generation;
    wire [ROB_TAG_WIDTH-1:0] pick_rob_tag;
    wire [31:0] pick_store_data;
    wire [3:0] pick_store_mask;
    wire pick_load,pick_unsigned;
    wire [1:0] pick_size;
    wire candidate_wait,candidate_load,candidate_sent,candidate_complete;
    rv32_frequency_array_read #(.WIDTH(SELECT_STATE_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) selection_state_read (
        .rows_i(selection_state_rows),.index_i(selection_slot),
        .value_o({selection_row_generation,selection_row_valid,selection_row_sent,selection_row_complete,selection_row_wait,
                  selection_row_store,selection_row_commit,selection_row_load,selection_row_retired}));
    rv32_frequency_array_read #(.WIDTH(PICK_PAYLOAD_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) pick_payload_read (
        .rows_i(pick_payload_rows),.index_i(pick_slot[1]),
        .value_o({pick_generation,pick_rob_tag,pick_store_data,pick_store_mask,pick_load,pick_size,pick_unsigned}));
    rv32_frequency_array_read #(.WIDTH(4),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) candidate_state_read (
        .rows_i(candidate_state_rows),.index_i(candidate[SLOT_WIDTH-1:0]),
        .value_o({candidate_wait,candidate_load,candidate_sent,candidate_complete}));
    generate for(genvar query_row=0;query_row<LSQ_ENTRIES;query_row=query_row+1) begin:g_selected_query
        assign selection_state_rows[query_row*SELECT_STATE_WIDTH +: SELECT_STATE_WIDTH]={
            generation_mem[query_row],valid_mem[query_row],request_sent_mem[query_row],complete_mem[query_row],response_wait_mem[query_row],
            store_mem[query_row],store_commit_mem[query_row],load_mem[query_row],retired_mem[query_row]};
        assign pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH]={
            generation_mem[query_row],rob_tag_mem[query_row],data_mem[query_row],mask_mem[query_row],
            load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};
        assign candidate_state_rows[query_row*4 +: 4]={
            response_wait_mem[query_row],load_mem[query_row],request_sent_mem[query_row],complete_mem[query_row]};
    end endgenerate
    wire selection_live=selection_valid && selection_row_valid && selection_lsq_tag[0] &&
        selection_lsq_tag[3 +: SLOT_WIDTH]==selection_slot &&
        selection_lsq_tag[3+SLOT_WIDTH +: GENERATION_WIDTH]==selection_row_generation &&
        !selection_row_sent && !selection_row_complete && !selection_row_wait;
    wire selection_discard=selection_valid && !selection_live;
    wire [SLOT_WIDTH-1:0] selected_slot=(REQUEST_PIPELINE!=0)?selection_slot:pick_slot[1];
    wire [31:0] selected_addr=(REQUEST_PIPELINE!=0)?selection_addr:pick_addr[1];
    wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH];
    localparam integer FORWARD_ORDER_WIDTH=SLOT_WIDTH+1;
    wire [LSQ_ENTRIES*FORWARD_ORDER_WIDTH-1:0] selected_order_views;
    wire selected_wrap=selected_slot<head_query_views[LSQ_ENTRIES*SLOT_WIDTH +: SLOT_WIDTH];
    rv32_frequency_control_tree #(.WIDTH(FORWARD_ORDER_WIDTH),.LEAVES(LSQ_ENTRIES)) selected_order_tree (
        .signal_i({selected_wrap,selected_slot}),.views_o(selected_order_views));
    wire [1:0] selected_size=(REQUEST_PIPELINE!=0)?selection_size:pick_size;
    // A forwarding row consumes its own address + decoded byte-mask view.
    // Raw selection FFs no longer drive every row's overlap/data formatter.
    localparam integer FORWARD_QUERY_WIDTH=36;
    wire [LSQ_ENTRIES*FORWARD_QUERY_WIDTH-1:0] forward_query_views;
    rv32_frequency_control_tree #(.WIDTH(FORWARD_QUERY_WIDTH),.LEAVES(LSQ_ENTRIES)) forward_query_tree (
        .signal_i({selected_addr,access_mask(selected_size)}),.views_o(forward_query_views));
    wire selected_unsigned=(REQUEST_PIPELINE!=0)?selection_unsigned:pick_unsigned;
    wire selected_load=(REQUEST_PIPELINE!=0)?selection_load:pick_load;
    wire [3:0] selected_store_mask=(REQUEST_PIPELINE!=0)?selection_store_mask:pick_store_mask;
    wire [31:0] selected_store_data=(REQUEST_PIPELINE!=0)?selection_store_data:pick_store_data;
    wire [ROB_TAG_WIDTH-1:0] selected_rob_tag=(REQUEST_PIPELINE!=0)?selection_rob_tag:pick_rob_tag;
    wire [TAG_WIDTH-1:0] selected_lsq_tag=(REQUEST_PIPELINE!=0)?selection_lsq_tag:
        make_lsq_tag(pick_slot[1],pick_generation);
    wire selection_done=selection_live && (request_fire ||
        (selection_load && candidate_found && ((fwd_mask & target_mask)==target_mask)));
    wire selection_input_fire=(REQUEST_PIPELINE!=0) && !reset_i && !flush_i && !recovery_valid_i &&
        (!selection_valid || selection_discard || selection_done) && pick_valid[1];
    wire [4:0] selection_write_views;
    rv32_frequency_control_tree #(.LEAVES(5)) selection_write_tree (
        .signal_i(selection_input_fire),.views_o(selection_write_views));
    wire forwarding_hold_write=(REQUEST_PIPELINE!=0) && candidate_found && selected_load &&
        dcache_req_valid_o && !dcache_req_ready_i && !forwarding_hold_valid;
    wire forwarding_payload_write;
    rv32_frequency_control_tree #(.LEAVES(1)) forwarding_hold_tree (
        .signal_i(forwarding_hold_write),.views_o(forwarding_payload_write));
    wire [ROB_SLOT_WIDTH-1:0] selection_rob_age=selection_rob_tag[3 +: ROB_SLOT_WIDTH]-recovery_head_i;
    wire [ROB_SLOT_WIDTH-1:0] selection_branch_age=recovery_tag_i[3 +: ROB_SLOT_WIDTH]-recovery_head_i;
    wire selection_recovery_kill=selection_valid &&
        !(selection_row_store && selection_row_commit) &&
        !(selection_row_load && selection_row_retired) &&
        selection_rob_age>selection_branch_age && selection_rob_age<recovery_occupancy_i;
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin selection_valid<=0;forwarding_hold_valid<=0;end
        else if(recovery_valid_i) begin
            if(selection_recovery_kill) begin selection_valid<=0;forwarding_hold_valid<=0;end
        end else begin
            if(selection_input_fire) selection_valid<=1;
            else if(selection_done || selection_discard) selection_valid<=0;
            if(selection_input_fire || selection_done || selection_discard) forwarding_hold_valid<=0;
            else if(forwarding_hold_write) forwarding_hold_valid<=1;
        end
        if(selection_write_views[0]) begin
            selection_slot<=pick_slot[1];
            selection_lsq_tag<=make_lsq_tag(pick_slot[1],pick_generation);
            selection_rob_tag<=pick_rob_tag;
        end
        if(selection_write_views[1]) selection_addr<=pick_addr[1];
        if(selection_write_views[2]) begin
            selection_load<=pick_load;selection_size<=pick_size;
            selection_unsigned<=pick_unsigned;
        end
        if(selection_write_views[3]) selection_store_mask<=pick_store_mask;
        if(selection_write_views[4]) selection_store_data<=pick_store_data;
        if(forwarding_payload_write) begin forwarding_hold_mask<=fwd_mask;forwarding_hold_data<=fwd_data;end
    end

    genvar age_slot;
    generate
        for (age_slot = 0; age_slot < LSQ_ENTRIES; age_slot = age_slot + 1) begin : g_entry_age
            assign entry_age[age_slot] = (age_slot - head_query_views[age_slot*SLOT_WIDTH +: SLOT_WIDTH]) & (LSQ_ENTRIES - 1);
            assign store_addr_pending_o[age_slot] = (STORE_ADDRESS_PROBE != 0) &&
                !reset_i && !flush_i && !recovery_valid_i &&
                (entry_age[age_slot] < occupancy_reg) && valid_mem[age_slot] &&
                store_mem[age_slot] && !addr_ready_mem[age_slot] &&
                !request_sent_mem[age_slot] && !complete_mem[age_slot];
            assign store_addr_rob_tag_o[age_slot*ROB_TAG_WIDTH +: ROB_TAG_WIDTH] = rob_tag_mem[age_slot];
            assign store_addr_lsq_tag_o[age_slot*TAG_WIDTH +: TAG_WIDTH] =
                make_lsq_tag(age_slot, generation_mem[age_slot]);
            assign load_line_mask[age_slot] =
                {12'b0, access_mask(size_mem[age_slot])} << addr_mem[age_slot][3:0];
            assign store_line_mask[age_slot] =
                {12'b0, mask_mem[age_slot]} << addr_mem[age_slot][3:0];
            assign pick_valid[LSQ_ENTRIES+age_slot] = request_eligible[age_slot];
            assign pick_slot[LSQ_ENTRIES+age_slot] = age_slot;
            assign pick_age[LSQ_ENTRIES+age_slot] = entry_age[age_slot];
            assign pick_addr[LSQ_ENTRIES+age_slot] = addr_mem[age_slot];
            wire [SLOT_WIDTH-1:0] local_selected_slot;
            wire local_selected_wrap;
            assign {local_selected_wrap,local_selected_slot}=
                selected_order_views[age_slot*FORWARD_ORDER_WIDTH +: FORWARD_ORDER_WIDTH];
            wire older_than_selected=
                (circular_wrap_views[age_slot*8+7]==local_selected_wrap) ?
                    (age_slot<local_selected_slot) :
                    (!circular_wrap_views[age_slot*8+7] && local_selected_wrap);
            wire [31:0] local_load_addr;
            wire [3:0] local_load_mask,local_overlap;
            assign {local_load_addr,local_load_mask}=
                forward_query_views[age_slot*FORWARD_QUERY_WIDTH +: FORWARD_QUERY_WIDTH];
            rv32_lsq_forward_window window_owner (
                .store_data_i(data_mem[age_slot]),.store_offset_i(addr_mem[age_slot][3:0]),
                .store_mask_i(mask_mem[age_slot]),.load_offset_i(local_load_addr[3:0]),
                .load_mask_i(local_load_mask),.mask_o(local_overlap),.data_o(store_forward_data[age_slot]));
            assign store_overlap[age_slot] =
                valid_mem[age_slot] && store_mem[age_slot] &&
                addr_ready_mem[age_slot] && data_ready_mem[age_slot] &&
                (CIRCULAR_ORDER_POWER2 ? older_than_selected : (entry_age[age_slot] < selected_age)) &&
                (addr_mem[age_slot][31:4] == local_load_addr[31:4]) ? local_overlap : 4'b0;
        end
    endgenerate

    // A load is blocked by any older store with an unknown address, or by an
    // older same-line store whose data is unknown for an overlapping byte.
    // Natural alignment keeps each access inside one 16-byte cache line.
    // Per-entry line masks and an OR reduction avoid a serial hazard scan.
    genvar request_slot, older_slot;
    generate
        for (request_slot = 0; request_slot < LSQ_ENTRIES;
             request_slot = request_slot + 1) begin : g_request_eligible
            wire [LSQ_ENTRIES-1:0] older_hazard;
            for (older_slot = 0; older_slot < LSQ_ENTRIES;
                  older_slot = older_slot + 1) begin : g_older_hazard
                wire older_wrap=hazard_wrap_views[older_slot*HAZARD_WRAP_GROUPS+request_slot/4];
                wire request_wrap=hazard_wrap_views[request_slot*HAZARD_WRAP_GROUPS+older_slot/4];
                wire ordered_before;
                if(older_slot<request_slot) begin:g_lower_slot
                    assign ordered_before=!older_wrap || request_wrap;
                end else if(older_slot>request_slot) begin:g_higher_slot
                    assign ordered_before=!older_wrap && request_wrap;
                end else begin:g_same_slot
                    assign ordered_before=1'b0;
                end
                assign older_hazard[older_slot] =
                    (CIRCULAR_ORDER_POWER2 ? ordered_before : (entry_age[older_slot] < entry_age[request_slot])) &&
                    valid_mem[older_slot] && store_mem[older_slot] &&
                    (!addr_ready_mem[older_slot] ||
                     ((addr_mem[older_slot][31:4] ==
                       addr_mem[request_slot][31:4]) &&
                      !data_ready_mem[older_slot] &&
                       (|(store_line_mask[older_slot] &
                          load_line_mask[request_slot]))));
            end
            assign request_eligible[request_slot] =
                (entry_age[request_slot] < occupancy_reg) &&
                valid_mem[request_slot] &&
                !(REQUEST_PIPELINE!=0 && selection_valid && selection_slot==request_slot) &&
                ((load_mem[request_slot] && addr_ready_mem[request_slot] &&
                  !request_sent_mem[request_slot] &&
                  !complete_mem[request_slot] && !(|older_hazard)) ||
                 (store_mem[request_slot] && addr_ready_mem[request_slot] &&
                  data_ready_mem[request_slot] &&
                  (store_commit_mem[request_slot] ||
                   ((STORE_ADMISSION_BYPASS != 0) && store_admission_fire &&
                    (commit_slot_select == request_slot))) &&
                  !request_sent_mem[request_slot]));
        end
    endgenerate

    // The oldest eligible operation wins a balanced tournament. This avoids
    // a priority chain of age compares across every physical queue slot.
    genvar pick_node, forward_byte, forward_slot, forward_node;
    generate
        for (pick_node = 1; pick_node < LSQ_ENTRIES; pick_node = pick_node + 1) begin : g_pick
            wire choose_left = pick_valid[2*pick_node] &&
                (!pick_valid[2*pick_node+1] ||
                 (CIRCULAR_ORDER_POWER2 ? (!pick_wrap[2*pick_node] || pick_wrap[2*pick_node+1]) :
                  (pick_age[2*pick_node] <= pick_age[2*pick_node+1])));
            assign pick_valid[pick_node] = pick_valid[2*pick_node] || pick_valid[2*pick_node+1];
            assign pick_slot[pick_node] = choose_left ? pick_slot[2*pick_node] : pick_slot[2*pick_node+1];
            assign pick_age[pick_node] = choose_left ? pick_age[2*pick_node] : pick_age[2*pick_node+1];
            assign pick_wrap[pick_node] = choose_left ? pick_wrap[2*pick_node] : pick_wrap[2*pick_node+1];
            // Carry the address alongside the winning age/slot. The cache
            // need not wait for a second binary-indexed read after selection.
            assign pick_addr[pick_node] = choose_left ? pick_addr[2*pick_node] : pick_addr[2*pick_node+1];
        end
        // Each byte independently selects the youngest overlapping older
        // store. Static reads replace repeated head-relative array muxes.
        for (forward_byte = 0; forward_byte < 4; forward_byte = forward_byte + 1) begin : g_forward
            wire byte_valid [1:2*LSQ_ENTRIES-1];
            wire [SLOT_WIDTH-1:0] byte_age [1:2*LSQ_ENTRIES-1];
            wire byte_wrap [1:2*LSQ_ENTRIES-1];
            wire [7:0] byte_data [1:2*LSQ_ENTRIES-1];
            for (forward_slot = 0; forward_slot < LSQ_ENTRIES; forward_slot = forward_slot + 1) begin : g_leaf
                assign byte_valid[LSQ_ENTRIES+forward_slot] = store_overlap[forward_slot][forward_byte];
                assign byte_age[LSQ_ENTRIES+forward_slot] = entry_age[forward_slot];
                assign byte_wrap[LSQ_ENTRIES+forward_slot] = circular_wrap_views[forward_slot*8+1+forward_byte];
                assign byte_data[LSQ_ENTRIES+forward_slot] = store_forward_data[forward_slot][forward_byte*8 +: 8];
            end
            for (forward_node = 1; forward_node < LSQ_ENTRIES; forward_node = forward_node + 1) begin : g_node
                wire choose_left = byte_valid[2*forward_node] &&
                    (!byte_valid[2*forward_node+1] ||
                     (CIRCULAR_ORDER_POWER2 ? (byte_wrap[2*forward_node] && !byte_wrap[2*forward_node+1]) :
                      (byte_age[2*forward_node] >= byte_age[2*forward_node+1])));
                assign byte_valid[forward_node] = byte_valid[2*forward_node] || byte_valid[2*forward_node+1];
                assign byte_age[forward_node] = choose_left ? byte_age[2*forward_node] : byte_age[2*forward_node+1];
                assign byte_wrap[forward_node] = choose_left ? byte_wrap[2*forward_node] : byte_wrap[2*forward_node+1];
                assign byte_data[forward_node] = choose_left ? byte_data[2*forward_node] : byte_data[2*forward_node+1];
            end
            assign tree_forward_mask[forward_byte] = byte_valid[1];
            assign tree_forward_data[forward_byte*8 +: 8] = byte_valid[1] ? byte_data[1] : 8'b0;
        end
    endgenerate

    initial begin
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid LSQ BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if ((LSQ_ENTRIES < 1) || ((LSQ_ENTRIES & (LSQ_ENTRIES - 1)) != 0)) begin
            $display("ERROR: invalid LSQ_ENTRIES=%0d; expected a power of two", LSQ_ENTRIES);
            $finish;
        end
        if (TAG_WIDTH < SLOT_WIDTH + 3) begin
            $display("ERROR: LSQ TAG_WIDTH=%0d is too narrow for LSQ_ENTRIES=%0d", TAG_WIDTH, LSQ_ENTRIES);
            $finish;
        end
    end

    always @* begin
        // Unconditional defaults: these temporaries are written only inside
        // nested conditions below, and a conditional-only write would infer
        // latches (thousands of proc_dlatch candidates in synthesis).
        target_mask = 4'b0;
        fwd_mask = 4'b0;
        fwd_data = 32'b0;
        alloc_slot = 0;
        free_count_calc = LSQ_ENTRIES - occupancy_reg;
        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        alloc_lsq_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        alloc_count_calc = 0;
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            // Memory operations are a sparse subset of the dispatch bundle.
            // Compact valid memory lanes into consecutive LSQ slots while
            // retaining each lane's ROB tag and payload.
            if (alloc_valid_i[lane] &&
                (alloc_is_load_i[lane] || alloc_is_store_i[lane]) &&
                (alloc_count_calc < free_count_calc)) begin
                alloc_fire_o[lane] = !flush_i;
                alloc_slot = tail_reg + alloc_count_calc;
                if (alloc_slot >= LSQ_ENTRIES) alloc_slot = alloc_slot - LSQ_ENTRIES;
                alloc_lsq_tag_o[(lane*TAG_WIDTH) +: TAG_WIDTH] =
                    make_lsq_tag(alloc_slot, generation_next_mem[alloc_slot]);
                alloc_count_calc = alloc_count_calc + 1;
                alloc_count_o = alloc_count_calc[ALLOC_COUNT_WIDTH-1:0];
            end
        end

        // Preserve lowest physical-slot matching priority, with a balanced selector.
        commit_slot_found=!flush_i && occupancy_reg!=0 && commit_valid_tree[1];
        store_commit_ready_o=commit_slot_found;
        commit_slot_select=commit_slot_found?commit_slot_tree[1]:0;

        // The eligibility bits above feed the balanced oldest-first tree.
        candidate_found = (REQUEST_PIPELINE!=0)?selection_live:pick_valid[1];
        candidate = candidate_found ? selected_slot : 0;
        candidate_age = candidate_found ? selected_age : LSQ_ENTRIES + 1;

        dcache_req_valid_o = 1'b0;
        dcache_req_is_load_o = 1'b0;
        dcache_req_is_store_o = 1'b0;
        // Payload is meaningful only with valid. Expose the selected address
        // directly so forwarding and recovery gates do not sit on the cache
        // index path.
        dcache_req_addr_o = selected_addr;
        dcache_req_size_o = 2'b0;
        dcache_req_unsigned_o = 1'b0;
        dcache_req_mask_o = 16'b0;
        // Wide request data is routed by the bounded combinational unit below.
        dcache_req_rob_tag_o = {ROB_TAG_WIDTH{1'b0}};
        dcache_req_lsq_tag_o = {TAG_WIDTH{1'b0}};
        request_fire = 1'b0;
        // Recovery updates retained responses but cannot record a new request.
        // Do not let the cache (or request register) accept an untracked send.
        if (!flush_i && !recovery_valid_i && candidate_found && !candidate_wait) begin
            if (selected_load) begin
                target_mask = access_mask(selected_size);
                fwd_mask = (REQUEST_PIPELINE!=0 && forwarding_hold_valid)?forwarding_hold_mask:tree_forward_mask;
                fwd_data = (REQUEST_PIPELINE!=0 && forwarding_hold_valid)?forwarding_hold_data:tree_forward_data;
                if ((fwd_mask & target_mask) != target_mask) begin
                    dcache_req_valid_o = 1'b1;
                    dcache_req_is_load_o = 1'b1;
                    dcache_req_size_o = selected_size;
                    dcache_req_unsigned_o = selected_unsigned;
                    dcache_req_mask_o = line_mask_from_relative(target_mask & ~fwd_mask,
                                                                 selected_addr);
                    // Forwarded request bytes use the shared insertion unit.
                    dcache_req_rob_tag_o = selected_rob_tag;
                    dcache_req_lsq_tag_o = selected_lsq_tag;
                    request_fire = dcache_req_ready_i;
                end
            end else begin
                dcache_req_valid_o = 1'b1;
                dcache_req_is_store_o = 1'b1;
                dcache_req_size_o = selected_size;
                dcache_req_unsigned_o = 1'b0;
                dcache_req_mask_o = line_mask_from_relative(selected_store_mask, selected_addr);
                // Store request bytes use the shared insertion unit.
                dcache_req_rob_tag_o = selected_rob_tag;
                dcache_req_lsq_tag_o = selected_lsq_tag;
                request_fire = dcache_req_ready_i;
            end
        end

        // A fully covered load never touches the cache.  It becomes a
        // completion at the next edge, preserving the same handshake timing.
        response_match = 1'b0;
        response_slot = 0;
        for (i = 0; i < LSQ_ENTRIES; i = i + 1)
            if (dcache_resp_valid_i && tag_matches_slot(dcache_resp_lsq_tag_i, i) && response_wait_mem[i]) begin
                response_match = 1'b1;
                response_slot = i;
            end
        // Always drain a cache response.  A generation mismatch is a killed
        // wrong-path request; a matching live response is captured below.
        dcache_resp_ready_o = 1'b1;
        response_fire = dcache_resp_valid_i && response_match;
    end


    // The old request-admission gate fed ~151 mapped pins and also happened
    // to be named as AXI enabled_words bit0 after flattening. Keep admission
    // itself unchanged. Select one relative32-bit source, then insert it;
    // qualify AFTER insertion so late request-valid never traverses shifts.
    wire [1:0] request_source_views;
    wire [7:0] request_data_views;
    wire [31:0] request_relative_data;
    wire [127:0] request_inserted_data;
    rv32_frequency_control_tree #(.LEAVES(2)) request_source_tree (
        .signal_i(selected_load),.views_o(request_source_views));
    rv32_frequency_control_tree #(.LEAVES(8)) request_data_tree (
        .signal_i(dcache_req_valid_o),.views_o(request_data_views));
    generate for(genvar request_source_word=0;request_source_word<2;request_source_word=request_source_word+1) begin:g_request_source_word
        assign request_relative_data[request_source_word*16 +: 16]=request_source_views[request_source_word]?
            fwd_data[request_source_word*16 +: 16]:selected_store_data[request_source_word*16 +: 16];
    end endgenerate
    rv32_frequency_line_insert32 request_insertion (
        .value_i(request_relative_data),.offset_i(selected_addr[3:0]),.line_o(request_inserted_data));
    generate for(genvar request_line_word=0;request_line_word<8;request_line_word=request_line_word+1) begin:g_request_line_word
        assign dcache_req_wdata_o[request_line_word*16 +: 16]=
            {16{request_data_views[request_line_word]}} & request_inserted_data[request_line_word*16 +: 16];
    end endgenerate

    // Move the existing backend LSQ_ENTRIES x PHYS_ADDR_WIDTH map into its
    // transaction owner. These are the SAME unreset allocation payload bits.
    // A valid report selects phys/value/full ROB+LSQ identity in parallel;
    // it no longer selects a tag then uses that tag for a second table read.
    localparam integer PHYS_MAP_DOMAINS=(LSQ_ENTRIES+3)/4;
    wire [LSQ_ENTRIES*PHYS_ADDR_WIDTH-1:0] physical_destinations;
    wire [PHYS_MAP_DOMAINS*BE_WIDTH-1:0] physical_alloc_views;
    wire [PHYS_MAP_DOMAINS*BE_WIDTH*SLOT_WIDTH-1:0] physical_slot_views;
    wire [PHYS_MAP_DOMAINS*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] physical_value_views;
    wire [BE_WIDTH*SLOT_WIDTH-1:0] physical_alloc_slots;
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(PHYS_MAP_DOMAINS)) physical_alloc_tree (
        .signal_i(alloc_fire_o & {BE_WIDTH{!reset_i}}),.views_o(physical_alloc_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*SLOT_WIDTH),.LEAVES(PHYS_MAP_DOMAINS)) physical_slot_tree (
        .signal_i(physical_alloc_slots),.views_o(physical_slot_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(PHYS_MAP_DOMAINS)) physical_value_tree (
        .signal_i(alloc_phys_rd_i),.views_o(physical_value_views));
    generate
        for(genvar physical_lane=0;physical_lane<BE_WIDTH;physical_lane=physical_lane+1) begin:g_physical_alloc_slot
            assign physical_alloc_slots[physical_lane*SLOT_WIDTH +: SLOT_WIDTH]=
                alloc_lsq_tag_o[physical_lane*TAG_WIDTH+TAG_SLOT_LSB +: SLOT_WIDTH];
        end
        for(genvar physical_row=0;physical_row<LSQ_ENTRIES;physical_row=physical_row+1) begin:g_physical_destination_row
            localparam integer DOMAIN=physical_row/4;
            wire [BE_WIDTH-1:0] row_match_mask;
            wire row_write;
            wire [PHYS_ADDR_WIDTH-1:0] next_phys;
            for(genvar physical_lane=0;physical_lane<BE_WIDTH;physical_lane=physical_lane+1) begin:g_match
                assign row_match_mask[physical_lane]=physical_alloc_views[DOMAIN*BE_WIDTH+physical_lane] &&
                    physical_slot_views[(DOMAIN*BE_WIDTH+physical_lane)*SLOT_WIDTH +: SLOT_WIDTH]==physical_row;
            end
            rv32_frequency_event_select #(.WIDTH(PHYS_ADDR_WIDTH),.EVENTS(BE_WIDTH)) selector (
                .events_i(row_match_mask),
                .values_i(physical_value_views[DOMAIN*BE_WIDTH*PHYS_ADDR_WIDTH +: BE_WIDTH*PHYS_ADDR_WIDTH]),
                .write_o(row_write),.value_o(next_phys));
            rv32_frequency_word_bank #(.WIDTH(PHYS_ADDR_WIDTH)) owner (
                .clk_i(clk_i),.write_i(row_write),.data_i(next_phys),
                .data_o(physical_destinations[physical_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]));
        end
    endgenerate

    // Load reporting follows queue age; store admission preserves the former
    // lowest physical-slot priority. Neither selection is a serial scan.
    localparam integer REPORT_ROWS=(LSQ_ENTRIES<=1)?1:(1<<$clog2(LSQ_ENTRIES));
    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+34;
    localparam integer ACK_WIDTH=ROB_TAG_WIDTH+TAG_WIDTH+1;
    localparam integer REPORT_WORDS=(REPORT_WIDTH+15)/16;
    localparam integer ACK_WORDS=(ACK_WIDTH+15)/16;
    wire report_valid_tree [1:2*REPORT_ROWS-1];
    wire [SLOT_WIDTH-1:0] report_slot_tree [1:2*REPORT_ROWS-1];
    wire report_wrap_tree [1:2*REPORT_ROWS-1];
    wire commit_valid_tree [1:2*REPORT_ROWS-1];
    wire [SLOT_WIDTH-1:0] commit_slot_tree [1:2*REPORT_ROWS-1];
    wire [REPORT_WIDTH-1:0] report_payload_tree [1:2*REPORT_ROWS-1];
    wire [ACK_WIDTH-1:0] ack_payload_tree [1:2*REPORT_ROWS-1];
    wire ack_valid_tree [1:2*REPORT_ROWS-1];
    genvar report_row,report_word,report_node;
    generate
        for(report_row=0;report_row<REPORT_ROWS;report_row=report_row+1) begin:g_report_row
            if(report_row<LSQ_ENTRIES) begin:g_present
                wire [REPORT_WORDS-1:0] report_select;
                wire [ACK_WORDS-1:0] ack_select;
                wire [REPORT_WIDTH-1:0] report_payload={
                    !retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};
                wire [ACK_WIDTH-1:0] ack_payload={store_ack_error_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};
                assign report_valid_tree[REPORT_ROWS+report_row]=entry_age[report_row]<occupancy_reg &&
                    valid_mem[report_row] && load_mem[report_row] && complete_mem[report_row] && !load_reported_mem[report_row];
                assign report_slot_tree[REPORT_ROWS+report_row]=report_row;
                assign report_wrap_tree[REPORT_ROWS+report_row]=circular_wrap_views[report_row*8+5];
                assign commit_valid_tree[REPORT_ROWS+report_row]=valid_mem[report_row] && store_mem[report_row] &&
                    addr_ready_mem[report_row] && data_ready_mem[report_row] && !store_commit_mem[report_row] &&
                    rob_tag_mem[report_row]==store_commit_rob_tag_i;
                assign commit_slot_tree[REPORT_ROWS+report_row]=report_row;
                assign ack_valid_tree[REPORT_ROWS+report_row]=occupancy_reg!=0 && head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH]==report_row &&
                    valid_mem[report_row] && store_mem[report_row] && store_ack_mem[report_row];
                rv32_frequency_control_tree #(.LEAVES(REPORT_WORDS)) report_selection_tree (
                    .signal_i(report_valid_tree[1] && report_slot_tree[1]==report_row),.views_o(report_select));
                rv32_frequency_control_tree #(.LEAVES(ACK_WORDS)) ack_selection_tree (
                    .signal_i(ack_valid_tree[REPORT_ROWS+report_row]),.views_o(ack_select));
                for(report_word=0;report_word<REPORT_WORDS;report_word=report_word+1) begin:g_result_word
                    localparam integer LOW=report_word*16;
                    localparam integer BITS=REPORT_WIDTH-LOW>=16?16:REPORT_WIDTH-LOW;
                    assign report_payload_tree[REPORT_ROWS+report_row][LOW +: BITS]=
                        {BITS{report_select[report_word]}} & report_payload[LOW +: BITS];
                end
                for(report_word=0;report_word<ACK_WORDS;report_word=report_word+1) begin:g_ack_word
                    localparam integer LOW=report_word*16;
                    localparam integer BITS=ACK_WIDTH-LOW>=16?16:ACK_WIDTH-LOW;
                    assign ack_payload_tree[REPORT_ROWS+report_row][LOW +: BITS]=
                        {BITS{ack_select[report_word]}} & ack_payload[LOW +: BITS];
                end
            end else begin:g_padding
                assign report_valid_tree[REPORT_ROWS+report_row]=0;
                assign report_slot_tree[REPORT_ROWS+report_row]=0;
                assign report_wrap_tree[REPORT_ROWS+report_row]=0;
                assign commit_valid_tree[REPORT_ROWS+report_row]=0;
                assign commit_slot_tree[REPORT_ROWS+report_row]=0;
                assign report_payload_tree[REPORT_ROWS+report_row]=0;
                assign ack_payload_tree[REPORT_ROWS+report_row]=0;
                assign ack_valid_tree[REPORT_ROWS+report_row]=0;
            end
        end
        for(report_node=1;report_node<REPORT_ROWS;report_node=report_node+1) begin:g_report_merge
            wire choose_left=report_valid_tree[2*report_node] &&
                (!report_valid_tree[2*report_node+1] ||
                 !report_wrap_tree[2*report_node] || report_wrap_tree[2*report_node+1]);
            assign report_valid_tree[report_node]=report_valid_tree[2*report_node] || report_valid_tree[2*report_node+1];
            assign report_slot_tree[report_node]=choose_left?report_slot_tree[2*report_node]:report_slot_tree[2*report_node+1];
            assign report_wrap_tree[report_node]=choose_left?report_wrap_tree[2*report_node]:report_wrap_tree[2*report_node+1];
            assign commit_valid_tree[report_node]=commit_valid_tree[2*report_node] || commit_valid_tree[2*report_node+1];
            assign commit_slot_tree[report_node]=commit_valid_tree[2*report_node]?
                commit_slot_tree[2*report_node]:commit_slot_tree[2*report_node+1];
            assign report_payload_tree[report_node]=report_payload_tree[2*report_node] | report_payload_tree[2*report_node+1];
            assign ack_payload_tree[report_node]=ack_payload_tree[2*report_node] | ack_payload_tree[2*report_node+1];
            assign ack_valid_tree[report_node]=ack_valid_tree[2*report_node] || ack_valid_tree[2*report_node+1];
        end
    endgenerate

    always @* begin
        complete_slot_found=report_valid_tree[1];
        complete_slot_select=complete_slot_found?report_slot_tree[1]:head_reg;
        load_complete_valid_o=complete_slot_found;
        {load_complete_unretired_o,load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];
        store_ack_valid_o=ack_valid_tree[1];
        {store_ack_error_o,store_ack_lsq_tag_o,store_ack_rob_tag_o}=ack_payload_tree[1];
    end


    // Wide payload fields have no reset state. Their old write sequence is
    // expressed as independent local events; scalar metadata remains separate.
    localparam integer ADDRESS_EVENTS=1+2*BE_WIDTH;
    localparam integer DATA_EVENTS=3*BE_WIDTH;
    localparam integer RESULT_EVENTS=2+BE_WIDTH;
    localparam integer FORWARD_EVENTS=1+BE_WIDTH;
    wire [3*LSQ_ENTRIES-1:0] payload_modes;
    wire [SLOT_WIDTH-1:0] payload_alloc_slot [0:BE_WIDTH-1];
    // Returning-cache identity previously selected separate dynamic arrays
    // with shared, wide decoded drivers. One static packet query reads the
    // exact same row; only the low address nibble is needed for extraction.
    localparam integer RESPONSE_QUERY_WIDTH=ROB_TAG_WIDTH+43;
    wire [LSQ_ENTRIES*RESPONSE_QUERY_WIDTH-1:0] response_query_rows;
    wire [3:0] response_query_offset,response_query_mask;
    wire [31:0] response_query_forward;
    wire [1:0] response_query_size;
    wire response_query_unsigned;
    wire [ROB_TAG_WIDTH-1:0] response_query_rob_tag;
    rv32_frequency_array_read #(.WIDTH(RESPONSE_QUERY_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) response_query_read (
        .rows_i(response_query_rows),.index_i(response_slot[SLOT_WIDTH-1:0]),
        .value_o({response_query_rob_tag,response_query_offset,response_query_forward,
                  response_query_mask,response_query_size,response_query_unsigned}));
    generate for(genvar response_row=0;response_row<LSQ_ENTRIES;response_row=response_row+1) begin:g_response_query
        assign response_query_rows[response_row*RESPONSE_QUERY_WIDTH +: RESPONSE_QUERY_WIDTH]={
            rob_tag_mem[response_row],addr_mem[response_row][3:0],forward_data_mem[response_row],
            forward_mask_mem[response_row],size_mem[response_row],unsigned_mem[response_row]};
    end endgenerate
    wire [LSQ_ENTRIES*SLOT_WIDTH-1:0] response_slot_views;
    rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(LSQ_ENTRIES)) response_slot_tree (
        .signal_i(response_slot[SLOT_WIDTH-1:0]),.views_o(response_slot_views));
    wire [31:0] response_line_word,payload_response_word;
    rv32_frequency_line_extract32 response_extract (
        .line_i(dcache_resp_line_data_i),.offset_i(response_query_offset),
        .size_i(2'd2),.unsigned_i(1'b1),.value_o(response_line_word));
    wire [1:0] response_line_views;
    rv32_frequency_control_tree #(.LEAVES(2)) response_line_tree (
        .signal_i(dcache_resp_line_valid_i),.views_o(response_line_views));
    generate for(genvar response_word_id=0;response_word_id<2;response_word_id=response_word_id+1) begin:g_response_word
        assign payload_response_word[response_word_id*16 +: 16]=response_line_views[response_word_id]?
            response_line_word[response_word_id*16 +: 16]:dcache_resp_word_data_i[response_word_id*16 +: 16];
    end endgenerate
    wire [31:0] payload_response_merge=
        (response_query_forward & expand_word_bytes(response_query_mask)) |
        (payload_response_word & ~expand_word_bytes(response_query_mask));
    wire [31:0] payload_response_value=format_relative_value(
        payload_response_merge,response_query_size,response_query_unsigned);
    wire [31:0] payload_forward_value=format_relative_value(fwd_data,selected_size,selected_unsigned);
    function [RECOVERY_ARITH_WIDTH-1:0] payload_recovery_age;
        input [ROB_TAG_WIDTH-1:0] tag;
        reg [RECOVERY_ARITH_WIDTH-1:0] difference;
        begin
            difference=tag[3 +: ROB_SLOT_WIDTH]-recovery_head_i;
            if(((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && difference[RECOVERY_ARITH_WIDTH-1])
                difference=difference+ROB_ENTRIES;
            payload_recovery_age=difference;
        end
    endfunction
    wire [RECOVERY_ARITH_WIDTH-1:0] payload_branch_age=payload_recovery_age(recovery_tag_i);
    localparam integer OWNER_RECOVERY_WIDTH=ROB_SLOT_WIDTH+RECOVERY_ARITH_WIDTH+16;
    wire [LSQ_ENTRIES*OWNER_RECOVERY_WIDTH-1:0] owner_recovery_views;
    rv32_frequency_control_tree #(.WIDTH(OWNER_RECOVERY_WIDTH),.LEAVES(LSQ_ENTRIES)) owner_recovery_tree (
        .signal_i({recovery_head_i,payload_branch_age,recovery_occupancy_i}),.views_o(owner_recovery_views));
    function [RECOVERY_ARITH_WIDTH-1:0] payload_owner_recovery_age;
        input [ROB_TAG_WIDTH-1:0] tag;
        input [ROB_SLOT_WIDTH-1:0] local_head;
        reg [RECOVERY_ARITH_WIDTH-1:0] difference;
        begin
            difference=tag[3 +: ROB_SLOT_WIDTH]-local_head;
            if(((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && difference[RECOVERY_ARITH_WIDTH-1])
                difference=difference+ROB_ENTRIES;
            payload_owner_recovery_age=difference;
        end
    endfunction
    // Count retained live rows and locate the oldest killed row in parallel.
    // Four merge levels replace sixteen conditional integer accumulations
    // for the current queue, on the same recovery edge and with no new FF.
    wire [COUNT_WIDTH-1:0] recovery_keep_tree [1:2*LSQ_ENTRIES-1];
    wire recovery_kill_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_age_tree [1:2*LSQ_ENTRIES-1];
    wire recovery_kill_wrap_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_slot_tree [1:2*LSQ_ENTRIES-1];
    generate for(genvar trim_node=1;trim_node<LSQ_ENTRIES;trim_node=trim_node+1) begin:g_recovery_trim
        wire choose_left=recovery_kill_tree[2*trim_node] &&
            (!recovery_kill_tree[2*trim_node+1] ||
             (CIRCULAR_ORDER_POWER2 ? (!recovery_kill_wrap_tree[2*trim_node] || recovery_kill_wrap_tree[2*trim_node+1]) :
              recovery_kill_age_tree[2*trim_node]<=recovery_kill_age_tree[2*trim_node+1]));
        assign recovery_keep_tree[trim_node]=recovery_keep_tree[2*trim_node]+recovery_keep_tree[2*trim_node+1];
        assign recovery_kill_tree[trim_node]=recovery_kill_tree[2*trim_node] || recovery_kill_tree[2*trim_node+1];
        assign recovery_kill_age_tree[trim_node]=choose_left?recovery_kill_age_tree[2*trim_node]:recovery_kill_age_tree[2*trim_node+1];
        assign recovery_kill_wrap_tree[trim_node]=choose_left?recovery_kill_wrap_tree[2*trim_node]:recovery_kill_wrap_tree[2*trim_node+1];
        assign recovery_kill_slot_tree[trim_node]=choose_left?recovery_kill_slot_tree[2*trim_node]:recovery_kill_slot_tree[2*trim_node+1];
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(LSQ_ENTRIES)) payload_mode_tree (
        .signal_i({recovery_valid_i,flush_i,reset_i}),.views_o(payload_modes));
    genvar payload_row,payload_lane;
    generate
        for(payload_lane=0;payload_lane<BE_WIDTH;payload_lane=payload_lane+1) begin:g_payload_allocation
            wire [31:0] offset=tail_reg+alloc_count_before_lane(payload_lane,alloc_fire_o);
            assign payload_alloc_slot[payload_lane]=(offset>=LSQ_ENTRIES)?offset-LSQ_ENTRIES:offset;
        end
        for(payload_row=0;payload_row<LSQ_ENTRIES;payload_row=payload_row+1) begin:g_payload_row
            wire enabled=!payload_modes[payload_row*3] && !payload_modes[payload_row*3+1];
            wire recovery=payload_modes[payload_row*3+2];
            wire normal=enabled && !recovery;
            wire [BE_WIDTH-1:0] allocations;
            wire [ADDRESS_EVENTS-1:0] address_events;
            wire [ADDRESS_EVENTS*32-1:0] address_values;
            wire [DATA_EVENTS-1:0] data_events;
            wire [DATA_EVENTS*32-1:0] data_values;
            wire [RESULT_EVENTS-1:0] result_events;
            wire [RESULT_EVENTS*32-1:0] result_values;
            wire [FORWARD_EVENTS-1:0] forward_events;
            wire [FORWARD_EVENTS*32-1:0] forward_values;
            wire [BE_WIDTH*ROB_TAG_WIDTH-1:0] rob_tag_values;
            wire [31:0] address_value,data_value,result_value,forward_value;
            wire [ROB_TAG_WIDTH-1:0] rob_tag_value;
            wire address_write,data_write,result_write,forward_write,rob_tag_write;
            wire early_event=normal && (STORE_ADDRESS_PROBE!=0) && early_addr_valid_i &&
                tag_matches_slot(early_addr_tag_i,payload_row) && store_mem[payload_row] &&
                !addr_ready_mem[payload_row] && !request_sent_mem[payload_row] && !complete_mem[payload_row];
            assign address_events[0]=early_event;
            assign address_values[0 +: 32]=early_addr_i;
            assign result_events[0]=normal && candidate_found && candidate==payload_row &&
                load_mem[payload_row] && !request_sent_mem[payload_row] && !complete_mem[payload_row] &&
                ((fwd_mask & target_mask)==target_mask);
            assign result_values[0 +: 32]=payload_forward_value;
            wire [ROB_SLOT_WIDTH-1:0] local_recovery_head;
            wire [RECOVERY_ARITH_WIDTH-1:0] local_branch_age;
            wire [15:0] local_recovery_occupancy;
            assign {local_recovery_head,local_branch_age,local_recovery_occupancy}=
                owner_recovery_views[payload_row*OWNER_RECOVERY_WIDTH +: OWNER_RECOVERY_WIDTH];
            wire [RECOVERY_ARITH_WIDTH-1:0] row_age=payload_owner_recovery_age(rob_tag_mem[payload_row],local_recovery_head);
            assign result_events[1]=enabled && response_fire && response_slot_views[payload_row*SLOT_WIDTH +: SLOT_WIDTH]==payload_row &&
                (!recovery || !(row_age>local_branch_age && row_age<local_recovery_occupancy));
            assign result_values[32 +: 32]=payload_response_value;
            assign forward_events[0]=normal && request_fire && candidate==payload_row && load_mem[payload_row];
            assign forward_values[0 +: 32]=fwd_data;
            for(payload_lane=0;payload_lane<BE_WIDTH;payload_lane=payload_lane+1) begin:g_lane
                assign allocations[payload_lane]=normal && alloc_fire_o[payload_lane] &&
                    payload_alloc_slot[payload_lane]==payload_row;
                assign address_events[1+payload_lane]=enabled && addr_update_valid_i[payload_lane] &&
                    tag_matches_slot(addr_update_tag_i[payload_lane*TAG_WIDTH +: TAG_WIDTH],payload_row);
                assign address_values[(1+payload_lane)*32 +: 32]=addr_update_i[payload_lane*32 +: 32];
                assign address_events[1+BE_WIDTH+payload_lane]=allocations[payload_lane];
                assign address_values[(1+BE_WIDTH+payload_lane)*32 +: 32]=alloc_addr_i[payload_lane*32 +: 32];
                assign data_events[2*payload_lane]=enabled && data_update_valid_i[payload_lane] &&
                    tag_matches_slot(data_update_tag_i[payload_lane*TAG_WIDTH +: TAG_WIDTH],payload_row);
                assign data_values[(2*payload_lane)*32 +: 32]=data_update_i[payload_lane*32 +: 32];
                assign data_events[2*payload_lane+1]=enabled && wakeup_valid_i[payload_lane] &&
                    tag_matches_slot(wakeup_tag_i[payload_lane*TAG_WIDTH +: TAG_WIDTH],payload_row);
                assign data_values[(2*payload_lane+1)*32 +: 32]=wakeup_value_i[payload_lane*32 +: 32];
                assign data_events[2*BE_WIDTH+payload_lane]=allocations[payload_lane];
                assign data_values[(2*BE_WIDTH+payload_lane)*32 +: 32]=alloc_store_data_i[payload_lane*32 +: 32];
                assign result_events[2+payload_lane]=allocations[payload_lane];
                assign result_values[(2+payload_lane)*32 +: 32]=0;
                assign forward_events[1+payload_lane]=allocations[payload_lane];
                assign forward_values[(1+payload_lane)*32 +: 32]=0;
                assign rob_tag_values[payload_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]=alloc_rob_tag_i[payload_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH];
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(ADDRESS_EVENTS)) address_selector (
                .events_i(address_events),.values_i(address_values),.write_o(address_write),.value_o(address_value));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(DATA_EVENTS)) data_selector (
                .events_i(data_events),.values_i(data_values),.write_o(data_write),.value_o(data_value));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RESULT_EVENTS)) result_selector (
                .events_i(result_events),.values_i(result_values),.write_o(result_write),.value_o(result_value));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FORWARD_EVENTS)) forward_selector (
                .events_i(forward_events),.values_i(forward_values),.write_o(forward_write),.value_o(forward_value));
            rv32_frequency_event_select #(.WIDTH(ROB_TAG_WIDTH),.EVENTS(BE_WIDTH)) tag_selector (
                .events_i(allocations),.values_i(rob_tag_values),.write_o(rob_tag_write),.value_o(rob_tag_value));
            always @* begin
                addr_mem_write_data[payload_row]=address_value;
                addr_mem_write_enable[payload_row]=address_write;
                data_mem_write_data[payload_row]=data_value;
                data_mem_write_enable[payload_row]=data_write;
                complete_value_mem_write_data[payload_row]=result_value;
                complete_value_mem_write_enable[payload_row]=result_write;
                forward_data_mem_write_data[payload_row]=forward_value;
                forward_data_mem_write_enable[payload_row]=forward_write;
                rob_tag_mem_write_data[payload_row]=rob_tag_value;
                rob_tag_mem_write_enable[payload_row]=rob_tag_write;
            end
        end
    endgenerate

    // Three independent metadata groups per physical LSQ row. Local mode
    // leaves cannot collapse into one reset/recovery driver across all rows.
    localparam integer META_LSQ_AGE_WIDTH=((LSQ_ENTRIES & (LSQ_ENTRIES-1))==0)?SLOT_WIDTH:SLOT_WIDTH+1;
    wire [7*LSQ_ENTRIES-1:0] metadata_events;
    wire metadata_pop=(occupancy_reg!=0) && head_valid &&
        ((head_load && head_complete &&
          (head_reported || (load_complete_valid_o && load_complete_ready_i && complete_slot_select==head_reg))) ||
         (head_store && head_ack && store_ack_ready_i));
    wire metadata_forward=candidate_found && candidate_load &&
        !candidate_sent && !candidate_complete && ((fwd_mask & target_mask)==target_mask);
    rv32_frequency_control_tree #(.WIDTH(7),.LEAVES(LSQ_ENTRIES)) metadata_event_tree (
        .signal_i({metadata_pop,metadata_forward,request_fire,response_fire,dcache_store_ack_valid_i,
                   load_complete_valid_o && load_complete_ready_i,store_commit_valid_i && store_commit_ready_o}),
        .views_o(metadata_events));
    genvar metadata_row,metadata_lane;
    generate for(metadata_row=0;metadata_row<LSQ_ENTRIES;metadata_row=metadata_row+1) begin:g_metadata_row
        wire [8:0] modes;
        rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(3)) mode_tree (
            .signal_i(payload_modes[metadata_row*3 +: 3]),.views_o(modes));
        wire [BE_WIDTH-1:0] alloc_matches,addr_matches,data_matches,wake_matches,retire_matches;
        wire [BE_WIDTH*11-1:0] alloc_values;
        wire allocated;
        wire [10:0] allocation;
        for(metadata_lane=0;metadata_lane<BE_WIDTH;metadata_lane=metadata_lane+1) begin:g_match
            assign alloc_matches[metadata_lane]=alloc_fire_o[metadata_lane] &&
                payload_alloc_slot[metadata_lane]==metadata_row;
            assign alloc_values[metadata_lane*11 +: 11]={
                alloc_store_mask_i[metadata_lane*4 +: 4],
                alloc_data_valid_i[metadata_lane] || alloc_is_load_i[metadata_lane],
                alloc_addr_valid_i[metadata_lane],alloc_unsigned_i[metadata_lane],
                alloc_size_i[metadata_lane*2 +: 2],alloc_is_store_i[metadata_lane],alloc_is_load_i[metadata_lane]};
            assign addr_matches[metadata_lane]=addr_update_valid_i[metadata_lane] &&
                tag_matches_slot(addr_update_tag_i[metadata_lane*TAG_WIDTH +: TAG_WIDTH],metadata_row);
            assign data_matches[metadata_lane]=data_update_valid_i[metadata_lane] &&
                tag_matches_slot(data_update_tag_i[metadata_lane*TAG_WIDTH +: TAG_WIDTH],metadata_row);
            assign wake_matches[metadata_lane]=wakeup_valid_i[metadata_lane] &&
                tag_matches_slot(wakeup_tag_i[metadata_lane*TAG_WIDTH +: TAG_WIDTH],metadata_row);
            assign retire_matches[metadata_lane]=retire_valid_i[metadata_lane] && valid_mem[metadata_row] &&
                load_mem[metadata_row] && rob_tag_mem[metadata_row]==retire_rob_tag_i[metadata_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH];
        end
        rv32_frequency_event_select #(.WIDTH(11),.EVENTS(BE_WIDTH)) allocation_selector (
            .events_i(alloc_matches),.values_i(alloc_values),.write_o(allocated),.value_o(allocation));
        wire [GENERATION_WIDTH-1:0] allocated_generation=(generation_next_mem[metadata_row]==0)?
            {{(GENERATION_WIDTH-1){1'b0}},1'b1}:generation_next_mem[metadata_row];
        wire [META_LSQ_AGE_WIDTH-1:0] lsq_difference=metadata_row-head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH];
        wire [META_LSQ_AGE_WIDTH-1:0] lsq_age=
            (((LSQ_ENTRIES & (LSQ_ENTRIES-1))!=0) && lsq_difference[META_LSQ_AGE_WIDTH-1])?
            lsq_difference+LSQ_ENTRIES:lsq_difference;
        wire [ROB_SLOT_WIDTH-1:0] local_recovery_head;
        wire [RECOVERY_ARITH_WIDTH-1:0] local_branch_age;
        wire [15:0] local_recovery_occupancy;
        assign {local_recovery_head,local_branch_age,local_recovery_occupancy}=
            owner_recovery_views[metadata_row*OWNER_RECOVERY_WIDTH +: OWNER_RECOVERY_WIDTH];
        wire [RECOVERY_ARITH_WIDTH-1:0] row_rob_age=payload_owner_recovery_age(rob_tag_mem[metadata_row],local_recovery_head);
        wire kill=lsq_age<occupancy_reg && valid_mem[metadata_row] &&
            !(store_mem[metadata_row] && store_commit_mem[metadata_row]) &&
            !(load_mem[metadata_row] && retired_mem[metadata_row]) &&
            row_rob_age>local_branch_age && row_rob_age<local_recovery_occupancy;
        wire response_allowed=!(row_rob_age>local_branch_age && row_rob_age<local_recovery_occupancy);
        assign recovery_keep_tree[LSQ_ENTRIES+metadata_row]=
            (lsq_age<occupancy_reg && valid_mem[metadata_row] && !kill)?1:0;
        assign recovery_kill_tree[LSQ_ENTRIES+metadata_row]=kill;
        assign recovery_kill_age_tree[LSQ_ENTRIES+metadata_row]=lsq_age;
        assign recovery_kill_wrap_tree[LSQ_ENTRIES+metadata_row]=circular_wrap_views[metadata_row*8+6];
        assign recovery_kill_slot_tree[LSQ_ENTRIES+metadata_row]=metadata_row;
        wire commit_event=metadata_events[metadata_row*7] && commit_slot_select==metadata_row;
        wire report_event=metadata_events[metadata_row*7+1] && complete_slot_select==metadata_row;
        wire ack_event=metadata_events[metadata_row*7+2] &&
            tag_matches_slot(dcache_store_ack_lsq_tag_i,metadata_row) &&
            request_sent_mem[metadata_row] && response_wait_mem[metadata_row];
        wire response_event=metadata_events[metadata_row*7+3] && response_slot_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==metadata_row;
        wire request_event=metadata_events[metadata_row*7+4] && candidate==metadata_row;
        wire forward_event=metadata_events[metadata_row*7+5] && candidate==metadata_row;
        wire pop_event=metadata_events[metadata_row*7+6] && head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==metadata_row;
        wire early_event=(STORE_ADDRESS_PROBE!=0) && early_addr_valid_i &&
            tag_matches_slot(early_addr_tag_i,metadata_row) && store_mem[metadata_row] &&
            !addr_ready_mem[metadata_row] && !request_sent_mem[metadata_row] && !complete_mem[metadata_row];

        always @* begin:g_static_commands
                load_mem_write_data[metadata_row]=0; load_mem_write_enable[metadata_row]=0;
                store_mem_write_data[metadata_row]=0; store_mem_write_enable[metadata_row]=0;
                generation_mem_write_data[metadata_row]=0; generation_mem_write_enable[metadata_row]=0;
                generation_next_mem_write_data[metadata_row]=0; generation_next_mem_write_enable[metadata_row]=0;
                size_mem_write_data[metadata_row]=0; size_mem_write_enable[metadata_row]=0;
                unsigned_mem_write_data[metadata_row]=0; unsigned_mem_write_enable[metadata_row]=0;
                if(modes[0]) begin
                    generation_mem_write_data[metadata_row]={{(GENERATION_WIDTH-1){1'b0}},1'b1}; generation_mem_write_enable[metadata_row]=1'b1;
                    generation_next_mem_write_data[metadata_row]={{(GENERATION_WIDTH-1){1'b0}},1'b1}; generation_next_mem_write_enable[metadata_row]=1'b1;
                end else if(!modes[1] && !modes[2] && allocated) begin
                    generation_mem_write_data[metadata_row]=allocated_generation; generation_mem_write_enable[metadata_row]=1'b1;
                    generation_next_mem_write_data[metadata_row]=(allocated_generation=={GENERATION_WIDTH{1'b1}})?{{(GENERATION_WIDTH-1){1'b0}},1'b1}:allocated_generation+1'b1; generation_next_mem_write_enable[metadata_row]=1'b1;
                    load_mem_write_data[metadata_row]=allocation[0]; load_mem_write_enable[metadata_row]=1'b1;
                    store_mem_write_data[metadata_row]=allocation[1]; store_mem_write_enable[metadata_row]=1'b1;
                    size_mem_write_data[metadata_row]=allocation[2 +: 2]; size_mem_write_enable[metadata_row]=1'b1;
                    unsigned_mem_write_data[metadata_row]=allocation[4]; unsigned_mem_write_enable[metadata_row]=1'b1;
                end
        end
        always @* begin:g_ready_commands
            integer update_lane;
            update_lane=0;
                addr_ready_mem_write_data[metadata_row]=0; addr_ready_mem_write_enable[metadata_row]=0;
                data_ready_mem_write_data[metadata_row]=0; data_ready_mem_write_enable[metadata_row]=0;
                mask_mem_write_data[metadata_row]=0; mask_mem_write_enable[metadata_row]=0;
            if(!modes[3] && !modes[4]) begin
                if(!modes[5] && early_event) begin
                    addr_ready_mem_write_data[metadata_row]=1'b1; addr_ready_mem_write_enable[metadata_row]=1'b1;
                    if(mask_mem[metadata_row]==0) begin mask_mem_write_data[metadata_row]=access_mask(size_mem[metadata_row]); mask_mem_write_enable[metadata_row]=1'b1; end
                end
                // Both ordinary execution and recovery accept older live
                // AGU/data/wakeup updates. Later lanes preserve old priority.
                for(update_lane=0;update_lane<BE_WIDTH;update_lane=update_lane+1) begin
                    if(addr_matches[update_lane]) begin
                        addr_ready_mem_write_data[metadata_row]=1'b1; addr_ready_mem_write_enable[metadata_row]=1'b1;
                        if(mask_mem[metadata_row]==0 && store_mem[metadata_row]) begin mask_mem_write_data[metadata_row]=access_mask(size_mem[metadata_row]); mask_mem_write_enable[metadata_row]=1'b1; end
                    end
                    if(data_matches[update_lane]) begin
                        data_ready_mem_write_data[metadata_row]=1'b1; data_ready_mem_write_enable[metadata_row]=1'b1;
                        if(data_mask_update_i[update_lane*4 +: 4]!=0) begin mask_mem_write_data[metadata_row]=data_mask_update_i[update_lane*4 +: 4]; mask_mem_write_enable[metadata_row]=1'b1; end
                    end
                    if(wake_matches[update_lane]) begin data_ready_mem_write_data[metadata_row]=1'b1; data_ready_mem_write_enable[metadata_row]=1'b1; end
                end
                if(!modes[5] && allocated) begin
                    addr_ready_mem_write_data[metadata_row]=allocation[5]; addr_ready_mem_write_enable[metadata_row]=1'b1;
                    data_ready_mem_write_data[metadata_row]=allocation[6]; data_ready_mem_write_enable[metadata_row]=1'b1;
                    mask_mem_write_data[metadata_row]=(allocation[7 +: 4]!=0)?allocation[7 +: 4]:((allocation[1] && allocation[5])?access_mask(allocation[2 +: 2]):4'b0); mask_mem_write_enable[metadata_row]=1'b1;
                end
            end
        end
        always @* begin:g_lifecycle_commands
                valid_mem_write_data[metadata_row]=0; valid_mem_write_enable[metadata_row]=0;
                retired_mem_write_data[metadata_row]=0; retired_mem_write_enable[metadata_row]=0;
                request_sent_mem_write_data[metadata_row]=0; request_sent_mem_write_enable[metadata_row]=0;
                response_wait_mem_write_data[metadata_row]=0; response_wait_mem_write_enable[metadata_row]=0;
                complete_mem_write_data[metadata_row]=0; complete_mem_write_enable[metadata_row]=0;
                load_reported_mem_write_data[metadata_row]=0; load_reported_mem_write_enable[metadata_row]=0;
                complete_error_mem_write_data[metadata_row]=0; complete_error_mem_write_enable[metadata_row]=0;
                forward_mask_mem_write_data[metadata_row]=0; forward_mask_mem_write_enable[metadata_row]=0;
                store_commit_mem_write_data[metadata_row]=0; store_commit_mem_write_enable[metadata_row]=0;
                store_ack_mem_write_data[metadata_row]=0; store_ack_mem_write_enable[metadata_row]=0;
                store_ack_error_mem_write_data[metadata_row]=0; store_ack_error_mem_write_enable[metadata_row]=0;
            if(modes[6] || modes[7]) begin
                    valid_mem_write_data[metadata_row]=1'b0; valid_mem_write_enable[metadata_row]=1'b1;
                    retired_mem_write_data[metadata_row]=1'b0; retired_mem_write_enable[metadata_row]=1'b1;
                    request_sent_mem_write_data[metadata_row]=1'b0; request_sent_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b0; complete_mem_write_enable[metadata_row]=1'b1;
                    load_reported_mem_write_data[metadata_row]=1'b0; load_reported_mem_write_enable[metadata_row]=1'b1;
                    store_commit_mem_write_data[metadata_row]=1'b0; store_commit_mem_write_enable[metadata_row]=1'b1;
                    store_ack_mem_write_data[metadata_row]=1'b0; store_ack_mem_write_enable[metadata_row]=1'b1;
            end else if(modes[8]) begin
                if(kill) begin
                    valid_mem_write_data[metadata_row]=1'b0; valid_mem_write_enable[metadata_row]=1'b1;
                    request_sent_mem_write_data[metadata_row]=1'b0; request_sent_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b0; complete_mem_write_enable[metadata_row]=1'b1;
                    load_reported_mem_write_data[metadata_row]=1'b0; load_reported_mem_write_enable[metadata_row]=1'b1;
                    store_commit_mem_write_data[metadata_row]=1'b0; store_commit_mem_write_enable[metadata_row]=1'b1;
                    store_ack_mem_write_data[metadata_row]=1'b0; store_ack_mem_write_enable[metadata_row]=1'b1;
                end
                if(ack_event) begin
                    store_ack_mem_write_data[metadata_row]=1'b1; store_ack_mem_write_enable[metadata_row]=1'b1;
                    store_ack_error_mem_write_data[metadata_row]=dcache_store_ack_error_i; store_ack_error_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                end
                if(response_event && response_allowed) begin
                    complete_error_mem_write_data[metadata_row]=dcache_resp_error_i; complete_error_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b1; complete_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                end
            end else begin
                if(commit_event) begin store_commit_mem_write_data[metadata_row]=1'b1; store_commit_mem_write_enable[metadata_row]=1'b1; end
                if(|retire_matches) begin retired_mem_write_data[metadata_row]=1'b1; retired_mem_write_enable[metadata_row]=1'b1; end
                if(forward_event) begin
                    complete_error_mem_write_data[metadata_row]=1'b0; complete_error_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b1; complete_mem_write_enable[metadata_row]=1'b1;
                end
                if(request_event) begin
                    request_sent_mem_write_data[metadata_row]=1'b1; request_sent_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b1; response_wait_mem_write_enable[metadata_row]=1'b1;
                    if(load_mem[metadata_row]) begin forward_mask_mem_write_data[metadata_row]=fwd_mask; forward_mask_mem_write_enable[metadata_row]=1'b1; end
                end
                if(response_event) begin
                    complete_error_mem_write_data[metadata_row]=dcache_resp_error_i; complete_error_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b1; complete_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                end
                if(report_event) begin load_reported_mem_write_data[metadata_row]=1'b1; load_reported_mem_write_enable[metadata_row]=1'b1; end
                if(ack_event) begin
                    store_ack_mem_write_data[metadata_row]=1'b1; store_ack_mem_write_enable[metadata_row]=1'b1;
                    store_ack_error_mem_write_data[metadata_row]=dcache_store_ack_error_i; store_ack_error_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                end
                if(pop_event) begin
                    valid_mem_write_data[metadata_row]=1'b0; valid_mem_write_enable[metadata_row]=1'b1;
                    request_sent_mem_write_data[metadata_row]=1'b0; request_sent_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b0; complete_mem_write_enable[metadata_row]=1'b1;
                    load_reported_mem_write_data[metadata_row]=1'b0; load_reported_mem_write_enable[metadata_row]=1'b1;
                    store_ack_mem_write_data[metadata_row]=1'b0; store_ack_mem_write_enable[metadata_row]=1'b1;
                end
                if(allocated) begin
                    valid_mem_write_data[metadata_row]=1'b1; valid_mem_write_enable[metadata_row]=1'b1;
                    retired_mem_write_data[metadata_row]=1'b0; retired_mem_write_enable[metadata_row]=1'b1;
                    request_sent_mem_write_data[metadata_row]=1'b0; request_sent_mem_write_enable[metadata_row]=1'b1;
                    response_wait_mem_write_data[metadata_row]=1'b0; response_wait_mem_write_enable[metadata_row]=1'b1;
                    complete_mem_write_data[metadata_row]=1'b0; complete_mem_write_enable[metadata_row]=1'b1;
                    load_reported_mem_write_data[metadata_row]=1'b0; load_reported_mem_write_enable[metadata_row]=1'b1;
                    complete_error_mem_write_data[metadata_row]=1'b0; complete_error_mem_write_enable[metadata_row]=1'b1;
                    forward_mask_mem_write_data[metadata_row]=1'b0; forward_mask_mem_write_enable[metadata_row]=1'b1;
                    store_commit_mem_write_data[metadata_row]=1'b0; store_commit_mem_write_enable[metadata_row]=1'b1;
                    store_ack_mem_write_data[metadata_row]=1'b0; store_ack_mem_write_enable[metadata_row]=1'b1;
                    store_ack_error_mem_write_data[metadata_row]=1'b0; store_ack_error_mem_write_enable[metadata_row]=1'b1;
                end
            end
        end
    end endgenerate

    always @(posedge clk_i) begin
        if (reset_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            occupancy_reg <= 0;
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
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
            end
        end else if (flush_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            occupancy_reg <= 0;
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                ;
                ;
                ;
                ;
                ;
                ;
                ;
                ;
            end
        end else if (recovery_valid_i) begin
            
            
            
            
            recovery_branch_slot = recovery_tag_i[3 +: ROB_SLOT_WIDTH];
            recovery_branch_age = recovery_branch_slot - recovery_head_i;
            if (((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && recovery_branch_age[RECOVERY_ARITH_WIDTH-1]) recovery_branch_age = recovery_branch_age + ROB_ENTRIES;
            recovery_keep_count = recovery_keep_tree[1];
            recovery_first_killed = recovery_kill_tree[1]?recovery_kill_slot_tree[1]:tail_reg;
            recovery_kill_found = recovery_kill_tree[1];
            for (update_slot = 0; update_slot < LSQ_ENTRIES; update_slot = update_slot + 1) begin
                for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                    if (addr_update_valid_i[lane] &&
                        tag_matches_slot(addr_update_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        ;
                        ;
                        if (mask_mem[update_slot] == 4'b0 && store_mem[update_slot])
                            ;
                    end
                    if (data_update_valid_i[lane] &&
                        tag_matches_slot(data_update_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        ;
                        ;
                        if (data_mask_update_i[(lane*4) +: 4] != 4'b0)
                            ;
                    end
                    if (wakeup_valid_i[lane] &&
                        tag_matches_slot(wakeup_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        ;
                        ;
                    end
                end
            end
            
            
            
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                if (dcache_store_ack_valid_i &&
                    tag_matches_slot(dcache_store_ack_lsq_tag_i, slot) &&
                    request_sent_mem[slot] && response_wait_mem[slot]) begin
                    ;
                    ;
                    ;
                end
            end
            
            
            
            if (response_fire) begin
                entry_rob_slot = response_query_rob_tag[3 +: ROB_SLOT_WIDTH];
                recovery_entry_age = entry_rob_slot - recovery_head_i;
                if (((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && recovery_entry_age[RECOVERY_ARITH_WIDTH-1]) recovery_entry_age = recovery_entry_age + ROB_ENTRIES;
                if (!((recovery_entry_age > recovery_branch_age) &&
                      (recovery_entry_age < recovery_occupancy_i))) begin
                    response_word = payload_response_word;
                    merged_word = (response_query_forward &
                                   expand_word_bytes(response_query_mask)) |
                                  (response_word &
                                   ~expand_word_bytes(response_query_mask));
                    ;
                    ;
                    ;
                    ;
                end
            end
            if (recovery_keep_count < occupancy_reg)
                tail_reg <= recovery_first_killed[SLOT_WIDTH-1:0];
            occupancy_reg <= recovery_keep_count;
        end else begin
            commit_fire = store_commit_valid_i && store_commit_ready_o;
            if (commit_fire) ;

            for (retirement_slot = 0; retirement_slot < LSQ_ENTRIES; retirement_slot = retirement_slot + 1)
                for (retirement_lane = 0; retirement_lane < BE_WIDTH; retirement_lane = retirement_lane + 1)
                    if (valid_mem[retirement_slot] && load_mem[retirement_slot] &&
                        retire_valid_i[retirement_lane] &&
                        rob_tag_mem[retirement_slot] == retire_rob_tag_i[retirement_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH])
                        ;

            
            
            for (update_slot = 0; update_slot < LSQ_ENTRIES; update_slot = update_slot + 1) begin
                
                
                if ((STORE_ADDRESS_PROBE != 0) && early_addr_valid_i &&
                    tag_matches_slot(early_addr_tag_i, update_slot) &&
                    store_mem[update_slot] && !addr_ready_mem[update_slot] &&
                    !request_sent_mem[update_slot] && !complete_mem[update_slot]) begin
                    ;
                    ;
                    if (mask_mem[update_slot] == 4'b0)
                        ;
                end
                for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                    if (addr_update_valid_i[lane] && tag_matches_slot(addr_update_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        ;
                        ;
                        if (mask_mem[update_slot] == 4'b0 && store_mem[update_slot])
                            ;
                    end
                    if (data_update_valid_i[lane] && tag_matches_slot(data_update_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        ;
                        ;
                        if (data_mask_update_i[(lane*4) +: 4] != 4'b0)
                            ;
                    end
                    if (wakeup_valid_i[lane] && tag_matches_slot(wakeup_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        ;
                        ;
                    end
                end
            end

            
            
            if (candidate_found && candidate_load && !candidate_sent && !candidate_complete) begin
                if ((fwd_mask & target_mask) == target_mask) begin
                    ;
                    ;
                    ;
                end
            end

            if (request_fire) begin
                ;
                if (candidate_load) begin
                    ;
                    ;
                    ;
                end else begin
                    ;
                end
            end

            if (response_fire) begin
                response_word = payload_response_word;
                merged_word = (response_query_forward &
                               expand_word_bytes(response_query_mask)) |
                              (response_word &
                               ~expand_word_bytes(response_query_mask));
                ;
                ;
                ;
                ;
            end

            if (load_complete_valid_o && load_complete_ready_i)
                ;

            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                if (dcache_store_ack_valid_i && tag_matches_slot(dcache_store_ack_lsq_tag_i, slot) &&
                    request_sent_mem[slot] && response_wait_mem[slot]) begin
                    ;
                    ;
                    ;
                end
            end

            if ((occupancy_reg != 0) && head_valid &&
                ((head_load && head_complete &&
                  (head_reported ||
                   (load_complete_valid_o && load_complete_ready_i &&
                    (complete_slot_select == head_reg)))) ||
                 (head_store && head_ack && store_ack_ready_i))) begin
                ;
                ;
                ;
                ;
                ;
                ;
            end

            
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                if (alloc_fire_o[lane]) begin
                    alloc_slot = tail_reg + alloc_count_before_lane(lane, alloc_fire_o);
                    if (alloc_slot >= LSQ_ENTRIES) alloc_slot = alloc_slot - LSQ_ENTRIES;
                    next_generation = generation_next_mem[alloc_slot];
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
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                    ;
                end
            end

            alloc_count_calc = alloc_count_o;
            pop_count_calc = ((occupancy_reg != 0) && head_valid &&
                              ((head_load && head_complete &&
                                (head_reported ||
                                 (load_complete_valid_o && load_complete_ready_i &&
                                  (complete_slot_select == head_reg)))) ||
                               (head_store && head_ack && store_ack_ready_i))) ? 1 : 0;
            head_reg <= advance_slot(head_reg, pop_count_calc);
            tail_reg <= advance_slot(tail_reg, alloc_count_calc);
            occupancy_reg <= occupancy_reg - pop_count_calc + alloc_count_calc;
        end
    end

    genvar storage_row;
    generate for(storage_row=0;storage_row<LSQ_ENTRIES;storage_row=storage_row+1) begin:g_state_row
        rv32_lsq_owned_field #(.WIDTH(1)) valid_mem_owner (
            .clk_i(clk_i),.write_i(valid_mem_write_enable[storage_row]),
            .data_i(valid_mem_write_data[storage_row]),.data_o(valid_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) load_mem_owner (
            .clk_i(clk_i),.write_i(load_mem_write_enable[storage_row]),
            .data_i(load_mem_write_data[storage_row]),.data_o(load_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) store_mem_owner (
            .clk_i(clk_i),.write_i(store_mem_write_enable[storage_row]),
            .data_i(store_mem_write_data[storage_row]),.data_o(store_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(ROB_TAG_WIDTH-1+1)) rob_tag_mem_owner (
            .clk_i(clk_i),.write_i(rob_tag_mem_write_enable[storage_row]),
            .data_i(rob_tag_mem_write_data[storage_row]),.data_o(rob_tag_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) retired_mem_owner (
            .clk_i(clk_i),.write_i(retired_mem_write_enable[storage_row]),
            .data_i(retired_mem_write_data[storage_row]),.data_o(retired_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(GENERATION_WIDTH-1+1)) generation_mem_owner (
            .clk_i(clk_i),.write_i(generation_mem_write_enable[storage_row]),
            .data_i(generation_mem_write_data[storage_row]),.data_o(generation_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(GENERATION_WIDTH-1+1)) generation_next_mem_owner (
            .clk_i(clk_i),.write_i(generation_next_mem_write_enable[storage_row]),
            .data_i(generation_next_mem_write_data[storage_row]),.data_o(generation_next_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1+1)) size_mem_owner (
            .clk_i(clk_i),.write_i(size_mem_write_enable[storage_row]),
            .data_i(size_mem_write_data[storage_row]),.data_o(size_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) unsigned_mem_owner (
            .clk_i(clk_i),.write_i(unsigned_mem_write_enable[storage_row]),
            .data_i(unsigned_mem_write_data[storage_row]),.data_o(unsigned_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) addr_ready_mem_owner (
            .clk_i(clk_i),.write_i(addr_ready_mem_write_enable[storage_row]),
            .data_i(addr_ready_mem_write_data[storage_row]),.data_o(addr_ready_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) data_ready_mem_owner (
            .clk_i(clk_i),.write_i(data_ready_mem_write_enable[storage_row]),
            .data_i(data_ready_mem_write_data[storage_row]),.data_o(data_ready_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(31+1)) addr_mem_owner (
            .clk_i(clk_i),.write_i(addr_mem_write_enable[storage_row]),
            .data_i(addr_mem_write_data[storage_row]),.data_o(addr_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(31+1)) data_mem_owner (
            .clk_i(clk_i),.write_i(data_mem_write_enable[storage_row]),
            .data_i(data_mem_write_data[storage_row]),.data_o(data_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(3+1)) mask_mem_owner (
            .clk_i(clk_i),.write_i(mask_mem_write_enable[storage_row]),
            .data_i(mask_mem_write_data[storage_row]),.data_o(mask_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) request_sent_mem_owner (
            .clk_i(clk_i),.write_i(request_sent_mem_write_enable[storage_row]),
            .data_i(request_sent_mem_write_data[storage_row]),.data_o(request_sent_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) response_wait_mem_owner (
            .clk_i(clk_i),.write_i(response_wait_mem_write_enable[storage_row]),
            .data_i(response_wait_mem_write_data[storage_row]),.data_o(response_wait_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) complete_mem_owner (
            .clk_i(clk_i),.write_i(complete_mem_write_enable[storage_row]),
            .data_i(complete_mem_write_data[storage_row]),.data_o(complete_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) load_reported_mem_owner (
            .clk_i(clk_i),.write_i(load_reported_mem_write_enable[storage_row]),
            .data_i(load_reported_mem_write_data[storage_row]),.data_o(load_reported_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(31+1)) complete_value_mem_owner (
            .clk_i(clk_i),.write_i(complete_value_mem_write_enable[storage_row]),
            .data_i(complete_value_mem_write_data[storage_row]),.data_o(complete_value_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) complete_error_mem_owner (
            .clk_i(clk_i),.write_i(complete_error_mem_write_enable[storage_row]),
            .data_i(complete_error_mem_write_data[storage_row]),.data_o(complete_error_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(3+1)) forward_mask_mem_owner (
            .clk_i(clk_i),.write_i(forward_mask_mem_write_enable[storage_row]),
            .data_i(forward_mask_mem_write_data[storage_row]),.data_o(forward_mask_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(31+1)) forward_data_mem_owner (
            .clk_i(clk_i),.write_i(forward_data_mem_write_enable[storage_row]),
            .data_i(forward_data_mem_write_data[storage_row]),.data_o(forward_data_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) store_commit_mem_owner (
            .clk_i(clk_i),.write_i(store_commit_mem_write_enable[storage_row]),
            .data_i(store_commit_mem_write_data[storage_row]),.data_o(store_commit_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) store_ack_mem_owner (
            .clk_i(clk_i),.write_i(store_ack_mem_write_enable[storage_row]),
            .data_i(store_ack_mem_write_data[storage_row]),.data_o(store_ack_mem[storage_row]));
        rv32_lsq_owned_field #(.WIDTH(1)) store_ack_error_mem_owner (
            .clk_i(clk_i),.write_i(store_ack_error_mem_write_enable[storage_row]),
            .data_i(store_ack_error_mem_write_data[storage_row]),.data_o(store_ack_error_mem[storage_row]));
    end endgenerate

    function integer alloc_count_before_lane;
        input integer target_lane;
        input [BE_WIDTH-1:0] fire;
        integer k;
        begin
            alloc_count_before_lane = 0;
            for (k = 0; k < BE_WIDTH; k = k + 1)
                if ((k < target_lane) && fire[k]) alloc_count_before_lane = alloc_count_before_lane + 1;
        end
    endfunction
endmodule

// Owns actual architectural queue fields. The enable/hold mux is local,
// so a shared write decision drives one input rather than every data bit.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.
module rv32_lsq_owned_field #(parameter integer WIDTH=32) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) payload_owner (
        .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
endmodule


// Exact relative byte routing for any pair of four-bit line offsets.
// Instead of sixteen repeated (load_offset+b)==(store_offset+j) comparisons,
// decode seven possible nonempty windows once and share across the four bytes.
// This adds no state, speculation, or new alignment assumption.
(* keep_hierarchy = 1 *)
module rv32_lsq_forward_window (
    input wire [31:0] store_data_i,
    input wire [3:0] store_offset_i,store_mask_i,load_offset_i,load_mask_i,
    output wire [3:0] mask_o,
    output wire [31:0] data_o
);
    // Five bits exactly represent every difference in [-15,+15] modulo32.
    // Only differences -3..+3 can place a store byte in the four-byte window.
    wire [4:0] offset_delta={1'b0,load_offset_i}-{1'b0,store_offset_i};
    wire [6:0] alignments;
    wire [27:0] alignment_views;
    rv32_frequency_control_tree #(.WIDTH(7),.LEAVES(4)) alignment_tree (
        .signal_i(alignments),.views_o(alignment_views));
    genvar delta_id,load_byte,store_byte;
    generate
        for(delta_id=0;delta_id<7;delta_id=delta_id+1) begin:g_delta
            localparam [4:0] DELTA=delta_id-3;
            assign alignments[delta_id]=offset_delta==DELTA;
        end
        for(load_byte=0;load_byte<4;load_byte=load_byte+1) begin:g_load_byte
            wire [3:0] byte_match_bits;
            wire [7:0] routed [0:3];
            for(store_byte=0;store_byte<4;store_byte=store_byte+1) begin:g_store_byte
                localparam integer ALIGNMENT=store_byte-load_byte+3;
                wire match_view;
                rv32_frequency_control_tree #(.LEAVES(1)) match_tree (
                    .signal_i(load_mask_i[load_byte] && store_mask_i[store_byte] &&
                              alignment_views[load_byte*7+ALIGNMENT]),.views_o(match_view));
                assign byte_match_bits[store_byte]=match_view;
                assign routed[store_byte]={8{match_view}} & store_data_i[store_byte*8 +: 8];
            end
            // There is at most one matching source byte for each output byte.
            assign mask_o[load_byte]=|byte_match_bits;
            assign data_o[load_byte*8 +: 8]=(routed[0] | routed[1]) | (routed[2] | routed[3]);
        end
    endgenerate
endmodule
