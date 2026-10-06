"""Launch one already reported, frozen native batch in the background."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
from summarize_course_frequency_native import read,sha

ROOT=Path('E:/Verilog_cpu')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--correctness',action='store_true')
    parser.add_argument('--timing-only',action='store_true',help='First measure frequency/area only; leave CPU build and simulation stopped')
    args=parser.parse_args()
    assert not (args.timing_only and args.correctness),'Timing-only must not start correctness'
    assert os.name=='nt','Native Windows only'
    run=args.run.resolve()
    active=read(ACTIVE)
    assert Path(active['frozen_run']).resolve()==run and not active['tests_started']
    assert Path(active['pretest_report']).is_file(),'Concrete pretest report required'
    assert active.get('measurement_plan',{}).get('ready_for_dispatch',True), 'Source research/scope report is still pending'
    if active.get('pretest_report_sha256'):
        assert sha(Path(active['pretest_report']))==active['pretest_report_sha256'], 'Pretest report identity changed'
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=read(run/'source_manifest.json')
    for name,expected in active['source_sha256'].items():
        assert sha(ROOT/name)==expected,'Worktree changed: '+name
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,'Frozen input changed: '+name
    for name in ('result','driver_stdout.log','driver_stderr.log','dispatch_identity.json'):
        assert not (run/name).exists(),'Preserve existing dispatch/results: '+name
    config=read(run/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    command=[sys.executable,'-u',str(ROOT/'tools/run_course_standard_windows.py'),
             '--config',str(run/'course_windows_config.json')]
    if args.correctness:
        command.append('--correctness')
    if args.timing_only:
        command.append('--timing-only')
    started=datetime.now(timezone.utc).isoformat()
    with (run/'driver_stdout.log').open('w',encoding='utf-8') as stdout, \
         (run/'driver_stderr.log').open('w',encoding='utf-8') as stderr:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch=dict(status='BACKGROUND_DISPATCHED',environment='WINDOWS_NATIVE',command=command,
        process_id=process.pid,started_at=started,source_manifest_sha256=sha(run/'source_manifest.json'),
        pretest_report=active['pretest_report'],pretest_report_sha256=sha(active['pretest_report']),
        initial_process_alive=process.poll() is None,official_correctness_requested=args.correctness,
        timing_only_requested=args.timing_only,cpu_build_and_simulation_requested=not args.timing_only)
    (run/'dispatch_identity.json').write_text(json.dumps(dispatch,indent=2)+'\n',encoding='utf-8')
    active.update(status='WORKTREE_IMPLEMENTED_MEASUREMENT_IN_PROGRESS',tests_started=True,
                  measurement_process_id=process.pid,measurement_started_at=started)
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dispatch,ensure_ascii=False))


if __name__=='__main__':
    main()
