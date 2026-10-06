"""Reconcile prepared source with the worktree and freeze one native run; no EDA."""
import hashlib
import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

MAIN=Path('E:/Verilog_cpu')
BASE=Path('F:/CPU2026CourseRuns/current_adopted_20261003')
CANDIDATE=Path('F:/CPU2026Candidates/frequency_research_20261003/L_local_recovery_queries')
RUN=Path('F:/CPU2026CourseRuns/architecture_L_20261004')
BACKUP=Path('F:/CPU2026Candidates/pre_L_worktree_20261004')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p,data):
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    global CANDIDATE,RUN,BACKUP
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,default=CANDIDATE)
    parser.add_argument('--run',type=Path,default=RUN)
    parser.add_argument('--backup',type=Path,default=BACKUP)
    args=parser.parse_args()
    CANDIDATE,RUN,BACKUP=args.candidate,args.run,args.backup
    record_path=MAIN/'build/cpu2026/active_frequency_implementation_20261004.json'
    previous=json.loads(record_path.read_text(encoding='utf-8'))
    candidate=json.loads((CANDIDATE/'candidate.json').read_text(encoding='utf-8'))
    baseline=json.loads((BASE/'source_manifest.json').read_text(encoding='utf-8'))
    for n,h in previous['source_sha256'].items():
        if sha(MAIN/n)!=h:
            raise RuntimeError('Preserve changed worktree source: '+n)
    for n,h in candidate['source_sha256'].items():
        if sha(CANDIDATE/n)!=h:
            raise RuntimeError('Prepared source changed: '+n)
    for n,h in baseline['snapshot_sha256'].items():
        if sha(BASE/'source'/n)!=h:
            raise RuntimeError('Measured baseline changed: '+n)
    if RUN.exists() or BACKUP.exists():
        raise FileExistsError('Preserve existing frozen runs and backups')
    names=sorted(set(candidate['changed_files']+['rtl/course/student_top.v']))
    BACKUP.mkdir()
    for n in names:
        target=BACKUP/n
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(MAIN/n,target)
    write(BACKUP/'backup.json',dict(status='BACKUP_COMPLETE',source_sha256={n:sha(BACKUP/n) for n in names},
                                   previous_identity=previous))
    for n in names:
        shutil.copyfile(CANDIDATE/n,MAIN/n)
    source=RUN/'source'
    source.mkdir(parents=True)
    for n in baseline['snapshot_sha256']:
        target=source/n
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(BASE/'source'/n,target)
    for n in candidate['source_sha256']:
        target=source/n
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(CANDIDATE/n,target)
    files=sorted(set(baseline['snapshot_sha256'])|set(candidate['source_sha256']))
    frozen=dict(baseline)
    frozen.update(status='FROZEN_UNTESTED',created_at=datetime.now(timezone.utc).isoformat(),
                  baseline_manifest_sha256=sha(BASE/'source_manifest.json'),
                  candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),candidate=str(CANDIDATE),
                  snapshot_sha256={n:sha(source/n) for n in files},
                  original_worktree_sha256={n:sha(MAIN/n) for n in candidate['source_sha256'] if (MAIN/n).is_file()},
                  parameter_overrides=candidate['parameter_overrides'],materialized_top_defaults=True,
                  source_root=str(source),tests_started=False)
    write(RUN/'source_manifest.json',frozen)
    config=json.loads((MAIN/'tools/course_windows_config.json').read_text())
    config.update(source=str(source),source_manifest=str(RUN/'source_manifest.json'),out=str(RUN/'result'),
                  native_build_path=str(RUN/'native_build'),native_ipc_path=str(RUN/'native_ipc'))
    write(RUN/'course_windows_config.json',config)
    record=dict(previous)
    record.update(status='WORKTREE_IMPLEMENTED_UNTESTED',
                  created_at=frozen['created_at'],candidate=str(CANDIDATE),backup=str(BACKUP),
                  previous_identity_backup=str(BACKUP/'backup.json'),implemented_files=names,
                  source_sha256=frozen['original_worktree_sha256'],
                  generated_course_alias_sha256={n:h for n,h in candidate['source_sha256'].items() if not (MAIN/n).is_file()},
                  candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),frozen_run=str(RUN),
                  frozen_manifest_sha256=sha(RUN/'source_manifest.json'),tests_started=False)
    record.pop('measurement_process_id',None)
    record.pop('measurement_started_at',None)
    # A frequency measured for the baseline must never look like a frequency
    # measured for the newly edited worktree.
    record['previous_measurement']={key:previous.get(key) for key in [
        'frozen_run','status','current_measured_fmax_mhz','current_measured_ipc',
        'current_measured_area_um2','measured_metrics_report','current_correctness_status',
        'current_correctness_passed','current_correctness_failed','current_correctness_failed_cases']}
    if previous.get('current_measured_fmax_mhz') is not None:
        record['last_observed_measurement']=record['previous_measurement']
    elif previous.get('last_observed_measurement'):
        record['last_observed_measurement']=previous['last_observed_measurement']
    elif previous.get('previous_measurement',{}).get('current_measured_fmax_mhz') is not None:
        record['last_observed_measurement']=previous['previous_measurement']
    record['current_measured_fmax_mhz']=None
    record['current_measured_ipc']=None
    record['current_measured_area_um2']=None
    record['measured_metrics_report']=None
    record['current_correctness_suite_passed']=None
    record['current_correctness_status']='UNTESTED'
    record['current_correctness_passed']=None
    record['current_correctness_failed']=None
    record['current_correctness_failed_cases']=[]
    record.pop('next_unadopted_candidate',None)
    record['measured_frequency_belongs_to']=None
    record['last_complete_course_standard_result']=previous.get('last_complete_course_standard_result',str(BASE/'result/result.json'))
    write(record_path,record)
    print(json.dumps(dict(status='FROZEN_UNTESTED',implemented_files=len(names),frozen_files=len(files),run=str(RUN)),ensure_ascii=False))


if __name__=='__main__':
    main()
