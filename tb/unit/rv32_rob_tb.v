`timescale 1ns/1ps

module rv32_rob_tb #(
    parameter integer BE_WIDTH = 1,
    parameter integer ROB_ENTRIES = 8
);
    localparam integer PHYS_AW = 6;
    localparam integer SLOT_W = $clog2(ROB_ENTRIES);
    localparam integer GEN_W = 8;
    localparam integer TAG_W = 1 + 2 + SLOT_W + GEN_W;
    localparam integer CP_W = 32;
    localparam integer COUNT_W = $clog2(ROB_ENTRIES + 1);
    localparam integer ACW = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    reg clk, reset;
    reg [BE_WIDTH-1:0] alloc_valid, alloc_rd_we, alloc_store, alloc_branch, alloc_halt, alloc_error;
    reg [(BE_WIDTH*32)-1:0] alloc_pc, alloc_inst;
    reg [(BE_WIDTH*5)-1:0] alloc_rd;
    reg [(BE_WIDTH*PHYS_AW)-1:0] alloc_old, alloc_new;
    reg [(BE_WIDTH*CP_W)-1:0] alloc_cp;
    wire alloc_ready;
    wire [BE_WIDTH-1:0] alloc_fire;
    wire [(BE_WIDTH*TAG_W)-1:0] alloc_tag;
    wire [ACW-1:0] alloc_count;
    reg [BE_WIDTH-1:0] cpl_valid, cpl_done, cpl_error;
    reg [(BE_WIDTH*TAG_W)-1:0] cpl_tag;
    reg [(BE_WIDTH*32)-1:0] cpl_value, cpl_addr;
    reg [(BE_WIDTH*4)-1:0] cpl_mask;
    reg [(BE_WIDTH*32)-1:0] cpl_data;
    reg commit_ready;
    wire [BE_WIDTH-1:0] commit_valid, commit_rd_we, commit_store;
    wire [(BE_WIDTH*5)-1:0] commit_rd;
    wire [(BE_WIDTH*32)-1:0] commit_pc, commit_inst, commit_value, commit_addr;
    wire [(BE_WIDTH*16)-1:0] commit_mask;
    wire [(BE_WIDTH*128)-1:0] commit_data;
    wire [(BE_WIDTH*TAG_W)-1:0] commit_tag;
    wire store_valid;
    reg store_ready, store_ack_valid, store_ack_error;
    wire [TAG_W-1:0] store_tag;
    wire [31:0] store_addr;
    wire [15:0] store_mask;
    wire [127:0] store_data;
    reg [BE_WIDTH-1:0] recovery_valid;
    reg [(BE_WIDTH*TAG_W)-1:0] recovery_tag;
    reg [(BE_WIDTH*32)-1:0] recovery_pc;
    wire recovery_accept, redirect_valid, checkpoint_valid;
    wire [31:0] redirect_pc;
    wire [3:0] redirect_epoch;
    wire [CP_W-1:0] checkpoint;
    wire recovery_rd_we;
    wire [4:0] recovery_rd;
    wire [PHYS_AW-1:0] recovery_new_phys;
    wire [(1<<PHYS_AW)-1:0] recovery_reclaim_bitmap;
    wire [PHYS_AW:0] recovery_reclaim_count;
    wire [(BE_WIDTH*PHYS_AW)-1:0] commit_old_phys, commit_new_phys;
    reg [TAG_W-1:0] store_ack_tag;
    wire halted, error;
    wire [7:0] return_value;
    wire [SLOT_W-1:0] head, tail;
    wire [COUNT_W-1:0] occupancy;
    integer bad;
    integer j;
    reg [TAG_W-1:0] saved_tag0, saved_tag1, saved_store_tag, saved_branch_tag, stale_tag;
    reg [TAG_W-1:0] reused_tag, current_tag;

    rv32_rob #(.BE_WIDTH(BE_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .PHYS_REGS(1<<PHYS_AW), .PHYS_ADDR_WIDTH(PHYS_AW), .CHECKPOINT_WIDTH(CP_W)) dut (
        .clk_i(clk), .reset_i(reset), .alloc_valid_i(alloc_valid), .alloc_pc_i(alloc_pc), .alloc_inst_i(alloc_inst), .alloc_rd_i(alloc_rd), .alloc_rd_we_i(alloc_rd_we),
        .alloc_old_phys_i(alloc_old), .alloc_new_phys_i(alloc_new), .alloc_is_store_i(alloc_store), .alloc_is_branch_i(alloc_branch), .alloc_is_halt_i(alloc_halt), .alloc_is_error_i(alloc_error), .alloc_checkpoint_i(alloc_cp),
        .alloc_ready_o(alloc_ready), .alloc_fire_o(alloc_fire), .alloc_tag_o(alloc_tag), .alloc_count_o(alloc_count),
        .completion_valid_i(cpl_valid), .completion_tag_i(cpl_tag), .completion_value_i(cpl_value), .completion_done_i(cpl_done), .completion_error_i(cpl_error), .completion_store_addr_i(cpl_addr), .completion_store_mask_i(cpl_mask), .completion_store_data_i(cpl_data),
        .commit_ready_i(commit_ready), .commit_valid_o(commit_valid), .commit_rd_we_o(commit_rd_we), .commit_rd_o(commit_rd), .commit_pc_o(commit_pc), .commit_inst_o(commit_inst), .commit_value_o(commit_value), .commit_is_store_o(commit_store), .commit_store_addr_o(commit_addr), .commit_store_mask_o(commit_mask), .commit_store_data_o(commit_data), .commit_tag_o(commit_tag), .commit_old_phys_o(commit_old_phys), .commit_new_phys_o(commit_new_phys),
        .store_commit_valid_o(store_valid), .store_commit_ready_i(store_ready), .store_commit_tag_o(store_tag), .store_commit_addr_o(store_addr), .store_commit_mask_o(store_mask), .store_commit_data_o(store_data), .store_ack_valid_i(store_ack_valid), .store_ack_tag_i(store_ack_tag), .store_ack_error_i(store_ack_error),
        .recovery_valid_i(recovery_valid), .recovery_tag_i(recovery_tag), .recovery_pc_i(recovery_pc), .recovery_accept_o(recovery_accept), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc), .redirect_epoch_o(redirect_epoch), .checkpoint_restore_valid_o(checkpoint_valid), .checkpoint_restore_o(checkpoint), .recovery_rd_we_o(recovery_rd_we), .recovery_rd_o(recovery_rd), .recovery_new_phys_o(recovery_new_phys), .recovery_reclaim_bitmap_o(recovery_reclaim_bitmap), .recovery_reclaim_count_o(recovery_reclaim_count),
        .halted_o(halted), .error_o(error), .return_value_o(return_value), .head_o(head), .tail_o(tail), .occupancy_o(occupancy)
    );
    initial begin clk = 0; forever #5 clk = ~clk; end

    task clear_inputs;
        begin
            alloc_valid = 0; alloc_rd_we = 0; alloc_store = 0; alloc_branch = 0; alloc_halt = 0; alloc_error = 0;
            alloc_pc = 0; alloc_inst = 0; alloc_rd = 0; alloc_old = 0; alloc_new = 0; alloc_cp = 0;
            cpl_valid = 0; cpl_done = 0; cpl_error = 0; cpl_tag = 0; cpl_value = 0; cpl_addr = 0; cpl_mask = 0; cpl_data = 0;
            recovery_valid = 0; recovery_tag = 0; recovery_pc = 0; store_ack_valid = 0; store_ack_tag = 0; store_ack_error = 0;
        end
    endtask
    task alloc_one;
        input integer lane; input integer pc; input integer rd_num;
        begin
            alloc_valid[lane] = 1; alloc_pc[(lane*32) +: 32] = pc; alloc_inst[(lane*32) +: 32] = 32'h00000013; alloc_rd[(lane*5) +: 5] = rd_num; alloc_rd_we[lane] = (rd_num != 0); alloc_new[(lane*PHYS_AW) +: PHYS_AW] = rd_num + 1;
        end
    endtask
    task complete_one;
        input integer lane; input [TAG_W-1:0] tag; input integer value;
        begin cpl_valid[lane] = 1; cpl_done[lane] = 1; cpl_tag[(lane*TAG_W) +: TAG_W] = tag; cpl_value[(lane*32) +: 32] = value; end
    endtask
    initial begin
        reset = 1; commit_ready = 1; store_ready = 1; bad = 0; clear_inputs(); #12; reset = 0; #1;
        if (occupancy != 0 || head != 0 || tail != 0) bad = bad + 1;

        // Out-of-order completion still commits in program order.
        clear_inputs(); alloc_one(0, 0, 1); if (BE_WIDTH > 1) alloc_one(1, 4, 2); #1;
        if (!alloc_ready || alloc_count != ((BE_WIDTH > 1) ? 2 : 1)) bad = bad + 1;
        saved_tag0 = alloc_tag[0 +: TAG_W]; if (BE_WIDTH > 1) saved_tag1 = alloc_tag[TAG_W +: TAG_W];
        @(posedge clk); #1; clear_inputs();
        complete_one(0, (BE_WIDTH > 1) ? saved_tag1 : saved_tag0, 22); @(posedge clk); #1; clear_inputs();
        if ((BE_WIDTH > 1) && (commit_valid != 0)) bad = bad + 1;
        if (BE_WIDTH > 1) begin
            complete_one(0, saved_tag0, 11); @(posedge clk); #1; clear_inputs();
            if (!commit_valid[0] || commit_value[31:0] != 11 || !commit_valid[1] || commit_value[63:32] != 22) bad = bad + 1;
        end else if (!commit_valid[0] || commit_value[31:0] != 22) begin
            bad = bad + 1;
        end
        @(posedge clk); #1;

        // Store visibility is separate from retirement and waits for ack.
        clear_inputs(); alloc_store[0] = 1; alloc_one(0, 8, 0); alloc_store[0] = 1; #1; saved_store_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs();
        complete_one(0, saved_store_tag, 99); cpl_addr[31:0] = 32'h100; cpl_mask[3:0] = 4'hf; cpl_data[31:0] = 32'h1234; @(posedge clk); #1; clear_inputs();
        if (!store_valid || commit_valid != 0 || store_addr != 32'h100 ||
            store_mask != 16'h000f || store_data != 128'h00000000000000000000000000001234)
            bad = bad + 1;
        @(posedge clk); #1; clear_inputs(); store_ack_valid = 1; store_ack_tag = saved_store_tag; @(posedge clk); #1; clear_inputs();
        if (!commit_valid[0] || !commit_store[0]) bad = bad + 1;
        @(posedge clk); #1;

        // A non-head branch may complete on the same cycle that its recovery
        // removes younger entries.  The completion must still make the
        // retained branch ready while the older entry remains at the head.
        clear_inputs(); alloc_one(0, 16, 2); #1; saved_tag0 = alloc_tag[0 +: TAG_W]; @(posedge clk); #1;
        clear_inputs(); alloc_branch[0] = 1; alloc_cp[CP_W-1:0] = 32'hcafe; alloc_one(0, 20, 0); alloc_branch[0] = 1; #1; saved_branch_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1;
        clear_inputs(); alloc_one(0, 24, 3); #1; stale_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs();
        recovery_valid[0] = 1; recovery_tag[0 +: TAG_W] = saved_branch_tag; recovery_pc[31:0] = 32'h200;
        complete_one(0, saved_branch_tag, 33); #1;
        if (!recovery_accept || !redirect_valid || redirect_pc != 32'h200 || !checkpoint_valid || checkpoint != 32'hcafe ||
            recovery_rd_we || recovery_rd != 0 || recovery_new_phys != 1 ||
            recovery_reclaim_count != 1 || !recovery_reclaim_bitmap[4]) bad = bad + 1;
        @(posedge clk); #1; clear_inputs();
        if (occupancy != 2 || !dut.ready_mem[saved_branch_tag[3 +: SLOT_W]] ||
            dut.value_mem[saved_branch_tag[3 +: SLOT_W]] != 33) bad = bad + 1;
        // A stale younger tag cannot complete after recovery.
        complete_one(0, stale_tag, 77); @(posedge clk); #1; clear_inputs();

        // Completing the older entry releases both survivors in order.  Two
        // commit cycles cover the single-lane configuration as well.
        complete_one(0, saved_tag0, 11); @(posedge clk); #1; clear_inputs();
        repeat (2) begin @(posedge clk); #1; end
        if (occupancy != 0) bad = bad + 1;

        // Reuse one slot and reject a completion carrying its old generation.
        clear_inputs(); alloc_one(0, 26, 0); #1; stale_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs();
        complete_one(0, stale_tag, 1); @(posedge clk); #1; clear_inputs(); @(posedge clk); #1;
        for (j = 1; j < ROB_ENTRIES; j = j + 1) begin
            clear_inputs(); alloc_one(0, 40 + j, 0); #1; current_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs();
            complete_one(0, current_tag, j); @(posedge clk); #1; clear_inputs(); @(posedge clk); #1;
        end
        clear_inputs(); alloc_one(0, 80, 0); #1; reused_tag = alloc_tag[0 +: TAG_W];
        if (reused_tag == stale_tag) bad = bad + 1;
        complete_one(0, stale_tag, 8'hcc); @(posedge clk); #1; clear_inputs();
        if (commit_valid != 0) bad = bad + 1;
        @(posedge clk); #1;
        clear_inputs(); complete_one(0, reused_tag, 8'hdd); @(posedge clk); #1; clear_inputs(); @(posedge clk); #1;

        // HALT and error become visible only at precise head commit.
        clear_inputs(); alloc_halt[0] = 1; alloc_one(0, 28, 10); alloc_halt[0] = 1; #1; stale_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs(); complete_one(0, stale_tag, 8'h5a); @(posedge clk); #1; clear_inputs();
        if (!commit_valid[0]) bad = bad + 1; @(posedge clk); #1;
        if (!halted || return_value != 8'h5a) bad = bad + 1;
        clear_inputs(); alloc_error[0] = 1; alloc_one(0, 32, 0); alloc_error[0] = 1; #1; stale_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs(); complete_one(0, stale_tag, 0); cpl_error[0] = 1; @(posedge clk); #1; clear_inputs(); @(posedge clk); #1;
        if (!error) bad = bad + 1;

        // A failed store acknowledgement becomes a precise ROB error when
        // the acknowledged store retires.
        reset = 1; clear_inputs(); @(posedge clk); #1; reset = 0; #1;
        clear_inputs(); alloc_store[0] = 1; alloc_one(0, 36, 0); alloc_store[0] = 1; #1; saved_store_tag = alloc_tag[0 +: TAG_W]; @(posedge clk); #1; clear_inputs();
        complete_one(0, saved_store_tag, 0); cpl_addr[31:0] = 32'h104; cpl_mask[3:0] = 4'h3;
        cpl_data[31:0] = 32'h89abcdef; @(posedge clk); #1; clear_inputs();
        if (!store_valid || commit_valid != 0 || store_addr != 32'h104 ||
            store_mask != 16'h0030 ||
            store_data != 128'h000000000000000089abcdef00000000)
            bad = bad + 1;
        @(posedge clk); #1; clear_inputs(); store_ack_valid = 1; store_ack_tag = saved_store_tag; store_ack_error = 1; @(posedge clk); #1; clear_inputs();
        if (!commit_valid[0] || !commit_store[0]) bad = bad + 1;
        @(posedge clk); #1;
        if (!error) bad = bad + 1;

        if (bad != 0) begin $display("FAIL: B-03 ROB BE_WIDTH=%0d checks=%0d", BE_WIDTH, bad); $finish(1); end
        $display("PASS: B-03 ROB BE_WIDTH=%0d", BE_WIDTH); $finish(0);
    end
endmodule
