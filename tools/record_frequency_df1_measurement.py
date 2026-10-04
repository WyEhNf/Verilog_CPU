"""Read existing frozen DF1 progress/metrics; never execute hardware tools."""
import json
import math
from pathlib import Path
from datetime import datetime,timezone
from summarize_course_frequency_native import read,sha

ROOT=Path('E:/Verilog_cpu')
RUN=Path('F:/CPU2026CourseRuns/architecture_DF1_20261005')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'


def main():
    active=read(ACTIVE)
    assert Path(active['frozen_run'])==RUN
    assert active['tests_started'] and active['frozen_manifest_sha256']==sha(RUN/'source_manifest.json')
    frozen=read(RUN/'source_manifest.json')
    for name,expected in active['source_sha256'].items():
        assert sha(ROOT/name)==expected,'Worktree:'+name
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(RUN/'source'/name)==expected,'Frozen:'+name
    identity=read(RUN/'result/measurement_identity.json')
    assert identity['environment']=='WINDOWS_NATIVE' and identity['source_manifest_sha256']==sha(RUN/'source_manifest.json')
    build=read(RUN/'native_build/build_identity.json')
    assert build['status']=='COMPLETE' and build['source_manifest_sha256']==sha(RUN/'source_manifest.json')
    assert sha(build['executable'])==build['executable_sha256']
    ipc=read(RUN/'result/ipc.json')
    assert ipc['status']=='COMPLETE' and ipc['latency']==10 and len(ipc['results'])==6
    directed=read(RUN/'directed_cases/results.json')
    assert directed['source_manifest_sha256']==sha(RUN/'source_manifest.json')
    assert directed['executable_sha256']==build['executable_sha256']
    assert len(directed['results'])==2
    assert all(row['status']=='PASS' for row in directed['results'])
    report_path=RUN/'result/synth/opt/report.json'
    if report_path.is_file():
        official=read(report_path)
        fmax=official['timing']['estimated_fmax_mhz']
        assert math.isfinite(fmax) and fmax>0
        active.update(current_measured_fmax_mhz=fmax,
            current_measured_area_um2=official['area']['area_um2'],
            measured_frequency_belongs_to=str(RUN),measured_metrics_report=str(report_path))
    terminal=(RUN/'result/result.json').is_file() or (RUN/'result/failure.json').is_file()
    active.update(current_measured_ipc=ipc['geomean_ipc'],
        completed_ipc_report=str(RUN/'result/ipc.json'),directed_result_report=str(RUN/'directed_cases/results.json'),
        current_correctness_status='LIMITED_CASES_PASSED_FULL_SUITE_NOT_RUN',
        current_correctness_suite_passed=None,current_correctness_passed=None,current_correctness_failed=None,
        limited_directed_cases_passed=2,limited_directed_checks=176,
        measurement_progress_recorded_at=datetime.now(timezone.utc).isoformat())
    if terminal:
        active['status']='WORKTREE_IMPLEMENTED_MEASUREMENT_COMPLETE_FULL_CORRECTNESS_NOT_RUN'
        active['measurement_process_id']=None
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:active[key] for key in ('status','current_measured_fmax_mhz',
                     'current_measured_area_um2','current_measured_ipc','current_correctness_status')}))


if __name__=='__main__':
    main()
