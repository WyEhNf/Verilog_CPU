"""Freeze and test bank-local live Cache metadata queries and original protocols.

An independent candidate root may override the Cache and testbenches. Preserve
the official four-state SRAM model, existing data/dirty/refill/flush checks,
and independently check every active query's indices and live valid/dirty/LRU
views from the captured address, including undefined dirty bits after reset.
This is protocol evidence, not whole-CPU equivalence or a CPU PPA claim.
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
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--local-action', type=int, choices=(0, 1),
                        help='Explicitly test a candidate with LOCAL_ACTION_DECODE')
    parser.add_argument('--group-rows', type=int, choices=(16,32,64,128), default=64)
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh local-metadata protocol directory')
    relative = [Path(name) for name in (
        'rtl/cache/rv32_dcache_nonblocking.v', 'rtl/cache/rv32_dcache_control_banks.v',
        'rtl/rv32im_defs.vh', '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv',
        'tb/models/rv32im_memory_model.v', 'tb/unit/rv32_dcache_sram_tb.v',
        'tb/unit/rv32_dcache_hash_tb.v', 'tools/observe_course_perf.py',
        'tools/test_dcache_local_metadata.py')]
    snapshot, inputs, origins = out/'source_snapshot', {}, {}
    for name in relative:
        original = candidate/name if (candidate/name).is_file() else ROOT/name
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        inputs[str(target)] = sha(target)
        origins[name.as_posix()] = dict(path=str(original), sha256=sha(original))
        if sha(target) != sha(original):
            raise SystemExit('Candidate snapshot changed during copy')
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    iv, vv = [suite/'bin'/name for name in ('iverilog.exe', 'vvp.exe')]
    inputs[str(iv)], inputs[str(vv)] = sha(iv), sha(vv)
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    cases = []
    for registered in (0, 1):
        for mode in (0, 1, 2):
            for tag in (0, 1):
                for ways in (1, 2):
                    for delay in (0, 16, 32):
                        cases.append(('rv32_dcache_sram_tb', dict(REGISTERED_INDEX=registered,
                            STATIC_UPDATES=mode, TAG_SRAM=tag, CACHE_WAYS=ways, MERGE_DELAY=delay)))
                    for lines in (16, 64, 1024):
                        for hashing in (0, 1):
                            for prefetch in (0, 1):
                                cases.append(('rv32_dcache_hash_tb', dict(REGISTERED_INDEX=registered,
                                    STATIC_UPDATES=mode, TAG_SRAM=tag, CACHE_WAYS=ways,
                                    CACHE_LINES=lines, INDEX_HASH=hashing, PREFETCH=prefetch)))
    cases = [(top, config | dict(LOCAL_METADATA_QUERY=local))
             for local in (0, 1) for top, config in cases]
    if args.smoke:
        cases = []
        for registered in (0, 1):
            for mode in (0, 1, 2):
                common = dict(REGISTERED_INDEX=registered, STATIC_UPDATES=mode,
                              TAG_SRAM=1, CACHE_WAYS=2)
                cases.append(('rv32_dcache_sram_tb', common | dict(MERGE_DELAY=16)))
                cases.append(('rv32_dcache_hash_tb', common | dict(CACHE_LINES=1024,
                                                                  INDEX_HASH=1, PREFETCH=1)))
        cases = [(top, config | dict(LOCAL_METADATA_QUERY=local))
                 for local in (0, 1) for top, config in cases]
    results = []
    for top, config in cases:
        config = config | dict(METADATA_GROUP_ROWS=args.group_rows)
        if args.local_action is not None:
            config = config | dict(LOCAL_ACTION_DECODE=args.local_action)
        name = top.removeprefix('rv32_dcache_').removesuffix('_tb')+'_'+ \
            '_'.join(key.lower()+str(value) for key, value in config.items())
        source_names = relative[:2]+relative[3:4]+[Path('tb/unit/'+top+'.v')]
        if top.endswith('hash_tb'):
            source_names.append(Path('tb/models/rv32im_memory_model.v'))
        executable = out/(name+'.vvp')
        command = [str(iv), '-g2012', '-I', str(snapshot/'rtl'), '-s', top,
                   '-o', str(executable)]
        command += [value for key, setting in config.items()
                    for value in ('-P', f'{top}.{key}={setting}')]
        command += [str(snapshot/source) for source in source_names]
        compile_log, sim_log = out/(name+'.compile.log'), out/(name+'.simulation.log')
        with compile_log.open('w') as stream:
            subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        with sim_log.open('w') as stream:
            subprocess.run([str(vv), '-N', str(executable)], env=env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        observed = sim_log.read_text()
        marker = re.search(r'PASS: registered index scoreboard mode=(\d+) tag=(\d+) checks=(\d+)', observed)
        if not marker or tuple(map(int, marker.groups()[:2])) != \
                (config['REGISTERED_INDEX'], config['TAG_SRAM']) or \
                (config['TAG_SRAM'] and int(marker[3]) == 0) or \
                re.search(r'ERROR|FAIL|FATAL', observed):
            raise SystemExit('Real Cache protocol/index check failed: '+str(sim_log))
        required = 'PASS: D-cache SRAM hit latency' if top.endswith('sram_tb') else 'PASS: D-cache tag_sram='
        if required not in observed:
            raise SystemExit('Original Cache checks did not execute: '+str(sim_log))
        metadata = re.search(r'PASS: live metadata query scoreboard mode=(\d+) tag=(\d+) checks=(\d+)', observed)
        if not metadata or tuple(map(int, metadata.groups()[:2])) != \
                (config['LOCAL_METADATA_QUERY'], config['TAG_SRAM']) or \
                int(metadata[3]) != int(marker[3]):
            raise SystemExit('Independent live metadata checks missing or incomplete: '+str(sim_log))
        results.append(dict(name=name, status='PASS', parameters=config, top=top,
                            index_checks=int(marker[3]), metadata_query_checks=int(metadata[3]),
                            compile_log_sha256=sha(compile_log),
                            simulation_log_sha256=sha(sim_log)))
        print('PASS '+name, flush=True)
    if len(results) != (24 if args.smoke else 720):
        raise SystemExit('Incomplete local-metadata protocol matrix')
    for path, expected in inputs.items():
        if sha(Path(path)) != expected:
            raise SystemExit('Frozen protocol input changed: '+path)
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE', total_cases=len(results),
        compiled_origins=origins, input_sha256=inputs, results=results,
        scope='Original four-state SRAM/hash/dirty/refill/hold/flush protocols and independent active-query index/live-metadata scoreboards',
        proves_whole_cpu=False, claims_cpu_ppa=False), indent=2)+'\n')
    print(f'COMPLETE: {len(results)} actual Cache local-metadata protocol configurations', flush=True)


if __name__ == '__main__':
    main()
