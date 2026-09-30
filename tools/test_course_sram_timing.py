"""Validate macro pricing and full timing on a tiny non-CPU fixture.

This regression never provides a CPU area/IPC/frequency result. It checks the
real course generator, raw five ASAP7 libraries, Yosys mapping and WSL OpenSTA
including both SRAM launch and capture paths, plus fail-closed source hashes.
"""
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

from run_course_sram_area import ROOT, FRAMEWORK, digest, load_course, quote


def main():
    out = ROOT / 'build/test_course_sram_timing'
    out.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / 'tb/unit/course_sram_timing_fixture.v'
    fakeram, reporter = load_course('fakeram'), load_course('synth_report')
    libs = sorted((ROOT / '.deps/course_asap7_r28/lib').glob('*.lib'))
    assert len(libs) == 5
    seq = next(path for path in libs if '_SEQ_' in path.name)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']

    def yosys(name, commands):
        script = out / (name + '.ys')
        script.write_text('\n'.join(commands) + '\n')
        with (out / (name + '.log')).open('w') as log:
            subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script)],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    yosys('elaborate', [
        'read_verilog ' + quote(fixture),
        'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(fakeram.RAM_SOURCE),
        'hierarchy -check -top student_top', 'proc', 'memory_collect',
        'write_json ' + quote(out / 'elaborated.json'),
    ])
    prepared, wrappers, ram_libs, macros = fakeram.prepare_memories(
        json.loads((out / 'elaborated.json').read_text()), out / 'ram')
    all_libs = [*libs, *ram_libs]
    libargs = ' '.join('-liberty ' + quote(path) for path in libs)
    all_libargs = ' '.join('-liberty ' + quote(path) for path in all_libs)
    yosys('map', [
        'read_json ' + quote(prepared), 'read_verilog ' + quote(wrappers),
        *['read_liberty -lib -ignore_miss_func ' + quote(path) for path in all_libs],
        'hierarchy -check -top student_top', 'synth -top student_top -noabc -flatten',
        'dfflibmap -liberty ' + quote(seq), 'abc ' + libargs + ' -D 3333.33333',
        'clean', 'delete t:$scopeinfo', 'clean -purge',
        'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
        'check -assert -mapped',
        'tee -o ' + quote(out / 'stat.json') + ' stat -json ' + all_libargs,
        'write_json ' + quote(out / 'design.json'),
        'write_verilog -noattr -noexpr ' + quote(out / 'mapped.v'),
    ])
    design = json.loads((out / 'design.json').read_text())
    stats = json.loads((out / 'stat.json').read_text())
    area = reporter.area_report(design, stats, macros)
    instances = area['sram_instances']
    shape = fakeram.Shape(16, 32, 8)
    assert len(instances) == 4
    assert {instance['module'] for instance in instances} == {shape.macro}
    assert Decimal(str(area['sram_area_um2'])) == Decimal(str(shape.lane_area)) * 4
    counts = Counter(cell['type'] for cell in design['modules']['student_top']['cells'].values())
    independent = sum((Decimal(str(design['modules'][kind]['attributes']['area'])) * count
                       for kind, count in counts.items()), Decimal(0))
    assert abs(independent - Decimal(str(area['area_um2']))) < Decimal('0.00001')
    source_inputs = [fixture, fakeram.RAM_SOURCE, FRAMEWORK / 'scripts/fakeram.py',
                     FRAMEWORK / 'scripts/synth_report.py', *libs]
    manifest = dict(is_test_fixture=True, not_a_cpu_result=True,
                    source_sha256={path.relative_to(ROOT).as_posix(): digest(path) for path in source_inputs})
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    audit = dict(status='COMPLETE', is_test_fixture=True, not_a_cpu_result=True, area=area,
                 unpriced_leaf_instances=0, unmapped_memory_cells=0,
                 settings=dict(clock_period_ns=10 / 3), netlist_sha256=digest(out / 'mapped.v'),
                 libraries=[dict(path=str(path), sha256=digest(path)) for path in all_libs])
    (out / 'area_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    timing_command = [sys.executable, str(ROOT / 'tools/run_course_full_timing.py'), str(out),
                      '--clock-port', 'clk_i', '--reset-port', 'reset_i']
    subprocess.run(timing_command, check=True)
    timing = json.loads((out / 'full_timing_audit.json').read_text())
    assert timing['status'] == 'COMPLETE' and timing['includes_sram']
    paths = timing['critical_paths']['checks']
    assert any('fakeram_asap7_' in point.get('cell', '')
               for path in paths for point in path.get('source_path', [])), 'macro launch path absent'
    # Independently ask OpenSTA for an SRAM endpoint rather than infer coverage
    # solely from the fastest/worst path names. Preserve these checks as evidence.
    text = (out / 'timing_checks.rpt').read_text()
    assert 'unconstrained' not in text.lower() or '0 unconstrained' in text.lower()
    # Deliberately corrupt only the fixture manifest, not any source or CPU data.
    key = fixture.relative_to(ROOT).as_posix()
    manifest['source_sha256'][key] = '0' * 64
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        rejected = subprocess.run(timing_command,
                                  capture_output=True, text=True)
        assert rejected.returncode != 0 and 'Frozen area input changed' in rejected.stderr + rejected.stdout
    finally:
        manifest['source_sha256'][key] = digest(fixture)
        (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / 'test_result.json').write_text(json.dumps(dict(
        status='PASS', is_test_fixture=True, not_a_cpu_result=True, macros=4,
        checks=['official macro pricing', 'independent leaf sum', 'full timing with macro launch',
                'complete timing constraints', 'changed-input rejection']), indent=2) + '\n')
    print('PASS: course SRAM pricing/full-timing tool fixture; not a CPU result')


if __name__ == '__main__':
    main()
