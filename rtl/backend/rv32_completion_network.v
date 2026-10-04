`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Completion/CDB network: BYPASS=0 retains the completion FIFO, BYPASS=1
// retains the legacy single-CDB path, and BYPASS=2 directly arbitrates up to
// CDB_WIDTH producer results. Producers must retain each result until ready;
// a stalled direct lane locks its source and full tag, not another payload copy.
module rv32_completion_network #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer CDB_WIDTH = BE_WIDTH,
    parameter integer SOURCES = 5,
    parameter integer FIFO_DEPTH = 16,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer BYPASS = 0,
    parameter integer SLOT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH),
    parameter integer COUNT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH + 1),
    parameter integer READ_MATCH_PORTS = 0,
    parameter integer READ_MATCH_COUNT = (READ_MATCH_PORTS>0)?READ_MATCH_PORTS:1,
    parameter integer LATE_ELIGIBILITY_SOURCE = -1,
    parameter integer READ_DIRECT_VALUE = 0,
    parameter integer DIRECT_PRF_ENABLE = 0
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire                         kill_valid_i,
    input  wire [FIFO_DEPTH-1:0]        kill_mask_i,
    input  wire [SOURCES-1:0]           producer_valid_i,
    output reg  [SOURCES-1:0]           producer_ready_o,
    input  wire [(SOURCES*TAG_WIDTH)-1:0] producer_tag_i,
    input  wire [(SOURCES*PHYS_ADDR_WIDTH)-1:0] producer_phys_rd_i,
    input  wire [(SOURCES*32)-1:0]       producer_value_i,
    input  wire [(SOURCES*32)-1:0]       producer_addr_i,
    input  wire [(SOURCES*32)-1:0]       producer_branch_target_i,
    input  wire [(SOURCES*32)-1:0]       producer_store_data_i,
    input  wire [SOURCES-1:0]           producer_rd_we_i,
    input  wire [SOURCES-1:0]           producer_is_store_i,
    input  wire [SOURCES-1:0]           producer_is_branch_i,
    input  wire [SOURCES-1:0]           producer_branch_taken_i,
    input  wire [SOURCES-1:0]           producer_redirect_valid_i,
    input  wire [SOURCES-1:0]           producer_is_memory_i,
    input  wire [SOURCES-1:0]           producer_is_load_i,
    input  wire [SOURCES-1:0]           producer_target_live_i,
    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i,

    output reg  [BE_WIDTH-1:0]          cdb_valid_o,
    input  wire [BE_WIDTH-1:0]          cdb_ready_i,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] cdb_tag_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] cdb_phys_rd_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_value_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_addr_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_branch_target_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_store_data_o,
    output reg  [BE_WIDTH-1:0]          cdb_rd_we_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_store_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_branch_o,
    output reg  [BE_WIDTH-1:0]          cdb_branch_taken_o,
    output reg  [BE_WIDTH-1:0]          cdb_redirect_valid_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_memory_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_load_o,

    output wire [BE_WIDTH-1:0]          prf_write_valid_o,
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] prf_write_tag_o,
    output wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] prf_write_phys_rd_o,
    output wire [(BE_WIDTH*32)-1:0]      prf_write_value_o,
    output wire [BE_WIDTH-1:0]          rob_ready_valid_o,
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] rob_ready_tag_o,
    output wire [(BE_WIDTH*32)-1:0]      rob_ready_value_o,
    output wire [BE_WIDTH-1:0]          wakeup_valid_o,
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] wakeup_tag_o,
    output wire [(BE_WIDTH*32)-1:0]      wakeup_value_o,
    output wire [FIFO_DEPTH-1:0]        entry_valid_o,
    output wire [(FIFO_DEPTH*TAG_WIDTH)-1:0] entry_tag_o,
    output wire [COUNT_WIDTH-1:0]       occupancy_o,
    input wire [READ_MATCH_COUNT*PHYS_ADDR_WIDTH-1:0] read_match_phys_i,
    output wire [READ_MATCH_COUNT*BE_WIDTH-1:0] prf_read_match_o,
    input wire [BE_WIDTH-1:0] bypass_write_valid_i,
    input wire bypass_last_override_i,
    output wire [READ_MATCH_COUNT-1:0] direct_read_valid_o,
    output wire [READ_MATCH_COUNT*32-1:0] direct_read_value_o
);
    reg valid_mem [0:FIFO_DEPTH-1];
    reg [TAG_WIDTH-1:0] tag_mem [0:FIFO_DEPTH-1];
    reg [PHYS_ADDR_WIDTH-1:0] phys_mem [0:FIFO_DEPTH-1];
    reg [31:0] value_mem [0:FIFO_DEPTH-1];
    reg [31:0] addr_mem [0:FIFO_DEPTH-1];
    reg [31:0] branch_target_mem [0:FIFO_DEPTH-1];
    reg [31:0] store_data_mem [0:FIFO_DEPTH-1];
    reg rd_we_mem [0:FIFO_DEPTH-1];
    reg store_mem [0:FIFO_DEPTH-1];
    reg branch_mem [0:FIFO_DEPTH-1];
    reg branch_taken_mem [0:FIFO_DEPTH-1];
    reg redirect_mem [0:FIFO_DEPTH-1];
    reg memory_mem [0:FIFO_DEPTH-1];
    reg load_mem [0:FIFO_DEPTH-1];
    reg live_mem [0:FIFO_DEPTH-1];
    reg [SLOT_WIDTH-1:0] head_reg, tail_reg;
    reg [COUNT_WIDTH-1:0] count_reg;
    integer source;
    integer lane;
    integer slot;
    integer enq_count;
    integer pop_count;
    integer free_slots;
    integer enq_slot;
    integer pop_slot;
    reg prefix_open;
    reg pop_break;
    reg [BE_WIDTH-1:0] pop_fire;
    reg [SOURCES-1:0] source_fire;
    reg bypass_selected;
    reg [TAG_WIDTH-1:0] bypass_source_tag;
    localparam integer SOURCE_WIDTH = (SOURCES <= 1) ? 1 : $clog2(SOURCES);
    reg [SOURCE_WIDTH-1:0] direct_rr_reg, direct_rr_next;
    reg [CDB_WIDTH-1:0] direct_hold_valid;
    reg [SOURCE_WIDTH-1:0] direct_hold_source [0:CDB_WIDTH-1];
    reg [TAG_WIDTH-1:0] direct_hold_tag [0:CDB_WIDTH-1];
    reg [CDB_WIDTH-1:0] direct_selected_valid;
    reg [SOURCE_WIDTH-1:0] direct_selected_source [0:CDB_WIDTH-1];
    wire [SOURCES-1:0] direct_eligible, direct_used;
    integer direct_source, direct_lane, direct_scan, direct_candidate;
    integer direct_state_lane;
    wire [COUNT_WIDTH-1:0] occupancy_wire = BYPASS ? {COUNT_WIDTH{1'b0}} : count_reg;
    assign occupancy_o = occupancy_wire;

    genvar entry_index;
    generate
        for (entry_index = 0; entry_index < FIFO_DEPTH; entry_index = entry_index + 1) begin : g_entry_state
            assign entry_valid_o[entry_index] = BYPASS ? 1'b0 :
                (valid_mem[entry_index] && live_mem[entry_index]);
            assign entry_tag_o[(entry_index*TAG_WIDTH) +: TAG_WIDTH] =
                BYPASS ? {TAG_WIDTH{1'b0}} : tag_mem[entry_index];
        end
    endgenerate


    // Reserve held sources using static tag comparisons. Each remaining
    // source computes its rank in the round-robin order in parallel. Free
    // lane numbers select ranks, rather than re-scanning a variable-indexed
    // source array once for each lane.
    localparam integer RANK_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES+1);
    localparam integer RANK_LEAVES=1<<$clog2(SOURCES);
    wire [SOURCES-1:0] selected_mask [0:CDB_WIDTH-1];
    wire [CDB_WIDTH*SOURCES-1:0] selected_flat;
    wire [CDB_WIDTH*SOURCE_WIDTH-1:0] held_sources_flat;
    wire [CDB_WIDTH*TAG_WIDTH-1:0] held_tags_flat;
    genvar rank_source,rank_lane,late_word;
    generate
        for(rank_source=0;rank_source<SOURCES;rank_source=rank_source+1) begin:g_direct_eligibility
            // Full normal ROB authority remains on this FINAL decision.
            assign direct_eligible[rank_source]=producer_valid_i[rank_source] &&
                producer_target_live_i[rank_source] && producer_tag_i[rank_source*TAG_WIDTH] &&
                (!live_tag_valid_i || producer_tag_i[rank_source*TAG_WIDTH +: TAG_WIDTH]==live_tag_i);
        end
        for(rank_lane=0;rank_lane<CDB_WIDTH;rank_lane=rank_lane+1) begin:g_rank_ports
            assign held_sources_flat[rank_lane*SOURCE_WIDTH +: SOURCE_WIDTH]=direct_hold_source[rank_lane];
            assign held_tags_flat[rank_lane*TAG_WIDTH +: TAG_WIDTH]=direct_hold_tag[rank_lane];
            assign selected_mask[rank_lane]=selected_flat[rank_lane*SOURCES +: SOURCES];
        end
        if(BYPASS==2 && LATE_ELIGIBILITY_SOURCE>=0 && LATE_ELIGIBILITY_SOURCE<SOURCES) begin:g_late_eligibility
            wire [SOURCES-1:0] eligible_without,eligible_with;
            wire [CDB_WIDTH*SOURCES-1:0] selected_without,selected_with;
            localparam integer SELECT_WORDS=(CDB_WIDTH*SOURCES+15)/16;
            wire [SELECT_WORDS-1:0] late_views;
            for(rank_source=0;rank_source<SOURCES;rank_source=rank_source+1) begin:g_hypothesis
                if(rank_source==LATE_ELIGIBILITY_SOURCE) begin:g_late
                    assign eligible_without[rank_source]=1'b0;
                    assign eligible_with[rank_source]=1'b1;
                end else begin:g_other
                    assign eligible_without[rank_source]=direct_eligible[rank_source];
                    assign eligible_with[rank_source]=direct_eligible[rank_source];
                end
            end
            // Both hypotheses apply the original round-robin, held full-tag
            // match, rank and free-lane rules. No source can publish until the
            // original late eligibility chooses its matching hypothesis.
            rv32_frequency_completion_grants #(.SOURCES(SOURCES),.CDB_WIDTH(CDB_WIDTH),.TAG_WIDTH(TAG_WIDTH)) absent (
                .cursor_i(direct_rr_reg),.eligible_i(eligible_without),
                .held_valid_i(direct_hold_valid),.held_sources_i(held_sources_flat),
                .held_tags_i(held_tags_flat),.producer_tag_i(producer_tag_i),.selected_o(selected_without));
            rv32_frequency_completion_grants #(.SOURCES(SOURCES),.CDB_WIDTH(CDB_WIDTH),.TAG_WIDTH(TAG_WIDTH)) present (
                .cursor_i(direct_rr_reg),.eligible_i(eligible_with),
                .held_valid_i(direct_hold_valid),.held_sources_i(held_sources_flat),
                .held_tags_i(held_tags_flat),.producer_tag_i(producer_tag_i),.selected_o(selected_with));
            rv32_frequency_control_tree #(.LEAVES(SELECT_WORDS)) late_tree (
                .signal_i(direct_eligible[LATE_ELIGIBILITY_SOURCE]),.views_o(late_views));
            for(late_word=0;late_word<SELECT_WORDS;late_word=late_word+1) begin:g_word
                localparam integer LOW=late_word*16;
                localparam integer BITS=(CDB_WIDTH*SOURCES-LOW>=16)?16:CDB_WIDTH*SOURCES-LOW;
                assign selected_flat[LOW +: BITS]=late_views[late_word] ?
                    selected_with[LOW +: BITS] : selected_without[LOW +: BITS];
            end
        end else begin:g_original_eligibility
            rv32_frequency_completion_grants #(.SOURCES(SOURCES),.CDB_WIDTH(CDB_WIDTH),.TAG_WIDTH(TAG_WIDTH)) original (
                .cursor_i(direct_rr_reg),.eligible_i(direct_eligible),
                .held_valid_i(direct_hold_valid),.held_sources_i(held_sources_flat),
                .held_tags_i(held_tags_flat),.producer_tag_i(producer_tag_i),.selected_o(selected_flat));
        end
    endgenerate
    always @* begin
        direct_selected_valid=0;
        direct_rr_next=direct_rr_reg;
        for(direct_lane=0;direct_lane<CDB_WIDTH;direct_lane=direct_lane+1) begin
            direct_selected_source[direct_lane]=0;
            direct_selected_valid[direct_lane]=|selected_mask[direct_lane];
            for(direct_source=0;direct_source<SOURCES;direct_source=direct_source+1)
                direct_selected_source[direct_lane]=direct_selected_source[direct_lane] |
                    ({SOURCE_WIDTH{selected_mask[direct_lane][direct_source]}} & direct_source);
            // Retain the exact old cursor rule: last accepted lane wins.
            if(direct_selected_valid[direct_lane] && cdb_ready_i[direct_lane]) begin
                if(direct_selected_source[direct_lane]==SOURCES-1) direct_rr_next=0;
                else direct_rr_next=direct_selected_source[direct_lane]+1'b1;
            end
        end
    end


    // Equality can run alongside full-tag authority and arbitration. Route
    // its single-bit result with the EXACT same one-hot source grant as the
    // physical destination payload, instead of comparing after that payload mux.
    // Query-dependent bits are never retained in a completion/hold packet.
    genvar match_source,match_read,match_lane,match_node;
    generate if(BYPASS==2 && READ_MATCH_PORTS>0) begin:g_direct_read_match
        wire [READ_MATCH_COUNT-1:0] source_match [0:SOURCES-1];
        wire [CDB_WIDTH*SOURCES*READ_MATCH_COUNT-1:0] match_grant;
        for(match_source=0;match_source<SOURCES;match_source=match_source+1) begin:g_source
            for(match_read=0;match_read<READ_MATCH_COUNT;match_read=match_read+1) begin:g_query
                assign source_match[match_source][match_read]=
                    producer_phys_rd_i[match_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==
                    read_match_phys_i[match_read*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
            end
            for(match_lane=0;match_lane<CDB_WIDTH;match_lane=match_lane+1) begin:g_grant
                // One bounded grant leaf controls at most sixteen match bits.
                localparam integer WORDS=(READ_MATCH_COUNT+15)/16;
                wire [WORDS-1:0] grant_views;
                genvar match_word;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) grant_tree (
                    .signal_i(selected_mask[match_lane][match_source] && !reset_i && !flush_i),
                    .views_o(grant_views));
                for(match_word=0;match_word<WORDS;match_word=match_word+1) begin:g_word
                    localparam integer LOW=match_word*16;
                    localparam integer BITS=(READ_MATCH_COUNT-LOW>=16)?16:READ_MATCH_COUNT-LOW;
                    assign match_grant[(match_lane*SOURCES+match_source)*READ_MATCH_COUNT+LOW +: BITS]={BITS{grant_views[match_word]}};
                end
            end
        end
        for(match_read=0;match_read<READ_MATCH_COUNT;match_read=match_read+1) begin:g_read
            for(match_lane=0;match_lane<BE_WIDTH;match_lane=match_lane+1) begin:g_lane
                if(match_lane<CDB_WIDTH) begin:g_present
                    wire match_tree [1:2*RANK_LEAVES-1];
                    for(match_source=0;match_source<RANK_LEAVES;match_source=match_source+1) begin:g_leaf
                        if(match_source<SOURCES) begin:g_source
                            assign match_tree[RANK_LEAVES+match_source]=
                                match_grant[(match_lane*SOURCES+match_source)*READ_MATCH_COUNT+match_read] && source_match[match_source][match_read];
                        end else begin:g_padding
                            assign match_tree[RANK_LEAVES+match_source]=1'b0;
                        end
                    end
                    for(match_node=1;match_node<RANK_LEAVES;match_node=match_node+1) begin:g_reduce
                        assign match_tree[match_node]=match_tree[2*match_node] || match_tree[2*match_node+1];
                    end
                    assign prf_read_match_o[match_read*BE_WIDTH+match_lane]=match_tree[1];
                end else begin:g_unused_lane
                    assign prf_read_match_o[match_read*BE_WIDTH+match_lane]=1'b0;
                end
            end
        end

        // Select the last matching ACTUAL PRF write lane, then route its
        // original producer value directly. This factors two serial payload
        // muxes into one, while preserving PRF write-valid and lane priority.
        if(READ_DIRECT_VALUE!=0) begin:g_direct_values
            genvar value_read,value_lane,value_source,value_node;
            for(value_read=0;value_read<READ_MATCH_COUNT;value_read=value_read+1) begin:g_read
                wire [BE_WIDTH-1:0] lane_hit,lane_grant;
                wire [SOURCES-1:0] source_grant;
                wire [31:0] value_tree [1:2*RANK_LEAVES-1];
                for(value_lane=0;value_lane<BE_WIDTH;value_lane=value_lane+1) begin:g_lane
                    if(value_lane<CDB_WIDTH) begin:g_present
                        // Branch-link publication overrides the last active
                        // lane; even a nonmatching link must hide its normal
                        // completion's physical destination and value.
                        assign lane_hit[value_lane]=prf_read_match_o[value_read*BE_WIDTH+value_lane] &&
                            bypass_write_valid_i[value_lane] &&
                            ((value_lane==CDB_WIDTH-1) ? !bypass_last_override_i : 1'b1);
                    end else begin:g_unused
                        assign lane_hit[value_lane]=1'b0;
                    end
                    if(value_lane==BE_WIDTH-1) begin:g_last
                        assign lane_grant[value_lane]=lane_hit[value_lane];
                    end else begin:g_priority
                        assign lane_grant[value_lane]=lane_hit[value_lane] && !(|lane_hit[BE_WIDTH-1:value_lane+1]);
                    end
                end
                assign direct_read_valid_o[value_read]=|lane_hit;
                for(value_source=0;value_source<RANK_LEAVES;value_source=value_source+1) begin:g_source
                    if(value_source<SOURCES) begin:g_present
                        wire [CDB_WIDTH-1:0] chosen_lanes;
                        wire [1:0] data_views;
                        for(value_lane=0;value_lane<CDB_WIDTH;value_lane=value_lane+1) begin:g_owner
                            assign chosen_lanes[value_lane]=lane_grant[value_lane] && selected_mask[value_lane][value_source];
                        end
                        assign source_grant[value_source]=|chosen_lanes;
                        rv32_frequency_control_tree #(.LEAVES(2)) data_tree (
                            .signal_i(source_grant[value_source]),.views_o(data_views));
                        assign value_tree[RANK_LEAVES+value_source]={
                            {16{data_views[1]}} & producer_value_i[value_source*32+16 +: 16],
                            {16{data_views[0]}} & producer_value_i[value_source*32 +: 16]};
                    end else begin:g_padding
                        assign value_tree[RANK_LEAVES+value_source]=0;
                    end
                end
                for(value_node=1;value_node<RANK_LEAVES;value_node=value_node+1) begin:g_reduce
                    assign value_tree[value_node]=value_tree[2*value_node] | value_tree[2*value_node+1];
                end
                assign direct_read_value_o[value_read*32 +: 32]=value_tree[1];
            end
        end else begin:g_no_direct_values
            assign direct_read_valid_o=0;
            assign direct_read_value_o=0;
        end
    end else begin:g_no_direct_read_match
        assign prf_read_match_o=0;
        assign direct_read_valid_o=0;
        assign direct_read_value_o=0;
    end endgenerate

    localparam integer DIRECT_META_WIDTH=TAG_WIDTH+PHYS_ADDR_WIDTH+7;
    wire [DIRECT_META_WIDTH-1:0] direct_meta [0:CDB_WIDTH-1];
    wire [31:0] direct_value [0:CDB_WIDTH-1],direct_target [0:CDB_WIDTH-1];
    wire [63:0] direct_memory [0:CDB_WIDTH-1];
    genvar payload_lane,payload_source,payload_node,payload_word;
    generate for(payload_lane=0;payload_lane<CDB_WIDTH;payload_lane=payload_lane+1) begin:g_direct_payload
        wire [DIRECT_META_WIDTH-1:0] meta_tree [1:2*RANK_LEAVES-1];
        wire [31:0] value_tree [1:2*RANK_LEAVES-1],target_tree [1:2*RANK_LEAVES-1];
        wire [63:0] memory_tree [1:2*RANK_LEAVES-1];
        for(payload_source=0;payload_source<RANK_LEAVES;payload_source=payload_source+1) begin:g_source
            if(payload_source<SOURCES) begin:g_live
                localparam integer DATA_WIDTH=DIRECT_META_WIDTH+128;
                localparam integer WORDS=(DATA_WIDTH+15)/16;
                wire [WORDS-1:0] selected_views;
                wire [DATA_WIDTH-1:0] data={
                    producer_tag_i[payload_source*TAG_WIDTH +: TAG_WIDTH],
                    producer_phys_rd_i[payload_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    producer_rd_we_i[payload_source] && !producer_is_store_i[payload_source],
                    producer_is_store_i[payload_source],producer_is_branch_i[payload_source],
                    producer_branch_taken_i[payload_source],producer_redirect_valid_i[payload_source],
                    producer_is_memory_i[payload_source],producer_is_load_i[payload_source],
                    producer_value_i[payload_source*32 +: 32],producer_addr_i[payload_source*32 +: 32],
                    producer_store_data_i[payload_source*32 +: 32],producer_branch_target_i[payload_source*32 +: 32]};
                wire [DATA_WIDTH-1:0] selected_data;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(selected_mask[payload_lane][payload_source] && !reset_i && !flush_i),
                    .views_o(selected_views));
                for(payload_word=0;payload_word<WORDS;payload_word=payload_word+1) begin:g_word
                    localparam integer LOW=payload_word*16;
                    localparam integer BITS=DATA_WIDTH-LOW>=16?16:DATA_WIDTH-LOW;
                    assign selected_data[LOW +: BITS]={BITS{selected_views[payload_word]}} & data[LOW +: BITS];
                end
                assign meta_tree[RANK_LEAVES+payload_source]=selected_data[128 +: DIRECT_META_WIDTH];
                assign value_tree[RANK_LEAVES+payload_source]=selected_data[96 +: 32];
                assign memory_tree[RANK_LEAVES+payload_source]=selected_data[32 +: 64];
                assign target_tree[RANK_LEAVES+payload_source]=selected_data[0 +: 32];
            end else begin:g_zero
                assign meta_tree[RANK_LEAVES+payload_source]=0;
                assign value_tree[RANK_LEAVES+payload_source]=0;
                assign memory_tree[RANK_LEAVES+payload_source]=0;
                assign target_tree[RANK_LEAVES+payload_source]=0;
            end
        end
        for(payload_node=1;payload_node<RANK_LEAVES;payload_node=payload_node+1) begin:g_or
            assign meta_tree[payload_node]=meta_tree[2*payload_node]|meta_tree[2*payload_node+1];
            assign value_tree[payload_node]=value_tree[2*payload_node]|value_tree[2*payload_node+1];
            assign memory_tree[payload_node]=memory_tree[2*payload_node]|memory_tree[2*payload_node+1];
            assign target_tree[payload_node]=target_tree[2*payload_node]|target_tree[2*payload_node+1];
        end
        assign direct_meta[payload_lane]=meta_tree[1];
        assign direct_value[payload_lane]=value_tree[1];
        assign direct_memory[payload_lane]=memory_tree[1];
        assign direct_target[payload_lane]=target_tree[1];
    end endgenerate

    always @(posedge clk_i) begin
        if (BYPASS != 2 || reset_i || flush_i) begin
            direct_rr_reg <= 0;
            direct_hold_valid <= 0;
            for (direct_state_lane = 0; direct_state_lane < CDB_WIDTH;
                 direct_state_lane = direct_state_lane + 1) begin
                direct_hold_source[direct_state_lane] <= 0;
                direct_hold_tag[direct_state_lane] <= 0;
            end
        end else begin
            direct_rr_reg <= direct_rr_next;
            for (direct_state_lane = 0; direct_state_lane < CDB_WIDTH;
                 direct_state_lane = direct_state_lane + 1) begin
                direct_hold_valid[direct_state_lane] <=
                    direct_selected_valid[direct_state_lane] && !cdb_ready_i[direct_state_lane];
                if (direct_selected_valid[direct_state_lane] && !cdb_ready_i[direct_state_lane]) begin
                    direct_hold_source[direct_state_lane] <= direct_selected_source[direct_state_lane];
                    direct_hold_tag[direct_state_lane] <=
                        direct_meta[direct_state_lane][PHYS_ADDR_WIDTH+7 +: TAG_WIDTH];
                end
            end
        end
    end

    always @* begin
        producer_ready_o = {SOURCES{1'b0}};
        source_fire = {SOURCES{1'b0}};
        bypass_selected = 1'b0;
        bypass_source_tag = {TAG_WIDTH{1'b0}};
        prefix_open = 1'b1;
        enq_count = 0;
        free_slots = FIFO_DEPTH - count_reg;
        for (source = 0; source < SOURCES; source = source + 1) begin
            if (prefix_open && producer_valid_i[source]) begin
                if (!producer_target_live_i[source]) begin
                    // A generation-stale execution result must be consumed
                    // without entering the FIFO; otherwise the functional
                    // unit holds it forever and blocks all future issues.
                    producer_ready_o[source] = !flush_i;
                end else if (enq_count < free_slots) begin
                    producer_ready_o[source] = !flush_i;
                    source_fire[source] = !flush_i;
                    enq_count = enq_count + 1;
                end else begin
                    prefix_open = 1'b0;
                end
            end else if (producer_valid_i[source]) begin
                prefix_open = 1'b0;
            end
        end

        cdb_valid_o = {BE_WIDTH{1'b0}};
        cdb_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        cdb_phys_rd_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        cdb_value_o = {(BE_WIDTH*32){1'b0}};
        cdb_addr_o = {(BE_WIDTH*32){1'b0}};
        cdb_branch_target_o = {(BE_WIDTH*32){1'b0}};
        cdb_store_data_o = {(BE_WIDTH*32){1'b0}};
        cdb_rd_we_o = {BE_WIDTH{1'b0}};
        cdb_is_store_o = {BE_WIDTH{1'b0}};
        cdb_is_branch_o = {BE_WIDTH{1'b0}};
        cdb_branch_taken_o = {BE_WIDTH{1'b0}};
        cdb_redirect_valid_o = {BE_WIDTH{1'b0}};
        cdb_is_memory_o = {BE_WIDTH{1'b0}};
        cdb_is_load_o = {BE_WIDTH{1'b0}};
        pop_fire = {BE_WIDTH{1'b0}};
        pop_count = 0;
        pop_slot = 0;
        pop_break = 1'b0;
        for (lane = 0; lane < CDB_WIDTH; lane = lane + 1) begin
            if (!pop_break) begin
                pop_slot = head_reg + pop_count;
                if (pop_slot >= FIFO_DEPTH) pop_slot = pop_slot - FIFO_DEPTH;
                if (!flush_i && valid_mem[pop_slot] && live_mem[pop_slot] &&
                    (!live_tag_valid_i || tag_mem[pop_slot] == live_tag_i)) begin
                    cdb_valid_o[lane] = 1'b1;
                    cdb_tag_o[(lane*TAG_WIDTH) +: TAG_WIDTH] = tag_mem[pop_slot];
                    cdb_phys_rd_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = phys_mem[pop_slot];
                    cdb_value_o[(lane*32) +: 32] = value_mem[pop_slot];
                    cdb_addr_o[(lane*32) +: 32] = addr_mem[pop_slot];
                    cdb_branch_target_o[(lane*32) +: 32] = branch_target_mem[pop_slot];
                    cdb_store_data_o[(lane*32) +: 32] = store_data_mem[pop_slot];
                    cdb_rd_we_o[lane] = rd_we_mem[pop_slot] && !store_mem[pop_slot];
                    cdb_is_store_o[lane] = store_mem[pop_slot];
                    cdb_is_branch_o[lane] = branch_mem[pop_slot];
                    cdb_branch_taken_o[lane] = branch_taken_mem[pop_slot];
                    cdb_redirect_valid_o[lane] = redirect_mem[pop_slot];
                    cdb_is_memory_o[lane] = memory_mem[pop_slot];
                    cdb_is_load_o[lane] = load_mem[pop_slot];
                    if (cdb_ready_i[lane]) begin
                        pop_fire[lane] = 1'b1;
                        pop_count = pop_count + 1;
                    end else begin
                        pop_break = 1'b1;
                    end
                end else if (valid_mem[pop_slot]) begin
                    // Stale/invalid head entries are discarded before arbitration.
                    pop_fire[lane] = 1'b1;
                    pop_count = pop_count + 1;
                end else begin
                    pop_break = 1'b1;
                end
            end
        end

        // Minimum-area single-CDB mode. Producers already retain their result
        // until ready, so they directly provide the only required storage.
        if (BYPASS == 1) begin
            producer_ready_o = {SOURCES{1'b0}};
            source_fire = {SOURCES{1'b0}};
            cdb_valid_o = {BE_WIDTH{1'b0}};
            cdb_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
            cdb_phys_rd_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
            cdb_value_o = {(BE_WIDTH*32){1'b0}};
            cdb_addr_o = {(BE_WIDTH*32){1'b0}};
            cdb_branch_target_o = {(BE_WIDTH*32){1'b0}};
            cdb_store_data_o = {(BE_WIDTH*32){1'b0}};
            cdb_rd_we_o = {BE_WIDTH{1'b0}};
            cdb_is_store_o = {BE_WIDTH{1'b0}};
            cdb_is_branch_o = {BE_WIDTH{1'b0}};
            cdb_branch_taken_o = {BE_WIDTH{1'b0}};
            cdb_redirect_valid_o = {BE_WIDTH{1'b0}};
            cdb_is_memory_o = {BE_WIDTH{1'b0}};
            cdb_is_load_o = {BE_WIDTH{1'b0}};
            pop_fire = {BE_WIDTH{1'b0}};
            enq_count = 0;
            pop_count = 0;
            bypass_selected = 1'b0;
            bypass_source_tag = {TAG_WIDTH{1'b0}};
            for (source = 0; source < SOURCES; source = source + 1) begin
                bypass_source_tag = producer_tag_i[(source*TAG_WIDTH) +: TAG_WIDTH];
                if (producer_valid_i[source] &&
                    (!producer_target_live_i[source] ||
                     (live_tag_valid_i && bypass_source_tag != live_tag_i))) begin
                    producer_ready_o[source] = !flush_i;
                end else if (!bypass_selected && producer_valid_i[source]) begin
                    bypass_selected = 1'b1;
                    cdb_valid_o[0] = !flush_i;
                    cdb_tag_o[0 +: TAG_WIDTH] = bypass_source_tag;
                    cdb_phys_rd_o[0 +: PHYS_ADDR_WIDTH] =
                        producer_phys_rd_i[(source*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    cdb_value_o[0 +: 32] = producer_value_i[(source*32) +: 32];
                    cdb_addr_o[0 +: 32] = producer_addr_i[(source*32) +: 32];
                    cdb_branch_target_o[0 +: 32] = producer_branch_target_i[(source*32) +: 32];
                    cdb_store_data_o[0 +: 32] = producer_store_data_i[(source*32) +: 32];
                    cdb_rd_we_o[0] = producer_rd_we_i[source] && !producer_is_store_i[source];
                    cdb_is_store_o[0] = producer_is_store_i[source];
                    cdb_is_branch_o[0] = producer_is_branch_i[source];
                    cdb_branch_taken_o[0] = producer_branch_taken_i[source];
                    cdb_redirect_valid_o[0] = producer_redirect_valid_i[source];
                    cdb_is_memory_o[0] = producer_is_memory_i[source];
                    cdb_is_load_o[0] = producer_is_load_i[source];
                    producer_ready_o[source] = !flush_i && cdb_ready_i[0];
                end
            end
        end
        if (BYPASS == 2) begin
            // No FIFO admission or prefix stall in this mode. Each result
            // handshakes on its own CDB lane; stale results drain even when
            // every live lane is blocked. Recovery supplies target_live, as
            // kill_mask only describes entries in the legacy FIFO.
            producer_ready_o = {SOURCES{1'b0}};
            source_fire = {SOURCES{1'b0}};
            cdb_valid_o = {BE_WIDTH{1'b0}};
            cdb_tag_o = 0; cdb_phys_rd_o = 0; cdb_value_o = 0;
            cdb_addr_o = 0; cdb_branch_target_o = 0; cdb_store_data_o = 0;
            cdb_rd_we_o = 0; cdb_is_store_o = 0; cdb_is_branch_o = 0;
            cdb_branch_taken_o = 0; cdb_redirect_valid_o = 0;
            cdb_is_memory_o = 0; cdb_is_load_o = 0;
            pop_fire = 0; enq_count = 0; pop_count = 0;
            for (source = 0; source < SOURCES; source = source + 1)
                if (producer_valid_i[source] && !direct_eligible[source])
                    producer_ready_o[source] = !reset_i && !flush_i;
            for(lane=0;lane<CDB_WIDTH;lane=lane+1) begin
                cdb_valid_o[lane]=!reset_i && !flush_i && direct_selected_valid[lane];
                {cdb_tag_o[lane*TAG_WIDTH +: TAG_WIDTH],
                 cdb_phys_rd_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                 cdb_rd_we_o[lane],cdb_is_store_o[lane],cdb_is_branch_o[lane],
                 cdb_branch_taken_o[lane],cdb_redirect_valid_o[lane],
                 cdb_is_memory_o[lane],cdb_is_load_o[lane]}=direct_meta[lane];
                cdb_value_o[lane*32 +: 32]=direct_value[lane];
                {cdb_addr_o[lane*32 +: 32],cdb_store_data_o[lane*32 +: 32]}=direct_memory[lane];
                cdb_branch_target_o[lane*32 +: 32]=direct_target[lane];
                for(source=0;source<SOURCES;source=source+1)
                    if(!reset_i && !flush_i && selected_mask[lane][source])
                        producer_ready_o[source]=cdb_ready_i[lane];
            end
        end
    end

    // In direct mode the same write-enable is the OR of selected writable
    // sources. Resolve this single-bit field beside arbitration instead of
    // waiting for the wide metadata payload's distribution/readback.
    genvar write_enable_lane,write_enable_source;
    generate if(BYPASS==2 && DIRECT_PRF_ENABLE!=0) begin:g_local_prf_write_enable
        for(write_enable_lane=0;write_enable_lane<BE_WIDTH;write_enable_lane=write_enable_lane+1) begin:g_lane
            if(write_enable_lane<CDB_WIDTH) begin:g_active
                wire [SOURCES-1:0] writing_sources;
                for(write_enable_source=0;write_enable_source<SOURCES;write_enable_source=write_enable_source+1) begin:g_source
                    assign writing_sources[write_enable_source]=selected_mask[write_enable_lane][write_enable_source] &&
                        producer_rd_we_i[write_enable_source] && !producer_is_store_i[write_enable_source];
                end
                assign prf_write_valid_o[write_enable_lane]=!reset_i && !flush_i && (|writing_sources);
            end else begin:g_unused
                assign prf_write_valid_o[write_enable_lane]=1'b0;
            end
        end
    end else begin:g_original_prf_write_enable
        assign prf_write_valid_o = cdb_valid_o & cdb_rd_we_o;
    end endgenerate
    assign prf_write_tag_o = cdb_tag_o;
    assign prf_write_phys_rd_o = cdb_phys_rd_o;
    assign prf_write_value_o = cdb_value_o;
    assign rob_ready_valid_o = cdb_valid_o;
    assign rob_ready_tag_o = cdb_tag_o;
    assign rob_ready_value_o = cdb_value_o;
    assign wakeup_valid_o = cdb_valid_o & cdb_rd_we_o;
    assign wakeup_tag_o = cdb_tag_o;
    assign wakeup_value_o = cdb_value_o;

    always @(posedge clk_i) begin
        if (BYPASS != 0) begin
            head_reg <= 0;
            tail_reg <= 0;
            count_reg <= 0;
            for (slot = 0; slot < FIFO_DEPTH; slot = slot + 1) begin
                valid_mem[slot] <= 1'b0;
                live_mem[slot] <= 1'b0;
            end
        end else if (reset_i || flush_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            count_reg <= 0;
            for (slot = 0; slot < FIFO_DEPTH; slot = slot + 1) begin
                valid_mem[slot] <= 1'b0;
                live_mem[slot] <= 1'b0;
            end
        end else begin
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                if (pop_fire[lane]) begin
                    pop_slot = head_reg + lane;
                    if (pop_slot >= FIFO_DEPTH) pop_slot = pop_slot - FIFO_DEPTH;
                    valid_mem[pop_slot] <= 1'b0;
                    live_mem[pop_slot] <= 1'b0;
                end
            end
            enq_slot = tail_reg;
            for (source = 0; source < SOURCES; source = source + 1) begin
                if (source_fire[source]) begin
                    if (enq_slot >= FIFO_DEPTH) enq_slot = enq_slot - FIFO_DEPTH;
                    valid_mem[enq_slot] <= 1'b1;
                    live_mem[enq_slot] <= producer_target_live_i[source] && producer_tag_i[(source*TAG_WIDTH)];
                    tag_mem[enq_slot] <= producer_tag_i[(source*TAG_WIDTH) +: TAG_WIDTH];
                    phys_mem[enq_slot] <= producer_phys_rd_i[(source*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    value_mem[enq_slot] <= producer_value_i[(source*32) +: 32];
                    addr_mem[enq_slot] <= producer_addr_i[(source*32) +: 32];
                    branch_target_mem[enq_slot] <= producer_branch_target_i[(source*32) +: 32];
                    store_data_mem[enq_slot] <= producer_store_data_i[(source*32) +: 32];
                    rd_we_mem[enq_slot] <= producer_rd_we_i[source];
                    store_mem[enq_slot] <= producer_is_store_i[source];
                    branch_mem[enq_slot] <= producer_is_branch_i[source];
                    branch_taken_mem[enq_slot] <= producer_branch_taken_i[source];
                    redirect_mem[enq_slot] <= producer_redirect_valid_i[source];
                    memory_mem[enq_slot] <= producer_is_memory_i[source];
                    load_mem[enq_slot] <= producer_is_load_i[source];
                    enq_slot = enq_slot + 1;
                end
            end
            head_reg <= head_reg + pop_count;
            if (head_reg + pop_count >= FIFO_DEPTH) head_reg <= head_reg + pop_count - FIFO_DEPTH;
            tail_reg <= tail_reg + enq_count;
            if (tail_reg + enq_count >= FIFO_DEPTH) tail_reg <= tail_reg + enq_count - FIFO_DEPTH;
            count_reg <= count_reg - pop_count + enq_count;
            if (kill_valid_i) begin
                for (slot = 0; slot < FIFO_DEPTH; slot = slot + 1)
                    if (kill_mask_i[slot]) live_mem[slot] <= 1'b0;
            end
        end
    end

    initial begin
        if (SOURCES < 1 || BYPASS < 0 || BYPASS > 2) begin
            $display("ERROR: SOURCES must be positive and BYPASS must be 0, 1 or 2");
            $finish;
        end
        if (CDB_WIDTH < 1 || CDB_WIDTH > BE_WIDTH) begin
            $display("ERROR: CDB_WIDTH must be in 1..BE_WIDTH");
            $finish;
        end
    end
endmodule
