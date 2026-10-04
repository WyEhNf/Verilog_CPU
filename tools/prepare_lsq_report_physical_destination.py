"""Fuse the load physical destination with LSQ report selection; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,',
                        '''    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,''')
    source=change(source,'    input  wire [(BE_WIDTH*ROB_TAG_WIDTH)-1:0] alloc_rob_tag_i,',
                        '''    input  wire [(BE_WIDTH*ROB_TAG_WIDTH)-1:0] alloc_rob_tag_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_phys_rd_i,''')
    source=change(source,'    output reg  [31:0]                  load_complete_value_o,',
                        '''    output reg  [31:0]                  load_complete_value_o,
    output reg  [PHYS_ADDR_WIDTH-1:0]    load_complete_phys_rd_o,''')
    source=change(source,'    // Load reporting follows queue age; store admission preserves the former','''    // Move the existing backend LSQ_ENTRIES x PHYS_ADDR_WIDTH map into its
    // transaction owner. These are the SAME unreset allocation payload bits.
    // A valid report selects phys/value/full ROB+LSQ identity in parallel;
    // it no longer selects a tag then uses that tag for a second table read.
    localparam integer PHYS_MAP_DOMAINS=(LSQ_ENTRIES+3)/4;
    wire [LSQ_ENTRIES*PHYS_ADDR_WIDTH-1:0] physical_destinations;
    wire [PHYS_MAP_DOMAINS*BE_WIDTH-1:0] physical_alloc_views;
    wire [PHYS_MAP_DOMAINS*BE_WIDTH*SLOT_WIDTH-1:0] physical_slot_views;
    wire [PHYS_MAP_DOMAINS*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] physical_value_views;
    wire [BE_WIDTH*SLOT_WIDTH-1:0] physical_alloc_slots;
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(PHYS_MAP_DOMAINS)) physical_alloc_tree (
        .signal_i(alloc_fire_o & {BE_WIDTH{!reset_i}}),.views_o(physical_alloc_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*SLOT_WIDTH),.LEAVES(PHYS_MAP_DOMAINS)) physical_slot_tree (
        .signal_i(physical_alloc_slots),.views_o(physical_slot_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(PHYS_MAP_DOMAINS)) physical_value_tree (
        .signal_i(alloc_phys_rd_i),.views_o(physical_value_views));
    generate
        for(genvar physical_lane=0;physical_lane<BE_WIDTH;physical_lane=physical_lane+1) begin:g_physical_alloc_slot
            assign physical_alloc_slots[physical_lane*SLOT_WIDTH +: SLOT_WIDTH]=
                alloc_lsq_tag_o[physical_lane*TAG_WIDTH+TAG_SLOT_LSB +: SLOT_WIDTH];
        end
        for(genvar physical_row=0;physical_row<LSQ_ENTRIES;physical_row=physical_row+1) begin:g_physical_destination_row
            localparam integer DOMAIN=physical_row/4;
            wire [BE_WIDTH-1:0] row_match_mask;
            wire row_write;
            wire [PHYS_ADDR_WIDTH-1:0] next_phys;
            for(genvar physical_lane=0;physical_lane<BE_WIDTH;physical_lane=physical_lane+1) begin:g_match
                assign row_match_mask[physical_lane]=physical_alloc_views[DOMAIN*BE_WIDTH+physical_lane] &&
                    physical_slot_views[(DOMAIN*BE_WIDTH+physical_lane)*SLOT_WIDTH +: SLOT_WIDTH]==physical_row;
            end
            rv32_frequency_event_select #(.WIDTH(PHYS_ADDR_WIDTH),.EVENTS(BE_WIDTH)) selector (
                .events_i(row_match_mask),
                .values_i(physical_value_views[DOMAIN*BE_WIDTH*PHYS_ADDR_WIDTH +: BE_WIDTH*PHYS_ADDR_WIDTH]),
                .write_o(row_write),.value_o(next_phys));
            rv32_frequency_word_bank #(.WIDTH(PHYS_ADDR_WIDTH)) owner (
                .clk_i(clk_i),.write_i(row_write),.data_i(next_phys),
                .data_o(physical_destinations[physical_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]));
        end
    endgenerate

    // Load reporting follows queue age; store admission preserves the former''')
    source=change(source,'    localparam integer REPORT_WIDTH=ROB_TAG_WIDTH+TAG_WIDTH+33;',
                        '    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+33;')
    source=change(source,'''                wire [REPORT_WIDTH-1:0] report_payload={complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};''','''                wire [REPORT_WIDTH-1:0] report_payload={
                    physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};''')
    source=change(source,'        {load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];',
                        '        {load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];')
    return source


def backend(source):
    source=change(source,'    wire [PAW-1:0] lsq_phys_mem [0:LSQ_ENTRIES-1];\n','')
    for old in [
        '    localparam integer LSQ_MAP_READ_DOMAINS=(LSQ_ENTRIES+3)/4;\n',
        '    localparam integer LSQ_MAP_READ_LEAVES=1<<$clog2(LSQ_ENTRIES);\n',
        '    localparam integer LSQ_MAP_READ_WORDS=(PAW+15)/16;\n',
        '    wire [LSQ_MAP_READ_DOMAINS*LSQ_SLOT_WIDTH-1:0] lsq_map_query_views;\n',
        '    wire [PAW-1:0] load_phys_map_read;\n',
        '    wire [MAP_DOMAINS*BE_WIDTH*LSQ_SLOT_WIDTH-1:0] d_lsq_map_slots;\n',
        '    wire [MAP_DOMAINS*BE_WIDTH*PAW-1:0] d_lsq_map_values;\n',
        '    wire [BE_WIDTH*LSQ_SLOT_WIDTH-1:0] d_lsq_slot_input;\n',
    ]:
        source=change(source,old,'')
    source=change(source,'''    rv32_frequency_control_tree #(.WIDTH(LSQ_SLOT_WIDTH),.LEAVES(LSQ_MAP_READ_DOMAINS)) lsq_map_query_tree (
        .signal_i(lsq_load_complete_lsq_tag[3 +: LSQ_SLOT_WIDTH]),.views_o(lsq_map_query_views));\n''','')
    start=source.index('        begin:g_lsq_phys_read')
    end=source.index('    endgenerate',start)
    source=source[:start]+source[end:]
    source=change(source,'producer_phys_r[LSQ_SOURCE*PAW +: PAW]=load_phys_map_read;',
                        'producer_phys_r[LSQ_SOURCE*PAW +: PAW]=lsq_load_complete_phys;')
    source=change(source,'''    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*LSQ_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) d_lsq_slot_tree (
        .signal_i(d_lsq_slot_input),.views_o(d_lsq_map_slots));\n''','')
    source=change(source,'''    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PAW),.LEAVES(MAP_DOMAINS)) d_lsq_value_tree (
        .signal_i(d_new_phys),.views_o(d_lsq_map_values));\n''','')
    source=change(source,'''            assign d_lsq_slot_input[map_lane_id*LSQ_SLOT_WIDTH +: LSQ_SLOT_WIDTH]=
                lsq_alloc_tag[map_lane_id*TAG_WIDTH+3 +: LSQ_SLOT_WIDTH];\n''','')
    start=source.index('        for(map_row=0;map_row<LSQ_ENTRIES;map_row=map_row+1) begin:g_lsq_phys_row')
    end=source.index('    endgenerate',start)
    source=source[:start]+source[end:]
    source=change(source,'    wire [31:0] lsq_load_complete_value;',
                        '''    wire [31:0] lsq_load_complete_value;
    wire [PAW-1:0] lsq_load_complete_phys;''')
    source=change(source,'.ROB_TAG_WIDTH(TAG_WIDTH), .ROB_ENTRIES(ROB_ENTRIES)) lsq (',
                        '.ROB_TAG_WIDTH(TAG_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .PHYS_ADDR_WIDTH(PAW)) lsq (')
    source=change(source,'.alloc_rob_tag_i(d_tag), .alloc_size_i(d_mem_size)',
                        '.alloc_rob_tag_i(d_tag), .alloc_phys_rd_i(d_new_phys), .alloc_size_i(d_mem_size)')
    source=change(source,'.load_complete_value_o(lsq_load_complete_value), .load_complete_error_o(lsq_load_complete_error)',
                        '.load_complete_value_o(lsq_load_complete_value), .load_complete_phys_rd_o(lsq_load_complete_phys), .load_complete_error_o(lsq_load_complete_error)')
    return source


if __name__=='__main__':
    prepare('CV_lsq_parallel_report_destination',ROOT/'CU1_rob_reclaim_width_guard',{
        'rtl/backend/rv32_lsq.v':lsq,
        'rtl/backend/rv32_backend_joint.v':backend,
    }, 'CU1 plus migration of the existing LSQ16xPHYS6 allocation map into LSQ ownership and parallel physical-destination selection in the same report payload as value/full ROB+LSQ tags. Removes post-report tag-to-phys lookup, not a new completion register. Same96 payload FFs and unreset allocation edge, last-lane priority, forwarding/cache result capture, report/hold/recovery/generation guards, oldest-report policy and cycles. Invalid phys output now0 with invalid report; no valid-interface behavior/extra stage/SRAM/hardware tests.')
