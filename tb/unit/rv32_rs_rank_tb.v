`timescale 1ns/1ps
// Differential combinational test against the original serial oldest-ready
// selector. Arbitrary ages include ties and wrap values, not just FIFO order.
module rv32_rs_rank_tb #(
    parameter integer BE_WIDTH = 2,
    parameter integer ENTRIES = 4,
    parameter integer AGE_WIDTH = 8,
    parameter integer WAKE_WIDTH = BE_WIDTH
);
    localparam integer SW = (ENTRIES <= 1) ? 1 : $clog2(ENTRIES);
    reg [WAKE_WIDTH-1:0] wake_valid;
    reg [BE_WIDTH-1:0] issue_ready;
    reg [WAKE_WIDTH*16-1:0] wake_tag;
    reg [WAKE_WIDTH*32-1:0] wake_value;
    wire [BE_WIDTH-1:0] issue_valid;
    wire [BE_WIDTH*SW-1:0] issue_slot;
    wire [BE_WIDTH*32-1:0] issue_src1, issue_src2, issue_pc, issue_store;
    wire [BE_WIDTH*16-1:0] issue_tag;
    wire [BE_WIDTH*6-1:0] issue_op, issue_phys;
    reg r1 [0:ENTRIES-1], r2 [0:ENTRIES-1];
    reg [31:0] v1 [0:ENTRIES-1], v2 [0:ENTRIES-1];
    reg [ENTRIES-1:0] selected;
    integer trial, slot, lane, wake, best, seed;
    reg [31:0] best_age;

    rv32_reservation_station #(.BE_WIDTH(BE_WIDTH), .ENTRIES(ENTRIES), .AGE_WIDTH(AGE_WIDTH), .WAKE_WIDTH(WAKE_WIDTH), .WAKE_MUX_IMPL(1), .ALLOC_STATIC_WRITE(1)) dut (
        .clk_i(1'b0), .reset_i(1'b0), .alloc_valid_i({BE_WIDTH{1'b0}}),
        .flush_valid_i(1'b0), .flush_kill_mask_i({ENTRIES{1'b0}}),
        .wake_valid_i(wake_valid), .wake_tag_i(wake_tag), .wake_value_i(wake_value),
        .issue_ready_i(issue_ready), .issue_valid_o(issue_valid), .issue_slot_o(issue_slot),
        .issue_op_o(issue_op), .issue_pc_o(issue_pc), .issue_rob_tag_o(issue_tag),
        .issue_phys_rd_o(issue_phys), .issue_src1_value_o(issue_src1),
        .issue_src2_value_o(issue_src2), .issue_store_data_o(issue_store)
    );

    initial begin
        seed = 32'h3ba57219;
        dut.occupancy_reg = 0;
        for (trial = 0; trial < 3000; trial = trial + 1) begin
            wake_valid = $random(seed);
            issue_ready = $random(seed);
            for (wake = 0; wake < WAKE_WIDTH; wake = wake + 1) begin
                wake_tag[wake*16 +: 16] = wake*2+1;
                wake_value[wake*32 +: 32] = $random(seed);
            end
            for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                dut.valid_mem[slot] = $random(seed);
                dut.target_live_mem[slot] = $random(seed);
                dut.src1_ready_mem[slot] = $random(seed);
                dut.src2_ready_mem[slot] = $random(seed);
                dut.src1_tag_mem[slot] = $random(seed) & 7;
                dut.src2_tag_mem[slot] = $random(seed) & 7;
                dut.src1_value_mem[slot] = $random(seed);
                dut.src2_value_mem[slot] = $random(seed);
                dut.age_mem[slot] = (trial % 2) ? ($random(seed) & 7) : $random(seed);
                dut.op_mem[slot] = $random(seed);
                dut.pc_mem[slot] = $random(seed);
                dut.rob_tag_mem[slot] = $random(seed);
                dut.phys_rd_mem[slot] = $random(seed);
                dut.store_data_mem[slot] = $random(seed);
                r1[slot] = dut.src1_ready_mem[slot];
                r2[slot] = dut.src2_ready_mem[slot];
                v1[slot] = dut.src1_value_mem[slot];
                v2[slot] = dut.src2_value_mem[slot];
                for (wake = 0; wake < WAKE_WIDTH; wake = wake + 1) begin
                    if (!r1[slot] && wake_valid[wake] &&
                        dut.src1_tag_mem[slot] == wake_tag[wake*16 +: 16] && dut.src1_tag_mem[slot][0]) begin
                        r1[slot] = 1;
                        v1[slot] = wake_value[wake*32 +: 32];
                    end
                    if (!r2[slot] && wake_valid[wake] &&
                        dut.src2_tag_mem[slot] == wake_tag[wake*16 +: 16] && dut.src2_tag_mem[slot][0]) begin
                        r2[slot] = 1;
                        v2[slot] = wake_value[wake*32 +: 32];
                    end
                end
            end
            #1;
            selected = 0;
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                best = -1;
                best_age = 32'hffffffff;
                for (slot = 0; slot < ENTRIES; slot = slot + 1)
                    if (dut.valid_mem[slot] && dut.target_live_mem[slot] && r1[slot] && r2[slot] &&
                        !selected[slot] && (best < 0 || dut.age_mem[slot] < best_age)) begin
                        best = slot;
                        best_age = dut.age_mem[slot];
                    end
                if (issue_valid[lane] !== (best >= 0)) $fatal(1, "valid mismatch trial %0d lane %0d", trial, lane);
                if (best >= 0) begin
                    selected[best] = 1;
                    if (issue_slot[lane*SW +: SW] !== best[SW-1:0] ||
                        issue_src1[lane*32 +: 32] !== v1[best] || issue_src2[lane*32 +: 32] !== v2[best] ||
                        issue_op[lane*6 +: 6] !== dut.op_mem[best] || issue_pc[lane*32 +: 32] !== dut.pc_mem[best] ||
                        issue_tag[lane*16 +: 16] !== dut.rob_tag_mem[best] ||
                        issue_phys[lane*6 +: 6] !== dut.phys_rd_mem[best] ||
                        issue_store[lane*32 +: 32] !== dut.store_data_mem[best])
                        $fatal(1, "selection/payload mismatch trial %0d lane %0d expected slot %0d", trial, lane, best);
                end
            end
        end
        $display("PASS: RS rank differential BE_WIDTH=%0d ENTRIES=%0d trials=%0d", BE_WIDTH, ENTRIES, trial);
        $finish;
    end
endmodule
