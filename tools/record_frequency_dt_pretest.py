"""Record the frozen DT source/report identity; do not start measurement."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=json.loads(active_path.read_text(encoding='utf-8'))
    run=Path('F:/CPU2026CourseRuns/architecture_DT_20261005')
    candidate=Path('F:/CPU2026Candidates/frequency_research_20261003/DT_completion_local_prf_enable')
    backup=Path('F:/CPU2026Candidates/pre_DT_worktree_20261005/backup.json')
    prior=json.loads(backup.read_text(encoding='utf-8'))['previous_identity']
    frozen_path=run/'source_manifest.json'
    frozen=json.loads(frozen_path.read_text(encoding='utf-8'))
    review_path=Path('F:/CPU2026Proofs/DT_source_review_20261005/source_review.json')
    review=json.loads(review_path.read_text(encoding='utf-8'))
    report=root/'reports/frequency_batch_DT_pretest_2026-10-05.md'
    assert Path(active['candidate'])==candidate and Path(active['frozen_run'])==run
    assert active['tests_started'] is False
    assert sha(frozen_path)==active['frozen_manifest_sha256']
    assert sha(candidate/'candidate.json')==frozen['candidate_manifest_sha256']
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    config=json.loads((run/'course_windows_config.json').read_text(encoding='utf-8'))
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert frozen['parameter_overrides']==prior['parameter_overrides']
    for n in ('result','native_build','native_ipc','dispatch_identity.json','driver_stdout.log','driver_stderr.log'):
        assert not (run/n).exists(),n
    compact_keys=('frozen_run','status','current_measured_fmax_mhz','current_measured_ipc',
                  'current_measured_area_um2','measured_metrics_report','current_correctness_status',
                  'current_correctness_suite_passed','current_correctness_passed','current_correctness_failed',
                  'current_correctness_failed_cases','completed_ipc_report','directed_result_report',
                  'limited_directed_cases_passed','limited_directed_checks','completed_build_identity',
                  'measurement_report')
    previous={k:prior.get(k) for k in compact_keys}
    previous.update(source_manifest_sha256=prior['frozen_manifest_sha256'],measurement_process_id=None)
    active['previous_measurement']=previous
    active['last_observed_measurement']=prior['last_observed_measurement']
    active['previous_implementation_identity']={
        'candidate':prior['candidate'],'frozen_run':prior['frozen_run'],
        'source_manifest_sha256':prior['frozen_manifest_sha256'],'tests_started':True}
    for key in ('completed_build_identity','directed_result_report','limited_directed_cases_passed',
                'limited_directed_checks','completed_ipc_report','measurement_report','measurement_observation',
                'measurement_progress_recorded_at','measurement_started_at'):
        active.pop(key,None)
    active.update(status='WORKTREE_IMPLEMENTED_UNTESTED_PRETEST_REPORTED',tests_started=False,
        measurement_process_id=None,current_measured_fmax_mhz=None,current_measured_ipc=None,
        current_measured_area_um2=None,measured_metrics_report=None,measured_frequency_belongs_to=None,
        current_correctness_status='UNTESTED',current_correctness_suite_passed=None,
        current_correctness_passed=None,current_correctness_failed=None,current_correctness_failed_cases=[],
        last_complete_course_standard_result=prior['last_complete_course_standard_result'],
        implementation_report=str(report),pretest_report=str(report),pretest_report_sha256=sha(report),
        ongoing_research_report=str(report),
        research_status='FIVE_COMBINATIONAL_GROUPS_IMPLEMENTED_SOURCE_REVIEWED_NO_HDL_TEST',
        test_start_condition='Deliver DT pretest report before one timing-only native batch. No CPU build or simulation until material frequency gain is observed and area is reviewed.',
        source_identity_review={**review,'active_input_files':len(active['source_sha256']),
                               'frozen_input_files':len(frozen['snapshot_sha256']),
                               'implemented_groups':5,'parameter_override_count':len(frozen['parameter_overrides']),
                               'review_report':str(review_path),'review_sha256':sha(review_path)},
        measurement_plan={'initial_phase':'TIMING_ONLY','cpu_build_started':False,'simulation_started':False,
            'official_course_synth_runs_planned':1,'intermediate_candidate_tests_planned':0,
            'material_frequency_gain_working_threshold_mhz':350,
            'frequency_reference_mhz':prior['current_measured_fmax_mhz'],
            'later_ipc_cases_planned_only_after_gain':6,
            'reuse_exact_timing_report':True,'environment':'WINDOWS_NATIVE','wsl_allowed':False,
            'area_reference_um2':46309.693490,'original_plus_10_percent_area_um2':50940.662839,
            'original_minus_10_percent_ipc':0.882115146585,
            'threshold_does_not_replace_original_requirements':True},
        last_verified_frequency_requirement=prior['frequency_requirement_verified'],
        frequency_requirement_verified={'status':'CURRENT_SOURCE_UNMEASURED',
            'source_manifest_sha256':sha(frozen_path),'previous_verified_report':prior['measurement_report']},
        completion_audit={'observed_at':datetime.now(timezone.utc).isoformat(),
            'frequency_300_met':None,'area_within_10_percent':None,'ipc_within_10_percent':None,
            'tier3_area_met':None,'tier3_ipc_met':None,'full_correctness_proven':False,
            'overall_goal_complete':False,
            'remaining':'DT unmeasured. Previous DM1 frequency met 300 MHz, but original area/IPC ranges, Tier3 area/IPC and full correctness were unmet.'},
        orchestration_source_sha256={n:sha(root/n) for n in
            ('tools/run_course_standard_windows.py','tools/start_frequency_course_background.py')})
    alternatives=list(prior.get('prepared_unmeasured_alternatives',[]))
    for n in ('DP_store_alloc_simm12','DQ_prf_compare_before_completion',
              'DR_late_lsq_completion_grants','DS_direct_prf_operand_bypass'):
        p=candidate.parent/n
        if not any(Path(x['candidate'])==p for x in alternatives):
            alternatives.append({'candidate':str(p),'manifest_sha256':sha(p/'candidate.json'),
                'tests_started':False,'adopted':False,'role':'Archived intermediate source candidate; not scheduled for measurement'})
    active['prepared_unmeasured_alternatives']=alternatives
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (run/'pretest_source_identity.json').write_text(json.dumps({
        'status':'FROZEN_UNTESTED_PRETEST_REPORTED','source_manifest_sha256':sha(frozen_path),
        'candidate_manifest_sha256':sha(candidate/'candidate.json'),'active_source_count':len(active['source_sha256']),
        'frozen_source_count':len(frozen['snapshot_sha256']),'pretest_report':str(report),
        'pretest_report_sha256':sha(report),'review_report':str(review_path),
        'tests_started':False,'measurement_plan':active['measurement_plan']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':active['status'],'frozen_manifest_sha256':sha(frozen_path),
        'pretest_report':str(report),'tests_started':False,'current_measured_fmax_mhz':None,
        'previous_measured_fmax_mhz':prior['current_measured_fmax_mhz']},ensure_ascii=False))


if __name__=='__main__':
    main()
