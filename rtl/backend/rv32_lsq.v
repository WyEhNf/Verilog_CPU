`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Ordered load/store queue.  Addresses and store data may arrive after
// allocation; loads inspect older stores before issuing a cache request.
// Store requests are gated by the ROB commit handshake and are only emitted
// for the LSQ head, so memory visibility remains precise.
module rv32_lsq #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer LSQ_ENTRIES = 8,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer ROB_TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
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
    input  wire [(BE_WIDTH*128)-1:0]     alloc_store_data_i,
    input  wire [(BE_WIDTH*16)-1:0]      alloc_store_mask_i,

    input  wire [BE_WIDTH-1:0]           addr_update_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] addr_update_tag_i,
    input  wire [(BE_WIDTH*32)-1:0]      addr_update_i,
    input  wire [BE_WIDTH-1:0]           data_update_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] data_update_tag_i,
    input  wire [(BE_WIDTH*128)-1:0]     data_update_i,
    input  wire [(BE_WIDTH*16)-1:0]      data_mask_update_i,
    input  wire [BE_WIDTH-1:0]           wakeup_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] wakeup_tag_i,
    input  wire [(BE_WIDTH*128)-1:0]     wakeup_value_i,

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
    localparam integer BYTES_WIDTH = 3;
    localparam integer TAG_SLOT_LSB = 3;
    localparam integer TAG_GEN_LSB = TAG_SLOT_LSB + SLOT_WIDTH;
    localparam integer ROB_SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES);

    reg valid_mem [0:LSQ_ENTRIES-1];
    reg load_mem [0:LSQ_ENTRIES-1];
    reg store_mem [0:LSQ_ENTRIES-1];
    reg [ROB_TAG_WIDTH-1:0] rob_tag_mem [0:LSQ_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_mem [0:LSQ_ENTRIES-1];
    reg [GENERATION_WIDTH-1:0] generation_next_mem [0:LSQ_ENTRIES-1];
    reg [1:0] size_mem [0:LSQ_ENTRIES-1];
    reg unsigned_mem [0:LSQ_ENTRIES-1];
    reg addr_ready_mem [0:LSQ_ENTRIES-1];
    reg data_ready_mem [0:LSQ_ENTRIES-1];
    reg [31:0] addr_mem [0:LSQ_ENTRIES-1];
    reg [127:0] data_mem [0:LSQ_ENTRIES-1];
    reg [15:0] mask_mem [0:LSQ_ENTRIES-1];
    reg request_sent_mem [0:LSQ_ENTRIES-1];
    reg response_wait_mem [0:LSQ_ENTRIES-1];
    reg complete_mem [0:LSQ_ENTRIES-1];
    reg [31:0] complete_value_mem [0:LSQ_ENTRIES-1];
    reg complete_error_mem [0:LSQ_ENTRIES-1];
    reg [15:0] forward_mask_mem [0:LSQ_ENTRIES-1];
    reg [127:0] forward_data_mem [0:LSQ_ENTRIES-1];
    reg store_commit_mem [0:LSQ_ENTRIES-1];
    reg store_ack_mem [0:LSQ_ENTRIES-1];
    reg store_ack_error_mem [0:LSQ_ENTRIES-1];

    reg [SLOT_WIDTH-1:0] head_reg;
    reg [SLOT_WIDTH-1:0] tail_reg;
    reg [COUNT_WIDTH-1:0] occupancy_reg;

    integer i;
    integer lane;
    integer slot;
    integer scan;
    integer candidate;
    integer candidate_age;
    integer age;
    integer older_age;
    integer alloc_count_calc;
    integer free_count_calc;
    integer pop_count_calc;
    integer alloc_slot;
    integer update_slot;
    integer response_slot;
    integer entry_rob_slot;
    integer recovery_branch_slot;
    integer recovery_branch_age;
    integer recovery_entry_age;
    integer recovery_keep_count;
    integer recovery_first_killed;
    integer recovery_kill_found;
    integer byte_index;
    integer byte_count;
    integer byte_offset;
    integer req_offset;
    reg prefix_open;
    reg candidate_found;
    reg blocked;
    reg [15:0] target_mask;
    reg [15:0] fwd_mask;
    reg [127:0] fwd_data;
    reg [15:0] overlap;
    reg [127:0] response_line;
    reg [127:0] merged_line;
    reg [31:0] extracted_value;
    reg [7:0] extracted_byte;
    reg request_fire;
    reg response_match;
    reg response_fire;
    reg commit_match;
    reg commit_fire;
    reg load_pop_fire;
    reg store_pop_fire;
    reg [GENERATION_WIDTH-1:0] next_generation;

    function [127:0] expand_bytes;
        input [15:0] mask;
        begin
            expand_bytes = {{8{mask[15]}}, {8{mask[14]}}, {8{mask[13]}}, {8{mask[12]}},
                            {8{mask[11]}}, {8{mask[10]}}, {8{mask[9]}},  {8{mask[8]}},
                            {8{mask[7]}},  {8{mask[6]}},  {8{mask[5]}},  {8{mask[4]}},
                            {8{mask[3]}},  {8{mask[2]}},  {8{mask[1]}},  {8{mask[0]}}};
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

    function [15:0] size_mask;
        input [31:0] address;
        input [1:0] size;
        integer n;
        integer first;
        integer count;
        begin
            size_mask = 16'b0;
            first = address[3:0];
            case (size)
                2'd0: count = 1;
                2'd1: count = 2;
                default: count = 4;
            endcase
            for (n = 0; n < 16; n = n + 1)
                if ((n >= first) && (n < first + count)) size_mask[n] = 1'b1;
        end
    endfunction

    function [31:0] extract_value;
        input [127:0] line_data;
        input [31:0] address;
        input [1:0] size;
        input unsigned_load;
        integer n;
        integer first;
        integer count;
        reg [31:0] result;
        reg [7:0] b;
        begin
            first = address[3:0];
            case (size)
                2'd0: count = 1;
                2'd1: count = 2;
                default: count = 4;
            endcase
            result = 32'b0;
            for (n = 0; n < 4; n = n + 1) begin
                if (n < count) begin
                    b = line_data[((first + n) * 8) +: 8];
                    result[(n*8) +: 8] = b;
                end
            end
            if (!unsigned_load && (count < 4) && result[(count*8)-1]) begin
                for (n = 0; n < 4; n = n + 1)
                    if (n >= count) result[(n*8) +: 8] = 8'hff;
            end
            extract_value = result;
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

    initial begin
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid LSQ BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if ((LSQ_ENTRIES < 2) || ((LSQ_ENTRIES & (LSQ_ENTRIES - 1)) != 0)) begin
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
        blocked = 1'b0;
        target_mask = 16'b0;
        fwd_mask = 16'b0;
        fwd_data = 128'b0;
        overlap = 16'b0;
        alloc_slot = 0;
        older_age = 0;
        free_count_calc = LSQ_ENTRIES - occupancy_reg;
        alloc_fire_o = {BE_WIDTH{1'b0}};
        alloc_count_o = {ALLOC_COUNT_WIDTH{1'b0}};
        alloc_lsq_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        prefix_open = 1'b1;
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

        // The ROB only presents a store at its head.  LSQ also checks that
        // the corresponding entry is its own head and operands are ready.
        store_commit_ready_o = 1'b0;
        commit_match = 1'b0;
        if (!flush_i && occupancy_reg != 0 && valid_mem[head_reg] &&
            store_mem[head_reg] && addr_ready_mem[head_reg] &&
            data_ready_mem[head_reg] && !store_commit_mem[head_reg] &&
            (rob_tag_mem[head_reg] == store_commit_rob_tag_i)) begin
            store_commit_ready_o = 1'b1;
            commit_match = 1'b1;
        end

        // Select the oldest eligible memory operation.  A younger load is
        // blocked by an older unknown address or an overlapping store whose
        // data is not ready; ready bytes are accumulated for forwarding.
        candidate_found = 1'b0;
        candidate = 0;
        candidate_age = LSQ_ENTRIES + 1;
        for (scan = 0; scan < LSQ_ENTRIES; scan = scan + 1) begin
            age = scan - head_reg;
            if (age < 0) age = age + LSQ_ENTRIES;
            if (age < occupancy_reg && valid_mem[scan] && !candidate_found) begin
                blocked = 1'b0;
                if (load_mem[scan] && addr_ready_mem[scan] && !request_sent_mem[scan] && !complete_mem[scan]) begin
                    target_mask = size_mask(addr_mem[scan], size_mem[scan]);
                    fwd_mask = 16'b0;
                    fwd_data = 128'b0;
                    for (older_age = 0; older_age < LSQ_ENTRIES; older_age = older_age + 1) begin
                        if (older_age < age) begin
                            i = head_reg + older_age;
                            if (i >= LSQ_ENTRIES) i = i - LSQ_ENTRIES;
                            if (valid_mem[i] && store_mem[i]) begin
                                if (!addr_ready_mem[i]) begin
                                    blocked = 1'b1;
                                end else if ((addr_mem[i][31:4] == addr_mem[scan][31:4])) begin
                                    if (data_ready_mem[i]) begin
                                        // Word-level merge: same youngest-wins
                                        // per-byte result as the old byte loop,
                                        // but every fwd bit is assigned under
                                        // one uniform condition per store so
                                        // synthesis proc builds one decoder
                                        // instead of one per byte.
                                        overlap = mask_mem[i] & target_mask;
                                        fwd_data = (data_mem[i] & expand_bytes(overlap)) |
                                                   (fwd_data & ~expand_bytes(overlap));
                                        fwd_mask = fwd_mask | overlap;
                                    end else if ((mask_mem[i] & target_mask) != 0) begin
                                        blocked = 1'b1;
                                    end
                                end
                            end
                        end
                    end
                    if (!blocked) begin
                        candidate_found = 1'b1;
                        candidate = scan;
                        candidate_age = age;
                    end
                end else if (store_mem[scan] && scan == head_reg && addr_ready_mem[scan] &&
                             data_ready_mem[scan] && store_commit_mem[scan] && !request_sent_mem[scan]) begin
                    candidate_found = 1'b1;
                    candidate = scan;
                    candidate_age = age;
                end
            end
        end

        dcache_req_valid_o = 1'b0;
        dcache_req_is_load_o = 1'b0;
        dcache_req_is_store_o = 1'b0;
        dcache_req_addr_o = 32'b0;
        dcache_req_size_o = 2'b0;
        dcache_req_unsigned_o = 1'b0;
        dcache_req_mask_o = 16'b0;
        dcache_req_wdata_o = 128'b0;
        dcache_req_rob_tag_o = {ROB_TAG_WIDTH{1'b0}};
        dcache_req_lsq_tag_o = {TAG_WIDTH{1'b0}};
        request_fire = 1'b0;
        if (!flush_i && candidate_found && !response_wait_mem[candidate]) begin
            if (load_mem[candidate]) begin
                target_mask = size_mask(addr_mem[candidate], size_mem[candidate]);
                fwd_mask = 16'b0;
                fwd_data = 128'b0;
                for (older_age = 0; older_age < LSQ_ENTRIES; older_age = older_age + 1) begin
                    if (older_age < candidate_age) begin
                        i = head_reg + older_age;
                        if (i >= LSQ_ENTRIES) i = i - LSQ_ENTRIES;
                        if (valid_mem[i] && store_mem[i] && addr_ready_mem[i] && data_ready_mem[i] &&
                            (addr_mem[i][31:4] == addr_mem[candidate][31:4])) begin
                            overlap = mask_mem[i] & target_mask;
                            fwd_data = (data_mem[i] & expand_bytes(overlap)) |
                                       (fwd_data & ~expand_bytes(overlap));
                            fwd_mask = fwd_mask | overlap;
                        end
                    end
                end
                if ((fwd_mask & target_mask) != target_mask) begin
                    dcache_req_valid_o = 1'b1;
                    dcache_req_is_load_o = 1'b1;
                    dcache_req_addr_o = addr_mem[candidate];
                    dcache_req_size_o = size_mem[candidate];
                    dcache_req_unsigned_o = unsigned_mem[candidate];
                    dcache_req_mask_o = target_mask & ~fwd_mask;
                    dcache_req_wdata_o = fwd_data;
                    dcache_req_rob_tag_o = rob_tag_mem[candidate];
                    dcache_req_lsq_tag_o = make_lsq_tag(candidate, generation_mem[candidate]);
                    request_fire = dcache_req_ready_i;
                end
            end else begin
                dcache_req_valid_o = 1'b1;
                dcache_req_is_store_o = 1'b1;
                dcache_req_addr_o = addr_mem[candidate];
                dcache_req_size_o = size_mem[candidate];
                dcache_req_unsigned_o = 1'b0;
                dcache_req_mask_o = mask_mem[candidate];
                dcache_req_wdata_o = data_mem[candidate];
                dcache_req_rob_tag_o = rob_tag_mem[candidate];
                dcache_req_lsq_tag_o = make_lsq_tag(candidate, generation_mem[candidate]);
                request_fire = dcache_req_ready_i;
            end
        end

        // A fully covered load never touches the cache.  It becomes a
        // completion at the next edge, preserving the same handshake timing.
        load_pop_fire = 1'b0;
        store_pop_fire = 1'b0;
        if (load_complete_valid_o && load_complete_ready_i) load_pop_fire = 1'b1;
        if (store_ack_valid_o && store_ack_ready_i) store_pop_fire = 1'b1;
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
        if (occupancy_reg != 0 && valid_mem[head_reg]) begin
            if (load_mem[head_reg] && complete_mem[head_reg]) begin
                load_complete_valid_o = 1'b1;
                load_complete_rob_tag_o = rob_tag_mem[head_reg];
                load_complete_lsq_tag_o = make_lsq_tag(head_reg, generation_mem[head_reg]);
                load_complete_value_o = complete_value_mem[head_reg];
                load_complete_error_o = complete_error_mem[head_reg];
            end else if (store_mem[head_reg] && store_ack_mem[head_reg]) begin
                store_ack_valid_o = 1'b1;
                store_ack_rob_tag_o = rob_tag_mem[head_reg];
                store_ack_lsq_tag_o = make_lsq_tag(head_reg, generation_mem[head_reg]);
                store_ack_error_o = store_ack_error_mem[head_reg];
            end
        end
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            occupancy_reg <= 0;
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                valid_mem[slot] <= 1'b0;
                generation_mem[slot] <= {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                generation_next_mem[slot] <= {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                request_sent_mem[slot] <= 1'b0;
                response_wait_mem[slot] <= 1'b0;
                complete_mem[slot] <= 1'b0;
                store_commit_mem[slot] <= 1'b0;
                store_ack_mem[slot] <= 1'b0;
            end
        end else if (flush_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            occupancy_reg <= 0;
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                valid_mem[slot] <= 1'b0;
                request_sent_mem[slot] <= 1'b0;
                response_wait_mem[slot] <= 1'b0;
                complete_mem[slot] <= 1'b0;
                store_commit_mem[slot] <= 1'b0;
                store_ack_mem[slot] <= 1'b0;
            end
        end else if (recovery_valid_i) begin
            // LSQ allocation follows program order, so entries younger than
            // the recovering branch form a suffix of the live queue.  Trim
            // that suffix in place and leave the older prefix/tag mappings
            // untouched for the ROB's pending stores and loads.
            recovery_branch_slot = recovery_tag_i[3 +: ROB_SLOT_WIDTH];
            recovery_branch_age = recovery_branch_slot - recovery_head_i;
            if (recovery_branch_age < 0) recovery_branch_age = recovery_branch_age + ROB_ENTRIES;
            recovery_keep_count = 0;
            recovery_first_killed = tail_reg;
            recovery_kill_found = 0;
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                scan = head_reg + slot;
                if (scan >= LSQ_ENTRIES) scan = scan - LSQ_ENTRIES;
                if ((slot < occupancy_reg) && valid_mem[scan]) begin
                    entry_rob_slot = rob_tag_mem[scan][3 +: ROB_SLOT_WIDTH];
                    recovery_entry_age = entry_rob_slot - recovery_head_i;
                    if (recovery_entry_age < 0) recovery_entry_age = recovery_entry_age + ROB_ENTRIES;
                    if ((recovery_entry_age > recovery_branch_age) &&
                        (recovery_entry_age < recovery_occupancy_i)) begin
                        if (!recovery_kill_found) begin
                            recovery_first_killed = scan;
                            recovery_kill_found = 1;
                        end
                        valid_mem[scan] <= 1'b0;
                        request_sent_mem[scan] <= 1'b0;
                        response_wait_mem[scan] <= 1'b0;
                        complete_mem[scan] <= 1'b0;
                        store_commit_mem[scan] <= 1'b0;
                        store_ack_mem[scan] <= 1'b0;
                    end else begin
                        recovery_keep_count = recovery_keep_count + 1;
                    end
                end
            end
            // Stores are architectural before they enter the D-cache.  If an
            // acknowledgement coincides with recovery, retain it for the
            // surviving store instead of consuming and losing it.
            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                if (dcache_store_ack_valid_i &&
                    tag_matches_slot(dcache_store_ack_lsq_tag_i, slot) &&
                    request_sent_mem[slot] && response_wait_mem[slot]) begin
                    store_ack_mem[slot] <= 1'b1;
                    store_ack_error_mem[slot] <= dcache_store_ack_error_i;
                    response_wait_mem[slot] <= 1'b0;
                end
            end
            // A load response is also consumed by the cache on this edge.
            // Record it only when its ROB entry is in the retained prefix;
            // wrong-path responses are intentionally drained and discarded.
            if (response_fire) begin
                entry_rob_slot = rob_tag_mem[response_slot][3 +: ROB_SLOT_WIDTH];
                recovery_entry_age = entry_rob_slot - recovery_head_i;
                if (recovery_entry_age < 0) recovery_entry_age = recovery_entry_age + ROB_ENTRIES;
                if (!((recovery_entry_age > recovery_branch_age) &&
                      (recovery_entry_age < recovery_occupancy_i))) begin
                    response_line = dcache_resp_line_valid_i ? dcache_resp_line_data_i :
                                    {96'b0, dcache_resp_word_data_i};
                    merged_line = response_line;
                    for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                        if (forward_mask_mem[response_slot][byte_index])
                            merged_line[(byte_index*8) +: 8] =
                                forward_data_mem[response_slot][(byte_index*8) +: 8];
                    complete_value_mem[response_slot] <= extract_value(
                        merged_line, addr_mem[response_slot], size_mem[response_slot],
                        unsigned_mem[response_slot]);
                    complete_error_mem[response_slot] <= dcache_resp_error_i;
                    complete_mem[response_slot] <= 1'b1;
                    response_wait_mem[response_slot] <= 1'b0;
                end
            end
            if (recovery_keep_count < occupancy_reg)
                tail_reg <= recovery_first_killed[SLOT_WIDTH-1:0];
            occupancy_reg <= recovery_keep_count;
        end else begin
            commit_fire = store_commit_valid_i && store_commit_ready_o;
            if (commit_fire) store_commit_mem[head_reg] <= 1'b1;

            // Independent address/data wakeups are tag-qualified.  An old
            // response cannot update a reused LSQ slot after wrap/flush.
            for (update_slot = 0; update_slot < LSQ_ENTRIES; update_slot = update_slot + 1) begin
                for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                    if (addr_update_valid_i[lane] && tag_matches_slot(addr_update_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        addr_ready_mem[update_slot] <= 1'b1;
                        addr_mem[update_slot] <= addr_update_i[(lane*32) +: 32];
                        if (mask_mem[update_slot] == 16'b0 && store_mem[update_slot])
                            mask_mem[update_slot] <= size_mask(addr_update_i[(lane*32) +: 32], size_mem[update_slot]);
                    end
                    if (data_update_valid_i[lane] && tag_matches_slot(data_update_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        data_ready_mem[update_slot] <= 1'b1;
                        data_mem[update_slot] <= data_update_i[(lane*128) +: 128];
                        if (data_mask_update_i[(lane*16) +: 16] != 16'b0)
                            mask_mem[update_slot] <= data_mask_update_i[(lane*16) +: 16];
                    end
                    if (wakeup_valid_i[lane] && tag_matches_slot(wakeup_tag_i[(lane*TAG_WIDTH) +: TAG_WIDTH], update_slot)) begin
                        data_ready_mem[update_slot] <= 1'b1;
                        data_mem[update_slot] <= wakeup_value_i[(lane*128) +: 128];
                    end
                end
            end

            // A fully forwarded load is marked complete without a cache trip.
            if (candidate_found && load_mem[candidate] && !request_sent_mem[candidate] && !complete_mem[candidate]) begin
                target_mask = size_mask(addr_mem[candidate], size_mem[candidate]);
                fwd_mask = 16'b0;
                fwd_data = 128'b0;
                for (older_age = 0; older_age < LSQ_ENTRIES; older_age = older_age + 1) begin
                    if (older_age < candidate_age) begin
                        i = head_reg + older_age;
                        if (i >= LSQ_ENTRIES) i = i - LSQ_ENTRIES;
                        if (valid_mem[i] && store_mem[i] && addr_ready_mem[i] && data_ready_mem[i] &&
                            (addr_mem[i][31:4] == addr_mem[candidate][31:4])) begin
                            for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                                if (mask_mem[i][byte_index] && target_mask[byte_index]) begin
                                    fwd_mask[byte_index] = 1'b1;
                                    fwd_data[(byte_index*8) +: 8] = data_mem[i][(byte_index*8) +: 8];
                                end
                        end
                    end
                end
                if ((fwd_mask & target_mask) == target_mask) begin
                    merged_line = fwd_data;
                    complete_value_mem[candidate] <= extract_value(merged_line, addr_mem[candidate], size_mem[candidate], unsigned_mem[candidate]);
                    complete_error_mem[candidate] <= 1'b0;
                    complete_mem[candidate] <= 1'b1;
                end
            end

            if (request_fire) begin
                request_sent_mem[candidate] <= 1'b1;
                if (load_mem[candidate]) begin
                    response_wait_mem[candidate] <= 1'b1;
                    forward_mask_mem[candidate] <= fwd_mask;
                    forward_data_mem[candidate] <= fwd_data;
                end else begin
                    response_wait_mem[candidate] <= 1'b1;
                end
            end

            if (response_fire) begin
                response_line = dcache_resp_line_valid_i ? dcache_resp_line_data_i : {96'b0, dcache_resp_word_data_i};
                merged_line = response_line;
                for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                    if (forward_mask_mem[response_slot][byte_index])
                        merged_line[(byte_index*8) +: 8] = forward_data_mem[response_slot][(byte_index*8) +: 8];
                complete_value_mem[response_slot] <= extract_value(merged_line, addr_mem[response_slot], size_mem[response_slot], unsigned_mem[response_slot]);
                complete_error_mem[response_slot] <= dcache_resp_error_i;
                complete_mem[response_slot] <= 1'b1;
                response_wait_mem[response_slot] <= 1'b0;
            end

            for (slot = 0; slot < LSQ_ENTRIES; slot = slot + 1) begin
                if (dcache_store_ack_valid_i && tag_matches_slot(dcache_store_ack_lsq_tag_i, slot) &&
                    request_sent_mem[slot] && response_wait_mem[slot]) begin
                    store_ack_mem[slot] <= 1'b1;
                    store_ack_error_mem[slot] <= dcache_store_ack_error_i;
                    response_wait_mem[slot] <= 1'b0;
                end
            end

            if ((occupancy_reg != 0) && valid_mem[head_reg] &&
                ((load_mem[head_reg] && complete_mem[head_reg] && load_complete_ready_i) ||
                 (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i))) begin
                valid_mem[head_reg] <= 1'b0;
                request_sent_mem[head_reg] <= 1'b0;
                response_wait_mem[head_reg] <= 1'b0;
                complete_mem[head_reg] <= 1'b0;
                store_ack_mem[head_reg] <= 1'b0;
            end

            // Allocate the accepted prefix at tail.
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                if (alloc_fire_o[lane]) begin
                    alloc_slot = tail_reg + alloc_count_before_lane(lane, alloc_fire_o);
                    if (alloc_slot >= LSQ_ENTRIES) alloc_slot = alloc_slot - LSQ_ENTRIES;
                    next_generation = generation_next_mem[alloc_slot];
                    if (next_generation == {GENERATION_WIDTH{1'b0}})
                        next_generation = {{(GENERATION_WIDTH-1){1'b0}}, 1'b1};
                    generation_mem[alloc_slot] <= next_generation;
                    generation_next_mem[alloc_slot] <= (next_generation == {GENERATION_WIDTH{1'b1}}) ?
                        {{(GENERATION_WIDTH-1){1'b0}}, 1'b1} : next_generation + 1'b1;
                    valid_mem[alloc_slot] <= 1'b1;
                    load_mem[alloc_slot] <= alloc_is_load_i[lane];
                    store_mem[alloc_slot] <= alloc_is_store_i[lane];
                    rob_tag_mem[alloc_slot] <= alloc_rob_tag_i[(lane*ROB_TAG_WIDTH) +: ROB_TAG_WIDTH];
                    size_mem[alloc_slot] <= alloc_size_i[(lane*2) +: 2];
                    unsigned_mem[alloc_slot] <= alloc_unsigned_i[lane];
                    addr_ready_mem[alloc_slot] <= alloc_addr_valid_i[lane];
                    data_ready_mem[alloc_slot] <= alloc_data_valid_i[lane] || alloc_is_load_i[lane];
                    addr_mem[alloc_slot] <= alloc_addr_i[(lane*32) +: 32];
                    data_mem[alloc_slot] <= alloc_store_data_i[(lane*128) +: 128];
                    mask_mem[alloc_slot] <= (alloc_store_mask_i[(lane*16) +: 16] != 16'b0) ?
                        alloc_store_mask_i[(lane*16) +: 16] :
                        ((alloc_is_store_i[lane] && alloc_addr_valid_i[lane]) ?
                         size_mask(alloc_addr_i[(lane*32) +: 32], alloc_size_i[(lane*2) +: 2]) : 16'b0);
                    request_sent_mem[alloc_slot] <= 1'b0;
                    response_wait_mem[alloc_slot] <= 1'b0;
                    complete_mem[alloc_slot] <= 1'b0;
                    complete_value_mem[alloc_slot] <= 32'b0;
                    complete_error_mem[alloc_slot] <= 1'b0;
                    forward_mask_mem[alloc_slot] <= 16'b0;
                    forward_data_mem[alloc_slot] <= 128'b0;
                    store_commit_mem[alloc_slot] <= 1'b0;
                    store_ack_mem[alloc_slot] <= 1'b0;
                    store_ack_error_mem[alloc_slot] <= 1'b0;
                end
            end

            alloc_count_calc = alloc_count_o;
            pop_count_calc = ((occupancy_reg != 0) && valid_mem[head_reg] &&
                              ((load_mem[head_reg] && complete_mem[head_reg] && load_complete_ready_i) ||
                               (store_mem[head_reg] && store_ack_mem[head_reg] && store_ack_ready_i))) ? 1 : 0;
            head_reg <= advance_slot(head_reg, pop_count_calc);
            tail_reg <= advance_slot(tail_reg, alloc_count_calc);
            occupancy_reg <= occupancy_reg - pop_count_calc + alloc_count_calc;
        end
    end

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
