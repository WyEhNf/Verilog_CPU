"""Audit a same-source, single-parameter native CPU performance tradeoff.

Use all 29 authorized tests, exact pinned driver/memory/image identities and
effective source defaults. Allow cycle changes, require identical retirement
counts and correct exits, and independently recalculate each benchmark IPC.
This does not claim area, timing, or whole-CPU formal equivalence.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--gate', type=Path, required=True)
    parser.add_argument('--parameter', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('Preserve prior audits; choose a fresh output file')
    inputs = {}
    def record(path,expected=None):
        path = path.resolve()
        actual = sha(path)
        assert expected is None or actual == expected.lower(), 'Changed input: '+str(path)
        if str(path) in inputs:
            assert inputs[str(path)] == actual
        inputs[str(path)] = actual
    top = ROOT/'rtl/course/student_top.v'
    parameters = top.read_text().split(') (',1)[0]
    defaults = {k:int(v) for k,v in re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)',parameters)}
    assert args.parameter in defaults
    manifests, profiles, reports = [], [], []
    counts = dict(benchmark=6,basic=5,simulator=17,boundary=1)
    benchmark_names = {'median','multiply','qsort','rsort','towers','vvadd'}
    for root in [args.gold.resolve(),args.gate.resolve()]:
        path = root/'build/build_manifest.json'
        record(path);manifest = read(path)
        assert manifest['format'] == 'course-axi-frozen-build-v1'
        assert set(manifest['parameter_overrides']) <= set(defaults)
        manifests.append(manifest);profiles.append(defaults | manifest['parameter_overrides'])
        for name,expected in manifest['source_sha256'].items():
            record(ROOT/name,expected)
        record(Path(manifest['executable']),manifest['executable_sha256'])
        driver = Path(manifest['generated_driver'])
        record(driver,manifest['generated_driver_sha256'])
        original = (ROOT/'.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
        observation = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
        observed = driver.read_text()
        assert observed.count(observation) == 1 and observed.replace(observation,'') == original
        suites = {}
        for suite,count in counts.items():
            report_path = root/(suite+'.json');record(report_path);report = read(report_path)
            assert report['status'] == 'COMPLETE' and report['suite'] == suite
            assert Path(report['build_manifest']).resolve() == path
            assert len(report['results']) == count and report['pi_excluded']
            assert not report['current_source_differences']
            memory = report['external_memory']
            assert memory['latency_cycles'] == 20 and memory['external_ram_bytes'] == 268435456
            assert memory['word_bytes'] == 4 and memory['shared_ar_r'] and memory['exit_at_b_handshake']
            for name,expected in report['source_sha256'].items():
                record(Path(name),expected)
            cases = report['results']
            assert len({r['name'] for r in cases}) == count
            assert sum(r['cycles'] for r in cases) == report['total_cycles']
            assert sum(r['instret'] for r in cases) == report['total_instret']
            for row in cases:
                assert row['status'] == 'passed' and row['return_u32'] == row['expected_u32']
                assert row['cycles'] > 0 and row['instret'] > 0
                assert math.isclose(row['ipc'],row['instret']/row['cycles'],rel_tol=1e-12)
                record(Path(row['image']))
            recalculated = math.exp(sum(math.log(r['instret']/r['cycles']) for r in cases)/count)
            assert math.isclose(recalculated,report['geomean_ipc'],rel_tol=1e-12)
            if suite == 'benchmark':
                assert {r['name'] for r in cases} == benchmark_names
            suites[suite] = report
        reports.append(suites)
    gold,gate = manifests
    normalize = lambda m: {n:h.lower() for n,h in m['source_sha256'].items()}
    assert normalize(gold) == normalize(gate), 'Hardware, filelist, builder or original driver differs'
    assert gold['configuration'] == gate['configuration'] and gold['external_memory'] == gate['external_memory']
    assert gold['generated_driver_sha256'].lower() == gate['generated_driver_sha256'].lower()
    changed = {n:[profiles[0][n],profiles[1][n]] for n in defaults if profiles[0][n] != profiles[1][n]}
    assert set(changed) == {args.parameter}, 'Additional effective hardware parameter change'
    raw_changes = {n:[gold['parameter_overrides'].get(n),gate['parameter_overrides'].get(n)]
                   for n in gold['parameter_overrides'].keys() | gate['parameter_overrides'].keys()
                   if gold['parameter_overrides'].get(n) != gate['parameter_overrides'].get(n)}
    rows = []
    for suite in counts:
        left,right = reports[0][suite],reports[1][suite]
        assert left['external_memory'] == right['external_memory']
        right_by_name = {r['name']:r for r in right['results']}
        for a in left['results']:
            b = right_by_name[a['name']]
            for field in ['expected_u32','return_u32','instret']:
                assert a[field] == b[field], 'Architectural result/retirement differs: '+suite+'/'+a['name']
            assert Path(a['image']).resolve() == Path(b['image']).resolve()
            rows.append(dict(suite=suite,name=a['name'],instret=a['instret'],return_u32=a['return_u32'],
                             cycles=[a['cycles'],b['cycles']],ipc=[a['ipc'],b['ipc']]))
    benchmark = [r['benchmark'] for r in reports]
    record(Path(__file__))
    report = dict(status='VERIFIED',scope='Same-source single-parameter full native regression/performance audit; not CPU PPA or formal proof',
                  gold=str(args.gold.resolve()),gate=str(args.gate.resolve()),cases=len(rows),
                  input_sha256=inputs,source_default_parameters=defaults,
                  raw_override_differences=raw_changes,effective_parameter_differences=changed,
                  all_exits_and_retirement_counts_identical=True,results=rows,
                  benchmark_geomean_ipc=[r['geomean_ipc'] for r in benchmark],
                  benchmark_total_cycles=[r['total_cycles'] for r in benchmark],
                  benchmark_total_instret=[r['total_instret'] for r in benchmark],
                  ipc_relative_change=benchmark[1]['geomean_ipc']/benchmark[0]['geomean_ipc']-1,
                  meets_tier3_ipc=[r['geomean_ipc'] >= 1.0985 for r in benchmark],cpu_ppa_claim=False)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','cases','effective_parameter_differences','benchmark_geomean_ipc','ipc_relative_change','meets_tier3_ipc']},indent=2))


if __name__ == '__main__':
    main()
