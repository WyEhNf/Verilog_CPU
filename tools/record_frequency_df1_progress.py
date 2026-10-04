"""Record DF1 source identities, preserving the live DD measurement."""
import json
from pathlib import Path
from datetime import datetime,timezone
from summarize_course_frequency_native import read,sha

ROOT=Path('E:/Verilog_cpu')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'


def main():
    active=read(ACTIVE)
    candidate=Path(active['candidate'])
    run=Path(active['frozen_run'])
    assert candidate.name=='DF1_lsq_forward_windows_names' and not active['tests_started']
    frozen=read(run/'source_manifest.json')
    for name,expected in active['source_sha256'].items():
        assert sha(ROOT/name)==expected,name
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,name
    dd=Path('F:/CPU2026CourseRuns/architecture_DD_20261005')
    dd_manifest=read(dd/'source_manifest.json')
    for name,expected in dd_manifest['snapshot_sha256'].items():
        assert sha(dd/'source'/name)==expected,'DD frozen:'+name
    changed=[name for name in active['source_sha256'] if name.endswith('.v') and sha(ROOT/name)!=sha(dd/'source'/name)]
    assert changed==['rtl/backend/rv32_lsq.v','rtl/cache/rv32_dcache_nonblocking.v']
    previous=read(Path(active['backup'])/'backup.json')['previous_identity']
    background=dict(previous['last_observed_measurement'])
    background.update(active['previous_measurement'])
    background.update(source_manifest_sha256=sha(dd/'source_manifest.json'),
        measurement_process_id=previous['measurement_process_id'],
        measurement_started_at=previous['measurement_started_at'],
        completed_ipc_report=previous['completed_ipc_report'],
        directed_result_report=previous['directed_result_report'])
    active['background_measurements']=[background]
    for key in ('completed_ipc_report','directed_result_report','metrics_recorded_at'):
        active.pop(key,None)
    active['implementation_report']='E:/Verilog_cpu/reports/frequency_batch_DF1_pretest_2026-10-05.md'
    active['pretest_report']=active['implementation_report']
    active['source_identity_review']=dict(status='SOURCE_IDENTITIES_ONLY_NO_HDL_TEST',
        reviewed_at=datetime.now(timezone.utc).isoformat(),active_source_files=len(active['source_sha256']),
        frozen_input_files=len(frozen['snapshot_sha256']),changed_rtl_vs_measured_DD=changed,
        ordinary_integer_pipeline_stages=10,tests_started=False,
        limitations='File identity and manual source reasoning only; no HDL syntax/function/area/IPC/timing proof')
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(active['source_identity_review'],ensure_ascii=False))


if __name__=='__main__':
    main()
