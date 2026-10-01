"""Prove the SV-compatible RAT candidate against its literal-proven snapshot.

The only candidate changes are comments and a local identifier ('matches' is
an SV keyword). Preserve the completed eight-case literal-backend evidence,
and independently prove every recovery output of the current module. This
does not prove the new CPU instance wiring or whole-core sequential behavior.
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
    parser.add_argument('--reference-proof', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    reference_dir, out = args.reference_proof.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh proof output directory')
    reference_report = reference_dir / 'report.json'
    reference = json.loads(reference_report.read_text())
    if reference['status'] != 'COMPLETE' or len(reference['results']) != 8 or any(
            row['status'] != 'PROVEN' or row['unproven_cells'] for row in reference['results']):
        raise SystemExit('Complete eight-case literal-backend proof required')
    for path, expected in reference['source_sha256'].items():
        if sha(path) != expected:
            raise SystemExit('Literal proof input changed: ' + path)
    prior = reference_dir / 'source_snapshot/rtl/backend/rv32_rat_recovery.v'
    current = ROOT / 'rtl/backend/rv32_rat_recovery.v'
    out.mkdir(parents=True)
    snapshots = []
    for source, name in ((prior, 'literal_proven_candidate.v'), (current, 'current_candidate.v'),
                         (Path(__file__).resolve(), Path(__file__).name)):
        target = out / name
        shutil.copyfile(source, target)
        snapshots.append(target)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes = {str(path): sha(path) for path in [prior, current, reference_report, yosys, *snapshots]}
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for depth, width in ((8, 6), (16, 6), (32, 6), (32, 7)):
        for implementation in (0, 1):
            name = f'rob{depth}_paw{width}_impl{implementation}'
            script, log = out / (name + '.ys'), out / (name + '.log')
            script.write_text('\n'.join([
                'read_verilog ' + quote(snapshots[0]),
                f'chparam -set ROB_ENTRIES {depth} -set PAW {width} -set IMPL {implementation} rv32_rat_recovery',
                'rename rv32_rat_recovery gold', 'read_verilog -sv ' + quote(snapshots[1]),
                f'chparam -set ROB_ENTRIES {depth} -set PAW {width} -set IMPL {implementation} rv32_rat_recovery',
                'rename rv32_rat_recovery gate', 'proc', 'flatten gold gate', 'opt_expr', 'opt_clean',
                'equiv_make gold gate equiv', 'hierarchy -check -top equiv', 'check -assert',
                'equiv_struct -icells', 'equiv_simple', 'equiv_status -assert']) + '\n')
            print('START ' + name, flush=True)
            with log.open('w') as stream:
                run = subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                                     stdout=stream, stderr=subprocess.STDOUT)
            text = log.read_text()
            counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
            if run.returncode or not counts or int(counts[-1][1]) or 'Equivalence successfully proven!' not in text:
                raise SystemExit('Current RAT candidate not proven: ' + str(log))
            results.append(dict(name=name, status='PROVEN', proven_cells=int(counts[-1][0]),
                                unproven_cells=0, log_sha256=sha(log)))
            print('PROVEN ' + name, flush=True)
    for path, expected in hashes.items():
        if sha(path) != expected:
            raise SystemExit('Proof input changed: ' + path)
    report = dict(status='COMPLETE', input_sha256=hashes, results=results,
                  reference_literal_proof=str(reference_report), current_module_matches_literal_proven_candidate=True,
                  proves_cpu_instance_wiring=False, proves_whole_cpu=False, claims_cpu_ppa=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: all current RAT recovery outputs match the literal-proven candidate')


if __name__ == '__main__':
    main()
