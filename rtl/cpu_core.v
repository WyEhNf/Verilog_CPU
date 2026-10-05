`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Parameterized RV32IM out-of-order top-level. Frontend bundles are decoded
// lane-wise and a contiguous prefix is dispatched to the backend each cycle.
module cpu_core #(
    parameter integer DECODE_PIPELINE = 0, ISSUE_PIPELINE = 0,
    parameter integer ICACHE_MSHR_STATIC_WRITES = 0,
    parameter integer ICACHE_MSHR_STATE_BANKS = 0,
    parameter integer FRONTEND_QUEUE_PAYLOAD_BANKS = 0,
    parameter integer FRONTEND_RESPONSE_BYPASS = 0,
    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 0,
    parameter integer FRONTEND_REDIRECT_REQUEST = 0,
    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 0,
    parameter integer FRONTEND_RAS_PREDECODE = 0,
    parameter integer FRONTEND_RAS_PARALLEL_CONTROL = 0,
    parameter integer RAS_REPEAT_COMPRESSION = 0,
    // Compare possible call return PCs before late accepted-call selection.
    parameter integer RAS_REPEAT_MATCH_PREDECODE = 0,
    parameter integer RAS_REPEAT_COUNTER_BITS = 6,
    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 0,
    parameter integer FRONTEND_DIRECT_WORD_BOUNDS = 0,
    parameter integer DCACHE_LOCAL_SRAM_COMMANDS = 0,
    parameter integer DCACHE_WAY_PARALLEL_QUERY = 0,
    parameter integer DCACHE_HIT_RESPONSE_COISSUE = 0,
    parameter integer FE_WIDTH = `RV32IM_FE_WIDTH_DEFAULT,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer RS_ENTRIES = 8,
    parameter integer LSQ_ENTRIES = 8,
    parameter integer LSQ_STORE_ADMISSION_BYPASS = 0,
    parameter integer EARLY_LOAD_ADDRESS = 0,
    parameter integer LOAD_COMPLETION_BYPASS = 0,
    parameter integer LOAD_WAKE_BYPASS = 0,
    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,
    parameter integer LSQ_RECLAIM_WIDTH = 1,
    parameter integer LSQ_SECOND_REPORT_RECLAIM = 0,
    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 0,
    parameter integer EARLY_FRONT_REDIRECT = 0,
    parameter integer BRANCH_CAPTURE_REDIRECT_READY = 0,
    parameter integer BRANCH_CAPTURE_PHASE_VALID = 0,
    parameter integer RECOVERY_DIRECT_APPLY = 0,
    parameter integer RECOVERY_ROB_CREDIT = 0,
    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 0,
    parameter integer RECOVERY_APPLY_OLDER_ISSUE = 0,
    parameter integer RS_ROW_RECOVERY_QUALIFICATION = 0,
    parameter integer RS_ROW_LIVE_MEMBERSHIP = 0,
    parameter integer RS_PREDECODE_ISSUE_CANCEL = 0,
    parameter integer DISPATCH_ELASTIC = 0,
    parameter integer DISPATCH_FULL_REPLACE = 0,
    parameter integer EARLY_STORE_ADDRESS = 0,
    parameter integer STORE_ALLOC_EARLY_DATA = 0,
    parameter integer RS_ISSUE_METADATA = 0,
    parameter integer RS_WAKE_MUX_IMPL = 0,
    parameter integer RS_AGE_WIDTH = 32,
    parameter integer RS_ALLOC_STATIC_WRITE = 0,
    parameter integer PRF_READ_MUX_IMPL = 0,
    parameter integer RAT_READ_BYPASS = 0,
    parameter integer RENAME_RETAIN_FREE_POOL = 0,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    parameter integer ROB_COMMIT_BANKED_READ = 0,
    parameter integer LIGHT_RETIRE_PAYLOAD = 0,
    parameter integer ROB_MMIO_PREDECODE = 0,
    parameter integer ROB_ALLOC_BANKED_WRITE = 0,
    parameter integer ROB_UNIQUE_RECLAIM_COUNT = 0,
    parameter integer INT_ISSUE_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer CDB_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer ENABLE_CACHE_STATS = 0,
    parameter integer ENABLE_CACHES = 1,
    parameter integer ICACHE_LOOP_LINES = 0,
    parameter integer ICACHE_LOOP_SRAM = 0,
    parameter integer ICACHE_FAST_HIT = 1,
    parameter integer ICACHE_COMBINATIONAL_HIT = 0,
    parameter integer ICACHE_PREFETCH = 1,
    parameter integer ICACHE_LOCAL_RESPONSE_READY = 0,
    parameter integer ICACHE_TAG_MATCH_PARALLEL = 0,
    parameter integer ICACHE_TAG_REGION_BITS = 0,
    parameter integer ICACHE_MSHRS = 8,
    parameter integer ICACHE_LINES = 64,
    parameter integer ICACHE_WAYS = 2,
    parameter integer DCACHE_MSHRS = 4,
    parameter integer DCACHE_LINES = 256,
    parameter integer DCACHE_WORD_RESPONSE = 0,
    parameter integer DCACHE_WAYS = 1,
    parameter integer DCACHE_INDEX_HASH = 0,
    parameter integer DCACHE_REQUEST_PIPELINE = 0,
    parameter integer DCACHE_STORE_MERGE_DELAY = 0,
    parameter integer DCACHE_TAG_SRAM = 0,
    parameter integer DCACHE_STATIC_UPDATES = 0,
    parameter integer DCACHE_REGISTERED_INDEX = 0,
    parameter integer DCACHE_LOCAL_METADATA_QUERY = 0,
    parameter integer DCACHE_LOCAL_ACTION_DECODE = 0,
    parameter integer RAM_SIZE_BYTES = 268435456,
    parameter integer LEGACY_SENTINEL_HALT = 0,
    // Disable only when this diagnostic output is unconnected in the caller.
    // Architectural MMIO writes still carry the original LSQ/AXI payload.
    parameter integer RETURN_VALUE_ENABLE = 1,
    parameter integer ENABLE_PREDICTOR = 1,
    parameter integer PREDICTOR_DIRECT_BRANCH_TARGET = 0,
    parameter integer PREDICTOR_HISTORY_BITS = 6,
    parameter integer PREDICTOR_HYBRID_DIRECTION = 0,
    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 0,
    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 0,
    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 0,
    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 0,
    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 0,
    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 0,
    parameter integer PREDICTOR_BANK_DIRECT_WORD_INDEX = 0,
    parameter integer PREDICTOR_COMPACT_TARGET = 0,
    parameter integer PREDICTOR_COMPACT_BTB = 0,
    parameter integer PREDICTOR_COMPACT_BTB_ENTRIES = 64,
    parameter integer PREDICTOR_MULTI_FEEDBACK = 0,
    parameter integer FRONTEND_NARROW_OCCUPANCY = 0,
    parameter integer FETCH_QUEUE_DEPTH = 16,
    parameter integer MUL_IMPL = 0,
    parameter integer SHIFT_IMPL = 0,
    parameter integer SHIFT_SHARED_BARREL = 0,
    parameter integer PHYS_TAG_IMPL = 0,
    parameter integer CHECKPOINT_IMPL = 0,
    parameter integer RAT_RECOVERY_IMPL = 0,
    parameter integer RAT_SUFFIX_BRANCH_MAPPING = 0,
    parameter integer STORE_BUFFERED_RETIRE = 1,
    parameter integer COMPLETION_BYPASS = 0,
    parameter integer SERIAL_BACKEND = 0,
    parameter integer GENERATION_WIDTH = `RV32IM_ROB_GENERATION_WIDTH,
    parameter integer COMPLETION_DEPTH = (BE_WIDTH <= 1) ? 4 :
                                         ((BE_WIDTH == 2) ? 8 : 16)
) (
    input  wire       clk,
    input  wire       reset,
    output wire       halted,
    output wire       error,
    output wire [31:0] return_value,
    output reg  [31:0] cycles,
    output reg  [31:0] instret,
    output wire        mem_i_req_valid,
    input  wire        mem_i_req_ready,
    output wire [31:0] mem_i_req_line_addr,
    output wire [7:0]  mem_i_req_id,
    input  wire        mem_i_resp_valid,
    output wire        mem_i_resp_ready,
    input  wire [31:0] mem_i_resp_line_addr,
    input  wire [127:0] mem_i_resp_data,
    input  wire [7:0]  mem_i_resp_id,
    input  wire        mem_i_resp_error,
    output wire        mem_d_req_valid,
    input  wire        mem_d_req_ready,
    output wire        mem_d_req_write,
    output wire [31:0] mem_d_req_line_addr,
    output wire [127:0] mem_d_req_wdata,
    output wire [15:0] mem_d_req_wmask,
    output wire [7:0]  mem_d_req_id,
    input  wire        mem_d_resp_valid,
    output wire        mem_d_resp_ready,
    input  wire [31:0] mem_d_resp_line_addr,
    input  wire [127:0] mem_d_resp_data,
    input  wire [7:0]  mem_d_resp_id,
    input  wire        mem_d_resp_error
);
    localparam integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH;
    localparam integer PACKET_WIDTH = `RV32IM_FETCH_PACKET_WIDTH;
    localparam integer DISPATCH_LANES = (FE_WIDTH < BE_WIDTH) ? FE_WIDTH : BE_WIDTH;
    localparam integer ROB_TAG_WIDTH = 1 + 2 +
        ((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) +
        GENERATION_WIDTH;

    initial begin
        if ((RS_ISSUE_METADATA != 0 && RS_ISSUE_METADATA != 1) ||
            (EARLY_STORE_ADDRESS < 0 || EARLY_STORE_ADDRESS > 2) ||
            (RAT_RECOVERY_IMPL != 0 && RAT_RECOVERY_IMPL != 1)) begin
            $display("ERROR: invalid early store address or RAT recovery implementation");
            $finish(1);
        end
        if (PREDICTOR_DIRECT_BRANCH_TARGET == 2 &&
            (SERIAL_BACKEND != 0 || ENABLE_PREDICTOR == 0)) begin
            $display("ERROR: indexed-history predictor requires enabled OoO predictor metadata");
            $finish;
        end
        if ((DCACHE_REQUEST_PIPELINE != 0) && (DCACHE_REQUEST_PIPELINE != 1)) begin
            $display("ERROR: invalid DCACHE_REQUEST_PIPELINE; expected 0 or 1");
            $finish;
        end
        if ((FE_WIDTH != 1) && (FE_WIDTH != 2) && (FE_WIDTH != 4)) begin
            $display("ERROR: invalid FE_WIDTH=%0d; expected 1, 2, or 4", FE_WIDTH);
            $finish;
        end
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if ((ROB_ENTRIES < 2) || ((ROB_ENTRIES & (ROB_ENTRIES - 1)) != 0)) begin
            $display("ERROR: invalid ROB_ENTRIES=%0d; expected a power of two", ROB_ENTRIES);
            $finish;
        end
    end

    wire if_req_valid, if_req_ready;
    wire [31:0] if_req_pc;
    wire [EPOCH_WIDTH-1:0] if_req_epoch;
    wire if_resp_valid, if_resp_ready, if_resp_error;
    wire [31:0] if_resp_pc, if_resp_line_addr;
    wire [31:0] response_base_pc;
    wire [127:0] if_resp_line_data;
    wire [EPOCH_WIDTH-1:0] if_resp_epoch;
    wire [FE_WIDTH-1:0] fetch_valid, fetch_ready;
    wire [FE_WIDTH*PACKET_WIDTH-1:0] fetch_packet;
    wire [EPOCH_WIDTH-1:0] frontend_epoch;
    wire frontend_frozen, frontend_event_fetch, frontend_event_redirect, frontend_event_stall;
    localparam integer COMPACT_TARGET_ACTIVE=(PREDICTOR_COMPACT_TARGET!=0) &&
        (SERIAL_BACKEND==0) && (PREDICTOR_DIRECT_BRANCH_TARGET!=0);
    wire redirect_valid;
    wire [2:0] redirect_domains;
    rv32_frequency_control_tree #(.LEAVES(3)) redirect_tree (
        .signal_i(redirect_valid),.views_o(redirect_domains));
    wire [31:0] redirect_pc;
    wire [3:0] redirect_epoch;
    // Only the cached nonblocking registered-response profile can accept a
    // redirect request on this edge. Other cache/serial profiles retain the
    // original registered epoch and original frontend request contract.
    localparam integer REDIRECT_REQUEST_ACTIVE=(FRONTEND_REDIRECT_REQUEST!=0) &&
        (ENABLE_CACHES!=0) && (ICACHE_MSHRS>1) &&
        (ICACHE_COMBINATIONAL_HIT==0) && (DECODE_PIPELINE!=0) && (SERIAL_BACKEND==0);
    wire [EPOCH_WIDTH-1:0] icache_effective_epoch=
        (REDIRECT_REQUEST_ACTIVE!=0 && redirect_domains[0])?redirect_epoch:frontend_epoch;
    wire branch_feedback_valid, branch_feedback_taken, branch_feedback_pred_taken;
    wire [31:0] branch_feedback_pc, branch_feedback_target, branch_feedback_pred_target;
    wire [15:0] branch_feedback_metadata;
    wire [BE_WIDTH-1:0] branch_feedback_lane_valid;
    wire [BE_WIDTH*100-1:0] branch_feedback_lane_packets;
    wire [BE_WIDTH*16-1:0] branch_feedback_lane_metadata;
    wire [7:0] branch_recovery_history;
    wire [FE_WIDTH*16-1:0] pred_metadata_bus, fetch_pred_metadata;
    wire [BE_WIDTH*16-1:0] trace_pred_metadata;
    wire [1:0] branch_feedback_kind;

    wire [FE_WIDTH-1:0] pred_taken_bus, pred_btb_hit_bus;
    wire [FE_WIDTH*32-1:0] pred_target_bus;
    wire [FE_WIDTH*2-1:0] pred_kind_bus;
    wire [FE_WIDTH-1:0] pred_taken_raw_bus, pred_btb_hit_raw_bus;
    wire [FE_WIDTH*32-1:0] pred_target_raw_bus;
    wire [FE_WIDTH*2-1:0] pred_kind_raw_bus;
    wire [FE_WIDTH*6-1:0] pred_bht_index_bus;
    wire [FE_WIDTH*4-1:0] pred_btb_index_bus;
    wire [FE_WIDTH*2-1:0] pred_counter_bus;
    wire [FE_WIDTH*32-1:0] pred_count_bus, pred_correct_bus;
    wire [31:0] pred_count, pred_correct;
    assign pred_count_bus = {FE_WIDTH{pred_count}};
    assign pred_correct_bus = {FE_WIDTH{pred_correct}};

    // Small speculative return-address stack shared by all fetch lanes.  The
    // A call and its return may appear in different bundle lanes; neither
    // individual predictor banks nor lanes can maintain the ordered RAS alone.
    // Updating here, after the frontend accepts a bundle, keeps one ordered
    // stack for the whole fetch stream at very small area cost.
    wire [31:0] ras_stack [0:3];
    reg [1:0] ras_sp;
    reg [2:0] ras_count;
    reg ras_push;
    reg ras_pop;
    wire [31:0] ras_push_address;
    reg [FE_WIDTH-1:0] ras_push_lanes;
    wire [FE_WIDTH*32-1:0] ras_return_addresses;
    integer ras_lane;
    integer ras_word_index;
    integer ras_event_found;
    wire [1:0] ras_top_index = ras_sp - 1'b1;
    wire [127:0] ras_rows;
    wire [31:0] ras_target;
    wire [FE_WIDTH*2-1:0] ras_query_flags;
    wire [7:0] ras_line_flags;
    generate if(FRONTEND_RAS_PREDECODE!=0) begin:g_ras_line_predecode
        for(genvar word=0;word<4;word=word+1) begin:g_word
            wire [31:0] line_inst=if_resp_line_data[word*32 +: 32];
            assign ras_line_flags[word*2+1]=((line_inst[6:0]==7'b1101111) || (line_inst[6:0]==7'b1100111 && line_inst[14:12]==3'b000)) && (line_inst[11:7]==5'd1 || line_inst[11:7]==5'd5);
            assign ras_line_flags[word*2]=line_inst[6:0]==7'b1100111 && line_inst[14:12]==3'b000 && line_inst[11:7]==5'd0 && (line_inst[19:15]==5'd1 || line_inst[19:15]==5'd5) && line_inst[31:20]==12'd0;
        end
    end else begin:g_no_ras_line_predecode
        assign ras_line_flags=8'b0;
    end endgenerate
    rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(2)) ras_query (
        .rows_i(ras_rows),.index_i(ras_top_index),.value_o(ras_target));

    // Consecutive identical return addresses occupy one physical word.
    // A repetition count is the number of additional logical copies. Full
    // counts allocate another ordinary word rather than wrapping to zero.
    wire ras_repeat_push,ras_repeat_pop;
    generate if(RAS_REPEAT_COMPRESSION!=0) begin:g_ras_repeat_compression
        wire [4*RAS_REPEAT_COUNTER_BITS-1:0] repeat_rows;
        wire [RAS_REPEAT_COUNTER_BITS-1:0] top_repeats;
        rv32_frequency_array_read #(.WIDTH(RAS_REPEAT_COUNTER_BITS),.ENTRIES(4),.INDEX_WIDTH(2)) repeat_query (
            .rows_i(repeat_rows),.index_i(ras_top_index),.value_o(top_repeats));
        wire selected_repeat_match;
        if(RAS_REPEAT_MATCH_PREDECODE!=0) begin:g_predecoded_match
            wire [FE_WIDTH-1:0] lane_matches;
            if(FE_WIDTH<=4) begin:g_shared_pc_parts
                // +4..+16 changes only word bits and one carry into [31:4].
                // Reuse two early high comparisons for all supported lanes.
                wire [27:0] next_pc_high=response_base_pc[31:4]+28'd1;
                wire high_same=ras_target[31:4]==response_base_pc[31:4];
                wire high_next=ras_target[31:4]==next_pc_high;
                wire low_same=ras_target[1:0]==response_base_pc[1:0];
                for(genvar match_lane=0;match_lane<FE_WIDTH;match_lane=match_lane+1) begin:g_lane
                    wire [1:0] return_word=response_base_pc[3:2]+2'(match_lane+1);
                    wire carry_high;
                    if(match_lane==3) begin:g_full_line
                        assign carry_high=1'b1;
                    end else begin:g_partial_line
                        assign carry_high=response_base_pc[3:2]>=2'(3-match_lane);
                    end
                    assign lane_matches[match_lane]=low_same &&
                        ras_target[3:2]==return_word && (carry_high?high_next:high_same);
                end
            end else begin:g_general_pc_parts
                for(genvar match_lane=0;match_lane<FE_WIDTH;match_lane=match_lane+1) begin:g_lane
                    assign lane_matches[match_lane]=
                        ras_target==ras_return_addresses[match_lane*32 +: 32];
                end
            end
            // The original first-call rule makes ras_push_lanes one-hot.
            // Late predictor/response acceptance now selects one bit only.
            rv32_frequency_event_select #(.WIDTH(1),.EVENTS(FE_WIDTH),.PRIORITY(0)) match_select (
                .events_i(ras_push_lanes),.values_i(lane_matches),
                .write_o(),.value_o(selected_repeat_match));
        end else begin:g_selected_address_match
            assign selected_repeat_match=ras_target==ras_push_address;
        end
        assign ras_repeat_push=ras_push && ras_count!=0 &&
            selected_repeat_match && !(&top_repeats);
        assign ras_repeat_pop=ras_pop && top_repeats!=0;
        for(genvar repeat_row=0;repeat_row<4;repeat_row=repeat_row+1) begin:g_row
            wire [RAS_REPEAT_COUNTER_BITS-1:0] saved_repeats;
            wire allocate=!reset && ras_push && !ras_repeat_push && ras_sp==repeat_row;
            wire increment=!reset && ras_repeat_push && ras_top_index==repeat_row;
            wire decrement=!reset && ras_repeat_pop && ras_top_index==repeat_row;
            wire [RAS_REPEAT_COUNTER_BITS-1:0] next_repeats=allocate?
                {RAS_REPEAT_COUNTER_BITS{1'b0}}:
                (increment?saved_repeats+1'b1:saved_repeats-1'b1);
            rv32_frequency_word_bank #(.WIDTH(RAS_REPEAT_COUNTER_BITS)) repeat_owner (
                .clk_i(clk),.write_i(allocate || increment || decrement),
                .data_i(next_repeats),.data_o(saved_repeats));
            assign repeat_rows[repeat_row*RAS_REPEAT_COUNTER_BITS +: RAS_REPEAT_COUNTER_BITS]=saved_repeats;
        end
        initial begin
            if(RAS_REPEAT_COUNTER_BITS<1 || RAS_REPEAT_COUNTER_BITS>16)
                $fatal(1,"RAS repetition counter width must be in 1..16");
        end
    end else begin:g_no_ras_repeat_compression
        assign ras_repeat_push=1'b0;
        assign ras_repeat_pop=1'b0;
    end endgenerate

    // Consecutive lane PCs route to disjoint low-index predictor banks. All
    // lanes retain a read without duplicating the complete BHT/BTB state.
    genvar predictor_lane;
    generate
        if (ENABLE_PREDICTOR != 0) begin : g_banked_predictor
            rv32_banked_predictor #(.FE_WIDTH(FE_WIDTH), .DIRECT_BRANCH_TARGET(PREDICTOR_DIRECT_BRANCH_TARGET),
                .FEEDBACK_LANES(BE_WIDTH), .MULTI_FEEDBACK(PREDICTOR_MULTI_FEEDBACK && !SERIAL_BACKEND), .COMPACT_INDIRECT_BTB(PREDICTOR_COMPACT_BTB), .COMPACT_BTB_ENTRIES(PREDICTOR_COMPACT_BTB_ENTRIES), .HISTORY_BITS(PREDICTOR_HISTORY_BITS), .HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION && !SERIAL_BACKEND),
                .DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET && COMPACT_TARGET_ACTIVE),
                .NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ),
                .BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT),
                .PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY && !SERIAL_BACKEND),
                .BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ),
                .BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY),
                .BANK_DIRECT_WORD_INDEX(PREDICTOR_BANK_DIRECT_WORD_INDEX), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) predictor (
                .clk_i(clk), .reset_i(reset), .query_valid_i(if_resp_valid),
                .query_pc_i(response_base_pc), .query_line_i(if_resp_line_data),
                .query_accept_i(if_resp_valid && if_resp_ready && !if_resp_error &&
                    !redirect_domains[1] && !halted && !error),
                .effective_pred_taken_i(pred_taken_bus),
                .recovery_valid_i(redirect_domains[1]), .recovery_history_i(branch_recovery_history),
                .pred_metadata_o(pred_metadata_bus),
                .pred_taken_o(pred_taken_raw_bus), .pred_target_o(pred_target_raw_bus),
                .pred_kind_o(pred_kind_raw_bus), .pred_btb_hit_o(pred_btb_hit_raw_bus),
                .pred_bht_index_o(pred_bht_index_bus), .pred_btb_index_o(pred_btb_index_bus),
                .pred_counter_o(pred_counter_bus), .feedback_valid_i(branch_feedback_valid),
                .feedback_pc_i(branch_feedback_pc), .feedback_kind_i(branch_feedback_kind),
                .feedback_taken_i(branch_feedback_taken), .feedback_target_i(branch_feedback_target),
                .feedback_pred_taken_i(branch_feedback_pred_taken),
                .feedback_pred_target_i(branch_feedback_pred_target),
                .feedback_metadata_i(branch_feedback_metadata),
                .feedback_lane_valid_i(branch_feedback_lane_valid),
                .feedback_lane_packets_i(branch_feedback_lane_packets),
                .feedback_lane_metadata_i(branch_feedback_lane_metadata),
                .prediction_count_o(pred_count), .correct_count_o(pred_correct)
            );
        end else begin : g_no_predictor
            assign pred_metadata_bus = {FE_WIDTH*16{1'b0}};
            assign pred_taken_raw_bus = {FE_WIDTH{1'b0}};
            assign pred_target_raw_bus = {FE_WIDTH*32{1'b0}};
            assign pred_kind_raw_bus = {FE_WIDTH*2{1'b0}};
            assign pred_btb_hit_raw_bus = {FE_WIDTH{1'b0}};
            assign pred_bht_index_bus = {FE_WIDTH*6{1'b0}};
            assign pred_btb_index_bus = {FE_WIDTH*4{1'b0}};
            assign pred_counter_bus = {FE_WIDTH*2{1'b0}};
            assign pred_count = 0;
            assign pred_correct = 0;
        end
        for (predictor_lane = 0; predictor_lane < FE_WIDTH;
             predictor_lane = predictor_lane + 1) begin : g_predictor
            wire [2:0] query_word_index =
                {1'b0, response_base_pc[3:2]} + predictor_lane;
            wire query_valid = if_resp_valid && ((FRONTEND_RAS_PREDECODE==2) ?
                (response_base_pc[3:2]<=(3-predictor_lane)) : (query_word_index<3'd4));
            wire [1:0] query_ras_flags;
            if(FRONTEND_RAS_PREDECODE==2) begin:g_offset_ras_query
                // Constant lane shift pads the unavailable final words with00.
                // Dynamic selection now uses only the original start word.
                wire [7:0] lane_flag_rows=ras_line_flags>>(predictor_lane*2);
                rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(4),.INDEX_WIDTH(2)) flags_query (
                    .rows_i(lane_flag_rows),.index_i(response_base_pc[3:2]),.value_o(query_ras_flags));
            end else if(FRONTEND_RAS_PREDECODE!=0) begin:g_predecoded_ras_query
                rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(4),.INDEX_WIDTH(3)) flags_query (
                    .rows_i(ras_line_flags),.index_i(query_word_index),.value_o(query_ras_flags));
            end else begin:g_original_ras_query
                wire [31:0] query_inst;
                rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                    .rows_i(if_resp_line_data),.index_i(query_word_index),.value_o(query_inst));
                assign query_ras_flags[1]=((query_inst[6:0]==7'b1101111) || (query_inst[6:0]==7'b1100111 && query_inst[14:12]==3'b000)) && (query_inst[11:7]==5'd1 || query_inst[11:7]==5'd5);
                assign query_ras_flags[0]=query_inst[6:0]==7'b1100111 && query_inst[14:12]==3'b000 && query_inst[11:7]==5'd0 && (query_inst[19:15]==5'd1 || query_inst[19:15]==5'd5) && query_inst[31:20]==12'd0;
            end
            assign ras_query_flags[predictor_lane*2 +: 2]=query_ras_flags;
            // Independent constant add replaces selected PC then PC+4.
            assign ras_return_addresses[predictor_lane*32 +: 32]=response_base_pc+((predictor_lane+1)*32'd4);
            wire query_is_return = query_ras_flags[0];
            wire ras_return_hit = (ENABLE_PREDICTOR != 0) && query_valid &&
                                  query_is_return && (ras_count != 0);

            wire [2:0] ras_hit_views;
            rv32_frequency_control_tree #(.LEAVES(3)) ras_hit_tree (
                .signal_i(ras_return_hit),.views_o(ras_hit_views));
            assign pred_taken_bus[predictor_lane]=ras_hit_views[2] ? 1'b1 : pred_taken_raw_bus[predictor_lane];
            assign pred_target_bus[predictor_lane*32 +: 32]={
                ras_hit_views[1] ? ras_target[31:16] : pred_target_raw_bus[predictor_lane*32+16 +: 16],
                ras_hit_views[0] ? ras_target[15:0] : pred_target_raw_bus[predictor_lane*32 +: 16]};
            assign pred_kind_bus[predictor_lane*2 +: 2]=ras_hit_views[2] ?
                `RV32IM_PRED_JALR : pred_kind_raw_bus[predictor_lane*2 +: 2];
            assign pred_btb_hit_bus[predictor_lane]=ras_hit_views[2] ? 1'b1 : pred_btb_hit_raw_bus[predictor_lane];
        end
    endgenerate

    generate if(FRONTEND_RAS_PARALLEL_CONTROL!=0) begin:g_parallel_ras_events
        wire [FE_WIDTH-1:0] response_accept_views;
        wire [FE_WIDTH-1:0] ras_events,ras_first_events,ras_call_grants,ras_return_grants;
        rv32_frequency_control_tree #(.LEAVES(FE_WIDTH)) response_accept_tree (
            .signal_i((ENABLE_PREDICTOR!=0) && if_resp_valid && if_resp_ready),
            .views_o(response_accept_views));
        for(genvar event_lane=0;event_lane<FE_WIDTH;event_lane=event_lane+1) begin:g_lane
            wire within_line;
            if(event_lane<4) begin:g_present
                // W+L<4 is W<=3-L, with a constant per-lane bound.
                assign within_line=response_base_pc[3:2]<=2'(3-event_lane);
            end else begin:g_outside_line
                assign within_line=1'b0;
            end
            assign ras_events[event_lane]=within_line &&
                (ras_query_flags[event_lane*2+1] || ras_query_flags[event_lane*2] || pred_taken_bus[event_lane]);
            if(event_lane==0) begin:g_first
                assign ras_first_events[event_lane]=ras_events[event_lane];
            end else begin:g_later
                assign ras_first_events[event_lane]=ras_events[event_lane] && !(|ras_events[event_lane-1:0]);
            end
            // Response acceptance is only a final local qualifier. A call
            // wins over a return flag exactly as the original if/else loop.
            assign ras_call_grants[event_lane]=response_accept_views[event_lane] &&
                ras_first_events[event_lane] && ras_query_flags[event_lane*2+1];
            assign ras_return_grants[event_lane]=response_accept_views[event_lane] &&
                ras_first_events[event_lane] && !ras_query_flags[event_lane*2+1] && ras_query_flags[event_lane*2];
        end
        always @* begin
            ras_push_lanes=ras_call_grants;
            ras_push=|ras_call_grants;
            ras_pop=(|ras_return_grants) && ras_count!=0;
        end
    end else begin:g_original_ras_events
    always @* begin
        ras_push = 1'b0;
        ras_pop = 1'b0;
        ras_push_lanes = {FE_WIDTH{1'b0}};
        ras_event_found = 0;
        ras_word_index = 0;
        if ((ENABLE_PREDICTOR != 0) && if_resp_valid && if_resp_ready) begin
            for (ras_lane = 0; ras_lane < FE_WIDTH; ras_lane = ras_lane + 1) begin
                ras_word_index = response_base_pc[3:2] + ras_lane;
                if (!ras_event_found && (ras_word_index < 4)) begin
                    if (ras_query_flags[ras_lane*2+1]) begin
                        ras_push = 1'b1;
                        ras_push_lanes[ras_lane] = 1'b1;
                        ras_event_found = 1;
                    end else if (ras_query_flags[ras_lane*2]) begin
                        if (ras_count != 0)
                            ras_pop = 1'b1;
                        ras_event_found = 1;
                    end else if (pred_taken_bus[ras_lane]) begin
                        // The frontend stops the accepted bundle at the first
                        // predicted-taken control transfer.
                        ras_event_found = 1;
                    end
                end
            end
        end
    end


    end endgenerate

    // The first accepted call wins; return/taken events close the
    // prefix even when they do not push. Each payload mask drives <=16 bits.
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FE_WIDTH),.PRIORITY(0)) ras_return_address_selector (
        .events_i(ras_push_lanes),.values_i(ras_return_addresses),.write_o(),.value_o(ras_push_address));
    genvar ras_row;
    generate for(ras_row=0;ras_row<4;ras_row=ras_row+1) begin:g_ras_row
        // count=0 suppresses all observable RAS predictions after reset.
        // Only valid return addresses need storage; same-edge pushes win.
        wire write_event=!reset && ras_push && !ras_repeat_push && ras_sp==ras_row;
        rv32_frequency_word_bank #(.WIDTH(32)) payload_owner (
            .clk_i(clk),.write_i(write_event),.data_i(ras_push_address),.data_o(ras_stack[ras_row]));
        assign ras_rows[ras_row*32 +: 32]=ras_stack[ras_row];
    end endgenerate
    always @(posedge clk) begin
        if(reset) begin ras_sp<=2'd0;ras_count<=3'd0;end
        else if(ras_push && !ras_repeat_push) begin
            ras_sp<=ras_sp+1'b1;
            if(ras_count<4) ras_count<=ras_count+1'b1;
        end else if(ras_pop && !ras_repeat_pop) begin
            ras_sp<=ras_sp-1'b1;
            ras_count<=ras_count-1'b1;
        end
    end

    rv32_fetch_frontend #(.QUEUE_PAYLOAD_BANKS(FRONTEND_QUEUE_PAYLOAD_BANKS), .FE_WIDTH(FE_WIDTH), .FQ_DEPTH(FETCH_QUEUE_DEPTH), .NARROW_OCCUPANCY(FRONTEND_NARROW_OCCUPANCY),
        .RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS && (DECODE_PIPELINE!=0) && !SERIAL_BACKEND),
        .PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL), .REDIRECT_REQUEST(REDIRECT_REQUEST_ACTIVE),
        .RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ),
        .DIRECT_WORD_BOUNDS(FRONTEND_DIRECT_WORD_BOUNDS),
        .RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC && (ENABLE_CACHES!=0) &&
            (ICACHE_MSHRS>1) && (ICACHE_COMBINATIONAL_HIT==0) && !SERIAL_BACKEND), .COMPACT_PRED_TARGET(COMPACT_TARGET_ACTIVE), .PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) frontend (
        .clk_i(clk), .reset_i(reset), .redirect_valid_i(redirect_domains[0]),
        .redirect_pc_i(redirect_pc), .redirect_epoch_i(redirect_epoch),
        .stop_i(halted), .error_i(error), .if_req_valid_o(if_req_valid),
        .if_req_ready_i(if_req_ready), .if_req_pc_o(if_req_pc),
        .if_req_epoch_o(if_req_epoch), .if_resp_valid_i(if_resp_valid),
        .if_resp_ready_o(if_resp_ready), .if_resp_pc_i(if_resp_pc), .response_base_pc_o(response_base_pc),
        .if_resp_line_addr_i(if_resp_line_addr), .if_resp_line_data_i(if_resp_line_data),
        .if_resp_epoch_i(if_resp_epoch), .if_resp_error_i(if_resp_error),
        .if_resp_pred_taken_i(pred_taken_bus), .if_resp_pred_target_i(pred_target_bus),
        .if_resp_pred_kind_i(pred_kind_bus), .if_resp_pred_btb_hit_i(pred_btb_hit_bus),
        .if_resp_pred_metadata_i(pred_metadata_bus), .fetch_pred_metadata_o(fetch_pred_metadata),
        .fetch_valid_o(fetch_valid), .fetch_ready_i(fetch_ready),
        .fetch_packet_o(fetch_packet), .current_epoch_o(frontend_epoch),
        .frozen_o(frontend_frozen), .event_fetch_o(frontend_event_fetch),
        .event_redirect_o(frontend_event_redirect), .event_stall_o(frontend_event_stall)
    );

    wire ic_mem_req_valid, ic_mem_req_ready, ic_mem_resp_valid, ic_mem_resp_ready, ic_mem_resp_error;
    wire [31:0] ic_mem_req_line_addr, ic_mem_resp_line_addr;
    wire [7:0] ic_mem_req_id, ic_mem_resp_id;
    wire [127:0] ic_mem_resp_data;
    wire ic_event_request, ic_event_hit, ic_event_miss, ic_event_refill, ic_event_stall;
    wire dcache_req_valid, dcache_req_ready, dcache_req_load, dcache_req_store, dcache_req_unsigned;
    wire [31:0] dcache_req_addr;
    wire [1:0] dcache_req_size;
    wire [15:0] dcache_req_mask;
    wire [ROB_TAG_WIDTH-1:0] dcache_req_rob_tag, dcache_req_lsq_tag;
    wire [127:0] dcache_req_wdata;
    wire memory_dreq_valid, memory_dreq_ready, memory_dreq_load, memory_dreq_store;
    wire normal_memory_dreq_ready;
    wire memory_dreq_unsigned;
    wire [31:0] memory_dreq_addr;
    wire [1:0] memory_dreq_size;
    wire [15:0] memory_dreq_mask;
    wire [127:0] memory_dreq_wdata;
    wire [ROB_TAG_WIDTH-1:0] memory_dreq_rob_tag, memory_dreq_lsq_tag;
    localparam integer DREQ_PAYLOAD_WIDTH = 181 + 2*ROB_TAG_WIDTH;
    wire [DREQ_PAYLOAD_WIDTH-1:0] dreq_payload_in = {
        dcache_req_load, dcache_req_store, dcache_req_addr, dcache_req_size,
        dcache_req_unsigned, dcache_req_mask, dcache_req_wdata,
        dcache_req_rob_tag, dcache_req_lsq_tag};
    wire [DREQ_PAYLOAD_WIDTH-1:0] dreq_payload_out;
    assign {memory_dreq_load, memory_dreq_store, memory_dreq_addr, memory_dreq_size,
            memory_dreq_unsigned, memory_dreq_mask, memory_dreq_wdata,
            memory_dreq_rob_tag, memory_dreq_lsq_tag} = dreq_payload_out;
    // An exit store is an uncached architectural side effect. It must reach
    // the external data port with its full 32-bit payload before the ROB may
    // retire it; ordinary cache write-back must not absorb this MMIO access.
    wire mmio_exit_request = memory_dreq_valid && memory_dreq_store &&
                             (memory_dreq_addr == 32'h80000000) &&
                             (memory_dreq_mask == 16'h000f);
    // Qualify once, then partition the final request consumers. The
    // acknowledgement retains the original predicate and capture edge.
    wire [16:0] mmio_exit_views;
    rv32_frequency_control_tree #(.LEAVES(17)) mmio_exit_request_tree (
        .signal_i(mmio_exit_request),.views_o(mmio_exit_views));
    wire normal_memory_dreq_valid = memory_dreq_valid && !mmio_exit_views[0];
    assign memory_dreq_ready = mmio_exit_views[1] ? mem_d_req_ready :
                                normal_memory_dreq_ready;
    generate
    if (DCACHE_REQUEST_PIPELINE != 0) begin : g_dcache_request_pipeline
        wire input_ready, output_valid;
        // This is a registered, non-fall-through stage. Keep accepted traffic
        // across branch recovery: stores are already committed; stale loads
        // are harmless cache accesses and LSQ generations reject responses.
        // Clearing this stage on redirect would lose older surviving loads
        // and architectural stores. Only whole-core reset cancels requests.
        rv32im_skid_buffer #(.WIDTH(DREQ_PAYLOAD_WIDTH)) request_register (
            .clk_i(clk), .reset_i(reset), .flush_i(1'b0),
            .in_valid_i(dcache_req_valid && !reset), .in_ready_o(input_ready),
            .in_payload_i(dreq_payload_in), .out_valid_o(output_valid),
            .out_ready_i(memory_dreq_ready), .out_payload_o(dreq_payload_out)
        );
        assign dcache_req_ready = input_ready && !reset;
        assign memory_dreq_valid = output_valid && !reset;
    end else begin : g_dcache_request_direct
        assign dcache_req_ready = memory_dreq_ready;
        assign memory_dreq_valid = dcache_req_valid;
        assign dreq_payload_out = dreq_payload_in;
    end
    endgenerate
    wire dcache_resp_valid, dcache_resp_ready, dcache_resp_line_valid, dcache_resp_error;
    wire [ROB_TAG_WIDTH-1:0] dcache_resp_lsq_tag;
    wire [31:0] dcache_resp_addr, dcache_resp_word;
    wire [127:0] dcache_resp_line;
    wire dcache_store_ack_valid, dcache_store_ack_error;
    wire [ROB_TAG_WIDTH-1:0] dcache_store_ack_lsq_tag;
    wire cache_store_ack_valid, cache_store_ack_error;
    wire [ROB_TAG_WIDTH-1:0] cache_store_ack_lsq_tag;
    reg mmio_ack_pending;
    reg [ROB_TAG_WIDTH-1:0] mmio_ack_lsq_tag;
    assign dcache_store_ack_valid = cache_store_ack_valid || mmio_ack_pending;
    assign dcache_store_ack_lsq_tag = cache_store_ack_valid ?
        cache_store_ack_lsq_tag : mmio_ack_lsq_tag;
    assign dcache_store_ack_error = cache_store_ack_valid ?
        cache_store_ack_error : 1'b0;
    always @(posedge clk) begin
        if (reset) begin
            mmio_ack_pending <= 1'b0;
            mmio_ack_lsq_tag <= {ROB_TAG_WIDTH{1'b0}};
        end else begin
            if (mmio_ack_pending && !cache_store_ack_valid)
                mmio_ack_pending <= 1'b0;
            if (mmio_exit_request && mem_d_req_ready) begin
                mmio_ack_pending <= 1'b1;
                mmio_ack_lsq_tag <= memory_dreq_lsq_tag;
            end
        end
    end
    wire dc_mem_req_valid, dc_mem_req_ready, dc_mem_req_write, dc_mem_resp_valid, dc_mem_resp_ready, dc_mem_resp_error;
    wire [31:0] dc_mem_req_line_addr, dc_mem_resp_line_addr;
    wire [127:0] dc_mem_req_wdata, dc_mem_resp_data;
    wire [15:0] dc_mem_req_wmask;
    wire [7:0] dc_mem_req_id, dc_mem_resp_id;
    wire normal_mem_d_req_valid, normal_mem_d_req_ready, normal_mem_d_req_write;
    wire [31:0] normal_mem_d_req_line_addr;
    wire [127:0] normal_mem_d_req_wdata;
    wire [15:0] normal_mem_d_req_wmask;
    wire [7:0] normal_mem_d_req_id;
    wire normal_mem_d_resp_ready;
    wire normal_mem_d_resp_valid = mem_d_resp_valid &&
                                   (mem_d_resp_id != 8'hfe);
    assign mem_d_req_valid = mmio_exit_views[2] || normal_mem_d_req_valid;
    assign mem_d_req_write = mmio_exit_views[3] ? 1'b1 : normal_mem_d_req_write;
    assign normal_mem_d_req_ready = mem_d_req_ready && !mmio_exit_views[4];
    genvar mmio_word;
    generate for(mmio_word=0;mmio_word<2;mmio_word=mmio_word+1) begin:g_mmio_request_word
        localparam [15:0] EXIT_ADDRESS_WORD=32'h80000000 >> (16*mmio_word);
        assign mem_d_req_line_addr[mmio_word*16 +: 16]=mmio_exit_views[5+mmio_word] ?
            EXIT_ADDRESS_WORD : normal_mem_d_req_line_addr[mmio_word*16 +: 16];
        assign mem_d_req_wdata[mmio_word*16 +: 16]=mmio_exit_views[7+mmio_word] ?
            memory_dreq_wdata[mmio_word*16 +: 16] : normal_mem_d_req_wdata[mmio_word*16 +: 16];
    end endgenerate
    // Every MMIO exit has mask 000f. Upper words issue no AXI write;
    // zero them during MMIO instead of selecting arbitrary MMIO data. This
    // keeps the entire held request stable even if normal cache data changes.
    generate for(genvar upper_word=0;upper_word<6;upper_word=upper_word+1) begin:g_mmio_masked_word
        assign mem_d_req_wdata[32+upper_word*16 +: 16]=
            {16{!mmio_exit_views[11+upper_word]}} & normal_mem_d_req_wdata[32+upper_word*16 +: 16];
    end endgenerate
    assign mem_d_req_wmask = mmio_exit_views[9] ? 16'h000f : normal_mem_d_req_wmask;
    assign mem_d_req_id = mmio_exit_views[10] ? 8'hfe : normal_mem_d_req_id;
    assign mem_d_resp_ready = (mem_d_resp_id == 8'hfe) ? 1'b1 :
                              normal_mem_d_resp_ready;
    wire dc_event_request, dc_event_hit, dc_event_miss, dc_event_refill, dc_event_writeback, dc_event_stall;
    wire dcache_debug_s0_valid, dcache_debug_s0_store;
    wire dcache_debug_s1_valid, dcache_debug_s1_store;
    wire dcache_debug_s2_valid, dcache_debug_s2_store, dcache_debug_s2_hit;
    wire dcache_debug_mshr_valid, dcache_debug_ack_valid, dcache_debug_resp_valid;
    generate
    if (ENABLE_CACHES != 0) begin : g_cached_memory
    if (ICACHE_MSHRS > 1) begin : g_nonblocking_icache
    rv32_icache_nonblocking #(.MSHR_STATIC_WRITES(ICACHE_MSHR_STATIC_WRITES), .MSHR_STATE_BANKS(ICACHE_MSHR_STATE_BANKS), 
        .MSHR_ENTRIES(ICACHE_MSHRS), .TAG_REGION_BITS(ICACHE_TAG_REGION_BITS), .TAG_MATCH_PARALLEL(ICACHE_TAG_MATCH_PARALLEL), .LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY), .REQUEST_PIPELINE(1),
        .LOOP_BUFFER_LINES(ICACHE_LOOP_LINES), .LOOP_BUFFER_SRAM(ICACHE_LOOP_SRAM),
        .CACHE_LINES(ICACHE_LINES), .CACHE_WAYS(ICACHE_WAYS),
        .NEXT_LINE_PREFETCH(ICACHE_PREFETCH),
        // Fill the remaining MSHRs with sequential lines.  Redirected
        // demands can immediately recycle old-epoch entries, so speculative
        // traffic no longer reserves or starves the demand path.
        .PREFETCH_DISTANCE((ICACHE_MSHRS > 1) ? (ICACHE_MSHRS-1) : 1)
    ) icache (
        .clk_i(clk), .reset_i(reset), .current_epoch_i(icache_effective_epoch),
        .if_req_valid_i(if_req_valid), .if_req_ready_o(if_req_ready), .if_req_pc_i(if_req_pc),
        .if_req_epoch_i(if_req_epoch), .if_resp_valid_o(if_resp_valid),
        .if_resp_ready_i(if_resp_ready), .if_resp_pc_o(if_resp_pc),
        .if_resp_line_addr_o(if_resp_line_addr), .if_resp_line_data_o(if_resp_line_data),
        .if_resp_epoch_o(if_resp_epoch), .if_resp_error_o(if_resp_error),
        .mem_req_valid_o(ic_mem_req_valid), .mem_req_ready_i(ic_mem_req_ready),
        .mem_req_line_addr_o(ic_mem_req_line_addr), .mem_req_id_o(ic_mem_req_id),
        .mem_resp_valid_i(ic_mem_resp_valid), .mem_resp_ready_o(ic_mem_resp_ready),
        .mem_resp_line_addr_i(ic_mem_resp_line_addr), .mem_resp_data_i(ic_mem_resp_data),
        .mem_resp_id_i(ic_mem_resp_id), .mem_resp_error_i(ic_mem_resp_error),
        .event_request_o(ic_event_request), .event_hit_o(ic_event_hit),
        .event_miss_o(ic_event_miss), .event_refill_o(ic_event_refill), .event_stall_o(ic_event_stall)
    );
    end else begin : g_blocking_icache
    rv32_icache #(
        .FAST_HIT(ICACHE_FAST_HIT),
        .COMBINATIONAL_HIT(ICACHE_COMBINATIONAL_HIT),
        .NEXT_LINE_PREFETCH(ICACHE_PREFETCH)
    ) icache (
        .clk_i(clk), .reset_i(reset), .current_epoch_i(frontend_epoch),
        .if_req_valid_i(if_req_valid), .if_req_ready_o(if_req_ready), .if_req_pc_i(if_req_pc),
        .if_req_epoch_i(if_req_epoch), .if_resp_valid_o(if_resp_valid),
        .if_resp_ready_i(if_resp_ready), .if_resp_pc_o(if_resp_pc),
        .if_resp_line_addr_o(if_resp_line_addr), .if_resp_line_data_o(if_resp_line_data),
        .if_resp_epoch_o(if_resp_epoch), .if_resp_error_o(if_resp_error),
        .mem_req_valid_o(ic_mem_req_valid), .mem_req_ready_i(ic_mem_req_ready),
        .mem_req_line_addr_o(ic_mem_req_line_addr), .mem_req_id_o(ic_mem_req_id),
        .mem_resp_valid_i(ic_mem_resp_valid), .mem_resp_ready_o(ic_mem_resp_ready),
        .mem_resp_line_addr_i(ic_mem_resp_line_addr), .mem_resp_data_i(ic_mem_resp_data),
        .mem_resp_id_i(ic_mem_resp_id), .mem_resp_error_i(ic_mem_resp_error),
        .event_request_o(ic_event_request), .event_hit_o(ic_event_hit),
        .event_miss_o(ic_event_miss), .event_refill_o(ic_event_refill), .event_stall_o(ic_event_stall)
    );
    end

    if (DCACHE_MSHRS > 1) begin : g_nonblocking_dcache
    rv32_dcache_nonblocking #(.WORD_RESPONSE((DCACHE_WORD_RESPONSE!=0) && (SERIAL_BACKEND==0)), .HIT_BYPASS(1), .LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS), .WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY), .HIT_RESPONSE_COISSUE(DCACHE_HIT_RESPONSE_COISSUE), 
        .TAG_WIDTH(ROB_TAG_WIDTH), .MSHR_ENTRIES(DCACHE_MSHRS),
        .CACHE_LINES(DCACHE_LINES), .CACHE_WAYS(DCACHE_WAYS),
        .INDEX_HASH(DCACHE_INDEX_HASH), .STORE_MERGE_DELAY(DCACHE_STORE_MERGE_DELAY),
        .TAG_SRAM(DCACHE_TAG_SRAM), .STATIC_UPDATES(DCACHE_STATIC_UPDATES), .REGISTERED_INDEX(DCACHE_REGISTERED_INDEX), .LOCAL_METADATA_QUERY(DCACHE_LOCAL_METADATA_QUERY), .LOCAL_ACTION_DECODE(DCACHE_LOCAL_ACTION_DECODE)
    ) dcache (
        // LSQ generations reject wrong-path responses while retaining older
        // loads across a redirect.  The cache itself has no ROB-age context.
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0), .dcache_req_valid_i(normal_memory_dreq_valid),
        .dcache_req_ready_o(normal_memory_dreq_ready), .dcache_req_is_load_i(memory_dreq_load),
        .dcache_req_is_store_i(memory_dreq_store), .dcache_req_addr_i(memory_dreq_addr),
        .dcache_req_size_i(memory_dreq_size), .dcache_req_unsigned_i(memory_dreq_unsigned),
        .dcache_req_mask_i(memory_dreq_mask), .dcache_req_wdata_i(memory_dreq_wdata),
        .dcache_req_rob_tag_i(memory_dreq_rob_tag), .dcache_req_lsq_tag_i(memory_dreq_lsq_tag),
        .dcache_resp_valid_o(dcache_resp_valid), .dcache_resp_ready_i(dcache_resp_ready),
        .dcache_resp_lsq_tag_o(dcache_resp_lsq_tag), .dcache_resp_addr_o(dcache_resp_addr),
        .dcache_resp_line_data_o(dcache_resp_line), .dcache_resp_word_data_o(dcache_resp_word),
        .dcache_resp_line_valid_o(dcache_resp_line_valid), .dcache_resp_error_o(dcache_resp_error),
        .dcache_store_ack_valid_o(cache_store_ack_valid), .dcache_store_ack_ready_i(1'b1),
        .dcache_store_ack_lsq_tag_o(cache_store_ack_lsq_tag), .dcache_store_ack_error_o(cache_store_ack_error),
        .mem_req_valid_o(dc_mem_req_valid), .mem_req_ready_i(dc_mem_req_ready),
        .mem_req_write_o(dc_mem_req_write), .mem_req_line_addr_o(dc_mem_req_line_addr),
        .mem_req_wdata_o(dc_mem_req_wdata), .mem_req_wmask_o(dc_mem_req_wmask),
        .mem_req_id_o(dc_mem_req_id), .mem_resp_valid_i(dc_mem_resp_valid),
        .mem_resp_ready_o(dc_mem_resp_ready), .mem_resp_line_addr_i(dc_mem_resp_line_addr),
        .mem_resp_data_i(dc_mem_resp_data), .mem_resp_id_i(dc_mem_resp_id),
        .mem_resp_error_i(dc_mem_resp_error), .event_request_o(dc_event_request),
        .event_hit_o(dc_event_hit), .event_miss_o(dc_event_miss), .event_refill_o(dc_event_refill),
        .event_writeback_o(dc_event_writeback), .event_stall_o(dc_event_stall)
    );
    end else begin : g_blocking_dcache
    rv32_dcache #(.TAG_WIDTH(ROB_TAG_WIDTH)) dcache (
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0), .dcache_req_valid_i(normal_memory_dreq_valid),
        .dcache_req_ready_o(normal_memory_dreq_ready), .dcache_req_is_load_i(memory_dreq_load),
        .dcache_req_is_store_i(memory_dreq_store), .dcache_req_addr_i(memory_dreq_addr),
        .dcache_req_size_i(memory_dreq_size), .dcache_req_unsigned_i(memory_dreq_unsigned),
        .dcache_req_mask_i(memory_dreq_mask), .dcache_req_wdata_i(memory_dreq_wdata),
        .dcache_req_rob_tag_i(memory_dreq_rob_tag), .dcache_req_lsq_tag_i(memory_dreq_lsq_tag),
        .dcache_resp_valid_o(dcache_resp_valid), .dcache_resp_ready_i(dcache_resp_ready),
        .dcache_resp_lsq_tag_o(dcache_resp_lsq_tag), .dcache_resp_addr_o(dcache_resp_addr),
        .dcache_resp_line_data_o(dcache_resp_line), .dcache_resp_word_data_o(dcache_resp_word),
        .dcache_resp_line_valid_o(dcache_resp_line_valid), .dcache_resp_error_o(dcache_resp_error),
        .dcache_store_ack_valid_o(cache_store_ack_valid), .dcache_store_ack_ready_i(1'b1),
        .dcache_store_ack_lsq_tag_o(cache_store_ack_lsq_tag), .dcache_store_ack_error_o(cache_store_ack_error),
        .mem_req_valid_o(dc_mem_req_valid), .mem_req_ready_i(dc_mem_req_ready),
        .mem_req_write_o(dc_mem_req_write), .mem_req_line_addr_o(dc_mem_req_line_addr),
        .mem_req_wdata_o(dc_mem_req_wdata), .mem_req_wmask_o(dc_mem_req_wmask),
        .mem_req_id_o(dc_mem_req_id), .mem_resp_valid_i(dc_mem_resp_valid),
        .mem_resp_ready_o(dc_mem_resp_ready), .mem_resp_line_addr_i(dc_mem_resp_line_addr),
        .mem_resp_data_i(dc_mem_resp_data), .mem_resp_id_i(dc_mem_resp_id),
        .mem_resp_error_i(dc_mem_resp_error), .event_request_o(dc_event_request),
        .event_hit_o(dc_event_hit), .event_miss_o(dc_event_miss), .event_refill_o(dc_event_refill),
        .event_writeback_o(dc_event_writeback), .event_stall_o(dc_event_stall)
    );
    end

    rv32_memory_bridge #(.MEMORY_SIZE(RAM_SIZE_BYTES)) memory_bridge (
        .clk_i(clk), .reset_i(reset), .cache_i_req_valid_i(ic_mem_req_valid),
        .cache_i_req_ready_o(ic_mem_req_ready), .cache_i_req_line_addr_i(ic_mem_req_line_addr),
        .cache_i_req_id_i(ic_mem_req_id), .cache_i_resp_valid_o(ic_mem_resp_valid),
        .cache_i_resp_ready_i(ic_mem_resp_ready), .cache_i_resp_line_addr_o(ic_mem_resp_line_addr),
        .cache_i_resp_data_o(ic_mem_resp_data), .cache_i_resp_id_o(ic_mem_resp_id),
        .cache_i_resp_error_o(ic_mem_resp_error), .cache_d_req_valid_i(dc_mem_req_valid),
        .cache_d_req_ready_o(dc_mem_req_ready), .cache_d_req_write_i(dc_mem_req_write),
        .cache_d_req_line_addr_i(dc_mem_req_line_addr), .cache_d_req_wdata_i(dc_mem_req_wdata),
        .cache_d_req_wmask_i(dc_mem_req_wmask), .cache_d_req_id_i(dc_mem_req_id),
        .cache_d_resp_valid_o(dc_mem_resp_valid), .cache_d_resp_ready_i(dc_mem_resp_ready),
        .cache_d_resp_line_addr_o(dc_mem_resp_line_addr), .cache_d_resp_data_o(dc_mem_resp_data),
        .cache_d_resp_id_o(dc_mem_resp_id), .cache_d_resp_error_o(dc_mem_resp_error),
        .mem_i_req_valid_o(mem_i_req_valid), .mem_i_req_ready_i(mem_i_req_ready),
        .mem_i_req_line_addr_o(mem_i_req_line_addr), .mem_i_req_id_o(mem_i_req_id),
        .mem_i_resp_valid_i(mem_i_resp_valid), .mem_i_resp_ready_o(mem_i_resp_ready),
        .mem_i_resp_line_addr_i(mem_i_resp_line_addr), .mem_i_resp_data_i(mem_i_resp_data),
        .mem_i_resp_id_i(mem_i_resp_id), .mem_i_resp_error_i(mem_i_resp_error),
        .mem_d_req_valid_o(normal_mem_d_req_valid), .mem_d_req_ready_i(normal_mem_d_req_ready),
        .mem_d_req_write_o(normal_mem_d_req_write), .mem_d_req_line_addr_o(normal_mem_d_req_line_addr),
        .mem_d_req_wdata_o(normal_mem_d_req_wdata), .mem_d_req_wmask_o(normal_mem_d_req_wmask),
        .mem_d_req_id_o(normal_mem_d_req_id), .mem_d_resp_valid_i(normal_mem_d_resp_valid),
        .mem_d_resp_ready_o(normal_mem_d_resp_ready), .mem_d_resp_line_addr_i(mem_d_resp_line_addr),
        .mem_d_resp_data_i(mem_d_resp_data), .mem_d_resp_id_i(mem_d_resp_id),
        .mem_d_resp_error_i(mem_d_resp_error), .event_i_mem_request_o(),
        .event_d_mem_read_o(), .event_d_mem_write_o()
    );
    // Stable diagnostic aliases avoid testbench dependence on generate paths.
    assign dcache_debug_s0_valid = 1'b0;
    assign dcache_debug_s0_store = 1'b0;
    assign dcache_debug_s1_valid = 1'b0;
    assign dcache_debug_s1_store = 1'b0;
    assign dcache_debug_s2_valid = 1'b0;
    assign dcache_debug_s2_store = 1'b0;
    assign dcache_debug_s2_hit = 1'b0;
    assign dcache_debug_mshr_valid = dc_mem_req_valid;
    assign dcache_debug_ack_valid = dcache_store_ack_valid;
    assign dcache_debug_resp_valid = dcache_resp_valid;
    end else begin : g_uncached_memory
        rv32_uncached_memory #(
            .EPOCH_WIDTH(EPOCH_WIDTH), .TAG_WIDTH(ROB_TAG_WIDTH)
        ) uncached_memory (
            .clk_i(clk), .reset_i(reset),
            .if_req_valid_i(if_req_valid), .if_req_ready_o(if_req_ready),
            .if_req_pc_i(if_req_pc), .if_req_epoch_i(if_req_epoch),
            .current_epoch_i(frontend_epoch),
            .if_resp_valid_o(if_resp_valid), .if_resp_ready_i(if_resp_ready),
            .if_resp_pc_o(if_resp_pc), .if_resp_line_addr_o(if_resp_line_addr),
            .if_resp_line_data_o(if_resp_line_data), .if_resp_epoch_o(if_resp_epoch),
            .if_resp_error_o(if_resp_error),
            .d_req_valid_i(normal_memory_dreq_valid), .d_req_ready_o(normal_memory_dreq_ready),
            .d_req_is_load_i(memory_dreq_load), .d_req_is_store_i(memory_dreq_store),
            .d_req_addr_i(memory_dreq_addr), .d_req_size_i(memory_dreq_size),
            .d_req_unsigned_i(memory_dreq_unsigned), .d_req_mask_i(memory_dreq_mask),
            .d_req_wdata_i(memory_dreq_wdata), .d_req_lsq_tag_i(memory_dreq_lsq_tag),
            .d_resp_valid_o(dcache_resp_valid), .d_resp_ready_i(dcache_resp_ready),
            .d_resp_lsq_tag_o(dcache_resp_lsq_tag), .d_resp_addr_o(dcache_resp_addr),
            .d_resp_line_data_o(dcache_resp_line), .d_resp_word_data_o(dcache_resp_word),
            .d_resp_line_valid_o(dcache_resp_line_valid), .d_resp_error_o(dcache_resp_error),
            .d_store_ack_valid_o(cache_store_ack_valid), .d_store_ack_ready_i(1'b1),
            .d_store_ack_lsq_tag_o(cache_store_ack_lsq_tag),
            .d_store_ack_error_o(cache_store_ack_error),
            .mem_i_req_valid_o(mem_i_req_valid), .mem_i_req_ready_i(mem_i_req_ready),
            .mem_i_req_line_addr_o(mem_i_req_line_addr), .mem_i_req_id_o(mem_i_req_id),
            .mem_i_resp_valid_i(mem_i_resp_valid), .mem_i_resp_ready_o(mem_i_resp_ready),
            .mem_i_resp_line_addr_i(mem_i_resp_line_addr), .mem_i_resp_data_i(mem_i_resp_data),
            .mem_i_resp_id_i(mem_i_resp_id), .mem_i_resp_error_i(mem_i_resp_error),
            .mem_d_req_valid_o(normal_mem_d_req_valid), .mem_d_req_ready_i(normal_mem_d_req_ready),
            .mem_d_req_write_o(normal_mem_d_req_write), .mem_d_req_line_addr_o(normal_mem_d_req_line_addr),
            .mem_d_req_wdata_o(normal_mem_d_req_wdata), .mem_d_req_wmask_o(normal_mem_d_req_wmask),
            .mem_d_req_id_o(normal_mem_d_req_id), .mem_d_resp_valid_i(normal_mem_d_resp_valid),
            .mem_d_resp_ready_o(normal_mem_d_resp_ready), .mem_d_resp_line_addr_i(mem_d_resp_line_addr),
            .mem_d_resp_data_i(mem_d_resp_data), .mem_d_resp_id_i(mem_d_resp_id),
            .mem_d_resp_error_i(mem_d_resp_error)
        );
        assign ic_mem_req_valid = 1'b0;
        assign ic_mem_req_line_addr = 32'b0;
        assign ic_mem_req_id = 8'b0;
        assign ic_mem_resp_ready = 1'b0;
        assign dc_mem_req_valid = 1'b0;
        assign dc_mem_req_write = 1'b0;
        assign dc_mem_req_line_addr = 32'b0;
        assign dc_mem_req_wdata = 128'b0;
        assign dc_mem_req_wmask = 16'b0;
        assign dc_mem_req_id = 8'b0;
        assign dc_mem_resp_ready = 1'b0;
        assign ic_event_request = if_req_valid && if_req_ready;
        assign ic_event_hit = 1'b0;
        assign ic_event_miss = ic_event_request;
        assign ic_event_refill = if_resp_valid && if_resp_ready;
        assign ic_event_stall = if_req_valid && !if_req_ready;
        assign dc_event_request = memory_dreq_valid && memory_dreq_ready;
        assign dc_event_hit = 1'b0;
        assign dc_event_miss = dc_event_request;
        assign dc_event_refill = dcache_resp_valid && dcache_resp_ready;
        assign dc_event_writeback = dcache_store_ack_valid;
        assign dc_event_stall = memory_dreq_valid && !memory_dreq_ready;
        assign dcache_debug_s0_valid = 1'b0;
        assign dcache_debug_s0_store = 1'b0;
        assign dcache_debug_s1_valid = 1'b0;
        assign dcache_debug_s1_store = 1'b0;
        assign dcache_debug_s2_valid = 1'b0;
        assign dcache_debug_s2_store = 1'b0;
        assign dcache_debug_s2_hit = 1'b0;
        assign dcache_debug_mshr_valid = uncached_memory.d_pending;
        assign dcache_debug_ack_valid = dcache_store_ack_valid;
        assign dcache_debug_resp_valid = dcache_resp_valid;
    end
    endgenerate

    wire [BE_WIDTH-1:0] trace_valid, trace_ready;
    wire [BE_WIDTH*PACKET_WIDTH-1:0] trace_packet;
    wire [BE_WIDTH*32-1:0] trace_pc, trace_inst;
    wire [BE_WIDTH-1:0] trace_pred_taken;
    wire [BE_WIDTH*32-1:0] trace_pred_target;
    wire [BE_WIDTH*2-1:0] trace_pred_kind;
    wire [BE_WIDTH-1:0] dec_legal, dec_rd_we, dec_rs1_used, dec_rs2_used;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] dec_op, backend_op;
    wire [BE_WIDTH*4-1:0] dec_class;
    wire [BE_WIDTH*5-1:0] dec_rd, dec_rs1, dec_rs2, backend_rs1, backend_rs2;
    wire [BE_WIDTH*32-1:0] dec_imm;
    wire [BE_WIDTH-1:0] dec_load, dec_store, dec_branch, dec_jump, dec_serialize;
    wire [BE_WIDTH*2-1:0] dec_mem_size;
    wire [BE_WIDTH-1:0] dec_mem_unsigned;
    wire [BE_WIDTH*4-1:0] dec_mem_base_mask;
    wire [BE_WIDTH-1:0] dec_jalr_clear_lsb, is_halt_trace, backend_rs1_used;


    // Decode output is registered before rename/PRF access.
    localparam integer DECODE_PAYLOAD_WIDTH = PACKET_WIDTH + 16 + 1 + `RV32IM_OP_WIDTH + 4 + 5 + 5 + 5 + 1 + 1 + 1 + 32 + 1 + 1 + 1 + 1 + 1 + 2 + 1 + 4 + 1;
    wire [BE_WIDTH-1:0] raw_trace_valid, raw_trace_ready;
    wire [BE_WIDTH*PACKET_WIDTH-1:0] raw_trace_packet;
    wire [BE_WIDTH*16-1:0] raw_trace_pred_metadata;
    wire [BE_WIDTH*1-1:0] raw_dec_legal;
    wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] raw_dec_op;
    wire [BE_WIDTH*4-1:0] raw_dec_class;
    wire [BE_WIDTH*5-1:0] raw_dec_rd;
    wire [BE_WIDTH*5-1:0] raw_dec_rs1;
    wire [BE_WIDTH*5-1:0] raw_dec_rs2;
    wire [BE_WIDTH*1-1:0] raw_dec_rd_we;
    wire [BE_WIDTH*1-1:0] raw_dec_rs1_used;
    wire [BE_WIDTH*1-1:0] raw_dec_rs2_used;
    wire [BE_WIDTH*32-1:0] raw_dec_imm;
    wire [BE_WIDTH*1-1:0] raw_dec_load;
    wire [BE_WIDTH*1-1:0] raw_dec_store;
    wire [BE_WIDTH*1-1:0] raw_dec_branch;
    wire [BE_WIDTH*1-1:0] raw_dec_jump;
    wire [BE_WIDTH*1-1:0] raw_dec_serialize;
    wire [BE_WIDTH*2-1:0] raw_dec_mem_size;
    wire [BE_WIDTH*1-1:0] raw_dec_mem_unsigned;
    wire [BE_WIDTH*4-1:0] raw_dec_mem_base_mask;
    wire [BE_WIDTH*1-1:0] raw_dec_jalr_clear_lsb;
    wire [BE_WIDTH*DECODE_PAYLOAD_WIDTH-1:0] decode_input, decode_output;

    genvar frontend_lane;
    generate
        for (frontend_lane = 0; frontend_lane < FE_WIDTH; frontend_lane = frontend_lane + 1) begin : g_frontend_ready
            if (frontend_lane < BE_WIDTH)
                assign fetch_ready[frontend_lane] = raw_trace_ready[frontend_lane];
            else
                assign fetch_ready[frontend_lane] = 1'b0;
        end
    endgenerate

    genvar decode_lane;
    generate
        for (decode_lane = 0; decode_lane < BE_WIDTH; decode_lane = decode_lane + 1) begin : g_decode
            if (decode_lane < FE_WIDTH) begin : g_has_frontend_lane
                assign raw_trace_pred_metadata[decode_lane*16 +: 16] =
                    fetch_pred_metadata[decode_lane*16 +: 16];
                assign raw_trace_valid[decode_lane] = fetch_valid[decode_lane];
                assign raw_trace_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH] =
                    fetch_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH];
            end else begin : g_no_frontend_lane
                assign raw_trace_pred_metadata[decode_lane*16 +: 16] = 16'b0;
                assign raw_trace_valid[decode_lane] = 1'b0;
                assign raw_trace_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH] =
                    {PACKET_WIDTH{1'b0}};
            end
            assign trace_pc[decode_lane*32 +: 32] =
                trace_packet[decode_lane*PACKET_WIDTH +: 32];
            assign trace_inst[decode_lane*32 +: 32] =
                trace_packet[decode_lane*PACKET_WIDTH + 32 +: 32];
            assign trace_pred_taken[decode_lane] =
                trace_packet[decode_lane*PACKET_WIDTH + 64];
            assign trace_pred_target[decode_lane*32 +: 32] =
                trace_packet[decode_lane*PACKET_WIDTH + 65 +: 32];
            assign trace_pred_kind[decode_lane*2 +: 2] =
                trace_packet[decode_lane*PACKET_WIDTH + 97 +: 2];

            rv32im_decoder #(.LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) decoder (
                .inst_i(raw_trace_packet[decode_lane*PACKET_WIDTH+32 +: 32]),
                .legal_o(raw_dec_legal[decode_lane]),
                .op_o(raw_dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH]),
                .class_o(raw_dec_class[decode_lane*4 +: 4]),
                .rd_o(raw_dec_rd[decode_lane*5 +: 5]),
                .rs1_o(raw_dec_rs1[decode_lane*5 +: 5]),
                .rs2_o(raw_dec_rs2[decode_lane*5 +: 5]),
                .rd_we_o(raw_dec_rd_we[decode_lane]),
                .rs1_used_o(raw_dec_rs1_used[decode_lane]),
                .rs2_used_o(raw_dec_rs2_used[decode_lane]),
                .imm_o(raw_dec_imm[decode_lane*32 +: 32]),
                .is_load_o(raw_dec_load[decode_lane]),
                .is_store_o(raw_dec_store[decode_lane]),
                .is_branch_o(raw_dec_branch[decode_lane]),
                .is_jump_o(raw_dec_jump[decode_lane]),
                .is_serialize_o(raw_dec_serialize[decode_lane]),
                .mem_size_o(raw_dec_mem_size[decode_lane*2 +: 2]),
                .mem_unsigned_o(raw_dec_mem_unsigned[decode_lane]),
                .mem_base_mask_o(raw_dec_mem_base_mask[decode_lane*4 +: 4]),
                .jalr_clear_lsb_o(raw_dec_jalr_clear_lsb[decode_lane])
            );

            assign decode_input[decode_lane*DECODE_PAYLOAD_WIDTH +: DECODE_PAYLOAD_WIDTH] = {raw_trace_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH], raw_trace_pred_metadata[decode_lane*16 +: 16], raw_dec_legal[decode_lane*1 +: 1], raw_dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH], raw_dec_class[decode_lane*4 +: 4], raw_dec_rd[decode_lane*5 +: 5], raw_dec_rs1[decode_lane*5 +: 5], raw_dec_rs2[decode_lane*5 +: 5], raw_dec_rd_we[decode_lane*1 +: 1], raw_dec_rs1_used[decode_lane*1 +: 1], raw_dec_rs2_used[decode_lane*1 +: 1], raw_dec_imm[decode_lane*32 +: 32], raw_dec_load[decode_lane*1 +: 1], raw_dec_store[decode_lane*1 +: 1], raw_dec_branch[decode_lane*1 +: 1], raw_dec_jump[decode_lane*1 +: 1], raw_dec_serialize[decode_lane*1 +: 1], raw_dec_mem_size[decode_lane*2 +: 2], raw_dec_mem_unsigned[decode_lane*1 +: 1], raw_dec_mem_base_mask[decode_lane*4 +: 4], raw_dec_jalr_clear_lsb[decode_lane*1 +: 1]};
            assign {trace_packet[decode_lane*PACKET_WIDTH +: PACKET_WIDTH], trace_pred_metadata[decode_lane*16 +: 16], dec_legal[decode_lane*1 +: 1], dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH], dec_class[decode_lane*4 +: 4], dec_rd[decode_lane*5 +: 5], dec_rs1[decode_lane*5 +: 5], dec_rs2[decode_lane*5 +: 5], dec_rd_we[decode_lane*1 +: 1], dec_rs1_used[decode_lane*1 +: 1], dec_rs2_used[decode_lane*1 +: 1], dec_imm[decode_lane*32 +: 32], dec_load[decode_lane*1 +: 1], dec_store[decode_lane*1 +: 1], dec_branch[decode_lane*1 +: 1], dec_jump[decode_lane*1 +: 1], dec_serialize[decode_lane*1 +: 1], dec_mem_size[decode_lane*2 +: 2], dec_mem_unsigned[decode_lane*1 +: 1], dec_mem_base_mask[decode_lane*4 +: 4], dec_jalr_clear_lsb[decode_lane*1 +: 1]} = decode_output[decode_lane*DECODE_PAYLOAD_WIDTH +: DECODE_PAYLOAD_WIDTH];

            // HALT commits the live architectural a0 value through the normal
            // ALU/read path while retaining precise sentinel classification.
            assign is_halt_trace[decode_lane] =
                (dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] == `RV32IM_OP_HALT);
            assign backend_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH] =
                is_halt_trace[decode_lane] ? `RV32IM_OP_ADD :
                dec_op[decode_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];
            assign backend_rs1[decode_lane*5 +: 5] =
                is_halt_trace[decode_lane] ? 5'd10 : dec_rs1[decode_lane*5 +: 5];
            assign backend_rs2[decode_lane*5 +: 5] =
                is_halt_trace[decode_lane] ? 5'd0 : dec_rs2[decode_lane*5 +: 5];
            assign backend_rs1_used[decode_lane] =
                is_halt_trace[decode_lane] ? 1'b1 : dec_rs1_used[decode_lane];
        end
    endgenerate


    generate if (DECODE_PIPELINE != 0) begin : g_decode_pipeline
        rv32_decode_bundle_register #(.LANES(BE_WIDTH), .PAYLOAD_WIDTH(DECODE_PAYLOAD_WIDTH)) pipe (
            .clk_i(clk), .reset_i(reset), .flush_i(redirect_domains[2] || halted || error),
            .valid_i(raw_trace_valid), .ready_o(raw_trace_ready), .data_i(decode_input),
            .valid_o(trace_valid), .ready_i(trace_ready), .data_o(decode_output));
    end else begin : g_decode_direct
        assign trace_valid = raw_trace_valid;
        assign raw_trace_ready = trace_ready;
        assign decode_output = decode_input;
    end endgenerate

    wire [BE_WIDTH-1:0] commit_valid, commit_rd_we, commit_is_store;
    wire commit_ready;
    wire [BE_WIDTH*32-1:0] commit_pc, commit_inst, commit_value, commit_store_addr;
    wire [BE_WIDTH*5-1:0] commit_rd;
    wire [BE_WIDTH*16-1:0] commit_store_mask;
    wire [BE_WIDTH*ROB_TAG_WIDTH-1:0] commit_tag;
    wire [BE_WIDTH*128-1:0] commit_store_data;
    wire [15:0] perf_rob_occupancy, perf_rs_occupancy, perf_lsq_occupancy;
    wire [BE_WIDTH-1:0] perf_issue_valid;
    wire perf_branch_pending, perf_mdu_busy;
    assign commit_ready = 1'b1;
    generate if (SERIAL_BACKEND != 0) begin : g_serial_backend
    assign branch_feedback_metadata = 16'b0;
    assign branch_feedback_lane_valid=0;
    assign branch_feedback_lane_packets=0;
    assign branch_feedback_lane_metadata=0;
    assign branch_recovery_history = 8'b0;
    rv32_serial_backend #(.BE_WIDTH(BE_WIDTH), .SHIFT_IMPL(SHIFT_IMPL),
        .TAG_WIDTH(ROB_TAG_WIDTH)) backend (
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0), .trace_valid_i(trace_valid),
        .trace_ready_o(trace_ready), .trace_pc_i(trace_pc), .trace_inst_i(trace_inst),
        .trace_op_i(backend_op), .trace_imm_i(dec_imm), .trace_rd_i(dec_rd), .trace_rs1_i(backend_rs1),
        .trace_rs2_i(backend_rs2), .trace_rd_we_i(dec_rd_we), .trace_rs1_used_i(backend_rs1_used),
        .trace_rs2_used_i(dec_rs2_used & ~is_halt_trace), .trace_is_load_i(dec_load), .trace_is_store_i(dec_store),
        .trace_is_branch_i(dec_branch | dec_jump), .trace_is_halt_i(is_halt_trace),
        .trace_is_error_i(trace_valid & ~dec_legal), .trace_mem_size_i(dec_mem_size),
        .trace_mem_unsigned_i(dec_mem_unsigned), .trace_store_data_i({BE_WIDTH*128{1'b0}}),
        .trace_pred_taken_i(trace_pred_taken), .trace_pred_target_i(trace_pred_target),
        .trace_pred_kind_i(trace_pred_kind), .dcache_req_valid_o(dcache_req_valid),
        .dcache_req_ready_i(dcache_req_ready), .dcache_req_is_load_o(dcache_req_load),
        .dcache_req_is_store_o(dcache_req_store), .dcache_req_addr_o(dcache_req_addr),
        .dcache_req_size_o(dcache_req_size), .dcache_req_unsigned_o(dcache_req_unsigned),
        .dcache_req_mask_o(dcache_req_mask), .dcache_req_wdata_o(dcache_req_wdata),
        .dcache_req_rob_tag_o(dcache_req_rob_tag), .dcache_req_lsq_tag_o(dcache_req_lsq_tag),
        .dcache_resp_valid_i(dcache_resp_valid), .dcache_resp_ready_o(dcache_resp_ready),
        .dcache_resp_lsq_tag_i(dcache_resp_lsq_tag), .dcache_resp_addr_i(dcache_resp_addr),
        .dcache_resp_line_data_i(dcache_resp_line), .dcache_resp_word_data_i(dcache_resp_word),
        .dcache_resp_line_valid_i(dcache_resp_line_valid), .dcache_resp_error_i(dcache_resp_error),
        .dcache_store_ack_valid_i(dcache_store_ack_valid), .dcache_store_ack_lsq_tag_i(dcache_store_ack_lsq_tag),
        .dcache_store_ack_error_i(dcache_store_ack_error), .commit_ready_i(commit_ready),
        .commit_valid_o(commit_valid), .commit_pc_o(commit_pc), .commit_inst_o(commit_inst),
        .commit_rd_o(commit_rd), .commit_rd_we_o(commit_rd_we), .commit_value_o(commit_value),
        .commit_is_store_o(commit_is_store), .commit_store_addr_o(commit_store_addr),
        .commit_store_mask_o(commit_store_mask), .commit_store_data_o(commit_store_data),
        .commit_tag_o(commit_tag), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc),
        .redirect_epoch_o(redirect_epoch), .halted_o(halted), .error_o(error),
        .return_value_o(return_value), .branch_feedback_valid_o(branch_feedback_valid),
        .branch_feedback_pc_o(branch_feedback_pc), .branch_feedback_kind_o(branch_feedback_kind),
        .branch_feedback_taken_o(branch_feedback_taken), .branch_feedback_target_o(branch_feedback_target),
        .branch_feedback_pred_taken_o(branch_feedback_pred_taken), .branch_feedback_pred_target_o(branch_feedback_pred_target)
    );
    assign perf_rob_occupancy = 16'd0;
    assign perf_rs_occupancy = 16'd0;
    assign perf_lsq_occupancy = 16'd0;
    assign perf_issue_valid = {BE_WIDTH{1'b0}};
    assign perf_branch_pending = 1'b0;
    assign perf_mdu_busy = 1'b0;
    end else begin : g_ooo_backend
    rv32_backend_joint #(.LSQ_RESPONSE_QUERY_PREDECODE(1), .STORE_ALLOC_EARLY_ADDRESS(2), .LSQ_ROB_QUERY_PREDECODE(1), .STORE_ALLOC_IMM12(1), .RS_PHYSICAL_WAKEUP(1), .DISPATCH_PIPELINE(1), .DISPATCH_ELASTIC(DISPATCH_ELASTIC), .DISPATCH_FULL_REPLACE(DISPATCH_FULL_REPLACE), .ISSUE_PIPELINE(ISSUE_PIPELINE), .LOCAL_EXEC_RECOVERY(1), .BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .ROB_ENTRIES(ROB_ENTRIES), .RS_ENTRIES(RS_ENTRIES), .LSQ_ENTRIES(LSQ_ENTRIES), .LSQ_STORE_ADMISSION_BYPASS(LSQ_STORE_ADMISSION_BYPASS), .EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS), .LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS), .LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS), .ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .LSQ_SECOND_REPORT_RECLAIM(LSQ_SECOND_REPORT_RECLAIM), .LSQ_EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS), .EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT), .BRANCH_CAPTURE_REDIRECT_READY(BRANCH_CAPTURE_REDIRECT_READY), .BRANCH_CAPTURE_PHASE_VALID(BRANCH_CAPTURE_PHASE_VALID), .RECOVERY_DIRECT_APPLY(RECOVERY_DIRECT_APPLY), .RECOVERY_ROB_CREDIT(RECOVERY_ROB_CREDIT), .RECOVERY_PREVIEW_OLDER_ISSUE(RECOVERY_PREVIEW_OLDER_ISSUE), .RECOVERY_APPLY_OLDER_ISSUE(RECOVERY_APPLY_OLDER_ISSUE), .RS_ROW_RECOVERY_QUALIFICATION(RS_ROW_RECOVERY_QUALIFICATION), .RS_ROW_LIVE_MEMBERSHIP(RS_ROW_LIVE_MEMBERSHIP), .RS_PREDECODE_ISSUE_CANCEL(RS_PREDECODE_ISSUE_CANCEL), .EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS), .STORE_ALLOC_EARLY_DATA(STORE_ALLOC_EARLY_DATA), .RS_ISSUE_METADATA(RS_ISSUE_METADATA), .RS_WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL), .RS_ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE), .RS_AGE_WIDTH(RS_AGE_WIDTH), .PRF_READ_MUX_IMPL(PRF_READ_MUX_IMPL), .RAT_READ_BYPASS(RAT_READ_BYPASS), .RENAME_RETAIN_FREE_POOL(RENAME_RETAIN_FREE_POOL), .ASAP7_FANOUT_BUFFERS(ASAP7_FANOUT_BUFFERS), .ROB_CONTROL_REGISTER_BANKS(ROB_CONTROL_REGISTER_BANKS), .ROB_COMMIT_BANKED_READ(ROB_COMMIT_BANKED_READ), .ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .ROB_UNIQUE_RECLAIM_COUNT(ROB_UNIQUE_RECLAIM_COUNT), .ROB_MMIO_PREDECODE(ROB_MMIO_PREDECODE), .LIGHT_RETIRE_PAYLOAD(LIGHT_RETIRE_PAYLOAD), .ROB_LEGACY_HALT_PAYLOAD(LEGACY_SENTINEL_HALT), .ROB_RETURN_VALUE_ENABLE(RETURN_VALUE_ENABLE), .COMPACT_PRED_TARGET(COMPACT_TARGET_ACTIVE), .PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .INT_ISSUE_WIDTH(INT_ISSUE_WIDTH), .CDB_WIDTH(CDB_WIDTH), .MUL_IMPL(MUL_IMPL), .SHIFT_IMPL(SHIFT_IMPL), .SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL), .PHYS_TAG_IMPL(PHYS_TAG_IMPL), .CHECKPOINT_IMPL(CHECKPOINT_IMPL), .RAT_RECOVERY_IMPL(RAT_RECOVERY_IMPL), .RAT_SUFFIX_BRANCH_MAPPING(RAT_SUFFIX_BRANCH_MAPPING), .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE), .COMPLETION_BYPASS(COMPLETION_BYPASS), .COMPLETION_DEPTH(COMPLETION_DEPTH), .TAG_WIDTH(ROB_TAG_WIDTH)) backend (
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0), .trace_valid_i(trace_valid),
        .trace_ready_o(trace_ready), .trace_pc_i(trace_pc), .trace_inst_i(trace_inst),
        .trace_op_i(backend_op), .trace_imm_i(dec_imm), .trace_rd_i(dec_rd), .trace_rs1_i(backend_rs1),
        .trace_rs2_i(backend_rs2), .trace_rd_we_i(dec_rd_we), .trace_rs1_used_i(backend_rs1_used),
        .trace_rs2_used_i(dec_rs2_used & ~is_halt_trace), .trace_is_load_i(dec_load), .trace_is_store_i(dec_store),
        .trace_is_branch_i(dec_branch | dec_jump), .trace_is_halt_i(is_halt_trace),
        .trace_is_error_i(trace_valid & ~dec_legal), .trace_mem_size_i(dec_mem_size),
        .trace_mem_unsigned_i(dec_mem_unsigned), .trace_store_data_i({BE_WIDTH*128{1'b0}}),
        .trace_pred_taken_i(trace_pred_taken), .trace_pred_target_i(trace_pred_target),
        .trace_pred_kind_i(trace_pred_kind), .dcache_req_valid_o(dcache_req_valid),
        .dcache_req_ready_i(dcache_req_ready), .dcache_req_is_load_o(dcache_req_load),
        .dcache_req_is_store_o(dcache_req_store), .dcache_req_addr_o(dcache_req_addr),
        .dcache_req_size_o(dcache_req_size), .dcache_req_unsigned_o(dcache_req_unsigned),
        .dcache_req_mask_o(dcache_req_mask), .dcache_req_wdata_o(dcache_req_wdata),
        .dcache_req_rob_tag_o(dcache_req_rob_tag), .dcache_req_lsq_tag_o(dcache_req_lsq_tag),
        .dcache_resp_valid_i(dcache_resp_valid), .dcache_resp_ready_o(dcache_resp_ready),
        .dcache_resp_lsq_tag_i(dcache_resp_lsq_tag), .dcache_resp_addr_i(dcache_resp_addr),
        .dcache_resp_line_data_i(dcache_resp_line), .dcache_resp_word_data_i(dcache_resp_word),
        .dcache_resp_line_valid_i(dcache_resp_line_valid), .dcache_resp_error_i(dcache_resp_error),
        .dcache_store_ack_valid_i(dcache_store_ack_valid), .dcache_store_ack_lsq_tag_i(dcache_store_ack_lsq_tag),
        .dcache_store_ack_error_i(dcache_store_ack_error), .commit_ready_i(commit_ready),
        .commit_valid_o(commit_valid), .commit_pc_o(commit_pc), .commit_inst_o(commit_inst),
        .commit_rd_o(commit_rd), .commit_rd_we_o(commit_rd_we), .commit_value_o(commit_value),
        .commit_is_store_o(commit_is_store), .commit_store_addr_o(commit_store_addr),
        .commit_store_mask_o(commit_store_mask), .commit_store_data_o(commit_store_data),
         .commit_tag_o(commit_tag), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc),
         .redirect_epoch_o(redirect_epoch), .halted_o(halted), .error_o(error),
         .return_value_o(return_value), .branch_feedback_valid_o(branch_feedback_valid),
         .branch_feedback_pc_o(branch_feedback_pc), .branch_feedback_kind_o(branch_feedback_kind),
         .branch_feedback_taken_o(branch_feedback_taken), .branch_feedback_target_o(branch_feedback_target),
         .branch_feedback_pred_taken_o(branch_feedback_pred_taken), .branch_feedback_pred_target_o(branch_feedback_pred_target),
         .branch_feedback_lane_valid_o(branch_feedback_lane_valid),
         .branch_feedback_lane_packets_o(branch_feedback_lane_packets),
         .branch_feedback_lane_metadata_o(branch_feedback_lane_metadata),
         .trace_pred_metadata_i(trace_pred_metadata), .branch_feedback_metadata_o(branch_feedback_metadata),
         .branch_recovery_history_o(branch_recovery_history),
         .perf_rob_occupancy_o(perf_rob_occupancy), .perf_rs_occupancy_o(perf_rs_occupancy),
         .perf_lsq_occupancy_o(perf_lsq_occupancy), .perf_issue_valid_o(perf_issue_valid),
         .perf_branch_pending_o(perf_branch_pending), .perf_mdu_busy_o(perf_mdu_busy)
    );
    end endgenerate

    wire [63:0] perf_i_requests, perf_i_hits, perf_i_misses, perf_i_refills, perf_i_stalls;
    wire [63:0] perf_d_requests, perf_d_hits, perf_d_misses, perf_d_refills;
    wire [63:0] perf_d_writebacks, perf_d_stalls, perf_i_mem_requests;
    wire [63:0] perf_d_mem_reads, perf_d_mem_writes;
    generate
        if (ENABLE_CACHE_STATS != 0) begin : gen_cache_stats
            rv32_cache_stats stats (
                .clk_i(clk), .reset_i(reset), .i_event_request_i(ic_event_request), .i_event_hit_i(ic_event_hit),
                .i_event_miss_i(ic_event_miss), .i_event_refill_i(ic_event_refill), .i_event_stall_i(ic_event_stall),
                .d_event_request_i(dc_event_request), .d_event_hit_i(dc_event_hit), .d_event_miss_i(dc_event_miss),
                .d_event_refill_i(dc_event_refill), .d_event_writeback_i(dc_event_writeback), .d_event_stall_i(dc_event_stall),
                .i_mem_request_fire_i(mem_i_req_valid && mem_i_req_ready),
                .d_mem_read_fire_i(mem_d_req_valid && mem_d_req_ready && !mem_d_req_write),
                .d_mem_write_fire_i(mem_d_req_valid && mem_d_req_ready && mem_d_req_write),
                .i_request_count_o(perf_i_requests), .i_hit_count_o(perf_i_hits),
                .i_miss_count_o(perf_i_misses), .i_refill_count_o(perf_i_refills),
                .i_stall_count_o(perf_i_stalls), .d_request_count_o(perf_d_requests),
                .d_hit_count_o(perf_d_hits), .d_miss_count_o(perf_d_misses),
                .d_refill_count_o(perf_d_refills), .d_writeback_count_o(perf_d_writebacks),
                .d_stall_count_o(perf_d_stalls), .i_mem_request_count_o(perf_i_mem_requests),
                .d_mem_read_count_o(perf_d_mem_reads), .d_mem_write_count_o(perf_d_mem_writes)
            );
        end else begin : gen_no_cache_stats
            assign perf_i_requests = 64'd0; assign perf_i_hits = 64'd0;
            assign perf_i_misses = 64'd0; assign perf_i_refills = 64'd0;
            assign perf_i_stalls = 64'd0; assign perf_d_requests = 64'd0;
            assign perf_d_hits = 64'd0; assign perf_d_misses = 64'd0;
            assign perf_d_refills = 64'd0; assign perf_d_writebacks = 64'd0;
            assign perf_d_stalls = 64'd0; assign perf_i_mem_requests = 64'd0;
            assign perf_d_mem_reads = 64'd0; assign perf_d_mem_writes = 64'd0;
        end
    endgenerate

    reg [63:0] perf_frontend_empty_cycles;
    reg [63:0] perf_backend_stall_cycles;
    reg [63:0] perf_no_commit_cycles;
    reg [63:0] perf_commit_active_cycles;
    reg [63:0] perf_issue_count;
    reg [63:0] perf_rob_full_cycles;
    reg [63:0] perf_rs_full_cycles;
    reg [63:0] perf_lsq_full_cycles;
    reg [63:0] perf_branch_pending_cycles;
    reg [63:0] perf_mdu_busy_cycles;

    function [31:0] commit_popcount;
        input [BE_WIDTH-1:0] bits;
        integer lane;
        begin
            commit_popcount = 32'd0;
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                if (bits[lane]) commit_popcount = commit_popcount + 32'd1;
        end
    endfunction

    always @(posedge clk) begin
        if (reset) begin
            cycles <= 32'd0;
            instret <= 32'd0;
            perf_frontend_empty_cycles <= 64'd0;
            perf_backend_stall_cycles <= 64'd0;
            perf_no_commit_cycles <= 64'd0;
            perf_commit_active_cycles <= 64'd0;
            perf_issue_count <= 64'd0;
            perf_rob_full_cycles <= 64'd0;
            perf_rs_full_cycles <= 64'd0;
            perf_lsq_full_cycles <= 64'd0;
            perf_branch_pending_cycles <= 64'd0;
            perf_mdu_busy_cycles <= 64'd0;
        end else begin
            cycles <= cycles + 32'd1;
            if ((|commit_valid) && commit_ready)
                instret <= instret + commit_popcount(commit_valid);
            if (ENABLE_CACHE_STATS != 0) begin
                if (!(|fetch_valid)) perf_frontend_empty_cycles <= perf_frontend_empty_cycles + 1'b1;
                if ((|trace_valid) && !(|trace_ready)) perf_backend_stall_cycles <= perf_backend_stall_cycles + 1'b1;
                if (!(|commit_valid)) perf_no_commit_cycles <= perf_no_commit_cycles + 1'b1;
                else perf_commit_active_cycles <= perf_commit_active_cycles + 1'b1;
                perf_issue_count <= perf_issue_count + commit_popcount(perf_issue_valid);
                if (perf_rob_occupancy >= ROB_ENTRIES) perf_rob_full_cycles <= perf_rob_full_cycles + 1'b1;
                if (perf_rs_occupancy >= RS_ENTRIES) perf_rs_full_cycles <= perf_rs_full_cycles + 1'b1;
                if (perf_lsq_occupancy >= LSQ_ENTRIES) perf_lsq_full_cycles <= perf_lsq_full_cycles + 1'b1;
                if (perf_branch_pending) perf_branch_pending_cycles <= perf_branch_pending_cycles + 1'b1;
                if (perf_mdu_busy) perf_mdu_busy_cycles <= perf_mdu_busy_cycles + 1'b1;
            end
        end
    end
endmodule

// Ordered elastic bundle implemented as a ring: dequeue changes a pointer,
// never shifts the entire decoded payload through a recovery/ready mux.
module rv32_decode_bundle_register #(
    parameter integer LANES=4, PAYLOAD_WIDTH=194, CAPACITY=2*LANES,
    parameter integer CW=(CAPACITY<2)?1:$clog2(CAPACITY+1),
    parameter integer PW=(CAPACITY<2)?1:$clog2(CAPACITY)
) (
    input wire clk_i,reset_i,flush_i,
    input wire [LANES-1:0] valid_i,
    output reg [LANES-1:0] ready_o,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output reg [LANES-1:0] valid_o,
    input wire [LANES-1:0] ready_i,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o
);
    localparam integer WORDS=(PAYLOAD_WIDTH+15)/16;
    reg [CW-1:0] count;
    reg [PW-1:0] head,tail;
    reg [CW-1:0] consumed,accepted;
    integer lane,capacity;
    reg prefix;
    // Raw storage writes agree with public acceptance on ordinary cycles.
    // During invalidation arbitrary payload writes are harmless: count=0 wins.
    reg [LANES-1:0] storage_push;
    reg [LANES-1:0] storage_ready;
    reg [CW-1:0] storage_consumed;
    wire invalidate = reset_i || flush_i;
    wire [1:0] invalidate_domains;
    rv32_frequency_control_tree #(.LEAVES(2)) invalidate_tree (
        .signal_i(invalidate),.views_o(invalidate_domains));
    wire [CAPACITY*PAYLOAD_WIDTH-1:0] rows;
    always @* begin
        consumed=0;accepted=0;valid_o=0;ready_o=0;prefix=1;
        storage_consumed=0;storage_push=0;storage_ready=0;
        for(lane=0;lane<LANES;lane=lane+1) begin
            valid_o[lane]=(lane<count) && !invalidate_domains[0];
            if(prefix && (lane<count) && ready_i[lane])
                storage_consumed=storage_consumed+1'b1;
            else prefix=0;
        end
        // Upstream space is determined solely by registered occupancy.
        capacity=CAPACITY-count;
        prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            storage_ready[lane]=prefix && (lane<capacity);
            storage_push[lane]=storage_ready[lane] && valid_i[lane];
            ready_o[lane]=storage_ready[lane] && !invalidate_domains[0];
            if(ready_o[lane] && valid_i[lane]) accepted=accepted+1'b1;
            if(!storage_push[lane]) prefix=0;
        end
        if(!invalidate_domains[0]) consumed=storage_consumed;
    end
    always @(posedge clk_i) begin
        if(invalidate_domains[1]) begin count<=0;head<=0;tail<=0;end
        else begin
            count<=count-consumed+accepted;
            head<=(head+consumed)%CAPACITY;
            tail<=(tail+accepted)%CAPACITY;
        end
    end
    genvar slot,word_id,read_lane;
    generate for(slot=0;slot<CAPACITY;slot=slot+1) begin:g_slot
        for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_field
            localparam integer W=((PAYLOAD_WIDTH-word_id*16)<16)?(PAYLOAD_WIDTH-word_id*16):16;
            wire [LANES*W-1:0] inputs;
            for(genvar writer=0;writer<LANES;writer=writer+1) begin:g_input
                assign inputs[writer*W +: W]=data_i[writer*PAYLOAD_WIDTH+word_id*16 +: W];
            end
            rv32_decode_field_bank #(.LANES(LANES),.WIDTH(W),.ROW(slot),.PW(PW),.CAPACITY(CAPACITY)) bank (
                .clk_i(clk_i),.reset_i(1'b0),.flush_i(1'b0),.tail_i(tail),
                .push_i(storage_push),.data_i(inputs),.data_o(rows[slot*PAYLOAD_WIDTH+word_id*16 +: W]));
        end
    end

    localparam integer READ_LEAVES=1<<$clog2(CAPACITY);
    wire [CAPACITY*LANES*WORDS-1:0] read_selections;
    genvar read_row,read_word,read_node;
    for(read_row=0;read_row<CAPACITY;read_row=read_row+1) begin:g_head_selection
        wire selected=head==read_row;
        rv32_frequency_control_tree #(.LEAVES(LANES*WORDS)) selection_tree (
            .signal_i(selected),.views_o(read_selections[read_row*LANES*WORDS +: LANES*WORDS]));
    end
    for(read_lane=0;read_lane<LANES;read_lane=read_lane+1) begin:g_read
        wire [PAYLOAD_WIDTH-1:0] payload_tree [1:2*READ_LEAVES-1];
        for(read_row=0;read_row<READ_LEAVES;read_row=read_row+1) begin:g_row
            if(read_row<CAPACITY) begin:g_present
                localparam integer HEAD_ROW=(read_row+CAPACITY-read_lane)%CAPACITY;
                for(read_word=0;read_word<WORDS;read_word=read_word+1) begin:g_word
                    localparam integer LOW=read_word*16;
                    localparam integer BITS=PAYLOAD_WIDTH-LOW>=16 ? 16 : PAYLOAD_WIDTH-LOW;
                    assign payload_tree[READ_LEAVES+read_row][LOW +: BITS]=
                        {BITS{read_selections[(HEAD_ROW*LANES+read_lane)*WORDS+read_word]}} &
                        rows[read_row*PAYLOAD_WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign payload_tree[READ_LEAVES+read_row]=0;
            end
        end
        for(read_node=1;read_node<READ_LEAVES;read_node=read_node+1) begin:g_or
            assign payload_tree[read_node]=payload_tree[2*read_node] | payload_tree[2*read_node+1];
        end
        assign data_o[read_lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]=payload_tree[1];
    end
    endgenerate
    initial begin
        if(CAPACITY<LANES || (CAPACITY & (CAPACITY-1))!=0)
            $fatal(1,"Decode queue capacity must be a power of two >= LANES");
    end

endmodule

// Functional state owner, not a buffer-only hierarchy boundary.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.
module rv32_decode_field_bank #(
    parameter integer LANES=4,WIDTH=32,ROW=0,CAPACITY=LANES,PW=(CAPACITY<2)?1:$clog2(CAPACITY)
) (
    input wire clk_i,reset_i,flush_i,
    input wire [PW-1:0] tail_i,
    input wire [LANES-1:0] push_i,
    input wire [LANES*WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    wire [LANES-1:0] selected;
    wire [LANES-1:0] selected_local;
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) select_tree (
        .signal_i(selected),.views_o(selected_local));
    genvar writer;
    generate for(writer=0;writer<LANES;writer=writer+1) begin:g_select
        assign selected[writer]=push_i[writer] && (((tail_i+writer)%CAPACITY)==ROW);
    end endgenerate
    wire write_local;
    rv32_frequency_control_tree #(.LEAVES(1)) write_enable_tree (
        .signal_i(|selected_local),.views_o(write_local));
    reg [WIDTH-1:0] next_data;
    integer lane;
    always @* begin
        next_data=0;
        for(lane=0;lane<LANES;lane=lane+1)
            next_data=next_data | ({WIDTH{selected_local[lane]}} & data_i[lane*WIDTH +: WIDTH]);
    end
    always @(posedge clk_i) begin
        // Count/head/tail invalidate the queue on the same edge. Every row
        // is fully rewritten before it becomes valid again.
        if(write_local) data_o<=next_data;
    end
endmodule
