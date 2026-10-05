"""Record coherent pool/redirect source progress; no HDL tool execution."""
from datetime import datetime,timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT,read,sha,write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF=ROOT/'build/cpu2026/er1_a68_a69_source_progress_20261006.json'


def main():
    assert not PROOF.exists()
    state=read(STATE)
    assert state['current_source_candidate']=='A67_rob_unique_reclaim_count'
    assert state['active_measurement_candidate'] is None and not state['active_measurement_process_ids']
    previous=Path(state['last_source_progress_proof'])
    assert sha(previous)==state['last_source_progress_proof_sha256']
    old=read(previous)
    active=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active)==old['main_active_manifest_sha256']
    main_record=read(active)
    for name,digest in main_record['source_sha256'].items():assert sha(ROOT/name)==digest,name
    candidates=[]
    for name,script,digest in [
        ('A68_retain_free_pool_restore','prepare_er1_retain_free_pool_restore.py','21e4279198c60bdccecccfa89b5b94a19988693a4b914689f1815eacffbb1fec'),
        ('A69_same_edge_redirect_fetch','prepare_er1_same_edge_redirect_fetch.py','bf0166c1acfedcb3c8631268fd8f440f65a59cc2a34213f81dbdec4c48cae074'),
    ]:
        root=BASE/name;manifest=read(root/'candidate.json')
        assert sha(root/'candidate.json')==digest
        assert sha(Path(manifest['parent_candidate'])/'candidate.json')==manifest['parent_candidate_sha256']
        assert sha(ROOT/'tools'/script)==manifest['preparation_script_sha256']
        for file,expected in manifest['source_sha256'].items():assert sha(root/file)==expected,file
        review=BASE/(name.split('_',1)[0]+'_source_review.json')
        assert read(review)['candidate_sha256']==digest
        candidates.append(dict(candidate=name,source_root=str(root),candidate_sha256=digest,
            source_file_count=len(manifest['source_sha256']),source_hashes_valid=True,parent_hash_valid=True,
            preparation_script_sha256=sha(ROOT/'tools'/script),review=str(review),review_sha256=sha(review),
            changed_files=manifest['changed_from_parent_files'],tests_started=False,adopted=False))
    classification='PROGRESS_A68_A69_PRESERVE_FREE_POOL_AND_COHERENT_REDIRECT_EDGE_FETCH_NO_NEW_TESTS'
    proof=dict(status='SOURCE_A68_A69_PROGRESS_NO_NEW_HDL_EXECUTION',recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification=state['last_goal_turn_classification'],this_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        candidates=candidates,pending_candidate=candidates[-1]['candidate'],
        pending_candidate_metrics=dict(ipc=None,fmax_mhz=None,area_um2=None),measured_incumbent=state['best_measured_combined_result'],
        new_hdl_or_lint_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        source_cost=dict(new_ff_bits=0,new_sram_bits=0,new_ordinary_pipeline_edges=0,new_recovery_priority_encoder=False),
        structural_gain='Keep already-free pool candidates through apply, and offer new PC/epoch to the registered-response ICache on the same redirect edge. This can expose earlier target rename together with direct recovery apply; readiness/credits/pool/miss conditions still apply.',
        speculative_gain_not_measured=True,main_eu_source_unchanged=True,main_active_manifest_sha256=sha(active),
        main_source_file_count=len(main_record['source_sha256']),adopted=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='A55R2_COMPLETE_A69_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=candidates[-1]['candidate'],current_source_candidate=candidates[-1]['candidate'],
        pending_source_candidate=candidates[-1]['source_root'],pending_source_candidate_sha256=candidates[-1]['candidate_sha256'],
        candidate_manifest_sha256=candidates[-1]['candidate_sha256'],candidate_tests_started=False,pending_source_candidate_tests_started=False,
        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,candidate_metrics_belong_to=candidates[-1]['candidate'],
        candidate_correctness_passed=None,candidate_correctness_failed=None,candidate_correctness_finished=False,candidate_correctness_not_run=True,
        candidates_adopted=False,goal_complete=False,prepared_run=None,prepared_source_manifest_sha256=None,
        candidate_pretest_report=None,candidate_pretest_report_sha256=None,
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        next_work=['Review the complete A56-A69 batch and report before one native pinned course measurement.',
            'Continue independent source optimization while observing the original process without restarting.',
            'Keep metrics bound to each source; verify complete functionality before any adoption.'])
    write(STATE,state)
    print(dict(status=proof['status'],pending_candidate=proof['pending_candidate'],proof=str(PROOF),proof_sha256=sha(PROOF),new_tests_started=False))


if __name__=='__main__':main()
