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
`ifdef CPU2026_WORD_SIM
    // Vector masks preserve the per-row nonblocking-write priority. Query
    // registers above remain unchanged and updates use their pre-edge value.
    wire [GROUP_ROWS-1:0] sim_refill =
        (refill_valid_i && refill_entry_i/GROUP_ROWS==GROUP_ID) ?
        ({{(GROUP_ROWS-1){1'b0}},1'b1} << (refill_entry_i%GROUP_ROWS)) : 0;
    wire [GROUP_ROWS-1:0] sim_local =
        (local_valid_i && local_entry_i/GROUP_ROWS==GROUP_ID) ?
        ({{(GROUP_ROWS-1){1'b0}},1'b1} << (local_entry_i%GROUP_ROWS)) : 0;
    wire sim_miss_here = miss_action && (LOCAL_QUERY ? query_request_active : miss_entry_i/GROUP_ROWS==GROUP_ID);
    wire sim_prefetch_here = prefetch_valid_i && (LOCAL_QUERY ? query_prefetch_active : prefetch_entry_i/GROUP_ROWS==GROUP_ID);
    wire sim_store_here = store_action && (LOCAL_QUERY ? query_request_active : hit_entry_i/GROUP_ROWS==GROUP_ID);
    wire [LOCAL_SET_WIDTH:0] sim_miss_row = LOCAL_QUERY ?
        query_request_row*CACHE_WAYS+miss_entry_i%CACHE_WAYS : miss_entry_i%GROUP_ROWS;
    wire [LOCAL_SET_WIDTH:0] sim_prefetch_row = LOCAL_QUERY ?
        query_prefetch_row*CACHE_WAYS+prefetch_entry_i%CACHE_WAYS : prefetch_entry_i%GROUP_ROWS;
    wire [LOCAL_SET_WIDTH:0] sim_store_row = LOCAL_QUERY ?
        query_request_row*CACHE_WAYS+hit_entry_i%CACHE_WAYS : hit_entry_i%GROUP_ROWS;
    wire [GROUP_ROWS-1:0] sim_miss = sim_miss_here ? ({{(GROUP_ROWS-1){1'b0}},1'b1} << sim_miss_row) : 0;
    wire [GROUP_ROWS-1:0] sim_prefetch = sim_prefetch_here ? ({{(GROUP_ROWS-1){1'b0}},1'b1} << sim_prefetch_row) : 0;
    wire [GROUP_ROWS-1:0] sim_store = sim_store_here ? ({{(GROUP_ROWS-1){1'b0}},1'b1} << sim_store_row) : 0;
    wire [GROUP_ROWS-1:0] sim_fill = sim_refill | sim_local;
    wire [GROUP_ROWS-1:0] sim_clear = (sim_miss | sim_prefetch) & ~sim_fill;
    wire [GROUP_ROWS-1:0] sim_dirty_set =
        (sim_local & ~sim_refill) | (sim_refill & {GROUP_ROWS{refill_dirty_i}}) |
        (sim_store & ~(sim_fill | sim_clear));
    wire [GROUP_SETS-1:0] sim_lru_prefetch =
        (prefetch_valid_i && (LOCAL_QUERY ? query_prefetch_active : prefetch_set_i/GROUP_SETS==GROUP_ID)) ?
        ({{(GROUP_SETS-1){1'b0}},1'b1} << (LOCAL_QUERY ? query_prefetch_row : prefetch_set_i%GROUP_SETS)) : 0;
    wire [GROUP_SETS-1:0] sim_lru_miss =
        (miss_action && (LOCAL_QUERY ? query_request_active : request_set_i/GROUP_SETS==GROUP_ID)) ?
        ({{(GROUP_SETS-1){1'b0}},1'b1} << (LOCAL_QUERY ? query_request_row : request_set_i%GROUP_SETS)) : 0;
    wire [GROUP_SETS-1:0] sim_lru_hit =
        (hit_action && (LOCAL_QUERY ? query_request_active : request_set_i/GROUP_SETS==GROUP_ID)) ?
        ({{(GROUP_SETS-1){1'b0}},1'b1} << (LOCAL_QUERY ? query_request_row : request_set_i%GROUP_SETS)) : 0;
    wire [GROUP_SETS-1:0] sim_lru_write = sim_lru_prefetch | sim_lru_miss | sim_lru_hit;
    wire [GROUP_SETS-1:0] sim_lru_set =
        (sim_lru_prefetch & {GROUP_SETS{!prefetch_entry_i[0]}}) |
        (sim_lru_miss & ~sim_lru_prefetch & {GROUP_SETS{!miss_entry_i[0]}}) |
        (sim_lru_hit & ~(sim_lru_prefetch | sim_lru_miss) & {GROUP_SETS{!hit_entry_i[0]}});
    always @(posedge clk_i) begin
        if(reset_i) begin valid_o<=0; lru_o<=0; end
        else begin
            if(|(sim_fill | sim_clear)) valid_o <= (valid_o & ~sim_clear) | sim_fill;
            if(|(sim_fill | sim_clear | sim_store))
                dirty_o <= (dirty_o & ~(sim_refill | sim_clear)) | sim_dirty_set;
            if(CACHE_WAYS==2 && |sim_lru_write) lru_o <= (lru_o & ~sim_lru_write) | sim_lru_set;
        end
    end
`else
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
`endif
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

`ifdef CPU2026_WORD_SIM
// Equivalent simulation representation for the 1024-line, two-way local
// query banks. Query addresses hold through reset, as in every original bank.
module rv32_dcache_metadata_word (
    input wire clk_i, reset_i,
    input wire [3:0] request_action_i,
    input wire refill_valid_i, refill_dirty_i, local_valid_i,
    input wire [9:0] refill_entry_i, local_entry_i,
    input wire miss_way_i, prefetch_valid_i, prefetch_way_i, hit_way_i,
    input wire query_fire_i,
    input wire [8:0] query_request_set_i, query_prefetch_set_i,
    output wire [1:0] query_request_valid_o, query_request_dirty_o,
    output wire [1:0] query_prefetch_valid_o, query_prefetch_dirty_o,
    output wire query_request_lru_o, query_prefetch_lru_o,
    output wire [1023:0] valid_o, dirty_o,
    output wire [511:0] lru_o
);
    reg [31:0] valid_words [0:31], dirty_words [0:31];
    reg [31:0] lru_words [0:15];
    reg [8:0] request_set, prefetch_set;
    reg query_seen;
    wire [9:0] miss_entry = {request_set,miss_way_i};
    wire [9:0] prefetch_entry = {prefetch_set,prefetch_way_i};
    wire [9:0] hit_entry = {request_set,hit_way_i};
    genvar w;
    generate for(w=0;w<32;w=w+1) begin:g_valid_view
        assign valid_o[w*32+:32]=valid_words[w];
        assign dirty_o[w*32+:32]=dirty_words[w];
    end
    for(w=0;w<16;w=w+1) begin:g_lru_view
        assign lru_o[w*32+:32]=lru_words[w];
    end endgenerate
    assign query_request_valid_o = query_seen ?
        valid_words[request_set[8:4]][{request_set[3:0],1'b0}+:2] : 2'b0;
    assign query_request_dirty_o = query_seen ?
        dirty_words[request_set[8:4]][{request_set[3:0],1'b0}+:2] : 2'b0;
    assign query_prefetch_valid_o = query_seen ?
        valid_words[prefetch_set[8:4]][{prefetch_set[3:0],1'b0}+:2] : 2'b0;
    assign query_prefetch_dirty_o = query_seen ?
        dirty_words[prefetch_set[8:4]][{prefetch_set[3:0],1'b0}+:2] : 2'b0;
    assign query_request_lru_o = query_seen ?
        lru_words[request_set[8:5]][request_set[4:0]] : 1'b0;
    assign query_prefetch_lru_o = query_seen ?
        lru_words[prefetch_set[8:5]][prefetch_set[4:0]] : 1'b0;
    integer row;
    always @(posedge clk_i) begin
        if (!reset_i && query_fire_i) begin
            request_set <= query_request_set_i;
            prefetch_set <= query_prefetch_set_i;
            query_seen <= 1'b1;
        end
        if (reset_i) begin
            for(row=0;row<32;row=row+1) valid_words[row]<=32'b0;
            for(row=0;row<16;row=row+1) lru_words[row]<=32'b0;
            // Dirty bits have no reset in the original state owners.
        end else begin
            // Ordered bit writes reproduce refill > local > clear > store.
            // Indices use the old captured query addresses on this edge.
            if (query_seen && request_action_i == 4'd2)
                dirty_words[hit_entry[9:5]][hit_entry[4:0]] <= 1'b1;
            if (query_seen && request_action_i == 4'd8) begin
                valid_words[miss_entry[9:5]][miss_entry[4:0]] <= 1'b0;
                dirty_words[miss_entry[9:5]][miss_entry[4:0]] <= 1'b0;
            end
            if (query_seen && prefetch_valid_i) begin
                valid_words[prefetch_entry[9:5]][prefetch_entry[4:0]] <= 1'b0;
                dirty_words[prefetch_entry[9:5]][prefetch_entry[4:0]] <= 1'b0;
            end
            if (local_valid_i) begin
                valid_words[local_entry_i[9:5]][local_entry_i[4:0]] <= 1'b1;
                dirty_words[local_entry_i[9:5]][local_entry_i[4:0]] <= 1'b1;
            end
            if (refill_valid_i) begin
                valid_words[refill_entry_i[9:5]][refill_entry_i[4:0]] <= 1'b1;
                dirty_words[refill_entry_i[9:5]][refill_entry_i[4:0]] <= refill_dirty_i;
            end
            if (query_seen && (request_action_i == 4'd1 || request_action_i == 4'd2))
                lru_words[request_set[8:5]][request_set[4:0]] <= !hit_way_i;
            if (query_seen && request_action_i == 4'd8)
                lru_words[request_set[8:5]][request_set[4:0]] <= !miss_way_i;
            if (query_seen && prefetch_valid_i)
                lru_words[prefetch_set[8:5]][prefetch_set[4:0]] <= !prefetch_way_i;
        end
    end
endmodule
`endif
