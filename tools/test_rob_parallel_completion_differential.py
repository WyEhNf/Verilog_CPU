"""Compare all original/candidate ROB ports, including undefined payloads.

Four-state Icarus comparison before and after each edge. Exercise real ROB64,
duplicate completion tags, stale generations, recovery and sticky errors.
This is simulation coverage, not a replacement for full formal equivalence.
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    assert not out.exists(), 'Preserve previous differential evidence'
    snapshot = out/'source_snapshot'
    snapshot.mkdir(parents=True)
    inputs = {}
    copies = [('baseline/rv32_rob.v','original.v'), ('rtl/backend/rv32_rob.v','candidate.v')]
    for source, target in copies:
        original = candidate/source
        shutil.copyfile(original, snapshot/target)
        inputs[str(original)], inputs[str(snapshot/target)] = sha(original), sha(snapshot/target)
    for name in ('rv32im_defs.vh', 'common/rv32_control_register_bank.v', 'common/rv32_asap7_fanout.v'):
        dest = snapshot/'rtl'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'rtl'/name, dest)
        inputs[str(dest)] = sha(dest)
    source = (snapshot/'original.v').read_text()
    gate = (snapshot/'candidate.v').read_text()
    header = source[source.index(') (')+3:source.index('\n);')]
    gate_header = gate[gate.index(') (')+3:gate.index('\n);')]
    assert header == gate_header, 'Complete interface changed'
    pattern = r'^\s*(input|output)\s+(?:wire|reg)\s*(\[[^\n]+?\])?\s*(\w+)\s*,?\s*$'
    ports = re.findall(pattern, header, re.M)
    assert len(ports) == len(re.findall(r'\b(?:input|output)\b', header)), 'Unparsed port'
    for label, code in [('gold',source),('gate',gate)]:
        assert code.count('module rv32_rob #(') == 1
        path = snapshot/(label+'.v')
        path.write_text(code.replace('module rv32_rob #(', 'module rob_'+label+' #(', 1))
        inputs[str(path)] = sha(path)
    inputs[str(Path(__file__).resolve())] = sha(__file__)
    shutil.copyfile(Path(__file__), snapshot/'differential_helper.py')
    inputs[str(snapshot/'differential_helper.py')] = sha(snapshot/'differential_helper.py')
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    iv, vv = suite/'bin/iverilog.exe', suite/'bin/vvp.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    inputs[str(iv)], inputs[str(vv)] = sha(iv),sha(vv)
    results = []
    report = dict(status='RUNNING', not_a_cpu_result=True, is_formal_proof=False,
                  no_output_masking=True, input_sha256=inputs, results=results)

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    for width, depth, checkpoint, buffered, generation in [(1,8,0,0,2),(2,8,1,1,2),
            (4,8,0,0,2),(4,64,1,1,8),(4,64,0,0,8),(4,64,1,0,2)]:
        config = dict(BE_WIDTH=width, ROB_ENTRIES=depth, PHYS_REGS=64, PHYS_ADDR_WIDTH=6,
                      GENERATION_WIDTH=generation, CHECKPOINT_WIDTH=192,
                      CHECKPOINT_IMPL=checkpoint, STORE_BUFFERED_RETIRE=buffered,
                      COMMIT_BANKED_READ=1, ALLOC_BANKED_WRITE=1)
        stem = f'be{width}_rob{depth}_cp{checkpoint}_sb{buffered}_gen{generation}'
        constants = [f'    localparam integer {k}={v};' for k,v in config.items()]
        constants += ['    localparam integer SLOT_WIDTH=$clog2(ROB_ENTRIES);',
                      '    localparam integer TAG_WIDTH=3+SLOT_WIDTH+GENERATION_WIDTH;']
        declarations, comparisons, randomize = [], [], []
        for direction, width_text, name in ports:
            if direction == 'input':
                declarations.append(f'    reg {width_text} {name}=0;')
                if name not in ('clk_i','reset_i'):
                    randomize.append(f'            rng=next_random(rng); {name}={{32{{rng}}}};')
            else:
                declarations.append(f'    wire {width_text} gold_{name}, gate_{name};')
                comparisons.append(f'        if (gold_{name} !== gate_{name}) $fatal(1,"{name} differs at cycle %0d",cycle);')
        instances = []
        for label in ('gold','gate'):
            params = config | ({'COMPLETION_PARALLEL_WRITE':1} if label == 'gate' else {})
            parameter_text = ', '.join(f'.{k}({v})' for k,v in params.items())
            connections = ', '.join(f'.{name}({name if direction == "input" else label+"_"+name})'
                                    for direction, _, name in ports)
            instances.append(f'    rob_{label} #({parameter_text}) {label} ({connections});')
        body = r'''
    integer cycle, lane, row, allocations=0, completions=0, recoveries=0, duplicates=0, commits=0;
    integer sticky_errors=0, stale_tags=0;
    reg [31:0] rng=32'h7f4a7c15;
    reg [TAG_WIDTH-1:0] tag_value;
    function [31:0] next_random; input [31:0] x; begin
        next_random={x[30:0],x[31]^x[21]^x[1]^x[0]}; end endfunction
    task compare; begin
COMPARE
    end endtask
    function [TAG_WIDTH-1:0] live_tag; input integer entry; begin
        live_tag=1 | (entry << 3) |
            (gold_entry_generation_o[entry*GENERATION_WIDTH +: GENERATION_WIDTH] << (3+SLOT_WIDTH));
    end endfunction
    initial begin
        for (cycle=0;cycle<8000;cycle=cycle+1) begin
            clk_i=0;
RANDOMIZE
            // Most of each epoch supplies legal contiguous allocations, so
            // large ROBs retire substantial work. Its final quarter retains
            // arbitrary lane holes and store/error/recovery combinations.
            if (cycle%128<96) begin
                alloc_valid_i=(1 << (rng%(BE_WIDTH+1)))-1;
                alloc_is_store_i=0;
            end
            reset_i=(cycle<2) || (cycle%128==0) ||
                ((gold_halted_o || gold_error_o) && cycle%7==0);
            alloc_is_halt_i=(cycle%587==0) ? 1 : 0;
            alloc_is_error_i=(cycle%397==0) ? 1 : 0;
            completion_error_i=0;
            recovery_valid_i=0;
            store_ack_error_i=(cycle%491==0);
            store_ack_valid_i=(cycle%3!=0);
            store_ack_tag_i=live_tag(gold_head_o);
            for (lane=0;lane<BE_WIDTH;lane=lane+1) begin
                row=(gold_head_o+lane+(cycle%3))%ROB_ENTRIES;
                if (cycle%11==0) row=gold_head_o;
                tag_value=live_tag(row);
                if (cycle%17==0) begin
                    tag_value[3+SLOT_WIDTH +: GENERATION_WIDTH]=
                        tag_value[3+SLOT_WIDTH +: GENERATION_WIDTH]+1'b1;
                    if (!reset_i) stale_tags=stale_tags+1;
                end
                // Kind bits are ignored by the original ROB tag predicate.
                rng=next_random(rng);tag_value[2:1]=rng[1:0];
                completion_tag_i[lane*TAG_WIDTH +: TAG_WIDTH]=tag_value;
                completion_valid_i[lane]=(cycle%5!=0);
                completion_done_i[lane]=(cycle%7!=0);
                rng=next_random(rng);completion_value_i[lane*32 +: 32]=rng;
                rng=next_random(rng);completion_store_addr_i[lane*32 +: 32]=rng;
                rng=next_random(rng);completion_store_data_i[lane*32 +: 32]=rng;
                rng=next_random(rng);completion_store_mask_i[lane*4 +: 4]=rng[3:0];
            end
            if (cycle%11==0 && cycle%5!=0 && cycle%7!=0 && gold_entry_valid_o[gold_head_o]) begin
                if (!reset_i && BE_WIDTH>1) duplicates=duplicates+1;
                // Lowest lane alone reports error; the last lane still owns data.
                if (cycle%33==0) begin completion_error_i[0]=1;sticky_errors=sticky_errors+1;end
            end
            if (cycle%19==0) begin
                for (lane=0;lane<BE_WIDTH;lane=lane+1) begin
                    row=(gold_head_o+lane+(cycle%5))%ROB_ENTRIES;
                    recovery_valid_i[lane]=1;
                    recovery_tag_i[lane*TAG_WIDTH +: TAG_WIDTH]=live_tag(row);
                end
            end
            #4;compare;
            if (!reset_i) begin
                if (gold_recovery_accept_o) recoveries=recoveries+1;
                for (lane=0;lane<BE_WIDTH;lane=lane+1) begin
                    if (gold_alloc_fire_o[lane]) allocations=allocations+1;
                    if (gold_commit_valid_o[lane] && commit_ready_i) commits=commits+1;
                    row=completion_tag_i[lane*TAG_WIDTH+3 +: SLOT_WIDTH];
                    if (completion_valid_i[lane] && completion_done_i[lane] &&
                        gold_entry_valid_o[row] &&
                        completion_tag_i[lane*TAG_WIDTH+3+SLOT_WIDTH +: GENERATION_WIDTH] ==
                        gold_entry_generation_o[row*GENERATION_WIDTH +: GENERATION_WIDTH])
                        completions=completions+1;
                end
            end
            clk_i=1;#1;compare;#4;
        end
        if (allocations<100 || completions<100 || recoveries<10 || commits<50 ||
            (BE_WIDTH>1 && duplicates<20) || sticky_errors<10 || stale_tags<100)
            $fatal(1,"Insufficient coverage alloc=%0d cpl=%0d rec=%0d commit=%0d dup=%0d err=%0d stale=%0d",
                allocations,completions,recoveries,commits,duplicates,sticky_errors,stale_tags);
        $display("PASS cycles=%0d allocations=%0d completions=%0d recoveries=%0d commits=%0d duplicates=%0d sticky_errors=%0d stale_tags=%0d",
            cycle,allocations,completions,recoveries,commits,duplicates,sticky_errors,stale_tags);
        $finish;
    end
'''
        body = body.replace('COMPARE','\n'.join(comparisons)).replace('RANDOMIZE','\n'.join(randomize))
        tb, exe = out/(stem+'.v'), out/(stem+'.vvp')
        tb.write_text('\n'.join(['`timescale 1ns/1ps','module differential_tb;',*constants,
                                 *declarations,*instances,body,'endmodule','']))
        report['active_case']=stem;save()
        compile_log, run_log = out/(stem+'.compile.log'), out/(stem+'.simulation.log')
        with compile_log.open('w') as stream:
            subprocess.run([str(iv),'-g2012','-I',str(snapshot/'rtl'),'-s','differential_tb','-o',str(exe),
                str(snapshot/'gold.v'),str(snapshot/'gate.v'),str(snapshot/'rtl/common/rv32_control_register_bank.v'),
                str(snapshot/'rtl/common/rv32_asap7_fanout.v'),str(tb)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        with run_log.open('w') as stream:
            subprocess.run([str(vv),'-N',str(exe)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        observed = run_log.read_text()
        match = re.search(r'PASS cycles=(\d+) allocations=(\d+) completions=(\d+) recoveries=(\d+) commits=(\d+) duplicates=(\d+) sticky_errors=(\d+) stale_tags=(\d+)',observed)
        assert match and int(match[1])==8000 and not re.search(r'FATAL|FAIL|ERROR',observed)
        counts = dict(zip(['cycles','allocations','completions','recoveries','commits','duplicates','sticky_errors','stale_tags'],map(int,match.groups())))
        results.append(dict(status='PASS',parameters=config,compared_output_ports=len(comparisons),**counts,
                            testbench_sha256=sha(tb),compile_log_sha256=sha(compile_log),simulation_log_sha256=sha(run_log)))
        save();print(stem+': '+match[0],flush=True)
    for name, expected in inputs.items():
        assert sha(name)==expected, 'Frozen input changed: '+name
    report.update(status='COMPLETE',active_case=None,total_cycles=sum(row['cycles'] for row in results))
    save();print('COMPLETE all-port four-state ROB differential including actual64',flush=True)


if __name__ == '__main__':
    main()
