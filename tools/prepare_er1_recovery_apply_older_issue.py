"""Prepare retained older issue on a selective recovery edge; do not run HDL tools."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A46_lsq_empty_selection_bypass'
TARGET = BASE / 'A47_recovery_apply_older_issue'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists()
    assert not (BASE / 'A47_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}

    name = 'rtl/backend/rv32_reservation_station.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer LOCAL_PAYLOAD_ROWS = 0,',
        '''    parameter integer LOCAL_PAYLOAD_ROWS = 0,
    // Caller filters recovery-edge issue to retained, live older rows.
    // Allocation stays blocked; accepted retained rows must leave exactly once.
    parameter integer RECOVERY_ISSUE_RELEASE = 0,''')
    text = once(text, '    genvar export_lane,export_row;',
        '    wire [ENTRIES-1:0] issue_release_mask;\n    genvar export_lane,export_row;')
    text = once(text, '''            // Mirrors valid_mem's reset / flush / ordinary issue priorities.
            assign entry_release_o[export_row]=reset_i ||
                (flush_valid_i ? flush_kill_mask_i[export_row] : (|issued_here));''',
        '''            assign issue_release_mask[export_row]=|issued_here;
            // Mirrors valid/occupancy ownership, including retained issue on
            // a selective flush. Kill and accepted issue clear a row only once.
            assign entry_release_o[export_row]=reset_i ||
                (flush_valid_i ? (flush_kill_mask_i[export_row] ||
                 ((RECOVERY_ISSUE_RELEASE!=0) && issue_release_mask[export_row])) :
                 issue_release_mask[export_row]);''')
    text = once(text, '.kill_i(flush_kill_mask_i[owner_row]),.valid_i(valid_mem[owner_row]),.issue_i(|issued_here),',
        '''.kill_i(flush_kill_mask_i[owner_row] ||
                    ((RECOVERY_ISSUE_RELEASE!=0) && issue_release_mask[owner_row])),
                .valid_i(valid_mem[owner_row]),.issue_i(|issued_here),''')
    text = once(text, '                if (flush_kill_mask_i[reset_slot]) begin',
        '''                if (flush_kill_mask_i[reset_slot] ||
                    ((RECOVERY_ISSUE_RELEASE!=0) && issue_release_mask[reset_slot])) begin''')
    # Ordinary allocation/wakeup/issue and row payload implementation remain exact.
    marker = '        end else begin\n            for (wake_slot = 0;'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text

    name = 'rtl/rv32i_alu.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer SELECTIVE_RECOVERY = 0,',
        '    parameter integer SELECTIVE_RECOVERY = 0,\n    parameter integer RECOVERY_OLDER_ISSUE = 0,')
    text = once(text, '''    assign issue_ready_o = !flush_i && !result_cancel && !issue_cancel && !shift_busy &&
        (!result_valid_reg || exec_ready_i ||
         (live_tag_valid_i && (result_rob_tag_reg != live_tag_i)));''',
        '''    // The canceled result is invisible before the clock. A qualified
    // retained older instruction may replace that result on this same edge.
    // Surviving older results still require the original output handshake.
    wire recovery_replace=(RECOVERY_OLDER_ISSUE!=0) && result_cancel;
    assign issue_ready_o = !flush_i && !issue_cancel &&
        (recovery_replace || (!result_cancel && !shift_busy &&
         (!result_valid_reg || exec_ready_i ||
          (live_tag_valid_i && (result_rob_tag_reg != live_tag_i)))));''')
    text = once(text, '''    wire payload_accept=!reset_i && !flush_i && !shift_busy && !payload_cancel &&
        issue_ready_o && issue_valid_i;''',
        '''    wire payload_accept=!reset_i && !flush_i &&
        (recovery_replace || (!shift_busy && !payload_cancel)) &&
        issue_ready_o && issue_valid_i;''')
    text = once(text, '        if (reset_i || flush_i || result_cancel) begin',
        '        if (reset_i || flush_i || (result_cancel && !payload_accept)) begin')
    text = once(text, '        end else if (shift_busy) begin',
        '        end else if (shift_busy && !recovery_replace) begin')
    text = once(text, '        end else if (result_valid_reg && live_tag_valid_i && (result_rob_tag_reg != live_tag_i) && !exec_ready_i) begin',
        '        end else if (result_valid_reg && live_tag_valid_i && (result_rob_tag_reg != live_tag_i) && !exec_ready_i && !recovery_replace) begin')
    # Arithmetic and all payload owners (except their shared write predicate)
    # stay exact. No new ALU result slot, metadata field or state bit.
    a = '    // Exclusive opcode classes'; z = '    always @(posedge clk_i) begin'
    assert text[text.index(a):text.index(z)] == original[original.index(a):original.index(z)]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text

    name = 'rtl/backend/rv32m_mdu_reservation_station.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer SELECTIVE_RECOVERY = 0,',
        '    parameter integer SELECTIVE_RECOVERY = 0,\n    parameter integer RECOVERY_OLDER_ISSUE = 0,')
    text = once(text, '''    assign issue_ready_o = !flush_i &&
                           (!SELECTIVE_RECOVERY || !recovery_packet_i[RECOVERY_WIDTH-1]) &&
                           (!pending_valid || unit_req_fire) &&
                           (issue_is_mul || issue_is_div);''',
        '''    wire issue_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(1)) issue_cancel_guard (
        .packet_i(recovery_views[0 +: RECOVERY_WIDTH]),
        .active_i(issue_valid_i),.tag_i(issue_rob_tag_i),.cancel_o(issue_cancel));
    assign issue_ready_o = !flush_i &&
                           (!SELECTIVE_RECOVERY || !recovery_packet_i[RECOVERY_WIDTH-1] ||
                            ((RECOVERY_OLDER_ISSUE!=0) && !issue_cancel)) &&
                           (!pending_valid || unit_req_fire ||
                            ((RECOVERY_OLDER_ISSUE!=0) && pending_cancel)) &&
                           (issue_is_mul || issue_is_div);''')
    # Existing launch_capture writes the full input packet. In the sequential
    # owner, accepted issue already has priority over pending_cancel clearing.
    marker = '    assign completion_valid_o = mul_resp_valid || div_resp_valid;'
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text

    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 0,',
        '    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 0,\n    parameter integer RECOVERY_APPLY_OLDER_ISSUE = 0,')
    text = once(text, '    // Registered RS selection / execution boundary.',
        '''    // The new edge uses the direct RS contract and selective execution
    // cancellation together. Other pipeline/recovery modes retain old gating.
    localparam integer RECOVERY_APPLY_ISSUE_ACTIVE=(RECOVERY_APPLY_OLDER_ISSUE!=0) &&
        (LOCAL_EXEC_RECOVERY!=0) && (ISSUE_PIPELINE==0);

    // Registered RS selection / execution boundary.''')
    text = once(text, '''            // Preview owns a registered branch tag, and does not flush RS.
            // A selected valid row strictly before that branch can execute on
            // this edge. The following descriptor-apply edge still blocks all
            // launches: RS flush has priority over its issue-release update.
            // This also prevents duplicate issue of a retained older row.''',
        '''            // Preview uses the live head. Apply uses the captured recovery
            // packet, and can issue only a retained row with the exact current
            // ROB generation. The RS now releases accepted retained rows on
            // that edge, so they cannot be issued again after recovery.''')
    text = once(text, '            assign rs_issue_allowed[io_lane]=!branch_busy_domains[0] || older_preview;',
        '''            wire older_apply;
            if(RECOVERY_APPLY_ISSUE_ACTIVE!=0) begin:g_apply_issue
                wire [ROB_LIVE_WIDTH-1:0] issue_live;
                wire issue_cancel;
                rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),
                    .index_i(rs_issue_tag[io_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                    .value_o(issue_live));
                rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
                    .ENABLED(1),.KILL_BRANCH(1)) age_guard (
                    .packet_i(execution_recovery_views[io_lane*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
                    .active_i(rs_issue_valid[io_lane]),
                    .tag_i(rs_issue_tag[io_lane*TAG_WIDTH +: TAG_WIDTH]),.cancel_o(issue_cancel));
                assign older_apply=branch_pending && recovery_descriptor_valid && recovery_domains[4] &&
                    !reset_i && !flush_i && rs_issue_valid[io_lane] && rs_issue_tag[io_lane*TAG_WIDTH] &&
                    issue_live[ROB_GENERATION_WIDTH] &&
                    rs_issue_tag[io_lane*TAG_WIDTH+3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
                        issue_live[0 +: ROB_GENERATION_WIDTH] && !issue_cancel;
            end else begin:g_apply_issue_disabled
                assign older_apply=1'b0;
            end
            assign rs_issue_allowed[io_lane]=!branch_busy_domains[0] || older_preview || older_apply;''')
    text = once(text, '.AGE_WIDTH(RS_AGE_WIDTH)) rs (',
        '.AGE_WIDTH(RS_AGE_WIDTH), .RECOVERY_ISSUE_RELEASE(RECOVERY_APPLY_ISSUE_ACTIVE)) rs (')
    child_argument = '.SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY))'
    assert text.count(child_argument) == 2
    text = text.replace(child_argument,
        '.SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY), .RECOVERY_OLDER_ISSUE(RECOVERY_APPLY_ISSUE_ACTIVE))')
    # Recovery construction/capture, ROB/LSQ/RAT state and normal execution
    # routing are otherwise the original source. No descriptor bit is added.
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text

    for name, default in (('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)):
        text = (PARENT / name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = {default},',
            f'    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = {default},\n    parameter integer RECOVERY_APPLY_OLDER_ISSUE = {default},')
        text = once(text, '.RECOVERY_PREVIEW_OLDER_ISSUE(RECOVERY_PREVIEW_OLDER_ISSUE),',
            '.RECOVERY_PREVIEW_OLDER_ISSUE(RECOVERY_PREVIEW_OLDER_ISSUE), .RECOVERY_APPLY_OLDER_ISSUE(RECOVERY_APPLY_OLDER_ISSUE),')
        changes[name] = text

    # Validate all intended transformations before creating a candidate.
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    for name in parent['source_sha256']:
        dst = TARGET / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dst)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], RECOVERY_APPLY_OLDER_ISSUE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],
        recovery_apply_issue_still_blocked=False, recovery_apply_strict_older_issue=True,
        recovery_apply_exact_rob_generation_check=True, recovery_apply_issue_added_ff_bits=0,
        recovery_apply_issue_added_sram_bits=0, recovery_apply_issue_added_pipeline_edges=0,
        recovery_apply_issue_generation_query_ports=2)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Permit exact-live strict-older direct RS issue during descriptor apply, release each accepted retained row in RS valid/occupancy/release/payload ownership, replace an invisible canceled ALU result or canceled MDU launch packet on the same edge. Keep all surviving-result backpressure and underlying M-unit recovery unchanged.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        recovery_apply_issue_eligible_survivor_count_unknown=True,
        recovery_apply_issue_removed_global_pause=True,
        recovery_apply_issue_extra_generation_read_and_control_cost_unknown=True,
        recovery_apply_issue_whole_program_gain_unmeasured=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_RECOVERY_APPLY_OLDER_ISSUE_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0,
        added_pipeline_edges=0, removed_global_issue_pause_edges=1,
        source_arguments=[
            'Apply eligibility requires the actual accepted recovery domain, a valid descriptor and pending branch, no reset/flush, valid selected RS and ROB row, exact ROB generation equality, and circular age strictly before the branch and within the captured occupancy. Preview behavior is unchanged. Current program observations do not establish how often eligible older rows exist.',
            'RS valid and occupancy on selective flush exclude the union of killed rows and accepted issued rows; entry_release exports that same union; local payload target_live receives the same issued-row kill. Ordinary allocation/age/wakeup/issue source stays exact. Recovery-edge allocation remains blocked. No row is removed solely because it was offered or became ready.',
            'ALU result cancellation still makes the old result invisible combinationally. A new older accepted packet writes all original value/metadata/prediction owners, and accepted replacement wins over cancel clearing in the valid owner. Canceled iterative shift cannot advance its old payload. Surviving old results remain protected by original ready/backpressure; reset or external flush never accepts replacement.',
            'MDU acceptance checks the incoming packet against the selective recovery range, and may replace only an empty, normally consumed or canceled launch buffer. Existing launch packet owner and pending_valid assignment priority already accept the full new packet after clearing the canceled one. Multiplier/divider/iterative engines remain source-exact and may continue to block their own request ports during apply.',
            'ALU issue_valid, RS issue_ready and MDU candidate arbitration share rs_issue_allowed. Wrong-path, resolving-branch and stale-generation rows cannot enter the new apply path. Completion/CDB/ROB/LSQ generation and in-order retirement authority are unchanged. An older branch that resolves while another recovery is pending still waits in its result slot for the existing one-entry branch queue.',
            'Optional mode is active only with direct ISSUE_PIPELINE0 and LOCAL_EXEC_RECOVERY1. Backend/core/standalone child defaults are0; course top enables1. Mode0 keeps original flush priority and all old recovery gates, and no new state is declared.',
            'There are two new9-bit ROB live-generation query views in the course profile, plus recovery eligibility, release and replacement control. Register/SRAM count is unchanged, but combinational area, fanout and delay can increase. No measured area/Fmax/IPC is assigned to this candidate; the known308MHz result belongs only toA41.',
            'Future meaningful coverage includes exact-once issue on preview/apply, dual-lane ALU and shared M arbitration, recovery-tag equality and ROB wrap, stale generation, canceled and surviving shift/result/MDU buffers, prolonged output backpressure, older nested mispredicts, younger loads/stores, reset/external flush, and optional-mode/pipeline fallback. No HDL/lint/simulation/synthesis/STA/unit execution is started by preparation.'
        ])
    write(BASE / 'A47_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
