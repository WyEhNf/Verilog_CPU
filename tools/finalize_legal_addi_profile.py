"""Bind the adopted repair to its own completed native and full-SRAM PPA evidence."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return Path(path).read_text(encoding='utf-8-sig')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    old_path = ROOT/'build/cpu2026/native_verified_legal_addi_profile_20261003.json'
    profile = json.loads(read(old_path))
    native_path = Path(profile['verified_native_audit'])
    result_path = native_path.parent/'verified_cpu_result.json'
    native, result = [json.loads(read(p)) for p in (native_path, result_path)]
    assert native['status'] == result['status'] == 'VERIFIED'
    assert native['cases'] == result['all_correctness_cases'] == 29
    assert native['added_native_cases'] == 8 and native['protocol_configurations'] == 39
    assert native['known_baseline_addi255_defect_fixed']
    assert result['parameters'] == profile['effective_parameters']
    assert result['geomean_ipc'] == profile['geomean_ipc']
    inputs = {str(p): sha(p) for p in (old_path, native_path, result_path, Path(__file__))}
    for evidence in (native, result):
        for path, expected in evidence['input_sha256'].items():
            assert sha(path) == expected.lower(), path
            inputs[path] = expected.lower()
    for name, expected in profile['source_sha256'].items():
        assert sha(ROOT/name) == expected.lower(), 'Main differs: '+name
        inputs[str(ROOT/name)] = expected.lower()
    assert len(profile['source_sha256']) == 43 and result['sram_instances'] == 37
    profile.update(status='VERIFIED_SOURCE_ADOPTED_FULL_PPA', new_area_pending=False,
                   new_frequency_pending=False, verified_cpu_result=str(result_path),
                   verified_cpu_result_sha256=sha(result_path), area=result['area'],
                   fmax_mhz=result['fmax_mhz'], minimum_period_ns=result['minimum_period_ns'],
                   sram_instances=result['sram_instances'], leaf_instances=result['leaf_instances'],
                   netlist_sha256=result['netlist_sha256'], tier3_checks=result['tier3_checks'],
                   tier3_achieved=result['tier3_achieved'], input_sha256=inputs,
                   original_native_adoption_profile=str(old_path),
                   correctness_scope='39 protocol configurations and 29+8 native cases; finite tests are not a full ISA proof.')
    out = ROOT/'build/cpu2026/verified_legal_addi_profile_20261003.json'
    assert not out.exists(), 'Preserve earlier finalized profile'
    out.write_text(json.dumps(profile, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=profile['status'], profile=str(out), area=result['area'],
                         ipc=result['geomean_ipc'], fmax_mhz=result['fmax_mhz'],
                         tier3_achieved=result['tier3_achieved']), indent=2))


if __name__ == '__main__':
    main()
