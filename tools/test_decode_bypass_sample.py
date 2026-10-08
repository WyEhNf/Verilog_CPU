"""One small frozen ordered-stream sample for the shared decode queue."""
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
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    selected = list((ROOT/'rtl/common').glob('*.v')) + [ROOT/name for name in (
        'rtl/rv32_decode_bundle_register.v', 'rtl/rv32_decode_field_bank.v',
        'rtl/rv32im_defs.vh', 'tb/unit/rv32_decode_bypass_tb.v')]
    selected.append(Path(__file__).resolve())
    source = out/'source'
    hashes = {}
    for original in selected:
        target = source/original.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        hashes[str(target)] = sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    iv, vv = suite/'bin/iverilog.exe', suite/'bin/vvp.exe'
    hashes[str(iv)], hashes[str(vv)] = sha(iv), sha(vv)
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    command = [str(iv), '-g2012', '-I', str(source/'rtl'), '-s', 'rv32_decode_bypass_tb',
               '-o', str(out/'sample.vvp')]
    command += [str(source/p.relative_to(ROOT)) for p in selected if p.suffix=='.v']
    started = time.monotonic()
    with (out/'compile.log').open('w') as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    with (out/'simulation.log').open('w') as stream:
        subprocess.run([str(vv), '-N', str(out/'sample.vvp')], env=env,
                       stdout=stream, stderr=subprocess.STDOUT, check=True)
    observed = (out/'simulation.log').read_text(encoding='utf-8')
    if ('PASS: limited shared decode queue sample' not in observed or
            any(x in observed for x in ('FATAL', 'FAIL', 'ERROR'))):
        raise SystemExit('Decode queue sample failed')
    for name, expected in hashes.items():
        if sha(Path(name)) != expected:
            raise SystemExit('Frozen sample input changed: ' + name)
    report = dict(status='PASS', elapsed_seconds=time.monotonic()-started, input_sha256=hashes,
                  simulation_log_sha256=sha(out/'simulation.log'), compile_log_sha256=sha(out/'compile.log'),
                  scope='18-cycle public-handshake stream scoreboard for each of 1/2/4 lanes at capacity=lanes',
                  proves_whole_cpu=False, claims_cpu_ppa=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(observed, end='')


if __name__=='__main__':
    main()
