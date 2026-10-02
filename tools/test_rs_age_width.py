"""Exercise existing RS age-width parameter with independent selection and natural wraps.

Sequential tests include original generation/wakeup/flush assertions and real
allocation-driven counter wraps. Combinational tests compare arbitrary state
to the original independent serial selector. Not a whole-CPU correctness proof.
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
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-root', type=Path, required=True)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    source, out = a.candidate_root.resolve(), a.outdir.resolve()
    assert not out.exists()
    snapshot = out/'source_snapshot'
    cm_path = source/'candidate_manifest.json'
    cm = json.loads(cm_path.read_text())
    inputs = {str(cm_path):sha(cm_path), str(Path(__file__).resolve()):sha(__file__)}
    for name, expected in cm['files_sha256'].items():
        assert sha(source/name) == expected
        inputs[str(source/name)] = expected
    for path in (source/'rtl/backend/rv32_reservation_station.v',
                 source/'tb/unit/rv32_reservation_station_tb.v', source/'tb/unit/rv32_rs_rank_tb.v',
                 ROOT/'rtl/rv32im_defs.vh'):
        relative = path.relative_to(source) if path.is_relative_to(source) else Path('rtl/rv32im_defs.vh')
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        inputs[str(path)] = sha(path)
        inputs[str(target)] = sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    iv, vv = suite/'bin/iverilog.exe', suite/'bin/vvp.exe'
    inputs[str(iv)], inputs[str(vv)] = sha(iv), sha(vv)
    report = dict(status='RUNNING', input_sha256=inputs, results=[],
                  proves_whole_cpu=False, is_formal_proof=False,
                  compares_against_age32_execution=False, unchanged_rtl=True)

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    for age in (3,8,16,32):
        for phase, configs in [('sequential', [(1,4,1),(2,8,2),(4,12,4)]),
                               ('rank', [(1,4,1),(2,8,4),(4,12,10),(4,16,10)])]:
            for width, entries, wake in configs:
                module = 'rv32_reservation_station_tb' if phase == 'sequential' else 'rv32_rs_rank_tb'
                config = dict(BE_WIDTH=width, ENTRIES=entries, AGE_WIDTH=age)
                if phase == 'rank':
                    config['WAKE_WIDTH'] = wake
                stem = f'{phase}_be{width}_e{entries}_w{wake}_a{age}'
                report['active_case'] = stem
                save()
                command = [str(iv), '-g2012', '-I', str(snapshot/'rtl'), '-s', module]
                for key, value in config.items():
                    command += ['-P', f'{module}.{key}={value}']
                image = out/(stem+'.vvp')
                command += ['-o', str(image), str(snapshot/'rtl/backend/rv32_reservation_station.v'),
                            str(snapshot/'tb/unit'/(module+'.v'))]
                logs = []
                for command, suffix in [(command, '.compile.log'), ([str(vv), '-N', str(image)], '.simulation.log')]:
                    log = out/(stem+suffix)
                    logs.append(log)
                    with log.open('w') as stream:
                        result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
                    if result.returncode:
                        report.update(status='FAILED', failure_log=str(log));save()
                        raise SystemExit('Age-width validation failed: '+str(log))
                text = logs[1].read_text()
                assert not re.search('FATAL|ERROR|FAIL', text), text
                if phase == 'rank':
                    assert 'PASS: RS rank differential' in text and 'trials=3000' in text
                    coverage = dict(independent_selection_trials=3000)
                else:
                    assert 'PASS: B-04 RS' in text
                    matched = re.search(r'PASS age-width sequential AGE_WIDTH=(\d+) wraps=(\d+)', text)
                    assert matched and int(matched[1]) == age
                    assert age > 8 or int(matched[2]) >= 2
                    coverage = dict(natural_counter_wraps=int(matched[2]))
                report['results'].append(dict(status='PASS', phase=phase, parameters=config,
                    **coverage, compile_log_sha256=sha(logs[0]), simulation_log_sha256=sha(logs[1])))
                save()
                print('PASS '+stem, flush=True)
    for name, expected in inputs.items():
        assert sha(name) == expected, name
    report.update(status='COMPLETE', active_case=None)
    save()
    print('COMPLETE 28 RS age-width configurations; natural wraps and48000 independent selector trials', flush=True)


if __name__ == '__main__':
    main()
