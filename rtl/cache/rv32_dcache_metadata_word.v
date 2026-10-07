`timescale 1ns/1ps
`include "rv32im_defs.vh"
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
        if (!reset_i && query_fire_i)
        begin
            request_set <= query_request_set_i;
            prefetch_set <= query_prefetch_set_i;
            query_seen <= 1'b1;
        end
        if (reset_i)
        begin
            for(row=0;row<32;row=row+1)
                valid_words[row]<=32'b0;
            for(row=0;row<16;row=row+1)
                lru_words[row]<=32'b0;
        end
        else
        begin
            if (query_seen && request_action_i == 4'd2)
                dirty_words[hit_entry[9:5]][hit_entry[4:0]] <= 1'b1;
            if (query_seen && request_action_i == 4'd8)
            begin
                valid_words[miss_entry[9:5]][miss_entry[4:0]] <= 1'b0;
                dirty_words[miss_entry[9:5]][miss_entry[4:0]] <= 1'b0;
            end
            if (query_seen && prefetch_valid_i)
            begin
                valid_words[prefetch_entry[9:5]][prefetch_entry[4:0]] <= 1'b0;
                dirty_words[prefetch_entry[9:5]][prefetch_entry[4:0]] <= 1'b0;
            end
            if (local_valid_i)
            begin
                valid_words[local_entry_i[9:5]][local_entry_i[4:0]] <= 1'b1;
                dirty_words[local_entry_i[9:5]][local_entry_i[4:0]] <= 1'b1;
            end
            if (refill_valid_i)
            begin
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
