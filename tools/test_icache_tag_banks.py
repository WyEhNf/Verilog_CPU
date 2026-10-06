"""Verify actual I-cache tag banks with original four-state SRAM protocols.

Full-module formal comparisons retain all ports, original tag aliases and
actual memory state; no input assumptions or invalid-output masking.
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


def quote(path):
    return '"'+Path(path).resolve().as_posix()+'"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    assert not out.exists()
    snapshot = out/'source_snapshot'
    snapshot.mkdir(parents=True)
    origins = {snapshot/'original.v': candidate/'baseline/rv32_icache_nonblocking.v',
               snapshot/'candidate.v': candidate/'rtl/cache/rv32_icache_nonblocking.v',
               snapshot/'tb.v': candidate/'tb/unit/rv32_icache_sram_tb.v',
               snapshot/'rtl/rv32im_defs.vh': ROOT/'rtl/rv32im_defs.vh',
               snapshot/'sram.sv': ROOT/'.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv',
               snapshot/'test_icache_tag_banks.py': Path(__file__)}
    hashes = {}
    for target, source in origins.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(source)] = sha(source)
        hashes[str(target)] = sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    bins = {n: suite/'bin'/(n+'.exe') for n in ['iverilog', 'vvp', 'yosys']}
    for path in bins.values():
        hashes[str(path)] = sha(path)
    report = dict(status='RUNNING', input_sha256=hashes, results=[],
                  no_input_assumptions=True, all_sram_state_included=True,
                  proves_whole_cpu=False, no_outputs_or_state_fields_omitted=True)

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    def verify():
        for path, value in hashes.items():
            assert sha(path) == value, 'Changed proof input: '+path

    def run(command, path):
        verify()
        with path.open('w') as stream:
            completed = subprocess.run(command, cwd=snapshot, env=env,
                                       stdout=stream, stderr=subprocess.STDOUT)
        verify()
        if completed.returncode:
            report.update(status='FAILED', failure_log=str(path))
            save()
            raise SystemExit('I-cache validation failed: '+str(path))

    for lines in (16, 64, 128, 256):
        for ways in (1, 2):
            for mshrs in (2, 4, 8, 16):
                stem = f'protocol_l{lines}_w{ways}_m{mshrs}'
                image, log = out/(stem+'.vvp'), out/(stem+'.simulation.log')
                run([str(bins['iverilog']), '-g2012', '-I', 'rtl', '-s', 'rv32_icache_sram_tb',
                     '-P', f'rv32_icache_sram_tb.LINES={lines}', '-P', f'rv32_icache_sram_tb.WAYS={ways}',
                     '-P', f'rv32_icache_sram_tb.MSHRS={mshrs}', '-o', str(image),
                     str(snapshot/'candidate.v'), str(snapshot/'sram.sv'), str(snapshot/'tb.v')],
                    out/(stem+'.compile.log'))
                run([str(bins['vvp']), '-N', str(image)], log)
                text = log.read_text()
                assert 'PASS: icache SRAM' in text and not re.search('FAIL|FATAL|ERROR', text)
                report['results'].append(dict(status='PASS', phase='protocol', lines=lines,
                                              ways=ways, mshrs=mshrs, log_sha256=sha(log)))
                save()
                print('PASS '+stem, flush=True)
    for lines, ways, mshrs, epoch in [(16, 1, 2, 2), (16, 2, 4, 2),
                                      (64, 2, 4, 4), (128, 2, 8, 4)]:
        stem = f'formal_l{lines}_w{ways}_m{mshrs}_e{epoch}'
        config = dict(CACHE_LINES=lines, CACHE_WAYS=ways, MSHR_ENTRIES=mshrs,
                      EPOCH_WIDTH=epoch, PREFETCH_DISTANCE=3, NEXT_LINE_PREFETCH=1)
        params = ' '.join(f'-set {key} {value}' for key, value in config.items())
        commands = []
        for label, filename in [('gold', 'original.v'), ('gate', 'candidate.v')]:
            commands += ['read_verilog -sv -I rtl '+quote(snapshot/filename)+' '+quote(snapshot/'sram.sv'),
                         'chparam '+params+(' -set TAG_REGISTER_BANKS 1' if label == 'gate' else '')+' rv32_icache_nonblocking',
                         'hierarchy -check -top rv32_icache_nonblocking', 'rename -top '+label,
                         'proc', 'memory_map', 'setattr -mod -unset keep_hierarchy', 'flatten '+label,
                         'opt_expr -keepdc', 'opt_clean', 'setattr -mod -unset top',
                         'design -stash '+label, 'design -reset']
        prepared = out/(stem+'.prepared.json')
        commands += ['design -copy-from gold -as gold gold', 'design -copy-from gate -as gate gate',
                     'write_json '+quote(prepared), 'equiv_make gold gate equiv',
                     'hierarchy -check -top equiv', 'check -assert',
                     'equiv_simple -short -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert']
        script, log = out/(stem+'.ys'), out/(stem+'.log')
        script.write_text('\n'.join(commands)+'\n')
        report['active_case'] = stem
        save()
        print('START '+stem, flush=True)
        run([str(bins['yosys']), '-T', '-s', str(script)], log)
        text = log.read_text()
        assert 'Equivalence successfully proven!' in text and 'ERROR:' not in text
        models = json.loads(prepared.read_text())['modules']
        schema = lambda m: {n: (v['direction'], len(v['bits'])) for n, v in m['ports'].items()}
        assert schema(models['gold']) == schema(models['gate'])
        state_names = [n for n in models['gold']['netnames'] if re.fullmatch(r'tag_mem\[\d+\]', n)]
        assert len(state_names) == lines
        memory_names = [n for n in models['gold']['netnames'] if n.startswith('data_array.') and '[' in n]
        assert memory_names, 'Original data SRAM state must be retained'
        for name in state_names + memory_names:
            assert name in models['gate']['netnames'], name
            assert len(models['gold']['netnames'][name]['bits']) == len(models['gate']['netnames'][name]['bits'])
        count = int(re.search(r'Found (\d+) \$equiv cells in equiv:', text)[1])
        report['results'].append(dict(status='PROVEN', phase='formal', parameters=config,
                                      equiv_cells=count, tag_rows_preserved=len(state_names),
                                      sram_aliases_preserved=len(memory_names),
                                      prepared_sha256=sha(prepared), script_sha256=sha(script), log_sha256=sha(log)))
        save()
        print('PROVEN '+stem, flush=True)
    verify()
    report.update(status='COMPLETE', active_case=None)
    save()
    print('COMPLETE32 original SRAM protocol configurations and four full I-cache proofs', flush=True)


if __name__ == '__main__':
    main()
