"""Prepare a source-only older-issue preview phase; keep apply-edge issue blocked."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A38_instruction_sram_command_lanes'
TARGET = BASE / 'A39_recovery_preview_older_issue'
PROFILE = Path('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    profile = read(PROFILE)
    assert profile['status'] == 'THREE_CASE_HOST_PROFILE_COMPLETE'
    assert all(row['official_answer_passed'] and row['cycles_exact_a36'] for row in profile['results'])
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer EARLY_FRONT_REDIRECT = 0,',
                '    parameter integer EARLY_FRONT_REDIRECT = 0,\n    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 0,')
    text = once(text, '    wire [BE_WIDTH-1:0] rs_issue_ready;',
                '    wire [BE_WIDTH-1:0] rs_issue_ready;\n    wire [BE_WIDTH-1:0] rs_issue_allowed;')
    start = '''            // Do not launch a new operation on the edge that accepts branch
            // recovery.  The RS is flushed on that edge, so a simultaneously
            // accepted younger operation would otherwise survive in an empty
            // ALU/MDU output slot after its ROB generation had been killed.
            // Existing strict-older execution results remain independently
            // drainable through alu_exec_ready/producers below.
            assign rs_issue_ready[io_lane] = !branch_busy_domains[0] &&'''
    replacement = '''            // Preview owns a registered branch tag, and does not flush RS.
            // A selected valid row strictly before that branch can execute on
            // this edge. The following descriptor-apply edge still blocks all
            // launches: RS flush has priority over its issue-release update.
            // This also prevents duplicate issue of a retained older row.
            wire [ROB_SLOT_WIDTH-1:0] issue_age=
                rs_issue_tag[io_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]-rob_head;
            wire [ROB_SLOT_WIDTH-1:0] pending_age=
                recovery_tag_views[0 +: TAG_WIDTH][3 +: ROB_SLOT_WIDTH]-rob_head;
            wire older_preview=(RECOVERY_PREVIEW_OLDER_ISSUE!=0) &&
                (LOCAL_EXEC_RECOVERY!=0) && (ISSUE_PIPELINE==0) &&
                branch_pending && rob_recovery_preview && !recovery_descriptor_valid &&
                !reset_i && !flush_i && rs_issue_valid[io_lane] &&
                rs_issue_tag[io_lane*TAG_WIDTH] && issue_age<pending_age &&
                issue_age<rob_occupancy;
            assign rs_issue_allowed[io_lane]=!branch_busy_domains[0] || older_preview;
            assign rs_issue_ready[io_lane] = rs_issue_allowed[io_lane] &&'''
    # Avoid a chained part select: use the original registered branch tag view.
    replacement = replacement.replace(
        'recovery_tag_views[0 +: TAG_WIDTH][3 +: ROB_SLOT_WIDTH]',
        'recovery_tag_views[3 +: ROB_SLOT_WIDTH]')
    text = once(text, start, replacement)
    text = once(text, 'wire [BE_WIDTH-1:0] mdu_candidates=rs_issue_valid & rs_issue_is_mdu;',
                'wire [BE_WIDTH-1:0] mdu_candidates=rs_issue_valid & rs_issue_is_mdu & rs_issue_allowed;')
    text = once(text, 'assign mdu_issue_valid = (|mdu_select) && !branch_busy_domains[0];',
                'assign mdu_issue_valid = (|mdu_select);')
    text = once(text, '.issue_valid_i(!branch_busy_domains[2] &&',
                '.issue_valid_i(rs_issue_allowed[alu_lane] &&')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer EARLY_FRONT_REDIRECT = 0,',
                '    parameter integer EARLY_FRONT_REDIRECT = 0,\n    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 0,')
    text = once(text, '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT),',
                '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT), .RECOVERY_PREVIEW_OLDER_ISSUE(RECOVERY_PREVIEW_OLDER_ISSUE),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer EARLY_FRONT_REDIRECT = 1,',
                '    parameter integer EARLY_FRONT_REDIRECT = 1,\n    parameter integer RECOVERY_PREVIEW_OLDER_ISSUE = 1,')
    text = once(text, '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT),',
                '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT), .RECOVERY_PREVIEW_OLDER_ISSUE(RECOVERY_PREVIEW_OLDER_ISSUE),')
    changes[name] = text
    for name in parent['source_sha256']:
        target = TARGET / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, target)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
                  parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
                  changed_from_parent_files=list(changes),
                  source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
                  preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], RECOVERY_PREVIEW_OLDER_ISSUE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], recovery_preview_strict_older_issue=True,
                                   recovery_apply_issue_still_blocked=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Permit selected strict-older ALU/MDU RS rows on the registered pending-branch preview edge only. Keep descriptor-apply issue blocked to preserve RS flush/issue priority and eliminate duplicate acceptance. No state or arithmetic/pipeline/recovery descriptor changes.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a36_three_case_profile_sha256=sha(PROFILE),
        branch_pending_cycles={r['name']: r['observations']['branch_pending'] for r in profile['results']},
        preview_older_issue_gain_unmeasured=True, preview_older_issue_new_ff_bits=0)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREVIEW_STRICT_OLDER_ISSUE_UNTESTED', candidate=str(TARGET),
                 candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
                 added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
                 tests_started=False, adopted=False,
                 source_arguments=[
                     'A36 has exactly two branch_pending samples per rising event in all three observed cases. The preview edge can retain useful older execution; raw ready-RS counts include younger rows and are only an upper bound, not a predicted speedup.',
                     'An allowed pending-phase instruction is a valid selected RS row with valid ROB tag, circular age below both the registered pending branch and current ROB occupancy. RS allocation/kill ownership remains the original full-generation path; no new source can inject a stale tag.',
                     'The branch is already accepted with full-generation liveness before pending is set. rob_recovery_preview validates that saved branch, and no rename/dispatch allocation is enabled during pending. No late current ALU branch-resolution signal enters the new gate.',
                     'Only preview with descriptor_valid=0 is enabled. At descriptor apply, RS flush ignores normal issue-release; accepting an older instruction there without changing that priority would issue it twice. Apply remains blocked.',
                     'Existing selective ALU/MDU result recovery retains strict-older results after preview issue. An older mispredicting branch result waits for the existing pending queue to become free, so redirect serialization is unchanged.',
                     'MDU candidate selection, ALU issue-valid, and RS issue-ready use the same eligibility. Their handshakes cannot disagree; no integer or MDU operation is silently removed from RS.',
                     'Optional mode is disabled for ISSUE_PIPELINE!=0 or LOCAL_EXEC_RECOVERY=0, preserving those configurations. Parameter zero preserves the original globally blocked recovery behavior.',
                     'No HDL/lint/simulation/synthesis/STA/unit tests. Source/hash checks are preparation evidence only; final meaningful coverage needs ROB wrap, strict older and younger M/ALU, backpressure, nested redirects, and duplicate-issue detection.'
                 ])
    write(BASE / 'A39_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'added_ff_bits', 'tests_started')})


if __name__ == '__main__':
    main()
