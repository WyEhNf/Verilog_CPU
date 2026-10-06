"""Back up and integrate prepared RTL only; no hardware tools/tests."""
import hashlib
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime,timezone

MAIN=Path('E:/Verilog_cpu')
CANDIDATE=Path('F:/CPU2026Candidates/frequency_research_20261003/H_cached_issue_age')
BASE=Path('F:/CPU2026CourseRuns/current_adopted_20261003')
BACKUP=Path('F:/CPU2026Candidates/pre_staged_frequency_20261004')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-integrated',action='store_true',help='Finish identity after an interrupted bookkeeping step; do not recopy source')
    args=parser.parse_args()
    original=json.loads((BASE/'source_manifest.json').read_text(encoding='utf-8'))
    manifest=json.loads((CANDIDATE/'candidate.json').read_text(encoding='utf-8'))
    names=sorted(set(manifest['changed_files']+['rtl/course/student_top.v']))
    # Check provenance BEFORE modifying any workspace files, preserving all
    # user work if the source has changed since the measured baseline.
    if args.record_integrated:
        before=json.loads((BACKUP/'backup.json').read_text(encoding='utf-8'))['source_sha256']
        for n in names:
            if sha(BACKUP/n)!=before[n] or sha(MAIN/n)!=manifest['source_sha256'][n]:
                raise RuntimeError('Cannot resume source identity: '+n)
    else:
        differences=[n for n in names if sha(MAIN/n)!=original['original_worktree_sha256'][n]]
        if differences:
            raise RuntimeError('Workspace edits require source reconciliation: '+str(differences))
        if BACKUP.exists():
            raise FileExistsError('Preserve previous backup: '+str(BACKUP))
        before={n:sha(MAIN/n) for n in names}
        for n in names:
            target=BACKUP/n
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(MAIN/n,target)
        (BACKUP/'backup.json').write_text(json.dumps(dict(
            status='BACKUP_COMPLETE',source_root=str(MAIN),source_sha256=before,
            measured_baseline_manifest_sha256=sha(BASE/'source_manifest.json')),
            ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for n in names:
        if sha(CANDIDATE/n)!=manifest['source_sha256'][n]:
            raise RuntimeError('Prepared candidate changed: '+n)
    if not args.record_integrated:
        for n in names:
            shutil.copyfile(CANDIDATE/n,MAIN/n)
    record=dict(status='WORKTREE_IMPLEMENTED_UNTESTED',created_at=datetime.now(timezone.utc).isoformat(),
                source_root=str(MAIN),candidate=str(CANDIDATE),backup=str(BACKUP),
                implemented_files=names,source_sha256={n:sha(MAIN/n) for n in manifest['source_sha256'] if (MAIN/n).is_file()},
                generated_course_alias_sha256={n:h for n,h in manifest['source_sha256'].items() if not (MAIN/n).is_file()},
                candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
                parameter_overrides=manifest['parameter_overrides'],
                materialized_top_defaults=True,tests_started=False,
                current_measured_fmax_mhz=32.39788654411997,
                measured_frequency_belongs_to='Frozen baseline only; experimental worktree has no measurements')
    target=MAIN/'build/cpu2026/active_frequency_implementation_20261004.json'
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':record['status'],'files':len(names),'identity':str(target),'backup':str(BACKUP)},ensure_ascii=False))


if __name__=='__main__':
    main()
