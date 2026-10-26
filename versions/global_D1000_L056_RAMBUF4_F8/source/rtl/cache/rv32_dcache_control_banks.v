`timescale 1ns/1ps

// Functional state banks, not buffer-cell stubs or cache-data substitutes.
// Keep their logic/state boundaries so the unmodified flattened/default-ABC
// flow cannot share one write-control gate across every metadata flip-flop.
// Cache data/tags remain in the CPU's real sram_fakeram instances. The cache
// selects these state owners only with STATIC_UPDATES=2 (default remains 0).
(* keep_hierarchy = 1 *)
module rv32_dcache_metadata_bank #(
    parameter integer CACHE_LINES = 1024,
    parameter integer CACHE_WAYS = 2,
    parameter integer GROUP_ROWS = 16,
    parameter integer GROUP_ID = 0,
    parameter integer LOCAL_QUERY = 0,
    parameter integer LOCAL_ACTION_DECODE = 0,
    parameter integer ENTRY_WIDTH = $clog2(CACHE_LINES),
    parameter integer SET_WIDTH = ($clog2(CACHE_LINES / CACHE_WAYS) < 1) ?
                                  1 : $clog2(CACHE_LINES / CACHE_WAYS)
) (
    input wire clk_i,
    input wire reset_i,
    input wire [3:0] request_action_i,
    input wire refill_valid_i,
    input wire [ENTRY_WIDTH-1:0] refill_entry_i,
    input wire refill_dirty_i,
    input wire local_valid_i,
    input wire [ENTRY_WIDTH-1:0] local_entry_i,
    input wire miss_valid_i,
    input wire [ENTRY_WIDTH-1:0] miss_entry_i,
    input wire prefetch_valid_i,
    input wire [ENTRY_WIDTH-1:0] prefetch_entry_i,
    input wire store_hit_i,
    input wire [ENTRY_WIDTH-1:0] hit_entry_i,
    input wire hit_valid_i,
    input wire [SET_WIDTH-1:0] request_set_i,
    input wire [SET_WIDTH-1:0] prefetch_set_i,
    input wire query_fire_i,
    input wire [SET_WIDTH-1:0] query_request_set_i,
    input wire [SET_WIDTH-1:0] query_prefetch_set_i,
    output wire [CACHE_WAYS-1:0] query_request_valid_o,
    output wire [CACHE_WAYS-1:0] query_request_dirty_o,
    output wire [CACHE_WAYS-1:0] query_prefetch_valid_o,
    output wire [CACHE_WAYS-1:0] query_prefetch_dirty_o,
    output wire query_request_lru_o,
    output wire query_prefetch_lru_o,
    output reg [GROUP_ROWS-1:0] valid_o,
    output reg [GROUP_ROWS-1:0] dirty_o,
    output reg [GROUP_ROWS/CACHE_WAYS-1:0] lru_o
);
    localparam integer GROUP_SETS = GROUP_ROWS / CACHE_WAYS;
    localparam integer LOCAL_SET_WIDTH = $clog2(GROUP_SETS);
    // Capture addresses, not metadata. A held query must observe later
    // fills/store hits/LRU updates, including updates on its acceptance edge.
    // These are functional local query registers owned by the state bank.
    reg [LOCAL_SET_WIDTH-1:0] query_request_row, query_prefetch_row;
    reg query_request_active, query_prefetch_active;
    generate if (LOCAL_QUERY != 0) begin : g_local_query
        always @(posedge clk_i) begin
            if (!reset_views[RESET_DOMAINS-1] && query_fire_i) begin
                query_request_row <= query_request_set_i % GROUP_SETS;
                query_prefetch_row <= query_prefetch_set_i % GROUP_SETS;
                query_request_active <= query_request_set_i / GROUP_SETS == GROUP_ID;
                query_prefetch_active <= query_prefetch_set_i / GROUP_SETS == GROUP_ID;
            end
        end
        genvar query_way;
        for (query_way = 0; query_way < CACHE_WAYS; query_way = query_way + 1) begin : g_way
            assign query_request_valid_o[query_way] = query_request_active ?
                valid_o[query_request_row*CACHE_WAYS + query_way] : 1'b0;
            assign query_request_dirty_o[query_way] = query_request_active ?
                dirty_o[query_request_row*CACHE_WAYS + query_way] : 1'b0;
            assign query_prefetch_valid_o[query_way] = query_prefetch_active ?
                valid_o[query_prefetch_row*CACHE_WAYS + query_way] : 1'b0;
            assign query_prefetch_dirty_o[query_way] = query_prefetch_active ?
                dirty_o[query_prefetch_row*CACHE_WAYS + query_way] : 1'b0;
        end
        assign query_request_lru_o = query_request_active ? lru_o[query_request_row] : 1'b0;
        assign query_prefetch_lru_o = query_prefetch_active ? lru_o[query_prefetch_row] : 1'b0;
    end else begin : g_no_local_query
        assign query_request_valid_o = {CACHE_WAYS{1'b0}};
        assign query_request_dirty_o = {CACHE_WAYS{1'b0}};
        assign query_prefetch_valid_o = {CACHE_WAYS{1'b0}};
        assign query_prefetch_dirty_o = {CACHE_WAYS{1'b0}};
        assign query_request_lru_o = 1'b0;
        assign query_prefetch_lru_o = 1'b0;
    end endgenerate
    // Decode the real request command inside its state owner. Sending one
    // predecoded miss flag to every row of every bank creates a chip-wide
    // fanout cone; bank-local decode retains identical edge and priority.
    wire miss_action = LOCAL_ACTION_DECODE ? request_action_i == 4'd8 : miss_valid_i;
    wire store_action = LOCAL_ACTION_DECODE ? request_action_i == 4'd2 : store_hit_i;
    wire hit_action = LOCAL_ACTION_DECODE ?
        (request_action_i == 4'd1 || request_action_i == 4'd2) : hit_valid_i;
    localparam integer RESET_DOMAINS=GROUP_ROWS+GROUP_ROWS/CACHE_WAYS+1;
    wire [RESET_DOMAINS-1:0] reset_views;
    rv32_frequency_control_tree #(.LEAVES(RESET_DOMAINS)) reset_tree (
        .signal_i(reset_i),.views_o(reset_views));
    genvar row, set_id;
    generate
        for (row = 0; row < GROUP_ROWS; row = row + 1) begin : g_row
            localparam integer ABS_ROW = GROUP_ID * GROUP_ROWS + row;
            wire refill = refill_valid_i && refill_entry_i == ABS_ROW;
            wire local_fill = local_valid_i && local_entry_i == ABS_ROW;
            wire miss = miss_action && ((LOCAL_QUERY != 0) ?
                (query_request_active && query_request_row == row/CACHE_WAYS &&
                 miss_entry_i % CACHE_WAYS == row%CACHE_WAYS) : miss_entry_i == ABS_ROW);
            wire prefetch = prefetch_valid_i && ((LOCAL_QUERY != 0) ?
                (query_prefetch_active && query_prefetch_row == row/CACHE_WAYS &&
                 prefetch_entry_i % CACHE_WAYS == row%CACHE_WAYS) : prefetch_entry_i == ABS_ROW);
            wire store_hit = store_action && ((LOCAL_QUERY != 0) ?
                (query_request_active && query_request_row == row/CACHE_WAYS &&
                 hit_entry_i % CACHE_WAYS == row%CACHE_WAYS) : hit_entry_i == ABS_ROW);
            always @(posedge clk_i) begin
                if (reset_views[row]) begin
                    valid_o[row] <= 1'b0;
                    // Original dirty metadata has no global reset value.
                end else if (refill) begin
                    valid_o[row] <= 1'b1;
                    dirty_o[row] <= refill_dirty_i;
                end else if (local_fill) begin
                    valid_o[row] <= 1'b1;
                    dirty_o[row] <= 1'b1;
                end else if (prefetch || miss) begin
                    valid_o[row] <= 1'b0;
                    dirty_o[row] <= 1'b0;
                end else if (store_hit) begin
                    dirty_o[row] <= 1'b1;
                end
            end
        end
        for (set_id = 0; set_id < GROUP_ROWS/CACHE_WAYS; set_id = set_id + 1) begin : g_set
            localparam integer ABS_SET = GROUP_ID * (GROUP_ROWS/CACHE_WAYS) + set_id;
            always @(posedge clk_i) begin
                if (reset_views[GROUP_ROWS+set_id]) lru_o[set_id] <= 1'b0;
                else if (CACHE_WAYS == 2) begin
                    // Original request order: prefetch allocation wins over
                    // demand allocation, which wins over a load/store hit.
                    if (prefetch_valid_i && ((LOCAL_QUERY != 0) ?
                        (query_prefetch_active && query_prefetch_row == set_id) : prefetch_set_i == ABS_SET))
                        lru_o[set_id] <= !prefetch_entry_i[0];
                    else if (miss_action && ((LOCAL_QUERY != 0) ?
                        (query_request_active && query_request_row == set_id) : request_set_i == ABS_SET))
                        lru_o[set_id] <= !miss_entry_i[0];
                    else if (hit_action && ((LOCAL_QUERY != 0) ?
                        (query_request_active && query_request_row == set_id) : request_set_i == ABS_SET))
                        lru_o[set_id] <= !hit_entry_i[0];
                end
            end
        end
    endgenerate
    initial begin
        if (CACHE_LINES < 16 || (CACHE_LINES & (CACHE_LINES-1)) != 0 ||
            (CACHE_WAYS != 1 && CACHE_WAYS != 2) || GROUP_ROWS < 2 ||
            (GROUP_ROWS & (GROUP_ROWS-1)) != 0 || GROUP_ROWS > CACHE_LINES ||
            GROUP_ID < 0 || GROUP_ID >= CACHE_LINES/GROUP_ROWS ||
            (LOCAL_QUERY != 0 && LOCAL_QUERY != 1)) begin
            $display("ERROR: invalid D-cache metadata bank geometry");
            $finish;
        end
    end
endmodule

// Actual in-flight store/RFO write-data state, retaining original byte masks
// and zero > write > merge priority. This is not the cache's data array.
(* keep_hierarchy = 1 *)
module rv32_dcache_mshr_data_bank #(
    parameter integer MSHR_ID = 0
) (
    input wire clk_i,
    input wire reset_i,
    input wire [3:0] request_action_i,
    input wire prefetch_allocate_i,
    input wire [2:0] second_free_i,
    input wire [2:0] free_i,
    input wire [2:0] matching_i,
    input wire [15:0] write_mask_i,
    input wire [127:0] write_data_i,
    output wire [127:0] data_o
);
    wire write_zero = prefetch_allocate_i && second_free_i == MSHR_ID;
    wire write_word = (request_action_i == 4'd8 && free_i == MSHR_ID) ||
                      (request_action_i == 4'd6 && matching_i == MSHR_ID);
    wire merge_word = request_action_i == 4'd7 && matching_i == MSHR_ID;
    wire [15:0] zero_views;
    rv32_frequency_control_tree #(.LEAVES(16)) zero_tree (
        .signal_i(reset_i || write_zero),.views_o(zero_views));
    genvar byte_id;
    generate for(byte_id=0;byte_id<16;byte_id=byte_id+1) begin:g_byte
        wire write_enable;
        wire [7:0] next_byte,saved_byte;
        wire update=write_word || (merge_word && write_mask_i[byte_id]);
        rv32_frequency_event_select #(.WIDTH(8),.EVENTS(2)) selector (
            .events_i({zero_views[byte_id],update}),
            .values_i({8'b0,write_data_i[byte_id*8 +: 8]}),
            .write_o(write_enable),.value_o(next_byte));
        rv32_frequency_word_bank #(.WIDTH(8)) owner (
            .clk_i(clk_i),.write_i(write_enable),.data_i(next_byte),.data_o(saved_byte));
        assign data_o[byte_id*8 +: 8]=saved_byte;
    end endgenerate
    initial begin
        if (MSHR_ID < 0 || MSHR_ID > 7) begin
            $display("ERROR: invalid D-cache MSHR data bank id");
            $finish;
        end
    end
endmodule
