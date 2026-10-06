"""Audit the three-file legal ADDI255 repair on the actual native CPU.

Check all 43 frozen inputs, unchanged parameters, original driver/memory/images,
all 29 original exits/retirement/cycles, 39 protocol tests and 8 added native
MMIO cases. The buggy baseline is intentionally not behavior-equivalent on
legal ADDI255; full PPA still requires a new same-build measurement.
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
    for name in ['gold', 'gate', 'gold-source', 'gate-source', 'out', 'protocol', 'additional']:
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

    expected_files = {'rtl/frontend/rv32_fetch_frontend.v', 'rtl/predictor/rv32_banked_predictor.v', 'rtl/cpu_core.v'}
    new_parameters = {}
    edits = {
        'rtl/frontend/rv32_fetch_frontend.v': [
            ('    parameter integer PREDICTOR_META = 0', '    parameter integer LEGACY_SENTINEL_HALT = 0,\n    parameter integer PREDICTOR_META = 0'),
            ("                if ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513) begin",
             "                if ((LEGACY_SENTINEL_HALT != 0) &&\n                    ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513)) begin")],
        'rtl/predictor/rv32_banked_predictor.v': [
            ('    parameter integer DIRECT_BRANCH_TARGET = 0,', '    parameter integer LEGACY_SENTINEL_HALT = 0,\n    parameter integer DIRECT_BRANCH_TARGET = 0,'),
            ("                    ((query_line_i >> (history_word*32)) == 32'h0ff00513))",
             "                    ((LEGACY_SENTINEL_HALT != 0) &&\n                     ((query_line_i >> (history_word*32)) == 32'h0ff00513)))")],
        'rtl/cpu_core.v': [
            ('.HISTORY_BITS(PREDICTOR_HISTORY_BITS)) predictor (', '.HISTORY_BITS(PREDICTOR_HISTORY_BITS), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) predictor ('),
            ('.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2)) frontend (', '.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) frontend (')]
    }
    for name, replacements in edits.items():
        expected = (args.gold_source/name).read_text()
        for before, after in replacements:
            assert expected.count(before) == 1
            expected = expected.replace(before, after)
        assert (args.gate_source/name).read_text() == expected, 'Unexpected RTL edit: '+name
    for path, count in [(args.protocol,39),(args.additional,8)]:
        record(path)
        report=read(path)
        assert report['status']=='COMPLETE' and len(report['results'])==count
        assert all(row['status']=='PASS' for row in report['results'])
        for name, value in report['input_sha256'].items(): record(Path(name),value)
    additional=read(args.additional)
    assert additional['additional_correctness_only'] and additional['memory_latency']==20
    assert all(row['result']==256 for row in additional['results'])
    assert additional['input_sha256'][str((args.gate/'build/build_manifest.json').resolve())] == sha(args.gate/'build/build_manifest.json')
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
    assert gold['parameter_overrides'] == gate['parameter_overrides']
    assert profiles[0] == profiles[1]
    assert set(profiles[1])-set(profiles[0]) == set(new_parameters)
    assert all(profiles[0][k] == profiles[1][k] for k in profiles[0])
    assert all(profiles[1][k] == v for k, v in new_parameters.items())
    stage_path = args.gate_source/'staging_manifest.json'
    record(stage_path)
    stage = read(stage_path)
    assert {k:v.lower() for k,v in stage['baseline_sha256'].items()} == old
    assert {k:v.lower() for k,v in stage['staged_sha256'].items()} == new
    assert set(stage['changed_files']) == expected_files
    assert stage['baseline_has_confirmed_isa_defect'] and stage['legacy_mode_preserved']
    record(Path(stage['reproduction']),stage['reproduction_sha256'])
    assert stage['parameters'] == gold['parameter_overrides']
    for name,value in stage['measurement_dependencies_sha256'].items():
        record(args.gate_source/name,value)
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
                  exact_three_file_repair_verified=True, protocol_configurations=39, added_native_cases=8,
                  known_baseline_addi255_defect_fixed=True,
                  all_shared_parameters_identical=True, all_cycles_retirement_and_exits_identical=True,
                  benchmark_geomean_ipc=reports[1]['benchmark']['geomean_ipc'],
                  results=rows, input_sha256=inputs, cpu_ppa_claim=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','cases','added_parameters','all_cycles_retirement_and_exits_identical','benchmark_geomean_ipc','cpu_ppa_claim']}, indent=2))


if __name__ == '__main__':
    main()
