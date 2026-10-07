`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Combinational recovery candidate, selected by the CPU's optional
// RAT_RECOVERY_IMPL. Both implementations preserve the branch mapping.
module rv32_rat_recovery #(
    parameter integer ROB_ENTRIES = 32,
    parameter integer PAW = 6,
    parameter integer IMPL = 1,
    // Caller guarantees rat_i is the current speculative map and old_phys_i
    // records every accepted rename in program order. Suffix undo already
    // keeps the branch's own destination under this contract.
    parameter integer SUFFIX_KEEPS_BRANCH_MAPPING = 0,
    parameter integer SLOT_WIDTH = $clog2(ROB_ENTRIES),
    parameter integer COUNT_WIDTH = $clog2(ROB_ENTRIES + 1)
) (
    input wire [32*PAW-1:0] rat_i,
    input wire [SLOT_WIDTH-1:0] head_i,
    input wire [SLOT_WIDTH-1:0] branch_slot_i,
    input wire [COUNT_WIDTH-1:0] occupancy_i,
    input wire [ROB_ENTRIES-1:0] valid_i,
    input wire [ROB_ENTRIES-1:0] rd_we_i,
    input wire [ROB_ENTRIES*5-1:0] rd_i,
    input wire [ROB_ENTRIES*PAW-1:0] old_phys_i,
    input wire branch_rd_we_i,
    input wire [4:0] branch_rd_i,
    input wire [PAW-1:0] branch_new_phys_i,
    output wire [32*PAW-1:0] restore_o
);
    wire [32*PAW-1:0] undo_result;
    genvar row, arch, bit_id, group;
    generate if (IMPL == 0) begin : g_undo_loop
        reg [32*PAW-1:0] result;
        integer age, slot, branch_age;
        always @* begin
            result = rat_i;
            branch_age = branch_slot_i - head_i;
            if (branch_age < 0) branch_age = branch_age + ROB_ENTRIES;
            for (age = ROB_ENTRIES - 1; age >= 0; age = age - 1) begin
                slot = head_i + age;
                if (slot >= ROB_ENTRIES) slot = slot - ROB_ENTRIES;
                if (age > branch_age && age < occupancy_i && valid_i[slot] &&
                    rd_we_i[slot] && rd_i[slot*5 +: 5] != 0)
                    result[rd_i[slot*5 +: 5]*PAW +: PAW] = old_phys_i[slot*PAW +: PAW];
            end
        end
        assign undo_result = result;
    end else if(IMPL==1) begin : g_parallel_oldest
        wire [COUNT_WIDTH-1:0] branch_age = (branch_slot_i >= head_i) ?
            branch_slot_i - head_i : ROB_ENTRIES + branch_slot_i - head_i;
        (* keep = 1 *) wire [ROB_ENTRIES-1:0] killed_writer;
        wire [ROB_ENTRIES-1:0] above_branch;
        for (row = 0; row < ROB_ENTRIES; row = row + 1) begin : g_age
            wire [COUNT_WIDTH-1:0] row_age = (row >= head_i) ?
                row - head_i : ROB_ENTRIES + row - head_i;
            assign killed_writer[row] = valid_i[row] && rd_we_i[row] &&
                (row_age > branch_age) && (row_age < occupancy_i);
            assign above_branch[row] = (row > branch_slot_i);
        end
        assign undo_result[0 +: PAW] = rat_i[0 +: PAW];
        for (arch = 1; arch < 32; arch = arch + 1) begin : g_arch
            wire [ROB_ENTRIES-1:0] writer_matches, upper_matches, choices, first;
            wire upper_found = |upper_matches;
            wire found = |writer_matches;
            for (row = 0; row < ROB_ENTRIES; row = row + 1) begin : g_match
                assign writer_matches[row] = killed_writer[row] && rd_i[row*5 +: 5] == arch;
                assign upper_matches[row] = writer_matches[row] && above_branch[row];
                assign choices[row] = upper_found ? upper_matches[row] : writer_matches[row];
                if (row == 0) begin : g_named_69_30
assign first[row] = choices[row];
end
                else begin : g_named_70_21
assign first[row] = choices[row] && !(|choices[row-1:0]);
end
            end
            // The oldest killed writer is the last link applied by a
            // youngest-to-oldest undo. No sequential chain of RAT writes.
`ifdef CPU2026_WORD_SIM
            reg [PAW-1:0] recovered_word;
            integer sim_row;
            always @* begin
                recovered_word=0;
                for(sim_row=0;sim_row<ROB_ENTRIES;sim_row=sim_row+1)
                    if(first[sim_row]) recovered_word=recovered_word | old_phys_i[sim_row*PAW +: PAW];
            end
            assign undo_result[arch*PAW +: PAW]=found?recovered_word:rat_i[arch*PAW +: PAW];
`else
            for (bit_id = 0; bit_id < PAW; bit_id = bit_id + 1) begin : g_value
                wire [ROB_ENTRIES-1:0] column;
                for (row = 0; row < ROB_ENTRIES; row = row + 1) begin : g_row
                    assign column[row] = first[row] && old_phys_i[row*PAW + bit_id];
                end
                assign undo_result[arch*PAW + bit_id] = found ? (|column) : rat_i[arch*PAW + bit_id];
            end
`endif
        end
    end else begin:g_local_oldest
        localparam integer GROUPS=(ROB_ENTRIES+7)/8;
        // Power-of-two ROB geometry makes narrow subtraction exactly the
        // wrapped age. No per-row compare/mux or unsized 32-bit wrap adder.
        wire [SLOT_WIDTH-1:0] branch_age=branch_slot_i-head_i;
        localparam integer ARCH_DOMAINS=(31+3)/4;
        wire [ROB_ENTRIES-1:0] raw_killed,raw_upper;
        wire [ARCH_DOMAINS*ROB_ENTRIES-1:0] killed,upper;
        for(row=0;row<ROB_ENTRIES;row=row+1) begin:g_age
            wire [SLOT_WIDTH-1:0] row_age=row-head_i;
            assign raw_killed[row]=valid_i[row] && rd_we_i[row] &&
                row_age>branch_age && row_age<occupancy_i;
            assign raw_upper[row]=(row>branch_slot_i);
        end
        // One leaf serves at most four architectural registers.
        // Keep the exact old killed/upper predicates; isolate their consumers.
        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(ARCH_DOMAINS)) killed_tree (
            .signal_i(raw_killed),.views_o(killed));
        rv32_frequency_control_tree #(.WIDTH(ROB_ENTRIES),.LEAVES(ARCH_DOMAINS)) upper_tree (
            .signal_i(raw_upper),.views_o(upper));
        assign undo_result[0 +: PAW]=rat_i[0 +: PAW];
        for(arch=1;arch<32;arch=arch+1) begin:g_arch
            wire [ROB_ENTRIES-1:0] row_match_mask,upper_matches,first_any,first_upper;
            wire [GROUPS-1:0] any_group,upper_group;
            wire found=|any_group;
            wire upper_found=|upper_group;
            wire [PAW-1:0] any_value,upper_value;
            for(group=0;group<GROUPS;group=group+1) begin:g_group
                localparam integer LAST=((group+1)*8>ROB_ENTRIES)?ROB_ENTRIES-1:(group+1)*8-1;
                assign any_group[group]=|row_match_mask[LAST:group*8];
                assign upper_group[group]=|upper_matches[LAST:group*8];
            end
            for(row=0;row<ROB_ENTRIES;row=row+1) begin:g_match
                localparam integer GROUP=row/8;
                localparam integer FIRST=GROUP*8;
                wire any_before_group,upper_before_group,any_before_row,upper_before_row;
                localparam integer ARCH_DOMAIN=(arch-1)/4;
                assign row_match_mask[row]=killed[ARCH_DOMAIN*ROB_ENTRIES+row] && rd_i[row*5 +: 5]==arch;
                assign upper_matches[row]=row_match_mask[row] && upper[ARCH_DOMAIN*ROB_ENTRIES+row];
                if(GROUP==0) begin:g_first_group
                    assign any_before_group=0;assign upper_before_group=0;
                end else begin:g_later_group
                    assign any_before_group=|any_group[GROUP-1:0];
                    assign upper_before_group=|upper_group[GROUP-1:0];
                end
                if(row==FIRST) begin:g_first_row
                    assign any_before_row=0;assign upper_before_row=0;
                end else begin:g_later_row
                    assign any_before_row=|row_match_mask[row-1:FIRST];
                    assign upper_before_row=|upper_matches[row-1:FIRST];
                end
                assign first_any[row]=row_match_mask[row] && !any_before_row && !any_before_group;
                assign first_upper[row]=upper_matches[row] && !upper_before_row && !upper_before_group;
            end
`ifdef CPU2026_WORD_SIM
            reg [PAW-1:0] sim_any_word,sim_upper_word;
            integer sim_row;
            always @* begin
                sim_any_word=0;
                sim_upper_word=0;
                for(sim_row=0;sim_row<ROB_ENTRIES;sim_row=sim_row+1) begin
                    if(first_any[sim_row]) sim_any_word=sim_any_word | old_phys_i[sim_row*PAW +: PAW];
                    if(first_upper[sim_row]) sim_upper_word=sim_upper_word | old_phys_i[sim_row*PAW +: PAW];
                end
            end
            assign any_value=sim_any_word;
            assign upper_value=sim_upper_word;
`else
            for(bit_id=0;bit_id<PAW;bit_id=bit_id+1) begin:g_payload
                wire [ROB_ENTRIES-1:0] any_column,upper_column;
                for(row=0;row<ROB_ENTRIES;row=row+1) begin:g_row
                    assign any_column[row]=first_any[row] && old_phys_i[row*PAW+bit_id];
                    assign upper_column[row]=first_upper[row] && old_phys_i[row*PAW+bit_id];
                end
                assign any_value[bit_id]=|any_column;
                assign upper_value[bit_id]=|upper_column;
            end
`endif
            // Select between two completed values, rather than broadcasting
            // upper_found into 64 priority inputs per architectural register.
            assign undo_result[arch*PAW +: PAW]=found?
                (upper_found?upper_value:any_value):rat_i[arch*PAW +: PAW];
        end
    end endgenerate
    generate if(SUFFIX_KEEPS_BRANCH_MAPPING!=0) begin:g_suffix_keeps_branch
        // The oldest killed writer's old map is the retained prefix map.
        // With no killed writer, the current RAT already is that same map.
        assign restore_o=undo_result;
    end else begin:g_explicit_branch_mapping
        for (arch = 0; arch < 32; arch = arch + 1) begin : g_keep_branch
            assign restore_o[arch*PAW +: PAW] = (arch != 0 && branch_rd_we_i && branch_rd_i == arch) ?
                branch_new_phys_i : undo_result[arch*PAW +: PAW];
        end
    end endgenerate
    initial begin
        if (ROB_ENTRIES < 2 || (ROB_ENTRIES & (ROB_ENTRIES-1)) != 0 ||
            PAW < 1 || (IMPL < 0 || IMPL > 2)) begin
            $display("ERROR: invalid standalone RAT recovery geometry");
            $finish;
        end
    end
endmodule
