"""Measure an actual standalone D-cache, explicitly NOT a complete CPU score.

Freeze the candidate controller, original SRAM validator/model, default ABC
and five raw ASAP7 libraries. Retain every Cache port and physical SRAM. Rename
only this Cache root for the course reporter, and time every memory boundary.
The experiment isolates query-index retiming without a simplified controller.
"""
import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from run_course_sram_area import ROOT, FRAMEWORK, digest, load_course, quote
from verify_course_axi_area import expand_stat_census


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--update-mode', type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    out, candidate = args.outdir.resolve(), args.candidate_root.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh standalone Cache PPA directory')
    libs = sorted((ROOT/'.deps/course_asap7_r28/lib').glob('*.lib'))
    if len(libs) != 5 or sum('_SEQ_' in lib.name for lib in libs) != 1:
        raise SystemExit('Exactly five original course libraries required')
    names = [Path(name) for name in (
        'rtl/cache/rv32_dcache_nonblocking.v', 'rtl/cache/rv32_dcache_control_banks.v',
        'rtl/rv32im_defs.vh', 'tools/probe_dcache_registered_index.py',
        'tools/run_course_sram_area.py', 'tools/run_course_full_timing.py',
        'tools/verify_course_axi_area.py')]
    names += [path.relative_to(ROOT) for path in [
        FRAMEWORK/'scripts/ram/sram_fakeram.sv', FRAMEWORK/'scripts/fakeram.py',
        FRAMEWORK/'scripts/synth_report.py', FRAMEWORK/'scripts/timing.py',
        FRAMEWORK/'scripts/timing.tcl', *libs]]
    snapshot, frozen, origins = out/'source_snapshot', {}, {}
    for name in names:
        source = candidate/name if (candidate/name).is_file() else ROOT/name
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        frozen[name.as_posix()] = digest(target)
        origins[name.as_posix()] = dict(path=str(source), sha256=digest(source))
        if digest(target) != digest(source):
            raise SystemExit('Probe snapshot changed during copy')
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    frozen_libs = [snapshot/lib.relative_to(ROOT) for lib in libs]
    saved = lambda name: snapshot/Path(name)
    fakeram, reporter = load_course('fakeram'), load_course('synth_report')
    results = []

    def check_inputs():
        for name, expected in frozen.items():
            if digest(snapshot/name) != expected:
                raise SystemExit('Frozen probe input changed: '+name)
        for row in origins.values():
            if digest(Path(row['path'])) != row['sha256']:
                raise SystemExit('Probe origin changed: '+row['path'])

    def run(case, stage, commands):
        check_inputs()
        script, log = case/(stage+'.ys'), case/(stage+'.log')
        script.write_text('\n'.join(commands)+'\n')
        print(f'START {case.name} {stage}', flush=True)
        with log.open('w') as stream:
            subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                           cwd=snapshot, stdout=stream, stderr=subprocess.STDOUT, check=True)
        check_inputs()
        print(f'DONE {case.name} {stage}', flush=True)

    for registered in (0, 1):
        case = out/f'updates{args.update_mode}_index{registered}'
        case.mkdir()
        parameters = dict(TAG_WIDTH=17, MSHR_ENTRIES=4, WAITER_ENTRIES=8, PREFETCH=1,
                          CACHE_LINES=1024, CACHE_WAYS=2, INDEX_HASH=1,
                          STORE_MERGE_DELAY=16, TAG_SRAM=1,
                          STATIC_UPDATES=args.update_mode, REGISTERED_INDEX=registered)
        run(case, 'elaborate', [
            'read_verilog -sv -D SYNTHESIS -I rtl '+
                quote(saved('rtl/cache/rv32_dcache_nonblocking.v')),
            'read_verilog -sv -D SYNTHESIS '+quote(saved('rtl/cache/rv32_dcache_control_banks.v')),
            'read_verilog -sv -noblackbox -D SYNTHESIS '+
                quote(saved('.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv')),
            'chparam '+' '.join(f'-set {key} {value}' for key, value in parameters.items())+
                ' rv32_dcache_nonblocking',
            'rename rv32_dcache_nonblocking student_top',
            'hierarchy -check -top student_top', 'proc', 'memory_collect',
            'write_json '+quote(case/'elaborated.json')])
        elaborated = json.loads((case/'elaborated.json').read_text())
        prepared, wrappers, ram_libs, macros = fakeram.prepare_memories(elaborated, case/'ram')
        del elaborated
        all_libs = [*frozen_libs, *ram_libs]
        reads = ['read_liberty -lib -ignore_miss_func '+quote(lib) for lib in all_libs]
        libargs = ' '.join('-liberty '+quote(lib) for lib in frozen_libs)
        all_libargs = ' '.join('-liberty '+quote(lib) for lib in all_libs)
        seq = next(lib for lib in frozen_libs if '_SEQ_' in lib.name)
        run(case, 'map', [
            'read_json '+quote(prepared), 'read_verilog '+quote(wrappers), *reads,
            'hierarchy -check -top student_top', 'synth -top student_top -noabc -flatten',
            'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
            'dfflibmap -liberty '+quote(seq), 'abc '+libargs+' -D 2000', 'clean',
            'delete t:$scopeinfo', 'clean -purge',
            'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
            'check -assert -mapped', 'tee -o '+quote(case/'stat.json')+' stat -json '+all_libargs,
            'write_json '+quote(case/'design.json'),
            'write_verilog -noattr -noexpr '+quote(case/'mapped.v'),
            'design -reset', *reads, 'read_verilog '+quote(case/'mapped.v'),
            'hierarchy -check -top student_top', 'check -assert -mapped'])
        design = json.loads((case/'design.json').read_text())
        statistics = json.loads((case/'stat.json').read_text())
        area = reporter.area_report(design, statistics, macros)
        leaves, hierarchy = expand_stat_census(statistics)
        prices = {}
        for lib in all_libs:
            for kind, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                                         lib.read_text(), re.S):
                match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
                if not match:
                    raise SystemExit('Raw leaf price missing: '+kind)
                price = Decimal(match[1])
                if kind in prices and prices[kind] != price:
                    raise SystemExit('Conflicting raw leaf price: '+kind)
                prices[kind] = price
        if set(leaves)-set(prices):
            raise SystemExit('Unpriced actual Cache leaf')
        actual_sram = Counter(entry['module'] for entry in area['sram_instances'])
        if actual_sram != Counter({kind: count for kind, count in leaves.items() if kind in macros}):
            raise SystemExit('Actual Cache SRAM census differs')
        total = sum((prices[kind]*count for kind, count in leaves.items()), Decimal(0))
        if abs(total-Decimal(str(area['area_um2']))) >= Decimal('0.00001'):
            raise SystemExit('Course and independent raw-price area differ')
        del design
        check_inputs()
        settings = dict(clock_period_ns=2.0, parameters=parameters)
        audit = dict(status='COMPLETE', area=area, independent_area_um2=str(total),
                     leaf_counts=dict(leaves), leaf_instances=sum(leaves.values()),
                     functional_hierarchy_instances=sum(hierarchy.values()),
                     unpriced_leaf_instances=0, unmapped_memory_cells=0,
                     is_test_fixture=True, not_a_cpu_result=True, includes_axi_adapter=False,
                     settings=settings, netlist_sha256=digest(case/'mapped.v'),
                     libraries=[dict(path=str(lib), sha256=digest(lib)) for lib in all_libs])
        (case/'area_audit.json').write_text(json.dumps(audit, indent=2)+'\n')
        (case/'run_manifest.json').write_text(json.dumps(dict(source_sha256=frozen,
            source_snapshot_root=str(snapshot), not_a_cpu_result=True, settings=settings), indent=2)+'\n')
        print(f'AREA {case.name} {total} um2; standalone actual Cache, NOT CPU', flush=True)
        subprocess.run([sys.executable, str(ROOT/'tools/run_course_full_timing.py'), str(case),
                        '--clock-port', 'clk_i', '--reset-port', 'reset_i'], env=env, check=True)
        timing = json.loads((case/'full_timing_audit.json').read_text())
        if not timing['not_a_cpu_result'] or not timing['includes_sram'] or timing['omitted_memory_boundaries']:
            raise SystemExit('Standalone Cache timing scope changed')
        results.append(dict(parameters=parameters, area_um2=str(total),
                            sram_instances=sum(actual_sram.values()), netlist_sha256=audit['netlist_sha256'],
                            estimated_fmax_mhz=timing['estimated_fmax_mhz'],
                            minimum_period_ns=timing['minimum_period_ns']))
    check_inputs()
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE', not_a_cpu_result=True,
        integrated_into_cpu=False, compiled_origins=origins, snapshot_sha256=frozen,
        yosys_sha256=digest(yosys), results=results,
        scope='Actual complete standalone D-cache controller and all physical SRAM; not CPU IPC or CPU PPA'), indent=2)+'\n')
    print('COMPLETE: two actual standalone Cache PPA profiles; NOT CPU scores', flush=True)


if __name__ == '__main__':
    main()
