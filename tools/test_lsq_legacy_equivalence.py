"""Prove disabled store-admission/address probes preserve the sequential LSQ.

The enabled option intentionally changes request latency and is covered by
protocol/architecture regressions, not a false cycle-equivalence claim.
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
    inputs = [args.baseline.resolve(), ROOT / 'rtl/backend/rv32_lsq.v',
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
    gate_has_probe = 'STORE_ADDRESS_PROBE' in inputs[1].read_text()
    gold_has_probe = 'STORE_ADDRESS_PROBE' in inputs[0].read_text()
    for be in (1, 2, 4):
        name = f'be{be}_lsq8_rob32_legacy'
        parameters = dict(BE_WIDTH=be, LSQ_ENTRIES=8, ROB_ENTRIES=32,
                          TAG_WIDTH=14, ROB_TAG_WIDTH=14)
        commands = []
        for kind in ('gold', 'gate'):
            settings = ' '.join(f'-set {key} {value}' for key, value in parameters.items())
            if kind == 'gate':
                settings += ' -set STORE_ADMISSION_BYPASS 0'
                if gate_has_probe:
                    settings += ' -set STORE_ADDRESS_PROBE 0'
            commands += [f'read_verilog -I{frozen.as_posix()} "{(frozen / (kind + ".v")).as_posix()}"',
                         f'chparam {settings} rv32_lsq', f'rename rv32_lsq {kind}']
        commands += ['proc', 'memory_map', 'opt_clean']
        if gate_has_probe and not gold_has_probe:
            # The literal old interface predates these read-only views.
            # Probe enable is a constant zero, so its input cannot affect any
            # state. Compare every original port and state, not the new views.
            commands += ['delete -port gate/w:early_addr_valid_i gate/w:early_addr_tag_i '
                         'gate/w:early_addr_i gate/w:store_addr_pending_o '
                         'gate/w:store_addr_rob_tag_o gate/w:store_addr_lsq_tag_o', 'opt_clean']
        commands += ['equiv_make gold gate equiv',
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
        results.append(dict(name=name, status='PROVEN', parameters=parameters,
                            proven_cells=int(counts[-1][0]), unproven_cells=0,
                            script_sha256=sha(script), log_sha256=sha(log)))
        print('PROVEN: ' + name, flush=True)
    for name, expected in hashes.items():
        if sha(Path(name)) != expected:
            raise SystemExit('Proof input changed: ' + name)
    (out / 'proof_manifest.json').write_text(json.dumps(dict(
        status='PROVEN', input_sha256=hashes, results=results,
        coverage='All original ports/state of sequential LSQ; STORE_ADMISSION_BYPASS=0, '
                 'STORE_ADDRESS_PROBE=0, BE1/2/4, LSQ8/ROB32/G8; only added probe/view ports excluded',
        enabled_probe_cycle_equivalence_claimed=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
