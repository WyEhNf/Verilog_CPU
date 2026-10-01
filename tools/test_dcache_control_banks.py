"""Validate functional cache-control banks through the original course flow.

This isolated fixture is NOT a CPU result. Keep hierarchy on real logic/state
modules, retain the original RAM validator/default ABC/raw libraries, and price
every physical leaf. No library edits, buffer stubs, memory omissions or new
constraints. Functional tests cover priorities, byte masks and warm reset.
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
import time

from run_course_sram_area import ROOT, FRAMEWORK, digest, load_course, quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--timing', action='store_true')
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh control-bank diagnostic directory')
    snapshot = out / 'source_snapshot'
    banks = ROOT / 'rtl/cache/rv32_dcache_control_banks.v'
    fixture = ROOT / 'tb/unit/rv32_dcache_control_banks_fixture.v'
    libs = sorted((ROOT / '.deps/course_asap7_r28/lib').glob('*.lib'))
    if len(libs) != 5:
        raise SystemExit('Exactly five original course libraries required')
    sources = [banks, fixture, Path(__file__).resolve(), ROOT / 'tools/run_course_sram_area.py',
               ROOT / 'tools/run_course_full_timing.py', FRAMEWORK / 'scripts/ram/sram_fakeram.sv',
               FRAMEWORK / 'scripts/fakeram.py', FRAMEWORK / 'scripts/synth_report.py',
               FRAMEWORK / 'scripts/timing.py', FRAMEWORK / 'scripts/timing.tcl', *libs]
    originals, frozen = {}, {}
    for source in sources:
        name = source.relative_to(ROOT)
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        originals[str(source)] = digest(source)
        frozen[name.as_posix()] = digest(destination)
        if digest(destination) != originals[str(source)]:
            raise SystemExit('Source snapshot differs')
    banks = snapshot / banks.relative_to(ROOT)
    fixture = snapshot / fixture.relative_to(ROOT)
    ram = snapshot / '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'
    libs = [snapshot / lib.relative_to(ROOT) for lib in libs]
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    fakeram, reporter = load_course('fakeram'), load_course('synth_report')
    results = []
    for lines in (16, 64, 1024):
        for ways in (1, 2):
            for rows in (16, 32):
                if rows > lines:
                    continue
                name = f'lines{lines}_ways{ways}_rows{rows}'
                executable, log = out / (name + '.vvp'), out / (name + '.log')
                command = [str(suite / 'bin/iverilog.exe'), '-g2012', '-s', 'rv32_dcache_control_banks_tb',
                           '-P', f'rv32_dcache_control_banks_tb.CACHE_LINES={lines}',
                           '-P', f'rv32_dcache_control_banks_tb.CACHE_WAYS={ways}',
                           '-P', f'rv32_dcache_control_banks_tb.GROUP_ROWS={rows}',
                           '-o', str(executable), str(banks), str(fixture), str(ram)]
                with log.open('w') as stream:
                    subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
                    subprocess.run([str(suite / 'bin/vvp.exe'), '-N', str(executable)], env=env,
                                   stdout=stream, stderr=subprocess.STDOUT, check=True)
                text = log.read_text()
                if 'PASS: cache-control banks 2000 cycles' not in text or re.search(r'(?im)^.*(?:ERROR|FATAL|FAIL)', text):
                    raise SystemExit('Functional bank identity failed: ' + str(log))
                results.append(dict(name=name, status='PASS', cycles=2000, log_sha256=digest(log)))
                print('PASS ' + name, flush=True)

    def run(case, name, commands):
        script, log = case / (name + '.ys'), case / (name + '.log')
        script.write_text('\n'.join(commands) + '\n')
        started = time.monotonic()
        with log.open('w') as stream:
            subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script)], env=env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        print(f'DONE {case.name} {name} {time.monotonic()-started:.2f}s', flush=True)

    ppa = []
    for enabled in (0, 1):
        case = out / f'banked{enabled}'
        case.mkdir()
        run(case, 'elaborate', [
            'read_verilog -sv -D SYNTHESIS ' + quote(banks),
            'read_verilog -sv -D SYNTHESIS ' + quote(fixture),
            'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(ram),
            f'chparam -set BANKED {enabled} -set CACHE_LINES 1024 -set CACHE_WAYS 2 -set GROUP_ROWS 16 student_top',
            'hierarchy -check -top student_top', 'proc', 'memory_collect',
            'write_json ' + quote(case / 'elaborated.json')])
        design = json.loads((case / 'elaborated.json').read_text())
        prepared, wrappers, ram_libs, macros = fakeram.prepare_memories(design, case / 'ram')
        all_libs = [*libs, *ram_libs]
        libargs = ' '.join('-liberty ' + quote(lib) for lib in libs)
        all_libargs = ' '.join('-liberty ' + quote(lib) for lib in all_libs)
        libreads = ['read_liberty -lib -ignore_miss_func ' + quote(lib) for lib in all_libs]
        sequential = next(lib for lib in libs if '_SEQ_' in lib.name)
        run(case, 'map', [
            'read_json ' + quote(prepared), 'read_verilog ' + quote(wrappers), *libreads,
            'hierarchy -check -top student_top', 'synth -top student_top -noabc -flatten',
            'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
            'dfflibmap -liberty ' + quote(sequential), 'abc ' + libargs + ' -D 2000',
            'clean', 'delete t:$scopeinfo', 'clean -purge',
            'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
            'check -assert -mapped', 'tee -o ' + quote(case / 'stat.json') + ' stat -json ' + all_libargs,
            'write_json ' + quote(case / 'design.json'), 'write_verilog -noattr -noexpr ' + quote(case / 'mapped.v'),
            'design -reset', *libreads, 'read_verilog ' + quote(case / 'mapped.v'),
            'hierarchy -check -top student_top', 'check -assert -mapped'])
        design = json.loads((case / 'design.json').read_text())
        statistics = json.loads((case / 'stat.json').read_text())
        raw_prices = {}
        for lib in all_libs:
            for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)', lib.read_text(), re.S):
                match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
                if not match:
                    raise SystemExit('Unpriced raw library cell: ' + name)
                raw_prices[name] = Decimal(match[1])
        leaves, functional_banks = Counter(), Counter()

        def visit(kind, ancestors=()):
            if kind in ancestors:
                raise SystemExit('Recursive mapped hierarchy')
            for cell in design['modules'][kind].get('cells', {}).values():
                child = cell['type']
                if child in raw_prices:
                    leaves[child] += 1
                elif child in design['modules'] and not int(design['modules'][child].get('attributes', {}).get('blackbox', '0'), 2):
                    source_name = design['modules'][child].get('attributes', {}).get('hdlname', child).split()[0]
                    functional_banks[source_name] += 1
                    visit(child, ancestors + (kind,))
                else:
                    raise SystemExit('Unpriced or undeclared mapped leaf: ' + child)

        visit('student_top')
        if {name: count for name, count in leaves.items() if name in macros} != {'fakeram_asap7_16x8': 4}:
            raise SystemExit('All four real byte-masked SRAM macros must remain')
        if statistics['design']['num_memories'] or statistics['design']['num_memory_bits']:
            raise SystemExit('Unmapped memory objects remain')
        if enabled and (functional_banks['rv32_dcache_metadata_bank'] != 64 or
                        functional_banks['rv32_dcache_mshr_data_bank'] != 4):
            raise SystemExit('Functional logic/state hierarchy was unexpectedly flattened')
        area = reporter.area_report(design, statistics, macros)
        total = sum((raw_prices[name] * count for name, count in leaves.items()), Decimal(0))
        if abs(total - Decimal(str(area['area_um2']))) > Decimal('0.00001'):
            raise SystemExit('Original and independent Decimal area sums differ')
        audit = dict(status='COMPLETE', area=area, independent_area_um2=str(total),
                     unpriced_leaf_instances=0, unmapped_memory_cells=0,
                     settings=dict(clock_period_ns=2.0), is_test_fixture=True, not_a_cpu_result=True,
                     netlist_sha256=digest(case / 'mapped.v'), leaf_counts=dict(leaves),
                     functional_banks=dict(functional_banks),
                     libraries=[dict(path=str(lib), sha256=digest(lib)) for lib in all_libs])
        (case / 'area_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
        (case / 'run_manifest.json').write_text(json.dumps(dict(source_sha256=frozen,
            source_snapshot_root=str(snapshot), not_a_cpu_result=True), indent=2) + '\n')
        result = dict(banked=enabled, status='PASS', area_um2=str(total), leaf_instances=sum(leaves.values()),
                      functional_banks=dict(functional_banks), sram_instances=4, netlist_sha256=audit['netlist_sha256'])
        if args.timing:
            subprocess.run(['python', str(ROOT / 'tools/run_course_full_timing.py'), str(case), '--clock-port', 'clock'],
                           env=env, check=True)
            timing = json.loads((case / 'full_timing_audit.json').read_text())
            if not timing['not_a_cpu_result'] or timing['omitted_memory_boundaries']:
                raise SystemExit('Fixture timing scope changed')
            result.update({key: timing[key] for key in ('minimum_period_ns', 'estimated_fmax_mhz', 'worst_setup_slack_ns')})
        ppa.append(result)
        print(json.dumps(result), flush=True)
    for source, expected in originals.items():
        if digest(Path(source)) != expected:
            raise SystemExit('Original input changed during control-bank test: ' + source)
    for source, expected in frozen.items():
        if digest(snapshot / source) != expected:
            raise SystemExit('Frozen input changed during control-bank test: ' + source)
    report = dict(status='COMPLETE', not_a_cpu_result=True, integrated_into_cpu=False,
                  input_sha256=originals, snapshot_sha256=frozen, functional_results=results, fixture_ppa=ppa,
                  scope='isolated valid/dirty/LRU/MSHR-data state banks; not full cache protocol or whole CPU equivalence',
                  flow='original SRAM validator, synth -flatten respecting real keep_hierarchy, default ABC and raw five libraries')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: functional cache-control bank fixture; NOT a CPU result', flush=True)


if __name__ == '__main__':
    main()
