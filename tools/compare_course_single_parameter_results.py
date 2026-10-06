"""Verify identical native results for exactly one declared RTL parameter change.

This is a bounded regression comparison, not a whole-CPU formal proof or PPA
claim. Require the same current hardware/driver sources and original external
memory semantics; reject any additional parameter change or incomplete suite.
"""
import argparse
import json
from pathlib import Path
import re

from observe_course_perf import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in ('gold', 'gate'):
        parser.add_argument('--'+kind+'-build', type=Path, required=True)
        parser.add_argument('--'+kind+'-suffix', required=True)
        parser.add_argument('--'+kind+'-value', type=int, required=True)
    parser.add_argument('--parameter', required=True)
    parser.add_argument('--suites', nargs='+', choices=('benchmark', 'basic', 'simulator', 'boundary'),
                        default=['benchmark', 'basic', 'simulator', 'boundary'])
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[A-Z][A-Z0-9_]*', args.parameter) or args.gold_value==args.gate_value:
        raise SystemExit('Exactly one actual RTL parameter change must be declared')
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh comparison audit directory')
    inputs, manifests, suites = {}, [], []
    counts = dict(benchmark=6, basic=5, simulator=17, boundary=1)
    for kind in ('gold', 'gate'):
        build = getattr(args, kind+'_build').resolve()
        suffix = getattr(args, kind+'_suffix')
        if not build.name.endswith('_'+suffix):
            raise SystemExit('Build does not match declared suffix')
        manifest_path = build/'build_manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if manifest['format']!='course-axi-frozen-build-v1' or \
                manifest['parameter_overrides'].get(args.parameter)!=getattr(args,kind+'_value'):
            raise SystemExit('Frozen build parameter mismatch')
        manifests.append(manifest)
        inputs[manifest_path] = sha(manifest_path)
        for name, expected in manifest['source_sha256'].items():
            inputs[ROOT/name] = expected.lower()
        inputs[Path(manifest['executable'])] = manifest['executable_sha256'].lower()
        driver = Path(manifest['generated_driver'])
        inputs[driver] = manifest['generated_driver_sha256'].lower()
        original = (ROOT/'.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
        observed = driver.read_text()
        retirement = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
        if observed.count(retirement)!=1 or observed.replace(retirement,'')!=original:
            raise SystemExit('Official driver differs beyond retirement print')
        label = build.name.removesuffix('_'+suffix)
        reports = {}
        for suite in args.suites:
            path = ROOT/f'build/cpu2026/{label}_{suite}_{suffix}.json'
            report = json.loads(path.read_text(encoding='utf-8-sig'))
            if report['status']!='COMPLETE' or report['suite']!=suite or \
                    Path(report['build_manifest']).resolve()!=manifest_path or \
                    len(report['results'])!=counts[suite] or not report['pi_excluded']:
                raise SystemExit('Incomplete/different report: '+str(path))
            memory = report['external_memory']
            if memory['latency_cycles']!=20 or memory['external_ram_bytes']!=268435456 or \
                    memory['word_bytes']!=4 or not memory['shared_ar_r'] or not memory['exit_at_b_handshake']:
                raise SystemExit('External memory contract changed')
            inputs[path] = sha(path)
            for source,expected in report['source_sha256'].items():
                source = Path(source)
                if source in inputs and inputs[source]!=expected.lower():
                    raise SystemExit('Conflicting frozen input hash: '+str(source))
                inputs[source] = expected.lower()
            reports[suite] = report
        suites.append(reports)
    gold, gate = manifests
    normalize = lambda m: {k:v.lower() for k,v in m['source_sha256'].items()}
    if normalize(gold)!=normalize(gate) or gold['configuration']!=gate['configuration'] or \
            gold['generated_driver_sha256'].lower()!=gate['generated_driver_sha256'].lower():
        raise SystemExit('Hardware/filelist/header/builder/driver sources differ')
    remove = lambda m: {k:v for k,v in m['parameter_overrides'].items() if k!=args.parameter}
    if remove(gold)!=remove(gate):
        raise SystemExit('Additional hardware parameters changed')
    fields = ('name','status','expected_u32','return_u32','cycles','instret','ipc')
    results = []
    for suite in args.suites:
        first, second = suites[0][suite], suites[1][suite]
        if first['external_memory']!=second['external_memory'] or first['geomean_ipc']!=second['geomean_ipc']:
            raise SystemExit('Memory or suite IPC differs: '+suite)
        for left,right in zip(first['results'],second['results']):
            if left['status']!='passed' or any(left[k]!=right[k] for k in fields):
                raise SystemExit('Native result differs: '+suite+'/'+left['name'])
            results.append(dict(suite=suite,name=left['name'],cycles=left['cycles'],instret=left['instret'],
                                return_u32=left['return_u32'],status='IDENTICAL'))
    inputs[Path(__file__).resolve()] = sha(__file__)
    inputs[ROOT/'tools/observe_course_perf.py'] = sha(ROOT/'tools/observe_course_perf.py')
    for path,expected in inputs.items():
        if sha(path)!=expected:
            raise SystemExit('Current frozen input changed: '+str(path))
    out.mkdir(parents=True)
    report = dict(status='COMPLETE',input_sha256={str(p):h for p,h in inputs.items()},
                  parameter=args.parameter,gold_value=args.gold_value,gate_value=args.gate_value,
                  cases=len(results),suites=args.suites,results=results,
                  same_current_hardware_sources=True,only_declared_parameter_differs=True,
                  all_cycle_instret_exit_results_identical=True,cpu_ppa_claim=False,
                  scope='Exact native outcomes for declared suites; not whole-CPU formal equivalence')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'COMPLETE: {len(results)} identical native cases; only {args.parameter} {args.gold_value}->{args.gate_value}')


if __name__=='__main__':
    main()
