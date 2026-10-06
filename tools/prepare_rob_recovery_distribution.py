"""Prepare bounded ROB recovery queries/capture from CO; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def rob(source):
    source = change(source,
                    '    reg [SLOT_WIDTH-1:0] recovery_saved_slot, recovery_saved_age;',
                    '    wire [SLOT_WIDTH-1:0] recovery_saved_slot, recovery_saved_age;')
    source = change(source,
                    '    reg [ROB_ENTRIES-1:0] recovery_saved_kill;',
                    '    wire [ROB_ENTRIES-1:0] recovery_saved_kill;')
    start = source.index('    genvar recovery_row;')
    end = source.index('    // Allocation and commit are held', start)
    source = source[:start] + '''    // chosen_age is either a slot distance or ROB_ENTRIES+1 (no match).
    // COUNT_WIDTH retains that sentinel; SLOT_WIDTH alone would truncate it.
    localparam integer RECOVERY_QUERY_WIDTH=SLOT_WIDTH+2*COUNT_WIDTH+1;
    localparam integer RECOVERY_QUERY_DOMAINS=(ROB_ENTRIES+3)/4;
    wire [RECOVERY_QUERY_DOMAINS*RECOVERY_QUERY_WIDTH-1:0] recovery_query_views;
    wire [ROB_ENTRIES-1:0] recovery_row_preview;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_QUERY_WIDTH),.LEAVES(RECOVERY_QUERY_DOMAINS)) recovery_query_tree (
        .signal_i({recovery_preview_domains[2],head_recovery_index,COUNT_WIDTH'(chosen_age),occupancy_reg}),
        .views_o(recovery_query_views));
    genvar recovery_row;
    generate for(recovery_row=0;recovery_row<ROB_ENTRIES;recovery_row=recovery_row+1) begin:g_recovery_descriptor
        wire preview;
        wire [SLOT_WIDTH-1:0] local_head;
        wire [COUNT_WIDTH-1:0] local_branch_age,local_occupancy;
        assign {preview,local_head,local_branch_age,local_occupancy}=
            recovery_query_views[(recovery_row/4)*RECOVERY_QUERY_WIDTH +: RECOVERY_QUERY_WIDTH];
        wire [SLOT_WIDTH-1:0] relative_age=recovery_row-local_head;
        assign recovery_preview_kill[recovery_row]=valid_mem[recovery_row] &&
            relative_age>local_branch_age && relative_age<local_occupancy;
        assign recovery_row_preview[recovery_row]=preview;
    end endgenerate
    localparam integer RECOVERY_SAVED_WIDTH=ROB_ENTRIES+2*SLOT_WIDTH;
    wire [RECOVERY_SAVED_WIDTH-1:0] recovery_saved_payload;
    wire recovery_save_payload=!reset_i && !recovery_domains[5] && recovery_hold &&
        recovery_preview_domains[0] && !recovery_saved_valid;
    assign {recovery_saved_slot,recovery_saved_age,recovery_saved_kill}=recovery_saved_payload;
    // Same preview edge and unreset payload as the original descriptor.
    rv32_frequency_word_bank #(.WIDTH(RECOVERY_SAVED_WIDTH)) recovery_saved_owner (
        .clk_i(clk_i),.write_i(recovery_save_payload),
        .data_i({SLOT_WIDTH'(chosen_slot),SLOT_WIDTH'(chosen_age),recovery_preview_kill}),
        .data_o(recovery_saved_payload));
''' + source[end:]
    source = change(source, '''            recovery_saved_slot<=chosen_slot;
            recovery_saved_age<=chosen_age;
            recovery_saved_kill<=recovery_preview_kill;''',
                    '            // Payload is captured by the bounded owner on this same edge.')
    source = change(source, '''            wire [SLOT_WIDTH-1:0] relative_age = reclaim_entry - head_recovery_index;
            assign reclaim_eligible[reclaim_entry] = recovery_preview_domains[2] && valid_mem[reclaim_entry] &&
                rd_we_mem[reclaim_entry] && (relative_age > chosen_age) && (relative_age < occupancy_reg);''', '''            // Share the exact per-row interval predicate with the saved mask.
            assign reclaim_eligible[reclaim_entry]=recovery_row_preview[reclaim_entry] &&
                rd_we_mem[reclaim_entry] && recovery_preview_kill[reclaim_entry];''')

    anchor = '    // Allocation and all observable outputs are evaluated from old state.'
    source = change(source, anchor, '''    // Recovery lane tags query only live/generation metadata. Qualified
    // destination/checkpoint payload has a separate selected-slot read.
    localparam integer RECOVERY_LIVE_WIDTH=GENERATION_WIDTH+1;
    localparam integer RECOVERY_DEST_WIDTH=6+PHYS_ADDR_WIDTH+CHECKPOINT_WIDTH;
    wire [ROB_ENTRIES*RECOVERY_LIVE_WIDTH-1:0] recovery_live_rows;
    wire [ROB_ENTRIES*RECOVERY_DEST_WIDTH-1:0] recovery_dest_rows;
    wire [BE_WIDTH-1:0] recovery_lane_live;
    wire [RECOVERY_DEST_WIDTH-1:0] recovery_selected_dest;
    wire recovery_selected_rd_we;
    wire [4:0] recovery_selected_rd;
    wire [PHYS_ADDR_WIDTH-1:0] recovery_selected_phys;
    wire [CHECKPOINT_WIDTH-1:0] recovery_selected_checkpoint;
    assign {recovery_selected_checkpoint,recovery_selected_rd_we,recovery_selected_rd,recovery_selected_phys}=
        recovery_selected_dest;
    generate
        for(genvar recovery_query_row=0;recovery_query_row<ROB_ENTRIES;recovery_query_row=recovery_query_row+1) begin:g_recovery_query_row
            assign recovery_live_rows[recovery_query_row*RECOVERY_LIVE_WIDTH +: RECOVERY_LIVE_WIDTH]=
                {valid_mem[recovery_query_row],generation_mem[recovery_query_row]};
            if(CHECKPOINT_IMPL==0) begin:g_checkpoint
                assign recovery_dest_rows[recovery_query_row*RECOVERY_DEST_WIDTH +: RECOVERY_DEST_WIDTH]=
                    {checkpoint_mem[recovery_query_row],rd_we_mem[recovery_query_row],rd_mem[recovery_query_row],new_phys_mem[recovery_query_row]};
            end else begin:g_no_checkpoint
                assign recovery_dest_rows[recovery_query_row*RECOVERY_DEST_WIDTH +: RECOVERY_DEST_WIDTH]=
                    {{CHECKPOINT_WIDTH{1'b0}},rd_we_mem[recovery_query_row],rd_mem[recovery_query_row],new_phys_mem[recovery_query_row]};
            end
        end
        for(genvar recovery_query_lane=0;recovery_query_lane<BE_WIDTH;recovery_query_lane=recovery_query_lane+1) begin:g_recovery_lane_query
            wire [TAG_WIDTH-1:0] tag=recovery_tag_i[recovery_query_lane*TAG_WIDTH +: TAG_WIDTH];
            wire [RECOVERY_LIVE_WIDTH-1:0] live_state;
            rv32_frequency_array_read #(.WIDTH(RECOVERY_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) live_reader (
                .rows_i(recovery_live_rows),.index_i(tag[SLOT_LSB +: SLOT_WIDTH]),.value_o(live_state));
            assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] && live_state[GENERATION_WIDTH] &&
                tag[GEN_LSB +: GENERATION_WIDTH]==live_state[0 +: GENERATION_WIDTH];
        end
    endgenerate
    rv32_frequency_array_read #(.WIDTH(RECOVERY_DEST_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) recovery_dest_reader (
        .rows_i(recovery_dest_rows),.index_i(SLOT_WIDTH'(chosen_slot)),.value_o(recovery_selected_dest));

''' + anchor)
    source = change(source,
                    '                tag_matches(recovery_tag_i[(recovery_lane*TAG_WIDTH) +: TAG_WIDTH], recovery_slot) &&',
                    '                recovery_lane_live[recovery_lane] &&')
    source = change(source, 'checkpoint_restore_o = checkpoint_mem[chosen_slot];',
                           'checkpoint_restore_o = recovery_selected_checkpoint;')
    source = change(source, 'recovery_rd_we_o = rd_we_mem[chosen_slot];',
                           'recovery_rd_we_o = recovery_selected_rd_we;')
    source = change(source, "recovery_rd_o = rd_mem[chosen_slot];", "recovery_rd_o = recovery_selected_rd;")
    source = change(source, 'recovery_new_phys_o = new_phys_mem[chosen_slot];',
                           'recovery_new_phys_o = recovery_selected_phys;')
    return source


if __name__ == '__main__':
    prepare('CP_rob_recovery_distribution', ROOT/'CO_divider_payload_distribution', {
        'rtl/backend/rv32_rob.v': rob,
    }, 'CO plus four-row ROB recovery interval domains, shared descriptor/reclaim predicate, bounded saved descriptor write on its existing edge, static live/generation lane queries and selected destination/checkpoint query. Oldest/tie policy, valid/generation, sentinel ROB_ENTRIES+1, reset/unreset payload, preview/hold/apply, commit and cycle count preserved. No new FF/SRAM or hardware tests; source-only candidate.')
