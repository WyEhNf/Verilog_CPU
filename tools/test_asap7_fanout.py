"""Test actual-library fanout buffering with the default ASAP7 mapping flow.

This is a non-CPU circuit experiment. All buffers remain actual priced Liberty
cells, all ordinary logic is mapped normally, and timing uses original course
constraints. No result from this test is a CPU frequency or area score.
"""
import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from run_course_sram_area import ROOT, FRAMEWORK, digest, load_course, quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / 'rtl/common/rv32_asap7_fanout.v',
               ROOT / 'tb/unit/rv32_asap7_fanout_fixture.v']
    libraries = sorted((ROOT / '.deps/course_asap7_r28/lib').glob('*.lib'))
    if len(libraries) != 5:
        raise SystemExit('Original five RVT TT libraries required')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    inputs = [*sources, *libraries, Path(__file__), FRAMEWORK / 'scripts/synth_report.py',
              FRAMEWORK / 'scripts/timing.tcl', ROOT / 'tools/run_course_full_timing.py']
    frozen = {str(path): digest(path) for path in inputs}
    executable = out / 'functional.vvp'
    command = [str(suite / 'bin/iverilog.exe'), '-g2012', '-s', 'rv32_asap7_fanout_tb',
               '-o', str(executable), *map(str, sources)]
    subprocess.run(command, env=env, check=True)
    subprocess.run([str(suite / 'bin/vvp.exe'), '-N', str(executable)], env=env, check=True)
    reporter = load_course('synth_report')
    prices = {}
    for library in libraries:
        for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                                     library.read_text(), re.S):
            value = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            if not value:
                raise SystemExit('Missing original raw cell area: ' + name)
            prices[name] = Decimal(value[1])
    results = []
    for enabled in (0, 1):
        case = out / f'enabled{enabled}'
        case.mkdir(exist_ok=True)
        seq = next(lib for lib in libraries if '_SEQ_' in lib.name)
        libargs = ' '.join('-liberty ' + quote(lib) for lib in libraries)
        script = case / 'map.ys'
        script.write_text('\n'.join([
            *['read_verilog -sv -D SYNTHESIS ' + quote(path) for path in sources],
            f'chparam -set ENABLED {enabled} rv32_asap7_fanout_fixture',
            'rename rv32_asap7_fanout_fixture student_top',
            *['read_liberty -lib -ignore_miss_func ' + quote(lib) for lib in libraries],
            'hierarchy -check -top student_top', 'synth -top student_top -noabc -flatten',
            'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
            'dfflibmap -liberty ' + quote(seq), 'abc ' + libargs + ' -D 2000',
            'clean', 'delete t:$scopeinfo', 'clean -purge',
            'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
            'check -assert -mapped',
            'tee -o ' + quote(case / 'stat.json') + ' stat -json ' + libargs,
            'write_json ' + quote(case / 'design.json'),
            'write_verilog -noattr -noexpr ' + quote(case / 'mapped.v'),
        ]) + '\n')
        with (case / 'map.log').open('w') as log:
            subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script)],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        model = json.loads((case / 'design.json').read_text())
        stats = json.loads((case / 'stat.json').read_text())
        counts = Counter(cell['type'] for cell in model['modules']['student_top']['cells'].values())
        if set(counts) - set(prices):
            raise SystemExit('Unpriced mapped leaf in fixture')
        area = reporter.area_report(model, stats, {})
        independent = sum((prices[name] * count for name, count in counts.items()), Decimal(0))
        if abs(independent - Decimal(str(area['area_um2']))) > Decimal('.00001'):
            raise SystemExit('Raw-price and reported area differ')
        fixed = [cell for name, cell in model['modules']['student_top']['cells'].items()
                 if name.endswith('.buffer_root') or name.endswith('.buffer_leaf')]
        fixed_counts = Counter(cell['type'] for cell in fixed)
        expected = {'BUFx16f_ASAP7_75t_R': 1, 'BUFx2_ASAP7_75t_R': 16} if enabled else {}
        if dict(fixed_counts) != expected:
            raise SystemExit('Kept physical-buffer instance census differs')
        manifest = dict(is_test_fixture=True, not_a_cpu_result=True,
                        source_sha256={Path(path).relative_to(ROOT).as_posix(): value for path, value in frozen.items()})
        (case / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        audit = dict(status='COMPLETE', is_test_fixture=True, not_a_cpu_result=True, area=area,
                     unpriced_leaf_instances=0, unmapped_memory_cells=0,
                     settings=dict(clock_period_ns=2), netlist_sha256=digest(case / 'mapped.v'),
                     libraries=[dict(path=str(path), sha256=digest(path)) for path in libraries])
        (case / 'area_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
        subprocess.run([sys.executable, str(ROOT / 'tools/run_course_full_timing.py'), str(case),
                        '--clock-port', 'clock'], check=True)
        timing = json.loads((case / 'full_timing_audit.json').read_text())
        results.append(dict(enabled=enabled, area_um2=str(independent), fixed_buffers=expected,
                            fixed_buffer_area_um2=str(sum((prices[k] * v for k, v in expected.items()), Decimal(0))),
                            minimum_period_ns=timing['minimum_period_ns'],
                            estimated_fmax_mhz=timing['estimated_fmax_mhz']))
    for path, expected in frozen.items():
        if digest(Path(path)) != expected:
            raise SystemExit('Fixture input changed while running: ' + path)
    report = dict(status='COMPLETE', is_test_fixture=True, not_a_cpu_result=True,
                  source_sha256=frozen, functional_cycles=1000, results=results)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['results'], indent=2))


if __name__ == '__main__':
    main()
