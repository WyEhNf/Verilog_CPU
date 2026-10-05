"""Record a reviewed frozen candidate's concrete scope before any test."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('E:/Verilog_cpu')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--scope',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    ap=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(ap)
    candidate=Path(active['candidate'])
    run=Path(active['frozen_run'])
    prior=read(active['previous_identity_backup'])['previous_identity']
    cm,frozen,review=read(candidate/'candidate.json'),read(run/'source_manifest.json'),read(args.review)
    assert active['status']=='WORKTREE_IMPLEMENTED_UNTESTED' and not active['tests_started']
    assert Path(review['candidate'])==candidate
    assert sha(candidate/'candidate.json')==review['candidate_manifest_sha256']==frozen['candidate_manifest_sha256']
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert frozen['parameter_overrides']==prior['parameter_overrides']==cm['parameter_overrides']
    assert review['source_groups']==len(cm['implemented_groups'])
    assert review['new_declared_state_bits']==cm['new_declared_sequential_state_bits']
    assert not review['new_test_started'] and not review['adopted']
    assert prior['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert prior['measurement_process_id'] is None
    config=read(run/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    for n,h in active['source_sha256'].items():
        assert sha(ROOT/n)==h,n
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    for n in ('result','native_build','native_ipc','dispatch_identity.json','driver_stdout.log','driver_stderr.log'):
        assert not (run/n).exists(),n
    assert args.scope.is_file() and not args.report.exists()
    text=args.scope.read_text(encoding='utf-8')
    text+=f'''\n\n## 最终冻结与调度身份\n\n- Candidate：`{candidate}`\n- Candidate manifest SHA256：`{sha(candidate/'candidate.json')}`\n- Frozen run：`{run}`\n- Frozen manifest SHA256：`{sha(run/'source_manifest.json')}`\n- 源审查：`{args.review.resolve()}`\n- 源审查 SHA256：`{sha(args.review)}`\n- 范围文件 SHA256：`{sha(args.scope)}`\n- 当前主工作区输入：{len(active['source_sha256'])}\n- 冻结输入：{len(frozen['snapshot_sha256'])}\n- 后台调用：`tools/start_frequency_course_background.py --run {run.as_posix()} --timing-only`\n\n上述身份只执行一次timing-only，在对话汇报后才能调度。该报告落盘不调用任何测量工具。\n'''
    args.report.write_text(text,encoding='utf-8')
    for key in ('measurement_report','current_timing_result_report','completed_timing_only_report',
        'measurement_observation','measurement_progress_recorded_at','measurement_started_at',
        'completed_build_identity','directed_result_report','completed_ipc_report',
        'limited_directed_checks','limited_directed_cases_passed'):
        active.pop(key,None)
    if 'post_dispatch_source_research' in active:
        active['last_background_source_research']=active.pop('post_dispatch_source_research')
    now=datetime.now(timezone.utc).isoformat()
    active.update(status='WORKTREE_IMPLEMENTED_UNTESTED_PRETEST_REPORTED',tests_started=False,
        measurement_process_id=None,current_measured_fmax_mhz=None,current_measured_ipc=None,current_measured_area_um2=None,
        measured_metrics_report=None,measured_frequency_belongs_to=None,
        implementation_report=str(args.report.resolve()),pretest_report=str(args.report.resolve()),
        pretest_report_sha256=sha(args.report),ongoing_research_report=str(args.report.resolve()),
        research_status='FINAL_REVIEWED_COMBINATION_PRETEST_REPORTED',
        source_identity_review={**review,'review_path':str(args.review.resolve()),'review_sha256':sha(args.review)},
        pending_source_research=[],source_research_decision=review['architecture_triage'][-1],
        test_start_condition='Deliver this exact frozen complete pretest report in conversation before one native background timing-only job. No intermediate or program tests.',
        frequency_requirement_verified=dict(status='CURRENT_SOURCE_UNMEASURED',
            source_manifest_sha256=active['frozen_manifest_sha256'],
            previous_verified_report=active['last_verified_frequency_requirement']['report']),
        completion_audit=dict(observed_at=now,frequency_300_met=None,area_within_10_percent=None,
            ipc_within_10_percent=None,tier3_area_met=None,tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='Current new frozen source unmeasured. Previous timing-only frequency/area preserved; IPC/correctness and full Tier3 remain unverified or unmet.'))
    active['measurement_plan'].update(ready_for_dispatch=True,initial_phase='TIMING_ONLY',
        cpu_build_started=False,simulation_started=False,official_course_synth_runs_planned=1,
        intermediate_candidate_tests_planned=0,measurement_scope_finalized=True,
        implemented_source_groups=len(cm['implemented_groups']),frequency_reference_mhz=prior['current_measured_fmax_mhz'])
    active['orchestration_source_sha256']={n:sha(ROOT/n) for n in ('tools/run_course_standard_windows.py',
        'tools/start_frequency_course_background.py','tools/record_frequency_measurement_progress.py')}
    for item in active['prepared_unmeasured_alternatives']:
        if Path(item['candidate'])==candidate:
            item.update(adopted=True,tests_started=False,role='Current frozen complete combination; components not separately measured')
    ap.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=active['status'],report=str(args.report.resolve()),
        pretest_report_sha256=active['pretest_report_sha256'],frozen_manifest_sha256=active['frozen_manifest_sha256'],
        source_groups=len(cm['implemented_groups']),tests_started=False,ready_for_one_timing_only=True)))


if __name__=='__main__':
    main()
