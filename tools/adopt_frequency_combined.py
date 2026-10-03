"""Adopt a fully measured combined CPU without changing the fixed comparison baseline."""
from pathlib import Path
import datetime
import json
import shutil
from audit_frequency_priority import validate_hashes
from prepare_icache_selective_hierarchy import read, sha


ROOT=Path(__file__).resolve().parents[1]
STAGE=Path('F:/CPU2026Candidates/frequency_combined_v2_20261003')
RESULT=Path('F:/CPU2026Integration/frequency_combined_v2_20261003')
BACKUP=Path('F:/CPU2026Candidates/frequency_combined_main_backup_20261003')


def main():
    profile=ROOT/'build/cpu2026/verified_frequency_combined_profile_20261003.json'
    assert not BACKUP.exists() and not profile.exists(), 'Preserve previous adoption'
    result_path=RESULT/'verified_cpu_result.json';result=read(result_path)
    native_path=RESULT/'independent_native_audit.json';native=read(native_path)
    gate_path=RESULT/'frequency_priority_audit.json';gate=read(gate_path)
    for evidence in (result,native,gate):
        assert evidence['status']=='VERIFIED'
        validate_hashes(evidence)
    assert native['cases']==29 and native['added_native_cases']==8 and native['additional_isa_cases']==16
    assert native['all_retirement_and_exits_identical']
    assert all(row['within_10percent'] for row in gate['metrics'].values())
    assert result['fmax_mhz'] > 49.368431202391285
    assert result['sram_instances']==37
    manifest_path=RESULT/'build/build_manifest.json';manifest=read(manifest_path)
    new={n:h.lower() for n,h in manifest['source_sha256'].items()}
    assert len(new)==43
    prior=read(ROOT/'build/cpu2026/verified_legal_addi_profile_20261003.json')
    old={n:h.lower() for n,h in prior['source_sha256'].items()}
    pipeline=read(Path('F:/CPU2026Candidates/pipeline8_worktree_before_20261003/change_record.json'))
    old.update(pipeline['after_sha256'])
    assert old.keys()==new.keys()
    for n,h in old.items():assert sha(ROOT/n)==h, 'Preserve unrecognized worktree edits: '+n
    for n,h in new.items():assert sha(STAGE/n)==h,n
    changed=[n for n in new if new[n]!=old[n]]
    assert set(changed)==set(read(STAGE/'staging_manifest.json')['changed_files'])
    for n in changed:
        p=BACKUP/n;p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/n,p)
    for n in changed:shutil.copyfile(STAGE/n,ROOT/n)
    assert all(sha(ROOT/n)==h for n,h in new.items())
    record=dict(status='VERIFIED_SOURCE_ADOPTED_FULL_PPA',
        adopted_at=datetime.datetime.now().astimezone().isoformat(),source_root=str(ROOT),
        verified_source_root=str(STAGE),verified_result=str(result_path),
        verified_native_audit=str(native_path),frequency_priority_audit=str(gate_path),
        build_manifest=str(manifest_path),source_sha256=new,old_source_sha256=old,
        changed_files=changed,old_source_backup=str(BACKUP),
        parameter_overrides=manifest['parameter_overrides'],effective_parameters=result['parameters'],
        geomean_ipc=result['geomean_ipc'],area=result['area'],fmax_mhz=result['fmax_mhz'],
        netlist_sha256=result['netlist_sha256'],sram_instances=result['sram_instances'],
        normal_integer_pipeline_stages=8,original_cases=29,additional_cases=24,
        fixed_comparison_baseline_unchanged=True,frequency_target_reached=False,
        tier3_achieved=False,adopter_sha256=sha(__file__),
        evidence_sha256={str(p):sha(p) for p in (result_path,native_path,gate_path,manifest_path)})
    for p in (BACKUP/'adoption.json',profile):
        p.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=record['status'],changed_files=changed,
        all43_main_inputs_match_verified_build=True,profile=str(profile),
        fmax_mhz=record['fmax_mhz'],frequency_goal_met=False),indent=2))


if __name__=='__main__':main()
