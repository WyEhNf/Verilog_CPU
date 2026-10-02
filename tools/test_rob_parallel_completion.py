"""Compare actual allocation banks against a verified process-local ROB baseline.

The complete architectural state and outputs are compared with arbitrary
inputs. This is a compositional component proof, not a direct original CPU
proof; the supplied baseline's separate certificate must also be checked.

Smoke formal profiles cover eight small/edge whole-module configurations, not
ROB64; protocol profiles still cover all four original depths. The original
CPU RTL is the reference. No ports, state fields or input cases are removed.

Protocols retain every original ROB check and visit every physical head with
full-width commit, reversed completion lanes and retirement backpressure.
Formal compares the entire actual candidate ROB against the original RTL,
including all module outputs and same-named state, not a hand-written mux.
No assumptions narrow completion, recovery or allocation input behavior.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path('E:/Verilog_cpu')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"' + Path(path).resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True,
                        help='Actual verified clean ROB; compositional, not a direct original-CPU proof')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--phase', choices=('protocol', 'formal', 'all'), default='all')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--alloc-mode', type=int, choices=(0,1), default=1)
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh ROB parallel-completion evidence directory')
    names = [Path(name) for name in (
        'rtl/backend/rv32_rob.v', 'tb/unit/rv32_rob_tb.v', 'rtl/rv32im_defs.vh',
        'rtl/common/rv32_control_register_bank.v', 'rtl/common/rv32_asap7_fanout.v',
        'tools/test_rob_parallel_completion.py')]
    snapshot, hashes, origins = out/'source_snapshot', {}, {}
    for name in names:
        source = candidate/name if (candidate/name).is_file() else ROOT/name
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(target)] = digest(target)
        origins[name.as_posix()] = dict(path=str(source), sha256=digest(source))
    baseline = snapshot/'original_rob.v'
    shutil.copyfile(args.baseline.resolve(), baseline)
    hashes[str(baseline)] = digest(baseline)
    origins['original_rob.v'] = dict(path=str(args.baseline.resolve()), sha256=digest(baseline))
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    binaries = {name: suite/'bin'/file for name, file in
                (('iverilog','iverilog.exe'), ('vvp','vvp.exe'), ('yosys','yosys.exe'))}
    hashes.update({str(path): digest(path) for path in binaries.values()})
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    results = []

    def verify_inputs():
        for name, expected in hashes.items():
            if digest(name) != expected:
                raise SystemExit('Frozen ROB proof input changed: '+name)
        for row in origins.values():
            if digest(row['path']) != row['sha256']:
                raise SystemExit('ROB original source changed: '+row['path'])

    def run(command, log):
        verify_inputs()
        with log.open('w') as stream:
            subprocess.run(command, cwd=snapshot, env=env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        verify_inputs()

    if args.phase in ('protocol','all'):
        cases = [(width, depth, control, mode) for width in (1,2,4)
                 for depth in (4,8,32,64) for control in (0,1) for mode in (0,1)]
        if args.smoke:
            cases = [(width,64,0,mode) for width in (1,2,4) for mode in (0,1)]
        for width, depth, control, mode in cases:
            stem = f'protocol_be{width}_rob{depth}_control{control}_bank{mode}'
            image = out/(stem+'.vvp')
            compile_log, log = out/(stem+'.compile.log'), out/(stem+'.simulation.log')
            settings = dict(BE_WIDTH=width, ROB_ENTRIES=depth,
                            ROB_CONTROL_REGISTER_BANKS=control, COMMIT_BANKED_READ=mode,
                            ALLOC_BANKED_WRITE=args.alloc_mode)
            command = [str(binaries['iverilog']), '-g2012', '-I', 'rtl', '-s', 'rv32_rob_tb',
                       '-o', str(image)]
            command += [item for key, value in settings.items()
                        for item in ('-P',f'rv32_rob_tb.{key}={value}')]
            command += [str(snapshot/name) for name in names[:2]+names[3:5]]
            run(command, compile_log)
            run([str(binaries['vvp']), '-N', str(image)], log)
            observed = log.read_text()
            marker = re.search(r'PASS: banked commit rotation mode=(\d+) head_positions=(\d+) lane_checks=(\d+)', observed)
            if not marker or tuple(map(int,marker.groups())) != (mode,depth,depth*width) or \
                    f'PASS: B-03 ROB BE_WIDTH={width}' not in observed or re.search(r'FAIL|FATAL|ERROR',observed):
                raise SystemExit('Original ROB protocol or exhaustive rotation failed: '+str(log))
            results.append(dict(name=stem, phase='protocol', parameters=settings, status='PASS',
                all_physical_heads_visited=True, lane_checks=depth*width,
                compile_log_sha256=digest(compile_log), log_sha256=digest(log)))
            print('PASS '+stem, flush=True)
        if len(results) != (6 if args.smoke else 48):
            raise SystemExit('Incomplete ROB protocol matrix')

    if args.phase in ('formal','all'):
        cases = [(width,depth,checkpoint,buffered,1) for checkpoint in (1,0) for buffered in (1,0)
                 for width in (1,2,4) for depth in (2,4,8,16,32,64)]
        cases.append((4,64,1,1,0))
        if args.smoke:
            cases = [(1,8,1,1,1),(2,8,1,1,1),(4,8,1,1,1),(4,2,1,1,1),
                     (4,8,1,1,0),(4,8,0,0,1),(4,8,1,0,1),(4,8,0,1,1)]
        for width, depth, checkpoint, buffered, mode in cases:
            stem = f'formal_be{width}_rob{depth}_cp{checkpoint}_sb{buffered}_bank{mode}'
            script, log = out/(stem+'.ys'), out/(stem+'.log')
            settings = dict(BE_WIDTH=width, ROB_ENTRIES=depth, PHYS_REGS=64, PHYS_ADDR_WIDTH=6,
                            GENERATION_WIDTH=8, CHECKPOINT_WIDTH=32, CHECKPOINT_IMPL=checkpoint,
                            STORE_BUFFERED_RETIRE=buffered, COMMIT_BANKED_READ=mode,
                            ALLOC_BANKED_WRITE=args.alloc_mode)
            parameters = ' '.join(f'-set {key} {value}' for key,value in settings.items())
            commands = [
                'read_verilog -I rtl '+quote(baseline),
                'chparam '+parameters+' rv32_rob', 'rename rv32_rob gold',
                'read_verilog -I rtl '+quote(snapshot/'rtl/backend/rv32_rob.v'),
                'chparam '+parameters+' -set COMPLETION_PARALLEL_WRITE 1 rv32_rob',
                'rename rv32_rob gate', 'proc', 'memory_map', 'opt_expr -keepdc', 'opt_clean',
                'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
                'equiv_simple -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert']
            script.write_text('\n'.join(commands)+'\n')
            print('START '+stem, flush=True)
            run([str(binaries['yosys']), '-T', '-s', str(script)], log)
            observed = log.read_text()
            count = re.search(r'Found (\d+) \$equiv cells in equiv:',observed)
            if not count or 'Equivalence successfully proven!' not in observed or \
                    re.search(r'ERROR:',observed):
                raise SystemExit('Complete actual ROB equivalence not proven: '+str(log))
            results.append(dict(name=stem, phase='formal', parameters=settings|dict(COMMIT_BANKED_READ=mode, ALLOC_BANKED_WRITE=args.alloc_mode),
                                status='PROVEN', equiv_cells=int(count[1]),
                                script_sha256=digest(script), log_sha256=digest(log)))
            print('PROVEN '+stem, flush=True)
        if sum(row['phase']=='formal' for row in results) != (8 if args.smoke else 73):
            raise SystemExit('Incomplete full-ROB equivalence matrix')
    verify_inputs()
    report = dict(status='COMPLETE', total_cases=len(results), phase=args.phase, smoke=args.smoke,
                  input_sha256=hashes, compiled_origins=origins, results=results,
                  allocation_bank_mode=args.alloc_mode, baseline_path=str(args.baseline.resolve()),
                  direct_original_cpu_proof=False, compositional_component_proof=True,
                  not_a_cpu_result=True, integrated_into_cpu=False,
                  scope='All actual ROB state and outputs versus supplied clean baseline; compositional component proof, not original CPU',
                  no_added_pipeline_stage=True, no_ports_or_fields_omitted=True)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'COMPLETE {len(results)} ROB parallel-completion cases; not CPU PPA',flush=True)


if __name__ == '__main__':
    main()
