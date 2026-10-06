"""Prove both legacy completion modes against an immutable full-module baseline.

Direct mode is a new latency/arbitration architecture, tested separately rather
than falsely described as cycle-equivalent to the buffered completion FIFO.
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
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / 'source_snapshot'
    frozen.mkdir(exist_ok=True)
    inputs = [args.baseline.resolve(), ROOT / 'rtl/backend/rv32_completion_network.v',
              ROOT / 'rtl/rv32im_defs.vh', Path(__file__).resolve()]
    hashes = {str(p): sha(p) for p in inputs}
    for source, name in zip(inputs, ('gold.v', 'gate.v', 'rv32im_defs.vh', 'test_completion_equivalence.py')):
        destination = frozen / name
        if destination.exists() and sha(destination) != sha(source):
            raise SystemExit('Existing proof snapshot differs: ' + str(destination))
        shutil.copyfile(source, destination)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = os.environ.copy()
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for bypass in (0, 1):
        for be in (1, 2, 4):
            for cdb in (1, 2, 4):
                if cdb > be:
                    continue
                name = f'be{be}_cdb{cdb}_bypass{bypass}'
                parameters = dict(BE_WIDTH=be, CDB_WIDTH=cdb, SOURCES=be+2,
                                  FIFO_DEPTH=16 if be == 4 else 8, TAG_WIDTH=16,
                                  PHYS_ADDR_WIDTH=6, BYPASS=bypass)
                settings = ' '.join(f'-set {key} {value}' for key, value in parameters.items())
                script = out / (name + '.ys')
                lines = []
                for kind in ('gold', 'gate'):
                    lines += [f'read_verilog -I{frozen.as_posix()} "{(frozen / (kind + ".v")).as_posix()}"',
                              f'chparam {settings} rv32_completion_network',
                              f'rename rv32_completion_network {kind}']
                lines += ['proc', 'memory_map', 'opt_clean', 'equiv_make gold gate equiv',
                          'hierarchy -top equiv', 'equiv_simple -seq 2',
                          'equiv_induct -seq 4', 'equiv_status -assert']
                script.write_text('\n'.join(lines) + '\n')
                log = out / (name + '.log')
                with log.open('w') as stream:
                    completed = subprocess.run([str(yosys), '-T', '-s', str(script)], cwd=ROOT,
                                               env=env, stdout=stream, stderr=subprocess.STDOUT)
                text = log.read_text()
                matches = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
                if completed.returncode or not matches or int(matches[-1][1]) != 0 or \
                        'Equivalence successfully proven!' not in text:
                    raise SystemExit('Legacy completion equivalence failed: ' + str(log))
                results.append(dict(name=name, status='PROVEN', parameters=parameters,
                                    proven_cells=int(matches[-1][0]), unproven_cells=0,
                                    script_sha256=sha(script), log_sha256=sha(log)))
                print('PROVEN: ' + name, flush=True)
    for name, expected in hashes.items():
        if sha(Path(name)) != expected:
            raise SystemExit('Proof input changed: ' + name)
    report = dict(status='PROVEN', input_sha256=hashes, results=results,
                  coverage='Complete sequential module, modes0/1; BE1/2/4 and every supported CDB1/2/4 combination')
    (out / 'proof_manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'PROVEN: all {len(results)} legacy configurations', flush=True)


if __name__ == '__main__':
    main()
