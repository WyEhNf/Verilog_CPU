"""Record already completed official CD1 metrics; never run hardware tools."""
import json
import re
from pathlib import Path
from summarize_course_frequency_native import sha, read

root=Path('E:/Verilog_cpu')
active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
active=read(active_path)
summary=read('F:/CPU2026Proofs/CD1_existing_reports_20261004/summary.json')
if active['frozen_manifest_sha256']!=summary['source_manifest_sha256']:
    raise ValueError('Current implementation is not the measured CD1 source')
for name,expected in active['source_sha256'].items():
    if sha(root/name)!=expected:
        raise ValueError('Worktree source changed: '+name)
correctness_path=Path(active['frozen_run'])/'result/correctness.log'
correctness_text=correctness_path.read_text(encoding='utf-8') if correctness_path.is_file() else ''
observed_failure='FAIL:' in correctness_text
totals=re.search(r'^Results: (\d+) passed, (\d+) failed\s*$',correctness_text,re.MULTILINE)
terminal=totals is not None
failed_cases=re.findall(r'\[([^\]]+)\]\s*\nFAIL:',correctness_text)
active.update(status=('WORKTREE_IMPLEMENTED_MEASUREMENT_COMPLETE_WITH_FAILURES' if terminal and observed_failure else 'WORKTREE_IMPLEMENTED_PARTIAL_MEASUREMENT_COMPLETE'),
    current_measured_fmax_mhz=summary['timing']['estimated_fmax_mhz'],
    current_measured_ipc=summary['ipc'],
    current_measured_area_um2=summary['area']['area_um2'],
    measured_frequency_belongs_to=active['frozen_run'],
    measured_metrics_report='F:/CPU2026Proofs/CD1_existing_reports_20261004/summary.json',
    current_correctness_suite_passed=(int(totals.group(2))==0 if terminal else (False if observed_failure else None)),
    current_correctness_status=('COMPLETE_WITH_FAILURES' if observed_failure else 'COMPLETE') if terminal else ('RUNNING_WITH_FAILURES' if observed_failure else 'RUNNING'),
    current_correctness_passed=(int(totals.group(1)) if terminal else None),
    current_correctness_failed=(int(totals.group(2)) if terminal else None),
    current_correctness_failed_cases=failed_cases,
    next_unadopted_candidate='F:/CPU2026Candidates/frequency_research_20261003/CG_dcache_load_extract_distribution')
if terminal:
    active['measurement_process_id']=None
active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({key:active[key] for key in ['status','current_measured_fmax_mhz','current_measured_ipc','current_measured_area_um2']},ensure_ascii=False))
