"""Observe actual store base/data readiness without changing hardware.

Match LSQ stores to live RS entries using the complete ROB tag. Count the
presence of computable addresses and a bounded counterfactual: an otherwise
eligible load if every unknown older-store address that is currently
computable were published. This is not additive CPI or an IPC prediction.
All six official cycle/retirement/exit results must remain exact.
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
    defaults = {key: int(value) for key, value in re.findall(
        r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)', (ROOT / 'rtl/course/student_top.v').read_text())}
    params = defaults | manifest['parameter_overrides']
    n, rs_n, rob_n = params['LSQ_ENTRIES'], params['RS_ENTRIES'], params['ROB_ENTRIES']
    if params['LSQ_STORE_ADMISSION_BYPASS'] or n not in (1, 2, 4, 8, 16, 32):
        raise SystemExit('Observer requires the original LSQ admission, at most 32 entries')
    inputs = {ROOT / name: value.lower() for name, value in manifest['source_sha256'].items()}
    driver = Path(manifest['generated_driver'])
    inputs.update({driver: manifest['generated_driver_sha256'].lower(),
                   Path(manifest['executable']): manifest['executable_sha256'].lower(),
                   manifest_path: sha(manifest_path), args.reference_report.resolve(): sha(args.reference_report)})
    header = build / 'Vstudent_top___024root.h'
    header_text = header.read_text()
    prefix = 'student_top__DOT__core__DOT__g_ooo_backend__DOT__backend__DOT__'
    groups = {
        'lsq': ('valid_mem', 'load_mem', 'store_mem', 'addr_ready_mem', 'data_ready_mem',
                'request_sent_mem', 'complete_mem', 'rob_tag_mem', 'addr_mem', 'mask_mem',
                'size_mem', 'head_reg', 'occupancy_reg', 'candidate_found'),
        'rs': ('valid_mem', 'target_live_mem', 'rob_tag_mem', 'src1_ready_mem',
               'src1_ready_effective', 'src2_ready_effective', 'src1_value_effective'),
    }
    aliases = []
    for group, fields in groups.items():
        for field in fields:
            member = prefix + group + '__DOT__' + field
            if not re.search(r'\b' + re.escape(member) + r'\b', header_text):
                raise SystemExit('Required frozen observation missing: ' + member)
            aliases.append(f'                const auto &{group}_{field} = top.rootp->{member};')
    if not re.search(r'\b' + re.escape(prefix + 'rob_imm_mem') + r'\b', header_text):
        raise SystemExit('Frozen ROB immediate unavailable')
    aliases.append(f'                const auto &rob_imm = top.rootp->{prefix}rob_imm_mem;')
    names = ('active_cycles', 'unknown_store', 'unknown_store_no_rs', 'base_unready',
             'base_ready_data_wait', 'base_ready_both_ready', 'base_wakeup_this_cycle',
             'load_blocked_unknown_but_computable', 'load_counterfactual_eligible',
             'no_candidate_base_ready_data_wait', 'no_candidate_load_counterfactual_eligible',
             'predicted_address_verified', 'predicted_address_cancelled')
    declarations = '\n'.join(f'        uint64_t opportunity_{name}=0;' for name in names) + '\n'
    declarations += (f'        bool predicted_valid[{n}]={{}};\n'
                     f'        uint32_t predicted_tag[{n}]={{}}, predicted_address[{n}]={{}};\n')
    sample = r'''
            if (!top.reset) {
ALIASES
                // Verify hypothetical addresses against the later real LSQ
                // address. Recovery/reuse cancels a prediction, never proves
                // it. Full tags prevent checking a different instruction.
                for (unsigned row=0; row<N; ++row) {
                    if (!predicted_valid[row]) continue;
                    if (!lsq_valid_mem[row] || !lsq_store_mem[row] ||
                        predicted_tag[row]!=lsq_rob_tag_mem[row]) {
                        ++opportunity_predicted_address_cancelled;
                        predicted_valid[row]=false;
                    } else if (lsq_addr_ready_mem[row]) {
                        if (predicted_address[row]!=lsq_addr_mem[row])
                            throw std::runtime_error("Computed store address differs from its later real LSQ address");
                        ++opportunity_predicted_address_verified;
                        predicted_valid[row]=false;
                    }
                }
                bool unknown_store=false, unknown_store_no_rs=false, base_unready=false;
                bool base_ready_data_wait=false, base_ready_both_ready=false, base_wakeup_this_cycle=false;
                bool load_blocked_unknown_but_computable=false, load_counterfactual_eligible=false;
                bool computable[N] = {};
                uint32_t computed_address[N] = {};
                auto age = [&](unsigned row) { return (row+N-lsq_head_reg)&(N-1); };
                auto active = [&](unsigned row) { return age(row)<lsq_occupancy_reg && lsq_valid_mem[row]; };
                for (unsigned row=0; row<N; ++row) {
                    if (!active(row) || !lsq_store_mem[row] || lsq_addr_ready_mem[row]) continue;
                    unknown_store=true;
                    unsigned matches=0;
                    for (unsigned entry=0; entry<RS_N; ++entry) {
                        if (!rs_valid_mem[entry] || !rs_target_live_mem[entry] ||
                            rs_rob_tag_mem[entry]!=lsq_rob_tag_mem[row]) continue;
                        ++matches;
                        if (rs_src1_ready_mem[entry] && !rs_src1_ready_effective[entry])
                            throw std::runtime_error("RS base-ready observation violates its actual effective logic");
                        if (!rs_src1_ready_effective[entry]) base_unready=true;
                        else {
                            computable[row]=true;
                            computed_address[row]=uint32_t(rs_src1_value_effective[entry])+
                                uint32_t(rob_imm[(lsq_rob_tag_mem[row]>>3)&(ROB_N-1)]);
                            if (predicted_valid[row] && predicted_address[row]!=computed_address[row])
                                throw std::runtime_error("Ready store address changed before publication");
                            predicted_valid[row]=true;
                            predicted_tag[row]=lsq_rob_tag_mem[row];
                            predicted_address[row]=computed_address[row];
                            base_ready_data_wait |= !rs_src2_ready_effective[entry];
                            base_ready_both_ready |= bool(rs_src2_ready_effective[entry]);
                            base_wakeup_this_cycle |= !rs_src1_ready_mem[entry];
                        }
                    }
                    if (matches>1) throw std::runtime_error("Ambiguous full-tag live RS/LSQ store identity");
                    unknown_store_no_rs |= matches==0;
                }
                for (unsigned row=0; row<N; ++row) {
                    if (!active(row) || !lsq_load_mem[row] || !lsq_addr_ready_mem[row] ||
                        lsq_request_sent_mem[row] || lsq_complete_mem[row]) continue;
                    bool had_unknown=false, still_unknown=false, overlap_unready=false;
                    const unsigned load_relative=lsq_size_mem[row]==0?1:(lsq_size_mem[row]==1?3:15);
                    const unsigned load_mask=(load_relative<<(lsq_addr_mem[row]&15))&65535;
                    for (unsigned older=0; older<N; ++older) {
                        if (!active(older) || !lsq_store_mem[older] || age(older)>=age(row)) continue;
                        uint32_t address=lsq_addr_mem[older];
                        unsigned relative=lsq_mask_mem[older];
                        if (!lsq_addr_ready_mem[older]) {
                            had_unknown=true;
                            if (!computable[older]) { still_unknown=true; continue; }
                            address=computed_address[older];
                            relative=lsq_size_mem[older]==0?1:(lsq_size_mem[older]==1?3:15);
                        }
                        const unsigned store_mask=(relative<<(address&15))&65535;
                        overlap_unready |= (address>>4)==(lsq_addr_mem[row]>>4) &&
                            !lsq_data_ready_mem[older] && bool(store_mask&load_mask);
                    }
                    load_blocked_unknown_but_computable |= had_unknown && !still_unknown;
                    load_counterfactual_eligible |= had_unknown && !still_unknown && !overlap_unready;
                }
                const bool no_candidate=lsq_occupancy_reg && !lsq_candidate_found;
COUNTS
            }'''.replace('ALIASES', '\n'.join(aliases)).replace('RS_N', str(rs_n)).replace('ROB_N', str(rob_n))
    sample = re.sub(r'\bN\b', str(n), sample)
    counts = []
    for name in names:
        if name.startswith('predicted_address_'):
            continue  # Event counts are incremented only by identity checks.
        condition = 'true' if name == 'active_cycles' else (
            'no_candidate && ' + name.removeprefix('no_candidate_') if name.startswith('no_candidate_') else name)
        counts.append(f'                opportunity_{name} += bool({condition});')
    sample = sample.replace('COUNTS', '\n'.join(counts))
    original = driver.read_text()
    official = (ROOT / '.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
    retirement = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
    if original.count(retirement) != 1 or original.replace(retirement, '') != official:
        raise SystemExit('Official observer driver differs beyond retirement print')
    tick, edge, final = '        auto tick = [&]() {', '            memory.drive(top);\n            top.eval();', '        top.final();'
    include = '#include "Vstudent_top___024root.h"\n#include <stdexcept>\n'
    if include in original or any(original.count(anchor)!=1 for anchor in (tick, edge, final)):
        raise SystemExit('Unexpected official driver anchors')
    prints = '\n' + '\n'.join(f'        std::cerr << "OPPORTUNITY {name}=" << opportunity_{name} << std::endl;' for name in names)
    modified = include + original.replace(tick, declarations+tick).replace(edge, edge+sample).replace(final, final+prints)
    if modified.removeprefix(include).replace(declarations+tick, tick).replace(edge+sample, edge).replace(final+prints, final)!=original:
        raise SystemExit('Driver changed outside read-only observations')
    for path, expected in inputs.items():
        if sha(path)!=expected:
            raise SystemExit('Frozen input changed: '+str(path))
    out.mkdir(parents=True)
    source, exe, obj = out/'sim_store_address_opportunity.cpp', out/'sim_store_address_opportunity.exe', out/'observer.o'
    source.write_text(modified)
    helper_copy = out/Path(__file__).name
    shutil.copyfile(__file__, helper_copy)
    runtime = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite/share/verilator/include'
    objects = [build/name for name in ('verilated.o', 'verilated_vcd_c.o', 'verilated_threads.o', 'Vstudent_top__ALL.a')]
    compiler = args.compiler_bin/'g++.exe'
    inputs.update({path:sha(path) for path in [source, helper_copy, Path(__file__).resolve(),
                   ROOT/'tools/observe_course_perf.py', header, runtime/'verilated.h', compiler, *objects, *build.glob('*.h')]})
    env = dict(os.environ)
    env['PATH'] = str(args.compiler_bin)+os.pathsep+env['PATH']
    commands = [[str(compiler), '-Os', '-std=c++17', '-DVL_TIME_CONTEXT', '-I'+str(build), '-I'+str(runtime),
                 '-I'+str(runtime/'vltstd'), '-c', str(source), '-o', str(obj)],
                [str(compiler), str(obj), *map(str, objects), '-pthread', '-lpthread', '-latomic', '-o', str(exe)]]
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    results = []
    for item in reference['results']:
        inputs[Path(item['image'])] = sha(item['image'])
        run = subprocess.run([str(exe), item['image'], str(item['expected_u32']), '20000000', '20'],
                             cwd=ROOT, env=env, text=True, capture_output=True)
        log = out/(item['name']+'.log')
        log.write_text(run.stdout+run.stderr)
        passed = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', run.stdout, re.M)
        retired = re.search(r'^CPU2026 instret=(\d+)$', run.stderr, re.M)
        counters = {name:int(value) for name,value in re.findall(r'^OPPORTUNITY (\w+)=(\d+)$', run.stderr, re.M)}
        if run.returncode or not passed or not retired or set(counters)!=set(names) or \
                (int(passed[1]),int(passed[2]),int(passed[3]),int(retired[1])) != \
                (item['cycles'],item['return_u32'],item['expected_u32'],item['instret']) or counters['active_cycles']!=item['cycles']:
            raise SystemExit('Read-only diagnostic differs from official benchmark: '+str(log))
        result = dict(name=item['name'], cycles=item['cycles'], instret=item['instret'], observations=counters, log_sha256=sha(log))
        results.append(result)
        print(json.dumps(result), flush=True)
    for path,expected in inputs.items():
        if sha(path)!=expected:
            raise SystemExit('Frozen diagnostic input changed: '+str(path))
    report = dict(status='COMPLETE', not_a_grade=True, input_sha256={str(p):h for p,h in inputs.items()},
                  diagnostic_executable_sha256=sha(exe), parameters=params, commands=commands, results=results,
                  sample_phase='low-edge after memory.drive/eval, before memory.step/rising edge; reset excluded',
                  identity='live RS/LSQ stores matched with complete ROB tags, duplicate matches forbidden',
                  validation='all six official cycle/retirement/exit results exact; predicted ready addresses checked against later real LSQ addresses, full-tag recovery/reuse cancellation',
                  caution='Overlapping presence counts; counterfactual assumes all computable addresses published without latency. Not additive CPI or guaranteed IPC gain.')
    (out/'store_address_opportunity.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
