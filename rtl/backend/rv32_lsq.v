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
    integer entry_rob_slot;
    integer recovery_branch_slot;
    integer recovery_branch_age;
    integer recovery_entry_age;
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
            p = start;
            for (n = 0; n < LSQ_ENTRIES; n = n + 1) begin
                if (n < amount) begin
                    if (p == LSQ_ENTRIES - 1) p = 0; else p = p + 1;
                end
            end
            advance_slot = p[SLOT_WIDTH-1:0];
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
                (entry_age[age_slot] < pick_age[1]) &&
                (addr_mem[age_slot][31:4] == pick_addr[1][31:4]) ?
                relative_overlap(addr_mem[age_slot][3:0], mask_mem[age_slot],
                    pick_addr[1][3:0], access_mask(size_mem[pick_slot[1]])) : 4'b0;
            assign store_forward_data[age_slot] = store_data_relative_to_load(
                data_mem[age_slot], addr_mem[age_slot][3:0], mask_mem[age_slot],
                pick_addr[1][3:0], access_mask(size_mem[pick_slot[1]]));
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
        candidate_found = pick_valid[1];
        candidate = pick_valid[1] ? pick_slot[1] : 0;
        candidate_age = pick_valid[1] ? pick_age[1] : LSQ_ENTRIES + 1;

        dcache_req_valid_o = 1'b0;
        dcache_req_is_load_o = 1'b0;
        dcache_req_is_store_o = 1'b0;
        // Payload is meaningful only with valid. Expose the selected address
        // directly so forwarding and recovery gates do not sit on the cache
        // index path.
        dcache_req_addr_o = pick_addr[1];
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
            if (load_mem[candidate]) begin
                target_mask = access_mask(size_mem[candidate]);
                fwd_mask = tree_forward_mask;
                fwd_data = tree_forward_data;
                if ((fwd_mask & target_mask) != target_mask) begin
                    dcache_req_valid_o = 1'b1;
                    dcache_req_is_load_o = 1'b1;
                    dcache_req_size_o = size_mem[candidate];
                    dcache_req_unsigned_o = unsigned_mem[candidate];
                    dcache_req_mask_o = line_mask_from_relative(target_mask & ~fwd_mask,
                                                                 pick_addr[1]);
                    dcache_req_wdata_o = line_data_from_relative(fwd_data, pick_addr[1]);
                    dcache_req_rob_tag_o = rob_tag_mem[candidate];
                    dcache_req_lsq_tag_o = make_lsq_tag(candidate, generation_mem[candidate]);
                    request_fire = dcache_req_ready_i;
                end
            end else begin
                dcache_req_valid_o = 1'b1;
                dcache_req_is_store_o = 1'b1;
                dcache_req_size_o = size_mem[candidate];
                dcache_req_unsigned_o = 1'b0;
                dcache_req_mask_o = line_mask_from_relative(mask_mem[candidate], pick_addr[1]);
                dcache_req_wdata_o = line_data_from_relative(data_mem[candidate], pick_addr[1]);
                dcache_req_rob_tag_o = rob_tag_mem[candidate];
                dcache_req_lsq_tag_o = make_lsq_tag(candidate, generation_mem[candidate]);
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


    // Recovery compares physical rows in parallel. No head-relative payload
    // mux is repeated for every age in a serial scan.
    wire [ROB_SLOT_WIDTH-1:0] recovery_branch_age_parallel =
        recovery_tag_i[3 +: ROB_SLOT_WIDTH] - recovery_head_i;
    wire [LSQ_ENTRIES-1:0] recovery_kill_parallel;
    wire [COUNT_WIDTH-1:0] recovery_keep_tree [1:2*LSQ_ENTRIES-1];
    wire recovery_kill_valid_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_age_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_slot_tree [1:2*LSQ_ENTRIES-1];
    genvar recovery_row,recovery_node;
    generate for(recovery_row=0;recovery_row<LSQ_ENTRIES;recovery_row=recovery_row+1) begin:g_recovery_row
        wire [ROB_SLOT_WIDTH-1:0] age = rob_tag_mem[recovery_row][3 +: ROB_SLOT_WIDTH] - recovery_head_i;
        wire live = entry_age[recovery_row]<occupancy_reg && valid_mem[recovery_row];
        assign recovery_kill_parallel[recovery_row] = live &&
            !(store_mem[recovery_row] && store_commit_mem[recovery_row]) &&
            !(load_mem[recovery_row] && retired_mem[recovery_row]) &&
            age>recovery_branch_age_parallel && age<recovery_occupancy_i;
        assign recovery_keep_tree[LSQ_ENTRIES+recovery_row] = live && !recovery_kill_parallel[recovery_row];
        assign recovery_kill_valid_tree[LSQ_ENTRIES+recovery_row] = recovery_kill_parallel[recovery_row];
        assign recovery_kill_age_tree[LSQ_ENTRIES+recovery_row] = entry_age[recovery_row];
        assign recovery_kill_slot_tree[LSQ_ENTRIES+recovery_row] = recovery_row;
    end
    for(recovery_node=1;recovery_node<LSQ_ENTRIES;recovery_node=recovery_node+1) begin:g_recovery_tree
        wire pick_left = recovery_kill_valid_tree[2*recovery_node] &&
            (!recovery_kill_valid_tree[2*recovery_node+1] ||
             recovery_kill_age_tree[2*recovery_node] <= recovery_kill_age_tree[2*recovery_node+1]);
        assign recovery_keep_tree[recovery_node] = recovery_keep_tree[2*recovery_node] + recovery_keep_tree[2*recovery_node+1];
        assign recovery_kill_valid_tree[recovery_node] = recovery_kill_valid_tree[2*recovery_node] || recovery_kill_valid_tree[2*recovery_node+1];
        assign recovery_kill_age_tree[recovery_node] = pick_left ? recovery_kill_age_tree[2*recovery_node] : recovery_kill_age_tree[2*recovery_node+1];
        assign recovery_kill_slot_tree[recovery_node] = pick_left ? recovery_kill_slot_tree[2*recovery_node] : recovery_kill_slot_tree[2*recovery_node+1];
    end endgenerate

    always @* begin : g_state_commands
        integer bank_alloc_count_calc;
        integer bank_alloc_slot;
        reg bank_commit_fire;
        integer bank_entry_rob_slot;
        integer bank_lane;
        reg [31:0] bank_merged_word;
        reg [GENERATION_WIDTH-1:0] bank_next_generation;
        integer bank_pop_count_calc;
        integer bank_recovery_branch_age;
        integer bank_recovery_entry_age;
        integer bank_recovery_first_killed;
        integer bank_recovery_keep_count;
        integer bank_recovery_kill_found;
        reg [31:0] bank_response_word;
        integer bank_slot;
        integer bank_update_slot;
        integer bank_default_row;
        for(bank_default_row=0;bank_default_row<LSQ_ENTRIES;bank_default_row=bank_default_row+1) begin
            valid_mem_write_data[bank_default_row]=0; valid_mem_write_enable[bank_default_row]=0;
            load_mem_write_data[bank_default_row]=0; load_mem_write_enable[bank_default_row]=0;
            store_mem_write_data[bank_default_row]=0; store_mem_write_enable[bank_default_row]=0;
            rob_tag_mem_write_data[bank_default_row]=0; rob_tag_mem_write_enable[bank_default_row]=0;
            retired_mem_write_data[bank_default_row]=0; retired_mem_write_enable[bank_default_row]=0;
            generation_mem_write_data[bank_default_row]=0; generation_mem_write_enable[bank_default_row]=0;
            generation_next_mem_write_data[bank_default_row]=0; generation_next_mem_write_enable[bank_default_row]=0;
            size_mem_write_data[bank_default_row]=0; size_mem_write_enable[bank_default_row]=0;
            unsigned_mem_write_data[bank_default_row]=0; unsigned_mem_write_enable[bank_default_row]=0;
            addr_ready_mem_write_data[bank_default_row]=0; addr_ready_mem_write_enable[bank_default_row]=0;
            data_ready_mem_write_data[bank_default_row]=0; data_ready_mem_write_enable[bank_default_row]=0;
            addr_mem_write_data[bank_default_row]=0; addr_mem_write_enable[bank_default_row]=0;
            data_mem_write_data[bank_default_row]=0; data_mem_write_enable[bank_default_row]=0;
            mask_mem_write_data[bank_default_row]=0; mask_mem_write_enable[bank_default_row]=0;
            request_sent_mem_write_data[bank_default_row]=0; request_sent_mem_write_enable[bank_default_row]=0;
            response_wait_mem_write_data[bank_default_row]=0; response_wait_mem_write_enable[bank_default_row]=0;
            complete_mem_write_data[bank_default_row]=0; complete_mem_write_enable[bank_default_row]=0;
            load_reported_mem_write_data[bank_default_row]=0; load_reported_mem_write_enable[bank_default_row]=0;
            complete_value_mem_write_data[bank_default_row]=0; complete_value_mem_write_enable[bank_default_row]=0;
            complete_error_mem_write_data[bank_default_row]=0; complete_error_mem_write_enable[bank_default_row]=0;
            forward_mask_mem_write_data[bank_default_row]=0; forward_mask_mem_write_enable[bank_default_row]=0;
            forward_data_mem_write_data[bank_default_row]=0; forward_data_mem_write_enable[bank_default_row]=0;
            store_commit_mem_write_data[bank_default_row]=0; store_commit_mem_write_enable[bank_default_row]=0;
            store_ack_mem_write_data[bank_default_row]=0; store_ack_mem_write_enable[bank_default_row]=0;
            store_ack_error_mem_write_data[bank_default_row]=0; store_ack_error_mem_write_enable[bank_default_row]=0;
        end
        bank_alloc_count_calc=0;
        bank_alloc_slot=0;
        bank_commit_fire=0;
        bank_entry_rob_slot=0;
        bank_lane=0;
        bank_merged_word=0;
        bank_next_generation=0;
        bank_pop_count_calc=0;
        bank_recovery_branch_age=0;
        bank_recovery_entry_age=0;
        bank_recovery_first_killed=0;
        bank_recovery_keep_count=0;
        bank_recovery_kill_found=0;
        bank_response_word=0;
        bank_slot=0;
        bank_update_slot=0;

        if (reset_i) begin
            ;
            ;
            ;
            for (bank_slot = 0; bank_slot < LSQ_ENTRIES; bank_slot = bank_slot + 1) begin
                begin valid_mem_write_data[bank_slot] = 1'b0; valid_mem_write_enable[bank_slot] = 1'b1; end
                begin retired_mem_write_data[bank_slot] = 1'b0; retired_mem_write_enable[bank_slot] = 1'b1; end
                begin generation_mem_write_data[bank_slot] = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1}; generation_mem_write_enable[bank_slot] = 1'b1; end
                begin generation_next_mem_write_data[bank_slot] = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1}; generation_next_mem_write_enable[bank_slot] = 1'b1; end
                begin request_sent_mem_write_data[bank_slot] = 1'b0; request_sent_mem_write_enable[bank_slot] = 1'b1; end
                begin response_wait_mem_write_data[bank_slot] = 1'b0; response_wait_mem_write_enable[bank_slot] = 1'b1; end
                begin complete_mem_write_data[bank_slot] = 1'b0; complete_mem_write_enable[bank_slot] = 1'b1; end
                begin load_reported_mem_write_data[bank_slot] = 1'b0; load_reported_mem_write_enable[bank_slot] = 1'b1; end
                begin store_commit_mem_write_data[bank_slot] = 1'b0; store_commit_mem_write_enable[bank_slot] = 1'b1; end
                begin store_ack_mem_write_data[bank_slot] = 1'b0; store_ack_mem_write_enable[bank_slot] = 1'b1; end
            end
        end else if (flush_i) begin
            ;
            ;
            ;
            for (bank_slot = 0; bank_slot < LSQ_ENTRIES; bank_slot = bank_slot + 1) begin
                begin valid_mem_write_data[bank_slot] = 1'b0; valid_mem_write_enable[bank_slot] = 1'b1; end
                begin retired_mem_write_data[bank_slot] = 1'b0; retired_mem_write_enable[bank_slot] = 1'b1; end
                begin request_sent_mem_write_data[bank_slot] = 1'b0; request_sent_mem_write_enable[bank_slot] = 1'b1; end
                begin response_wait_mem_write_data[bank_slot] = 1'b0; response_wait_mem_write_enable[bank_slot] = 1'b1; end
                begin complete_mem_write_data[bank_slot] = 1'b0; complete_mem_write_enable[bank_slot] = 1'b1; end
                begin load_reported_mem_write_data[bank_slot] = 1'b0; load_reported_mem_write_enable[bank_slot] = 1'b1; end
                begin store_commit_mem_write_data[bank_slot] = 1'b0; store_commit_mem_write_enable[bank_slot] = 1'b1; end
                begin store_ack_mem_write_data[bank_slot] = 1'b0; store_ack_mem_write_enable[bank_slot] = 1'b1; end
            end
        end else if (recovery_valid_i) begin
            
            
            
            
            bank_recovery_branch_age = recovery_branch_age_parallel;
            bank_recovery_keep_count = recovery_keep_tree[1];
            bank_recovery_first_killed = recovery_kill_slot_tree[1];
            bank_recovery_kill_found = recovery_kill_valid_tree[1];
            for (bank_slot=0;bank_slot<LSQ_ENTRIES;bank_slot=bank_slot+1) begin
                if(recovery_kill_parallel[bank_slot]) begin
                    begin valid_mem_write_data[bank_slot] = 0; valid_mem_write_enable[bank_slot] = 1'b1; end begin request_sent_mem_write_data[bank_slot] = 0; request_sent_mem_write_enable[bank_slot] = 1'b1; end
                    begin response_wait_mem_write_data[bank_slot] = 0; response_wait_mem_write_enable[bank_slot] = 1'b1; end begin complete_mem_write_data[bank_slot] = 0; complete_mem_write_enable[bank_slot] = 1'b1; end
                    begin load_reported_mem_write_data[bank_slot] = 0; load_reported_mem_write_enable[bank_slot] = 1'b1; end begin store_commit_mem_write_data[bank_slot] = 0; store_commit_mem_write_enable[bank_slot] = 1'b1; end
                    begin store_ack_mem_write_data[bank_slot] = 0; store_ack_mem_write_enable[bank_slot] = 1'b1; end
                end
            end
            
            
            
            
            
            for (bank_update_slot = 0; bank_update_slot < LSQ_ENTRIES; bank_update_slot = bank_update_slot + 1) begin
                for (bank_lane = 0; bank_lane < BE_WIDTH; bank_lane = bank_lane + 1) begin
                    if (addr_update_valid_i[bank_lane] &&
                        tag_matches_slot(addr_update_tag_i[(bank_lane*TAG_WIDTH) +: TAG_WIDTH], bank_update_slot)) begin
                        begin addr_ready_mem_write_data[bank_update_slot] = 1'b1; addr_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                        begin addr_mem_write_data[bank_update_slot] = addr_update_i[(bank_lane*32) +: 32]; addr_mem_write_enable[bank_update_slot] = 1'b1; end
                        if (mask_mem[bank_update_slot] == 4'b0 && store_mem[bank_update_slot])
                            begin mask_mem_write_data[bank_update_slot] = access_mask(size_mem[bank_update_slot]); mask_mem_write_enable[bank_update_slot] = 1'b1; end
                    end
                    if (data_update_valid_i[bank_lane] &&
                        tag_matches_slot(data_update_tag_i[(bank_lane*TAG_WIDTH) +: TAG_WIDTH], bank_update_slot)) begin
                        begin data_ready_mem_write_data[bank_update_slot] = 1'b1; data_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                        begin data_mem_write_data[bank_update_slot] = data_update_i[(bank_lane*32) +: 32]; data_mem_write_enable[bank_update_slot] = 1'b1; end
                        if (data_mask_update_i[(bank_lane*4) +: 4] != 4'b0)
                            begin mask_mem_write_data[bank_update_slot] = data_mask_update_i[(bank_lane*4) +: 4]; mask_mem_write_enable[bank_update_slot] = 1'b1; end
                    end
                    if (wakeup_valid_i[bank_lane] &&
                        tag_matches_slot(wakeup_tag_i[(bank_lane*TAG_WIDTH) +: TAG_WIDTH], bank_update_slot)) begin
                        begin data_ready_mem_write_data[bank_update_slot] = 1'b1; data_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                        begin data_mem_write_data[bank_update_slot] = wakeup_value_i[(bank_lane*32) +: 32]; data_mem_write_enable[bank_update_slot] = 1'b1; end
                    end
                end
            end
            
            
            
            for (bank_slot = 0; bank_slot < LSQ_ENTRIES; bank_slot = bank_slot + 1) begin
                if (dcache_store_ack_valid_i &&
                    tag_matches_slot(dcache_store_ack_lsq_tag_i, bank_slot) &&
                    request_sent_mem[bank_slot] && response_wait_mem[bank_slot]) begin
                    begin store_ack_mem_write_data[bank_slot] = 1'b1; store_ack_mem_write_enable[bank_slot] = 1'b1; end
                    begin store_ack_error_mem_write_data[bank_slot] = dcache_store_ack_error_i; store_ack_error_mem_write_enable[bank_slot] = 1'b1; end
                    begin response_wait_mem_write_data[bank_slot] = 1'b0; response_wait_mem_write_enable[bank_slot] = 1'b1; end
                end
            end
            
            
            
            if (response_fire) begin
                bank_entry_rob_slot = rob_tag_mem[response_slot][3 +: ROB_SLOT_WIDTH];
                bank_recovery_entry_age = bank_entry_rob_slot - recovery_head_i;
                if (bank_recovery_entry_age < 0) bank_recovery_entry_age = bank_recovery_entry_age + ROB_ENTRIES;
                if (!((bank_recovery_entry_age > bank_recovery_branch_age) &&
                      (bank_recovery_entry_age < recovery_occupancy_i))) begin
                    bank_response_word = dcache_resp_line_valid_i ?
                        relative_data_from_line(dcache_resp_line_data_i, addr_mem[response_slot]) :
                        dcache_resp_word_data_i;
                    bank_merged_word = (forward_data_mem[response_slot] &
                                   expand_word_bytes(forward_mask_mem[response_slot])) |
                                  (bank_response_word &
                                   ~expand_word_bytes(forward_mask_mem[response_slot]));
                    begin complete_value_mem_write_data[response_slot] = format_relative_value(
                        bank_merged_word, size_mem[response_slot], unsigned_mem[response_slot]); complete_value_mem_write_enable[response_slot] = 1'b1; end
                    begin complete_error_mem_write_data[response_slot] = dcache_resp_error_i; complete_error_mem_write_enable[response_slot] = 1'b1; end
                    begin complete_mem_write_data[response_slot] = 1'b1; complete_mem_write_enable[response_slot] = 1'b1; end
                    begin response_wait_mem_write_data[response_slot] = 1'b0; response_wait_mem_write_enable[response_slot] = 1'b1; end
                end
            end
            if (bank_recovery_keep_count < occupancy_reg)
                ;
            ;
        end else begin
            bank_commit_fire = store_commit_valid_i && store_commit_ready_o;
            if (bank_commit_fire) begin store_commit_mem_write_data[commit_slot_select] = 1'b1; store_commit_mem_write_enable[commit_slot_select] = 1'b1; end

            for (retirement_slot = 0; retirement_slot < LSQ_ENTRIES; retirement_slot = retirement_slot + 1)
                for (retirement_lane = 0; retirement_lane < BE_WIDTH; retirement_lane = retirement_lane + 1)
                    if (valid_mem[retirement_slot] && load_mem[retirement_slot] &&
                        retire_valid_i[retirement_lane] &&
                        rob_tag_mem[retirement_slot] == retire_rob_tag_i[retirement_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH])
                        begin retired_mem_write_data[retirement_slot] = 1'b1; retired_mem_write_enable[retirement_slot] = 1'b1; end

            
            
            for (bank_update_slot = 0; bank_update_slot < LSQ_ENTRIES; bank_update_slot = bank_update_slot + 1) begin
                
                
                if ((STORE_ADDRESS_PROBE != 0) && early_addr_valid_i &&
                    tag_matches_slot(early_addr_tag_i, bank_update_slot) &&
                    store_mem[bank_update_slot] && !addr_ready_mem[bank_update_slot] &&
                    !request_sent_mem[bank_update_slot] && !complete_mem[bank_update_slot]) begin
                    begin addr_ready_mem_write_data[bank_update_slot] = 1'b1; addr_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                    begin addr_mem_write_data[bank_update_slot] = early_addr_i; addr_mem_write_enable[bank_update_slot] = 1'b1; end
                    if (mask_mem[bank_update_slot] == 4'b0)
                        begin mask_mem_write_data[bank_update_slot] = access_mask(size_mem[bank_update_slot]); mask_mem_write_enable[bank_update_slot] = 1'b1; end
                end
                for (bank_lane = 0; bank_lane < BE_WIDTH; bank_lane = bank_lane + 1) begin
                    if (addr_update_valid_i[bank_lane] && tag_matches_slot(addr_update_tag_i[(bank_lane*TAG_WIDTH) +: TAG_WIDTH], bank_update_slot)) begin
                        begin addr_ready_mem_write_data[bank_update_slot] = 1'b1; addr_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                        begin addr_mem_write_data[bank_update_slot] = addr_update_i[(bank_lane*32) +: 32]; addr_mem_write_enable[bank_update_slot] = 1'b1; end
                        if (mask_mem[bank_update_slot] == 4'b0 && store_mem[bank_update_slot])
                            begin mask_mem_write_data[bank_update_slot] = access_mask(size_mem[bank_update_slot]); mask_mem_write_enable[bank_update_slot] = 1'b1; end
                    end
                    if (data_update_valid_i[bank_lane] && tag_matches_slot(data_update_tag_i[(bank_lane*TAG_WIDTH) +: TAG_WIDTH], bank_update_slot)) begin
                        begin data_ready_mem_write_data[bank_update_slot] = 1'b1; data_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                        begin data_mem_write_data[bank_update_slot] = data_update_i[(bank_lane*32) +: 32]; data_mem_write_enable[bank_update_slot] = 1'b1; end
                        if (data_mask_update_i[(bank_lane*4) +: 4] != 4'b0)
                            begin mask_mem_write_data[bank_update_slot] = data_mask_update_i[(bank_lane*4) +: 4]; mask_mem_write_enable[bank_update_slot] = 1'b1; end
                    end
                    if (wakeup_valid_i[bank_lane] && tag_matches_slot(wakeup_tag_i[(bank_lane*TAG_WIDTH) +: TAG_WIDTH], bank_update_slot)) begin
                        begin data_ready_mem_write_data[bank_update_slot] = 1'b1; data_ready_mem_write_enable[bank_update_slot] = 1'b1; end
                        begin data_mem_write_data[bank_update_slot] = wakeup_value_i[(bank_lane*32) +: 32]; data_mem_write_enable[bank_update_slot] = 1'b1; end
                    end
                end
            end

            
            
            if (candidate_found && load_mem[candidate] && !request_sent_mem[candidate] && !complete_mem[candidate]) begin
                if ((fwd_mask & target_mask) == target_mask) begin
                    begin complete_value_mem_write_data[candidate] = format_relative_value(
                        fwd_data, size_mem[candidate], unsigned_mem[candidate]); complete_value_mem_write_enable[candidate] = 1'b1; end
                    begin complete_error_mem_write_data[candidate] = 1'b0; complete_error_mem_write_enable[candidate] = 1'b1; end
                    begin complete_mem_write_data[candidate] = 1'b1; complete_mem_write_enable[candidate] = 1'b1; end
                end
            end

            if (request_fire) begin
                begin request_sent_mem_write_data[candidate] = 1'b1; request_sent_mem_write_enable[candidate] = 1'b1; end
                if (load_mem[candidate]) begin
                    begin response_wait_mem_write_data[candidate] = 1'b1; response_wait_mem_write_enable[candidate] = 1'b1; end
                    begin forward_mask_mem_write_data[candidate] = fwd_mask; forward_mask_mem_write_enable[candidate] = 1'b1; end
                    begin forward_data_mem_write_data[candidate] = fwd_data; forward_data_mem_write_enable[candidate] = 1'b1; end
                end else begin
                    begin response_wait_mem_write_data[candidate] = 1'b1; response_wait_mem_write_enable[candidate] = 1'b1; end
                end
            end

            if (response_fire) begin
                bank_response_word = dcache_resp_line_valid_i ?
                    relative_data_from_line(dcache_resp_line_data_i, addr_mem[response_slot]) :
                    dcache_resp_word_data_i;
                bank_merged_word = (forward_data_mem[response_slot] &
                               expand_word_bytes(forward_mask_mem[response_slot])) |
                              (bank_response_word &
                               ~expand_word_bytes(forward_mask_mem[response_slot]));
                begin complete_value_mem_write_data[response_slot] = format_relative_value(
                    bank_merged_word, size_mem[response_slot], unsigned_mem[response_slot]); complete_value_mem_write_enable[response_slot] = 1'b1; end
                begin complete_error_mem_write_data[response_slot] = dcache_resp_error_i; complete_error_mem_write_enable[response_slot] = 1'b1; end
                begin complete_mem_write_data[response_slot] = 1'b1; complete_mem_write_enable[response_slot] = 1'b1; end
                begin response_wait_mem_write_data[response_slot] = 1'b0; response_wait_mem_write_enable[response_slot] = 1'b1; end
            end

            if (load_complete_valid_o && load_complete_ready_i)
                begin load_reported_mem_write_data[complete_slot_select] = 1'b1; load_reported_mem_write_enable[complete_slot_select] = 1'b1; end

            for (bank_slot = 0; bank_slot < LSQ_ENTRIES; bank_slot = bank_slot + 1) begin
                if (dcache_store_ack_valid_i && tag_matches_slot(dcache_store_ack_lsq_tag_i, bank_slot) &&
                    request_sent_mem[bank_slot] && response_wait_mem[bank_slot]) begin
                    begin store_ack_mem_write_data[bank_slot] = 1'b1; store_ack_mem_write_enable[bank_slot] = 1'b1; end
                    begin store_ack_error_mem_write_data[bank_slot] = dcache_store_ack_error_i; store_ack_error_mem_write_enable[bank_slot] = 1'b1; end
                    begin response_wait_mem_write_data[bank_slot] = 1'b0; response_wait_mem_write_enable[bank_slot] = 1'b1; end
                end
            end

            if ((occupancy_reg != 0) && valid_mem[head_reg] &&
                ((load_mem[head_reg] && complete_mem[head_reg] &&
                  (load_reported_mem[head_reg] ||
                   (load_complete_valid_o && load_complete_ready_i &&
                    (complete_slot_select == head_reg)))) ||
                 (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i))) begin
                begin valid_mem_write_data[head_reg] = 1'b0; valid_mem_write_enable[head_reg] = 1'b1; end
                begin request_sent_mem_write_data[head_reg] = 1'b0; request_sent_mem_write_enable[head_reg] = 1'b1; end
                begin response_wait_mem_write_data[head_reg] = 1'b0; response_wait_mem_write_enable[head_reg] = 1'b1; end
                begin complete_mem_write_data[head_reg] = 1'b0; complete_mem_write_enable[head_reg] = 1'b1; end
                begin load_reported_mem_write_data[head_reg] = 1'b0; load_reported_mem_write_enable[head_reg] = 1'b1; end
                begin store_ack_mem_write_data[head_reg] = 1'b0; store_ack_mem_write_enable[head_reg] = 1'b1; end
            end

            
            for (bank_lane = 0; bank_lane < BE_WIDTH; bank_lane = bank_lane + 1) begin
                if (alloc_fire_o[bank_lane]) begin
                    bank_alloc_slot = tail_reg + alloc_count_before_lane(bank_lane, alloc_fire_o);
                    if (bank_alloc_slot >= LSQ_ENTRIES) bank_alloc_slot = bank_alloc_slot - LSQ_ENTRIES;
                    bank_next_generation = generation_next_mem[bank_alloc_slot];
                    if (bank_next_generation == {GENERATION_WIDTH{1'b0}})
                        bank_next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                    begin generation_mem_write_data[bank_alloc_slot] = bank_next_generation; generation_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin generation_next_mem_write_data[bank_alloc_slot] = (bank_next_generation == {GENERATION_WIDTH{1'b1}}) ?
                        {{(GENERATION_WIDTH-1){1'b0}}, 1'b1} : bank_next_generation + 1'b1; generation_next_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin valid_mem_write_data[bank_alloc_slot] = 1'b1; valid_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin load_mem_write_data[bank_alloc_slot] = alloc_is_load_i[bank_lane]; load_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin store_mem_write_data[bank_alloc_slot] = alloc_is_store_i[bank_lane]; store_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin rob_tag_mem_write_data[bank_alloc_slot] = alloc_rob_tag_i[(bank_lane*ROB_TAG_WIDTH) +: ROB_TAG_WIDTH]; rob_tag_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin retired_mem_write_data[bank_alloc_slot] = 1'b0; retired_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin size_mem_write_data[bank_alloc_slot] = alloc_size_i[(bank_lane*2) +: 2]; size_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin unsigned_mem_write_data[bank_alloc_slot] = alloc_unsigned_i[bank_lane]; unsigned_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin addr_ready_mem_write_data[bank_alloc_slot] = alloc_addr_valid_i[bank_lane]; addr_ready_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin data_ready_mem_write_data[bank_alloc_slot] = alloc_data_valid_i[bank_lane] || alloc_is_load_i[bank_lane]; data_ready_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin addr_mem_write_data[bank_alloc_slot] = alloc_addr_i[(bank_lane*32) +: 32]; addr_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin data_mem_write_data[bank_alloc_slot] = alloc_store_data_i[(bank_lane*32) +: 32]; data_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin mask_mem_write_data[bank_alloc_slot] = (alloc_store_mask_i[(bank_lane*4) +: 4] != 4'b0) ?
                        alloc_store_mask_i[(bank_lane*4) +: 4] :
                        ((alloc_is_store_i[bank_lane] && alloc_addr_valid_i[bank_lane]) ?
                         access_mask(alloc_size_i[(bank_lane*2) +: 2]) : 4'b0); mask_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin request_sent_mem_write_data[bank_alloc_slot] = 1'b0; request_sent_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin response_wait_mem_write_data[bank_alloc_slot] = 1'b0; response_wait_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin complete_mem_write_data[bank_alloc_slot] = 1'b0; complete_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin load_reported_mem_write_data[bank_alloc_slot] = 1'b0; load_reported_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin complete_value_mem_write_data[bank_alloc_slot] = 32'b0; complete_value_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin complete_error_mem_write_data[bank_alloc_slot] = 1'b0; complete_error_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin forward_mask_mem_write_data[bank_alloc_slot] = 4'b0; forward_mask_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin forward_data_mem_write_data[bank_alloc_slot] = 32'b0; forward_data_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin store_commit_mem_write_data[bank_alloc_slot] = 1'b0; store_commit_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin store_ack_mem_write_data[bank_alloc_slot] = 1'b0; store_ack_mem_write_enable[bank_alloc_slot] = 1'b1; end
                    begin store_ack_error_mem_write_data[bank_alloc_slot] = 1'b0; store_ack_error_mem_write_enable[bank_alloc_slot] = 1'b1; end
                end
            end

            bank_alloc_count_calc = alloc_count_o;
            bank_pop_count_calc = ((occupancy_reg != 0) && valid_mem[head_reg] &&
                              ((load_mem[head_reg] && complete_mem[head_reg] &&
                                (load_reported_mem[head_reg] ||
                                 (load_complete_valid_o && load_complete_ready_i &&
                                  (complete_slot_select == head_reg)))) ||
                               (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i))) ? 1 : 0;
            ;
            ;
            ;
        end
    end

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
            
            
            
            
            recovery_branch_age = recovery_branch_age_parallel;
            recovery_keep_count = recovery_keep_tree[1];
            recovery_first_killed = recovery_kill_slot_tree[1];
            recovery_kill_found = recovery_kill_valid_tree[1];
            for (slot=0;slot<LSQ_ENTRIES;slot=slot+1) begin
                if(recovery_kill_parallel[slot]) begin
                    ; ;
                    ; ;
                    ; ;
                    ;
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
                if (recovery_entry_age < 0) recovery_entry_age = recovery_entry_age + ROB_ENTRIES;
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
        rv32_lsq_state_word #(.WIDTH(1)) valid_mem_owner (
            .clk_i(clk_i),.write_i(valid_mem_write_enable[storage_row]),
            .data_i(valid_mem_write_data[storage_row]),.data_o(valid_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) load_mem_owner (
            .clk_i(clk_i),.write_i(load_mem_write_enable[storage_row]),
            .data_i(load_mem_write_data[storage_row]),.data_o(load_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) store_mem_owner (
            .clk_i(clk_i),.write_i(store_mem_write_enable[storage_row]),
            .data_i(store_mem_write_data[storage_row]),.data_o(store_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(ROB_TAG_WIDTH-1+1)) rob_tag_mem_owner (
            .clk_i(clk_i),.write_i(rob_tag_mem_write_enable[storage_row]),
            .data_i(rob_tag_mem_write_data[storage_row]),.data_o(rob_tag_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) retired_mem_owner (
            .clk_i(clk_i),.write_i(retired_mem_write_enable[storage_row]),
            .data_i(retired_mem_write_data[storage_row]),.data_o(retired_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(GENERATION_WIDTH-1+1)) generation_mem_owner (
            .clk_i(clk_i),.write_i(generation_mem_write_enable[storage_row]),
            .data_i(generation_mem_write_data[storage_row]),.data_o(generation_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(GENERATION_WIDTH-1+1)) generation_next_mem_owner (
            .clk_i(clk_i),.write_i(generation_next_mem_write_enable[storage_row]),
            .data_i(generation_next_mem_write_data[storage_row]),.data_o(generation_next_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1+1)) size_mem_owner (
            .clk_i(clk_i),.write_i(size_mem_write_enable[storage_row]),
            .data_i(size_mem_write_data[storage_row]),.data_o(size_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) unsigned_mem_owner (
            .clk_i(clk_i),.write_i(unsigned_mem_write_enable[storage_row]),
            .data_i(unsigned_mem_write_data[storage_row]),.data_o(unsigned_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) addr_ready_mem_owner (
            .clk_i(clk_i),.write_i(addr_ready_mem_write_enable[storage_row]),
            .data_i(addr_ready_mem_write_data[storage_row]),.data_o(addr_ready_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) data_ready_mem_owner (
            .clk_i(clk_i),.write_i(data_ready_mem_write_enable[storage_row]),
            .data_i(data_ready_mem_write_data[storage_row]),.data_o(data_ready_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(31+1)) addr_mem_owner (
            .clk_i(clk_i),.write_i(addr_mem_write_enable[storage_row]),
            .data_i(addr_mem_write_data[storage_row]),.data_o(addr_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(31+1)) data_mem_owner (
            .clk_i(clk_i),.write_i(data_mem_write_enable[storage_row]),
            .data_i(data_mem_write_data[storage_row]),.data_o(data_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(3+1)) mask_mem_owner (
            .clk_i(clk_i),.write_i(mask_mem_write_enable[storage_row]),
            .data_i(mask_mem_write_data[storage_row]),.data_o(mask_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) request_sent_mem_owner (
            .clk_i(clk_i),.write_i(request_sent_mem_write_enable[storage_row]),
            .data_i(request_sent_mem_write_data[storage_row]),.data_o(request_sent_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) response_wait_mem_owner (
            .clk_i(clk_i),.write_i(response_wait_mem_write_enable[storage_row]),
            .data_i(response_wait_mem_write_data[storage_row]),.data_o(response_wait_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) complete_mem_owner (
            .clk_i(clk_i),.write_i(complete_mem_write_enable[storage_row]),
            .data_i(complete_mem_write_data[storage_row]),.data_o(complete_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) load_reported_mem_owner (
            .clk_i(clk_i),.write_i(load_reported_mem_write_enable[storage_row]),
            .data_i(load_reported_mem_write_data[storage_row]),.data_o(load_reported_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(31+1)) complete_value_mem_owner (
            .clk_i(clk_i),.write_i(complete_value_mem_write_enable[storage_row]),
            .data_i(complete_value_mem_write_data[storage_row]),.data_o(complete_value_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) complete_error_mem_owner (
            .clk_i(clk_i),.write_i(complete_error_mem_write_enable[storage_row]),
            .data_i(complete_error_mem_write_data[storage_row]),.data_o(complete_error_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(3+1)) forward_mask_mem_owner (
            .clk_i(clk_i),.write_i(forward_mask_mem_write_enable[storage_row]),
            .data_i(forward_mask_mem_write_data[storage_row]),.data_o(forward_mask_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(31+1)) forward_data_mem_owner (
            .clk_i(clk_i),.write_i(forward_data_mem_write_enable[storage_row]),
            .data_i(forward_data_mem_write_data[storage_row]),.data_o(forward_data_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) store_commit_mem_owner (
            .clk_i(clk_i),.write_i(store_commit_mem_write_enable[storage_row]),
            .data_i(store_commit_mem_write_data[storage_row]),.data_o(store_commit_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) store_ack_mem_owner (
            .clk_i(clk_i),.write_i(store_ack_mem_write_enable[storage_row]),
            .data_i(store_ack_mem_write_data[storage_row]),.data_o(store_ack_mem[storage_row]));
        rv32_lsq_state_word #(.WIDTH(1)) store_ack_error_mem_owner (
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
(* keep_hierarchy = 1 *)
module rv32_lsq_state_word #(parameter integer WIDTH=32) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    always @(posedge clk_i) if(write_i) data_o<=data_i;
endmodule
