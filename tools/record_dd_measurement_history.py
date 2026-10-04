"""Refresh completed DD artifacts after adopting another source; no test runs."""
import json
import re
from datetime import datetime,timezone
from pathlib import Path
from summarize_course_frequency_native import read,sha

ROOT=Path('E:/Verilog_cpu')
RUN=Path('F:/CPU2026CourseRuns/architecture_DD_20261005')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'


def main():
    active=read(ACTIVE)
    frozen=read(RUN/'source_manifest.json')
    digest=sha(RUN/'source_manifest.json')
    identity=read(RUN/'result/measurement_identity.json')
    assert identity['environment']=='WINDOWS_NATIVE' and identity['source_manifest_sha256']==digest
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(RUN/'source'/name)==expected,name
    summary=read('F:/CPU2026Proofs/DD_existing_reports_20261005/summary.json')
    assert summary['source_manifest_sha256']==digest
    assert summary['report_sha256']==sha(RUN/'result/synth/opt/report.json')
    ipc=read(RUN/'result/ipc.json')
    assert ipc['status']=='COMPLETE' and ipc['latency']==10 and len(ipc['results'])==6
    text=(RUN/'result/correctness.log').read_text(encoding='utf-8')
    totals=re.search(r'^Results: (\d+) passed, (\d+) failed\s*$',text,re.M)
    failures=re.findall(r'\[([^\]]+)\]\s*\nFAIL:',text)
    record=dict(frozen_run=str(RUN),source_manifest_sha256=digest,
        status=('MEASUREMENT_COMPLETE_WITH_FAILURES' if failures else 'MEASUREMENT_COMPLETE') if totals else 'MEASUREMENT_IN_PROGRESS',
        observed_at=datetime.now(timezone.utc).isoformat(),
        current_measured_fmax_mhz=summary['timing']['estimated_fmax_mhz'],
        current_measured_area_um2=summary['area']['area_um2'],
        current_measured_ipc=ipc['geomean_ipc'],
        measured_metrics_report='F:/CPU2026Proofs/DD_existing_reports_20261005/summary.json',
        completed_ipc_report=str(RUN/'result/ipc.json'),
        current_correctness_status=('COMPLETE_WITH_FAILURES' if failures else 'COMPLETE') if totals else
            ('RUNNING_WITH_FAILURES' if failures else 'RUNNING'),
        current_correctness_passed=int(totals[1]) if totals else text.count('PASS cycles='),
        current_correctness_failed=int(totals[2]) if totals else len(failures),
        current_correctness_failed_cases=failures,
        current_correctness_suite_passed=(int(totals[2])==0 if totals else False if failures else None))
    (RUN/'measurement_progress.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    for entry in active.get('background_measurements',[]):
        if Path(entry['frozen_run'])==RUN:
            assert entry['source_manifest_sha256']==digest
            entry.update(record)
            if totals:
                entry['measurement_process_id']=None
    last=active.get('last_observed_measurement',{})
    if last.get('frozen_run') and Path(last['frozen_run'])==RUN:
        last.update(record)
    # Current worktree metrics remain untouched; these belong only to DD.
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:record[key] for key in ('status','current_correctness_status',
                     'current_correctness_passed','current_correctness_failed','current_correctness_failed_cases')}))


if __name__=='__main__':
    main()
