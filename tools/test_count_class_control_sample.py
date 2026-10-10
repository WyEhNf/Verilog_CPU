"""One finite paired shared-backend RS count and private MDU class sample; not a CPU suite."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    selected = list((ROOT/'rtl').rglob('*.v'))
    selected += [ROOT/'rtl/rv32im_defs.vh', ROOT/'scripts/ram/sram_fakeram.sv',
                 ROOT/'tb/unit/rv32_count_class_control_tb.v', Path(__file__).resolve()]
    source = out / 'source'
    hashes = {}
    for original in selected:
        target = source / original.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        hashes[str(target)] = sha(target)
    from run_tier_candidate import HOST
    verilator = Path(HOST['verilator'])
    hashes[str(verilator)] = sha(verilator)
    env = dict(os.environ)
    env['PATH'] = HOST['runtime_bin'] + os.pathsep + HOST['build_bin'] + os.pathsep + env['PATH']
    env['VERILATOR_ROOT'] = HOST['verilator_root']
    env['MAKE'] = str(Path(HOST['build_bin'])/'make.exe')
    env['SHELL'] = str(Path(HOST['build_bin'])/'sh.exe')
    top = 'rv32_count_class_control_tb'
    started = time.monotonic()
    results = []
    # One bounded paired source-state stimulus, including direct/staged recovery.
    for name in ('limited',):
        obj = out / name
        executable = obj / ('V' + top + '.exe')
        cpp = (Path(HOST['runtime_bin'])/'g++.exe').as_posix()
        ar = (Path(HOST['runtime_bin'])/'ar.exe').as_posix()
        command = [str(verilator), '--binary', '--timing', '--assert', '-Wno-fatal',
                   '-j', '1', '+define+CPU2026_WORD_SIM', '-I' + str(source/'rtl'),
                   '--top-module', top, '--Mdir', str(obj), '-o', str(executable),
                   '-MAKEFLAGS', f'CXX={cpp} LINK={cpp} AR={ar}', '-CFLAGS', '-std=c++17']
        command += [str(source/p.relative_to(ROOT)) for p in selected if p.suffix in ('.v', '.sv')]
        compile_log, log = out/(name+'.compile.log'), out/(name+'.simulation.log')
        with compile_log.open('w', encoding='utf-8') as stream:
            subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        with log.open('w', encoding='utf-8') as stream:
            subprocess.run([str(executable)], env=env, stdout=stream,
                           stderr=subprocess.STDOUT, check=True)
        observed = log.read_text(encoding="utf-8")
        marker = 'PASS: limited paired count class control sample'
        if marker not in observed or any(x in observed for x in ('FATAL', 'ERROR', 'FAIL')):
            raise SystemExit('Sample did not pass: ' + str(log))
        results.append(dict(name=name, status='PASS', compile_log_sha256=sha(compile_log),
                            simulation_log_sha256=sha(log), executable_sha256=sha(executable)))
        print('PASS ' + name, flush=True)
    for name, expected in hashes.items():
        if sha(Path(name)) != expected:
            raise SystemExit('Frozen sample input changed: ' + name)
    report = dict(status='PASS', elapsed_seconds=time.monotonic()-started, results=results,
                  input_sha256=hashes, proves_whole_lsq=False, proves_whole_cpu=False,
                  claims_cpu_ppa=False, simulator='native Verilator two-state, WORD_SIM scheduling',
                  scope='One BE2/ROB8/PHYS40/RS8/LSQ4 finite shared backend pair: original occupancy expression/class decode0 versus exact delta-select/private-qualified-class1 with all earlier PC/arithmetic/comparison/window/MDU-step/address policies fixed1. Direct and staged recovery with original direct and registered issue. Every nonreset normal RS count next compares to the original full arithmetic, every valid/invalid MDU packet class compares to original opcode decoding. Original real LOAD wake/BNE, arithmetic/PC wrap, MUL0, STORE ACKs, full tags/recovery/reset/error and public cycles/valid packets/ROB/allocator identities retained. No all-width or whole CPU proof')
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
