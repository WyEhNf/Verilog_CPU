`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_lsq_tb #(
    parameter integer BE_WIDTH = 1
);
    localparam integer ENTRIES = 8;
    localparam integer TAG_WIDTH = 16;
    localparam integer ROB_TAG_WIDTH = 16;
    localparam integer ACW = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    localparam integer CW = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES + 1);
    reg clk, reset, flush, recovery_valid;
    reg [ROB_TAG_WIDTH-1:0] recovery_tag;
    reg [4:0] recovery_head;
    reg [15:0] recovery_occupancy;
    reg [BE_WIDTH-1:0] alloc_valid, alloc_load, alloc_store, alloc_addr_valid, alloc_data_valid, alloc_unsigned;
    reg [BE_WIDTH*ROB_TAG_WIDTH-1:0] alloc_rob;
    reg [BE_WIDTH*2-1:0] alloc_size;
    reg [BE_WIDTH*32-1:0] alloc_addr;
    reg [BE_WIDTH*128-1:0] alloc_data;
    reg [BE_WIDTH*16-1:0] alloc_mask;
    reg [BE_WIDTH-1:0] addr_up_valid, data_up_valid, wake_valid;
    reg [BE_WIDTH*TAG_WIDTH-1:0] addr_up_tag, data_up_tag, wake_tag;
    reg [BE_WIDTH*32-1:0] addr_up;
    reg [BE_WIDTH*128-1:0] data_up, wake_value;
    reg [BE_WIDTH*16-1:0] data_up_mask;
    reg commit_valid;
    reg [ROB_TAG_WIDTH-1:0] commit_rob;
    reg dreq_ready;
    reg dresp_valid, dresp_line_valid, dresp_error;
    reg [TAG_WIDTH-1:0] dresp_tag;
    reg [31:0] dresp_addr, dresp_word;
    reg [127:0] dresp_line;
    reg dack_valid, dack_error;
    reg [TAG_WIDTH-1:0] dack_tag;
    reg load_ready, store_ack_ready;
    wire alloc_ready, commit_ready, dreq_valid, dreq_load, dreq_store, dreq_unsigned;
    wire dresp_ready, load_valid, load_error, store_ack_valid;
    wire [BE_WIDTH-1:0] alloc_fire;
    wire [ACW-1:0] alloc_count;
    wire [BE_WIDTH*TAG_WIDTH-1:0] alloc_tag;
    wire [1:0] dreq_size;
    wire [15:0] dreq_mask;
    wire [127:0] dreq_data;
    wire [31:0] dreq_addr, load_value;
    wire [ROB_TAG_WIDTH-1:0] dreq_rob, load_rob, store_ack_rob;
    wire [TAG_WIDTH-1:0] dreq_lsq, load_lsq, store_ack_lsq;
    wire [TAG_WIDTH-1:0] alloc_tag0;
    wire [CW-1:0] occupancy;
    integer bad;
    reg [15:0] st_tag, st_tag2, st_tag3, st_tag4, st_tag5, st_tag6, unknown_tag;
    reg [TAG_WIDTH-1:0] last_alloc_tag;

    assign alloc_tag0 = alloc_tag[0 +: TAG_WIDTH];
    rv32_lsq #(.BE_WIDTH(BE_WIDTH), .LSQ_ENTRIES(ENTRIES), .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(ROB_TAG_WIDTH)) dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .recovery_valid_i(recovery_valid),
        .recovery_tag_i(recovery_tag), .recovery_head_i(recovery_head), .recovery_occupancy_i(recovery_occupancy),
        .alloc_valid_i(alloc_valid), .alloc_ready_o(alloc_ready),
        .alloc_fire_o(alloc_fire), .alloc_count_o(alloc_count), .alloc_lsq_tag_o(alloc_tag), .alloc_is_load_i(alloc_load),
        .alloc_is_store_i(alloc_store), .alloc_rob_tag_i(alloc_rob), .alloc_size_i(alloc_size), .alloc_unsigned_i(alloc_unsigned),
        .alloc_addr_valid_i(alloc_addr_valid), .alloc_addr_i(alloc_addr), .alloc_data_valid_i(alloc_data_valid),
        .alloc_store_data_i(alloc_data), .alloc_store_mask_i(alloc_mask), .addr_update_valid_i(addr_up_valid),
        .addr_update_tag_i(addr_up_tag), .addr_update_i(addr_up), .data_update_valid_i(data_up_valid),
        .data_update_tag_i(data_up_tag), .data_update_i(data_up), .data_mask_update_i(data_up_mask),
        .wakeup_valid_i(wake_valid), .wakeup_tag_i(wake_tag), .wakeup_value_i(wake_value), .store_commit_valid_i(commit_valid),
        .store_commit_ready_o(commit_ready), .store_commit_rob_tag_i(commit_rob), .dcache_req_valid_o(dreq_valid),
        .dcache_req_ready_i(dreq_ready), .dcache_req_is_load_o(dreq_load), .dcache_req_is_store_o(dreq_store),
        .dcache_req_addr_o(dreq_addr), .dcache_req_size_o(dreq_size), .dcache_req_unsigned_o(dreq_unsigned),
        .dcache_req_mask_o(dreq_mask), .dcache_req_wdata_o(dreq_data), .dcache_req_rob_tag_o(dreq_rob),
        .dcache_req_lsq_tag_o(dreq_lsq), .dcache_resp_valid_i(dresp_valid), .dcache_resp_ready_o(dresp_ready),
        .dcache_resp_lsq_tag_i(dresp_tag), .dcache_resp_addr_i(dresp_addr), .dcache_resp_line_data_i(dresp_line),
        .dcache_resp_word_data_i(dresp_word), .dcache_resp_line_valid_i(dresp_line_valid), .dcache_resp_error_i(dresp_error),
        .load_complete_valid_o(load_valid), .load_complete_ready_i(load_ready), .load_complete_rob_tag_o(load_rob),
        .load_complete_lsq_tag_o(load_lsq), .load_complete_value_o(load_value), .load_complete_error_o(load_error),
        .dcache_store_ack_valid_i(dack_valid), .dcache_store_ack_lsq_tag_i(dack_tag), .dcache_store_ack_error_i(dack_error),
        .store_ack_valid_o(store_ack_valid), .store_ack_ready_i(store_ack_ready), .store_ack_rob_tag_o(store_ack_rob),
        .store_ack_lsq_tag_o(store_ack_lsq), .store_ack_error_o(), .occupancy_o(occupancy), .head_o(), .tail_o()
    );

    initial begin clk = 0; forever #5 clk = ~clk; end

    task clear_inputs;
        begin
            alloc_valid = 0; alloc_load = 0; alloc_store = 0; alloc_addr_valid = 0; alloc_data_valid = 0; alloc_unsigned = 0;
            alloc_rob = 0; alloc_size = 0; alloc_addr = 0; alloc_data = 0; alloc_mask = 0;
            addr_up_valid = 0; data_up_valid = 0; wake_valid = 0; addr_up_tag = 0; data_up_tag = 0; wake_tag = 0;
            addr_up = 0; data_up = 0; wake_value = 0; data_up_mask = 0; commit_valid = 0; commit_rob = 0;
            dreq_ready = 1; dresp_valid = 0; dresp_line_valid = 1; dresp_error = 0; dresp_tag = 0; dresp_addr = 0;
            dresp_word = 0; dresp_line = 0; dack_valid = 0; dack_error = 0; dack_tag = 0; load_ready = 1; store_ack_ready = 1;
            recovery_valid = 0; recovery_tag = 0; recovery_head = 0; recovery_occupancy = 0;
        end
    endtask

    task alloc_one;
        input is_load;
        input is_store;
        input [15:0] rob;
        input [31:0] address;
        input [1:0] size;
        input unsign;
        input [127:0] data;
        input [15:0] mask;
        begin
            alloc_valid[0] = 1'b1; alloc_load[0] = is_load; alloc_store[0] = is_store; alloc_rob[15:0] = rob;
            alloc_addr_valid[0] = 1'b1; alloc_data_valid[0] = is_store; alloc_unsigned[0] = unsign;
            alloc_addr[31:0] = address; alloc_size[1:0] = size; alloc_data[127:0] = data; alloc_mask[15:0] = mask;
            #1; last_alloc_tag = alloc_tag0;
            @(posedge clk); #1; clear_inputs();
        end
    endtask

    task commit_store;
        input [15:0] rob;
        input [15:0] tag;
        begin
            commit_rob = rob; commit_valid = 1'b1; #1;
            if (!commit_ready) bad = bad + 1;
            @(posedge clk); #1; commit_valid = 0;
            @(posedge clk); #1;
            dack_tag = tag; dack_valid = 1'b1; @(posedge clk); #1; dack_valid = 0;
            if (!store_ack_valid) bad = bad + 1;
            @(posedge clk); #1;
        end
    endtask

    initial begin
        bad = 0; reset = 1; flush = 0; clear_inputs(); #12; reset = 0; #1;
        // A byte store forwards to all byte/word load forms and retains the
        // store until the ROB grants visibility.
        alloc_one(0, 1, 16'h0101, 32'h00000100, 0, 0, 128'h00000000000000000000000000000080, 16'h0001);
        if (!last_alloc_tag[0]) bad = bad + 1;
        begin
            st_tag = last_alloc_tag;
            alloc_one(1, 0, 16'h0202, 32'h00000100, 0, 1, 0, 0);
            if (dreq_valid) bad = bad + 1;
            commit_store(16'h0101, st_tag);
            if (!load_valid || load_value != 32'h00000080) bad = bad + 1;
        end
        // Signed load must sign extend the forwarded byte.
        alloc_one(0, 1, 16'h0303, 32'h00000110, 0, 0, 128'h00000000000000000000000000000080, 16'h0001);
        begin
            st_tag2 = last_alloc_tag;
            alloc_one(1, 0, 16'h0404, 32'h00000110, 0, 0, 0, 0);
            commit_store(16'h0303, st_tag2);
            if (!load_valid || load_value != 32'hffffff80) bad = bad + 1;
        end
        // Partial forwarding leaves a cache request for the uncovered bytes.
        alloc_one(0, 1, 16'h0505, 32'h00000201, 0, 0, 128'h0000000000000000000000000000aa00, 16'h0002);
        begin
            st_tag3 = last_alloc_tag;
            alloc_one(1, 0, 16'h0606, 32'h00000200, 2, 1, 0, 0);
            if (!dreq_valid || !dreq_load || dreq_mask[1]) bad = bad + 1;
            dresp_tag = dreq_lsq; dresp_line = 128'h00000000000000000000000011223344; dresp_line_valid = 1;
            @(posedge clk); #1; dresp_valid = 1; @(posedge clk); #1; dresp_valid = 0;
            commit_store(16'h0505, st_tag3);
            if (!load_valid || load_value != 32'h1122aa44) bad = bad + 1;
        end
        // Multiple older stores merge by byte and the youngest overlapping
        // store wins.  Only the two uncovered bytes are requested from cache.
        alloc_one(0, 1, 16'h0610, 32'h00000210, 0, 0,
                  128'h00000000000000000000000000000011, 16'h0001);
        st_tag4 = last_alloc_tag;
        alloc_one(0, 1, 16'h0611, 32'h00000211, 0, 0,
                  128'h00000000000000000000000000002200, 16'h0002);
        st_tag5 = last_alloc_tag;
        alloc_one(0, 1, 16'h0612, 32'h00000210, 0, 0,
                  128'h000000000000000000000000000000aa, 16'h0001);
        st_tag6 = last_alloc_tag;
        alloc_one(1, 0, 16'h0613, 32'h00000210, 2, 1, 0, 0);
        if (!dreq_valid || !dreq_load || dreq_mask != 16'h000c) bad = bad + 1;
        dresp_tag = dreq_lsq;
        dresp_line = 128'h00000000000000000000000044332211;
        @(posedge clk); #1; dresp_valid = 1; @(posedge clk); #1; dresp_valid = 0;
        commit_store(16'h0610, st_tag4);
        commit_store(16'h0611, st_tag5);
        commit_store(16'h0612, st_tag6);
        if (!load_valid || load_value != 32'h443322aa) bad = bad + 1;

        // Halfword forwarding keeps access-relative data and sign extension.
        alloc_one(0, 1, 16'h0620, 32'h00000222, 1, 0,
                  128'h00000000000000000000000080ff0000, 16'h000c);
        st_tag4 = last_alloc_tag;
        alloc_one(1, 0, 16'h0621, 32'h00000222, 1, 0, 0, 0);
        if (dreq_valid) bad = bad + 1;
        commit_store(16'h0620, st_tag4);
        if (!load_valid || load_value != 32'hffff80ff) bad = bad + 1;

        // An unknown older store blocks a younger load until its address is known.
        alloc_valid[0] = 1; alloc_store[0] = 1; alloc_data_valid[0] = 1; alloc_addr_valid[0] = 0; alloc_rob[15:0] = 16'h0707;
        alloc_size[1:0] = 0; alloc_data[127:0] = 128'h55; alloc_mask[15:0] = 1; #1; unknown_tag = alloc_tag0; @(posedge clk); #1; clear_inputs();
        begin
            alloc_one(1, 0, 16'h0808, 32'h00000300, 0, 1, 0, 0);
            if (dreq_valid) bad = bad + 1;
            addr_up_tag[15:0] = unknown_tag; addr_up[31:0] = 32'h00000300; addr_up_valid[0] = 1;
            @(posedge clk); #1; clear_inputs();
            if (dreq_valid) bad = bad + 1;
            commit_store(16'h0707, unknown_tag);
            if (!load_valid || load_value != 32'h00000055) bad = bad + 1;
            flush = 1; @(posedge clk); #1; flush = 0; clear_inputs();
            if (occupancy != 0) bad = bad + 1;
        end
        // A response for a flushed generation is drained without updating a
        // reused slot or becoming an architectural completion.
        alloc_one(1, 0, 16'h0909, 32'h00000400, 2, 1, 0, 0);
        dresp_tag = dreq_lsq; @(posedge clk); #1; flush = 1; @(posedge clk); #1; flush = 0; clear_inputs();
        dresp_valid = 1; @(posedge clk); #1; if (!dresp_ready || load_valid) bad = bad + 1; dresp_valid = 0;

        // A committed-store acknowledgement can coincide with a younger
        // branch recovery and must remain visible to the ROB.
        reset = 1; clear_inputs(); @(posedge clk); #1; reset = 0; #1;
        alloc_one(0, 1, 16'h0001, 32'h00000500, 2, 0, 128'h12345678, 16'h000f);
        begin
            st_tag = last_alloc_tag;
            commit_rob = 16'h0001; commit_valid = 1'b1;
            @(posedge clk); #1; commit_valid = 1'b0;
            @(posedge clk); #1;
            recovery_valid = 1'b1; recovery_tag = 16'h0011;
            recovery_head = 0; recovery_occupancy = 3;
            dack_valid = 1'b1; dack_tag = st_tag;
            @(posedge clk); #1;
            recovery_valid = 1'b0; dack_valid = 1'b0;
            if (!store_ack_valid || store_ack_rob != 16'h0001 || occupancy != 1) bad = bad + 1;
            @(posedge clk); #1; clear_inputs();
            if (occupancy != 0) bad = bad + 1;
        end

        // An older load response arriving on a younger branch recovery edge
        // completes the retained load rather than disappearing at the cache
        // handshake boundary.
        reset = 1; clear_inputs(); @(posedge clk); #1; reset = 0; #1;
        alloc_one(1, 0, 16'h0001, 32'h00000600, 2, 1, 0, 0);
        dresp_tag = dreq_lsq;
        @(posedge clk); #1;
        recovery_valid = 1'b1; recovery_tag = 16'h0011;
        recovery_head = 0; recovery_occupancy = 3;
        dresp_valid = 1'b1; dresp_line_valid = 1'b1;
        dresp_line = 128'h00000000000000000000000089abcdef;
        @(posedge clk); #1;
        recovery_valid = 1'b0; dresp_valid = 1'b0;
        if (!load_valid || load_value != 32'h89abcdef || occupancy != 1) bad = bad + 1;
        @(posedge clk); #1; clear_inputs();
        if (occupancy != 0) bad = bad + 1;
        if (bad != 0) begin $display("FAIL: B-08 LSQ BE_WIDTH=%0d checks=%0d", BE_WIDTH, bad); $finish(1); end
        $display("PASS: B-08 LSQ BE_WIDTH=%0d", BE_WIDTH); $finish(0);
    end
endmodule
