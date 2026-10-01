"""Prove full sequential ROB identity with physical fanout buffering enabled.

Use the original Liberty's real buffer functions, not synthesis blackboxes or
assumed uninterpreted identities. The complete ROB output/state interface is
checked; all proof inputs are frozen before lengthy solving.
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


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--register-banks', action='store_true',
                        help='Prove pure RTL control-bank 0/1 rather than physical buffers')
    args = parser.parse_args()
    out = args.outdir.resolve()
    frozen = out / 'source_snapshot'
    frozen.mkdir(parents=True, exist_ok=True)
    original_lib = ROOT / '.deps/course_asap7_r28/lib/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib'
    sources = [ROOT / 'rtl/backend/rv32_rob.v', ROOT / 'rtl/rv32im_defs.vh',
               ROOT / 'rtl/common/rv32_asap7_fanout.v',
               ROOT / 'rtl/common/rv32_control_register_bank.v', original_lib, Path(__file__)]
    hashes = {}
    for source in sources:
        destination = frozen / source.name
        if destination.exists() and sha(destination) != sha(source):
            raise SystemExit('Existing proof snapshot differs: ' + str(destination))
        shutil.copyfile(source, destination)
        hashes[str(destination)] = sha(destination)
    # Explicitly verify that the functional cells consumed by flattening are
    # the genuine A->Y, non-inverting buffer definitions from this raw library.
    libtext = (frozen / original_lib.name).read_text()
    for name in ('BUFx16f_ASAP7_75t_R', 'BUFx2_ASAP7_75t_R'):
        section = re.search(r'\bcell\s*\(\s*' + re.escape(name) + r'\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)', libtext, re.S)
        if not section or not re.search(r'\bfunction\s*:\s*"A"', section[1]):
            raise SystemExit('Required original Liberty buffer function is absent')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for width, depth in ((4, 32), (1, 8), (2, 8), (4, 8), (1, 32), (2, 32)):
        option = 'register01' if args.register_banks else 'buf01'
        name = f'be{width}_rob{depth}_{option}'
        commands = [
            'read_verilog -sv -D SYNTHESIS ' + quote(frozen / 'rv32_asap7_fanout.v'),
            'read_verilog -sv -D SYNTHESIS ' + quote(frozen / 'rv32_control_register_bank.v'),
            'read_liberty -wb -ignore_miss_func ' + quote(frozen / original_lib.name),
        ]
        for kind, enabled in (('gold', 0), ('gate', 1)):
            commands.extend([
                'read_verilog -I' + frozen.as_posix() + ' ' + quote(frozen / 'rv32_rob.v'),
                f'chparam -set BE_WIDTH {width} -set ROB_ENTRIES {depth} -set PHYS_REGS 48 '
                '-set PHYS_ADDR_WIDTH 6 -set GENERATION_WIDTH 8 -set CHECKPOINT_WIDTH 192 '
                f'-set CHECKPOINT_IMPL 1 -set STORE_BUFFERED_RETIRE 1 '
                f'-set ASAP7_FANOUT_BUFFERS {0 if args.register_banks else enabled} '
                f'-set ROB_CONTROL_REGISTER_BANKS {enabled if args.register_banks else 0} rv32_rob',
                'rename rv32_rob ' + kind,
            ])
        commands.extend([
            'hierarchy -check', 'proc', 'memory_map', 'flatten -wb gold gate',
            'opt_expr gold gate', 'opt_clean gold gate',
            'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
            'select -assert-none t:BUFx16f_ASAP7_75t_R t:BUFx2_ASAP7_75t_R',
            'equiv_simple -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert',
        ])
        script, log = out / (name + '.ys'), out / (name + '.log')
        script.write_text('\n'.join(commands) + '\n')
        print('START ' + name, flush=True)
        with log.open('w') as stream:
            run = subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                                 stdout=stream, stderr=subprocess.STDOUT)
        text = log.read_text()
        counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
        if run.returncode or not counts or int(counts[-1][1]) or 'Equivalence successfully proven!' not in text:
            raise SystemExit('Full buffered ROB equivalence NOT proven: ' + str(log))
        results.append(dict(name=name, status='PROVEN', width=width, depth=depth,
                            proven_cells=int(counts[-1][0]), unproven_cells=0,
                            script_sha256=sha(script), log_sha256=sha(log)))
        print('PROVEN ' + name, flush=True)
    for path, expected in hashes.items():
        if sha(Path(path)) != expected:
            raise SystemExit('Frozen proof input changed: ' + path)
    method = ('Full sequential ROB equivalence of pure RTL control-register banks'
              if args.register_banks else 'Full sequential ROB equivalence using genuine raw Liberty buffer functions')
    report = dict(status='COMPLETE', method=method, register_banks=args.register_banks,
                  source_sha256=hashes, results=results,
                  yosys_version=subprocess.check_output([str(yosys), '-V'], env=env, text=True).strip())
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: six full ROB option configurations proven')


if __name__ == '__main__':
    main()
