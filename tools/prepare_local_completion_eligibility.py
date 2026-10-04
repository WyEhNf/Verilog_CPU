"""Prepare task-local direct completion eligibility; no hardware tools."""
from prepare_staged_frequency_candidate import ROOT,change,prepare


def local_completion(t):
    t=change(t,'    localparam integer LOCAL_EXEC_RECOVERY=(ISSUE_PIPELINE!=0);',
        '''    localparam integer LOCAL_EXEC_RECOVERY=(ISSUE_PIPELINE!=0);
    // A direct lane retains its source/full tag, not a second result payload.
    // Local owners suppress killed tasks before ROB/physical reuse. Queued
    // completion modes retain the original full ROB query as their authority.
    localparam integer LOCAL_COMPLETION_ELIGIBILITY=
        (LOCAL_EXEC_RECOVERY!=0) && (COMPLETION_BYPASS==2);''')
    t=change(t,'''        // A long-latency unit may still hold work older than a resolving
        // branch. Keep that work alive, while continuously rejecting stale
        // completions by ROB generation after recovery truncates the younger
        // suffix (whose slots and physical destinations may then be reused).''',
        '''        // In direct locally cancelled mode, each ALU/MDU still owns the
        // unfinished ROB task until its result is accepted. A load report also
        // carries unretired ownership. Recovery hides cancelled source-valid
        // before reclaim and rename reuse; no queued payload outlives its
        // source here. ROB completion still checks the complete tag/generation.
        // Legacy/nonlocal/queued modes retain full-table generation filtering.''')
    t=change(t,'''                (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                 !producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] ||
                 (producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 + ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] !=
                  producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH])))''',
        '''                (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                 (LOCAL_COMPLETION_ELIGIBILITY ? !producer_wake_live[producer_recovery_index] :
                  (!producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] ||
                   (producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 + ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] !=
                    producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH])))))''')
    t=change(t,'        if (recovery_domains[6]) begin\n            for (producer_recovery_index',
        '        if (!LOCAL_COMPLETION_ELIGIBILITY && recovery_domains[6]) begin\n            for (producer_recovery_index')
    t=change(t,'''        producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&
        lsq_load_complete_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
        producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH];''',
        '''        (LOCAL_COMPLETION_ELIGIBILITY ? producer_wake_live[LSQ_SOURCE] :
         (producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&
          lsq_load_complete_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
          producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]));''')
    t=change(t,'''    // CDB/PRF/ROB generation filtering is unchanged.
    // A locally owned ALU/MDU result loses valid on recovery BEFORE its
    // destination can be reclaimed. Completion still uses the full ROB
    // valid/generation authority above. A retained retired load cannot''',
        '''    // Direct local completion may use this same ownership eligibility;
    // queued modes keep the full ROB authority. A locally owned ALU/MDU
    // result loses valid on recovery BEFORE its destination is reclaimed.
    // The ROB's final tag/generation check is retained. A retained retired load cannot''')
    return t


if __name__=='__main__':
    prepare('DG_local_completion_eligibility',ROOT/'DF1_lsq_forward_windows_names',
            {'rtl/backend/rv32_backend_joint.v':local_completion},
            'DF1 source-only conditional proposal: direct locally cancelled completion '
            'uses retained task/unretired-load ownership before arbitration; legacy queued modes, '
            'branch training authority and final ROB generation checks retained; not adopted or tested')
