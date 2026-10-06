"""Audit the CDB3 plus proven frontend and I-cache rewrites against actual CDB3.

Require exactly four source changes, two default-off/trial-on adapters, all
other parameters unchanged, and exact cycles/retirement/exits for all29+8
native cases. Preserve all original driver, memory, image and source checks.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['gold', 'gate', 'gold-source', 'gate-source', 'out']:
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists(), 'Preserve earlier audit evidence'
    inputs = {}

    def record(path, expected=None):
        path = path.resolve()
        actual = sha(path)
        assert expected is None or actual == expected.lower(), 'Changed input: '+str(path)
        assert str(path) not in inputs or inputs[str(path)] == actual
        inputs[str(path)] = actual

    expected_files = {'rtl/cache/rv32_icache_nonblocking.v','rtl/frontend/rv32_fetch_frontend.v','rtl/cpu_core.v','rtl/course/student_top.v'}
    new_parameters = {'ICACHE_LOCAL_RESPONSE_READY': 1, 'FRONTEND_NARROW_OCCUPANCY': 1}
    for name in ('rtl/cpu_core.v','rtl/course/student_top.v'):
        code=(args.gold_source/name).read_text()
        before='    parameter integer ICACHE_MSHRS = 8,'
        assert code.count(before)==1
        code=code.replace(before,'    parameter integer ICACHE_LOCAL_RESPONSE_READY = 0,\n'+before)
        before='.MSHR_ENTRIES(ICACHE_MSHRS),' if name.endswith('cpu_core.v') else '.ICACHE_MSHRS(ICACHE_MSHRS),'
        after=before+' .LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY),' if name.endswith('cpu_core.v') else before+' .ICACHE_LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY),'
        assert code.count(before)==1
        code=code.replace(before,after)
        before='    parameter integer FETCH_QUEUE_DEPTH = 16,'
        assert code.count(before)==1
        code=code.replace(before,'    parameter integer FRONTEND_NARROW_OCCUPANCY = 0,\n'+before)
        before='.FQ_DEPTH(FETCH_QUEUE_DEPTH),' if name.endswith('cpu_core.v') else '.FETCH_QUEUE_DEPTH(FETCH_QUEUE_DEPTH),'
        after=before+' .NARROW_OCCUPANCY(FRONTEND_NARROW_OCCUPANCY),' if name.endswith('cpu_core.v') else before+' .FRONTEND_NARROW_OCCUPANCY(FRONTEND_NARROW_OCCUPANCY),'
        assert code.count(before)==1
        assert code.replace(before,after)==(args.gate_source/name).read_text()
    extra_path=args.gate/'legal_addi_native/report.json'
    record(extra_path);extra=read(extra_path)
    assert extra['status']=='COMPLETE' and len(extra['results'])==8 and extra['memory_latency']==20
    assert all(row['status']=='PASS' and row['result']==256 for row in extra['results'])
    for name,h in extra['input_sha256'].items():record(Path(name),h)
    assert extra['input_sha256'][str((args.gate/'build/build_manifest.json').resolve())]==sha(args.gate/'build/build_manifest.json')
    counts = dict(benchmark=6, basic=5, simulator=17, boundary=1)
    benchmark_names = {'median', 'multiply', 'qsort', 'rsort', 'towers', 'vvadd'}
    profiles, manifests, reports = [], [], []
    for index, (root, source) in enumerate([(args.gold, args.gold_source), (args.gate, args.gate_source)]):
        root, source = root.resolve(), source.resolve()
        path = root/'build/build_manifest.json'
        record(path)
        manifest = read(path)
        assert manifest['format'] == 'course-axi-frozen-build-v1'
        text = (source/'rtl/course/student_top.v').read_text().split(') (', 1)[0]
        defaults = {k: int(v) for k, v in re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)', text)}
        assert set(manifest['parameter_overrides']) <= set(defaults)
        if index:
            assert defaults['ICACHE_LOCAL_RESPONSE_READY'] == 0 and defaults['FRONTEND_NARROW_OCCUPANCY'] == 0
        profile = defaults | manifest['parameter_overrides']
        assert profile['RS_ENTRIES'] == 12 and profile['CDB_WIDTH'] == 3
        profiles.append(profile)
        manifests.append(manifest)
        assert len(manifest['source_sha256']) == 43
        for name, expected in manifest['source_sha256'].items():
            record(source/name, expected)
        record(Path(manifest['executable']), manifest['executable_sha256'])
        driver = Path(manifest['generated_driver'])
        record(driver, manifest['generated_driver_sha256'])
        original = (source/'.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
        observation = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
        observed = driver.read_text()
        assert observed.count(observation) == 1 and observed.replace(observation, '') == original
        suites = {}
        for suite, count in counts.items():
            report_path = root/(suite+'.json')
            record(report_path)
            report = read(report_path)
            assert report['status'] == 'COMPLETE' and report['suite'] == suite
            assert Path(report['build_manifest']).resolve() == path
            assert Path(report['evaluated_source_root']).resolve() == source
            assert report['evaluates_current_worktree'] == (not report['current_source_differences'])
            # Historical current-worktree differences may change after an adoption; every actual evaluated source hash is checked below.
            assert len(report['results']) == count and report['pi_excluded']
            memory = report['external_memory']
            assert memory['latency_cycles'] == 20 and memory['external_ram_bytes'] == 268435456
            assert memory['word_bytes'] == 4 and memory['shared_ar_r'] and memory['exit_at_b_handshake']
            for name, expected in report['source_sha256'].items():
                record(Path(name), expected)
            cases = report['results']
            assert len({r['name'] for r in cases}) == count
            assert sum(r['cycles'] for r in cases) == report['total_cycles']
            assert sum(r['instret'] for r in cases) == report['total_instret']
            for row in cases:
                assert row['status'] == 'passed' and row['return_u32'] == row['expected_u32']
                assert row['cycles'] > 0 and row['instret'] > 0
                assert math.isclose(row['ipc'], row['instret']/row['cycles'], rel_tol=1e-12)
                record(Path(row['image']))
            geomean = math.exp(sum(math.log(r['instret']/r['cycles']) for r in cases)/count)
            assert math.isclose(geomean, report['geomean_ipc'], rel_tol=1e-12)
            if suite == 'benchmark':
                assert {r['name'] for r in cases} == benchmark_names
            suites[suite] = report
        reports.append(suites)
    gold, gate = manifests
    normalize = lambda m: {n: h.lower() for n, h in m['source_sha256'].items()}
    old, new = normalize(gold), normalize(gate)
    assert old.keys() == new.keys()
    changed = {n: [old[n], new[n]] for n in old if old[n] != new[n]}
    assert set(changed) == expected_files
    assert gold['configuration'] == gate['configuration'] and gold['external_memory'] == gate['external_memory']
    assert gold['generated_driver_sha256'].lower() == gate['generated_driver_sha256'].lower()
    assert set(profiles[1])-set(profiles[0]) == set(new_parameters)
    assert all(profiles[0][k] == profiles[1][k] for k in profiles[0])
    assert all(profiles[1][k] == v for k, v in new_parameters.items())
    stage_path = args.gate_source/'staging_manifest.json'
    record(stage_path)
    stage = read(stage_path)
    assert {k:v.lower() for k,v in stage['baseline_sha256'].items()} == old
    assert {k:v.lower() for k,v in stage['staged_sha256'].items()} == new
    assert new['rtl/cache/rv32_icache_nonblocking.v']==stage['component_sha256']
    component=Path(stage['component_root'])
    record(component/'candidate_manifest.json')
    cm=read(component/'candidate_manifest.json')
    assert cm['baseline_sha256']==old['rtl/cache/rv32_icache_nonblocking.v']
    assert cm['files_sha256']['rtl/cache/rv32_icache_nonblocking.v']==new['rtl/cache/rv32_icache_nonblocking.v']
    for evidence, expected in stage['validation_evidence_sha256'].items():
        record(Path(evidence), expected)
        if Path(evidence).suffix == '.json':
            for name,h in read(Path(evidence)).get('input_sha256',{}).items():record(Path(name),h)
    for name,h in stage['measurement_dependencies_sha256'].items():record(args.gate_source/name,h)
    assert stage['cycle_equivalence_required'] and stage['replacement_policy_protection'] == 1
    assert cm['default_protect_pending_hit'] == cm['formal_policy_protection'] == 1
    assert cm['default_local_response_ready'] == 0 and cm['formal_prefetch_distance'] == 7
    formal_path=Path('F:/CPU2026Proofs/icache_local_response_ready_formal_20261003/report.json')
    record(formal_path,stage['validation_evidence_sha256'][str(formal_path)])
    formal=read(formal_path)
    proofs=[r for r in formal['results'] if r['phase']=='formal']
    assert formal['status']=='COMPLETE' and len(proofs)==4 and all(r['status']=='PROVEN' for r in proofs)
    assert formal['no_input_assumptions'] and formal['all_sram_pin_contracts_included']
    assert formal['sram_read_data_shared_unrestricted'] and not formal['proves_sram_storage_internals']
    frontend=Path(stage['frontend_component_root']); fm_path=frontend/'candidate_manifest.json'
    record(fm_path); fm=read(fm_path)
    assert fm['baseline_sha256']==old['rtl/frontend/rv32_fetch_frontend.v']
    assert fm['candidate_sha256']==new['rtl/frontend/rv32_fetch_frontend.v']==stage['frontend_component_sha256']
    assert fm['default_narrow_occupancy']==0 and fm['actual_depth16_storage_bits']==[32,5]
    for name,h in fm['files_sha256'].items():record(frontend/name,h)
    fproof_path=Path('F:/CPU2026Proofs/frontend_bounded_count_20261003/report.json')
    record(fproof_path,stage['validation_evidence_sha256'][str(fproof_path)])
    fproof=read(fproof_path); rows=[r for r in fproof['results'] if r['phase']=='formal']
    assert fproof['status']=='COMPLETE' and len(rows)==9 and all(r['status']=='PROVEN' for r in rows)
    assert sum(r['equiv_cells'] for r in rows)==26767 and fproof['no_input_assumptions']
    gold_extra_path=args.gold/'legal_addi_native/report.json'
    record(gold_extra_path)
    gold_extra=read(gold_extra_path)
    assert gold_extra['status']=='COMPLETE'
    for name,h in gold_extra['input_sha256'].items():record(Path(name),h)
    assert gold_extra['results']==extra['results'], 'Additional eight cases must preserve cycles and values'


    rows = []
    for suite in counts:
        left, right = reports[0][suite], reports[1][suite]
        assert left['external_memory'] == right['external_memory']
        right_by_name = {r['name']: r for r in right['results']}
        for a in left['results']:
            b = right_by_name[a['name']]
            for field in ['expected_u32', 'return_u32', 'instret', 'cycles']:
                assert a[field] == b[field], 'Mismatch: '+suite+'/'+a['name']+'/'+field
            assert Path(a['image']).resolve() == Path(b['image']).resolve()
            rows.append(dict(suite=suite, name=a['name'], cycles=[a['cycles'],b['cycles']], instret=a['instret'], return_u32=a['return_u32']))
    record(Path(__file__))
    for name, expected in inputs.items():
        assert sha(Path(name)) == expected, 'Input changed during audit: '+name
    result = dict(status='VERIFIED', scope=__doc__, cases=len(rows),
                  gold=str(args.gold.resolve()), gate=str(args.gate.resolve()),
                  source_roots=[str(args.gold_source.resolve()), str(args.gate_source.resolve())],
                  compiled_input_differences=changed, added_parameters=new_parameters,
                  all_shared_parameters_identical=True, all_retirement_and_exits_identical=True, all_cycles_identical=True,
                  added_native_cases=8, baseline_geomean_ipc=reports[0]['benchmark']['geomean_ipc'],
                  benchmark_geomean_ipc=reports[1]['benchmark']['geomean_ipc'],
                  results=rows, input_sha256=inputs, cpu_ppa_claim=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','cases','added_parameters','all_retirement_and_exits_identical','benchmark_geomean_ipc','cpu_ppa_claim']}, indent=2))


if __name__ == '__main__':
    main()
