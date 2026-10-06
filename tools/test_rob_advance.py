"""Prove the literal original/candidate ROB pointer functions for arbitrary inputs.

Extract the real function bodies, including signed 32-bit amount, from frozen
RTL. Compare every head and every amount without restricting it to legal CPU
pop counts; retain old negative/over-capacity saturation and wrap semantics.
This function proof is supplementary, never a full ROB/CPU equivalence claim.
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
        return hashlib.file_digest(stream,'sha256').hexdigest()


def quote(path):
    return '"'+Path(path).resolve().as_posix()+'"'


def extract(path):
    functions = re.findall(r'function\s+\[SLOT_WIDTH-1:0\]\s+advance_slot\s*;.*?endfunction',
                           path.read_text(),re.S)
    if len(functions) != 1 or 'input integer amount;' not in functions[0] or \
            'input [SLOT_WIDTH-1:0] start;' not in functions[0]:
        raise SystemExit('Actual ROB advance function signature changed: '+str(path))
    return functions[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=ROOT/'rtl/backend/rv32_rob.v')
    parser.add_argument('--outdir',type=Path,required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh ROB pointer proof directory')
    snapshot, origins, hashes = out/'source_snapshot', {}, {}
    snapshot.mkdir(parents=True)
    for name,source in [('original_rob.v',args.baseline.resolve()),
                        ('candidate_rob.v',args.candidate.resolve()),
                        ('test_rob_advance.py',Path(__file__).resolve())]:
        target = snapshot/name
        shutil.copyfile(source,target)
        origins[name] = dict(path=str(source),sha256=sha(source))
        hashes[str(target)] = sha(target)
    bodies = [extract(snapshot/name) for name in ('original_rob.v','candidate_rob.v')]
    fixture = out/'actual_function_miter.v'
    declarations = []
    for name,body in zip(('gold','gate'),bodies):
        declarations.append(f'''module advance_{name} #(parameter integer ROB_ENTRIES=64,
            parameter integer SLOT_WIDTH=$clog2(ROB_ENTRIES)) (
            input wire [SLOT_WIDTH-1:0] start, input wire signed [31:0] amount,
            output wire [SLOT_WIDTH-1:0] result);
            {body}
            assign result=advance_slot(start,amount);
            endmodule''')
    declarations.append('''module student_top #(parameter integer ROB_ENTRIES=64,
        parameter integer SLOT_WIDTH=$clog2(ROB_ENTRIES)) (
        input wire [SLOT_WIDTH-1:0] start, input wire signed [31:0] amount,
        output wire matches);
        wire [SLOT_WIDTH-1:0] gold_result,gate_result;
        advance_gold #(.ROB_ENTRIES(ROB_ENTRIES)) gold(start,amount,gold_result);
        advance_gate #(.ROB_ENTRIES(ROB_ENTRIES)) gate(start,amount,gate_result);
        assign matches=(gold_result==gate_result);
        endmodule''')
    fixture.write_text('\n'.join(declarations)+'\n')
    hashes[str(fixture)] = sha(fixture)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    results = []
    for depth in (2,4,8,16,32,64,128):
        script,log = out/f'rob{depth}.ys',out/f'rob{depth}.log'
        script.write_text('\n'.join([
            'read_verilog '+quote(fixture),
            f'chparam -set ROB_ENTRIES {depth} student_top',
            'prep -top student_top -flatten','opt',
            'sat -verify -prove matches 1 -show-inputs -show-outputs'])+'\n')
        print(f'START literal ROB advance depth{depth}; all signed amounts',flush=True)
        with log.open('w') as stream:
            subprocess.run([str(yosys),'-T','-s',str(script)],env=env,
                           stdout=stream,stderr=subprocess.STDOUT,check=True)
        observed = log.read_text()
        if 'SAT proof finished - no model found: SUCCESS!' not in observed:
            raise SystemExit('Literal ROB function not proven: '+str(log))
        results.append(dict(depth=depth,status='PROVEN',arbitrary_head=True,
                            arbitrary_signed_32bit_amount=True,script_sha256=sha(script),log_sha256=sha(log)))
        print(f'PROVEN depth{depth}',flush=True)
    for path,expected in hashes.items():
        if sha(path) != expected:
            raise SystemExit('Frozen function proof input changed: '+path)
    for row in origins.values():
        if sha(row['path']) != row['sha256']:
            raise SystemExit('Literal function proof origin changed: '+row['path'])
    report = dict(status='COMPLETE',scope='Literal actual ROB advance functions, arbitrary head and signed amount',
                  extracted_actual_bodies=True,proves_whole_rob=False,proves_cpu=False,
                  input_sha256=hashes,compiled_origins=origins,results=results)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('COMPLETE seven literal ROB pointer function proofs',flush=True)


if __name__ == '__main__':
    main()
