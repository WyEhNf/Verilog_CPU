"""Exercise MMIO retirement rules on original ROB and both predecode modes.

Use independent expected handshake/retirement outcomes, all 16 strobes,
adjacent and ordinary addresses, duplicate completion priority, stalled
retirement, wrong-generation acknowledgements, and first/last physical heads.
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

BODY = r'''
    integer tests, true_exits, partial_writes, wrong_acks, terminal_prefixes;
    integer duplicate_tests, head_boundary_tests, mask_number, position, step;
    reg [TAG_W-1:0] group_tags [0:BE_WIDTH-1];
    reg [31:0] expected_data;
    task require;
        input condition; input [8*100-1:0] message;
        begin if (condition !== 1'b1) begin
            $display("FAIL case=%0d head=%0d: %0s",tests,position,message); $fatal(1);
        end end
    endtask
    task run_case;
        input [31:0] address;
        input [3:0] mask;
        input expected_exit;
        input duplicate;
        integer k;
        begin
            @(negedge clk); reset=1; clear_inputs(); commit_ready=1; store_ready=0;
            @(posedge clk); #1; reset=0;
            // Reach the chosen physical head using real allocate/complete/pop.
            for (k=0;k<position;k=k+1) begin
                clear_inputs(); alloc_one(0,32'h1000+k*4,0); #1;
                current_tag=alloc_tag[0 +: TAG_W];
                @(posedge clk); #1; clear_inputs(); complete_one(0,current_tag,k);
                @(posedge clk); #1; clear_inputs(); @(posedge clk); #1;
            end
            require(head===position && occupancy===0,"head reached by normal retirement");
            commit_ready=0; clear_inputs();
            for(k=0;k<BE_WIDTH;k=k+1) alloc_one(k,32'h2000+k*4,k+1);
            alloc_store[0]=1; #1;
            require(alloc_count===BE_WIDTH,"allocate complete group");
            for(k=0;k<BE_WIDTH;k=k+1) group_tags[k]=alloc_tag[k*TAG_W +: TAG_W];
            saved_store_tag=group_tags[0]; expected_data=32'h12340000+tests;
            @(posedge clk); #1; clear_inputs();
            for(k=0;k<BE_WIDTH;k=k+1) complete_one(k,group_tags[k],32'h10+k);
            cpl_addr[31:0]=address; cpl_mask[3:0]=mask; cpl_data[31:0]=expected_data;
            @(posedge clk); #1; clear_inputs();
            if (duplicate) begin
                // The last completion lane wins for both payload and predicate.
                complete_one(0,saved_store_tag,0);
                cpl_addr[31:0]=expected_exit ? 32'h80000004 : 32'h80000000;
                cpl_mask[3:0]=4'hf; cpl_data[31:0]=32'hbad;
                complete_one(BE_WIDTH-1,saved_store_tag,0);
                cpl_addr[(BE_WIDTH-1)*32 +: 32]=address;
                cpl_mask[(BE_WIDTH-1)*4 +: 4]=mask;
                cpl_data[(BE_WIDTH-1)*32 +: 32]=expected_data;
                @(posedge clk); #1; clear_inputs();
                duplicate_tests=duplicate_tests+1;
            end
            #1;
            require(store_valid===1'b1 && store_addr===address && store_tag===saved_store_tag,
                    "original store payload and tag stay visible");
            require(commit_valid===0 && halted===0 && error===0,"no retirement before store admission");
            repeat(2) begin @(posedge clk); #1;
                require(commit_valid===0 && halted===0,"store backpressure cannot terminate");
            end
            store_ready=1; @(posedge clk); #1; store_ready=0;
            require(commit_valid[0]===((BUFFERED!=0) && !expected_exit),
                    "MMIO waits for ack; ordinary buffered store may retire after admission");
            // Flip a generation bit, leaving slot and tag-valid bits intact.
            store_ack_valid=1; store_ack_tag=saved_store_tag ^ (1 << (3+SLOT_W));
            @(posedge clk); #1; clear_inputs();
            require(commit_valid[0]===((BUFFERED!=0) && !expected_exit),"wrong generation ack ignored");
            require(halted===0 && error===0,"wrong ack cannot halt or fault"); wrong_acks=wrong_acks+1;
            store_ack_valid=1; store_ack_tag=saved_store_tag;
            @(posedge clk); #1; clear_inputs();
            require(commit_valid[0]===1'b1,"correct ack exposes retirement");
            if(expected_exit) begin
                require(commit_valid===1,"MMIO terminal event suppresses younger commit lanes");
                terminal_prefixes=terminal_prefixes+1;
            end else require(commit_valid==={BE_WIDTH{1'b1}},"nonterminal store allows younger ready lanes");
            repeat(2) begin @(posedge clk); #1;
                require(halted===0 && head===position && occupancy===BE_WIDTH,
                        "retirement backpressure preserves architectural state");
            end
            commit_ready=1; @(posedge clk); #1;
            require(halted===expected_exit && error===0,"exact MMIO word classification");
            if(expected_exit) begin
                require(return_value===expected_data,"exit result comes from store data");
                require(occupancy===BE_WIDTH-1,"younger instructions remain unretired after exit");
                true_exits=true_exits+1;
            end else require(occupancy===0 && return_value===0,"ordinary/partial writes do not terminate");
            if(address==32'h80000000 && mask!=4'hf) partial_writes=partial_writes+1;
            if(position==ROB_ENTRIES-1) head_boundary_tests=head_boundary_tests+1;
            tests=tests+1;
        end
    endtask
    initial begin
        reset=1; clear_inputs(); commit_ready=1; store_ready=0;
        tests=0; true_exits=0; partial_writes=0; wrong_acks=0; terminal_prefixes=0;
        duplicate_tests=0; head_boundary_tests=0;
        for(position=0;position<ROB_ENTRIES;position=position+ROB_ENTRIES-1) begin
            for(mask_number=0;mask_number<16;mask_number=mask_number+1)
                run_case(32'h80000000,mask_number[3:0],mask_number==15,0);
            run_case(32'h80000004,4'hf,0,0);
            run_case(32'h0,4'hf,0,0);
            if(BE_WIDTH>1) begin
                run_case(32'h80000000,4'hf,1,1);
                run_case(32'h80000004,4'hf,0,1);
            end
        end
        require(tests==((BE_WIDTH>1)?40:36),"complete directed case matrix");
        require(partial_writes==30 && wrong_acks==tests,"all strobes and wrong ack coverage");
        require(true_exits==((BE_WIDTH>1)?4:2) && terminal_prefixes==true_exits,"real word exits exercised");
        $display("PASS MMIO tests=%0d exits=%0d partial=%0d wrong_ack=%0d duplicates=%0d boundary=%0d",
                 tests,true_exits,partial_writes,wrong_acks,duplicate_tests,head_boundary_tests);
        $finish(0);
    end
endmodule
'''


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    assert not out.exists()
    snapshot = out/'source_snapshot'
    files = {snapshot/'original.v': candidate/'baseline/rv32_rob.v',
             snapshot/'candidate.v': candidate/'rtl/backend/rv32_rob.v',
             snapshot/'original_tb.v': ROOT/'tb/unit/rv32_rob_tb.v',
             snapshot/'rtl/rv32im_defs.vh': ROOT/'rtl/rv32im_defs.vh',
             snapshot/'rtl/common/rv32_control_register_bank.v': ROOT/'rtl/common/rv32_control_register_bank.v',
             snapshot/'rtl/common/rv32_asap7_fanout.v': ROOT/'rtl/common/rv32_asap7_fanout.v',
             snapshot/Path(__file__).name: Path(__file__).resolve()}
    hashes = {}
    for target, source in files.items():
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
        hashes[str(source)], hashes[str(target)] = sha(source), sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    binaries = [suite/'bin/iverilog.exe', suite/'bin/vvp.exe']
    hashes.update({str(p):sha(p) for p in binaries})
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    prefix = (snapshot/'original_tb.v').read_text().split('    initial begin\n        reset = 1;',1)[0]
    assert prefix.endswith('    endtask\n')
    prefix = prefix.replace('    parameter integer BE_WIDTH = 1,',
                            '    parameter integer BUFFERED = 0,\n    parameter integer BE_WIDTH = 1,')
    prefix = prefix.replace('.STORE_BUFFERED_RETIRE(0)', '.STORE_BUFFERED_RETIRE(BUFFERED)')
    report = dict(status='RUNNING', input_sha256=hashes, results=[], proves_whole_cpu=False,
                  checks_independent_expected_behavior=True, hierarchical_state_injection=False)
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    configurations = [(1,8,0,0),(1,8,1,1),(2,8,0,1),(2,8,1,0),
                      (4,8,0,0),(4,8,1,1),(4,64,0,1),(4,64,1,1)]
    for width, depth, buffered, bank in configurations:
        for mode in (-1,0,1):
            stem = f'be{width}_rob{depth}_sb{buffered}_bank{bank}_mode{mode}'
            tb = out/(stem+'.v')
            code = prefix
            if mode >= 0:
                code = code.replace('.BE_WIDTH(BE_WIDTH)', f'.MMIO_PREDECODE({mode}), .BE_WIDTH(BE_WIDTH)',1)
            tb.write_text(code+BODY)
            hashes[str(tb)] = sha(tb)
            params = dict(BE_WIDTH=width, ROB_ENTRIES=depth, BUFFERED=buffered, COMMIT_BANKED_READ=bank)
            command = [str(binaries[0]),'-g2012','-I',str(snapshot/'rtl'),'-s','rv32_rob_tb']
            command += [v for k,n in params.items() for v in ('-P',f'rv32_rob_tb.{k}={n}')]
            executable = out/(stem+'.vvp')
            command += ['-o',str(executable),str(snapshot/('original.v' if mode==-1 else 'candidate.v')),str(tb),
                        str(snapshot/'rtl/common/rv32_control_register_bank.v'),str(snapshot/'rtl/common/rv32_asap7_fanout.v')]
            report['active_case']=stem; save()
            for suffix, cmd in [('compile',command),('simulation',[str(binaries[1]),'-N',str(executable)])]:
                log = out/(stem+'.'+suffix+'.log')
                with log.open('w') as stream:
                    p = subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT)
                if p.returncode:
                    report.update(status='FAILED',failure_log=str(log)); save()
                    raise SystemExit('Directed MMIO validation failed: '+str(log))
                hashes[str(log)] = sha(log)
            text = log.read_text()
            found = re.search(r'PASS MMIO tests=(\d+) exits=(\d+) partial=(\d+) wrong_ack=(\d+) duplicates=(\d+) boundary=(\d+)',text)
            assert found and not re.search('FAIL|FATAL|ERROR',text)
            values = dict(zip(('tests','exits','partial','wrong_ack','duplicates','boundary'),map(int,found.groups())))
            report['results'].append(dict(status='PASS',parameters=params,mode=mode,**values));save()
            print('PASS '+stem, flush=True)
    for name, expected in hashes.items(): assert sha(name)==expected, name
    report.update(status='COMPLETE', active_case=None,
                  total_cases=sum(r['tests'] for r in report['results']),
                  total_true_exits=sum(r['exits'] for r in report['results']));save()
    print(json.dumps({k:report[k] for k in ('status','total_cases','total_true_exits')}))


if __name__ == '__main__':
    main()
