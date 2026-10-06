"""Freeze an isolated eight-stage CPU candidate from the verified parallel-match CPU."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from pipeline8_transform import transform

MODULES = {'rtl/cache/rv32_icache_nonblocking.v': 'rv32_icache_nonblocking'}
ATTRIBUTE = b'(* keep_hierarchy = 1 *)\n'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ('source-root', 'baseline-native', 'outdir'):
        ap.add_argument('--'+arg, type=Path, required=True)
    a = ap.parse_args()
    source, out = a.source_root.resolve(), a.outdir.resolve()
    assert not out.exists(), 'Preserve previous candidate'
    native = read(a.baseline_native)
    assert native['status'] == 'VERIFIED' and native['cases'] == 29
    assert native['added_native_cases'] == 8 and native['additional_isa_cases'] == 16
    assert Path(native['source_roots'][1]).resolve() == source
    evidence = {str(a.baseline_native.resolve()): sha(a.baseline_native)}
    for name, expected in native['input_sha256'].items():
        assert sha(name) == expected.lower(), name
    manifest_path = Path(native['gate'])/'build/build_manifest.json'
    manifest = read(manifest_path)
    assert manifest['parameter_overrides']['ICACHE_TAG_MATCH_PARALLEL'] == 1
    originals = {n:h.lower() for n,h in manifest['source_sha256'].items()}
    assert len(originals) == 43
    dependencies = read(source/'measurement_dependencies.json')['input_sha256']
    files = dependencies | originals
    for name, expected in files.items():
        assert sha(source/name) == expected.lower(), name
    framework = out/'.deps/RISC-V-CPU-2026'
    framework.parent.mkdir(parents=True)
    revision = '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',
                    str(source/'.deps/RISC-V-CPU-2026'),str(framework)], check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision], check=True)
    for name in files:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
    transform(out)
    changed = {n for n,h in originals.items() if sha(out/n) != h}
    assert changed == {'rtl/cpu_core.v','rtl/backend/rv32_backend_joint.v','rtl/course/student_top.v'}
    sta = out/'.deps/OpenSTA/build/sta'
    sta.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source/'.deps/OpenSTA/build/sta',sta)
    runtime_rel = Path('.deps/oss-cad-suite-install/oss-cad-suite')
    runtime_source, runtime_target = source/runtime_rel, out/runtime_rel
    assert not runtime_target.exists()
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    esc = lambda p: "'"+str(p).replace("'", "''")+"'"
    subprocess.run([shutil.which('pwsh.exe'),'-NoProfile','-Command',
                    'New-Item -ItemType Junction -Path '+esc(runtime_target)+
                    ' -Target '+esc(runtime_source)+' | Out-Null'], check=True)
    repair = read(source/'tool_runtime_repair.json')
    binaries = ('bin/verilator_bin.exe','bin/yosys.exe','bin/yosys-abc.exe')
    runtime_hashes = {n:sha(runtime_target/n) for n in binaries}
    assert all(h == repair['runtime_sha256'][n] for n,h in runtime_hashes.items())
    for name, expected in dependencies.items():
        assert sha(out/name) == expected.lower(), name
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'],text=True).strip()
    for name, expected in files.items():
        assert sha(source/name) == expected.lower(), name
    (out/'measurement_dependencies.json').write_text(json.dumps(dict(
        status='COMPLETE',source_root=str(source),stage_root=str(out),
        input_sha256=dependencies),indent=2)+'\n',encoding='utf-8')
    result = dict(status='STAGED',source_root=str(source),baseline_manifest=str(manifest_path),
        baseline_native_audit=str(a.baseline_native.resolve()),baseline_sha256=originals,
        staged_sha256={n:sha(out/n) for n in originals},changed_files=sorted(changed),
        parameters=manifest['parameter_overrides'] | {'DECODE_PIPELINE':1,'ISSUE_PIPELINE':1},
        transformation_sha256=sha(Path(__file__).with_name('pipeline8_transform.py')),
        added_registered_boundaries=['decoded bundle to rename','RS select to execution'],
        measurement_dependencies_sha256=dependencies,validation_evidence_sha256=evidence,
        original_framework_revision=revision,opensta_sha256=sha(sta),
        runtime_junction_source=str(runtime_source),runtime_binary_sha256=runtime_hashes,
        preparer_sha256=sha(__file__),no_cpu_ppa_claim=True)
    (out/'staging_manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='STAGED',changed_files=sorted(changed),
                         source_inputs=43,added_pipeline_stages=2)))


if __name__ == '__main__':
    main()
