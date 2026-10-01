"""Read existing RTL counters from a frozen model without rebuilding the RTL.

The diagnostic executable links the existing model/runtime objects. Its driver
is the official observer driver plus one include and read-only final counter
prints. Each benchmark's cycle/retirement/result is checked against its strict
course report. This diagnostic is not an alternative graded IPC/area flow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COUNTERS = (
    'frontend_empty_cycles', 'backend_stall_cycles', 'no_commit_cycles',
    'commit_active_cycles', 'issue_count', 'rob_full_cycles', 'rs_full_cycles',
    'lsq_full_cycles', 'branch_pending_cycles', 'mdu_busy_cycles',
    'i_requests', 'i_hits', 'i_misses', 'i_refills', 'i_stalls',
    'd_requests', 'd_hits', 'd_misses', 'd_refills', 'd_writebacks', 'd_stalls',
    'i_mem_requests', 'd_mem_reads', 'd_mem_writes',
)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--reference-report', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--compiler-bin', type=Path, default=Path('E:/mingw64/bin'))
    parser.add_argument('--branch-stats', action='store_true',
                        help='Also observe committed predictor count/correct, not speculative resolution count')
    args = parser.parse_args()
    build, out = args.build.resolve(), args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = build / 'build_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    reference = json.loads(args.reference_report.read_text(encoding='utf-8-sig'))
    if reference['status'] != 'COMPLETE' or reference['suite'] != 'benchmark' or \
            Path(reference['build_manifest']).resolve() != manifest_path:
        raise SystemExit('Same frozen build full benchmark report required')
    header = build / 'Vstudent_top___024root.h'
    header_text = header.read_text()
    driver_path = Path(manifest['generated_driver'])
    if sha(driver_path) != manifest['generated_driver_sha256'].lower() or \
            sha(manifest['executable']) != manifest['executable_sha256'].lower():
        raise SystemExit('Frozen executable/driver changed')
    original = driver_path.read_text()
    root_include = '#include "Vstudent_top___024root.h"\n'
    anchor = '        top.final();'
    if original.count(anchor) != 1 or root_include in original:
        raise SystemExit('Unexpected driver shape')
    prints = []
    members = {counter: 'perf_' + counter for counter in COUNTERS}
    if args.branch_stats:
        members.update(prediction_count='pred_count', prediction_correct='pred_correct')
    for counter, field in members.items():
        member = 'student_top__DOT__core__DOT__' + field
        if not re.search(r'\b' + member + r'\b', header_text):
            raise SystemExit('Counter missing from frozen model: ' + counter)
        prints.append(f'        std::cerr << "PERF {counter}=" << top.rootp->{member} << std::endl;')
    modified = root_include + original.replace(anchor, anchor + '\n' + '\n'.join(prints))
    if modified.removeprefix(root_include).replace(anchor + '\n' + '\n'.join(prints), anchor) != original:
        raise SystemExit('Diagnostic modified behavior beyond final read-only prints')
    source = out / 'sim_perf.cpp'
    source.write_text(modified)
    helper_snapshot = out / Path(__file__).name
    helper_snapshot.write_bytes(Path(__file__).read_bytes())
    runtime = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/share/verilator/include'
    objects = [build / name for name in ('verilated.o', 'verilated_vcd_c.o',
                                       'verilated_threads.o', 'Vstudent_top__ALL.a')]
    inputs = [manifest_path, args.reference_report.resolve(), driver_path, Path(manifest['executable']),
              source, helper_snapshot, *objects, *build.glob('*.h'), runtime / 'verilated.h', Path(__file__).resolve()]
    hashes = {str(path): sha(path) for path in inputs}
    compiler = args.compiler_bin / 'g++.exe'
    hashes[str(compiler)] = sha(compiler)
    env = os.environ.copy()
    env['PATH'] = str(args.compiler_bin) + os.pathsep + env['PATH']
    obj, exe = out / 'sim_perf.o', out / 'sim_perf.exe'
    compile_command = [str(compiler), '-std=c++17', '-DVL_TIME_CONTEXT', '-I' + str(build),
                       '-I' + str(runtime), '-I' + str(runtime / 'vltstd'),
                       '-c', str(source), '-o', str(obj)]
    link_command = [str(compiler), str(obj), *map(str, objects), '-pthread', '-lpthread',
                    '-latomic', '-o', str(exe)]
    for command in (compile_command, link_command):
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    results = []
    for item in reference['results']:
        image = Path(item['image'])
        hashes[str(image)] = sha(image)
        command = [str(exe), str(image), str(item['expected_u32']), '20000000', '20']
        completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
        (out / (item['name'] + '.log')).write_text(completed.stdout + completed.stderr)
        passed = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', completed.stdout, re.M)
        retired = re.search(r'^CPU2026 instret=(\d+)$', completed.stderr, re.M)
        counters = {name: int(value) for name, value in re.findall(r'^PERF (\w+)=(\d+)$', completed.stderr, re.M)}
        if completed.returncode or not passed or not retired or set(counters) != set(members) or \
                int(passed[1]) != item['cycles'] or int(retired[1]) != item['instret'] or \
                int(passed[2]) != item['return_u32'] or int(passed[3]) != item['expected_u32']:
            raise SystemExit('Diagnostic differs from strict benchmark: ' + item['name'])
        results.append(dict(name=item['name'], cycles=item['cycles'], instret=item['instret'], counters=counters))
        print(json.dumps(results[-1]), flush=True)
    for name, expected in hashes.items():
        if sha(name) != expected:
            raise SystemExit('Diagnostic input changed: ' + name)
    report = dict(status='COMPLETE', not_a_grade=True, input_sha256=hashes,
                  diagnostic_executable_sha256=sha(exe), compile_command=compile_command,
                  link_command=link_command, driver_change='one include and final read-only prints only',
                  results=results, caution='Cycle categories overlap; event stalls are not all miss-latency cycles')
    (out / 'perf_observation.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
