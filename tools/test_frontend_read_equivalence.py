"""Prove frontend queue-read refactoring against a frozen previous RTL.

Yosys checks the complete sequential module, including queue payloads, pointers,
metadata, valid/ready, redirect, stop, error and performance event outputs.
No testbench memory or timing boundary is substituted for the real frontend.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    source = ROOT / 'rtl/frontend/rv32_fetch_frontend.v'
    header = ROOT / 'rtl/rv32im_defs.vh'
    inputs = {str(p): digest(p) for p in (baseline, source, header, Path(__file__))}
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    env = os.environ.copy()
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for width in (1, 2, 4):
        for depth in (2, 4, 8, 16, 32):
            if depth < width:
                continue
            stem = f'fe{width}_fq{depth}'
            script, log = out / (stem + '.ys'), out / (stem + '.log')
            commands = [
                f'read_verilog -Irtl {quote(baseline)}',
                f'chparam -set FE_WIDTH {width} -set FQ_DEPTH {depth} rv32_fetch_frontend',
                'rename rv32_fetch_frontend gold',
                f'read_verilog -Irtl {quote(source)}',
                f'chparam -set FE_WIDTH {width} -set FQ_DEPTH {depth} rv32_fetch_frontend',
                'rename rv32_fetch_frontend gate',
                'proc', 'memory_map', 'opt_clean',
                'equiv_make gold gate equiv', 'hierarchy -top equiv',
                'equiv_simple -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert',
            ]
            script.write_text('\n'.join(commands) + '\n')
            with log.open('w') as stream:
                completed = subprocess.run([str(yosys), '-T', '-s', str(script)],
                                           cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            text = log.read_text()
            proved = re.search(r'Equivalence successfully proven!', text)
            if completed.returncode or not proved:
                raise SystemExit(f'{stem}: equivalence NOT proven; inspect {log}')
            results.append(dict(width=width, depth=depth, status='PROVEN', log=str(log),
                                script_sha256=digest(script), log_sha256=digest(log)))
            print(f'PROVEN: FE_WIDTH={width} FQ_DEPTH={depth}', flush=True)
    for name, expected in inputs.items():
        if digest(Path(name)) != expected:
            raise SystemExit('Input changed during equivalence: ' + name)
    report = dict(status='COMPLETE', method='Full sequential Yosys equivalence, all module outputs',
                  yosys_version=subprocess.check_output([str(yosys), '-V'], env=env, text=True).strip(),
                  source_sha256=inputs, results=results)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'COMPLETE: {len(results)} frontend parameter combinations proven')


if __name__ == '__main__':
    main()
