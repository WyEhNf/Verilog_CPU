"""Compare real mapped frontends before/after queue-read changes.

These are isolated frontend diagnostics, NOT CPU area or frequency scores.
Both designs keep all ports and use default ABC, the five raw course ASAP7
libraries and complete memory_map; no storage is blackboxed or excluded.
"""
from collections import Counter
from decimal import Decimal
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from run_course_sram_area import ROOT, digest, load_course, quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    sources = {'baseline': args.baseline.resolve(),
               'onehot': ROOT / 'rtl/frontend/rv32_fetch_frontend.v'}
    libs = sorted((ROOT / '.deps/course_asap7_r28/lib').glob('*.lib'))
    if len(libs) != 5:
        raise SystemExit('Exactly five original course libraries required')
    seq = next(path for path in libs if '_SEQ_' in path.name)
    reporter = load_course('synth_report')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = os.environ.copy()
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    inputs = {str(p): digest(p) for p in [*sources.values(), *libs,
              ROOT / 'rtl/rv32im_defs.vh', Path(__file__)]}
    libargs = ' '.join('-liberty ' + quote(path) for path in libs)
    results = {}
    for name, source in sources.items():
        out = args.outdir.resolve() / name
        out.mkdir(parents=True, exist_ok=True)
        script, log = out / 'map.ys', out / 'map.log'
        script.write_text('\n'.join([
            'read_verilog -Irtl ' + quote(source),
            'chparam -set FE_WIDTH 4 -set FQ_DEPTH 16 rv32_fetch_frontend',
            'rename rv32_fetch_frontend student_top',
            *['read_liberty -lib -ignore_miss_func ' + quote(path) for path in libs],
            'synth -top student_top -flatten -noabc', 'check -assert',
            'dfflibmap -liberty ' + quote(seq), 'abc ' + libargs + ' -D 2000',
            'clean', 'delete t:$scopeinfo', 'clean -purge',
            'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
            'check -assert -mapped',
            'tee -o ' + quote(out / 'stat.json') + ' stat -json ' + libargs,
            'write_json ' + quote(out / 'design.json'),
            'write_verilog -noattr -noexpr ' + quote(out / 'mapped.v'),
        ]) + '\n')
        print('START: isolated frontend ' + name, flush=True)
        with log.open('w') as stream:
            subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script)],
                           cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        design = json.loads((out / 'design.json').read_text())
        stats = json.loads((out / 'stat.json').read_text())
        area = reporter.area_report(design, stats, {})
        counts = Counter(cell['type'] for cell in design['modules']['student_top']['cells'].values())
        if sum(counts.values()) != stats['design']['num_cells']:
            raise SystemExit('Leaf count mismatch')
        if stats['design']['num_memories'] or stats['design']['num_memory_bits']:
            raise SystemExit('Unmapped memory remains')
        independent = sum((Decimal(str(design['modules'][kind]['attributes']['area'])) * count
                           for kind, count in counts.items()), Decimal(0))
        if abs(independent - Decimal(str(area['area_um2']))) > Decimal('.00001'):
            raise SystemExit('Independent area mismatch')
        settings = dict(clock_period_ns=2.0, FE_WIDTH=4, FQ_DEPTH=16, abc_script='standard')
        manifest = dict(is_test_fixture=True, not_a_cpu_result=True, source_sha256=inputs,
                        settings=settings)
        (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        audit = dict(status='COMPLETE', is_test_fixture=True, not_a_cpu_result=True,
                     component='isolated rv32_fetch_frontend', area=area,
                     independent_area_um2=str(independent), leaf_instances=sum(counts.values()),
                     unpriced_leaf_instances=0, unmapped_memory_cells=0, settings=settings,
                     netlist_sha256=digest(out / 'mapped.v'),
                     libraries=[dict(path=str(p), sha256=digest(p)) for p in libs])
        (out / 'area_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
        subprocess.run([sys.executable, str(ROOT / 'tools/run_course_full_timing.py'), str(out),
                        '--clock-port', 'clk_i', '--reset-port', 'reset_i'], check=True)
        timing = json.loads((out / 'full_timing_audit.json').read_text())
        results[name] = dict(area_um2=str(independent),
                             estimated_fmax_mhz=timing['estimated_fmax_mhz'],
                             minimum_period_ns=timing['minimum_period_ns'],
                             leaf_instances=sum(counts.values()), netlist_sha256=audit['netlist_sha256'])
    for name, expected in inputs.items():
        if digest(Path(name)) != expected:
            raise SystemExit('Input changed during frontend diagnostic: ' + name)
    report = dict(status='COMPLETE', not_a_cpu_result=True,
                  source_sha256=inputs, results=results)
    (args.outdir / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['results'], indent=2))


if __name__ == '__main__':
    main()
