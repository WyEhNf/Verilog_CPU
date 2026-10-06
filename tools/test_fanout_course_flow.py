"""Check non-CPU fanout views against the UNMODIFIED course RAM/mapping flow.

The course's prepare_memories validator runs before read_liberty, just as in
CPU synthesis. Every final physical leaf is independently priced from the raw
five ASAP7 libraries or actual generated SRAM macro. No bypass/overwrite flags
or framework edits are used. Snapshot all inputs before starting either case.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--views', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--registered', action='store_true',
                        help='Test pure RTL control-register replicas, not physical cells')
    parser.add_argument('--timing', action='store_true',
                        help='Run the original full-SRAM STA on each fixture netlist')
    parser.add_argument('--expect-rejected', action='store_true',
                        help='Negative control: enabled physical views must be rejected')
    args = parser.parse_args()
    out = args.outdir.resolve()
    if (out / 'report.json').exists():
        raise SystemExit('A completed probe exists; choose a fresh output directory')
    snapshot = out / 'source_snapshot'
    libs = sorted((ROOT / '.deps/course_asap7_r28/lib').glob('*.lib'))
    if len(libs) != 5:
        raise SystemExit('The original five course RVT TT libraries are required')
    inputs = [args.views.resolve(), ROOT / ('tb/unit/rv32_registered_fanout_fixture.v'
                                          if args.registered else 'tb/unit/rv32_asap7_fanout_fixture.v'),
              ROOT / 'tb/unit/rv32_asap7_fanout_course_fixture.v',
              FRAMEWORK / 'scripts/ram/sram_fakeram.sv',
              FRAMEWORK / 'scripts/fakeram.py', FRAMEWORK / 'scripts/synth_report.py',
              Path(__file__).resolve(), ROOT / 'tools/run_course_sram_area.py',
              ROOT / 'tools/run_course_full_timing.py', FRAMEWORK / 'scripts/timing.py',
              FRAMEWORK / 'scripts/timing.tcl', *libs]
    originals, frozen = {}, {}
    for source in inputs:
        name = source.relative_to(ROOT)
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(source)
        if target.exists() and digest(target) != expected:
            raise SystemExit('Existing input snapshot differs: ' + str(target))
        shutil.copyfile(source, target)
        originals[str(source)] = expected
        frozen[str(target)] = expected
    saved = lambda source: snapshot / Path(source).resolve().relative_to(ROOT)
    views, fixture, wrapper, ram_source = map(saved, inputs[:4])
    frozen_libs = [saved(lib) for lib in libs]
    # Verify both functional cells really are A->Y in the untouched library.
    invbuf = next(lib for lib in frozen_libs if '_INVBUF_' in lib.name)
    for cell_name in ('BUFx16f_ASAP7_75t_R', 'BUFx2_ASAP7_75t_R'):
        body = re.search(r'\bcell\s*\(\s*' + re.escape(cell_name) +
                         r'\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)', invbuf.read_text(), re.S)
        if not body or not re.search(r'\bfunction\s*:\s*"A"', body[1]):
            raise SystemExit('Original buffer truth function is not A->Y')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    fakeram, reporter = load_course('fakeram'), load_course('synth_report')
    results = []
    if args.registered:
        functional = out / 'functional.vvp'
        subprocess.run([str(suite / 'bin/iverilog.exe'), '-g2012', '-s', 'rv32_registered_fanout_tb',
                        '-o', str(functional), str(views), str(fixture)], env=env, check=True)
        subprocess.run([str(suite / 'bin/vvp.exe'), '-N', str(functional)], env=env, check=True)

    def run(case, stage, commands):
        script, log = case / (stage + '.ys'), case / (stage + '.log')
        script.write_text('\n'.join(commands) + '\n')
        with log.open('w') as stream:
            result = subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script)],
                                    cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            failure = dict(status='FAILED', stage=stage, case=case.name,
                           is_test_fixture=True, not_a_cpu_result=True,
                           no_framework_overrides=True, exit_code=result.returncode,
                           diagnostic_tail=log.read_text().splitlines()[-30:],
                           source_sha256=originals, frozen_sha256=frozen)
            (out / 'failure.json').write_text(json.dumps(failure, indent=2) + '\n')
            result.check_returncode()

    for enabled in (0, 1):
        case = out / ('enabled' + str(enabled))
        case.mkdir(parents=True, exist_ok=True)
        run(case, 'elaborate', [
            *['read_verilog -sv -D SYNTHESIS ' + quote(path) for path in (views, fixture, wrapper)],
            'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(ram_source),
            f'chparam -set ENABLED {enabled} -set REGISTERED {int(args.registered)} student_top',
            'hierarchy -check -top student_top', 'proc', 'memory_collect',
            'write_json ' + quote(case / 'elaborated.json')])
        model = json.loads((case / 'elaborated.json').read_text())
        try:
            prepared, ram_wrappers, ram_libs, macros = fakeram.prepare_memories(model, case / 'ram')
        except ValueError as error:
            if not args.expect_rejected or not enabled or 'unsupported external module' not in str(error):
                raise
            results.append(dict(enabled=enabled, status='EXPECTED_REJECTION', error=str(error)))
            print('EXPECTED_REJECTION enabled1: ' + str(error), flush=True)
            continue
        if args.expect_rejected and enabled:
            raise SystemExit('Negative-control source unexpectedly passed official validation')
        all_libs = [*frozen_libs, *ram_libs]
        raw_prices = {}
        for lib in all_libs:
            for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                                         lib.read_text(), re.S):
                area = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
                if not area:
                    raise SystemExit('A library cell has no raw area: ' + name)
                raw_prices[name] = Decimal(area[1])
        libargs = ' '.join('-liberty ' + quote(lib) for lib in frozen_libs)
        all_libargs = ' '.join('-liberty ' + quote(lib) for lib in all_libs)
        seq = next(lib for lib in frozen_libs if '_SEQ_' in lib.name)
        libreads = ['read_liberty -lib -ignore_miss_func ' + quote(lib) for lib in all_libs]
        run(case, 'map', [
            'read_json ' + quote(prepared), 'read_verilog ' + quote(ram_wrappers), *libreads,
            'hierarchy -check -top student_top', 'synth -top student_top -noabc -flatten',
            'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
            'dfflibmap -liberty ' + quote(seq), 'abc ' + libargs + ' -D 2000',
            'clean', 'delete t:$scopeinfo', 'clean -purge',
            'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
            'check -assert -mapped',
            'tee -o ' + quote(case / 'stat.json') + ' stat -json ' + all_libargs,
            'write_json ' + quote(case / 'design.json'),
            'write_verilog -noattr -noexpr ' + quote(case / 'mapped.v'),
            'design -reset', *libreads, 'read_verilog ' + quote(case / 'mapped.v'),
            'hierarchy -check -top student_top', 'check -assert -mapped'])
        design = json.loads((case / 'design.json').read_text())
        stats = json.loads((case / 'stat.json').read_text())
        cells = design['modules']['student_top']['cells']
        counts = Counter(cell['type'] for cell in cells.values())
        if set(counts) - set(raw_prices) or stats['design']['num_memories'] or stats['design']['num_memory_bits']:
            raise SystemExit('Unpriced leaf or unmapped memory remains')
        if dict(counts) != stats['design']['num_cells_by_type']:
            raise SystemExit('Actual physical leaf census differs from statistics')
        fixed = Counter(cell['type'] for name, cell in cells.items()
                        if name.endswith('.buffer_root') or name.endswith('.buffer_leaf'))
        expected = {'BUFx16f_ASAP7_75t_R': 1, 'BUFx2_ASAP7_75t_R': 16} if enabled and not args.registered else {}
        if dict(fixed) != expected:
            raise SystemExit('Actual retained physical buffer census differs')
        sram_counts = {name: count for name, count in counts.items() if name in macros}
        if sram_counts != {'fakeram_asap7_16x8': 4}:
            raise SystemExit('Expected all four actual byte-masked SRAM lanes')
        area = reporter.area_report(design, stats, macros)
        total = sum((raw_prices[name] * count for name, count in counts.items()), Decimal(0))
        if abs(total - Decimal(str(area['area_um2']))) > Decimal('.00001'):
            raise SystemExit('Official and independent physical area sums differ')
        result = dict(enabled=enabled, status='PASS', area_um2=str(total),
                      fixed_buffers=dict(fixed), sram_counts=sram_counts,
                      unpriced_leaves=0, unmapped_memory_bits=0,
                      netlist_sha256=digest(case / 'mapped.v'))
        if args.registered:
            flop_count = sum(count for name, count in counts.items() if name.startswith('DFF'))
            expected_flops = 1024 + (16 if enabled else 1)
            if flop_count != expected_flops:
                raise SystemExit(f'Register banks were merged or omitted: {flop_count} != {expected_flops}')
            result['physical_flops'] = flop_count
            sink_count = Counter(bit for cell in cells.values()
                                 for pin, bits in cell['connections'].items()
                                 if cell['port_directions'][pin] == 'input'
                                 for bit in bits if isinstance(bit, int))
            names = design['modules']['student_top']['netnames']
            controls = {bit for name, net in names.items()
                        if name.endswith('.value_q') for bit in net['bits']}
            expected_controls = 16 if enabled else 1
            if len(controls) != expected_controls:
                raise SystemExit('Control-register output aliases were unexpectedly merged')
            # DFFHQN exposes an inverted physical output. ABC may consume
            # that polarity directly and leave the kept positive alias unused;
            # resolve each public Q through genuine INV cells to its real FF.
            drivers = {bit: cell for cell in cells.values()
                       for pin, bits in cell['connections'].items()
                       if cell['port_directions'][pin] == 'output'
                       for bit in bits if isinstance(bit, int)}
            physical_controls = set()
            for bit in controls:
                driver = drivers.get(bit)
                if driver and driver['type'].startswith('INV'):
                    bit = driver['connections']['A'][0]
                    driver = drivers.get(bit)
                if not driver or not driver['type'].startswith('DFF'):
                    raise SystemExit('Control Q alias does not resolve to an actual physical FF')
                physical_controls.add(bit)
            if len(physical_controls) != expected_controls:
                raise SystemExit('Control FFs are physically shared despite distinct aliases')
            result['maximum_control_ff_output_fanout'] = max(sink_count[bit] for bit in physical_controls)
        if args.timing:
            (case / 'run_manifest.json').write_text(json.dumps(dict(
                source_snapshot_root=str(snapshot),
                source_sha256={Path(path).relative_to(ROOT).as_posix(): value
                               for path, value in originals.items()},
                is_test_fixture=True, not_a_cpu_result=True), indent=2) + '\n')
            (case / 'area_audit.json').write_text(json.dumps(dict(
                status='COMPLETE', area=area, settings=dict(clock_period_ns=2),
                unpriced_leaf_instances=0, unmapped_memory_cells=0,
                is_test_fixture=True, not_a_cpu_result=True,
                netlist_sha256=result['netlist_sha256'],
                libraries=[dict(path=str(lib), sha256=digest(lib)) for lib in all_libs]), indent=2) + '\n')
            subprocess.run([sys.executable, str(ROOT / 'tools/run_course_full_timing.py'),
                            str(case), '--clock-port', 'clock'], check=True)
            timing = json.loads((case / 'full_timing_audit.json').read_text())
            result['minimum_period_ns'] = timing['minimum_period_ns']
            result['estimated_fmax_mhz'] = timing['estimated_fmax_mhz']
        results.append(result)
        print('PASS official prepare+mapping enabled' + str(enabled), flush=True)
    for path, expected in (originals | frozen).items():
        if digest(Path(path)) != expected:
            raise SystemExit('Probe input changed: ' + path)
    report = dict(status='COMPLETE', is_test_fixture=True, not_a_cpu_result=True,
                  includes_official_prepare_memories=True, no_framework_overrides=True,
                  negative_control=args.expect_rejected, source_sha256=originals,
                  registered_control=args.registered,
                  frozen_sha256=frozen, results=results)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
