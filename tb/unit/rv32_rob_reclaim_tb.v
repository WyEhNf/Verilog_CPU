`timescale 1ns/1ps
module rv32_rob_reclaim_tb #(
    parameter integer BE_WIDTH = 2,
    parameter integer ENTRIES = 16,
    parameter integer PHYS_REGS = 48
);
    localparam integer SW = $clog2(ENTRIES);
    localparam integer PW = $clog2(PHYS_REGS);
    localparam integer TW = SW+11;
    reg [BE_WIDTH-1:0] recovery_valid;
    reg [BE_WIDTH*TW-1:0] recovery_tag;
    wire recovery_accept;
    wire [PHYS_REGS-1:0] bitmap;
    wire [$clog2(PHYS_REGS+1)-1:0] count;
    reg [PHYS_REGS-1:0] expected_bitmap;
    integer seed, trial, slot, lane, selected_slot, selected_age, lane_slot, lane_age;
    integer entry_age, expected_count;
    reg [TW-1:0] lane_tag;

    rv32_rob #(.BE_WIDTH(BE_WIDTH), .ROB_ENTRIES(ENTRIES),
        .PHYS_REGS(PHYS_REGS), .PHYS_ADDR_WIDTH(PW), .CHECKPOINT_WIDTH(32)) dut (
        .clk_i(1'b0), .reset_i(1'b0), .alloc_valid_i({BE_WIDTH{1'b0}}),
        .recovery_valid_i(recovery_valid), .recovery_tag_i(recovery_tag),
        .recovery_pc_i({BE_WIDTH*32{1'b0}}), .recovery_accept_o(recovery_accept),
        .recovery_reclaim_bitmap_o(bitmap), .recovery_reclaim_count_o(count)
    );
    initial begin
        seed = 32'h092345a7;
        dut.tail_reg = 0;
        for (trial = 0; trial < 3000; trial = trial + 1) begin
            dut.head_reg = ($random(seed) & 32'h7fffffff) % ENTRIES;
            dut.occupancy_reg = ($random(seed) & 32'h7fffffff) % (ENTRIES+1);
            for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                dut.valid_mem[slot] = $random(seed);
                dut.rd_we_mem[slot] = $random(seed);
                // Include zero, out-of-range and duplicate physical IDs.
                dut.new_phys_mem[slot] = (trial % 2) ? ($random(seed) & 7) : $random(seed);
                dut.generation_mem[slot] = 8'h32;
            end
            recovery_valid = $random(seed);
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                lane_slot = ($random(seed) & 32'h7fffffff) % ENTRIES;
                lane_tag = {8'h32, lane_slot[SW-1:0], 3'b001};
                if (trial % 7 == 0) lane_tag[TW-1:TW-8] = 8'h31;
                if (trial % 11 == 0) lane_tag[0] = 0;
                recovery_tag[lane*TW +: TW] = lane_tag;
            end
            if (trial == 0) begin
                // Exercise a large count, duplicate destinations and x0 in
                // one full queue, beyond typical sparse random states.
                dut.head_reg = 0;
                dut.occupancy_reg = ENTRIES;
                recovery_valid = 1;
                recovery_tag[0 +: TW] = {8'h32, {SW{1'b0}}, 3'b001};
                for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                    dut.valid_mem[slot] = 1;
                    dut.rd_we_mem[slot] = 1;
                    dut.new_phys_mem[slot] = slot % PHYS_REGS;
                end
            end
            #1;
            selected_slot = -1;
            selected_age = ENTRIES+1;
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                lane_tag = recovery_tag[lane*TW +: TW];
                lane_slot = lane_tag[3 +: SW];
                lane_age = (lane_slot + ENTRIES - dut.head_reg) % ENTRIES;
                if (recovery_valid[lane] && lane_tag[0] && dut.valid_mem[lane_slot] &&
                    lane_tag[TW-1:TW-8] == dut.generation_mem[lane_slot] &&
                    lane_age < dut.occupancy_reg && lane_age < selected_age) begin
                    selected_slot = lane_slot;
                    selected_age = lane_age;
                end
            end
            expected_bitmap = 0;
            expected_count = 0;
            if (selected_slot >= 0)
                for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                    entry_age = (slot + ENTRIES - dut.head_reg) % ENTRIES;
                    if (dut.valid_mem[slot] && dut.rd_we_mem[slot] &&
                        entry_age > selected_age && entry_age < dut.occupancy_reg &&
                        dut.new_phys_mem[slot] != 0 && dut.new_phys_mem[slot] < PHYS_REGS &&
                        !expected_bitmap[dut.new_phys_mem[slot]]) begin
                        expected_bitmap[dut.new_phys_mem[slot]] = 1;
                        expected_count = expected_count + 1;
                    end
                end
            if (recovery_accept !== (selected_slot >= 0) || bitmap !== expected_bitmap || count !== expected_count)
                $fatal(1, "reclaim mismatch trial=%0d expected bitmap=%h count=%0d actual bitmap=%h count=%0d",
                    trial, expected_bitmap, expected_count, bitmap, count);
        end
        $display("PASS: ROB reclaim BE_WIDTH=%0d ENTRIES=%0d PHYS=%0d trials=%0d", BE_WIDTH, ENTRIES, PHYS_REGS, trial);
        $finish;
    end
endmodule
