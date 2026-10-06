"""Stage the proven local-response-ready rewrite on the repaired, measured CPU.

Keep replacement protection enabled, all existing parameters unchanged, and
change only the I-cache plus two default-off parameter adapters. Require the
original protocols, directed replay tests, all four controller/SRAM-pin proofs,
and the complete component PPA pair before any whole-CPU measurement.
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


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'baseline-native', 'outdir'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    source, out = a.source_root.resolve(), a.outdir.resolve()
    assert not out.exists(), 'Preserve existing staging evidence'
    native = read(a.baseline_native)
    assert native['status'] == 'VERIFIED' and native['cases'] == 29 and native['added_native_cases'] == 8
    assert native['protocol_configurations'] == 39 and native['known_baseline_addi255_defect_fixed']
    assert Path(native['source_roots'][1]).resolve() == source
    result_path = Path(native['gate'])/'verified_cpu_result.json'
    assert read(result_path)['status'] == 'VERIFIED'
    base_path = Path(native['gate'])/'build/build_manifest.json'
    base = read(base_path)
    originals = {n:h.lower() for n,h in base['source_sha256'].items()}
    dependencies = read(source/'measurement_dependencies.json')['input_sha256']
    files = dependencies | originals
    for name, expected in files.items():
        assert sha(source/name) == expected, name
    component = Path('F:/CPU2026Candidates/icache_local_response_ready_20261003')
    component_manifest = component/'candidate_manifest.json'
    cm = read(component_manifest)
    assert cm['baseline_sha256'] == originals['rtl/cache/rv32_icache_nonblocking.v']
    assert cm['formal_policy_protection'] == cm['default_protect_pending_hit'] == 1
    assert cm['formal_prefetch_distance'] == 7 and cm['default_local_response_ready'] == 0
    for name, expected in cm['files_sha256'].items():
        assert sha(component/name) == expected, name
    evidence = [a.baseline_native.resolve(), result_path, component_manifest,
                Path('F:/CPU2026Proofs/icache_local_response_ready_protocol_20261003/report.json'),
                Path('F:/CPU2026Proofs/icache_local_response_ready_replay_20261003/report.json'),
                Path('F:/CPU2026Proofs/icache_local_response_ready_formal_20261003/report.json'),
                Path('F:/CPU2026Probes/icache_local_response_ready_protect1_actual128_20261003/independent_component_verification.json')]
    assert read(evidence[3])['status'] == 'COMPLETE' and len(read(evidence[3])['results']) == 32
    assert read(evidence[4])['status'] == 'COMPLETE' and len(read(evidence[4])['results']) == 88
    formal = read(evidence[5])
    assert formal['status'] == 'COMPLETE' and formal['no_input_assumptions']
    assert formal['all_sram_pin_contracts_included'] and formal['sram_read_data_shared_unrestricted']
    assert formal['no_outputs_or_state_fields_omitted'] and not formal['proves_sram_storage_internals']
    rows = [r for r in formal['results'] if r['phase'] == 'formal']
    assert len(rows) == 4 and all(r['status'] == 'PROVEN' for r in rows)
    assert sum(r['equiv_cells'] for r in rows) == 11782
    for row in rows:
        c = row['parameters']
        stem = 'formal_l{CACHE_LINES}_w{CACHE_WAYS}_m{MSHR_ENTRIES}_e{EPOCH_WIDTH}'.format(**c)
        for suffix, field in (('.log', 'log_sha256'), ('.ys', 'script_sha256'), ('.prepared.json', 'prepared_sha256')):
            path = evidence[5].parent/(stem+suffix)
            assert sha(path) == row[field], path
            evidence.append(path)
        assert set(row['raw_sram_pin_contracts']) == {'data_array.'+s for s in ('clk','en','we','wmask','addr','wdata','rdata')}
    assert read(evidence[6])['status'] == 'VERIFIED'
    for path in evidence[:7]:
        for name, expected in read(path).get('input_sha256', {}).items():
            assert sha(name) == expected, name
    framework = out/'.deps/RISC-V-CPU-2026'
    framework.parent.mkdir(parents=True)
    revision = '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(source/'.deps/RISC-V-CPU-2026'),str(framework)], check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision], check=True)
    for name in files:
        path = out/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, path)
    (out/'measurement_dependencies.json').write_text(json.dumps(dict(status='COMPLETE', source_root=str(source), stage_root=str(out), input_sha256=dependencies), indent=2)+'\n', encoding='utf-8')
    modified = {'rtl/cache/rv32_icache_nonblocking.v', 'rtl/cpu_core.v', 'rtl/course/student_top.v'}
    for name in modified:
        path = out/'baseline'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, path)
    shutil.copyfile(component/'rtl/cache/rv32_icache_nonblocking.v', out/'rtl/cache/rv32_icache_nonblocking.v')
    for name in ('rtl/cpu_core.v', 'rtl/course/student_top.v'):
        path = out/name
        code = replace(path.read_text(), '    parameter integer ICACHE_MSHRS = 8,',
                       '    parameter integer ICACHE_LOCAL_RESPONSE_READY = 0,\n    parameter integer ICACHE_MSHRS = 8,')
        if name.endswith('cpu_core.v'):
            code = replace(code, '.MSHR_ENTRIES(ICACHE_MSHRS),',
                           '.MSHR_ENTRIES(ICACHE_MSHRS), .LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY),')
        else:
            code = replace(code, '.ICACHE_MSHRS(ICACHE_MSHRS),',
                           '.ICACHE_MSHRS(ICACHE_MSHRS), .ICACHE_LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY),')
        path.write_text(code)
    assert {n for n,h in originals.items() if sha(out/n) != h} == modified
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'], text=True).strip()
    sta = out/'.deps/OpenSTA/build/sta'
    sta.parent.mkdir(parents=True)
    shutil.copyfile(source/'.deps/OpenSTA/build/sta', sta)
    stage = dict(status='STAGED', source_root=str(source), baseline_manifest=str(base_path),
                 baseline_native_audit=str(a.baseline_native.resolve()), baseline_sha256=originals,
                 staged_sha256={n:sha(out/n) for n in originals}, changed_files=sorted(modified),
                 parameters=base['parameter_overrides'] | dict(ICACHE_LOCAL_RESPONSE_READY=1),
                 component_root=str(component), component_sha256=cm['files_sha256']['rtl/cache/rv32_icache_nonblocking.v'],
                 measurement_dependencies_sha256=dependencies, framework_revision=revision, opensta_sha256=sha(sta),
                 validation_evidence_sha256={str(path):sha(path) for path in evidence},
                 cycle_equivalence_required=True, replacement_policy_protection=1,
                 no_cpu_ppa_claim=True, preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(stage, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status='STAGED', changed_files=sorted(modified), parameter='ICACHE_LOCAL_RESPONSE_READY=1', replacement_policy_protection=1), indent=2))


if __name__ == '__main__':
    main()
