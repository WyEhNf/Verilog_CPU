"""Prove the complete legacy predictor across all supported bank widths.

The new direct conditional target mode changes predictions intentionally; only
DIRECT_BRANCH_TARGET=0 is claimed sequentially equivalent to the frozen module.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    frozen = out / 'source_snapshot'
    frozen.mkdir(parents=True, exist_ok=True)
    inputs = [args.baseline.resolve(), ROOT / 'rtl/predictor/rv32_branch_predictor.v',
              ROOT / 'rtl/rv32im_defs.vh', Path(__file__).resolve()]
    hashes = {str(path): sha(path) for path in inputs}
    for path, name in zip(inputs, ('gold.v', 'gate.v', 'rv32im_defs.vh', Path(__file__).name)):
        destination = frozen / name
        if destination.exists() and sha(destination) != sha(path):
            raise SystemExit('Existing snapshot differs: ' + str(destination))
        shutil.copyfile(path, destination)
        hashes[str(destination)] = sha(destination)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = os.environ.copy()
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for bank_bits in (0, 1, 2):
        name = f'bank{bank_bits}_legacy'
        commands = []
        for kind in ('gold', 'gate'):
            settings = f'-set BANK_BITS {bank_bits}'
            if kind == 'gate':
                settings += ' -set DIRECT_BRANCH_TARGET 0'
            commands += [f'read_verilog -I{frozen.as_posix()} "{(frozen / (kind + ".v")).as_posix()}"',
                         f'chparam {settings} rv32_branch_predictor',
                         f'rename rv32_branch_predictor {kind}']
        commands += ['proc', 'memory_map', 'opt_clean', 'equiv_make gold gate equiv',
                     'hierarchy -top equiv', 'equiv_simple -seq 2', 'equiv_induct -seq 4',
                     'equiv_status -assert']
        script, log = out / (name + '.ys'), out / (name + '.log')
        script.write_text('\n'.join(commands) + '\n')
        with log.open('w') as stream:
            completed = subprocess.run([str(yosys), '-T', '-s', str(script)], cwd=ROOT,
                                       env=env, stdout=stream, stderr=subprocess.STDOUT)
        text = log.read_text()
        counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
        if completed.returncode or not counts or int(counts[-1][1]) or \
                'Equivalence successfully proven!' not in text:
            raise SystemExit('Legacy equivalence failed: ' + str(log))
        results.append(dict(name=name, status='PROVEN', bank_bits=bank_bits,
                            proven_cells=int(counts[-1][0]), unproven_cells=0,
                            script_sha256=sha(script), log_sha256=sha(log)))
        print('PROVEN: ' + name, flush=True)
    for name, expected in hashes.items():
        if sha(Path(name)) != expected:
            raise SystemExit('Proof input changed: ' + name)
    (out / 'proof_manifest.json').write_text(json.dumps(dict(
        status='PROVEN', input_sha256=hashes, results=results,
        coverage='Complete sequential predictor; DIRECT_BRANCH_TARGET=0, BANK_BITS=0/1/2'), indent=2) + '\n')


if __name__ == '__main__':
    main()
