"""Expose the existing RS age-width parameter on the verified parallel-match CPU.

The RS RTL is unchanged. Numeric arbitration may differ on wrap, so native
cycles must be measured anew; no cycle equivalence or CPU PPA is assumed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def replace(code, before, after):
    assert code.count(before) == 1, before
    return code.replace(before, after)


def adapt(name, code):
    code = replace(code, '    parameter integer RS_ALLOC_STATIC_WRITE = 0,',
                   '    parameter integer RS_AGE_WIDTH = 32,\n    parameter integer RS_ALLOC_STATIC_WRITE = 0,')
    if name.endswith('rv32_backend_joint.v'):
        return replace(code, '.ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE)) rs (',
                       '.ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE), .AGE_WIDTH(RS_AGE_WIDTH)) rs (')
    return replace(code, '.RS_ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE),',
                   '.RS_ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE), .RS_AGE_WIDTH(RS_AGE_WIDTH),')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'baseline-native', 'outdir'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source_root.resolve(), args.outdir.resolve()
    assert not out.exists(), 'Preserve previous staged evidence'
    native = read(args.baseline_native)
    assert native['status'] == 'VERIFIED' and native['cases'] == 29
    assert native['added_native_cases'] == 8 and native['additional_isa_cases'] == 16
    assert native['all_cycles_identical'] and Path(native['source_roots'][1]).resolve() == source
    base_path = Path(native['gate'])/'build/build_manifest.json'
    base = read(base_path)
    originals = {n:h.lower() for n,h in base['source_sha256'].items()}
    assert len(originals) == 43 and base['parameter_overrides']['ICACHE_TAG_MATCH_PARALLEL'] == 1
    component = Path('F:/CPU2026Candidates/rs_age_width_20261003')
    component_manifest = component/'candidate_manifest.json'
    protocol_path = Path('F:/CPU2026Proofs/rs_age_width_20261003/report.json')
    pair_path = Path('F:/CPU2026Probes/rs_age_width_actual12_20261003/independent_component_verification.json')
    cm, protocol, pair = map(read, (component_manifest, protocol_path, pair_path))
    assert cm['unchanged_rtl_sha256'] == originals['rtl/backend/rv32_reservation_station.v']
    assert protocol['status'] == 'COMPLETE' and len(protocol['results']) == 28
    assert pair['status'] == 'VERIFIED' and pair['effective_parameter_differences'] == {'AGE_WIDTH':[8,32]}
    assert all(r['parameters']['ENTRIES'] == 12 and r['parameters']['TAG_WIDTH'] == 17 for r in pair['results'])
    by_age = {r['parameters']['AGE_WIDTH']:r for r in pair['results']}
    assert float(by_age[8]['area_um2']) < float(by_age[32]['area_um2'])
    assert by_age[8]['fmax_mhz'] > by_age[32]['fmax_mhz']
    evidence = [args.baseline_native.resolve(), component_manifest, protocol_path, pair_path]
    for path in evidence:
        for name, expected in read(path).get('input_sha256', {}).items():
            assert sha(name) == expected.lower(), name
    dependencies = read(source/'measurement_dependencies.json')['input_sha256']
    files = dependencies | originals
    for name, expected in files.items(): assert sha(source/name) == expected.lower(), name
    framework = out/'.deps/RISC-V-CPU-2026'
    framework.parent.mkdir(parents=True)
    revision = '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(source/'.deps/RISC-V-CPU-2026'),str(framework)],check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision],check=True)
    for name in files:
        target = out/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
    modified = {'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v'}
    for name in modified:
        path = out/name
        backup = out/'baseline'/name; backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,backup)
        path.write_text(adapt(name,path.read_text()))
    assert {n for n,h in originals.items() if sha(out/n)!=h} == modified
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'],text=True).strip()
    sta = out/'.deps/OpenSTA/build/sta'; sta.parent.mkdir(parents=True)
    shutil.copyfile(source/'.deps/OpenSTA/build/sta',sta)
    runtime_rel = Path('.deps/oss-cad-suite-install/oss-cad-suite')
    runtime_source, runtime_target = source/runtime_rel, out/runtime_rel
    runtime_target.parent.mkdir(parents=True)
    repair_path = source/'tool_runtime_repair.json'
    repair = read(repair_path)
    assert repair['status'] == 'VERIFIED' and repair['frozen_inputs_unchanged']
    # Reuse the already byte-verified host runtime. Hardware, libraries and
    # all measurement scripts remain independent copies in this stage.
    esc = lambda p: "'"+str(p).replace("'","''")+"'"
    subprocess.run([shutil.which('pwsh.exe'),'-NoProfile','-Command',
                    'New-Item -ItemType Junction -Path '+esc(runtime_target)+' -Target '+esc(runtime_source)+' | Out-Null'],check=True)
    binaries = ('bin/verilator_bin.exe','bin/yosys.exe','bin/yosys-abc.exe')
    runtime_hashes = {n:sha(runtime_target/n) for n in binaries}
    assert all(runtime_hashes[n] == repair['runtime_sha256'][n] for n in binaries)
    evidence.append(repair_path)
    (out/'measurement_dependencies.json').write_text(json.dumps(dict(status='COMPLETE',source_root=str(source),stage_root=str(out),input_sha256=dependencies),indent=2)+'\n')
    result = dict(status='STAGED', source_root=str(source), baseline_manifest=str(base_path),
        baseline_native_audit=str(args.baseline_native.resolve()), baseline_sha256=originals,
        staged_sha256={n:sha(out/n) for n in originals}, changed_files=sorted(modified),
        parameters=base['parameter_overrides'] | dict(RS_AGE_WIDTH=8), default_rs_age_width=32,
        rs_rtl_unchanged=True, rs_sha256=originals['rtl/backend/rv32_reservation_station.v'],
        measurement_dependencies_sha256=dependencies, framework_revision=revision, opensta_sha256=sha(sta),
        runtime_junction_source=str(runtime_source), runtime_binary_sha256=runtime_hashes,
        validation_evidence_sha256={str(p):sha(p) for p in evidence},
        cycle_equivalence_required=False, changes_issue_priority_on_wrap=True,
        no_cpu_ppa_claim=True, preparer_sha256=sha(Path(__file__)))
    (out/'staging_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','changed_files','rs_rtl_unchanged','cycle_equivalence_required','no_cpu_ppa_claim')},indent=2))


if __name__ == '__main__':
    main()
