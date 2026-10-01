"""Frozen backend protocol matrix for optional RAT and early-store paths.

The existing joint test covers RAW/WAR/WAW, load/store forwarding, precise
errors, completion collisions and branch recovery/free-list ownership. Its
stimulus enters lane zero at each tested BE width; full multi-lane instruction
streams are additionally required from the native course suites.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh matrix output directory')
    snapshot = out / 'source_snapshot'
    filelist = ROOT / 'rtl/filelist.f'
    sources = [ROOT / x.split('#', 1)[0].strip() for x in filelist.read_text().splitlines()
               if x.split('#', 1)[0].strip()]
    ram = ROOT / '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'
    testbench = ROOT / 'tb/unit/rv32_backend_joint_tb.v'
    inputs = [*sources, filelist, ROOT / 'rtl/rv32im_defs.vh', ram, testbench, Path(__file__).resolve()]
    hashes = {}
    for source in inputs:
        target = snapshot / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(target)] = sha(target)
    frozen = lambda p: snapshot / p.relative_to(ROOT)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    iverilog, vvp = suite / 'bin/iverilog.exe', suite / 'bin/vvp.exe'
    hashes[str(iverilog)], hashes[str(vvp)] = sha(iverilog), sha(vvp)
    configurations = [dict(BE_WIDTH=w, CHECKPOINT_IMPL=1, RAT_RECOVERY_IMPL=r, EARLY_STORE_ADDRESS=e,
                           COMPLETION_BYPASS=c, STORE_BUFFERED_RETIRE=s, PREDICTOR_META=m)
                      for w in (1, 2, 4) for r in (0, 1) for e in (0, 1, 2)
                      for c in (0, 2) for s in (0, 1) for m in (0, 1)]
    configurations += [dict(BE_WIDTH=w, CHECKPOINT_IMPL=0, RAT_RECOVERY_IMPL=1, EARLY_STORE_ADDRESS=e,
                            COMPLETION_BYPASS=0, STORE_BUFFERED_RETIRE=s, PREDICTOR_META=0)
                       for w in (1, 2, 4) for e in (0, 1, 2) for s in (0, 1)]
    results = []
    for config in configurations:
        name = '_'.join(k.lower() + str(v) for k, v in config.items())
        image = out / (name + '.vvp')
        overrides = [value for k, v in config.items() for value in ('-P', f'rv32_backend_joint_tb.{k}={v}')]
        compile_command = [str(iverilog), '-g2012', '-I', str(snapshot / 'rtl'), '-s', 'rv32_backend_joint_tb',
                           *overrides, '-o', str(image), *[str(frozen(p)) for p in [*sources, ram, testbench]]]
        compile_log, sim_log = out / (name + '.compile.log'), out / (name + '.simulation.log')
        with compile_log.open('w') as stream:
            subprocess.run(compile_command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        with sim_log.open('w') as stream:
            subprocess.run([str(vvp), '-N', str(image)], env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        text = sim_log.read_text()
        if not re.search(r'^PASS: B-09 backend joint BE_WIDTH=' + str(config['BE_WIDTH']) + '$', text, re.M) or \
                re.search(r'FAIL|FATAL|ERROR', text):
            raise SystemExit('Backend protocol matrix failed: ' + str(sim_log))
        results.append(dict(name=name, status='PASS', parameters=config, compile_log_sha256=sha(compile_log),
                            simulation_log_sha256=sha(sim_log)))
        print('PASS ' + name, flush=True)
    if len(results) != 162:
        raise SystemExit('Incomplete backend matrix')
    for path, expected in hashes.items():
        if sha(path) != expected:
            raise SystemExit('Frozen matrix input changed: ' + path)
    report = dict(status='COMPLETE', total_cases=len(results), source_sha256=hashes, results=results,
                  stimulus_scope='lane-zero stimulus at BE widths 1/2/4; independent native suites test multi-lane streams',
                  proves_whole_cpu=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: all 162 backend recovery/store-address protocol configurations')


if __name__ == '__main__':
    main()
