"""Read one native reused-timing program job; never start/restart any test."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from start_reused_frequency_programs_background import ROOT, ACTIVE, read, sha
from wait_frequency_directed_native import live


def optional(path):
    try:
        return read(path)
    except (FileNotFoundError,json.JSONDecodeError):
        return None


def correctness_rows(path,expected):
    if not path.exists():
        return []
    rows=[]
    current=None
    for line in path.read_text(encoding='utf-8',errors='replace').splitlines():
        match=re.fullmatch(r'\[(correctness_\S+)\]',line)
        if match:
            current=match[1]
            assert current in expected,current
        elif current and re.fullmatch(r'PASS(?: cycles=\d+)?',line):
            rows.append(dict(name=current,status='PASS',detail=line))
            current=None
        elif current and line.startswith('FAIL:'):
            rows.append(dict(name=current,status='FAIL',detail=line))
            current=None
    assert len({r['name'] for r in rows})==len(rows),'No repeated completed cases'
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    args=p.parse_args()
    assert os.name=='nt'
    run=args.run.resolve()
    active=read(ACTIVE)
    assert Path(active['frozen_run']).resolve()==run
    dispatch=read(run/'program_dispatch_identity.json')
    manifest_sha=sha(run/'source_manifest.json')
    assert dispatch['source_manifest_sha256']==manifest_sha==active['frozen_manifest_sha256']
    assert dispatch['reuse_existing_synth'] and not dispatch['new_synth_requested']
    assert dispatch['timing_only_report_sha256']==sha(run/'result/timing_only.json')
    assert dispatch['timing_identity_sha256']==sha(run/'result/timing_identity.json')
    assert dispatch['original_timing_dispatch_sha256']==sha(run/'dispatch_identity.json')
    assert dispatch['official_report_sha256']==sha(run/'result/synth/opt/report.json')
    assert dispatch['pretest_report_sha256']==sha(dispatch['pretest_report'])
    for n,h in active['source_sha256'].items():
        assert sha(ROOT/n)==h,n
    frozen=read(run/'source_manifest.json')
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    config=read(run/'course_windows_config.json')
    timing=read(run/'result/timing_only.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert timing['config_sha256']==sha(run/'course_windows_config.json')
    assert timing['toolchain_manifest_sha256']==sha(Path(config['tools_root'])/'toolchain_manifest.json')
    active.update(current_measured_fmax_mhz=timing['fmax_mhz'],current_measured_area_um2=timing['area_um2'])
    identity=optional(run/'result/measurement_identity.json')
    if identity:
        assert identity['source_manifest_sha256']==manifest_sha and identity['environment']=='WINDOWS_NATIVE'
    build=optional(Path(config['native_build_path'])/'build_identity.json')
    built=bool(build and build.get('status')=='COMPLETE')
    if built:
        assert build['source_manifest_sha256']==manifest_sha
        assert build['verilator_sha256']==sha(config['verilator'])
        assert build['executable_sha256']==sha(build['executable'])
        active['completed_build_identity']=str(Path(config['native_build_path'])/'build_identity.json')
    ipc=optional(run/'result/ipc.json')
    if ipc:
        assert built and ipc['status']=='COMPLETE' and ipc['latency']==10
        assert sorted(r['name'] for r in ipc['results'])==dispatch['perf_cases']
        assert len(ipc['results'])==6
        base=run/'source/.deps/RISC-V-CPU-2026/testcases'
        for row in ipc['results']:
            case=base/row['name']
            assert row['program_sha256']==sha(case/'program.data')
            assert row['metrics_sha256']==sha(case/'metrics.json')
            assert row['instructions']==read(case/'metrics.json')['dynamic_instructions']
            assert row['cycles']>0 and math.isclose(row['ipc'],row['instructions']/row['cycles'],rel_tol=1e-12)
        geometric=math.exp(sum(math.log(r['ipc']) for r in ipc['results'])/6)
        assert math.isclose(geometric,ipc['geomean_ipc'],rel_tol=1e-12)
        active.update(current_measured_ipc=geometric,completed_ipc_report=str(run/'result/ipc.json'))
    rows=correctness_rows(run/'result/correctness.log',dispatch['correctness_cases'])
    failed=[r['name'] for r in rows if r['status']=='FAIL']
    passed=sum(r['status']=='PASS' for r in rows)
    active.update(current_correctness_passed=passed,current_correctness_failed=len(failed),
        current_correctness_failed_cases=failed,current_correctness_suite_passed=None,
        current_correctness_status=('FULL_COURSE_PROGRAM_FAILURE_OBSERVED' if failed else 'FULL_COURSE_PROGRAMS_IN_PROGRESS'))
    result=optional(run/'result/result.json')
    failure=optional(run/'result/failure.json')
    alive=live(dispatch['process_id'])
    complete=False
    if result:
        assert built and ipc and identity and identity['status']=='COMPLETE'
        assert result['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
        assert identity['result_sha256']==sha(run/'result/result.json')
        assert identity['ipc_sha256']==sha(run/'result/ipc.json')
        assert identity['official_report_sha256']==dispatch['official_report_sha256']
        assert Path(result['source_manifest']).resolve()==(run/'source_manifest.json').resolve()
        assert result['latency']==10 and result['official_perf_expected_results_passed']
        assert result['official_correctness_suite_passed'] and not result['official_correctness_suite_not_run']
        assert sorted(r['name'] for r in rows)==dispatch['correctness_cases'] and passed==19 and not failed
        assert math.isclose(result['ipc'],active['current_measured_ipc'],rel_tol=1e-12)
        assert result['fmax_mhz']==timing['fmax_mhz'] and result['area_um2']==timing['area_um2']
        assert 'Results: 19 passed, 0 failed' in (run/'result/correctness.log').read_text(encoding='utf-8')
        active.update(current_correctness_status='FULL_COURSE_19_CASES_PASSED',current_correctness_suite_passed=True,
            current_correctness_report=str(run/'result/correctness.log'),
            last_complete_course_standard_result=str(run/'result/result.json'))
        complete=True
    phase=('WORKTREE_IMPLEMENTED_REUSED_TIMING_PROGRAMS_IN_PROGRESS' if alive else
        'WORKTREE_IMPLEMENTED_FULL_COURSE_MEASUREMENT_COMPLETE' if complete else
        'WORKTREE_IMPLEMENTED_PROGRAM_MEASUREMENT_FAILED' if failure or failed else
        'WORKTREE_IMPLEMENTED_PROGRAM_MEASUREMENT_TERMINAL_WITHOUT_COMPLETE_RESULT')
    observation=dict(status=phase,observed_at=datetime.now(timezone.utc).isoformat(),run=str(run),
        source_manifest_sha256=manifest_sha,process_id=dispatch['process_id'],process_live_now=alive,
        build_complete=built,ipc_complete=bool(ipc),correctness_cases_completed=len(rows),
        correctness_passed=passed,correctness_failed=failed,full_result_complete=complete,
        official_timing_reused_unchanged=True,new_synth_started=False,failure=failure,observer_sha256=sha(__file__))
    path=run/'program_measurement_observation.json'
    path.write_text(json.dumps(observation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    active.update(status=phase,measurement_process_id=dispatch['process_id'] if alive else None,
        program_measurement_observation=str(path),measurement_progress_recorded_at=observation['observed_at'])
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**observation,'current_measured_fmax_mhz':timing['fmax_mhz'],
        'current_measured_area_um2':timing['area_um2'],'current_measured_ipc':active.get('current_measured_ipc')},ensure_ascii=False))


if __name__=='__main__':
    main()
