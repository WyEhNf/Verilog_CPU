"""Prove the actual twelve-entry RS static allocation against the complete frozen baseline.

No assumptions on duplicate tags, values, allocation masks or flush inputs.
Keep both first-lane bypass and last-lane sequential wake priority observable.
"""
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
        raise SystemExit('Choose a fresh RS proof directory')
    snapshot = out / 'source_snapshot'
    snapshot.mkdir(parents=True)
    name = Path('rtl/backend/rv32_reservation_station.v')
    sources = {snapshot/'original.v': ROOT/name,
               snapshot/'candidate.v': args.candidate_root.resolve()/name,
               snapshot/'rtl/rv32im_defs.vh': ROOT/'rtl/rv32im_defs.vh',
               snapshot/'test_rs_static12.py': Path(__file__)}
    hashes = {}
    for target, source in sources.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(target)] = digest(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    cases = [(4,12,10,70)]
    report = dict(status='RUNNING', proves_whole_cpu=False, no_input_assumptions=True,
                  input_sha256=hashes, results=[])
    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    for width, entries, wake, metadata in cases:
        config = dict(BE_WIDTH=width, ENTRIES=entries, TAG_WIDTH=17, PHYS_ADDR_WIDTH=6,
                      WAKE_WIDTH=wake, METADATA_WIDTH=metadata, AGE_WIDTH=32)
        stem = f'be{width}_entries{entries}_wake{wake}_metadata{metadata}'
        report['active_case'] = stem
        save()
        args_text = ' '.join(f'-set {k} {v}' for k,v in config.items())
        commands = [
            'read_verilog -I rtl '+quote(snapshot/'original.v'),
            'chparam '+args_text+' -set WAKE_MUX_IMPL 1 rv32_reservation_station',
            'rename rv32_reservation_station gold',
            'read_verilog -I rtl '+quote(snapshot/'candidate.v'),
            'chparam '+args_text+' -set WAKE_MUX_IMPL 1 -set ALLOC_STATIC_WRITE 1 rv32_reservation_station',
            'rename rv32_reservation_station gate',
            'proc', 'memory_map', 'opt_expr -keepdc', 'opt_clean -purge',
            'write_json '+quote(out/(stem+'.prepared.json')),
            'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
            'equiv_simple -short -seq 2', 'equiv_simple -short -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert']
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
            raise SystemExit('Actual RS equivalence not proven: '+str(log))
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
    print('COMPLETE actual 4-wide/12-entry/10-wake RS static allocation proof', flush=True)


if __name__ == '__main__':
    main()
