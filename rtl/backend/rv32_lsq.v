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
    output reg  [127:0]                 dcache_req_wdata_o,
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
    wire selection_live=selection_valid && tag_matches_slot(selection_lsq_tag,selection_slot) &&
        !request_sent_mem[selection_slot] && !complete_mem[selection_slot] && !response_wait_mem[selection_slot];
    wire selection_discard=selection_valid && !selection_live;
    wire [SLOT_WIDTH-1:0] selected_slot=(REQUEST_PIPELINE!=0)?selection_slot:pick_slot[1];
    wire [31:0] selected_addr=(REQUEST_PIPELINE!=0)?selection_addr:pick_addr[1];
    wire [SLOT_WIDTH-1:0] selected_age=selected_slot-head_reg;
    wire [1:0] selected_size=(REQUEST_PIPELINE!=0)?selection_size:size_mem[pick_slot[1]];
    wire selected_unsigned=(REQUEST_PIPELINE!=0)?selection_unsigned:unsigned_mem[pick_slot[1]];
    wire selected_load=(REQUEST_PIPELINE!=0)?selection_load:load_mem[pick_slot[1]];
    wire [3:0] selected_store_mask=(REQUEST_PIPELINE!=0)?selection_store_mask:mask_mem[pick_slot[1]];
    wire [31:0] selected_store_data=(REQUEST_PIPELINE!=0)?selection_store_data:data_mem[pick_slot[1]];
    wire [ROB_TAG_WIDTH-1:0] selected_rob_tag=(REQUEST_PIPELINE!=0)?selection_rob_tag:rob_tag_mem[pick_slot[1]];
    wire [TAG_WIDTH-1:0] selected_lsq_tag=(REQUEST_PIPELINE!=0)?selection_lsq_tag:
        make_lsq_tag(pick_slot[1],generation_mem[pick_slot[1]]);
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
        !(store_mem[selection_slot] && store_commit_mem[selection_slot]) &&
        !(load_mem[selection_slot] && retired_mem[selection_slot]) &&
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
            selection_lsq_tag<=make_lsq_tag(pick_slot[1],generation_mem[pick_slot[1]]);
            selection_rob_tag<=rob_tag_mem[pick_slot[1]];
        end
        if(selection_write_views[1]) selection_addr<=pick_addr[1];
        if(selection_write_views[2]) begin
            selection_load<=load_mem[pick_slot[1]];selection_size<=size_mem[pick_slot[1]];
            selection_unsigned<=unsigned_mem[pick_slot[1]];
        end
        if(selection_write_views[3]) selection_store_mask<=mask_mem[pick_slot[1]];
        if(selection_write_views[4]) selection_store_data<=data_mem[pick_slot[1]];
        if(forwarding_payload_write) begin forwarding_hold_mask<=fwd_mask;forwarding_hold_data<=fwd_data;end
    end

    genvar age_slot;
    generate
        for (age_slot = 0; age_slot < LSQ_ENTRIES; age_slot = age_slot + 1) begin : g_entry_age
            assign entry_age[age_slot] = (age_slot - head_reg) & (LSQ_ENTRIES - 1);
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
            assign store_overlap[age_slot] =
                valid_mem[age_slot] && store_mem[age_slot] &&
                addr_ready_mem[age_slot] && data_ready_mem[age_slot] &&
                (entry_age[age_slot] < selected_age) &&
                (addr_mem[age_slot][31:4] == selected_addr[31:4]) ?
                relative_overlap(addr_mem[age_slot][3:0], mask_mem[age_slot],
                    selected_addr[3:0], access_mask(selected_size)) : 4'b0;
            assign store_forward_data[age_slot] = store_data_relative_to_load(
                data_mem[age_slot], addr_mem[age_slot][3:0], mask_mem[age_slot],
                selected_addr[3:0], access_mask(selected_size));
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
                assign older_hazard[older_slot] =
                    (entry_age[older_slot] < entry_age[request_slot]) &&
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
                (!pick_valid[2*pick_node+1] || (pick_age[2*pick_node] <= pick_age[2*pick_node+1]));
            assign pick_valid[pick_node] = pick_valid[2*pick_node] || pick_valid[2*pick_node+1];
            assign pick_slot[pick_node] = choose_left ? pick_slot[2*pick_node] : pick_slot[2*pick_node+1];
            assign pick_age[pick_node] = choose_left ? pick_age[2*pick_node] : pick_age[2*pick_node+1];
            // Carry the address alongside the winning age/slot. The cache
            // need not wait for a second binary-indexed read after selection.
            assign pick_addr[pick_node] = choose_left ? pick_addr[2*pick_node] : pick_addr[2*pick_node+1];
        end
        // Each byte independently selects the youngest overlapping older
        // store. Static reads replace repeated head-relative array muxes.
        for (forward_byte = 0; forward_byte < 4; forward_byte = forward_byte + 1) begin : g_forward
            wire byte_valid [1:2*LSQ_ENTRIES-1];
            wire [SLOT_WIDTH-1:0] byte_age [1:2*LSQ_ENTRIES-1];
            wire [7:0] byte_data [1:2*LSQ_ENTRIES-1];
            for (forward_slot = 0; forward_slot < LSQ_ENTRIES; forward_slot = forward_slot + 1) begin : g_leaf
                assign byte_valid[LSQ_ENTRIES+forward_slot] = store_overlap[forward_slot][forward_byte];
                assign byte_age[LSQ_ENTRIES+forward_slot] = entry_age[forward_slot];
                assign byte_data[LSQ_ENTRIES+forward_slot] = store_forward_data[forward_slot][forward_byte*8 +: 8];
            end
            for (forward_node = 1; forward_node < LSQ_ENTRIES; forward_node = forward_node + 1) begin : g_node
                wire choose_left = byte_valid[2*forward_node] &&
                    (!byte_valid[2*forward_node+1] || (byte_age[2*forward_node] >= byte_age[2*forward_node+1]));
                assign byte_valid[forward_node] = byte_valid[2*forward_node] || byte_valid[2*forward_node+1];
                assign byte_age[forward_node] = choose_left ? byte_age[2*forward_node] : byte_age[2*forward_node+1];
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

        // ROB presents stores in architectural order.  Match by ROB tag
        // instead of requiring the LSQ entry itself to be at the queue head:
        // older committed stores may still be waiting for the cache.
        store_commit_ready_o = 1'b0;
        commit_slot_select = 0;
        commit_slot_found = 1'b0;
        if (!flush_i && occupancy_reg != 0) begin
            for (scan = 0; scan < LSQ_ENTRIES; scan = scan + 1) begin
                if (!commit_slot_found && valid_mem[scan] && store_mem[scan] &&
                    addr_ready_mem[scan] && data_ready_mem[scan] &&
                    !store_commit_mem[scan] &&
                    (rob_tag_mem[scan] == store_commit_rob_tag_i)) begin
                    store_commit_ready_o = 1'b1;
                    commit_slot_select = scan;
                    commit_slot_found = 1'b1;
                end
            end
        end

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
        dcache_req_wdata_o = 128'b0;
        dcache_req_rob_tag_o = {ROB_TAG_WIDTH{1'b0}};
        dcache_req_lsq_tag_o = {TAG_WIDTH{1'b0}};
        request_fire = 1'b0;
        // Recovery updates retained responses but cannot record a new request.
        // Do not let the cache (or request register) accept an untracked send.
        if (!flush_i && !recovery_valid_i && candidate_found && !response_wait_mem[candidate]) begin
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
                    dcache_req_wdata_o = line_data_from_relative(fwd_data, selected_addr);
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
                dcache_req_wdata_o = line_data_from_relative(selected_store_data, selected_addr);
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

    always @* begin
        load_complete_valid_o = 1'b0;
        load_complete_rob_tag_o = {ROB_TAG_WIDTH{1'b0}};
        load_complete_lsq_tag_o = {TAG_WIDTH{1'b0}};
        load_complete_value_o = 32'b0;
        load_complete_error_o = 1'b0;
        store_ack_valid_o = 1'b0;
        store_ack_rob_tag_o = {ROB_TAG_WIDTH{1'b0}};
        store_ack_lsq_tag_o = {TAG_WIDTH{1'b0}};
        store_ack_error_o = 1'b0;
        complete_slot_found = 1'b0;
        complete_slot_select = head_reg;
        // Loads already obeyed all older-store hazards when they issued.
        // Report the oldest completed, not-yet-reported load even when an
        // older committed store is still occupying the LSQ head.
        for (complete_scan = 0; complete_scan < LSQ_ENTRIES;
             complete_scan = complete_scan + 1) begin
            complete_index = head_reg + complete_scan;
            if (complete_index >= LSQ_ENTRIES)
                complete_index = complete_index - LSQ_ENTRIES;
            if (!complete_slot_found && (complete_scan < occupancy_reg) &&
                valid_mem[complete_index] && load_mem[complete_index] &&
                complete_mem[complete_index] &&
                !load_reported_mem[complete_index]) begin
                complete_slot_found = 1'b1;
                complete_slot_select = complete_index;
            end
        end
        if (complete_slot_found) begin
            load_complete_valid_o = 1'b1;
            load_complete_rob_tag_o = rob_tag_mem[complete_slot_select];
            load_complete_lsq_tag_o = make_lsq_tag(
                complete_slot_select, generation_mem[complete_slot_select]);
            load_complete_value_o = complete_value_mem[complete_slot_select];
            load_complete_error_o = complete_error_mem[complete_slot_select];
        end
        if (occupancy_reg != 0 && valid_mem[head_reg]) begin
            if (store_mem[head_reg] && store_ack_mem[head_reg]) begin
                store_ack_valid_o = 1'b1;
                store_ack_rob_tag_o = rob_tag_mem[head_reg];
                store_ack_lsq_tag_o = make_lsq_tag(head_reg, generation_mem[head_reg]);
                store_ack_error_o = store_ack_error_mem[head_reg];
            end
        end
    end


    // Wide payload fields have no reset state. Their old write sequence is
    // expressed as independent local events; scalar metadata remains separate.
    localparam integer ADDRESS_EVENTS=1+2*BE_WIDTH;
    localparam integer DATA_EVENTS=3*BE_WIDTH;
    localparam integer RESULT_EVENTS=2+BE_WIDTH;
    localparam integer FORWARD_EVENTS=1+BE_WIDTH;
    wire [3*LSQ_ENTRIES-1:0] payload_modes;
    wire [SLOT_WIDTH-1:0] payload_alloc_slot [0:BE_WIDTH-1];
    wire [31:0] payload_response_word=dcache_resp_line_valid_i ?
        relative_data_from_line(dcache_resp_line_data_i,addr_mem[response_slot]) : dcache_resp_word_data_i;
    wire [31:0] payload_response_merge=
        (forward_data_mem[response_slot] & expand_word_bytes(forward_mask_mem[response_slot])) |
        (payload_response_word & ~expand_word_bytes(forward_mask_mem[response_slot]));
    wire [31:0] payload_response_value=format_relative_value(
        payload_response_merge,size_mem[response_slot],unsigned_mem[response_slot]);
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
            wire [RECOVERY_ARITH_WIDTH-1:0] row_age=payload_recovery_age(rob_tag_mem[payload_row]);
            assign result_events[1]=enabled && response_fire && response_slot==payload_row &&
                (!recovery || !(row_age>payload_branch_age && row_age<recovery_occupancy_i));
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
    wire metadata_pop=(occupancy_reg!=0) && valid_mem[head_reg] &&
        ((load_mem[head_reg] && complete_mem[head_reg] &&
          (load_reported_mem[head_reg] || (load_complete_valid_o && load_complete_ready_i && complete_slot_select==head_reg))) ||
         (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i));
    wire metadata_forward=candidate_found && load_mem[candidate] &&
        !request_sent_mem[candidate] && !complete_mem[candidate] && ((fwd_mask & target_mask)==target_mask);
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
        wire [META_LSQ_AGE_WIDTH-1:0] lsq_difference=metadata_row-head_reg;
        wire [META_LSQ_AGE_WIDTH-1:0] lsq_age=
            (((LSQ_ENTRIES & (LSQ_ENTRIES-1))!=0) && lsq_difference[META_LSQ_AGE_WIDTH-1])?
            lsq_difference+LSQ_ENTRIES:lsq_difference;
        wire [RECOVERY_ARITH_WIDTH-1:0] row_rob_age=payload_recovery_age(rob_tag_mem[metadata_row]);
        wire kill=lsq_age<occupancy_reg && valid_mem[metadata_row] &&
            !(store_mem[metadata_row] && store_commit_mem[metadata_row]) &&
            !(load_mem[metadata_row] && retired_mem[metadata_row]) &&
            row_rob_age>payload_branch_age && row_rob_age<recovery_occupancy_i;
        wire response_allowed=!(row_rob_age>payload_branch_age && row_rob_age<recovery_occupancy_i);
        wire commit_event=metadata_events[metadata_row*7] && commit_slot_select==metadata_row;
        wire report_event=metadata_events[metadata_row*7+1] && complete_slot_select==metadata_row;
        wire ack_event=metadata_events[metadata_row*7+2] &&
            tag_matches_slot(dcache_store_ack_lsq_tag_i,metadata_row) &&
            request_sent_mem[metadata_row] && response_wait_mem[metadata_row];
        wire response_event=metadata_events[metadata_row*7+3] && response_slot==metadata_row;
        wire request_event=metadata_events[metadata_row*7+4] && candidate==metadata_row;
        wire forward_event=metadata_events[metadata_row*7+5] && candidate==metadata_row;
        wire pop_event=metadata_events[metadata_row*7+6] && head_reg==metadata_row;
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
            recovery_keep_count = 0;
            recovery_first_killed = tail_reg;
            recovery_kill_found = 0;
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                scan = head_reg + slot;
                if (scan >= LSQ_ENTRIES) scan = scan - LSQ_ENTRIES;
                if ((slot < occupancy_reg) && valid_mem[scan]) begin
                    entry_rob_slot = rob_tag_mem[scan][3 +: ROB_SLOT_WIDTH];
                    recovery_entry_age = entry_rob_slot - recovery_head_i;
                    if (((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && recovery_entry_age[RECOVERY_ARITH_WIDTH-1]) recovery_entry_age = recovery_entry_age + ROB_ENTRIES;
                    
                    
                    
                    
                    
                    
                    
                    
                    if (!(store_mem[scan] && store_commit_mem[scan]) &&
                        !(load_mem[scan] && retired_mem[scan]) &&
                        (recovery_entry_age > recovery_branch_age) &&
                        (recovery_entry_age < recovery_occupancy_i)) begin
                        if (!recovery_kill_found) begin
                            recovery_first_killed = scan;
                            recovery_kill_found = 1;
                        end
                        ;
                        ;
                        ;
                        ;
                        ;
                        ;
                        ;
                    end else begin
                        recovery_keep_count = recovery_keep_count + 1;
                    end
                end
            end
            
            
            
            
            
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
                entry_rob_slot = rob_tag_mem[response_slot][3 +: ROB_SLOT_WIDTH];
                recovery_entry_age = entry_rob_slot - recovery_head_i;
                if (((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && recovery_entry_age[RECOVERY_ARITH_WIDTH-1]) recovery_entry_age = recovery_entry_age + ROB_ENTRIES;
                if (!((recovery_entry_age > recovery_branch_age) &&
                      (recovery_entry_age < recovery_occupancy_i))) begin
                    response_word = dcache_resp_line_valid_i ?
                        relative_data_from_line(dcache_resp_line_data_i, addr_mem[response_slot]) :
                        dcache_resp_word_data_i;
                    merged_word = (forward_data_mem[response_slot] &
                                   expand_word_bytes(forward_mask_mem[response_slot])) |
                                  (response_word &
                                   ~expand_word_bytes(forward_mask_mem[response_slot]));
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

            
            
            if (candidate_found && load_mem[candidate] && !request_sent_mem[candidate] && !complete_mem[candidate]) begin
                if ((fwd_mask & target_mask) == target_mask) begin
                    ;
                    ;
                    ;
                end
            end

            if (request_fire) begin
                ;
                if (load_mem[candidate]) begin
                    ;
                    ;
                    ;
                end else begin
                    ;
                end
            end

            if (response_fire) begin
                response_word = dcache_resp_line_valid_i ?
                    relative_data_from_line(dcache_resp_line_data_i, addr_mem[response_slot]) :
                    dcache_resp_word_data_i;
                merged_word = (forward_data_mem[response_slot] &
                               expand_word_bytes(forward_mask_mem[response_slot])) |
                              (response_word &
                               ~expand_word_bytes(forward_mask_mem[response_slot]));
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

            if ((occupancy_reg != 0) && valid_mem[head_reg] &&
                ((load_mem[head_reg] && complete_mem[head_reg] &&
                  (load_reported_mem[head_reg] ||
                   (load_complete_valid_o && load_complete_ready_i &&
                    (complete_slot_select == head_reg)))) ||
                 (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i))) begin
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
            pop_count_calc = ((occupancy_reg != 0) && valid_mem[head_reg] &&
                              ((load_mem[head_reg] && complete_mem[head_reg] &&
                                (load_reported_mem[head_reg] ||
                                 (load_complete_valid_o && load_complete_ready_i &&
                                  (complete_slot_select == head_reg)))) ||
                               (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i))) ? 1 : 0;
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
