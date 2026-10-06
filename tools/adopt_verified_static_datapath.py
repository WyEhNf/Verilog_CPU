"""Adopt the exact five RTL files of the verified completion2 CPU candidate.

Require unchanged current/target builds and preserve all 43 old compiled
inputs before copying. Defaults stay as measured; the selected explicit
parameter profile is exported separately, with all result identities.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-build',type=Path,required=True)
    parser.add_argument('--verified-result',type=Path,required=True)
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--profile',type=Path,required=True)
    args=parser.parse_args()
    assert not args.backup.exists() and not args.profile.exists(), 'Preserve previous adoption evidence'
    result=read(args.verified_result)
    assert result['status']=='VERIFIED' and result['all_correctness_cases']==29
    assert result['tier3_checks']['ipc'] and not result['tier3_achieved']
    for name,h in result['input_sha256'].items():
        assert sha(name)==h,'Verified candidate evidence changed: '+name
    source=Path(result['evaluated_source_root'])
    build_path=Path(result['directory'])/'build/build_manifest.json'
    target=read(build_path);old=read(args.old_build)
    old_hashes={n:h.lower() for n,h in old['source_sha256'].items()}
    new_hashes={n:h.lower() for n,h in target['source_sha256'].items()}
    assert old_hashes.keys()==new_hashes.keys() and len(old_hashes)==43
    expected={'rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_reservation_station.v',
              'rtl/course/student_top.v','rtl/cpu_core.v','rtl/rv32_physical_register_file.v'}
    changes={n for n in old_hashes if old_hashes[n]!=new_hashes[n]}
    assert changes==expected
    for name,h in old_hashes.items():
        assert sha(ROOT/name)==h,'Current worktree differs from frozen old build: '+name
    for name,h in new_hashes.items():
        assert sha(source/name)==h,'Measured candidate source changed: '+name
    for name in old_hashes:
        backup=args.backup/name;backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,backup)
        assert sha(backup)==old_hashes[name]
    for name in sorted(changes):
        shutil.copyfile(source/name,ROOT/name)
    assert all(sha(ROOT/name)==h for name,h in new_hashes.items())
    profile=dict(status='EXACT_VERIFIED_SOURCE_ADOPTED',source_root=str(ROOT),
                 verified_source_root=str(source),verified_result=str(args.verified_result.resolve()),
                 verified_result_sha256=sha(args.verified_result),build_manifest=str(build_path),
                 build_manifest_sha256=sha(build_path),parameter_overrides=target['parameter_overrides'],
                 effective_parameters=result['parameters'],source_sha256=new_hashes,
                 old_source_sha256=old_hashes,old_source_backup=str(args.backup.resolve()),
                 changed_files=sorted(changes),area=result['area'],geomean_ipc=result['geomean_ipc'],
                 fmax_mhz=result['fmax_mhz'],sram_instances=result['sram_instances'],
                 tier3_achieved=False,all_correctness_cases=29,adopter_sha256=sha(__file__))
    args.profile.parent.mkdir(parents=True,exist_ok=True)
    args.profile.write_text(json.dumps(profile,indent=2)+'\n')
    (args.backup/'adoption.json').write_text(json.dumps(profile,indent=2)+'\n')
    print(json.dumps({k:profile[k] for k in ['status','changed_files','area','geomean_ipc','fmax_mhz','tier3_achieved']},indent=2))


if __name__=='__main__':
    main()
