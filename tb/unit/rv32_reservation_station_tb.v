`timescale 1ns/1ps

module rv32_reservation_station_tb #(
    parameter integer BE_WIDTH = 1,
    parameter integer ENTRIES = 4
);
    localparam integer OPW = 6;
    localparam integer TAGW = 16;
    localparam integer PAW = 6;
    localparam integer SW = $clog2(ENTRIES);
    localparam integer ACW = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    localparam integer CW = $clog2(ENTRIES + 1);
    reg clk, reset;
    reg [BE_WIDTH-1:0] alloc_valid, target_live, src1_ready, src2_ready;
    reg [(BE_WIDTH*OPW)-1:0] alloc_op;
    reg [(BE_WIDTH*32)-1:0] alloc_pc, alloc_imm, alloc_pred_target, src1_value, src2_value;
    reg [BE_WIDTH-1:0] alloc_pred_taken, alloc_mem_unsigned;
    reg [(BE_WIDTH*2)-1:0] alloc_pred_kind, alloc_mem_size;
    reg [(BE_WIDTH*TAGW)-1:0] alloc_tag, src1_tag, src2_tag;
    reg [(BE_WIDTH*PAW)-1:0] alloc_phys;
    reg [(BE_WIDTH*32)-1:0] alloc_store;
    wire alloc_ready;
    wire [BE_WIDTH-1:0] alloc_fire;
    wire [ACW-1:0] alloc_count;
    reg [BE_WIDTH-1:0] wake_valid;
    reg [(BE_WIDTH*TAGW)-1:0] wake_tag;
    reg [(BE_WIDTH*32)-1:0] wake_value;
    reg [BE_WIDTH-1:0] issue_ready;
    wire [BE_WIDTH-1:0] issue_valid;
    wire [(BE_WIDTH*OPW)-1:0] issue_op;
    wire [(BE_WIDTH*32)-1:0] issue_pc, issue_imm, issue_pred_target, issue_src1, issue_src2;
    wire [BE_WIDTH-1:0] issue_pred_taken, issue_mem_unsigned;
    wire [(BE_WIDTH*2)-1:0] issue_pred_kind, issue_mem_size;
    wire [(BE_WIDTH*TAGW)-1:0] issue_tag;
    wire [(BE_WIDTH*PAW)-1:0] issue_phys;
    wire [(BE_WIDTH*32)-1:0] issue_store;
    wire [(BE_WIDTH*SW)-1:0] issue_slot;
    reg flush_valid;
    reg [ENTRIES-1:0] flush_mask;
    wire [CW-1:0] occupancy;
    integer bad;
    reg [TAGW-1:0] tag0, tag1, stale_tag;

    rv32_reservation_station #(.BE_WIDTH(BE_WIDTH), .ENTRIES(ENTRIES)) dut (
        .clk_i(clk), .reset_i(reset), .alloc_valid_i(alloc_valid), .alloc_op_i(alloc_op), .alloc_pc_i(alloc_pc), .alloc_imm_i(alloc_imm), .alloc_pred_taken_i(alloc_pred_taken), .alloc_pred_target_i(alloc_pred_target), .alloc_pred_kind_i(alloc_pred_kind), .alloc_mem_size_i(alloc_mem_size), .alloc_mem_unsigned_i(alloc_mem_unsigned), .alloc_rob_tag_i(alloc_tag), .alloc_target_live_i(target_live), .alloc_phys_rd_i(alloc_phys), .alloc_src1_value_i(src1_value), .alloc_src1_tag_i(src1_tag), .alloc_src1_ready_i(src1_ready), .alloc_src2_value_i(src2_value), .alloc_src2_tag_i(src2_tag), .alloc_src2_ready_i(src2_ready), .alloc_store_data_i(alloc_store), .alloc_ready_o(alloc_ready), .alloc_fire_o(alloc_fire), .alloc_count_o(alloc_count), .wake_valid_i(wake_valid), .wake_tag_i(wake_tag), .wake_value_i(wake_value), .issue_ready_i(issue_ready), .issue_valid_o(issue_valid), .issue_op_o(issue_op), .issue_pc_o(issue_pc), .issue_imm_o(issue_imm), .issue_pred_taken_o(issue_pred_taken), .issue_pred_target_o(issue_pred_target), .issue_pred_kind_o(issue_pred_kind), .issue_mem_size_o(issue_mem_size), .issue_mem_unsigned_o(issue_mem_unsigned), .issue_rob_tag_o(issue_tag), .issue_phys_rd_o(issue_phys), .issue_src1_value_o(issue_src1), .issue_src2_value_o(issue_src2), .issue_store_data_o(issue_store), .issue_slot_o(issue_slot), .flush_valid_i(flush_valid), .flush_kill_mask_i(flush_mask), .occupancy_o(occupancy)
    );
    initial begin clk = 0; forever #5 clk = ~clk; end

    task clear_inputs;
        begin
            alloc_valid = 0; target_live = 0; src1_ready = 0; src2_ready = 0; alloc_op = 0; alloc_pc = 0; alloc_imm = 0; alloc_pred_taken = 0; alloc_pred_target = 0; alloc_pred_kind = 0; alloc_mem_size = 0; alloc_mem_unsigned = 0; alloc_tag = 0; alloc_phys = 0; src1_value = 0; src1_tag = 0; src2_value = 0; src2_tag = 0; alloc_store = 0; wake_valid = 0; wake_tag = 0; wake_value = 0; issue_ready = {BE_WIDTH{1'b1}}; flush_valid = 0; flush_mask = 0;
        end
    endtask
    task alloc_entry;
        input integer lane; input [TAGW-1:0] tag; input integer pc; input integer ready1; input integer ready2;
        begin
            alloc_valid[lane] = 1; target_live[lane] = 1; alloc_tag[(lane*TAGW) +: TAGW] = tag; alloc_pc[(lane*32) +: 32] = pc; alloc_op[(lane*OPW) +: OPW] = pc; src1_ready[lane] = ready1; src2_ready[lane] = ready2; src1_value[(lane*32) +: 32] = pc + 1; src2_value[(lane*32) +: 32] = pc + 2;
        end
    endtask
    initial begin
        reset = 1; bad = 0; clear_inputs(); #12; reset = 0; #1;
        // Allocate a blocked RAW entry and an older ready entry.
        clear_inputs(); alloc_entry(0, 16'h0101, 10, 0, 1); if (BE_WIDTH > 1) alloc_entry(1, 16'h0103, 8, 1, 1); #1;
        if (!alloc_ready || alloc_count != ((BE_WIDTH > 1) ? 2 : 1)) bad = bad + 1;
        tag0 = alloc_tag[0 +: TAGW]; if (BE_WIDTH > 1) tag1 = alloc_tag[TAGW +: TAGW]; @(posedge clk); #1; clear_inputs();
        if (BE_WIDTH > 1) begin
            if (!issue_valid[0] || issue_pc[31:0] != 8 || occupancy != 2) bad = bad + 1;
            issue_ready = 0; #1; if (!issue_valid[0] || occupancy != 2) bad = bad + 1;
            issue_ready = {BE_WIDTH{1'b1}}; @(posedge clk); #1; clear_inputs();
        end
        // Wake the blocked source; wakeup is visible from the following cycle.
        wake_valid[0] = 1; wake_tag[0 +: TAGW] = 16'h0201; wake_value[31:0] = 55; #1; @(posedge clk); #1; clear_inputs();
        if (BE_WIDTH == 1) begin
            // The single entry was blocked; its wakeup is covered below.
            if (issue_valid != 0) begin $display("ERROR: single early issue=%b occ=%0d", issue_valid, occupancy); bad = bad + 1; end
        end
        // Generation-qualified wakeup: an unrelated/stale tag must not wake.
        clear_inputs(); alloc_entry(0, 16'h0301, 20, 0, 1); src1_tag[0 +: TAGW] = 16'h0401; @(posedge clk); #1; clear_inputs(); wake_valid[0] = 1; wake_tag[0 +: TAGW] = 16'h0501; wake_value[31:0] = 66; @(posedge clk); #1; clear_inputs(); if (issue_valid != 0) begin $display("ERROR: stale issue=%b occ=%0d", issue_valid, occupancy); bad = bad + 1; end
        // Exact matching wakeup issues the entry, then flush removes a younger entry.
        wake_valid[0] = 1; wake_tag[0 +: TAGW] = 16'h0401; wake_value[31:0] = 77; @(posedge clk); #1; clear_inputs(); if (!issue_valid[0]) begin $display("ERROR: exact issue=%b occ=%0d", issue_valid, occupancy); bad = bad + 1; end @(posedge clk); #1;
        reset = 1; clear_inputs(); @(posedge clk); #1; reset = 0;
        clear_inputs(); alloc_entry(0, 16'h0601, 30, 1, 1); @(posedge clk); #1; clear_inputs(); flush_valid = 1; flush_mask = {ENTRIES{1'b1}}; @(posedge clk); #1; clear_inputs(); if (occupancy != 0) bad = bad + 1;

        // A selective recovery keeps an older blocked entry and must not lose
        // a matching wakeup that arrives on the recovery edge.
        clear_inputs(); alloc_entry(0, 16'h0701, 40, 0, 1); src1_tag[0 +: TAGW] = 16'h0801;
        @(posedge clk); #1; clear_inputs();
        flush_valid = 1; flush_mask = {ENTRIES{1'b0}};
        wake_valid[0] = 1; wake_tag[0 +: TAGW] = 16'h0801; wake_value[31:0] = 99;
        @(posedge clk); #1; clear_inputs();
        if (occupancy != 1 || !issue_valid[0] || issue_src1[31:0] != 99) bad = bad + 1;
        @(posedge clk); #1; clear_inputs();

        // A finite-width tag can alias after enough ROB reuse.  Once an
        // operand is ready, an aliasing broadcast must not overwrite it.
        clear_inputs(); alloc_entry(0, 16'h0901, 50, 1, 1);
        src1_tag[0 +: TAGW] = 16'h0a01; issue_ready = 0;
        @(posedge clk); #1; clear_inputs(); issue_ready = 0;
        wake_valid[0] = 1; wake_tag[0 +: TAGW] = 16'h0a01;
        wake_value[31:0] = 32'hdeadbeef;
        @(posedge clk); #1; clear_inputs();
        if (!issue_valid[0] || issue_src1[31:0] != 51) bad = bad + 1;
        @(posedge clk); #1; clear_inputs();

        if (bad != 0) begin $display("FAIL: B-04 RS BE_WIDTH=%0d ENTRIES=%0d checks=%0d", BE_WIDTH, ENTRIES, bad); $finish(1); end
        $display("PASS: B-04 RS BE_WIDTH=%0d ENTRIES=%0d", BE_WIDTH, ENTRIES); $finish(0);
    end
endmodule
