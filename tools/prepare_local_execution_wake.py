"""Split ALU/MDU early wake ownership from ROB completion authority; no tests."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def backend(source):
    anchor='    generate if(RS_DIRECT_WAKE!=0) begin:g_direct_producer_wake'
    source=change(source,anchor,'''    // A locally owned ALU/MDU result loses valid on recovery BEFORE its
    // destination can be reclaimed. Completion still uses the full ROB
    // valid/generation authority above. Loads retain that authority for wake.
    wire [PRODUCERS-1:0] producer_wake_live;
    generate for(genvar wake_owner=0;wake_owner<PRODUCERS;wake_owner=wake_owner+1) begin:g_wake_owner
        if(LOCAL_EXEC_RECOVERY!=0 && wake_owner<=MDU_SOURCE) begin:g_local_execution
            assign producer_wake_live[wake_owner]=!reset_i && !flush_i &&
                producer_tag[wake_owner*TAG_WIDTH];
        end else begin:g_rob_authority
            assign producer_wake_live[wake_owner]=producer_target_live_r[wake_owner];
        end
    end endgenerate
    generate if(RS_DIRECT_WAKE!=0) begin:g_direct_producer_wake''')
    old='producer_valid & producer_rd_we & producer_target_live_r'
    if source.count(old)!=2:
        raise ValueError('Preserve unexpected wake qualification uses')
    source=source.replace(old,'producer_valid & producer_rd_we & producer_wake_live')
    source=change(source,'''    // recovery is suppressed by producer_target_live_r; the ordinary CDB
    // lanes remain in the bus for already-queued results.''',
        '''    // recovery is suppressed in each ALU/MDU owner, while LSQ retains
    // producer_target_live_r. CDB/PRF/ROB generation filtering is unchanged.''')
    return source


if __name__=='__main__':
    prepare('CY_local_execution_wake',ROOT/'CX1_execution_local_cancel_source_fix',
            {'rtl/backend/rv32_backend_joint.v':backend},
            'ALU/MDU early wake uses recovery-aware local result ownership; LSQ and all completion/PRF/ROB valid/generation filters preserved; no new FF/cycles; no HDL/EDA tests')
