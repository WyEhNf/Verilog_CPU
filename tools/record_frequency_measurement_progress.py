"""Record existing native measurement evidence; never launch EDA or simulations."""
import argparse
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
from summarize_course_frequency_native import read,sha
from wait_frequency_directed_native import live

ROOT=Path('E:/Verilog_cpu')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'


def optional_json(path):
    try:
        return read(path)
    except (FileNotFoundError,json.JSONDecodeError):
        return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    assert os.name=='nt'
    run=args.run.resolve()
    active=read(ACTIVE)
    assert Path(active['frozen_run']).resolve()==run and active['tests_started']
    manifest_sha=sha(run/'source_manifest.json')
    assert active['frozen_manifest_sha256']==manifest_sha
    frozen=read(run/'source_manifest.json')
    for name,expected in active['source_sha256'].items():
        assert sha(ROOT/name)==expected,'Worktree changed: '+name
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,'Frozen input changed: '+name
    dispatch=read(run/'dispatch_identity.json')
    assert dispatch['source_manifest_sha256']==manifest_sha
    config=read(run/'course_windows_config.json')
    identity=optional_json(run/'result/measurement_identity.json')
    if identity:
        assert identity['environment']=='WINDOWS_NATIVE'
        assert identity['source_manifest_sha256']==manifest_sha
    build=optional_json(Path(config['native_build_path'])/'build_identity.json')
    complete_build=build and build.get('status')=='COMPLETE'
    if complete_build:
        assert build['source_manifest_sha256']==manifest_sha
        assert sha(build['executable'])==build['executable_sha256']
        active['completed_build_identity']=str(Path(config['native_build_path'])/'build_identity.json')
    ipc=optional_json(run/'result/ipc.json')
    if ipc:
        assert complete_build and ipc['status']=='COMPLETE' and ipc['latency']==10
        framework=run/'source/.deps/RISC-V-CPU-2026/testcases'
        expected=sorted(p.name for p in framework.glob('perf_*') if p.is_dir())
        assert len(expected)==6 and sorted(r['name'] for r in ipc['results'])==expected
        for row in ipc['results']:
            case=framework/row['name']
            assert row['program_sha256']==sha(case/'program.data')
            assert row['metrics_sha256']==sha(case/'metrics.json')
            assert row['instructions']==read(case/'metrics.json')['dynamic_instructions']
            assert row['cycles']>0 and math.isclose(row['ipc'],row['instructions']/row['cycles'],rel_tol=1e-12)
        geomean=math.exp(sum(math.log(row['ipc']) for row in ipc['results'])/6)
        assert math.isclose(ipc['geomean_ipc'],geomean,rel_tol=1e-12)
        active.update(current_measured_ipc=geomean,completed_ipc_report=str(run/'result/ipc.json'))
    directed=optional_json(run/'directed_cases/results.json')
    if directed:
        assert complete_build and directed['source_manifest_sha256']==manifest_sha
        assert directed['executable_sha256']==build['executable_sha256']
        assert directed['cases_manifest_sha256']==sha(run/'directed_cases/cases.json')
        assert directed['build_identity_sha256']==sha(Path(config['native_build_path'])/'build_identity.json')
        assert len(directed['results'])==2
        passed=sum(row['status']=='PASS' for row in directed['results'])
        active.update(directed_result_report=str(run/'directed_cases/results.json'),
            limited_directed_cases_passed=passed,
            limited_directed_checks=sum(row['checks'] for row in directed['results']),
            current_correctness_status=('LIMITED_CASES_PASSED_FULL_SUITE_NOT_RUN' if passed==2 else
                                        'LIMITED_CASES_FAILED_FULL_SUITE_NOT_RUN'),
            current_correctness_suite_passed=None)
    report_path=run/'result/synth/opt/report.json'
    report=optional_json(report_path)
    if report:
        assert identity
        fmax=report['timing']['estimated_fmax_mhz']
        area=report['area']['area_um2']
        assert math.isfinite(fmax) and fmax>0 and math.isfinite(area) and area>0
        active.update(current_measured_fmax_mhz=fmax,current_measured_area_um2=area,
            measured_frequency_belongs_to=str(run),measured_metrics_report=str(report_path))
    result=optional_json(run/'result/result.json')
    timing_only=optional_json(run/'result/timing_only.json')
    if timing_only:
        assert dispatch.get('timing_only_requested') and report and identity
        assert timing_only['status']=='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
        assert timing_only['source_manifest_sha256']==manifest_sha
        assert timing_only['config_sha256']==sha(run/'course_windows_config.json')
        tool_root=Path(config['tools_root'])
        assert timing_only['toolchain_manifest_sha256']==sha(tool_root/'toolchain_manifest.json')
        assert timing_only['official_report_sha256']==sha(report_path)
        assert identity['status']=='TIMING_ONLY_COMPLETE'
        assert identity['timing_only_report_sha256']==sha(run/'result/timing_only.json')
        assert identity['official_report_sha256']==sha(report_path)
        assert not timing_only['cpu_build_started'] and not timing_only['simulation_started']
        assert not complete_build and not ipc and not directed and not result
        assert math.isclose(timing_only['fmax_mhz'],active['current_measured_fmax_mhz'],rel_tol=1e-12)
        assert math.isclose(timing_only['area_um2'],active['current_measured_area_um2'],rel_tol=1e-12)
        assert math.isclose(timing_only['fmax_mhz'],1000/timing_only['minimum_period_ns'],rel_tol=1e-12)
        active['completed_timing_only_report']=str(run/'result/timing_only.json')
    failure=optional_json(run/'result/failure.json')
    process_live=live(dispatch['process_id'])
    if result:
        assert result['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
        assert report and ipc and identity and identity['status']=='COMPLETE'
        assert identity['result_sha256']==sha(run/'result/result.json')
        assert identity['official_report_sha256']==sha(report_path)
        assert identity['ipc_sha256']==sha(run/'result/ipc.json')
        assert Path(result['source_manifest']).resolve()==(run/'source_manifest.json').resolve()
        assert math.isclose(result['fmax_mhz'],active['current_measured_fmax_mhz'],rel_tol=1e-12)
        assert math.isclose(result['ipc'],active['current_measured_ipc'],rel_tol=1e-12)
        assert math.isclose(result['area_um2'],active['current_measured_area_um2'],rel_tol=1e-12)
    if process_live:
        phase='WORKTREE_IMPLEMENTED_MEASUREMENT_IN_PROGRESS'
    elif failure:
        phase='WORKTREE_IMPLEMENTED_MEASUREMENT_FAILED'
    elif timing_only:
        phase='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    elif result and directed:
        phase=('WORKTREE_IMPLEMENTED_MEASUREMENT_COMPLETE_FULL_CORRECTNESS_NOT_RUN' if
               active['limited_directed_cases_passed']==2 else
               'WORKTREE_IMPLEMENTED_MEASUREMENT_COMPLETE_WITH_LIMITED_CASE_FAILURES')
    elif result:
        phase='WORKTREE_IMPLEMENTED_METRICS_COMPLETE_LIMITED_CASES_PENDING'
    else:
        phase='WORKTREE_IMPLEMENTED_MEASUREMENT_TERMINAL_WITHOUT_COMPLETE_RESULT'
    now=datetime.now(timezone.utc).isoformat()
    observation=dict(status=phase,observed_at=now,run=str(run),source_manifest_sha256=manifest_sha,
        driver_process_id=dispatch['process_id'],driver_process_live_now=process_live,
        build_complete=bool(complete_build),ipc_complete=bool(ipc),synth_report_present=bool(report),
        limited_cases_complete=bool(directed),overall_result_present=bool(result),
        timing_only_complete=bool(timing_only),
        failure=failure,observer_sha256=sha(__file__))
    active.update(status=phase,measurement_process_id=dispatch['process_id'] if process_live else None,
        measurement_progress_recorded_at=now,measurement_observation=str(run/'measurement_observation.json'))
    (run/'measurement_observation.json').write_text(json.dumps(observation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**observation,**{k:active.get(k) for k in
        ('current_measured_fmax_mhz','current_measured_ipc','current_measured_area_um2','current_correctness_status')}},ensure_ascii=False))


if __name__=='__main__':main()
