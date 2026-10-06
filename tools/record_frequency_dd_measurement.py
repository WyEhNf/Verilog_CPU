"""Record existing DD measurements only; never invoke hardware tools."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from summarize_course_frequency_native import read, sha

ROOT = Path('E:/Verilog_cpu')
ACTIVE = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
RUN = Path('F:/CPU2026CourseRuns/architecture_DD_20261005')
SUMMARY = Path('F:/CPU2026Proofs/DD_existing_reports_20261005/summary.json')


def main():
    active=read(ACTIVE)
    summary=read(SUMMARY)
    assert Path(active['frozen_run'])==RUN
    assert active['frozen_manifest_sha256']==summary['source_manifest_sha256']==sha(RUN/'source_manifest.json')
    for name, expected in active['source_sha256'].items():
        assert sha(ROOT/name)==expected, name
    manifest=read(RUN/'source_manifest.json')
    for name, expected in manifest['snapshot_sha256'].items():
        assert sha(Path(manifest['source_root'])/name)==expected, name
    assert sha(RUN/'result/synth/opt/report.json')==summary['report_sha256']
    ipc=read(RUN/'result/ipc.json')
    assert ipc['status']=='COMPLETE' and ipc['latency']==10 and len(ipc['results'])==6
    directed=read(RUN/'directed_cases/results.json')
    text=(RUN/'result/correctness.log').read_text(encoding='utf-8')
    totals=re.search(r'^Results: (\d+) passed, (\d+) failed\s*$',text,re.MULTILINE)
    failed_cases=re.findall(r'\[([^\]]+)\]\s*\nFAIL:',text)
    terminal=bool(totals)
    active.update(
        status=('WORKTREE_IMPLEMENTED_MEASUREMENT_COMPLETE_WITH_FAILURES' if failed_cases else
                'WORKTREE_IMPLEMENTED_MEASUREMENT_COMPLETE') if terminal else
               'WORKTREE_IMPLEMENTED_MEASUREMENT_IN_PROGRESS',
        current_measured_fmax_mhz=summary['timing']['estimated_fmax_mhz'],
        current_measured_area_um2=summary['area']['area_um2'],
        current_measured_ipc=ipc['geomean_ipc'],
        measured_frequency_belongs_to=str(RUN),
        measured_metrics_report=str(SUMMARY),
        completed_ipc_report=str(RUN/'result/ipc.json'),
        directed_result_report=str(RUN/'directed_cases/results.json'),
        current_correctness_status=('COMPLETE_WITH_FAILURES' if failed_cases else 'COMPLETE') if terminal else
            ('RUNNING_WITH_FAILURES' if failed_cases else 'RUNNING'),
        current_correctness_suite_passed=(int(totals.group(2))==0 if terminal else False if failed_cases else None),
        current_correctness_passed=int(totals.group(1)) if terminal else text.count('PASS cycles='),
        current_correctness_failed=int(totals.group(2)) if terminal else len(failed_cases),
        current_correctness_failed_cases=failed_cases,
        metrics_recorded_at=datetime.now(timezone.utc).isoformat())
    if terminal:
        active['measurement_process_id']=None
    # The original summary was taken before IPC completed; retain that
    # historical artifact and explicitly point to the subsequently completed IPC.
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:active[key] for key in (
        'status','current_measured_fmax_mhz','current_measured_area_um2',
        'current_measured_ipc','current_correctness_status','current_correctness_passed')},ensure_ascii=False))


if __name__=='__main__':
    main()
