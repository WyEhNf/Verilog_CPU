"""Reconcile frozen source progress; no build, simulation, synthesis or STA."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write

ROOT=Path('E:/Verilog_cpu')
BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF=ROOT/'build/cpu2026/er1_a64_a67_source_progress_20261006.json'
AUDIT=ROOT/'build/cpu2026/er1_recovery_and_redirect_source_audit_20261006.json'


def main():
    assert not PROOF.exists() and not AUDIT.exists()
    state=read(STATE)
    assert state['current_source_candidate']=='A63_rs_predecode_issue_cancel'
    assert state['active_measurement_candidate'] is None
    assert state['active_measurement_process_ids']==[]
    before=sha(STATE)
    old_progress=Path(state['last_source_progress_proof'])
    assert sha(old_progress)==state['last_source_progress_proof_sha256']
    old=read(old_progress)
    active=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active)==old['main_active_manifest_sha256']
    main_record=read(active)
    for name,digest in main_record['source_sha256'].items():
        assert sha(ROOT/name)==digest,name
    measured=read(ROOT/'build/cpu2026/er1_a55r2_complete_result_20261005.json')
    for name,expected in measured['artifacts_sha256'].items():
        assert sha(Path(name))==expected,name
    metrics=measured['metrics']
    assert state['best_measured_combined_candidate']==metrics['candidate']
    assert all(state['best_measured_combined_result'][k]==metrics[k] for k in ['ipc','fmax_mhz','area_um2','candidate_sha256','source_manifest_sha256'])
    specs=[
        ('A64_ras_repeat_compression','prepare_er1_ras_repeat_compression.py','0b3c3101eb6a6321dc1781894ed309120e4bf0d3f3de26740d52766152147247'),
        ('A65_direct_recovery_apply','prepare_er1_direct_recovery_apply.py','4681c6e9f2b42a7dac4b7467eae85c88f1af2dd682b6934f44577b0f26fd436a'),
        ('A66_rat_suffix_branch_mapping','prepare_er1_rat_suffix_branch_mapping.py','7d7d89af8c393c70967e736c5c76d8ad1738c2bd245dabfae295087302fe9014'),
        ('A67_rob_unique_reclaim_count','prepare_er1_rob_unique_reclaim_count.py','b9edf22df78400dbf02c652ac3d73973e078a1c8c82414c92f34bf28e9952a1d'),
    ]
    candidates=[]
    for candidate,script,expected in specs:
        root=BASE/candidate
        manifest=read(root/'candidate.json')
        assert sha(root/'candidate.json')==expected
        assert sha(Path(manifest['parent_candidate'])/'candidate.json')==manifest['parent_candidate_sha256']
        assert sha(ROOT/'tools'/script)==manifest['preparation_script_sha256']
        for name,digest in manifest['source_sha256'].items():
            assert sha(root/name)==digest,name
        review=BASE/(candidate.split('_',1)[0]+'_source_review.json')
        r=read(review)
        assert r['candidate_sha256']==expected and not r['tests_started'] and not r['adopted']
        assert not manifest['tests_started'] and not manifest['adopted']
        candidates.append(dict(candidate=candidate,source_root=str(root),candidate_sha256=expected,
            source_file_count=len(manifest['source_sha256']),source_hashes_valid=True,parent_hash_valid=True,
            preparation_script_sha256=sha(ROOT/'tools'/script),review=str(review),review_sha256=sha(review),
            changed_files=manifest['changed_from_parent_files'],tests_started=False,adopted=False))
    last=BASE/specs[-1][0]
    contract_names=['rtl/cpu_core.v','rtl/frontend/rv32_fetch_frontend.v','rtl/cache/rv32_icache_nonblocking.v',
        'rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_rob.v','rtl/rv32_rename_unit.v',
        'rtl/backend/rv32_rat_recovery.v','rtl/backend/rv32_lsq.v','rtl/rv32i_alu.v',
        'rtl/backend/rv32m_mdu_reservation_station.v']
    audit=dict(status='SOURCE_OWNERSHIP_AND_RECOVERY_AUDIT_NO_HDL_EXECUTION',recorded_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(last),candidate_sha256=sha(last/'candidate.json'),source_sha256={n:sha(last/n) for n in contract_names},
        redirected_same_edge_fetch_implemented=False,
        redirected_fetch_findings=[
            'Current frontend request validity can offer the old PC/epoch on a redirect edge when no request is pending; redirect discards its ownership. A same-edge redirected request would need redirect PC/epoch selection, pending ownership from the actual new fire, and effective cache epoch on that edge. Merely selecting the request PC is incomplete.',
            'The filter fast hit/miss ownership, query-queue stale eviction, MSHR reuse and external transaction generations must agree on the effective epoch. Registered SRAM hit data and held responses have separate ownership. Existing AXI IDs and stale-response guards cannot be relaxed.',
            'Hot-hit target fetching one edge earlier can overlap existing recovery/rename barriers, so request latency is not proof of a useful IPC cycle saved. Even after A65 direct apply, the registered free pool clears on restore and refills afterward. No same-edge request feature or saved-cycle claim is made.'
        ],
        predictor_findings=[
            'Direction rows are2-bit counters plus a trained bit, not3-bit saturation counters. Deleting the third bit changes cold BTFNT policy and is not an equivalent area optimization.',
            'Static chooser64 PC collisions exist but are sparse: one pair each in median/qsort, two in rsort, three in towers, none in multiply/vvadd. Static PC collisions alone do not prove dynamic preference interference or a large IPC gain.',
            'The backend already wakes RS dependents from held live ALU/MDU/LSQ producers independently of completion FIFO ready, with a separate early load-return column. Adding that mechanism again would not produce progress.'
        ],
        direct_apply_contracts=[
            'Qualified branch capture remains registered. Direct apply reuses existing ROB STAGED_RECOVERY0 at the next pending edge; preview live/GEN/age qualification does not depend on the apply input.',
            'Current pre-edge head/occupancy, suffix RAT undo, reclaim bitmap/count, RS mask, held execution cancellation, LSQ response guards and completion kills belong to the same apply. Allocation/rename/commit are excluded on that edge.',
            'Branch result/link write and GHR repair remain the original captured event. Frontend receives early epoch+1 at capture; ROB increments once at qualified apply, now one edge earlier. No second redirect is emitted at preview.',
            'Pointer/GEN authority and full RV32IM execution remain intact. A66 relies on the accepted rename old-map chain; A67 relies on unique live physical destinations. These contracts require coherent integration coverage before adoption.'
        ],
        risks=['Direct RAT rollback/data and full ROB live qualification now feed restore/control in one cycle.',
            'Same-edge older completion, delayed LSQ response, D-stage survivor and held MDU state require meaningful correctness coverage.',
            'Removing a preview-only edge also removes its older request/issue opportunity; net useful-cycle improvement is unmeasured.',
            'A64 compression still has wrong-path RAS pollution and BTB-assisted underflow can limit its IPC gain.'],
        new_hdl_execution=False,new_lint=False,new_simulation=False,new_synthesis=False,new_sta=False,new_unit_tests=False)
    write(AUDIT,audit)
    classification='PROGRESS_A64_A67_FROZEN_DIRECT_RECOVERY_APPLY_AND_SHORTER_ROLLBACK_PATHS_NO_NEW_TESTS'
    proof=dict(status='SOURCE_A64_A65_A66_A67_PROGRESS_NO_NEW_HDL_EXECUTION',recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='NO_PROGRESS_STATUS_ONLY_REVALIDATED_BY_RESULT_HASHES',
        this_goal_turn_classification=classification,previous_state_sha256=before,
        previous_source_progress_proof=str(old_progress),previous_source_progress_proof_sha256=sha(old_progress),
        candidates=candidates,pending_candidate=specs[-1][0],pending_candidate_metrics=dict(ipc=None,fmax_mhz=None,area_um2=None),
        measured_incumbent=metrics,new_hdl_or_lint_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        audit=str(AUDIT),audit_sha256=sha(AUDIT),
        source_cost=dict(ras_ff_bits_added=24,backend_descriptor_ff_bits_removed=274,
            net_logical_ff_bits_change_vs_a63=-250,rob_saved_descriptor_bits_not_consumed_in_direct_mode=43,
            new_sram_bits=0,new_ordinary_pipeline_edges=0,recovery_wait_edges_removed=1),
        measured_gain_claimed=False,area_frequency_ipc_unknown=True,
        main_eu_source_unchanged=True,main_active_manifest_sha256=sha(active),main_source_file_count=len(main_record['source_sha256']),
        adopted=False,goal_complete=False,
        next_work=[
            'Review direct recovery control fanout and RAT/reclaim/RS/LSQ/held-result ownership as a coherent batch. Resolve known source concerns before HDL measurement.',
            'Assess remaining IPC opportunity, especially wrong-path RAS repair and recovery/rename overlap. Do not infer IPC1.1 from one fewer recovery edge.',
            'Before a materially justified native pinned course batch, report exact frozen source, changes, expected structural benefit, area/timing risks and meaningful correctness/performance scope; no per-edit tests or WSL.'
        ])
    write(PROOF,proof)
    state.update(status='A55R2_COMPLETE_A67_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=specs[-1][0],current_source_candidate=specs[-1][0],
        pending_source_candidate=str(last),pending_source_candidate_sha256=sha(last/'candidate.json'),
        candidate_manifest_sha256=sha(last/'candidate.json'),candidate_tests_started=False,pending_source_candidate_tests_started=False,
        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,candidate_metrics_belong_to=specs[-1][0],
        candidate_correctness_passed=None,candidate_correctness_failed=None,candidate_correctness_finished=False,candidate_correctness_not_run=True,
        candidates_adopted=False,goal_complete=False,prepared_run=None,prepared_source_manifest_sha256=None,
        candidate_pretest_report=None,candidate_pretest_report_sha256=None,
        active_measurement_candidate=None,active_measurement_process_ids=[],measurement_process_alive=False,
        previous_goal_turn_classification='NO_PROGRESS_STATUS_ONLY_REVALIDATED_BY_RESULT_HASHES',last_goal_turn_classification=classification,
        previous_source_progress_proof=str(old_progress),previous_source_progress_proof_sha256=sha(old_progress),
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),next_work=proof['next_work'])
    write(STATE,state)
    print(dict(status=proof['status'],pending_candidate=proof['pending_candidate'],
        candidates_verified=len(candidates),main_source_files_unchanged=proof['main_source_file_count'],
        new_tests_started=False,goal_complete=False,proof=str(PROOF),proof_sha256=sha(PROOF)))


if __name__=='__main__':
    main()
