"""Carry LSQ lifetime with the same report, preserving completion authority."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'    output reg  [PHYS_ADDR_WIDTH-1:0]    load_complete_phys_rd_o,',
        '''    output reg  [PHYS_ADDR_WIDTH-1:0]    load_complete_phys_rd_o,
    output reg                          load_complete_unretired_o,''')
    source=change(source,'    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+33;',
        '    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+34;')
    source=change(source,'''                wire [REPORT_WIDTH-1:0] report_payload={
                    physical_destinations''',
        '''                wire [REPORT_WIDTH-1:0] report_payload={
                    !retired_mem[report_row],physical_destinations''')
    source=change(source,'        {load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];',
        '        {load_complete_unretired_o,load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];')
    return source


def backend(source):
    source=change(source,'    wire [PAW-1:0] lsq_load_complete_phys;',
        '    wire [PAW-1:0] lsq_load_complete_phys;\n    wire lsq_load_complete_unretired;')
    source=change(source,'wire [(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH-1:0] execution_recovery_views;',
        'wire [(BE_WIDTH+2)*EXEC_RECOVERY_WIDTH-1:0] execution_recovery_views;')
    source=change(source,'.WIDTH(EXEC_RECOVERY_WIDTH),.LEAVES(BE_WIDTH+1)) execution_recovery_tree',
        '.WIDTH(EXEC_RECOVERY_WIDTH),.LEAVES(BE_WIDTH+2)) execution_recovery_tree')
    source=change(source,'.load_complete_phys_rd_o(lsq_load_complete_phys),',
        '.load_complete_phys_rd_o(lsq_load_complete_phys), .load_complete_unretired_o(lsq_load_complete_unretired),')
    source=change(source,'''    // recovery is suppressed in each ALU/MDU owner, while LSQ retains
    // producer_target_live_r. CDB/PRF/ROB generation filtering is unchanged.''',
        '''    // recovery is suppressed in each ALU/MDU owner. LSQ additionally
    // carries unretired lifetime with its report and applies the same snapshot.
    // CDB/PRF/ROB generation filtering is unchanged.''')
    source=change(source,'''    // valid/generation authority above. Loads retain that authority for wake.
    wire [PRODUCERS-1:0] producer_wake_live;''',
        '''    // valid/generation authority above. A retained retired load cannot
    // wake, even if a late response reaches its still-allocated LSQ row.
    wire lsq_wake_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(LOCAL_EXEC_RECOVERY),.KILL_BRANCH(0)) lsq_wake_guard (
        .packet_i(execution_recovery_views[(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
        .active_i(lsq_load_complete_valid),.tag_i(lsq_load_complete_tag),.cancel_o(lsq_wake_cancel));
    wire [PRODUCERS-1:0] producer_wake_live;''')
    source=change(source,'''                producer_tag[wake_owner*TAG_WIDTH];
        end else begin:g_rob_authority''',
        '''                producer_tag[wake_owner*TAG_WIDTH];
        end else if(LOCAL_EXEC_RECOVERY!=0 && wake_owner==LSQ_SOURCE) begin:g_local_load
            assign producer_wake_live[wake_owner]=!reset_i && !flush_i &&
                lsq_load_complete_unretired && lsq_load_complete_tag[0] && !lsq_wake_cancel;
        end else begin:g_rob_authority''')
    return source


if __name__=='__main__':
    prepare('DB_load_local_wake',ROOT/'DA_radix4_booth_pipeline',
            {'rtl/backend/rv32_lsq.v':lsq,'rtl/backend/rv32_backend_joint.v':backend},
            'LSQ report adds same-row unretired lifetime; local recovery age excludes killed/outside loads before early wake; all normal completion valid/generation/response guards retained; 74-bit report still five words; no HDL/EDA tests')
