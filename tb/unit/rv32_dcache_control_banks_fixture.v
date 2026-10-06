`timescale 1ns/1ps

// Isolated functional/timing fixture, NOT a CPU or a grading configuration.
module rv32_dcache_control_state #(
    parameter integer BANKED = 0,
    parameter integer CACHE_LINES = 1024,
    parameter integer CACHE_WAYS = 2,
    parameter integer GROUP_ROWS = 16,
    parameter integer MSHRS = 4,
    parameter integer ENTRY_WIDTH = $clog2(CACHE_LINES),
    parameter integer SET_WIDTH = ($clog2(CACHE_LINES/CACHE_WAYS) < 1) ?
                                  1 : $clog2(CACHE_LINES/CACHE_WAYS)
) (
    input wire clk_i, reset_i,
    input wire refill_valid_i, refill_dirty_i, local_valid_i, miss_valid_i,
    input wire prefetch_valid_i, store_hit_i, hit_valid_i,
    input wire [ENTRY_WIDTH-1:0] refill_entry_i, local_entry_i, miss_entry_i,
    input wire [ENTRY_WIDTH-1:0] prefetch_entry_i, hit_entry_i,
    input wire [SET_WIDTH-1:0] request_set_i, prefetch_set_i,
    input wire [3:0] request_action_i,
    input wire [2:0] second_free_i, free_i, matching_i,
    input wire [15:0] write_mask_i,
    input wire [127:0] write_data_i,
    output wire [CACHE_LINES-1:0] valid_o, dirty_o,
    output wire [CACHE_LINES/CACHE_WAYS-1:0] lru_o,
    output wire [MSHRS*128-1:0] mshr_data_o
);
    genvar group_id, mshr_id;
    generate if (BANKED != 0) begin : g_banked
        for (group_id = 0; group_id < CACHE_LINES/GROUP_ROWS; group_id = group_id + 1) begin : g_metadata
            rv32_dcache_metadata_bank #(.CACHE_LINES(CACHE_LINES), .CACHE_WAYS(CACHE_WAYS),
                .GROUP_ROWS(GROUP_ROWS), .GROUP_ID(group_id)) bank (
                .clk_i(clk_i), .reset_i(reset_i), .refill_valid_i(refill_valid_i),
                .refill_entry_i(refill_entry_i), .refill_dirty_i(refill_dirty_i),
                .local_valid_i(local_valid_i), .local_entry_i(local_entry_i),
                .miss_valid_i(miss_valid_i), .miss_entry_i(miss_entry_i),
                .prefetch_valid_i(prefetch_valid_i), .prefetch_entry_i(prefetch_entry_i),
                .store_hit_i(store_hit_i), .hit_entry_i(hit_entry_i),
                .hit_valid_i(hit_valid_i), .request_set_i(request_set_i), .prefetch_set_i(prefetch_set_i),
                .valid_o(valid_o[group_id*GROUP_ROWS +: GROUP_ROWS]),
                .dirty_o(dirty_o[group_id*GROUP_ROWS +: GROUP_ROWS]),
                .lru_o(lru_o[group_id*(GROUP_ROWS/CACHE_WAYS) +: GROUP_ROWS/CACHE_WAYS])
            );
        end
        for (mshr_id = 0; mshr_id < MSHRS; mshr_id = mshr_id + 1) begin : g_mshr
            rv32_dcache_mshr_data_bank #(.MSHR_ID(mshr_id)) bank (
                .clk_i(clk_i), .reset_i(reset_i), .request_action_i(request_action_i),
                .prefetch_allocate_i(prefetch_valid_i), .second_free_i(second_free_i),
                .free_i(free_i), .matching_i(matching_i), .write_mask_i(write_mask_i), .write_data_i(write_data_i),
                .data_o(mshr_data_o[mshr_id*128 +: 128])
            );
        end
    end else begin : g_reference
        reg [CACHE_LINES-1:0] valid_bits, dirty_bits;
        reg [CACHE_LINES/CACHE_WAYS-1:0] lru;
        reg [MSHRS*128-1:0] mshr;
        integer byte_id;
        assign valid_o=valid_bits;
        assign dirty_o=dirty_bits;
        assign lru_o=lru;
        assign mshr_data_o=mshr;
        always @(posedge clk_i) begin
            if (reset_i) begin
                valid_bits<=0;
                lru<=0;
                mshr<=0;
                // Dirty bits intentionally keep their old/unknown values.
            end else begin
                // Cache write priority: store < miss < prefetch < local < refill.
                if (store_hit_i) dirty_bits[hit_entry_i]<=1'b1;
                if (miss_valid_i) begin valid_bits[miss_entry_i]<=0; dirty_bits[miss_entry_i]<=0; end
                if (prefetch_valid_i) begin valid_bits[prefetch_entry_i]<=0; dirty_bits[prefetch_entry_i]<=0; end
                if (local_valid_i) begin valid_bits[local_entry_i]<=1; dirty_bits[local_entry_i]<=1; end
                if (refill_valid_i) begin valid_bits[refill_entry_i]<=1; dirty_bits[refill_entry_i]<=refill_dirty_i; end
                if (CACHE_WAYS==2) begin
                    if (hit_valid_i) lru[request_set_i]<=!hit_entry_i[0];
                    if (miss_valid_i) lru[request_set_i]<=!miss_entry_i[0];
                    if (prefetch_valid_i) lru[prefetch_set_i]<=!prefetch_entry_i[0];
                end
                if (request_action_i==8 && free_i<MSHRS)
                    mshr[free_i*128 +: 128]<=write_data_i;
                if (request_action_i==6 && matching_i<MSHRS)
                    mshr[matching_i*128 +: 128]<=write_data_i;
                if (request_action_i==7 && matching_i<MSHRS)
                    for (byte_id=0; byte_id<16; byte_id=byte_id+1)
                        if (write_mask_i[byte_id]) mshr[matching_i*128+byte_id*8 +: 8]<=write_data_i[byte_id*8 +: 8];
                if (prefetch_valid_i && second_free_i<MSHRS) mshr[second_free_i*128 +: 128]<=0;
            end
        end
    end endgenerate
endmodule

module student_top #(
    parameter integer BANKED=0,
    parameter integer CACHE_LINES=1024,
    parameter integer CACHE_WAYS=2,
    parameter integer GROUP_ROWS=16,
    parameter integer ENTRY_WIDTH=$clog2(CACHE_LINES),
    parameter integer SET_WIDTH=$clog2(CACHE_LINES/CACHE_WAYS)
) (
    input wire clock, reset,
    input wire [6:0] events_i,
    input wire [5*ENTRY_WIDTH+2*SET_WIDTH-1:0] indexes_i,
    input wire [3:0] action_i,
    input wire [8:0] mshr_indexes_i,
    input wire [15:0] mask_i,
    input wire [127:0] data_i,
    output wire [CACHE_LINES-1:0] valid_o, dirty_o,
    output wire [CACHE_LINES/CACHE_WAYS-1:0] lru_o,
    output wire [511:0] mshr_data_o,
    input wire ram_en_i, ram_we_i,
    input wire [3:0] ram_mask_i, ram_addr_i,
    input wire [31:0] ram_wdata_i,
    output wire [31:0] ram_rdata_o
);
    reg [6:0] events;
    reg [5*ENTRY_WIDTH+2*SET_WIDTH-1:0] indexes;
    reg [3:0] action;
    reg [8:0] mshr_indexes;
    reg [15:0] mask;
    reg [127:0] data;
    always @(posedge clock) begin
        events<=reset ? 0 : events_i;
        indexes<=indexes_i;
        action<=reset ? 0 : action_i;
        mshr_indexes<=mshr_indexes_i;
        mask<=mask_i;
        data<=data_i;
    end
    rv32_dcache_control_state #(.BANKED(BANKED), .CACHE_LINES(CACHE_LINES),
        .CACHE_WAYS(CACHE_WAYS), .GROUP_ROWS(GROUP_ROWS)) state (
        .clk_i(clock), .reset_i(reset), .refill_valid_i(events[0]), .refill_dirty_i(events[1]),
        .local_valid_i(events[2]), .miss_valid_i(events[3]), .prefetch_valid_i(events[4]),
        .store_hit_i(events[5]), .hit_valid_i(events[6]),
        .refill_entry_i(indexes[0*ENTRY_WIDTH +: ENTRY_WIDTH]),
        .local_entry_i(indexes[1*ENTRY_WIDTH +: ENTRY_WIDTH]),
        .miss_entry_i(indexes[2*ENTRY_WIDTH +: ENTRY_WIDTH]),
        .prefetch_entry_i(indexes[3*ENTRY_WIDTH +: ENTRY_WIDTH]),
        .hit_entry_i(indexes[4*ENTRY_WIDTH +: ENTRY_WIDTH]),
        .request_set_i(indexes[5*ENTRY_WIDTH +: SET_WIDTH]),
        .prefetch_set_i(indexes[5*ENTRY_WIDTH+SET_WIDTH +: SET_WIDTH]),
        .request_action_i(action), .second_free_i(mshr_indexes[2:0]),
        .free_i(mshr_indexes[5:3]), .matching_i(mshr_indexes[8:6]),
        .write_mask_i(mask), .write_data_i(data), .valid_o(valid_o), .dirty_o(dirty_o),
        .lru_o(lru_o), .mshr_data_o(mshr_data_o)
    );
    sram_fakeram #(.DEPTH(16), .WIDTH(32), .WRITE_GRANULARITY(8)) ram (
        .clk(clock), .en(ram_en_i), .we(ram_we_i), .wmask(ram_mask_i), .addr(ram_addr_i),
        .wdata(ram_wdata_i), .rdata(ram_rdata_o)
    );
endmodule

`ifndef SYNTHESIS
module rv32_dcache_control_banks_tb #(
    parameter integer CACHE_LINES=64,
    parameter integer CACHE_WAYS=2,
    parameter integer GROUP_ROWS=16
);
    localparam integer EW=$clog2(CACHE_LINES), SW=$clog2(CACHE_LINES/CACHE_WAYS);
    reg clk=0;
    always #5 clk=~clk;
    reg reset;
    reg [6:0] events;
    reg [EW-1:0] refill_entry, local_entry, miss_entry, prefetch_entry, hit_entry;
    reg [SW-1:0] request_set, prefetch_set;
    reg [3:0] action;
    reg [2:0] second_free, free_index, matching;
    reg [15:0] mask;
    reg [127:0] data;
    wire [CACHE_LINES-1:0] valid [0:1], dirty [0:1];
    wire [CACHE_LINES/CACHE_WAYS-1:0] lru [0:1];
    wire [511:0] mshr [0:1];
    genvar impl;
    generate for (impl=0; impl<2; impl=impl+1) begin : g_impl
        rv32_dcache_control_state #(.BANKED(impl), .CACHE_LINES(CACHE_LINES),
            .CACHE_WAYS(CACHE_WAYS), .GROUP_ROWS(GROUP_ROWS)) dut (
            .clk_i(clk), .reset_i(reset), .refill_valid_i(events[0]), .refill_dirty_i(events[1]),
            .local_valid_i(events[2]), .miss_valid_i(events[3]), .prefetch_valid_i(events[4]),
            .store_hit_i(events[5]), .hit_valid_i(events[6]), .refill_entry_i(refill_entry),
            .local_entry_i(local_entry), .miss_entry_i(miss_entry), .prefetch_entry_i(prefetch_entry),
            .hit_entry_i(hit_entry), .request_set_i(request_set), .prefetch_set_i(prefetch_set),
            .request_action_i(action), .second_free_i(second_free), .free_i(free_index), .matching_i(matching),
            .write_mask_i(mask), .write_data_i(data), .valid_o(valid[impl]), .dirty_o(dirty[impl]),
            .lru_o(lru[impl]), .mshr_data_o(mshr[impl])
        );
    end endgenerate
    integer cycle, seed;
    initial begin
        reset=1; events=0; refill_entry=0; local_entry=0; miss_entry=0;
        prefetch_entry=0; hit_entry=0; request_set=0; prefetch_set=0;
        action=0; second_free=0; free_index=0; matching=0; mask=0; data=0;
        seed=32'h3192ad48;
        for (cycle=0; cycle<2000; cycle=cycle+1) begin
            @(negedge clk);
            reset=(cycle<4 || cycle%251==0);
            events=$random(seed);
            refill_entry=$random(seed); local_entry=$random(seed); miss_entry=$random(seed);
            prefetch_entry=$random(seed); hit_entry=$random(seed);
            request_set=$random(seed); prefetch_set=$random(seed);
            action=($random(seed)&32'h7fffffff)%9;
            second_free=$random(seed); free_index=$random(seed); matching=$random(seed);
            mask=$random(seed);
            data={$random(seed),$random(seed),$random(seed),$random(seed)};
            // Directed collisions force all write priorities on one row/set.
            if (cycle%11==0) begin
                local_entry=refill_entry; miss_entry=refill_entry;
                prefetch_entry=refill_entry; hit_entry=refill_entry;
                prefetch_set=request_set; events=7'h7f;
                second_free=free_index; matching=free_index; action=8;
            end
            @(posedge clk); #1;
            if (valid[0]!==valid[1] || dirty[0]!==dirty[1] || lru[0]!==lru[1] || mshr[0]!==mshr[1])
                $fatal(1,"Cache-control bank state differs cycle=%0d lines=%0d ways=%0d group=%0d",cycle,CACHE_LINES,CACHE_WAYS,GROUP_ROWS);
        end
        $display("PASS: cache-control banks 2000 cycles lines=%0d ways=%0d group=%0d",CACHE_LINES,CACHE_WAYS,GROUP_ROWS);
        $finish;
    end
endmodule
`endif
