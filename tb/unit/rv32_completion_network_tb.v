`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_completion_network_tb #(
    parameter integer BE_WIDTH = 1
);
    localparam integer SOURCES = 5;
    reg clk, reset, flush, kill_valid, live_tag_valid;
    reg [7:0] kill_mask;
    reg [SOURCES-1:0] producer_valid, producer_target_live, producer_rd_we, producer_store, producer_branch, producer_taken, producer_redirect, producer_memory, producer_load;
    reg [SOURCES*16-1:0] producer_tag;
    reg [SOURCES*6-1:0] producer_phys;
    reg [SOURCES*32-1:0] producer_value, producer_addr, producer_branch_target;
    reg [SOURCES*32-1:0] producer_store_data;
    reg [15:0] live_tag;
    reg [BE_WIDTH-1:0] cdb_ready;
    wire [SOURCES-1:0] producer_ready;
    wire [BE_WIDTH-1:0] cdb_valid, cdb_rd_we, cdb_is_store, wakeup_valid;
    wire [BE_WIDTH*16-1:0] cdb_tag;
    wire [BE_WIDTH*6-1:0] cdb_phys;
    wire [BE_WIDTH*32-1:0] cdb_value, cdb_addr;
    wire [BE_WIDTH*32-1:0] cdb_store_data;
    wire [BE_WIDTH-1:0] rob_valid;
    wire [BE_WIDTH*16-1:0] rob_tag;
    wire [BE_WIDTH*32-1:0] rob_value;
    wire [BE_WIDTH-1:0] prf_valid;
    wire [BE_WIDTH*16-1:0] prf_tag;
    wire [BE_WIDTH*6-1:0] prf_phys;
    wire [BE_WIDTH*32-1:0] prf_value;
    wire [BE_WIDTH*16-1:0] wake_tag;
    wire [BE_WIDTH*32-1:0] wake_value;
    wire [BE_WIDTH*32-1:0] cdb_branch_target, cdb_store_data_dummy;
    wire [BE_WIDTH-1:0] cdb_branch_taken, cdb_redirect, cdb_is_branch, cdb_memory, cdb_load;
    wire [7:0] entry_valid;
    wire [8*16-1:0] entry_tag;
    integer bad;
    integer test_slot;
    rv32_completion_network #(.BE_WIDTH(BE_WIDTH), .SOURCES(SOURCES), .FIFO_DEPTH(8)) dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .kill_valid_i(kill_valid), .kill_mask_i(kill_mask), .producer_valid_i(producer_valid), .producer_ready_o(producer_ready),
        .producer_tag_i(producer_tag), .producer_phys_rd_i(producer_phys), .producer_value_i(producer_value), .producer_addr_i(producer_addr), .producer_branch_target_i(producer_branch_target), .producer_store_data_i(producer_store_data),
        .producer_rd_we_i(producer_rd_we), .producer_is_store_i(producer_store), .producer_is_branch_i(producer_branch), .producer_branch_taken_i(producer_taken), .producer_redirect_valid_i(producer_redirect), .producer_is_memory_i(producer_memory), .producer_is_load_i(producer_load), .producer_target_live_i(producer_target_live), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag),
        .cdb_valid_o(cdb_valid), .cdb_ready_i(cdb_ready), .cdb_tag_o(cdb_tag), .cdb_phys_rd_o(cdb_phys), .cdb_value_o(cdb_value), .cdb_addr_o(cdb_addr), .cdb_branch_target_o(cdb_branch_target), .cdb_store_data_o(cdb_store_data), .cdb_rd_we_o(cdb_rd_we), .cdb_is_store_o(cdb_is_store), .cdb_is_branch_o(cdb_is_branch), .cdb_branch_taken_o(cdb_branch_taken), .cdb_redirect_valid_o(cdb_redirect), .cdb_is_memory_o(cdb_memory), .cdb_is_load_o(cdb_load),
        .prf_write_valid_o(prf_valid), .prf_write_tag_o(prf_tag), .prf_write_phys_rd_o(prf_phys), .prf_write_value_o(prf_value), .rob_ready_valid_o(rob_valid), .rob_ready_tag_o(rob_tag), .rob_ready_value_o(rob_value), .wakeup_valid_o(wakeup_valid), .wakeup_tag_o(wake_tag), .wakeup_value_o(wake_value), .entry_valid_o(entry_valid), .entry_tag_o(entry_tag), .occupancy_o()
    );
    initial begin clk=0; forever #5 clk=~clk; end
    task clear_inputs;
        begin producer_valid=0; producer_target_live=0; producer_rd_we=0; producer_store=0; producer_branch=0; producer_taken=0; producer_redirect=0; producer_memory=0; producer_load=0; producer_tag=0; producer_phys=0; producer_value=0; producer_addr=0; producer_branch_target=0; producer_store_data=0; cdb_ready={BE_WIDTH{1'b1}}; flush=0; kill_valid=0; kill_mask=0; live_tag_valid=0; live_tag=0; end
    endtask
    initial begin
        bad=0; reset=1; clear_inputs(); #12; reset=0; #1;
        // Same-cycle ALU/MDU/load conflict: source priority is index order.
        producer_valid=5'b00111; producer_target_live=5'b00111; producer_rd_we=5'b00111; producer_tag[15:0]=16'h0101; producer_tag[31:16]=16'h0201; producer_tag[47:32]=16'h0301; producer_value[31:0]=11; producer_value[63:32]=22; producer_value[95:64]=33; @(posedge clk); #1; clear_inputs();
        if (!cdb_valid[0] || cdb_value[31:0] != 11 || producer_ready[0] != 1'b1) bad=bad+1;
        if (BE_WIDTH > 1) begin if (!cdb_valid[1] || cdb_value[63:32] != 22) bad=bad+1; end
        @(posedge clk); #1;
        if (!cdb_valid[0] || cdb_value[31:0] != ((BE_WIDTH > 1) ? 33 : 22)) bad=bad+1; @(posedge clk); #1;
        if (BE_WIDTH == 1 && (!cdb_valid[0] || cdb_value[31:0] != 33)) bad=bad+1; @(posedge clk); #1;
        // Backpressure retains the oldest result and blocks overwrite.
        producer_valid[0]=1; producer_target_live[0]=1; producer_rd_we[0]=1; producer_tag[15:0]=16'h0401; producer_value[31:0]=44; @(posedge clk); #1; clear_inputs(); cdb_ready=0; repeat (2) @(posedge clk); if (!cdb_valid[0] || cdb_value[31:0] != 44) bad=bad+1; cdb_ready={BE_WIDTH{1'b1}}; @(posedge clk); #1;
        // Stores reach ROB but never PRF/wakeup.
        producer_valid[1]=1; producer_target_live[1]=1; producer_store[1]=1; producer_rd_we[1]=1; producer_tag[31:16]=16'h0501; producer_value[63:32]=55; @(posedge clk); #1; clear_inputs(); if (!cdb_is_store[0] || cdb_rd_we[0] || prf_valid[0] || wakeup_valid[0] || !rob_valid[0]) bad=bad+1; @(posedge clk); #1;
        // Stale and flush filtering.
        producer_valid[0]=1; producer_target_live[0]=0; producer_tag[15:0]=16'h0601; producer_value[31:0]=66; @(posedge clk); #1; clear_inputs(); repeat (2) @(posedge clk); if (cdb_valid[0]) bad=bad+1;
        producer_valid[0]=1; producer_target_live[0]=1; producer_tag[15:0]=16'h0701; producer_value[31:0]=77; @(posedge clk); #1; flush=1; @(posedge clk); #1; flush=0; clear_inputs(); repeat (2) @(posedge clk); if (cdb_valid[0]) bad=bad+1;
        // Complete-tag filter hides an old buffered result.
        producer_valid[0]=1; producer_target_live[0]=1; producer_tag[15:0]=16'h0801; producer_value[31:0]=88; @(posedge clk); #1; clear_inputs(); live_tag_valid=1; live_tag=16'h0901; #1; if (cdb_valid[0]) bad=bad+1; @(posedge clk); #1;
        // Selective recovery keeps an older queued completion and drops a
        // younger one without clearing the FIFO wholesale.
        clear_inputs(); cdb_ready=0;
        producer_valid[0]=1; producer_target_live[0]=1; producer_rd_we[0]=1; producer_tag[15:0]=16'h1001; producer_value[31:0]=100; @(posedge clk); #1;
        clear_inputs(); cdb_ready=0;
        producer_valid[0]=1; producer_target_live[0]=1; producer_rd_we[0]=1; producer_tag[15:0]=16'h1101; producer_value[31:0]=110; @(posedge clk); #1;
        clear_inputs(); cdb_ready=0; kill_mask=0;
        for (test_slot=0; test_slot<8; test_slot=test_slot+1)
            if (entry_valid[test_slot] && entry_tag[(test_slot*16) +: 16] == 16'h1101)
                kill_mask[test_slot]=1'b1;
        kill_valid=1; @(posedge clk); #1; kill_valid=0;
        if (!cdb_valid[0] || cdb_value[31:0] != 100) bad=bad+1;
        cdb_ready={BE_WIDTH{1'b1}}; @(posedge clk); #1;
        repeat (2) @(posedge clk); #1;
        if (cdb_valid[0]) bad=bad+1;
        if (bad != 0) begin $display("FAIL: B-07 completion network BE_WIDTH=%0d checks=%0d", BE_WIDTH, bad); $finish(1); end
        $display("PASS: B-07 completion network BE_WIDTH=%0d", BE_WIDTH); $finish(0);
    end
endmodule
