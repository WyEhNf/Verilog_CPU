`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Speculative register renaming with a physical-register free bitmap.
// All bundle buses are flattened in program/lane order.
module rv32_rename_unit #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS),
    parameter integer COUNT_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS + 1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         rename_ready_i,
    input  wire [BE_WIDTH-1:0]           decoded_valid_i,
    input  wire [BE_WIDTH-1:0]           decoded_rd_we_i,
    input  wire [BE_WIDTH-1:0]           decoded_rs1_used_i,
    input  wire [BE_WIDTH-1:0]           decoded_rs2_used_i,
    input  wire [BE_WIDTH-1:0]           decoded_rs_need_i,
    input  wire [BE_WIDTH-1:0]           decoded_lsq_need_i,
    input  wire [(BE_WIDTH*5)-1:0]       decoded_rd_i,
    input  wire [(BE_WIDTH*5)-1:0]       decoded_rs1_i,
    input  wire [(BE_WIDTH*5)-1:0]       decoded_rs2_i,
    input  wire [15:0]                   rob_free_count_i,
    input  wire [15:0]                   rs_free_count_i,
    input  wire [15:0]                   lsq_free_count_i,
    output reg  [BE_WIDTH-1:0]           rename_valid_o,
    output reg  [BE_WIDTH-1:0]           rename_rd_we_o,
    output reg  [(BE_WIDTH*5)-1:0]       rename_rd_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] rename_old_phys_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] rename_new_phys_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] rename_rs1_phys_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] rename_rs2_phys_o,
    output reg  [((BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1))-1:0] rename_count_o,
    output wire [(32*PHYS_ADDR_WIDTH)-1:0] rat_state_o,
    output wire [(32*PHYS_ADDR_WIDTH)-1:0] rrat_state_o,
    output wire [PHYS_REGS-1:0]           free_bitmap_state_o,
    output wire [COUNT_WIDTH-1:0]         free_count_o,
    input  wire                           commit_valid_i,
    input  wire [BE_WIDTH-1:0]            commit_rd_we_i,
    input  wire [(BE_WIDTH*5)-1:0]        commit_rd_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] commit_old_phys_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] commit_new_phys_i,
    input  wire                           restore_valid_i,
    input  wire [(32*PHYS_ADDR_WIDTH)-1:0] restore_rat_i,
    input  wire [PHYS_REGS-1:0]           restore_free_bitmap_i,
    input  wire [COUNT_WIDTH-1:0]         restore_free_count_i
);
    localparam integer RENAME_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1);
    localparam integer FREE_SLOTS = PHYS_REGS - 1;
    localparam integer FREE_GROUPS = (PHYS_REGS + 7) / 8;

    reg [PHYS_ADDR_WIDTH-1:0] rat [0:31];
    reg [PHYS_REGS-1:0] free_bitmap;
    reg [COUNT_WIDTH-1:0] free_count;

    reg [PHYS_ADDR_WIDTH-1:0] bundle_rat [0:31];
    reg [PHYS_REGS-1:0] candidate_free_bitmap;
    reg [PHYS_ADDR_WIDTH-1:0] free_candidate [0:BE_WIDTH-1];
    integer lane;
    integer reg_index;
    integer alloc_used;
    integer rob_used;
    integer rs_used;
    integer lsq_used;
    integer release_used;
    integer candidate_lane;
    integer reset_index;
    integer commit_lane;
    integer restore_index;
    integer selected_phys;
    reg prefix_open;
    reg [COUNT_WIDTH-1:0] alloc_count_comb;

    // Two-level priority encoding keeps the per-candidate search to eight
    // local bits followed by at most ceil(PHYS_REGS/8) group selections.
    function [PHYS_ADDR_WIDTH-1:0] lowest_free_phys;
        input [PHYS_REGS-1:0] bitmap;
        integer group_index;
        integer bit_index;
        reg [2:0] local_index;
        reg group_found;
        begin
            lowest_free_phys = {PHYS_ADDR_WIDTH{1'b0}};
            for (group_index = FREE_GROUPS - 1; group_index >= 0;
                 group_index = group_index - 1) begin
                local_index = 3'd0;
                group_found = 1'b0;
                for (bit_index = 7; bit_index >= 0;
                     bit_index = bit_index - 1) begin
                    if (((group_index * 8 + bit_index) < PHYS_REGS) &&
                        bitmap[group_index * 8 + bit_index]) begin
                        local_index = bit_index[2:0];
                        group_found = 1'b1;
                    end
                end
                if (group_found)
                    lowest_free_phys = group_index * 8 + local_index;
            end
        end
    endfunction

    initial begin
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid rename BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid rename PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if (PHYS_ADDR_WIDTH < $clog2(PHYS_REGS)) begin
            $display("ERROR: invalid rename PHYS_ADDR_WIDTH=%0d for PHYS_REGS=%0d", PHYS_ADDR_WIDTH, PHYS_REGS);
            $finish;
        end
    end

    assign free_bitmap_state_o = free_bitmap;
    assign free_count_o = free_count;

    genvar state_index;
    generate
        for (state_index = 0; state_index < 32; state_index = state_index + 1) begin : g_state
            assign rat_state_o[(state_index*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = rat[state_index];
            assign rrat_state_o[(state_index*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] =
                {PHYS_ADDR_WIDTH{1'b0}};
        end
    endgenerate

    // Preselect the first BE_WIDTH free physical registers from registered
    // state.  This priority search no longer depends on the decoded bundle;
    // the instruction-dependent path only chooses candidate[alloc_used].
    always @* begin
        candidate_free_bitmap = free_bitmap;
        for (candidate_lane = 0; candidate_lane < BE_WIDTH;
             candidate_lane = candidate_lane + 1) begin
            selected_phys = lowest_free_phys(candidate_free_bitmap);
            free_candidate[candidate_lane] =
                selected_phys[PHYS_ADDR_WIDTH-1:0];
            candidate_free_bitmap[selected_phys] = 1'b0;
        end
    end

    // Work on a temporary RAT in program order.  Only a contiguous prefix can
    // be accepted, and later lanes see earlier lanes' newly allocated maps.
    always @* begin
        for (reg_index = 0; reg_index < 32; reg_index = reg_index + 1)
            bundle_rat[reg_index] = rat[reg_index];
        rename_valid_o = {BE_WIDTH{1'b0}};
        rename_rd_we_o = {BE_WIDTH{1'b0}};
        rename_rd_o = {(BE_WIDTH*5){1'b0}};
        rename_old_phys_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        rename_new_phys_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        rename_rs1_phys_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        rename_rs2_phys_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        rename_count_o = {RENAME_COUNT_WIDTH{1'b0}};
        alloc_used = 0;
        rob_used = 0;
        rs_used = 0;
        lsq_used = 0;
        prefix_open = 1'b1;
        alloc_count_comb = {COUNT_WIDTH{1'b0}};
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            if (prefix_open && decoded_valid_i[lane] && rename_ready_i &&
                ((rob_used + 1) <= rob_free_count_i) &&
                ((!decoded_rs_need_i[lane]) || ((rs_used + 1) <= rs_free_count_i)) &&
                ((!decoded_lsq_need_i[lane]) || ((lsq_used + 1) <= lsq_free_count_i)) &&
                ((!decoded_rd_we_i[lane]) || (decoded_rd_i[(lane*5) +: 5] == 0) || ((alloc_used + 1) <= free_count))) begin
                rename_valid_o[lane] = 1'b1;
                rename_rd_we_o[lane] = decoded_rd_we_i[lane] && (decoded_rd_i[(lane*5) +: 5] != 0);
                rename_rd_o[(lane*5) +: 5] = decoded_rd_i[(lane*5) +: 5];
                if (decoded_rs1_used_i[lane] && (decoded_rs1_i[(lane*5) +: 5] != 0))
                    rename_rs1_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = bundle_rat[decoded_rs1_i[(lane*5) +: 5]];
                if (decoded_rs2_used_i[lane] && (decoded_rs2_i[(lane*5) +: 5] != 0))
                    rename_rs2_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = bundle_rat[decoded_rs2_i[(lane*5) +: 5]];
                if (rename_rd_we_o[lane]) begin
                    rename_old_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = bundle_rat[decoded_rd_i[(lane*5) +: 5]];
                    rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] =
                        free_candidate[alloc_used];
                    bundle_rat[decoded_rd_i[(lane*5) +: 5]] =
                        free_candidate[alloc_used];
                    alloc_used = alloc_used + 1;
                end
                rob_used = rob_used + 1;
                if (decoded_rs_need_i[lane]) rs_used = rs_used + 1;
                if (decoded_lsq_need_i[lane]) lsq_used = lsq_used + 1;
                rename_count_o = rename_count_o + 1'b1;
            end else begin
                // Prefix rule: no later lane can pass a blocked/invalid lane.
                prefix_open = 1'b0;
            end
        end
        alloc_count_comb = alloc_used;
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            free_count <= FREE_SLOTS;
            free_bitmap <= {PHYS_REGS{1'b1}};
            free_bitmap[0] <= 1'b0;
            for (reset_index = 0; reset_index < 32; reset_index = reset_index + 1) begin
                rat[reset_index] <= 0;
            end
        end else if (restore_valid_i) begin
            free_count <= restore_free_count_i;
            free_bitmap <= restore_free_bitmap_i;
            free_bitmap[0] <= 1'b0;
            for (restore_index = 0; restore_index < 32; restore_index = restore_index + 1)
                rat[restore_index] <= restore_rat_i[(restore_index*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
            rat[0] <= 0;
        end else begin
            // Rename allocation advances RAT and the free-list head.
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                if (rename_valid_o[lane] && rename_rd_we_o[lane]) begin
                    rat[rename_rd_o[(lane*5) +: 5]] <= rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    free_bitmap[rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b0;
                end

            release_used = 0;
            for (commit_lane = 0; commit_lane < BE_WIDTH; commit_lane = commit_lane + 1) begin
                if (commit_valid_i && commit_rd_we_i[commit_lane] &&
                    (commit_rd_i[(commit_lane*5) +: 5] != 0)) begin
                    if (commit_old_phys_i[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) begin
                        free_bitmap[commit_old_phys_i[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b1;
                        release_used = release_used + 1;
                    end
                end
            end
            free_count <= free_count - alloc_count_comb + release_used;
            free_bitmap[0] <= 1'b0;
            rat[0] <= 0;
        end
    end
endmodule
