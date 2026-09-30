"""Prove the complete ROB against a frozen RTL, not only its read mux.

All module outputs and same-named state are compared with sequential Yosys
equivalence. Both checkpoint and store retirement implementations are covered.
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
    source = ROOT / 'rtl/backend/rv32_rob.v'
    header = ROOT / 'rtl/rv32im_defs.vh'
    inputs = {str(p): digest(p) for p in (baseline, source, header, Path(__file__))}
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    env = os.environ.copy()
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for checkpoint in (1, 0):
        for buffered in (1, 0):
            for width in (1, 2, 4):
                for depth in (2, 4, 8, 16, 32):
                    # Also cover BE4/ROB2, which keeps original single-wrap
                    # indexing in a dedicated fallback rather than changing
                    # the accepted parameter range during this refactoring.
                    stem = f'be{width}_rob{depth}_cp{checkpoint}_sb{buffered}'
                    script, log = out / (stem + '.ys'), out / (stem + '.log')
                    params = (f'-set BE_WIDTH {width} -set ROB_ENTRIES {depth} '
                              '-set PHYS_REGS 48 -set PHYS_ADDR_WIDTH 6 '
                              '-set GENERATION_WIDTH 8 -set CHECKPOINT_WIDTH 192 '
                              f'-set CHECKPOINT_IMPL {checkpoint} -set STORE_BUFFERED_RETIRE {buffered}')
                    commands = [
                        f'read_verilog -Irtl {quote(baseline)}',
                        f'chparam {params} rv32_rob', 'rename rv32_rob gold',
                        f'read_verilog -Irtl {quote(source)}',
                        f'chparam {params} rv32_rob', 'rename rv32_rob gate',
                        'proc', 'memory_map', 'opt_clean',
                        'equiv_make gold gate equiv', 'hierarchy -top equiv',
                        'equiv_simple -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert',
                    ]
                    script.write_text('\n'.join(commands) + '\n')
                    with log.open('w') as stream:
                        completed = subprocess.run([str(yosys), '-T', '-s', str(script)],
                                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
                    if completed.returncode or not re.search(r'Equivalence successfully proven!', log.read_text()):
                        raise SystemExit(f'{stem}: equivalence NOT proven; inspect {log}')
                    results.append(dict(width=width, depth=depth, checkpoint_impl=checkpoint,
                                        store_buffered_retire=buffered, status='PROVEN', log=str(log),
                                        script_sha256=digest(script), log_sha256=digest(log)))
                    print('PROVEN: ' + stem, flush=True)
    for name, expected in inputs.items():
        if digest(Path(name)) != expected:
            raise SystemExit('Input changed during ROB equivalence: ' + name)
    report = dict(status='COMPLETE', method='Full sequential Yosys equivalence, all ROB module outputs',
                  yosys_version=subprocess.check_output([str(yosys), '-V'], env=env, text=True).strip(),
                  source_sha256=inputs, physical_registers=48, physical_address_width=6,
                  checkpoint_width=192, generation_width=8, results=results)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'COMPLETE: {len(results)} ROB parameter combinations proven')


if __name__ == '__main__':
    main()
