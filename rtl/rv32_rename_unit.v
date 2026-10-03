`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Speculative register renaming with a physical-register free bitmap.
// All bundle buses are flattened in program/lane order.
module rv32_rename_unit #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer RAT_READ_BYPASS = 0,
    parameter integer REGISTERED_FREE_POOL = 0,
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
    output wire [((BE_WIDTH<=1)?1:$clog2(BE_WIDTH+1))-1:0] allocatable_count_o,
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

    wire [PHYS_ADDR_WIDTH-1:0] rat [0:31];
    wire [PHYS_REGS-1:0] free_bitmap;
    reg [COUNT_WIDTH-1:0] free_count;

    reg [PHYS_ADDR_WIDTH-1:0] bundle_rat [0:31];
    reg [PHYS_REGS-1:0] candidate_free_bitmap;
    reg [PHYS_ADDR_WIDTH-1:0] raw_candidate [0:BE_WIDTH-1];
    wire [PHYS_ADDR_WIDTH-1:0] free_candidate [0:BE_WIDTH-1];
    reg [PHYS_ADDR_WIDTH-1:0] pool_candidate [0:BE_WIDTH-1];
    reg [RENAME_COUNT_WIDTH-1:0] pool_count;
    wire [PHYS_REGS-1:0] pool_bitmap;
    reg [PHYS_REGS-1:0] pool_reserve_mask;
    reg [RENAME_COUNT_WIDTH-1:0] pool_next_count;
    reg [BE_WIDTH*PHYS_ADDR_WIDTH-1:0] pool_next_payload;
    reg [BE_WIDTH-1:0] pool_write;
    integer pool_retained,pool_refilled,pool_row,pool_source;
    wire [COUNT_WIDTH-1:0] available_for_rename=(REGISTERED_FREE_POOL!=0)?pool_count:free_count;
    assign allocatable_count_o=(available_for_rename>BE_WIDTH)?BE_WIDTH:available_for_rename;
    wire [BE_WIDTH*PHYS_ADDR_WIDTH-1:0] pool_ids,pool_ids_local;
    wire [BE_WIDTH-1:0] pool_valid,pool_valid_local;
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) pool_id_tree (
        .signal_i(pool_ids),.views_o(pool_ids_local));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(1)) pool_valid_tree (
        .signal_i(pool_valid),.views_o(pool_valid_local));
    genvar pool_index,pool_phys;
    generate for(pool_index=0;pool_index<BE_WIDTH;pool_index=pool_index+1) begin:g_pool_slot
        assign pool_ids[pool_index*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]=pool_candidate[pool_index];
        assign pool_valid[pool_index]=pool_index<pool_count;
        assign free_candidate[pool_index]=(REGISTERED_FREE_POOL!=0)?pool_candidate[pool_index]:raw_candidate[pool_index];
        wire local_write;
        rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
            .signal_i(REGISTERED_FREE_POOL!=0 && !reset_i && !restore_valid_i && pool_write[pool_index]),
            .views_o(local_write));
        always @(posedge clk_i) if(local_write)
            pool_candidate[pool_index]<=pool_next_payload[pool_index*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
    end
    for(pool_phys=0;pool_phys<PHYS_REGS;pool_phys=pool_phys+1) begin:g_pool_bitmap
        wire [BE_WIDTH-1:0] matches;
        for(pool_index=0;pool_index<BE_WIDTH;pool_index=pool_index+1) begin:g_match
            assign matches[pool_index]=pool_valid_local[pool_index] && pool_ids_local[pool_index*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==pool_phys;
        end
        assign pool_bitmap[pool_phys]=(pool_phys!=0) && (|matches);
    end endgenerate
    // The pool is not architectural allocation. Expose both unreserved and
    // reserved-but-unused registers as free so recovery never leaks them.
    always @* begin
        pool_retained=pool_count-alloc_count_comb;
        pool_refilled=0;
        pool_reserve_mask=0;pool_next_payload=0;pool_write=0;
        for(pool_row=0;pool_row<BE_WIDTH;pool_row=pool_row+1) begin
            if(pool_row<pool_retained) begin
                pool_source=pool_row+alloc_count_comb;
                pool_next_payload[pool_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]=pool_candidate[pool_source];
                pool_write[pool_row]=(alloc_count_comb!=0);
            end else begin
                pool_source=pool_row-pool_retained;
                if(pool_source>=0 && pool_source<BE_WIDTH && raw_candidate[pool_source]!=0) begin
                    pool_next_payload[pool_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]=raw_candidate[pool_source];
                    pool_reserve_mask[raw_candidate[pool_source]]=1'b1;
                    pool_write[pool_row]=1'b1;
                    pool_refilled=pool_refilled+1;
                end
            end
        end
        pool_next_count=pool_retained+pool_refilled;
    end
    always @(posedge clk_i) begin
        // Restore receives the complete logical free bitmap, including all
        // previous pool entries. Return them and refill from that new bitmap.
        if(reset_i || restore_valid_i || REGISTERED_FREE_POOL==0) pool_count<=0;
        else pool_count<=pool_next_count;
    end

    localparam integer FREE_WORDS=(PHYS_REGS+31)/32;
    wire [32+FREE_WORDS-1:0] rename_reset_views,rename_restore_views;
    wire [4*BE_WIDTH*5-1:0] map_address_views;
    wire [4*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] map_value_views;
    wire [4*BE_WIDTH-1:0] map_valid_views;
    rv32_frequency_control_tree #(.LEAVES(32+FREE_WORDS)) reset_tree (
        .signal_i(reset_i),.views_o(rename_reset_views));
    rv32_frequency_control_tree #(.LEAVES(32+FREE_WORDS)) restore_tree (
        .signal_i(restore_valid_i),.views_o(rename_restore_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*5),.LEAVES(4)) map_address_tree (
        .signal_i(rename_rd_o),.views_o(map_address_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) map_value_tree (
        .signal_i(rename_new_phys_o),.views_o(map_value_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) map_valid_tree (
        .signal_i(rename_valid_o & rename_rd_we_o),.views_o(map_valid_views));
    genvar map_row,map_lane,free_word;
    generate
        for(map_row=0;map_row<32;map_row=map_row+1) begin:g_map_row
            if(map_row==0) begin:g_zero
                assign rat[map_row]=0;
            end else begin:g_stored
                localparam integer DOMAIN=map_row/8;
                wire [BE_WIDTH-1:0] matches;
                for(map_lane=0;map_lane<BE_WIDTH;map_lane=map_lane+1) begin:g_match
                    assign matches[map_lane]=map_valid_views[DOMAIN*BE_WIDTH+map_lane] &&
                        map_address_views[(DOMAIN*BE_WIDTH+map_lane)*5 +: 5]==map_row;
                end
                rv32_rename_map_row #(.LANES(BE_WIDTH),.PAW(PHYS_ADDR_WIDTH)) owner (
                    .clk_i(clk_i),.reset_i(rename_reset_views[map_row]),
                    .restore_i(rename_restore_views[map_row]),
                    .restore_value_i(restore_rat_i[map_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]),
                    .match_i(matches),
                    .values_i(map_value_views[DOMAIN*BE_WIDTH*PHYS_ADDR_WIDTH +: BE_WIDTH*PHYS_ADDR_WIDTH]),
                    .value_o(rat[map_row]));
            end
        end
        for(free_word=0;free_word<FREE_WORDS;free_word=free_word+1) begin:g_free_word
            localparam integer LOW=free_word*32;
            localparam integer BITS=PHYS_REGS-LOW>=32 ? 32 : PHYS_REGS-LOW;
            reg [BITS-1:0] bits_q,bits_next;
            integer writer,phys_index;
            always @* begin
                bits_next=bits_q;
                phys_index=0;
                if(rename_reset_views[32+free_word]) bits_next={BITS{1'b1}};
                else if(rename_restore_views[32+free_word])
                    bits_next=restore_free_bitmap_i[LOW +: BITS];
                else begin
                    if(REGISTERED_FREE_POOL!=0)
                        bits_next=bits_q & ~pool_reserve_mask[LOW +: BITS];
                    for(writer=0;writer<BE_WIDTH;writer=writer+1) begin
                        phys_index=rename_new_phys_o[writer*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                        if(REGISTERED_FREE_POOL==0 && rename_valid_o[writer] && rename_rd_we_o[writer] &&
                           phys_index>=LOW && phys_index<LOW+BITS)
                            bits_next[phys_index-LOW]=0;
                    end
                    // Commit returns win over same-edge reservation/allocation,
                    // exactly as the original low-to-high NBA sequence.
                    for(writer=0;writer<BE_WIDTH;writer=writer+1) begin
                        phys_index=commit_old_phys_i[writer*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                        if(commit_valid_i && commit_rd_we_i[writer] && commit_rd_i[writer*5 +: 5]!=0 &&
                           phys_index!=0 && phys_index>=LOW && phys_index<LOW+BITS)
                            bits_next[phys_index-LOW]=1;
                    end
                end
                if(LOW==0) bits_next[0]=0;
            end
            always @(posedge clk_i) bits_q<=bits_next;
            assign free_bitmap[LOW +: BITS]=bits_q;
        end
    endgenerate

    integer lane;
    integer reg_index;
    integer bypass_lane;
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

    assign free_bitmap_state_o = (REGISTERED_FREE_POOL!=0)?(free_bitmap | pool_bitmap):free_bitmap;
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
            raw_candidate[candidate_lane] =
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
                ((!decoded_rd_we_i[lane]) || (decoded_rd_i[(lane*5) +: 5] == 0) || ((alloc_used + 1) <= available_for_rename))) begin
                rename_valid_o[lane] = 1'b1;
                rename_rd_we_o[lane] = decoded_rd_we_i[lane] && (decoded_rd_i[(lane*5) +: 5] != 0);
                rename_rd_o[(lane*5) +: 5] = decoded_rd_i[(lane*5) +: 5];
                if (decoded_rs1_used_i[lane] && (decoded_rs1_i[(lane*5) +: 5] != 0)) begin
                    if (RAT_READ_BYPASS != 0) begin
                        rename_rs1_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = rat[decoded_rs1_i[(lane*5) +: 5]];
                        // Forward the youngest accepted older writer directly,
                        // avoiding a full temporary RAT rewrite for every lane.
                        for (bypass_lane = 0; bypass_lane < BE_WIDTH; bypass_lane = bypass_lane + 1)
                            if (bypass_lane < lane && rename_valid_o[bypass_lane] && rename_rd_we_o[bypass_lane] &&
                                decoded_rd_i[bypass_lane*5 +: 5] == decoded_rs1_i[lane*5 +: 5])
                                rename_rs1_phys_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH] =
                                    rename_new_phys_o[bypass_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                    end else
                        rename_rs1_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = bundle_rat[decoded_rs1_i[(lane*5) +: 5]];
                end
                if (decoded_rs2_used_i[lane] && (decoded_rs2_i[(lane*5) +: 5] != 0)) begin
                    if (RAT_READ_BYPASS != 0) begin
                        rename_rs2_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = rat[decoded_rs2_i[(lane*5) +: 5]];
                        // Forward the youngest accepted older writer directly,
                        // avoiding a full temporary RAT rewrite for every lane.
                        for (bypass_lane = 0; bypass_lane < BE_WIDTH; bypass_lane = bypass_lane + 1)
                            if (bypass_lane < lane && rename_valid_o[bypass_lane] && rename_rd_we_o[bypass_lane] &&
                                decoded_rd_i[bypass_lane*5 +: 5] == decoded_rs2_i[lane*5 +: 5])
                                rename_rs2_phys_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH] =
                                    rename_new_phys_o[bypass_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                    end else
                        rename_rs2_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = bundle_rat[decoded_rs2_i[(lane*5) +: 5]];
                end
                if (rename_rd_we_o[lane]) begin
                    if (RAT_READ_BYPASS != 0) begin
                        rename_old_phys_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH] = rat[decoded_rd_i[lane*5 +: 5]];
                        for (bypass_lane = 0; bypass_lane < BE_WIDTH; bypass_lane = bypass_lane + 1)
                            if (bypass_lane < lane && rename_valid_o[bypass_lane] && rename_rd_we_o[bypass_lane] &&
                                decoded_rd_i[bypass_lane*5 +: 5] == decoded_rd_i[lane*5 +: 5])
                                rename_old_phys_o[lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH] =
                                    rename_new_phys_o[bypass_lane*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                    end else
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
        if (rename_reset_views[0]) begin
            free_count <= FREE_SLOTS;
        end else if (rename_restore_views[0]) begin
            free_count <= restore_free_count_i;
        end else begin
            // Rename allocation advances RAT and consumes reserved entries.
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1)
                if (rename_valid_o[lane] && rename_rd_we_o[lane]) begin
                end

            release_used = 0;
            for (commit_lane = 0; commit_lane < BE_WIDTH; commit_lane = commit_lane + 1) begin
                if (commit_valid_i && commit_rd_we_i[commit_lane] &&
                    (commit_rd_i[(commit_lane*5) +: 5] != 0)) begin
                    if (commit_old_phys_i[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) begin
                        release_used = release_used + 1;
                    end
                end
            end
            free_count <= free_count - alloc_count_comb + release_used;
        end
    end
endmodule


module rv32_rename_map_row #(parameter integer LANES=4,PAW=6) (
    input wire clk_i,reset_i,restore_i,
    input wire [PAW-1:0] restore_value_i,
    input wire [LANES-1:0] match_i,
    input wire [LANES*PAW-1:0] values_i,
    output reg [PAW-1:0] value_o
);
    reg [PAW-1:0] selected;
    integer lane;
    always @* begin
        selected=0;
        for(lane=0;lane<LANES;lane=lane+1)
            if(match_i[lane]) selected=values_i[lane*PAW +: PAW];
    end
    always @(posedge clk_i) begin
        if(reset_i) value_o<=0;
        else if(restore_i) value_o<=restore_value_i;
        else if(|match_i) value_o<=selected;
    end
endmodule
