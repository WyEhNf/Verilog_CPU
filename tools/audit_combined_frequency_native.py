"""Audit the complete combined frequency candidate and its single final protocol/native batch."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import shutil
from combined_frequency_transform import transform, PARAMETERS


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

    expected_files = {'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v','rtl/backend/rv32_rob.v','rtl/frontend/rv32_fetch_frontend.v','rtl/cache/rv32_icache_nonblocking.v','rtl/cache/rv32_dcache_nonblocking.v'}
    new_parameters = {k:v for k,v in PARAMETERS.items() if k not in ('DECODE_PIPELINE','ISSUE_PIPELINE')}
    # Replay the documented transformation and compare every changed byte.
    with tempfile.TemporaryDirectory(prefix='pipeline8_replay_', dir='F:/CPU2026Temp') as tmp:
        temp=Path(tmp)
        for name in expected_files:
            (temp/name).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(args.gold_source/name,temp/name)
        transform(temp)
        for name in expected_files:
            assert (temp/name).read_bytes() == (args.gate_source/name).read_bytes(), name
    record(Path(__file__).with_name('combined_frequency_transform.py'))
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
            assert defaults['DECODE_PIPELINE'] == defaults['ISSUE_PIPELINE'] == 0
        profile = defaults | manifest['parameter_overrides']
        assert profile['RS_ENTRIES'] == 12 and profile['CDB_WIDTH'] == 3
        assert profile['ICACHE_LOCAL_RESPONSE_READY'] == 1 and profile['FRONTEND_NARROW_OCCUPANCY'] == 1
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
    record(Path(__file__).with_name('prepare_combined_frequency_candidate.py'),stage['preparer_sha256'])
    record(Path(__file__).with_name('combined_frequency_transform.py'),stage['transformation_sha256'])
    assert {k:v.lower() for k,v in stage['baseline_sha256'].items()} == old
    assert {k:v.lower() for k,v in stage['staged_sha256'].items()} == new
    for evidence, expected in stage['validation_evidence_sha256'].items():
        record(Path(evidence),expected)
        for name,h in read(Path(evidence)).get('input_sha256',{}).items():record(Path(name),h)
    for name,h in stage['measurement_dependencies_sha256'].items():record(args.gate_source/name,h)
    proof_path=args.gate/'protocols_fixed_ports/report.json'
    record(proof_path); proof=read(proof_path)
    assert proof['status']=='COMPLETE' and proof['pipeline_vectors']==8400 and len(proof['results'])==5
    assert Path(proof['source_root']).resolve()==args.gate_source.resolve()
    for name,h in proof['input_sha256'].items():record(Path(name),h)
    for name,h in stage['component_origins_sha256'].items():record(Path(name),h)
    for helper in ('pipeline8_transform.py','prepare_rs_age_cpu_integration.py','prepare_rob_mmio_cpu_integration.py'):
        record(Path(__file__).with_name(helper))
    gold_extra_path=args.gold/'legal_addi_native/report.json'
    record(gold_extra_path)
    gold_extra=read(gold_extra_path)
    assert gold_extra['status']=='COMPLETE'
    for name,h in gold_extra['input_sha256'].items():record(Path(name),h)
    extra_by_name={r['name']:r for r in extra['results']}
    for left in gold_extra['results']:
        for field in ('status','instret','result'):
            assert left[field]==extra_by_name[left['name']][field],(left['name'],field)


    edge_paths=[args.gold/'arch_native/report.json',args.gate/'arch_native/report.json']
    edge_reports=[]
    for edge_path in edge_paths:
        record(edge_path); er=read(edge_path)
        assert er['status']=='COMPLETE' and er['instruction_types']==45 and len(er['results'])==16
        for name,h in er['input_sha256'].items():record(Path(name),h)
        edge_reports.append(er)
    for left,right in zip(edge_reports[0]['results'],edge_reports[1]['results']):
        for field in ('name','status','expected_u32','native_instret','oracle_instructions_through_exit_store'):
            assert left[field]==right[field], ('ISA edge difference',field,left,right)

    rows = []
    for suite in counts:
        left, right = reports[0][suite], reports[1][suite]
        assert left['external_memory'] == right['external_memory']
        right_by_name = {r['name']: r for r in right['results']}
        for a in left['results']:
            b = right_by_name[a['name']]
            for field in ['expected_u32', 'return_u32', 'instret']:
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
                  all_shared_parameters_identical=True, all_retirement_and_exits_identical=True, all_cycles_identical=all(r['cycles'][0]==r['cycles'][1] for r in rows),
                  additional_isa_cases=16, added_native_cases=8, baseline_geomean_ipc=reports[0]['benchmark']['geomean_ipc'],
                  benchmark_geomean_ipc=reports[1]['benchmark']['geomean_ipc'],
                  results=rows, input_sha256=inputs, cpu_ppa_claim=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','cases','added_parameters','all_retirement_and_exits_identical','benchmark_geomean_ipc','cpu_ppa_claim']}, indent=2))


if __name__ == '__main__':
    main()
