"""Prove depth-zero compatibility and check the registered-credit boundary.

The whole legacy bridge is compared against its actual verified frozen source.
FIFO modes intentionally have different buffering, so their timing equivalence
is NOT claimed. Their physical dependency check is complemented by protocol and
whole-core simulation; this is not a whole-CPU PPA or correctness proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import re

from verify_course_axi_area import verify

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    verified = verify(args.reference_run)
    manifest = json.loads((args.reference_run / 'run_manifest.json').read_text())
    original = Path(manifest['source_snapshot_root']) / 'rtl/course/rv32_axi_lite_bridge.v'
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Use a new equivalence directory')
    snapshot = out / 'source_snapshot'
    snapshot.mkdir(parents=True)
    hashes = {}
    for name, source in (('original_bridge.v', original),
                         ('candidate_bridge.v', ROOT / 'rtl/course/rv32_axi_lite_bridge.v'),
                         (Path(__file__).name, Path(__file__).resolve())):
        target = snapshot / name
        shutil.copyfile(source, target)
        hashes[str(target)] = sha(target)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []

    def run(name, commands):
        script, log = out / (name + '.ys'), out / (name + '.log')
        script.write_text('\n'.join(commands) + '\n')
        print('START ' + name, flush=True)
        with log.open('w') as stream:
            subprocess.run([str(yosys), '-T', '-s', str(script)], stdout=stream,
                           stderr=subprocess.STDOUT, env=env, check=True)
        return log

    for reads, writes, words in ((2, 2, 4), (8, 4, 16), (16, 8, 64)):
        name = f'legacy_r{reads}_w{writes}_q{words}'
        parameter = f'chparam -set READ_LINES {reads} -set WRITE_LINES {writes} -set WORD_QUEUE {words}'
        log = run(name, [
            'read_verilog ' + quote(snapshot / 'original_bridge.v'),
            parameter + ' rv32_axi_lite_bridge', 'rename rv32_axi_lite_bridge gold',
            'read_verilog ' + quote(snapshot / 'candidate_bridge.v'),
            parameter + ' -set RESPONSE_FIFO_DEPTH 0 rv32_axi_lite_bridge',
            'rename rv32_axi_lite_bridge gate', 'hierarchy -check', 'proc', 'memory_map',
            'flatten gold gate', 'opt_expr gold gate', 'opt_clean gold gate',
            'equiv_make gold gate equiv', 'hierarchy -check -top equiv', 'check -assert',
            'equiv_struct', 'equiv_simple -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert',
        ])
        text = log.read_text()
        counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
        if not counts or int(counts[-1][1]) or 'Equivalence successfully proven!' not in text:
            raise SystemExit('Whole legacy bridge NOT proven: ' + str(log))
        results.append(dict(name=name, status='PROVEN', proven_cells=int(counts[-1][0]),
                            unproven_cells=0, log_sha256=sha(log)))
        print('PROVEN ' + name, flush=True)

    credits = []
    for depth in (2, 4, 8):
        name = f'credit_d{depth}'
        model_path = out / (name + '.json')
        log = run(name, [
            'read_verilog ' + quote(snapshot / 'candidate_bridge.v'),
            f'chparam -set DEPTH {depth} -set WIDTH 169 rv32_axi_response_fifo',
            'hierarchy -check -top rv32_axi_response_fifo',
            'proc', 'memory_map', 'flatten', 'opt', 'check -assert', 'write_json ' + quote(model_path),
        ])
        model = json.loads(model_path.read_text())['modules']['rv32_axi_response_fifo']
        drivers = {}
        for cell in model['cells'].values():
            for pin, bits in cell['connections'].items():
                if cell['port_directions'][pin] == 'output':
                    for bit in bits:
                        if type(bit) is int:
                            if bit in drivers:
                                raise SystemExit('Multiple physical drivers')
                            drivers[bit] = cell

        def primary_inputs(output):
            pending, seen, inputs, boundaries = list(model['ports'][output]['bits']), set(), set(), set()
            input_ports = {bit: name for name, port in model['ports'].items()
                           if port['direction'] == 'input' for bit in port['bits']}
            while pending:
                bit = pending.pop()
                if type(bit) is not int or bit in seen:
                    continue
                seen.add(bit)
                if bit in input_ports:
                    inputs.add(input_ports[bit])
                if bit not in drivers:
                    continue
                cell = drivers[bit]
                if cell['type'] in ('$dff', '$dffe', '$sdff', '$sdffe', '$sdffce'):
                    boundaries.add(bit)
                    continue
                pending.extend(v for pin, bits in cell['connections'].items()
                               if cell['port_directions'][pin] == 'input' for v in bits)
            return inputs, boundaries

        ready_inputs, ready_boundaries = primary_inputs('in_ready')
        packet_inputs, packet_boundaries = primary_inputs('out_packet')
        if ready_inputs != {'reset'} or not ready_boundaries:
            raise SystemExit('Credit retains a combinational dependency on consumer READY')
        if packet_inputs or not packet_boundaries:
            raise SystemExit('Response payload retains a combinational external input path')
        credits.append(dict(depth=depth, status='VERIFIED',
                            credit_primary_inputs=sorted(ready_inputs),
                            credit_register_boundaries=len(ready_boundaries),
                            payload_primary_inputs=sorted(packet_inputs),
                            payload_register_boundaries=len(packet_boundaries),
                            model_sha256=sha(model_path), log_sha256=sha(log)))
        print('VERIFIED registered credit ' + name, flush=True)
    for path, digest in hashes.items():
        if sha(Path(path)) != digest:
            raise SystemExit('Frozen proof input changed: ' + path)
    report = dict(status='COMPLETE', source_sha256=hashes, results=results, registered_credit_checks=credits,
                  reference_run=str(args.reference_run.resolve()), reference_netlist_sha256=verified['netlist_sha256'],
                  method='Entire depth-zero bridge sequential identity against actual frozen source; FIFO dependency boundaries',
                  proves_fifo_cycle_equivalence=False, proves_whole_cpu=False, claims_cpu_ppa=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('COMPLETE: whole legacy bridge identity and registered-credit boundaries')


if __name__ == '__main__':
    main()
