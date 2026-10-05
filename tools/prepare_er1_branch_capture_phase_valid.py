"""Specialize capture visibility to direct recovery's empty-pending phase."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A74_ras_parallel_control'
TARGET = BASE / 'A75_branch_capture_phase_valid'
REVIEW = BASE / 'A75_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/rv32i_alu.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    output wire                         exec_valid_o,',
        '''    output wire                         exec_valid_o,
    // Private capture query: saved result validity before selective recovery.
    // It is not an execution/completion handshake or cancellation bypass.
    output wire                         exec_saved_valid_o,''')
    text = once(text, '    assign exec_valid_o = result_visible;',
        '''    assign exec_valid_o = result_visible;
    assign exec_saved_valid_o = result_valid_reg &&
        (!live_tag_valid_i || (result_rob_tag_reg == live_tag_i));''')
    assert text[text.index('    // The canceled result is invisible before the clock.'):]==original[
        original.index('    // The canceled result is invisible before the clock.'):]
    assert 'wire result_visible = result_valid_reg && !result_cancel &&' in text
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer BRANCH_CAPTURE_REDIRECT_READY = 0,',
        '''    parameter integer BRANCH_CAPTURE_REDIRECT_READY = 0,
    parameter integer BRANCH_CAPTURE_PHASE_VALID = 0,''')
    text = once(text, '    wire [BE_WIDTH-1:0] alu_exec_valid, alu_exec_ready, alu_issue_ready;',
        '    wire [BE_WIDTH-1:0] alu_exec_valid, alu_exec_ready, alu_issue_ready;\n    wire [BE_WIDTH-1:0] alu_exec_saved_valid;')
    text = once(text, '.exec_valid_o(alu_exec_valid[alu_lane]),',
        '.exec_valid_o(alu_exec_valid[alu_lane]), .exec_saved_valid_o(alu_exec_saved_valid[alu_lane]),')
    text = once(text, '''    wire [BE_WIDTH-1:0] capture_redirect_claim=
        alu_exec_valid & alu_exec_redirect_valid & ~alu_exec_is_load;''',
        '''    // Direct ROB apply is sourced only by branch_pending. Capture
    // requires !branch_pending, so selective apply cancellation is zero in
    // its whole acceptance domain. All real execution ports keep cancel.
    localparam integer CAPTURE_PHASE_VALID_ACTIVE=(BRANCH_CAPTURE_PHASE_VALID!=0) &&
        (BRANCH_CAPTURE_REDIRECT_READY!=0) && (RECOVERY_DIRECT_ACTIVE!=0);
    wire [BE_WIDTH-1:0] branch_capture_valid=(CAPTURE_PHASE_VALID_ACTIVE!=0)?
        alu_exec_saved_valid:alu_exec_valid;
    wire [BE_WIDTH-1:0] capture_redirect_claim=
        branch_capture_valid & alu_exec_redirect_valid & ~alu_exec_is_load;''')
    text = once(text, '''            alu_exec_valid[capture_lane] &&
            ((BRANCH_CAPTURE_REDIRECT_READY!=0)?capture_redirect_ready[capture_lane]:alu_exec_ready[capture_lane]) &&''',
        '''            branch_capture_valid[capture_lane] &&
            ((BRANCH_CAPTURE_REDIRECT_READY!=0)?capture_redirect_ready[capture_lane]:alu_exec_ready[capture_lane]) &&''')
    # Only the private capture predicate sees saved-valid. Ordinary ready,
    # producer/wake, predictor feedback and all selective guards stay exact.
    for a, b in [
        ('    always @* begin\n        producer_valid_r =', '    assign alu_exec_ready = alu_exec_ready_r;'),
        ('    // Train on every resolved control-flow instruction,', '    // Wide checkpoint recovery'),
    ]:
        if b in original:
            assert text[text.index(a):text.index(b)] == original[original.index(a):original.index(b)]
    for marker in [
        'assign branch_capture_match[capture_lane]=!reset_i && !flush_i && !branch_pending &&',
        'branch_training_live[capture_lane] && alu_exec_redirect_valid[capture_lane];',
        'assign branch_training_live[training_lane] = !reset_i && !flush_i && !alu_flush_r[training_lane] &&',
        'producer_live_reads[training_lane*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&',
        '(alu_exec_tag[training_lane*TAG_WIDTH+3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==',
        '.recovery_valid_i({ {(BE_WIDTH-1){1\'b0}}, branch_pending })',
        'assign recovery_descriptor_head=rob_head_views[0 +: ROB_SLOT_WIDTH];',
        'assign recovery_descriptor_valid=branch_pending && rob_recovery_preview;',
        '.STAGED_RECOVERY(RECOVERY_DIRECT_ACTIVE==0)',
    ]:
        assert marker in text, marker
    assert text.count('alu_exec_saved_valid') == 3
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        text = (PARENT / name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer BRANCH_CAPTURE_REDIRECT_READY = {default},',
            f'    parameter integer BRANCH_CAPTURE_REDIRECT_READY = {default},\n    parameter integer BRANCH_CAPTURE_PHASE_VALID = {default},')
        text = once(text, '.BRANCH_CAPTURE_REDIRECT_READY(BRANCH_CAPTURE_REDIRECT_READY),',
            '.BRANCH_CAPTURE_REDIRECT_READY(BRANCH_CAPTURE_REDIRECT_READY), .BRANCH_CAPTURE_PHASE_VALID(BRANCH_CAPTURE_PHASE_VALID),')
        changes[name] = text
    rob = (PARENT / 'rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    for marker in [
        'wire recovery_apply = STAGED_RECOVERY ?',
        '(recovery_apply_i && recovery_saved_valid) : recovery_found;',
        'recovery_found = 1\'b0;',
        'if (recovery_valid_i[recovery_lane] &&',
    ]:
        assert marker in rob, marker
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_DIRECT_BRANCH_CAPTURE_PHASE_VALID_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], BRANCH_CAPTURE_PHASE_VALID=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], branch_capture_phase_valid=True,
        branch_capture_phase_new_ff_bits=0, branch_capture_phase_new_sram_bits=0,
        branch_capture_full_gen_and_actual_execution_cancel_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Expose ALU saved-visible valid before selective recovery only as a private direct-mode branch-capture query. Under !branch_pending, direct ROB recovery_found/apply are zero, so it equals original execution valid. Use this same private valid for capture and prior redirect claims, preserving original full-GEN/flush/reset qualification and all actual ALU result cancellation/ready/completion/wakeup consumers. Remove recovery-apply to ALU visibility to fresh capture/redirect structural feedback without state/cycle changes.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        branch_capture_direct_recovery_phase_source_argument=True,
        recovery_apply_to_fresh_branch_capture_visibility_dependency_removed=True,
        branch_capture_phase_limit='Relies on exact direct-mode sole branch_pending recovery source; staged/default profiles fall back. Remaining full-GEN/current-PC/epoch/frontend paths need later STA. Metrics and formal/dynamic equivalence remain unknown.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        source_arguments=[
            'Active specialization requires BRANCH_CAPTURE_REDIRECT_READY and RECOVERY_DIRECT_ACTIVE. Backend ROB recovery_valid has only lane0=branch_pending. In direct mode STAGED_RECOVERY0, recovery_found requires one such valid lane and recovery_apply=recovery_found. Therefore branch_pending0 implies apply0 exactly, independent of tag/generation/occupancy or stale saved descriptors.',
            'Original ALU result_visible=saved_valid && !selective_cancel && same_live_tag_condition. Its selective guard returns cancel0 when packet apply0; enabled capture match already requires !branch_pending. Thus private saved-visible equals original execution-visible for all lanes in the entire capture acceptance domain. Outside it both old/new capture matches are zero. Shift work with result_valid0 remains invalid; there is no issue-to-output lookthrough.',
            'Prior redirect-claim valid uses the same phase-visible vector. Under !branch_pending it equals the original prior-lane ALU valid, including stale GEN redirects that reserve ready priority. A72 exact redirect-ready rule is required so no general ALU ready input reintroduces selective cancel/producer-ready into capture. Selected matching lane, packet value/enable/history and frontend redirect cycle remain original.',
            'Branch_training_live keeps reset, flush, ALU flush, tag-valid, current ROB valid and full eight-generation-bit comparison. Ordinary ALU exec_valid/issue_ready/result_cancel/payload_accept/state updates are byte exact. Completion, wake, AGU notifications, producer validity, actual ALU output ready, non-redirect predictor feedback and held MDU/LSQ cancellation never use the private sideband.',
            'On apply branch_pending1 suppresses all fresh capture regardless of private valid. The same edge kills younger ROB rows and updates original ALU valid owners. Next cycle pending0, surviving saved result candidates still face complete current ROB generation authority. No stale killed result is reinterpreted as a valid new branch. Reset/flush priority remains original.',
            'No FF/SRAM/pipeline edge added; ALU sideband is combinational from existing saved validity/tag. Flags0, staged recovery, non-local recovery or other inactive profiles use original exec_valid; unused sideband can be pruned. No false-path constraint or weakened execution cancel is added. Source phase/Boolean/hash reasoning only, not equivalence verification or measured Fmax.',
            'Future coherent coverage: capture before apply, no capture during apply, simultaneous older/younger held redirects, apply-edge older replacement, stale full-GEN/reused ROB slots, delayed/held branch, stalled completion with MDU/LSQ, flush/reset, shift result validity, widths1/2/4, direct0/flag0 fallbacks and exact branch feedback/history/epoch counts.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
