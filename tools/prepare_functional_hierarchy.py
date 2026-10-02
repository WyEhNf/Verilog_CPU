"""Stage a whole-CPU mapping experiment preserving real functional modules.

Only keep_hierarchy attributes change. Every RTL byte otherwise matches the
verified baseline. Original RAM validator, libraries, default ABC and timing
remain unchanged; no cell placeholders or omitted hierarchy are permitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

MODULES = {
    'rtl/frontend/rv32_fetch_frontend.v': 'rv32_fetch_frontend',
    'rtl/cache/rv32_icache_nonblocking.v': 'rv32_icache_nonblocking',
    'rtl/cache/rv32_dcache_nonblocking.v': 'rv32_dcache_nonblocking',
    'rtl/backend/rv32_backend_joint.v': 'rv32_backend_joint',
    'rtl/backend/rv32_reservation_station.v': 'rv32_reservation_station',
    'rtl/backend/rv32_rob.v': 'rv32_rob',
    'rtl/backend/rv32_lsq.v': 'rv32_lsq',
    'rtl/rv32_physical_register_file.v': 'rv32_physical_register_file',
    'rtl/rv32_rename_unit.v': 'rv32_rename_unit',
    'rtl/backend/rv32_completion_network.v': 'rv32_completion_network',
    'rtl/backend/rv32m_mdu_reservation_station.v': 'rv32m_mdu_reservation_station',
    'rtl/predictor/rv32_banked_predictor.v': 'rv32_banked_predictor',
    'rtl/predictor/rv32_branch_predictor.v': 'rv32_branch_predictor',
    'rtl/course/rv32_axi_lite_bridge.v': 'rv32_axi_lite_bridge',
}
ATTRIBUTE = b'(* keep_hierarchy = 1 *)\n'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--baseline-result', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source_root.resolve(), args.outdir.resolve()
    assert not out.exists()
    verified = read(args.baseline_result)
    assert verified['status'] == 'VERIFIED' and verified['all_correctness_cases'] == 29
    assert Path(verified['evaluated_source_root']).resolve() == source
    for name, value in verified['input_sha256'].items():
        assert sha(name) == value, 'Changed verified baseline: '+name
    manifest_path = Path(verified['directory'])/'build/build_manifest.json'
    manifest = read(manifest_path)
    originals = {n:h.lower() for n,h in manifest['source_sha256'].items()}
    dependencies = read(source/'measurement_dependencies.json')['input_sha256']
    files = dependencies | originals
    assert set(MODULES) <= set(originals)
    for name, value in files.items():
        assert sha(source/name) == value.lower(), 'Changed baseline source: '+name
    framework = out/'.deps/RISC-V-CPU-2026'
    framework.parent.mkdir(parents=True)
    revision = '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout',
                    str(source/'.deps/RISC-V-CPU-2026'), str(framework)], check=True)
    subprocess.run(['git', '-C', str(framework), 'checkout', '--detach', revision], check=True)
    for name in files:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
    dependency_manifest = dict(status='COMPLETE', source_root=str(source), stage_root=str(out),
                               purpose='Byte-identical inherited measurement dependencies',
                               input_sha256={n:sha(out/n) for n in dependencies})
    (out/'measurement_dependencies.json').write_text(json.dumps(dependency_manifest,indent=2)+'\n')
    normalized = {}
    for name, module in MODULES.items():
        path = out/name
        original = path.read_bytes()
        needle = ('module '+module+' #(').encode()
        assert original.count(needle) == 1
        assert ATTRIBUTE+needle not in original
        candidate = original.replace(needle, ATTRIBUTE+needle)
        assert candidate.replace(ATTRIBUTE+needle, needle) == original
        path.write_bytes(candidate)
        normalized[name] = hashlib.sha256(candidate.replace(ATTRIBUTE+needle, needle)).hexdigest()
        assert normalized[name] == originals[name]
    assert {n for n,h in originals.items() if sha(out/n) != h} == set(MODULES)
    for name, value in files.items():
        assert sha(source/name) == value.lower()
    assert not subprocess.check_output(['git', '-C', str(framework), 'status', '--porcelain'], text=True).strip()
    sta = out/'.deps/OpenSTA/build/sta'
    sta.parent.mkdir(parents=True)
    shutil.copyfile(source/'.deps/OpenSTA/build/sta', sta)
    assert sha(sta) == sha(source/'.deps/OpenSTA/build/sta')
    result = dict(status='STAGED', experiment='Actual functional module hierarchy, wholeCPU mapping tradeoff',
                  source_root=str(source), baseline_result=str(args.baseline_result.resolve()),
                  baseline_manifest=str(manifest_path), baseline_sha256=originals,
                  staged_sha256={n:sha(out/n) for n in originals},
                  changed_files=sorted(MODULES), preserved_modules=MODULES,
                  exact_attribute_bytes=ATTRIBUTE.decode(), normalized_source_sha256=normalized,
                  parameters=manifest['parameter_overrides'], no_effective_parameter_change=True,
                  measurement_dependencies_sha256={n:sha(out/n) for n in dependencies},
                  original_framework_revision=revision, opensta_sha256=sha(sta),
                  no_logic_or_state_or_port_or_cycle_change=True, no_cpu_ppa_claim=True,
                  preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(status='STAGED', compiled_inputs=len(originals),
                         preserved_modules=MODULES, normalized_all_changes_to_original=True), indent=2))


if __name__ == '__main__':
    main()
