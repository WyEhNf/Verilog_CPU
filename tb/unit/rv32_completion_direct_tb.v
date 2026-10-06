`timescale 1ns/1ps

module rv32_completion_direct_tb #(
    parameter integer BE_WIDTH = 4,
    parameter integer CDB_WIDTH = BE_WIDTH,
    parameter integer SOURCES = 6
);
    reg clk = 0;
    always #5 clk = !clk;
    reg reset, flush, live_filter;
    reg [15:0] live_tag;
    reg [SOURCES-1:0] valid, live, rd_we, is_store, is_branch;
    reg [SOURCES-1:0] taken, redirect, is_memory, is_load;
    reg [SOURCES*16-1:0] tag;
    reg [SOURCES*6-1:0] phys;
    reg [SOURCES*32-1:0] value, addr, branch_target, store_data;
    reg [BE_WIDTH-1:0] ready;
    wire [SOURCES-1:0] accepted;
    wire [BE_WIDTH-1:0] out_valid, out_rd, out_store, out_branch;
    wire [BE_WIDTH-1:0] out_taken, out_redirect, out_memory, out_load;
    wire [BE_WIDTH*16-1:0] out_tag;
    wire [BE_WIDTH*6-1:0] out_phys;
    wire [BE_WIDTH*32-1:0] out_value, out_addr, out_target, out_data;
    wire [BE_WIDTH-1:0] prf_valid, rob_valid, wake_valid;
    wire [7:0] entry_valid;
    wire [127:0] entry_tag;
    wire [3:0] occupancy;
    reg [SOURCES-1:0] handshakes, seen;
    reg [BE_WIDTH-1:0] stalled;
    reg [156:0] stalled_packet [0:BE_WIDTH-1];
    integer stalled_source [0:BE_WIDTH-1];
    integer serial [0:SOURCES-1];
    integer last_grant [0:SOURCES-1];
    integer s, l, cycle, eligible_count, granted_count, out_source;
    integer seed = 32'h13ace007;
    reg [156:0] packet;
    reg [BE_WIDTH*157-1:0] ready_snapshot;

    rv32_completion_network #(
        .BE_WIDTH(BE_WIDTH), .CDB_WIDTH(CDB_WIDTH), .SOURCES(SOURCES),
        .FIFO_DEPTH(8), .TAG_WIDTH(16), .PHYS_ADDR_WIDTH(6), .BYPASS(2)
    ) dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush),
        .kill_valid_i(1'b0), .kill_mask_i(8'b0),
        .producer_valid_i(valid), .producer_ready_o(accepted),
        .producer_tag_i(tag), .producer_phys_rd_i(phys),
        .producer_value_i(value), .producer_addr_i(addr),
        .producer_branch_target_i(branch_target), .producer_store_data_i(store_data),
        .producer_rd_we_i(rd_we), .producer_is_store_i(is_store),
        .producer_is_branch_i(is_branch), .producer_branch_taken_i(taken),
        .producer_redirect_valid_i(redirect), .producer_is_memory_i(is_memory),
        .producer_is_load_i(is_load), .producer_target_live_i(live),
        .live_tag_valid_i(live_filter), .live_tag_i(live_tag),
        .cdb_valid_o(out_valid), .cdb_ready_i(ready), .cdb_tag_o(out_tag),
        .cdb_phys_rd_o(out_phys), .cdb_value_o(out_value), .cdb_addr_o(out_addr),
        .cdb_branch_target_o(out_target), .cdb_store_data_o(out_data),
        .cdb_rd_we_o(out_rd), .cdb_is_store_o(out_store),
        .cdb_is_branch_o(out_branch), .cdb_branch_taken_o(out_taken),
        .cdb_redirect_valid_o(out_redirect), .cdb_is_memory_o(out_memory),
        .cdb_is_load_o(out_load), .prf_write_valid_o(prf_valid),
        .rob_ready_valid_o(rob_valid), .wakeup_valid_o(wake_valid),
        .entry_valid_o(entry_valid), .entry_tag_o(entry_tag), .occupancy_o(occupancy)
    );

    function eligible;
        input integer index;
        begin eligible = valid[index] && live[index] && tag[index*16] &&
            (!live_filter || tag[index*16 +: 16] == live_tag); end
    endfunction

    function [156:0] output_packet;
        input integer index;
        begin output_packet = {out_tag[index*16 +: 16], out_phys[index*6 +: 6],
            out_value[index*32 +: 32], out_addr[index*32 +: 32],
            out_target[index*32 +: 32], out_data[index*32 +: 32],
            out_rd[index], out_store[index], out_branch[index], out_taken[index],
            out_redirect[index], out_memory[index], out_load[index]}; end
    endfunction

    function [156:0] source_packet;
        input integer index;
        begin source_packet = {tag[index*16 +: 16], phys[index*6 +: 6],
            value[index*32 +: 32], addr[index*32 +: 32],
            branch_target[index*32 +: 32], store_data[index*32 +: 32],
            rd_we[index] && !is_store[index], is_store[index], is_branch[index],
            taken[index], redirect[index], is_memory[index], is_load[index]}; end
    endfunction

    task put;
        input integer index;
        begin
            serial[index] = serial[index] + 1;
            valid[index] = 1; live[index] = 1;
            tag[index*16 +: 16] = ((serial[index]*32 + index + 1) << 1) | 1;
            phys[index*6 +: 6] = (index + serial[index]) % 64;
            value[index*32 +: 32] = 32'h98765432 ^ (serial[index]*317 + index);
            addr[index*32 +: 32] = 32'hfedcba98 ^ (serial[index]*131 + index);
            branch_target[index*32 +: 32] = 32'h13579bdf ^ (serial[index]*67 + index);
            store_data[index*32 +: 32] = 32'h2468ace0 ^ (serial[index]*43 + index);
            rd_we[index] = 1;
            is_store[index] = (serial[index] + index) % 4 == 0;
            is_branch[index] = (serial[index] + index) % 3 == 0;
            taken[index] = serial[index] % 2;
            redirect[index] = serial[index] % 5 == 0;
            is_memory[index] = !is_branch[index];
            is_load[index] = is_memory[index] && !is_store[index];
        end
    endtask

    task check_outputs;
        begin
            if (occupancy !== 0 || entry_valid !== 0 || entry_tag !== 0)
                $fatal(1, "Direct mode fabricated completion FIFO storage");
            if (prf_valid !== (out_valid & out_rd) || rob_valid !== out_valid ||
                wake_valid !== (out_valid & out_rd)) $fatal(1, "Completion sideband mismatch");
            seen = 0; eligible_count = 0; granted_count = 0;
            for (s = 0; s < SOURCES; s = s + 1)
                if (eligible(s)) eligible_count = eligible_count + 1;
            for (l = 0; l < BE_WIDTH; l = l + 1) begin
                if (out_valid[l] === 1'b1) begin
                    if (reset || flush || l >= CDB_WIDTH) $fatal(1, "Invalid active lane");
                    out_source = ((out_tag[l*16 +: 16] >> 1) & 31) - 1;
                    if (out_source < 0 || out_source >= SOURCES) $fatal(1, "Unknown CDB source");
                    if (!eligible(out_source) || seen[out_source]) $fatal(1, "Stale/duplicate grant");
                    if (output_packet(l) !== source_packet(out_source)) $fatal(1, "CDB payload corruption");
                    if (accepted[out_source] !== ready[l]) $fatal(1, "Grant handshake mismatch");
                    seen[out_source] = 1;
                    granted_count = granted_count + 1;
                end else if (out_valid[l] !== 1'b0 || output_packet(l) !== 0)
                    $fatal(1, "Invalid lane has unknown/nonzero payload");
                if (!reset && !flush && stalled[l] &&
                    eligible(stalled_source[l]) &&
                    tag[stalled_source[l]*16 +: 16] == stalled_packet[l][156:141]) begin
                    if (!out_valid[l] || output_packet(l) !== stalled_packet[l])
                        $fatal(1, "Stalled lane changed source/payload");
                end
            end
            if (!reset && !flush && granted_count !=
                ((eligible_count < CDB_WIDTH) ? eligible_count : CDB_WIDTH))
                $fatal(1, "Available CDB bandwidth not used");
            for (s = 0; s < SOURCES; s = s + 1) begin
                if (reset || flush) begin
                    if (accepted[s] !== 0) $fatal(1, "Accepted result during reset/flush");
                end else if (valid[s] && !eligible(s)) begin
                    if (accepted[s] !== 1) $fatal(1, "Stale result did not drain under backpressure");
                end else if (!seen[s] && accepted[s] !== 0)
                    $fatal(1, "Unselected source accepted");
            end
        end
    endtask

    task step;
        begin
            #1;
            check_outputs;
            for (l = 0; l < BE_WIDTH; l = l + 1) begin
                stalled[l] = out_valid[l] && !ready[l] && !reset && !flush;
                stalled_packet[l] = output_packet(l);
                stalled_source[l] = ((out_tag[l*16 +: 16] >> 1) & 31) - 1;
            end
            handshakes = valid & accepted;
            @(posedge clk);
            #1;
            valid = valid & ~handshakes;
            @(negedge clk);
        end
    endtask

    task clear;
        begin
            reset = 1; flush = 0; live_filter = 0; live_tag = 0;
            valid = 0; live = 0; ready = 0;
            rd_we = 0; is_store = 0; is_branch = 0; taken = 0;
            redirect = 0; is_memory = 0; is_load = 0;
            tag = 0; phys = 0; value = 0; addr = 0; branch_target = 0; store_data = 0;
            stalled = 0;
            step;
            reset = 0;
        end
    endtask

    initial begin
        for (s = 0; s < SOURCES; s = s + 1) begin serial[s] = 0; last_grant[s] = 0; end
        clear;
        // Late sources must not displace a result whose lane is stalled.
        put(SOURCES-1); step;
        for (s = 0; s < SOURCES-1; s = s + 1) put(s);
        step;
        ready = 1; step;
        for (s = 0; s < SOURCES; s = s + 1) if (!valid[s]) put(s);
        step;
        // A source held on a HIGH lane must be reserved before a free low
        // lane gets a fresh grant; this catches duplicate-source stealing.
        ready = 0; step;
        ready[0] = 1; step;
        for (s = 0; s < SOURCES; s = s + 1) if (!valid[s]) put(s);
        step;
        // Cancellation and full-tag reuse release old locks.
        ready = 0;
        for (s = 0; s < SOURCES; s = s + 1) if (valid[s]) live[s] = 0;
        step;
        for (s = 0; s < SOURCES; s = s + 1) put(s);
        step;
        put(SOURCES-1); step;
        live_filter = 1; live_tag = tag[(SOURCES-1)*16 +: 16]; step;
        flush = 1; step;
        valid = 0; flush = 0; live_filter = 0; step;

        // Sustained all-source contention: demonstrate full width and fair
        // service, including MDU/LSQ-position sources beyond the ALU lanes.
        clear;
        ready = {BE_WIDTH{1'b1}};
        for (cycle = 0; cycle < SOURCES*8+8; cycle = cycle + 1) begin
            for (s = 0; s < SOURCES; s = s + 1) if (!valid[s]) put(s);
            step;
            for (s = 0; s < SOURCES; s = s + 1) begin
                if (handshakes[s]) last_grant[s] = cycle;
                if (cycle > SOURCES+2 && cycle-last_grant[s] > SOURCES+2)
                    $fatal(1, "Round-robin starvation source=%0d", s);
            end
        end

        clear;
        for (cycle = 0; cycle < 1200; cycle = cycle + 1) begin
            ready = $random(seed);
            flush = cycle % 97 == 0;
            reset = cycle % 251 == 0;
            live_filter = cycle % 53 == 0;
            live_tag = tag[(SOURCES-1)*16 +: 16];
            for (s = 0; s < SOURCES; s = s + 1) begin
                if (!valid[s] && ($random(seed) & 7) != 0) put(s);
                if (valid[s] && ($random(seed) & 31) == 0) live[s] = 0;
                if (valid[s] && ($random(seed) & 127) == 0) put(s);
            end
            #1;
            for (l = 0; l < BE_WIDTH; l = l + 1)
                ready_snapshot[l*157 +: 157] = output_packet(l);
            ready = ~ready;
            #1;
            for (l = 0; l < BE_WIDTH; l = l + 1)
                if (ready_snapshot[l*157 +: 157] !== output_packet(l))
                    $fatal(1, "Selection depends on downstream ready");
            step;
            if (reset || flush) begin valid = 0; stalled = 0; end
        end
        reset = 0; flush = 0; live_filter = 0; ready = {BE_WIDTH{1'b1}};
        for (cycle = 0; cycle < SOURCES+2; cycle = cycle + 1) step;
        if (valid !== 0) $fatal(1, "Final drain incomplete");
        $display("PASS: direct CDB BE=%0d CDB=%0d SOURCES=%0d", BE_WIDTH, CDB_WIDTH, SOURCES);
        $finish;
    end

    initial begin #100000; $fatal(1, "Direct completion test timeout"); end
endmodule
