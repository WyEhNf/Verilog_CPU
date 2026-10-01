"""Audit exact native results across host-only builds of the same hardware."""
import argparse
import json
from pathlib import Path

from observe_course_perf import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold-build', type=Path, required=True)
    parser.add_argument('--gate-build', type=Path, required=True)
    parser.add_argument('--gold-run-suffix', required=True)
    parser.add_argument('--gate-run-suffix', required=True)
    parser.add_argument('--suites', nargs='+', choices=('benchmark', 'basic', 'simulator', 'boundary'),
                        default=['benchmark', 'basic', 'simulator', 'boundary'])
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh comparison audit directory')
    builders = {'tools/build_course_verilator.ps1', 'tools/build_course_verilator_split.ps1'}
    expected_cases = {'benchmark': 6, 'basic': 5, 'simulator': 17, 'boundary': 1}
    inputs, reports, manifests = {}, [], []
    for build, suffix in ((args.gold_build.resolve(), args.gold_run_suffix),
                          (args.gate_build.resolve(), args.gate_run_suffix)):
        if not build.name.endswith('_' + suffix):
            raise SystemExit('Build directory does not match the declared run suffix')
        manifest_path = build / 'build_manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if manifest['format'] != 'course-axi-frozen-build-v1':
            raise SystemExit('Frozen official AXI build required')
        manifests.append(manifest)
        inputs[manifest_path] = sha(manifest_path)
        for name, expected in manifest['source_sha256'].items():
            inputs[ROOT / name] = expected.lower()
        inputs[Path(manifest['executable'])] = manifest['executable_sha256'].lower()
        driver = Path(manifest['generated_driver'])
        inputs[driver] = manifest['generated_driver_sha256'].lower()
        official = (ROOT / '.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
        observed = driver.read_text()
        addition = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
        if observed.count(addition) != 1 or observed.replace(addition, '') != official:
            raise SystemExit('Official driver/memory semantics changed')
        label = build.name.removesuffix('_' + suffix)
        build_reports = {}
        for suite in args.suites:
            path = ROOT / f'build/cpu2026/{label}_{suite}_{suffix}.json'
            report = json.loads(path.read_text(encoding='utf-8-sig'))
            if report['status'] != 'COMPLETE' or report['suite'] != suite or \
                    Path(report['build_manifest']).resolve() != manifest_path or \
                    len(report['results']) != expected_cases[suite] or not report['pi_excluded']:
                raise SystemExit('Incomplete or different native report: ' + str(path))
            memory = report['external_memory']
            if memory['latency_cycles'] != 20 or memory['external_ram_bytes'] != 268435456 or \
                    memory['word_bytes'] != 4 or not memory['shared_ar_r'] or not memory['exit_at_b_handshake']:
                raise SystemExit('Official external memory contract differs')
            inputs[path] = sha(path)
            for source, expected in report['source_sha256'].items():
                if Path(source) in inputs and inputs[Path(source)] != expected.lower():
                    raise SystemExit('Conflicting frozen input hash: ' + source)
                inputs[Path(source)] = expected.lower()
            build_reports[suite] = report
        reports.append(build_reports)
    gold, gate = manifests
    if gold['configuration'] != gate['configuration'] or gold['parameter_overrides'] != gate['parameter_overrides']:
        raise SystemExit('Hardware parameter configurations differ')
    normalize = lambda manifest: {name: value.lower() for name, value in manifest['source_sha256'].items() if name not in builders}
    if normalize(gold) != normalize(gate) or gold['generated_driver_sha256'].lower() != gate['generated_driver_sha256'].lower():
        raise SystemExit('RTL/filelist/header/driver inputs differ beyond named host build helpers')
    results = []
    fields = ('name', 'status', 'expected_u32', 'return_u32', 'cycles', 'instret', 'ipc')
    for suite in args.suites:
        first, second = reports[0][suite], reports[1][suite]
        if first['external_memory'] != second['external_memory'] or first['geomean_ipc'] != second['geomean_ipc']:
            raise SystemExit('Suite memory or IPC differs: ' + suite)
        for left, right in zip(first['results'], second['results']):
            if any(left[field] != right[field] for field in fields) or left['status'] != 'passed':
                raise SystemExit('Native result differs: ' + suite + '/' + left['name'])
            results.append(dict(suite=suite, name=left['name'], cycles=left['cycles'], instret=left['instret'],
                                return_u32=left['return_u32'], status='IDENTICAL'))
    inputs[Path(__file__).resolve()] = sha(__file__)
    inputs[ROOT / 'tools/observe_course_perf.py'] = sha(ROOT / 'tools/observe_course_perf.py')
    for path, expected in inputs.items():
        if sha(path) != expected:
            raise SystemExit('Current frozen input differs: ' + str(path))
    out.mkdir(parents=True)
    report = dict(status='COMPLETE', input_sha256={str(p): h for p, h in inputs.items()}, results=results,
                  cases=len(results), same_hardware=True, parameter_overrides=gold['parameter_overrides'],
                  all_cycle_instret_exit_results_identical=True, cpu_ppa_claim=False,
                  scope='exact native results for the selected suites; not a whole-CPU formal proof')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'COMPLETE: {len(results)} identical native cases; same RTL/parameters/official memory')


if __name__ == '__main__':
    main()
