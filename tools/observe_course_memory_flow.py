"""Observe pre-edge memory handshakes in a frozen, already compiled CPU model.

Only the diagnostic C++ driver changes. Reuse the original Verilator objects,
and require identical official cycles, retirement counts and exit results for
all six benchmarks. These overlapping observations are not a CPI attribution
or an alternative grading flow.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import COUNTERS, ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--reference-report', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--compiler-bin', type=Path, default=Path('E:/mingw64/bin'))
    args = parser.parse_args()
    build, out = args.build.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Use a fresh diagnostic output directory')
    out.mkdir(parents=True)
    manifest_path = build / 'build_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    reference = json.loads(args.reference_report.read_text(encoding='utf-8-sig'))
    if reference['status'] != 'COMPLETE' or reference['suite'] != 'benchmark' or \
            Path(reference['build_manifest']).resolve() != manifest_path or \
            {x['name'] for x in reference['results']} != {'median', 'multiply', 'qsort', 'rsort', 'towers', 'vvadd'}:
        raise SystemExit('Same frozen build, complete six-benchmark reference required')
    driver = Path(manifest['generated_driver'])
    if sha(driver) != manifest['generated_driver_sha256'].lower() or \
            sha(manifest['executable']) != manifest['executable_sha256'].lower():
        raise SystemExit('Frozen executable or driver changed')
    header_text = (build / 'Vstudent_top___024root.h').read_text()
    core = 'student_top__DOT__core__DOT__'
    lsq = core + 'g_ooo_backend__DOT__backend__DOT__lsq__DOT__'
    cache = core + 'g_cached_memory__DOT__g_nonblocking_dcache__DOT__dcache__DOT__'
    members = {
        'offered': lsq + 'dcache_req_valid_o',
        'ready': lsq + 'dcache_req_ready_i',
        'candidate': lsq + 'candidate_found',
        'occupancy': lsq + 'occupancy_reg',
        'query': cache + 'g_sram_tags__DOT__query_valid',
        'core_ready': cache + 'core_req_ready',
        'tag_write': cache + 'tag_array_write',
        'data_write': cache + 'data_we',
        'hit': cache + 'request_hit',
        'mshr_free': cache + 'free_found',
        'matching': cache + 'matching_found',
        'waiter_free': cache + 'waiter_free_found',
    }
    final_members = {counter: core + 'perf_' + counter for counter in COUNTERS}
    for member in [*members.values(), *final_members.values()]:
        if not re.search(r'\b' + re.escape(member) + r'\b', header_text):
            raise SystemExit('Observation unavailable in frozen model: ' + member)
    conditions = {
        'active_cycles': 'true',
        'cache_request_offered': 'offered',
        'cache_request_accepted': 'offered && ready',
        'cache_request_blocked': 'offered && !ready',
        'blocked_with_tag_write': 'offered && !ready && tag_write',
        'blocked_with_data_write': 'offered && !ready && data_write',
        'blocked_with_pending_query': 'offered && !ready && query && !core_ready',
        'query_present': 'query',
        'query_accepted': 'query && core_ready',
        'query_blocked': 'query && !core_ready',
        'query_blocked_hit': 'query && !core_ready && hit',
        'query_blocked_no_mshr': 'query && !core_ready && !hit && !matching && !mshr_free',
        'query_blocked_no_waiter': 'query && !core_ready && !hit && matching && !waiter_free',
        'lsq_nonempty_no_candidate': 'occupancy && !candidate',
        'lsq_candidate_no_cache_request': 'candidate && !offered',
    }
    original = driver.read_text()
    include = '#include "Vstudent_top___024root.h"\n'
    tick_anchor = '        auto tick = [&]() {'
    sample_anchor = '            memory.drive(top);\n            top.eval();'
    final_anchor = '        top.final();'
    if any(original.count(anchor) != 1 for anchor in (tick_anchor, sample_anchor, final_anchor)) or include in original:
        raise SystemExit('Unexpected original driver shape')
    declarations = '\n'.join('        uint64_t flow_' + name + ' = 0;' for name in conditions) + '\n'
    sample = '\n            if (!top.reset) {\n' + '\n'.join(
        '                const auto ' + name + ' = top.rootp->' + member + ';'
        for name, member in members.items()) + '\n' + '\n'.join(
        f'                flow_{name} += bool({condition});' for name, condition in conditions.items()) + '\n            }'
    prints = '\n' + '\n'.join(
        f'        std::cerr << "FLOW {name}=" << flow_{name} << std::endl;' for name in conditions) + '\n' + '\n'.join(
        f'        std::cerr << "PERF {name}=" << top.rootp->{member} << std::endl;'
        for name, member in final_members.items())
    modified = include + original.replace(tick_anchor, declarations + tick_anchor).replace(
        sample_anchor, sample_anchor + sample).replace(final_anchor, final_anchor + prints)
    recovered = modified.removeprefix(include).replace(declarations + tick_anchor, tick_anchor).replace(
        sample_anchor + sample, sample_anchor).replace(final_anchor + prints, final_anchor)
    if recovered != original:
        raise SystemExit('Driver changed beyond explicit read-only observations')
    source = out / 'sim_memory_flow.cpp'
    source.write_text(modified)
    helpers = [Path(__file__).resolve(), ROOT / 'tools/observe_course_perf.py']
    for helper in helpers:
        shutil.copyfile(helper, out / helper.name)
    runtime = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/share/verilator/include'
    objects = [build / name for name in ('verilated.o', 'verilated_vcd_c.o', 'verilated_threads.o', 'Vstudent_top__ALL.a')]
    compiler = args.compiler_bin / 'g++.exe'
    inputs = [manifest_path, args.reference_report.resolve(), driver, Path(manifest['executable']), source,
              *helpers, *[out / h.name for h in helpers], *objects, *build.glob('*.h'), runtime / 'verilated.h', compiler]
    hashes = {str(path): sha(path) for path in inputs}
    env = dict(os.environ)
    env['PATH'] = str(args.compiler_bin) + os.pathsep + env['PATH']
    obj, exe = out / 'sim_memory_flow.o', out / 'sim_memory_flow.exe'
    compile_command = [str(compiler), '-std=c++17', '-DVL_TIME_CONTEXT', '-I' + str(build), '-I' + str(runtime),
                       '-I' + str(runtime / 'vltstd'), '-c', str(source), '-o', str(obj)]
    link_command = [str(compiler), str(obj), *map(str, objects), '-pthread', '-lpthread', '-latomic', '-o', str(exe)]
    for command in (compile_command, link_command):
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    results = []
    for item in reference['results']:
        image = Path(item['image'])
        hashes[str(image)] = sha(image)
        run = subprocess.run([str(exe), str(image), str(item['expected_u32']), '20000000', '20'],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        (out / (item['name'] + '.log')).write_text(run.stdout + run.stderr)
        passed = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', run.stdout, re.M)
        retired = re.search(r'^CPU2026 instret=(\d+)$', run.stderr, re.M)
        flow = {name: int(value) for name, value in re.findall(r'^FLOW (\w+)=(\d+)$', run.stderr, re.M)}
        counters = {name: int(value) for name, value in re.findall(r'^PERF (\w+)=(\d+)$', run.stderr, re.M)}
        if run.returncode or not passed or not retired or set(flow) != set(conditions) or set(counters) != set(final_members) or \
                int(passed[1]) != item['cycles'] or int(retired[1]) != item['instret'] or \
                int(passed[2]) != item['return_u32'] or int(passed[3]) != item['expected_u32'] or \
                flow['active_cycles'] != item['cycles']:
            raise SystemExit('Read-only diagnostic differs from official benchmark: ' + item['name'])
        result = dict(name=item['name'], cycles=item['cycles'], instret=item['instret'], flow=flow, counters=counters)
        results.append(result)
        print(json.dumps(result), flush=True)
    for path, expected in hashes.items():
        if sha(path) != expected:
            raise SystemExit('Frozen diagnostic input changed: ' + path)
    report = dict(status='COMPLETE', not_a_grade=True, input_sha256=hashes, members=members, conditions=conditions,
                  sample_phase='after clock=0, memory.drive and eval; before memory.step and rising clock edge; reset excluded',
                  driver_change='one include, local counters, pre-edge read-only observations, final prints only',
                  diagnostic_executable_sha256=sha(exe), compile_command=compile_command, link_command=link_command,
                  results=results, caution='Overlapping signal observations; not a sum of mutually exclusive stall causes')
    (out / 'memory_flow_observation.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
