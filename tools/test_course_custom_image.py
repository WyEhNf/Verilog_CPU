"""Run an additional correctness image on exact frozen native AXI CPUs.

This is not a benchmark grade or a substitute for any official suite. Preserve
the original 20-cycle memory driver and its sole retirement-count print, pin
all RTL/driver/executable/image inputs, and save each exit result and cycle
count. An optional compiler log documents host optimization, not CPU timing.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, action='append', required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--case-source', type=Path, required=True)
    parser.add_argument('--expected', type=int, default=0)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--build-log', type=Path, action='append', default=[])
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh custom-test artifact directory')
    out.mkdir(parents=True)
    hashes, results = {}, []
    sources = [args.image.resolve(), args.case_source.resolve(), ROOT / 'tools/startup.S', ROOT / 'tools/link.ld',
               ROOT / 'tools/runtime.c', Path(__file__).resolve(), ROOT / 'tools/observe_course_perf.py']
    for index, path in enumerate(sources):
        snapshot = out / 'source_snapshot' / (str(index) + '_' + path.name)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, snapshot)
        hashes[str(path)], hashes[str(snapshot)] = sha(path), sha(snapshot)
    compiler_observations = []
    for log in args.build_log:
        text = log.read_text()
        flags = sorted(set(re.findall(r'^g\+\+\s+(-O\S+)', text, re.M)))
        hashes[str(log.resolve())] = sha(log)
        compiler_observations.append(dict(log=str(log.resolve()), observed_host_optimization_flags=flags))
    for build in args.build:
        manifest_path = build.resolve() / 'build_manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        hashes[str(manifest_path)] = sha(manifest_path)
        for name, expected in manifest['source_sha256'].items():
            path = ROOT / name
            if sha(path) != expected.lower():
                raise SystemExit('Frozen CPU source changed: ' + str(path))
            hashes[str(path)] = expected.lower()
        driver, exe = Path(manifest['generated_driver']), Path(manifest['executable'])
        if sha(driver) != manifest['generated_driver_sha256'].lower() or \
                sha(exe) != manifest['executable_sha256'].lower():
            raise SystemExit('Frozen executable/driver changed')
        hashes[str(driver)], hashes[str(exe)] = sha(driver), sha(exe)
        observation = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
        observed = driver.read_text()
        if observed.count(observation) != 1 or observed.replace(observation, '') != \
                (ROOT / '.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text():
            raise SystemExit('Driver differs from the original beyond its retirement print')
        command = [str(exe), str(args.image.resolve()), str(args.expected & 0xffffffff), '1000000', '20']
        run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        log = out / (manifest_path.parent.name + '.log')
        log.write_text(run.stdout + run.stderr)
        passed = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', run.stdout, re.M)
        retired = re.search(r'^CPU2026 instret=(\d+)$', run.stderr, re.M)
        if run.returncode or not passed or not retired or int(passed[2]) != (args.expected & 0xffffffff) or \
                int(passed[3]) != (args.expected & 0xffffffff):
            raise SystemExit('Additional image failed: ' + str(log))
        row = dict(build_manifest=str(manifest_path), configuration=manifest['configuration'],
                   parameter_overrides=manifest['parameter_overrides'], status='PASS',
                   cycles=int(passed[1]), instret=int(retired[1]), return_u32=int(passed[2]),
                   expected_u32=int(passed[3]), log_sha256=sha(log), command=command)
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ('parameter_overrides', 'command')}), flush=True)
    for path, expected in hashes.items():
        if sha(path) != expected:
            raise SystemExit('Custom-test input changed: ' + path)
    report = dict(status='COMPLETE', not_a_benchmark_grade=True, input_sha256=hashes,
                  external_latency_cycles=20, compiler_observations=compiler_observations, results=results)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
