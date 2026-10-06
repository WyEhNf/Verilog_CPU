"""Frozen AXI response-credit FIFO and complete bridge protocol matrix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Use a fresh protocol output directory')
    snapshot = out / 'source_snapshot'
    sources = [ROOT / 'rtl/course/rv32_axi_lite_bridge.v',
               ROOT / 'tb/unit/rv32_axi_lite_bridge_tb.v',
               ROOT / 'tb/unit/rv32_axi_response_fifo_tb.v', Path(__file__).resolve()]
    hashes = {}
    for source in sources:
        destination = snapshot / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        hashes[str(destination)] = sha(destination)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    compiler, simulator = suite / 'bin/iverilog.exe', suite / 'bin/vvp.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    hashes.update({str(compiler): sha(compiler), str(simulator): sha(simulator)})
    results = []

    def run(top, name, overrides):
        image = out / (name + '.vvp')
        compile_log, simulation_log = out / (name + '.compile.log'), out / (name + '.simulation.log')
        command = [str(compiler), '-g2012', '-s', top, '-o', str(image)]
        for key, value in overrides.items():
            command += ['-P', f'{top}.{key}={value}']
        command += [str(snapshot / 'rtl/course/rv32_axi_lite_bridge.v'),
                    str(snapshot / ('tb/unit/' + top + '.v'))]
        with compile_log.open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, check=True)
        with simulation_log.open('w') as log:
            result = subprocess.run([str(simulator), '-N', str(image)],
                                    stdout=log, stderr=subprocess.STDOUT, env=env)
        text = simulation_log.read_text()
        if result.returncode or 'PASS:' not in text or any(v in text for v in ('FATAL:', 'FAIL:', 'ERROR:')):
            raise SystemExit('Protocol test failed: ' + str(simulation_log))
        results.append(dict(name=name, status='PASS', overrides=overrides,
                            compile_log_sha256=sha(compile_log), simulation_log_sha256=sha(simulation_log)))
        print('PASS ' + name, flush=True)

    for depth in (2, 4, 8):
        for seed in (17, 97):
            run('rv32_axi_response_fifo_tb', f'fifo_d{depth}_s{seed}', dict(DEPTH=depth, SEED=seed))
    for depth in (0, 2, 4):
        for reads, writes, words in ((2, 2, 4), (8, 4, 16), (16, 8, 4)):
            run('rv32_axi_lite_bridge_tb', f'bridge_d{depth}_r{reads}_w{writes}_q{words}',
                dict(RESPONSE_FIFO_DEPTH=depth, READ_LINES=reads, WRITE_LINES=writes, WORD_QUEUE=words))
    for path, digest in hashes.items():
        if sha(Path(path)) != digest:
            raise SystemExit('Frozen protocol input changed: ' + path)
    report = dict(status='COMPLETE', total_cases=len(results), source_sha256=hashes, results=results,
                  method='169-bit response FIFO scoreboard and full single-bus AXI bridge protocol matrix',
                  changes_external_memory_model=False, proves_whole_cpu=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: all 15 response FIFO/AXI protocol configurations pass')


if __name__ == '__main__':
    main()
