"""Verify the frozen ROB parallel-completion/Cache64 CPU's 29 native tests.

This checks exact cycles, retirement and exits against its RS12 baseline and
records the five intentional RTL changes and their completed component evidence. It makes no CPU area/timing claim.
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

    expected_files = {
        'rtl/backend/rv32_backend_joint.v', 'rtl/backend/rv32_rob.v',
        'rtl/course/student_top.v', 'rtl/cpu_core.v', 'rtl/cache/rv32_dcache_nonblocking.v'}
    new_parameters = {'ROB_COMPLETION_PARALLEL_WRITE': 1, 'DCACHE_METADATA_GROUP_ROWS': 64}
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
            assert defaults['ROB_COMPLETION_PARALLEL_WRITE'] == 0 and defaults['DCACHE_METADATA_GROUP_ROWS'] == 16
        profile = defaults | manifest['parameter_overrides']
        assert profile['RS_ENTRIES'] == 12
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
            assert not report['evaluates_current_worktree']  # Both explicitly frozen external source trees.
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
    for evidence, expected in stage['validation_evidence_sha256'].items():
        record(Path(evidence), expected)
    rows = []
    for suite in counts:
        left, right = reports[0][suite], reports[1][suite]
        assert left['external_memory'] == right['external_memory']
        right_by_name = {r['name']: r for r in right['results']}
        for a in left['results']:
            b = right_by_name[a['name']]
            for field in ['expected_u32', 'return_u32', 'instret', 'cycles', 'ipc']:
                assert a[field] == b[field], 'Mismatch: '+suite+'/'+a['name']+'/'+field
            assert Path(a['image']).resolve() == Path(b['image']).resolve()
            rows.append(dict(suite=suite, name=a['name'], cycles=a['cycles'], instret=a['instret'], return_u32=a['return_u32']))
    record(Path(__file__))
    for name, expected in inputs.items():
        assert sha(Path(name)) == expected, 'Input changed during audit: '+name
    result = dict(status='VERIFIED', scope=__doc__, cases=len(rows),
                  gold=str(args.gold.resolve()), gate=str(args.gate.resolve()),
                  source_roots=[str(args.gold_source.resolve()), str(args.gate_source.resolve())],
                  compiled_input_differences=changed, added_parameters=new_parameters,
                  all_shared_parameters_identical=True, all_cycles_retirement_and_exits_identical=True,
                  benchmark_geomean_ipc=reports[1]['benchmark']['geomean_ipc'],
                  results=rows, input_sha256=inputs, cpu_ppa_claim=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','cases','added_parameters','all_cycles_retirement_and_exits_identical','benchmark_geomean_ipc','cpu_ppa_claim']}, indent=2))


if __name__ == '__main__':
    main()
