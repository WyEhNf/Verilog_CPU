"""Adopt exactly the three natively verified ADDI255 repair files.

Keep all43 old measured inputs in an immutable backup. Recheck both source
trees, the39protocol/29original/8added proof input hashes, exact shared
parameters and original-driver audit before writing main RTL. No old PPA is
assigned to the repair: its new wholeCPU measurement is recorded as pending.
"""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
STAGE=Path('F:/CPU2026Candidates/legal_addi_fix_20261003')
RUN=Path('F:/CPU2026Integration/r64p64rs12lsq16_cdb2_legal_addi_fix_20261003')
BACKUP=Path('F:/CPU2026Integration/parallel_select_20261002/pre_legal_addi_adoption_20261003')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def main():
    assert not BACKUP.exists(), 'Preserve earlier adoption record'
    audit_path=RUN/'independent_native_audit.json';audit=read(audit_path)
    assert audit['status']=='VERIFIED' and audit['cases']==29
    assert audit['protocol_configurations']==39 and audit['added_native_cases']==8
    assert audit['known_baseline_addi255_defect_fixed'] and audit['all_cycles_retirement_and_exits_identical']
    for name,value in audit['input_sha256'].items():assert sha(name)==value,name
    stage=read(STAGE/'staging_manifest.json');manifest_path=RUN/'build/build_manifest.json';manifest=read(manifest_path)
    old,new=stage['baseline_sha256'],stage['staged_sha256']
    assert len(old)==len(new)==43
    assert new=={n:h.lower() for n,h in manifest['source_sha256'].items()}
    changed={n for n in old if old[n]!=new[n]}
    assert changed=={'rtl/cpu_core.v','rtl/frontend/rv32_fetch_frontend.v','rtl/predictor/rv32_banked_predictor.v'}
    assert changed==set(audit['compiled_input_differences'])
    for name in old:
        assert sha(ROOT/name)==old[name], 'Main changed since baseline: '+name
        assert sha(STAGE/name)==new[name], 'Verified stage changed: '+name
    previous_profile=read(ROOT/'build/cpu2026/verified_static_completion2_profile_20261003.json')
    assert previous_profile['parameter_overrides']==manifest['parameter_overrides']
    for name in old:
        path=BACKUP/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,path)
        assert sha(path)==old[name]
    for name in sorted(changed):shutil.copyfile(STAGE/name,ROOT/name)
    assert all(sha(ROOT/n)==h for n,h in new.items())
    result=dict(status='NATIVE_VERIFIED_SOURCE_ADOPTED_PPA_PENDING',source_root=str(ROOT),
                verified_source_root=str(STAGE),verified_native_audit=str(audit_path),
                verified_native_audit_sha256=sha(audit_path),build_manifest=str(manifest_path),
                build_manifest_sha256=sha(manifest_path),source_sha256=new,old_source_sha256=old,
                old_source_backup=str(BACKUP),changed_files=sorted(changed),
                parameter_overrides=manifest['parameter_overrides'],
                effective_parameters=previous_profile['effective_parameters'],
                original_cases=29,added_cases=8,protocol_configurations=39,
                known_addi255_defect_fixed=True,geomean_ipc=audit['benchmark_geomean_ipc'],
                new_area_pending=True,new_frequency_pending=True,no_old_ppa_reuse=True,
                tier3_achieved=False,adopter_sha256=sha(__file__))
    (BACKUP/'adoption.json').write_text(json.dumps(result,indent=2)+'\n')
    profile=ROOT/'build/cpu2026/native_verified_legal_addi_profile_20261003.json'
    assert not profile.exists();profile.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],changed_files=result['changed_files'],
                         all43_main_inputs_match_verified_build=True,profile=str(profile)),indent=2))


if __name__=='__main__':main()
