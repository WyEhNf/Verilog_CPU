"""Prove direct RAT reads and older-lane forwarding against the original rename module."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from run_course_sram_area import ROOT, digest, quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh rename proof directory')
    snapshot = out / 'source_snapshot'
    snapshot.mkdir(parents=True)
    name = Path('rtl/rv32_rename_unit.v')
    sources = {snapshot/'original.v': ROOT/name,
               snapshot/'candidate.v': args.candidate_root.resolve()/name,
               snapshot/'rtl/rv32im_defs.vh': ROOT/'rtl/rv32im_defs.vh',
               snapshot/'test_rename_read_bypass.py': Path(__file__)}
    hashes = {}
    for target, source in sources.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(target)] = digest(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    cases = [(1,33), (2,48), (4,64), (4,96)]
    report = dict(status='RUNNING', proves_whole_cpu=False, no_input_assumptions=True,
                  input_sha256=hashes, results=[])
    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    for width, physical in cases:
        config = dict(BE_WIDTH=width, PHYS_REGS=physical)
        stem = f'be{width}_physical{physical}'
        report['active_case'] = stem
        save()
        args_text = ' '.join(f'-set {k} {v}' for k,v in config.items())
        commands = [
            'read_verilog -I rtl '+quote(snapshot/'original.v'),
            'chparam '+args_text+' rv32_rename_unit',
            'rename rv32_rename_unit gold',
            'read_verilog -I rtl '+quote(snapshot/'candidate.v'),
            'chparam '+args_text+' -set RAT_READ_BYPASS 1 rv32_rename_unit',
            'rename rv32_rename_unit gate',
            'proc', 'memory_map', 'opt_clean -purge',
            'write_json '+quote(out/(stem+'.prepared.json')),
            'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
            'equiv_simple -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert']
        script, log = out/(stem+'.ys'), out/(stem+'.log')
        script.write_text('\n'.join(commands)+'\n')
        print('START '+stem, flush=True)
        with log.open('w') as stream:
            result = subprocess.run([str(suite/'bin/yosys.exe'), '-T', '-s', str(script)],
                                    cwd=snapshot, env=env, stdout=stream, stderr=subprocess.STDOUT)
        text = log.read_text()
        if result.returncode or 'Equivalence successfully proven!' not in text:
            report.update(status='FAILED', failure_log=str(log))
            save()
            raise SystemExit('Actual rename equivalence not proven: '+str(log))
        model = json.loads((out/(stem+'.prepared.json')).read_text())['modules']
        schema = lambda m: {n:(v['direction'], len(v['bits'])) for n,v in m['ports'].items()}
        assert schema(model['gold']) == schema(model['gate'])
        count = re.search(r'Found (\d+) \$equiv cells in equiv:', text)
        assert count
        report['results'].append(dict(status='PROVEN', parameters=config,
                                      equiv_cells=int(count[1]), log_sha256=digest(log)))
        save()
        print('PROVEN '+stem, flush=True)
    for path, expected in hashes.items():
        assert digest(Path(path)) == expected
    report.update(status='COMPLETE', active_case=None)
    save()
    print('COMPLETE actual rename module proof, including 4-wide/64-physical configuration', flush=True)


if __name__ == '__main__':
    main()
