"""Record completion once the adopted current state has independently passed audit."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write

OUT=ROOT/'build/cpu2026/er1_a109_final_completion_20261006.json'
STATE=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not OUT.exists(), 'Preserve first successful final completion evidence'
    audit_path=ROOT/'build/cpu2026/er1_a109_independent_current_state_audit_20261006.json'
    active_path=ROOT/'build/cpu2026/active_er1_a109_implementation_20261006.json'
    audit,active=read(audit_path),read(active_path)
    assert audit['status']=='CURRENT_ADOPTED_A109_FULL_OBJECTIVE_INDEPENDENTLY_VERIFIED'
    required=['same_measured_source_and_executable_verified','official_six_perf_verified',
        'official_19_correctness_verified','official_19_verified_across_two_attempts',
        'original18_pass1_pi_timeout_preserved','frozen_four_boundary_verified',
        'architecture_and_parameter_source_review_bound_to_current_files',
        'report_and_historical_parameter_tradeoff_deliverables_preserved']
    assert all(audit[key] is True for key in required)
    for name,digest in audit['evidence_sha256'].items():
        assert sha(name)==digest,name
    sources=active['source_sha256']
    assert len(sources)==41
    for name,digest in sources.items():
        assert sha(ROOT/name)==digest,name
    assert audit['ipc']>=1.1 and audit['fmax_mhz']>300 and audit['area_um2']<=36000
    report=ROOT/'reports/ER1_A109_Tier3_verified_2026-10-06.md'
    result=dict(status='ER1_A109_FULL_OBJECTIVE_ACHIEVED_CURRENT_STATE_VERIFIED',
        completed_at=datetime.now(timezone.utc).isoformat(),ipc=audit['ipc'],fmax_mhz=audit['fmax_mhz'],
        total_area_including_sram_um2=audit['area_um2'],main_source_files=41,backup_source_files=40,
        correctness_unique_official_cases=19,boundary_cases=4,original18_pass1_timeout_preserved=True,
        pi_followup_cycles=audit['pi_followup_cycles'],pi_followup_max_cycles=48000000,
        independent_current_state_audit_sha256=sha(audit_path),main_source_adopted=True,
        new_builds_or_hardware_tests_run=False,goal_complete=True,
        evidence_sha256={str(path):sha(path) for path in [Path(__file__),audit_path,active_path,report]})
    write(OUT,result)
    state=read(STATE)
    state.update(status=result['status'],goal_complete=True,candidates_adopted=True,
        final_completion_evidence=str(OUT),final_completion_evidence_sha256=sha(OUT),
        independent_current_state_audit=str(audit_path),independent_current_state_audit_sha256=sha(audit_path),
        independent_current_state_audit_executed=True,combined_adoption_executed=True,
        pi_followup_completed=True,pi_budget_followup_process_alive=False,
        last_goal_turn_classification='PROGRESS_FULL_OBJECTIVE_VERIFIED_CURRENT_A109_SOURCE_ADOPTED',
        next_work='Report current verified A109 metrics and both correctness attempts; root must inspect completion evidence and mark the active thread goal complete.')
    write(STATE,state)
    print({key:value for key,value in result.items() if key!='evidence_sha256'})


if __name__=='__main__':
    main()
