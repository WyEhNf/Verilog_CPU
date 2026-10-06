"""Compare every actual RS output over deterministic randomized clock traces.

Freeze the same complete gold/candidate used by the static-allocation proof.
No output masking or two-state substitution: compare all ports with !== using
Icarus, including invalid-entry payloads. This is simulation, not formal proof.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-dir', type=Path, required=True)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.proof_dir.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh differential test directory')
    snapshot = out/'source_snapshot'
    snapshot.mkdir(parents=True)
    inputs = {}
    for name in ('original.v', 'candidate.v', 'rtl/rv32im_defs.vh'):
        original = (args.candidate_root.resolve()/'rtl/backend/rv32_reservation_station.v'
                    if name == 'candidate.v' else source/'source_snapshot'/name)
        target = snapshot/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target)
        inputs[str(original)] = sha(original)
        inputs[str(target)] = sha(target)
    for original, target, module in [('original.v','gold.v','rs_gold'),('candidate.v','gate.v','rs_gate')]:
        code = (snapshot/original).read_text()
        assert code.count('module rv32_reservation_station #(') == 1
        code = code.replace('module rv32_reservation_station #(', 'module '+module+' #(', 1)
        (snapshot/target).write_text(code)
        inputs[str(snapshot/target)] = sha(snapshot/target)
    shutil.copyfile(Path(__file__),snapshot/Path(__file__).name)
    inputs[str(snapshot/Path(__file__).name)] = sha(snapshot/Path(__file__).name)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    iv, vv = suite/'bin/iverilog.exe', suite/'bin/vvp.exe'
    inputs[str(iv)],inputs[str(vv)] = sha(iv),sha(vv)
    results = []
    cases = [(1,4,1,1),(2,4,4,70),(4,4,10,70),(4,16,10,70)]
    report = dict(status='RUNNING',proves_whole_cpu=False,is_formal_proof=False,
                  input_sha256=inputs,results=results)
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for width,entries,wake,metadata in cases:
        stem = f'be{width}_entries{entries}_wake{wake}_metadata{metadata}'
        prepared = source/(stem+'.prepared.json')
        model = json.loads(prepared.read_text())['modules']
        ports = model['gold']['ports']
        schema = lambda m: {n:(v['direction'],len(v['bits'])) for n,v in m['ports'].items()}
        assert schema(model['gold']) == schema(model['gate'])
        inputs[str(prepared)] = sha(prepared)
        del model
        config = dict(BE_WIDTH=width,ENTRIES=entries,TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,
                      WAKE_WIDTH=wake,METADATA_WIDTH=metadata,AGE_WIDTH=32,WAKE_MUX_IMPL=1)
        declarations,checks,randomize = [],[],[]
        for name,port in ports.items():
            size = len(port['bits'])
            packed = f'[{size-1}:0] '
            if port['direction'] == 'input':
                declarations.append(f'    reg {packed}{name} = 0;')
                if name not in ('clk_i','reset_i'):
                    for low in range(0,size,32):
                        chunk = min(32,size-low)
                        select = f'[{low} +: {chunk}]' if size > 1 else ''
                        randomize.append(f'            rng = next_random(rng); {name}{select} = rng[{chunk-1}:0];')
            else:
                assert port['direction'] == 'output'
                declarations.append(f'    wire {packed}gold_{name}, gate_{name};')
                checks.append(f'            if (gold_{name} !== gate_{name}) $fatal(1,"Output {name} differs at cycle %0d", cycle);')
        instances = []
        for label,module in [('gold','rs_gold'),('gate','rs_gate')]:
            parameters = config | ({'ALLOC_STATIC_WRITE':1} if label == 'gate' else {})
            parameter_text = ', '.join(f'.{k}({v})' for k,v in parameters.items())
            connections = ', '.join(f'.{n}({n if p["direction"] == "input" else label+"_"+n})' for n,p in ports.items())
            instances.append(f'    {module} #({parameter_text}) {label} ({connections});')
        code = '\n'.join(['`timescale 1ns/1ps','module differential_tb;',*declarations,
                          '    integer cycle, lane, allocations=0, issues=0, flushes=0, duplicate_wakes=0;',
                          "    reg [31:0] rng = 32'h6a09e667;",
                          '    function [31:0] next_random; input [31:0] x; begin',
                          '        next_random = {x[30:0],x[31]^x[21]^x[1]^x[0]}; end endfunction',
                          '    task compare; begin',*checks,'    end endtask',*instances,
                          '    initial begin', '        reset_i=1;',
                          '        for (cycle=0; cycle<8000; cycle=cycle+1) begin',
                          '            clk_i=0;',*randomize,
                          '            reset_i = (cycle<2) || (cycle%521==0);',
                          '            flush_valid_i = (cycle%23==0) || ((rng & 63)==0);',
                          f'            for (lane=0; lane<{width}; lane=lane+1) begin',
                          '                rng=next_random(rng); alloc_rob_tag_i[lane*17 +: 17]=((rng & 31)<<1)|1;',
                          '                rng=next_random(rng); alloc_src1_tag_i[lane*17 +: 17]=((rng & 31)<<1)|1;',
                          '                rng=next_random(rng); alloc_src2_tag_i[lane*17 +: 17]=((rng & 31)<<1)|1;',
                          '            end',
                          f'            for (lane=0; lane<{wake}; lane=lane+1) begin',
                          '                rng=next_random(rng); wake_tag_i[lane*17 +: 17]=((rng & 31)<<1)|1;',
                          '                if (cycle%13==0) begin wake_valid_i[lane]=1; wake_tag_i[lane*17 +: 17]=17\'d1; end',
                          '            end',
                          '            #4; compare;',
                          '            if (!reset_i) begin',
                          '                if (flush_valid_i) flushes=flushes+1;',
                          f'                if (cycle%13==0 && {wake}>1) duplicate_wakes=duplicate_wakes+1;',
                          f'                for (lane=0; lane<{width}; lane=lane+1) begin',
                          '                    if (!flush_valid_i && gold_alloc_fire_o[lane]) allocations=allocations+1;',
                          '                    if (!flush_valid_i && gold_issue_valid_o[lane] && issue_ready_i[lane]) issues=issues+1;',
                          '                end', '            end',
                          '            clk_i=1; #1; compare; #4;', '        end',
                          f'        if (allocations<100 || issues<25 || flushes<100 || ({wake}>1 && duplicate_wakes<100)) $fatal(1,"Insufficient exercised events");',
                          '        $display("PASS full-port RS differential cycles=%0d allocations=%0d issues=%0d flushes=%0d duplicate_wakes=%0d",cycle,allocations,issues,flushes,duplicate_wakes);',
                          '        $finish;', '    end','endmodule',''])
        tb,exe = out/(stem+'.v'),out/(stem+'.vvp')
        tb.write_text(code)
        compile_log,run_log = out/(stem+'.compile.log'),out/(stem+'.simulation.log')
        report['active_case']=stem;save()
        with compile_log.open('w') as stream:
            subprocess.run([str(iv),'-g2012','-I',str(snapshot/'rtl'),'-s','differential_tb',
                            '-o',str(exe),str(snapshot/'gold.v'),str(snapshot/'gate.v'),str(tb)],
                           env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        with run_log.open('w') as stream:
            subprocess.run([str(vv),'-N',str(exe)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        text = run_log.read_text()
        match = re.search(r'PASS full-port RS differential cycles=(\d+) allocations=(\d+) issues=(\d+) flushes=(\d+) duplicate_wakes=(\d+)',text)
        assert match and int(match[1]) == 8000 and not re.search(r'FATAL|ERROR|FAIL',text)
        results.append(dict(status='PASS',parameters=config,cycles=int(match[1]),allocations=int(match[2]),
                            issues=int(match[3]),flushes=int(match[4]),duplicate_wakes=int(match[5]),
                            compared_output_ports=sum(p['direction']=='output' for p in ports.values()),
                            testbench_sha256=sha(tb),compile_log_sha256=sha(compile_log),simulation_log_sha256=sha(run_log)))
        save();print(stem+': '+match[0],flush=True)
    for name,expected in inputs.items():
        assert sha(Path(name)) == expected, 'Frozen input changed: '+name
    report.update(status='COMPLETE',active_case=None,total_cycles=sum(r['cycles'] for r in results))
    save();print('COMPLETE 32000 full-port four-state differential cycles',flush=True)


if __name__ == '__main__':
    main()
