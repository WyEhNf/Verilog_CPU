"""Move exact LSQ wake cancellation before report selection; no hardware tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def report_cancel(t):
    t = change(t,
        '    parameter integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1)',
        '''    parameter integer ALLOC_COUNT_WIDTH = (BE_WIDTH <= 1) ? 1 : $clog2(BE_WIDTH + 1),
    parameter integer LOCAL_REPORT_CANCEL = 0,
    parameter integer REPORT_RECOVERY_WIDTH = 1 +
        2*((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) + $clog2(ROB_ENTRIES+1)''')
    t = change(t, '''    output wire [SLOT_WIDTH-1:0]        tail_o
);''',
        '''    output wire [SLOT_WIDTH-1:0]        tail_o,
    // Same execution recovery packet used by the backend's original guard:
    // {apply,occupancy,head,branch_relative_age}. Disabled by default.
    input  wire [REPORT_RECOVERY_WIDTH-1:0] report_recovery_packet_i,
    output reg                          load_complete_cancel_o
);''')
    t = change(t,
        '    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+34;',
        '''    // Cancellation travels with the selected row's complete packet.
    // It is computed from that row's stored tag before head/age arbitration.
    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+35;''')
    t = change(t, '''    genvar report_row,report_word,report_node;
    generate''',
        '''    wire [LSQ_ENTRIES*REPORT_RECOVERY_WIDTH-1:0] report_recovery_views;
    generate if(LOCAL_REPORT_CANCEL!=0) begin:g_report_cancel_domains
        rv32_frequency_control_tree #(.WIDTH(REPORT_RECOVERY_WIDTH),.LEAVES(LSQ_ENTRIES)) recovery_tree (
            .signal_i(report_recovery_packet_i),.views_o(report_recovery_views));
    end else begin:g_no_report_cancel_domains
        assign report_recovery_views=0;
    end endgenerate
    genvar report_row,report_word,report_node;
    generate''')
    t = change(t, '''                wire [REPORT_WIDTH-1:0] report_payload={
                    !retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],''',
        '''                wire row_cancel;
                // This local combinational owner prevents the exact guard
                // from being reconstructed after the report payload mux.
                (* keep_hierarchy = 1 *)
                rv32_execution_recovery_cancel #(.TAG_WIDTH(ROB_TAG_WIDTH),
                    .ROB_ENTRIES(ROB_ENTRIES),.ENABLED(LOCAL_REPORT_CANCEL),
                    .KILL_BRANCH(0),.WIDTH(REPORT_RECOVERY_WIDTH)) cancel_guard (
                    .packet_i(report_recovery_views[report_row*REPORT_RECOVERY_WIDTH +: REPORT_RECOVERY_WIDTH]),
                    .active_i(1'b1),.tag_i(rob_tag_mem[report_row]),.cancel_o(row_cancel));
                wire [REPORT_WIDTH-1:0] report_payload={
                    row_cancel,!retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],''')
    t = change(t,
        '        {load_complete_unretired_o,load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];',
        '        {load_complete_cancel_o,load_complete_unretired_o,load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];')
    return t


def backend_cancel(t):
    t = change(t, '    wire lsq_load_complete_unretired;',
        '    wire lsq_load_complete_unretired;\n    wire lsq_load_complete_cancel;')
    t = change(t, '.REQUEST_PIPELINE(1), .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH)',
        '.REQUEST_PIPELINE(1), .LOCAL_REPORT_CANCEL(LOCAL_EXEC_RECOVERY), .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH)')
    t = change(t, '.load_complete_unretired_o(lsq_load_complete_unretired), .load_complete_error_o(lsq_load_complete_error)',
        '.load_complete_unretired_o(lsq_load_complete_unretired), .load_complete_cancel_o(lsq_load_complete_cancel), .report_recovery_packet_i(execution_recovery_views[(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]), .load_complete_error_o(lsq_load_complete_error)')
    t = change(t, '''    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(LOCAL_EXEC_RECOVERY),.KILL_BRANCH(0)) lsq_wake_guard (
        .packet_i(execution_recovery_views[(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
        .active_i(lsq_load_complete_valid),.tag_i(lsq_load_complete_tag),.cancel_o(lsq_wake_cancel));''',
        '''    generate if(LOCAL_EXEC_RECOVERY!=0) begin:g_preselected_lsq_cancel
        // Exact cancellation is selected with the LSQ report, removing the
        // late selected-tag subtraction/comparisons from the RS wake chain.
        assign lsq_wake_cancel=lsq_load_complete_cancel;
    end else begin:g_legacy_lsq_cancel
        rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
            .ENABLED(LOCAL_EXEC_RECOVERY),.KILL_BRANCH(0)) lsq_wake_guard (
            .packet_i(execution_recovery_views[(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
            .active_i(lsq_load_complete_valid),.tag_i(lsq_load_complete_tag),.cancel_o(lsq_wake_cancel));
    end endgenerate''')
    return t


if __name__ == '__main__':
    prepare('DI_lsq_preselected_cancel', ROOT/'DH_dcache_merge_controls',
        {'rtl/backend/rv32_lsq.v': report_cancel,
         'rtl/backend/rv32_backend_joint.v': backend_cancel},
        'Compute exact local recovery cancellation per LSQ row before report selection, carrying one flag in the unchanged-cycle report; retain ROB authority and DH byte-local refill controls.')
