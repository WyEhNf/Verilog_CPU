"""Launch one reported native program phase using exact completed timing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path('E:/Verilog_cpu')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    args=p.parse_args()
    assert os.name=='nt','Native Windows only'
    run=args.run.resolve()
    active=read(ACTIVE)
    assert Path(active['frozen_run']).resolve()==run
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert active['measurement_process_id'] is None
    plan=active['program_measurement_plan']
    assert plan['ready_for_dispatch'] and plan['scope_finalized']
    assert plan['reuse_existing_synth'] and plan['full_course_correctness_requested']
    pretest=Path(active['program_pretest_report'])
    assert sha(pretest)==active['program_pretest_report_sha256']
    timing=read(run/'result/timing_only.json')
    config=read(run/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert timing['status']=='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256']==sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert timing['official_report_sha256']==sha(run/'result/synth/opt/report.json')
    assert timing['toolchain_manifest_sha256']==sha(Path(config['tools_root'])/'toolchain_manifest.json')
    assert timing['config_sha256']==sha(run/'course_windows_config.json')
    assert timing['fmax_mhz']==active['current_measured_fmax_mhz']
    assert timing['area_um2']==active['current_measured_area_um2']
    assert timing['fmax_mhz']>=active['measurement_plan']['material_frequency_gain_working_threshold_mhz']
    assert timing['area_um2']<=active['measurement_plan']['original_plus_10_percent_area_um2']
    assert not timing['cpu_build_started'] and not timing['simulation_started']
    for name,h in active['source_sha256'].items():
        assert sha(ROOT/name)==h,name
    frozen=read(run/'source_manifest.json')
    for name,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==h,name
    cases=run/'source/.deps/RISC-V-CPU-2026/testcases'
    perf=sorted(x.name for x in cases.glob('perf_*') if x.is_dir())
    correctness=sorted(x.name for x in cases.glob('correctness_*') if x.is_dir())
    assert len(perf)==6 and len(correctness)==19
    assert plan['perf_cases']==perf and plan['correctness_cases']==correctness
    for name in ('native_build','native_ipc','program_dispatch_identity.json',
        'program_driver_stdout.log','program_driver_stderr.log','result/ipc.json',
        'result/result.json','result/perf.log','result/correctness.log','result/build_host.log','result/failure.json'):
        assert not (run/name).exists(),'Preserve earlier program work: '+name
    command=[sys.executable,'-u',str(ROOT/'tools/run_course_standard_windows.py'),
        '--config',str(run/'course_windows_config.json'),'--reuse-synth','--correctness']
    started=datetime.now(timezone.utc).isoformat()
    with (run/'program_driver_stdout.log').open('w',encoding='utf-8') as stdout, \
        (run/'program_driver_stderr.log').open('w',encoding='utf-8') as stderr:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch=dict(status='PROGRAM_PHASE_BACKGROUND_DISPATCHED',environment='WINDOWS_NATIVE',
        process_id=process.pid,started_at=started,command=command,
        source_manifest_sha256=active['frozen_manifest_sha256'],
        pretest_report=str(pretest),pretest_report_sha256=sha(pretest),
        timing_only_report_sha256=sha(run/'result/timing_only.json'),
        timing_identity_sha256=sha(run/'result/timing_identity.json'),
        original_timing_dispatch_sha256=sha(run/'dispatch_identity.json'),
        official_report_sha256=timing['official_report_sha256'],
        reuse_existing_synth=True,new_synth_requested=False,full_course_correctness_requested=True,
        perf_cases=perf,correctness_cases=correctness,initial_process_alive=process.poll() is None)
    path=run/'program_dispatch_identity.json'
    path.write_text(json.dumps(dispatch,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    active.update(status='WORKTREE_IMPLEMENTED_REUSED_TIMING_PROGRAMS_IN_PROGRESS',
        measurement_process_id=process.pid,measurement_started_at=started,
        program_dispatch_identity=str(path),program_phase_source_frozen=True)
    active['measurement_plan']['current_phase']='PROGRAMS_REUSING_EXACT_TIMING'
    active['orchestration_source_sha256'].update({n:sha(ROOT/n) for n in (
        'tools/start_reused_frequency_programs_background.py','tools/record_reused_frequency_program_progress.py')})
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dispatch,ensure_ascii=False))


if __name__=='__main__':
    main()
