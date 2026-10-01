"""Prove cache-controller state and every raw SRAM port for updates 0 vs 1/2.

Only the proof design exposes/removes actual SRAM instances, turning each rdata
into the same unrestricted input and every SRAM input pin into a checked output.
No SRAM stub is declared or library/framework modified. Native four-state tests
separately exercise the real original storage model. This is not an area flow or
a proof of a fabricated SRAM implementation.
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
PROFILES = {
    'current': dict(lines=1024, ways=2, tag=1, mshr=4, waiters=8, merge=16),
    'ff_direct': dict(lines=16, ways=1, tag=0, mshr=2, waiters=2, merge=0),
    'sram_direct': dict(lines=16, ways=1, tag=1, mshr=2, waiters=2, merge=16),
    'ff_2way': dict(lines=16, ways=2, tag=0, mshr=2, waiters=2, merge=16),
    'sram_2way': dict(lines=16, ways=2, tag=1, mshr=2, waiters=2, merge=16),
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--case', choices=PROFILES, action='append')
    parser.add_argument('--candidate', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    selected = args.case or list(PROFILES)
    out = args.outdir.resolve()
    if (out / 'report.json').exists():
        raise SystemExit('Choose a fresh proof directory')
    snapshot = out / 'source_snapshot'
    sources = [ROOT / 'rtl/cache/rv32_dcache_nonblocking.v', ROOT / 'rtl/cache/rv32_dcache_control_banks.v', ROOT / 'rtl/rv32im_defs.vh',
               ROOT / '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv', Path(__file__)]
    hashes = {}
    for source in sources:
        destination = snapshot / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha(destination) != sha(source):
            raise SystemExit('Different existing snapshot: ' + str(destination))
        shutil.copyfile(source, destination)
        hashes[str(destination)] = sha(destination)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    cache = snapshot / 'rtl/cache/rv32_dcache_nonblocking.v'
    banks = snapshot / 'rtl/cache/rv32_dcache_control_banks.v'
    ram = snapshot / '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'
    results = []

    def run(name, stage, commands):
        script, log = out / f'{name}.{stage}.ys', out / f'{name}.{stage}.log'
        script.write_text('\n'.join(commands) + '\n')
        with log.open('w') as stream:
            completed = subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                                       stdout=stream, stderr=subprocess.STDOUT)
        if completed.returncode:
            raise SystemExit(f'Proof stage {stage} failed: {log}')
        return log

    for name in selected:
        cfg = PROFILES[name]
        print('START ' + name, flush=True)
        contracts = out / f'{name}.contracts.json'
        preparation = []
        for kind, enabled in (('gold', 0), ('gate', args.candidate)):
            preparation.extend([
                'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(ram),
                'read_verilog ' + quote(banks),
                'read_verilog -I' + (snapshot / 'rtl').as_posix() + ' ' + quote(cache),
                f'chparam -set CACHE_LINES {cfg["lines"]} -set CACHE_WAYS {cfg["ways"]} '
                f'-set TAG_SRAM {cfg["tag"]} -set STATIC_UPDATES {enabled} -set INDEX_HASH 1 '
                f'-set PREFETCH 1 -set MSHR_ENTRIES {cfg["mshr"]} -set WAITER_ENTRIES {cfg["waiters"]} '
                f'-set STORE_MERGE_DELAY {cfg["merge"]} -set TAG_WIDTH 14 rv32_dcache_nonblocking',
                # Elaborate each top independently. Dynamic bank port widths
                # can cause hierarchy to re-derive/rename a chparam template.
                'hierarchy -check -top rv32_dcache_nonblocking',
                'rename -top ' + kind,
                'expose -evert ' + kind + '/t:*sram_fakeram',
                'proc', 'memory_collect',
                # Expand the real controller state for proof only. The PPA
                # path still preserves all functional bank boundaries.
                'setattr -mod -unset keep_hierarchy', 'flatten ' + kind,
                'setattr -mod -unset top',
                'design -stash ' + kind, 'design -reset',
            ])
        preparation.extend(['design -copy-from gold -as gold gold',
                            'design -copy-from gate -as gate gate',
                            'write_json ' + quote(contracts)])
        run(name, 'prepare', preparation)
        model = json.loads(contracts.read_text())['modules']
        signatures = [{port: (p['direction'], len(p['bits'])) for port, p in model[kind]['ports'].items()}
                      for kind in ('gold', 'gate')]
        if signatures[0] != signatures[1]:
            raise SystemExit('RAM/controller port contracts differ')
        pins = ('clk', 'en', 'we', 'wmask', 'addr', 'wdata', 'rdata')
        ram_ports = {port: signature for port, signature in signatures[0].items()
                     if any(port.endswith('.' + pin) for pin in pins)}
        instances = {port.rsplit('.', 1)[0] for port in ram_ports}
        if len(instances) != (cfg['ways'] + 2 if cfg['tag'] else 1):
            raise SystemExit('Missing real raw SRAM port contract')
        for instance in instances:
            for pin in pins:
                signature = ram_ports.get(instance + '.' + pin)
                if not signature or signature[0] != ('input' if pin == 'rdata' else 'output'):
                    raise SystemExit('Incomplete or incorrectly directed SRAM pin contract')
        for kind in ('gold', 'gate'):
            if any('sram_fakeram' in cell['type'] for cell in model[kind]['cells'].values()):
                raise SystemExit('A storage blackbox remains in the controller proof')
        log = run(name, 'prove', [
            # Proof-only flattening expands the actual state banks; area/STA
            # preserve their real hierarchy through the original course flow.
            'read_json ' + quote(contracts), 'proc', 'memory_map',
            'setattr -mod -unset keep_hierarchy', 'flatten gold gate',
            'opt_expr gold gate', 'opt_clean gold gate',
            'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
            'select -assert-none equiv/t:*sram_fakeram equiv/t:$mem*', 'check -assert',
            'equiv_struct', 'equiv_simple -seq 1', 'equiv_induct -seq 4', 'equiv_status -assert',
        ])
        text = log.read_text()
        counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
        if not counts or int(counts[-1][1]) or 'Equivalence successfully proven!' not in text:
            raise SystemExit('Controller/SRAM-port identity NOT proven: ' + str(log))
        results.append(dict(name=name, status='PROVEN', configuration=cfg,
                            proven_cells=int(counts[-1][0]), unproven_cells=0,
                            raw_sram_instances=len(instances), raw_sram_pin_contracts=ram_ports,
                            contract_sha256=sha(contracts), log_sha256=sha(log)))
        print('PROVEN ' + name, flush=True)
    for path, expected in hashes.items():
        if sha(Path(path)) != expected:
            raise SystemExit('Frozen proof input changed: ' + path)
    report = dict(status='COMPLETE', selected_profiles=selected, results=results, source_sha256=hashes,
                  baseline_static_updates=0, candidate_static_updates=args.candidate,
                  method='Sequential controller/common-state and every raw SRAM pin contract equivalence',
                  sram_rdata_shared_unrestricted_input=True,
                  proves_sram_storage_internals=False, changes_area_flow=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: ' + str(len(results)) + ' controller/SRAM-port profiles proven')


if __name__ == '__main__':
    main()
