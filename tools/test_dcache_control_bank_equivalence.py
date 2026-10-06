"""Prove isolated cache-control bank state against its priority reference.

The fixture reference is explicit state-update logic, not the complete cache.
This proof covers the valid/dirty/LRU/MSHR-data state for arbitrary inputs,
including colliding writes and reset. It does not establish CPU integration,
SRAM data-array behavior, full cache protocol or whole-core equivalence.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh sequential proof directory')
    sources = [ROOT / 'rtl/cache/rv32_dcache_control_banks.v',
               ROOT / 'tb/unit/rv32_dcache_control_banks_fixture.v', Path(__file__).resolve(),
               ROOT / 'tools/observe_course_perf.py',
               ROOT / '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv']
    snapshots, hashes = [], {}
    for source in sources:
        target = out / 'source_snapshot' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        snapshots.append(target)
        hashes[str(source)] = sha(source)
        hashes[str(target)] = sha(target)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    cases = [(lines, ways, rows) for lines in (16, 64, 1024) for ways in (1, 2)
             for rows in ((16, 32) if lines == 64 else (16,))]
    results = []
    for lines, ways, rows in cases:
        name = f'lines{lines}_ways{ways}_rows{rows}'
        script, log = out / (name + '.ys'), out / (name + '.log')
        commands = []
        for banked, renamed in ((0, 'gold'), (1, 'gate')):
            commands.extend([
                'read_verilog -sv -D SYNTHESIS ' + quote(snapshots[0]),
                'read_verilog -sv -D SYNTHESIS ' + quote(snapshots[1]),
                'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(snapshots[4]),
                f'chparam -set BANKED {banked} -set CACHE_LINES {lines} -set CACHE_WAYS {ways} -set GROUP_ROWS {rows} rv32_dcache_control_state',
                'hierarchy -check -top rv32_dcache_control_state', 'proc',
                # Proof-only flattening compares all actual functions/state.
                # The PPA flow separately preserves the real bank hierarchy.
                'setattr -mod -unset keep_hierarchy', 'flatten', 'opt_expr', 'opt_clean',
                'rename rv32_dcache_control_state ' + renamed,
                'design -stash ' + renamed, 'design -reset'])
        commands.extend([
            'design -copy-from gold -as gold gold', 'design -copy-from gate -as gate gate',
            'equiv_make gold gate equiv', 'hierarchy -check -top equiv', 'check -assert',
            'equiv_struct -icells', 'equiv_simple -seq 1', 'equiv_induct -seq 4', 'equiv_status -assert'])
        script.write_text('\n'.join(commands) + '\n')
        print('START ' + name, flush=True)
        with log.open('w') as stream:
            run = subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                                 stdout=stream, stderr=subprocess.STDOUT)
        text = log.read_text()
        counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
        if run.returncode or not counts or int(counts[-1][1]) or 'Equivalence successfully proven!' not in text:
            raise SystemExit('Control-bank sequential equivalence NOT proven: ' + str(log))
        results.append(dict(name=name, status='PROVEN', proven_cells=int(counts[-1][0]),
                            unproven_cells=0, log_sha256=sha(log), script_sha256=sha(script)))
        print('PROVEN ' + name, flush=True)
    for path, expected in hashes.items():
        if sha(Path(path)) != expected:
            raise SystemExit('Frozen proof input changed: ' + path)
    report = dict(status='COMPLETE', input_sha256=hashes, results=results,
                  integrated_into_cpu=False, proves_whole_cache=False, proves_whole_cpu=False, claims_cpu_ppa=False,
                  scope='isolated valid/dirty/LRU/MSHR-data state vs explicit priority reference; arbitrary inputs')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: eight isolated cache-control state proofs; NOT whole-cache/CPU equivalence')


if __name__ == '__main__':
    main()
