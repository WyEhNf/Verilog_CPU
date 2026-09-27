`timescale 1ns/1ps

module rv32_rename_unit_tb #(
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 48
);
    localparam integer AW = $clog2(PHYS_REGS);
    localparam integer FREE = PHYS_REGS - 1;
    localparam integer CW = $clog2(PHYS_REGS + 1);
    localparam integer RW = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    reg clk, reset, rename_ready;
    reg [BE_WIDTH-1:0] valid, rd_we, rs1_used, rs2_used, rs_need, lsq_need;
    reg [(BE_WIDTH*5)-1:0] rd, rs1, rs2;
    reg [15:0] rob_free, rs_free, lsq_free;
    wire [BE_WIDTH-1:0] out_valid, out_rd_we;
    wire [(BE_WIDTH*5)-1:0] out_rd;
    wire [(BE_WIDTH*AW)-1:0] old_phys, new_phys, out_rs1, out_rs2;
    wire [RW-1:0] count;
    wire [(32*AW)-1:0] rat_state, rrat_state;
    wire [PHYS_REGS-1:0] free_bitmap;
    wire [CW-1:0] free_count;
    reg commit_valid;
    reg [BE_WIDTH-1:0] commit_rd_we;
    reg [(BE_WIDTH*5)-1:0] commit_rd;
    reg [(BE_WIDTH*AW)-1:0] commit_old, commit_new;
    reg restore_valid;
    reg [(32*AW)-1:0] restore_rat;
    reg [PHYS_REGS-1:0] restore_free_bitmap;
    reg [CW-1:0] restore_count;
    integer bad;
    integer lane;
    integer exhaust_cycles;
    reg [(32*AW)-1:0] saved_rat;
    reg [PHYS_REGS-1:0] saved_free_bitmap;
    reg [CW-1:0] saved_count;
    integer expected_phys;
    integer pattern;
    integer phys;
    integer pattern_free_count;
    integer expected_lane;
    reg [PHYS_REGS-1:0] pattern_free_bitmap;

    rv32_rename_unit #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS)) dut (
        .clk_i(clk), .reset_i(reset), .rename_ready_i(rename_ready),
        .decoded_valid_i(valid), .decoded_rd_we_i(rd_we), .decoded_rs1_used_i(rs1_used), .decoded_rs2_used_i(rs2_used),
        .decoded_rs_need_i(rs_need), .decoded_lsq_need_i(lsq_need), .decoded_rd_i(rd), .decoded_rs1_i(rs1), .decoded_rs2_i(rs2),
        .rob_free_count_i(rob_free), .rs_free_count_i(rs_free), .lsq_free_count_i(lsq_free),
        .rename_valid_o(out_valid), .rename_rd_we_o(out_rd_we), .rename_rd_o(out_rd), .rename_old_phys_o(old_phys),
        .rename_new_phys_o(new_phys), .rename_rs1_phys_o(out_rs1), .rename_rs2_phys_o(out_rs2), .rename_count_o(count),
        .rat_state_o(rat_state), .rrat_state_o(rrat_state), .free_bitmap_state_o(free_bitmap), .free_count_o(free_count),
        .commit_valid_i(commit_valid), .commit_rd_we_i(commit_rd_we), .commit_rd_i(commit_rd), .commit_old_phys_i(commit_old), .commit_new_phys_i(commit_new),
        .restore_valid_i(restore_valid), .restore_rat_i(restore_rat), .restore_free_bitmap_i(restore_free_bitmap), .restore_free_count_i(restore_count)
    );
    initial begin clk = 0; forever #5 clk = ~clk; end

    task clear_inputs;
        begin
            valid = 0; rd_we = 0; rs1_used = 0; rs2_used = 0; rs_need = 0; lsq_need = 0;
            rd = 0; rs1 = 0; rs2 = 0; rob_free = 16'hffff; rs_free = 16'hffff; lsq_free = 16'hffff;
            commit_valid = 0; commit_rd_we = 0; commit_rd = 0; commit_old = 0; commit_new = 0;
            restore_valid = 0; restore_rat = 0; restore_free_bitmap = 0; restore_count = 0;
        end
    endtask
    task set_decoded;
        input integer n; input integer r; input integer s1; input integer s2;
        begin
            valid[n] = 1; rd_we[n] = (r != 0); rd[(n*5) +: 5] = r; rs1_used[n] = (s1 != 0); rs1[(n*5) +: 5] = s1; rs2_used[n] = (s2 != 0); rs2[(n*5) +: 5] = s2; rs_need[n] = 1; end
    endtask
    function [AW-1:0] phys_lane;
        input [(BE_WIDTH*AW)-1:0] bus;
        input integer n;
        begin phys_lane = bus >> (n*AW); end
    endfunction
    initial begin
        reset = 1; rename_ready = 1; bad = 0; clear_inputs(); #12; reset = 0; #1;
        if (free_count != FREE || rat_state[AW-1:0] != 0 || rrat_state[AW-1:0] != 0) bad = bad + 1;

        // Bundle RAW/WAW: lane 1 sees lane 0's new mapping.
        clear_inputs(); set_decoded(0, 5, 0, 0); if (BE_WIDTH > 1) set_decoded(1, 6, 5, 0); #1;
        if (count != ((BE_WIDTH > 1) ? 2 : 1) || out_valid !== ((BE_WIDTH > 1) ? ((1 << 2) - 1) : 1) || phys_lane(new_phys, 0) != 1 || ((BE_WIDTH > 1) && (phys_lane(out_rs1, 1) != 1 || phys_lane(new_phys, 1) != 2))) bad = bad + 1;
        @(posedge clk); #1;

        // Same-bundle WAW makes lane 1 replace lane 0's new mapping.
        if (BE_WIDTH > 1) begin
            clear_inputs(); set_decoded(0, 7, 0, 0); set_decoded(1, 7, 0, 0); #1;
            if (phys_lane(old_phys, 1) != phys_lane(new_phys, 0)) bad = bad + 1;
            @(posedge clk); #1;
        end
        clear_inputs(); set_decoded(0, 5, 0, 0); #1;
        if (old_phys[AW-1:0] != 1 || new_phys[AW-1:0] != ((BE_WIDTH > 1) ? 5 : 2)) bad = bad + 1;
        @(posedge clk); #1;

        // Commit releases the replaced physical register.  This backend does
        // not consume the committed RAT debug output.
        clear_inputs(); commit_valid = 1; commit_rd_we[0] = 1; commit_rd[4:0] = 5; commit_old[AW-1:0] = 1; commit_new[AW-1:0] = 3; @(posedge clk); #1;
        if (free_count != FREE - ((BE_WIDTH > 1) ? 4 : 1)) bad = bad + 1;
        clear_inputs(); #1;

        // Resource shortage and invalid holes stop the prefix.
        valid = {BE_WIDTH{1'b1}}; rd_we = {BE_WIDTH{1'b1}}; rd[4:0] = 8; if (BE_WIDTH > 1) rd[9:5] = 9; rob_free = 0; #1;
        if (count != 0 || out_valid != 0) bad = bad + 1;
        rob_free = 16'hffff; valid[0] = 0; if (BE_WIDTH > 1) valid[1] = 1; #1;
        if (count != 0 || out_valid != 0) bad = bad + 1;

        // Restore the checkpoint snapshot and verify allocation restarts at its head.
        saved_rat = rat_state; saved_free_bitmap = free_bitmap; saved_count = free_count;
        expected_phys = 0;
        for (lane = PHYS_REGS - 1; lane > 0; lane = lane - 1)
            if (saved_free_bitmap[lane]) expected_phys = lane;
        clear_inputs(); set_decoded(0, 10, 0, 0); @(posedge clk); #1; clear_inputs();
        restore_rat = saved_rat; restore_free_bitmap = saved_free_bitmap; restore_count = saved_count;
        restore_valid = 1; @(posedge clk); #1; restore_valid = 0;
        set_decoded(0, 10, 0, 0); #1;
        if (new_phys[AW-1:0] != expected_phys[AW-1:0]) bad = bad + 1;

        // Exhaust the free list, then prove allocation resumes after release.
        clear_inputs(); exhaust_cycles = 0;
        while ((free_count != 0) && (exhaust_cycles < PHYS_REGS + 4)) begin
            set_decoded(0, 11, 0, 0); #1;
            if (count != 1) bad = bad + 1;
            @(posedge clk); #1;
            clear_inputs();
            exhaust_cycles = exhaust_cycles + 1;
        end
        if ((free_count != 0) || (exhaust_cycles >= PHYS_REGS + 4)) bad = bad + 1;
        set_decoded(0, 12, 0, 0); #1;
        if (count != 0 || out_valid != 0) bad = bad + 1;
        clear_inputs(); commit_valid = 1; commit_rd_we[0] = 1; commit_rd[4:0] = 12; commit_old[AW-1:0] = 1; commit_new[AW-1:0] = 2;
        @(posedge clk); #1; clear_inputs();
        if (free_count != 1) bad = bad + 1;
        set_decoded(0, 12, 0, 0); #1;
        if (count != 1 || phys_lane(new_phys, 0) != 1) bad = bad + 1;

        // Fragmented free lists must select the lowest available physical
        // registers in order, including when fewer lanes write than BE_WIDTH.
        for (pattern = 0; pattern < 20; pattern = pattern + 1) begin
            clear_inputs();
            pattern_free_bitmap = {PHYS_REGS{1'b0}};
            pattern_free_count = 0;
            for (phys = 1; phys < PHYS_REGS; phys = phys + 1)
                if (((phys * 17 + pattern * 13) % 7) < 3) begin
                    pattern_free_bitmap[phys] = 1'b1;
                    pattern_free_count = pattern_free_count + 1;
                end
            restore_rat = saved_rat;
            restore_free_bitmap = pattern_free_bitmap;
            restore_count = pattern_free_count;
            restore_valid = 1'b1;
            @(posedge clk); #1;
            clear_inputs();
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                set_decoded(lane, 13 + lane, 0, 0);
            #1;
            if (count != BE_WIDTH) bad = bad + 1;
            expected_lane = 0;
            for (phys = 1; phys < PHYS_REGS; phys = phys + 1)
                if (pattern_free_bitmap[phys] && expected_lane < BE_WIDTH) begin
                    if (phys_lane(new_phys, expected_lane) != phys)
                        bad = bad + 1;
                    expected_lane = expected_lane + 1;
                end
            clear_inputs();
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                set_decoded(lane, (lane % 2 == 0) ? 13 + lane : 0, 0, 0);
            #1;
            if (count != BE_WIDTH) bad = bad + 1;
            expected_lane = 0;
            for (phys = 1; phys < PHYS_REGS; phys = phys + 1)
                if (pattern_free_bitmap[phys] &&
                    (expected_lane * 2) < BE_WIDTH) begin
                    if (phys_lane(new_phys, expected_lane * 2) != phys)
                        bad = bad + 1;
                    expected_lane = expected_lane + 1;
                end
        end

        if (bad != 0) begin $display("FAIL: B-02 rename BE_WIDTH=%0d PHYS_REGS=%0d checks=%0d", BE_WIDTH, PHYS_REGS, bad); $finish(1); end
        $display("PASS: B-02 rename BE_WIDTH=%0d PHYS_REGS=%0d", BE_WIDTH, PHYS_REGS); $finish(0);
    end
endmodule
