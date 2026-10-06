"""Read LSQ readiness/hazards from an already compiled, frozen CPU model.

No RTL or official memory behavior changes. Recompute the actual eligibility
expression and assert equality on every active cycle, then require all six
official cycle/instret/exit results to remain exact. Categories overlap and
are observations, not additive CPI costs or a new grading flow.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--reference-report', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--compiler-bin', type=Path, default=Path('E:/mingw64/bin'))
    args = parser.parse_args()
    build, out = args.build.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh diagnostic directory')
    manifest_path = build / 'build_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    reference = json.loads(args.reference_report.read_text(encoding='utf-8-sig'))
    if reference['status'] != 'COMPLETE' or reference['suite'] != 'benchmark' or \
            Path(reference['build_manifest']).resolve() != manifest_path or \
            {x['name'] for x in reference['results']} != {'median', 'multiply', 'qsort', 'rsort', 'towers', 'vvadd'}:
        raise SystemExit('Same frozen build and complete six-case official report required')
    inputs = {ROOT / name: expected.lower() for name, expected in manifest['source_sha256'].items()}
    defaults = {key: int(value) for key, value in re.findall(
        r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)', (ROOT / 'rtl/course/student_top.v').read_text())}
    parameters = defaults | manifest['parameter_overrides']
    entries = parameters['LSQ_ENTRIES']
    if entries not in (1, 2, 4, 8, 16, 32) or parameters['LSQ_STORE_ADMISSION_BYPASS'] != 0:
        raise SystemExit('Observer scope: LSQ <=32 and original registered store admission only')
    driver = Path(manifest['generated_driver'])
    inputs[driver] = manifest['generated_driver_sha256'].lower()
    inputs[Path(manifest['executable'])] = manifest['executable_sha256'].lower()
    inputs[manifest_path] = sha(manifest_path)
    inputs[args.reference_report.resolve()] = sha(args.reference_report)
    header = build / 'Vstudent_top___024root.h'
    header_text = header.read_text()
    prefix = 'student_top__DOT__core__DOT__g_ooo_backend__DOT__backend__DOT__lsq__DOT__'
    fields = ('valid_mem', 'load_mem', 'store_mem', 'addr_ready_mem', 'data_ready_mem',
              'request_sent_mem', 'response_wait_mem', 'complete_mem', 'store_commit_mem',
              'addr_mem', 'mask_mem', 'size_mem', 'head_reg', 'occupancy_reg',
              'pick_valid', 'candidate_found')
    for field in fields:
        if not re.search(r'\b' + re.escape(prefix + field) + r'\b', header_text):
            raise SystemExit('Unavailable frozen LSQ observation: ' + field)
    names = ('active_cycles', 'nonempty_no_candidate', 'load_addr_unready',
             'load_blocked_older_unknown_store', 'load_blocked_overlap_data',
             'load_waiting_response', 'store_addr_unready', 'store_data_unready',
             'store_ready_waiting_commit', 'store_ready_committed_unsent',
             'store_waiting_response', 'no_candidate_load_addr_unready',
             'no_candidate_load_blocked_older_unknown_store',
             'no_candidate_load_blocked_overlap_data', 'no_candidate_load_waiting_response',
             'no_candidate_store_addr_unready', 'no_candidate_store_data_unready',
             'no_candidate_store_ready_waiting_commit', 'no_candidate_store_waiting_response')
    original = driver.read_text()
    official = (ROOT / '.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
    observation = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
    if original.count(observation) != 1 or original.replace(observation, '') != official:
        raise SystemExit('Original driver differs beyond its retirement observation')
    tick = '        auto tick = [&]() {'
    edge = '            memory.drive(top);\n            top.eval();'
    final = '        top.final();'
    include = '#include "Vstudent_top___024root.h"\n#include <stdexcept>\n'
    if any(original.count(anchor) != 1 for anchor in (tick, edge, final)) or include in original:
        raise SystemExit('Unexpected official driver insertion points')
    declarations = '\n'.join(f'        uint64_t lsq_{name} = 0;' for name in names) + '\n'
    aliases = '\n'.join(f'                const auto &{field} = top.rootp->{prefix}{field};' for field in fields)
    sample = '''
            if (!top.reset) {
ALIASES
                bool load_addr_unready=false, load_blocked_older_unknown_store=false;
                bool load_blocked_overlap_data=false, load_waiting_response=false;
                bool store_addr_unready=false, store_data_unready=false;
                bool store_ready_waiting_commit=false, store_ready_committed_unsent=false;
                bool store_waiting_response=false;
                uint32_t recomputed_eligible=0;
                for (unsigned row=0; row<ENTRIES; ++row) {
                    const unsigned age=(row+ENTRIES-head_reg)&(ENTRIES-1);
                    if (age>=occupancy_reg || !valid_mem[row]) continue;
                    if (load_mem[row]) {
                        load_waiting_response |= bool(response_wait_mem[row]);
                        if (!request_sent_mem[row] && !complete_mem[row]) {
                            load_addr_unready |= !addr_ready_mem[row];
                            bool unknown=false, overlap=false;
                            const unsigned relative=(size_mem[row]==0)?1:((size_mem[row]==1)?3:15);
                            const unsigned load_mask=(relative<<(addr_mem[row]&15))&65535;
                            for (unsigned older=0; older<ENTRIES; ++older) {
                                const unsigned older_age=(older+ENTRIES-head_reg)&(ENTRIES-1);
                                if (older_age>=age || !valid_mem[older] || !store_mem[older]) continue;
                                unknown |= !addr_ready_mem[older];
                                const unsigned store_mask=(unsigned(mask_mem[older])<<(addr_mem[older]&15))&65535;
                                overlap |= (addr_mem[older]>>4)==(addr_mem[row]>>4) &&
                                           !data_ready_mem[older] && bool(store_mask&load_mask);
                            }
                            load_blocked_older_unknown_store |= addr_ready_mem[row] && unknown;
                            load_blocked_overlap_data |= addr_ready_mem[row] && overlap;
                            if (addr_ready_mem[row] && !unknown && !overlap) recomputed_eligible |= uint32_t(1)<<row;
                        }
                    }
                    if (store_mem[row]) {
                        store_waiting_response |= bool(response_wait_mem[row]);
                        if (!request_sent_mem[row]) {
                            store_addr_unready |= !addr_ready_mem[row];
                            store_data_unready |= !data_ready_mem[row];
                            const bool ready=addr_ready_mem[row] && data_ready_mem[row];
                            store_ready_waiting_commit |= ready && !store_commit_mem[row];
                            store_ready_committed_unsent |= ready && store_commit_mem[row];
                            if (ready && store_commit_mem[row]) recomputed_eligible |= uint32_t(1)<<row;
                        }
                    }
                }
                // RTL pick_valid has range [1:2*ENTRIES-1]; Verilator's
                // zero-based array maps each eligibility leaf to ENTRIES-1+row.
                uint32_t actual_eligible=0;
                for (unsigned row=0; row<ENTRIES; ++row)
                    if (pick_valid[ENTRIES-1+row]) actual_eligible |= uint32_t(1)<<row;
                if (recomputed_eligible!=actual_eligible || bool(recomputed_eligible)!=bool(candidate_found))
                    throw std::runtime_error("Read-only eligibility reconstruction differs from actual LSQ RTL");
                const bool nonempty_no_candidate=occupancy_reg && !candidate_found;
COUNTS
            }'''.replace('ALIASES', aliases).replace('ENTRIES', str(entries))
    counts = []
    for name in names:
        condition = 'true' if name == 'active_cycles' else (
            'nonempty_no_candidate && ' + name.removeprefix('no_candidate_')
            if name.startswith('no_candidate_') else name)
        counts.append(f'                lsq_{name} += bool({condition});')
    sample = sample.replace('COUNTS', '\n'.join(counts))
    prints = '\n' + '\n'.join(f'        std::cerr << "LSQ {name}=" << lsq_{name} << std::endl;' for name in names)
    modified = include + original.replace(tick, declarations + tick).replace(edge, edge + sample).replace(final, final + prints)
    recovered = modified.removeprefix(include).replace(declarations + tick, tick).replace(edge + sample, edge).replace(final + prints, final)
    if recovered != original:
        raise SystemExit('Driver changed beyond enumerated read-only observations')
    for path, expected in inputs.items():
        if sha(path) != expected:
            raise SystemExit('Frozen input changed: ' + str(path))
    out.mkdir(parents=True)
    source = out / 'sim_lsq_reasons.cpp'
    source.write_text(modified)
    helper_copy = out / Path(__file__).name
    shutil.copyfile(__file__, helper_copy)
    runtime = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/share/verilator/include'
    objects = [build / name for name in ('verilated.o', 'verilated_vcd_c.o', 'verilated_threads.o', 'Vstudent_top__ALL.a')]
    compiler = args.compiler_bin / 'g++.exe'
    inputs.update({path: sha(path) for path in [source, helper_copy, Path(__file__).resolve(),
                  ROOT / 'tools/observe_course_perf.py', header, runtime / 'verilated.h', compiler, *objects, *build.glob('*.h')]})
    env = dict(os.environ)
    env['PATH'] = str(args.compiler_bin) + os.pathsep + env['PATH']
    obj, exe = out / 'sim_lsq_reasons.o', out / 'sim_lsq_reasons.exe'
    commands = [[str(compiler), '-Os', '-std=c++17', '-DVL_TIME_CONTEXT', '-I' + str(build), '-I' + str(runtime),
                 '-I' + str(runtime / 'vltstd'), '-c', str(source), '-o', str(obj)],
                [str(compiler), str(obj), *map(str, objects), '-pthread', '-lpthread', '-latomic', '-o', str(exe)]]
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    results = []
    for item in reference['results']:
        image = Path(item['image'])
        inputs[image] = sha(image)
        run = subprocess.run([str(exe), str(image), str(item['expected_u32']), '20000000', '20'],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        log = out / (item['name'] + '.log')
        log.write_text(run.stdout + run.stderr)
        passed = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', run.stdout, re.M)
        retired = re.search(r'^CPU2026 instret=(\d+)$', run.stderr, re.M)
        counts = {name: int(value) for name, value in re.findall(r'^LSQ (\w+)=(\d+)$', run.stderr, re.M)}
        if run.returncode or not passed or not retired or set(counts) != set(names) or \
                (int(passed[1]), int(passed[2]), int(passed[3]), int(retired[1])) != \
                (item['cycles'], item['return_u32'], item['expected_u32'], item['instret']) or \
                counts['active_cycles'] != item['cycles']:
            raise SystemExit('Diagnostic differs from official benchmark: ' + str(log))
        result = dict(name=item['name'], cycles=item['cycles'], instret=item['instret'], observations=counts,
                      per_cycle_eligibility_identity=True, log_sha256=sha(log))
        results.append(result)
        print(json.dumps(result), flush=True)
    for path, expected in inputs.items():
        if sha(path) != expected:
            raise SystemExit('Frozen diagnostic input changed: ' + str(path))
    report = dict(status='COMPLETE', not_a_grade=True, input_sha256={str(p): h for p, h in inputs.items()},
                  diagnostic_executable_sha256=sha(exe), lsq_entries=entries, commands=commands, results=results,
                  sample_phase='low-edge memory.drive/eval; before memory.step/rising edge; reset excluded',
                  validation='actual LSQ eligibility equals reconstruction on every active cycle; all six official results exact',
                  caution='Overlapping per-cycle presence observations; not additive CPI causes or a grade')
    (out / 'lsq_reasons_observation.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
