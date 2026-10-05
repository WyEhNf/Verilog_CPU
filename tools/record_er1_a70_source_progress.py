"""Record independent source work while the original A69 job stays active."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a69_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a70_source_progress_20261006.json'
NAME = 'A70_recovery_rob_credit'


def main():
    assert not PROOF.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A69_same_edge_redirect_fetch'
    assert state['active_measurement_candidate'] == 'A69_same_edge_redirect_fetch'
    plan = check()
    dispatch = read(RUN / 'dispatch_identity.json')
    assert dispatch['process_id'] == state['measurement_process_id'] == 44708
    assert dispatch['source_manifest_sha256'] == state['active_measurement_source_manifest_sha256']
    assert sha(RUN / 'dispatch_identity.json') == state['measurement_dispatch_sha256']
    alive = live(dispatch['process_id'])
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    active = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous)['main_active_manifest_sha256']
    main = read(active)
    for file, digest in main['source_sha256'].items():
        assert sha(ROOT / file) == digest, file
    root = BASE / NAME
    manifest = read(root / 'candidate.json')
    assert sha(root / 'candidate.json') == '20883172065dddb7854f8004a9ce255d6718749a73ed87e5157c4d9407f621dd'
    assert sha(Path(manifest['parent_candidate']) / 'candidate.json') == manifest['parent_candidate_sha256']
    script = ROOT / 'tools/prepare_er1_recovery_rob_credit.py'
    assert sha(script) == manifest['preparation_script_sha256']
    for file, digest in manifest['source_sha256'].items():
        assert sha(root / file) == digest, file
    review = BASE / 'A70_source_review.json'
    assert read(review)['candidate_sha256'] == sha(root / 'candidate.json')
    classification = 'PROGRESS_A70_EXACT_POST_RECOVERY_ROB_CREDIT_NO_NEW_HDL_JOB'
    proof = dict(status='SOURCE_A70_PROGRESS_WITH_ORIGINAL_A69_MEASUREMENT',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_audit='VERIFIED_WAIT_ORIGINAL_A69_PID44708_OBSERVED_LIVE_2026_10_05T16_52_24Z',
        this_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        candidate=NAME, source_root=str(root), candidate_sha256=sha(root / 'candidate.json'),
        source_file_count=len(manifest['source_sha256']), source_hashes_valid=True,
        parent_candidate_sha256=manifest['parent_candidate_sha256'], preparation_script_sha256=sha(script),
        review=str(review), review_sha256=sha(review), changed_files=manifest['changed_from_parent_files'],
        candidate_metrics=dict(ipc=None, fmax_mhz=None, area_um2=None), candidate_tests_started=False,
        source_cost=dict(new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0),
        new_hdl_or_lint_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        active_measurement=dict(candidate=state['active_measurement_candidate'], run=str(RUN),
            original_process_id=dispatch['process_id'], original_process_live_now=alive,
            source_manifest_sha256=plan['source_manifest_sha256'],
            dispatch_sha256=sha(RUN / 'dispatch_identity.json'), phase=read(RUN / 'serial_phase_identity.json')['status']),
        measured_incumbent=state['best_measured_combined_result'],
        structural_gain='Eliminate old-occupancy credit lag after qualified direct recovery; actual allocation guards unchanged. Opportunity depends on old credit, target response, retained physical pool and dispatch readiness.',
        speculative_gain_not_measured=True, main_eu_source_unchanged=True,
        main_active_manifest_sha256=sha(active), main_source_file_count=len(main['source_sha256']),
        adopted=False, goal_complete=False)
    write(PROOF, proof)
    state.update(status='A69_MEASUREMENT_ACTIVE_A70_SOURCE_PENDING_UNTESTED',
        current_prepared_candidate=NAME, current_source_candidate=NAME,
        pending_source_candidate=str(root), pending_source_candidate_sha256=sha(root / 'candidate.json'),
        candidate_manifest_sha256=sha(root / 'candidate.json'),
        candidate_tests_started=False, pending_source_candidate_tests_started=False,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        candidate_metrics_belong_to=NAME, candidate_correctness_passed=None,
        candidate_correctness_failed=None, candidate_correctness_finished=False, candidate_correctness_not_run=True,
        candidates_adopted=False, goal_complete=False, prepared_run=None,
        prepared_source_manifest_sha256=None, candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        previous_goal_turn_classification=proof['previous_goal_turn_audit'], last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF), last_background_progress_sha256=sha(PROOF),
        measurement_process_alive=alive,
        next_work=['Observe the original A69 serial measurement without restarting it.',
            'Continue independent source work; evaluate further IPC opportunities and frequency risks before another batch.',
            'Bind new metrics to their measured source; full correctness and relevant RV32IM/recovery/parameter coverage before adoption.'])
    write(STATE, state)
    print(dict(status=proof['status'], candidate=NAME, proof=str(PROOF), proof_sha256=sha(PROOF),
        active_measurement_original_pid=dispatch['process_id'], original_pid_live_now=alive, new_tests_started=False))


if __name__ == '__main__':
    main()
