"""Independent transaction scoreboards for the two registered CPU boundaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(root, out):
    assert not out.exists()
    out.mkdir(parents=True)
    runtime = root/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = os.environ | {'PATH':str(runtime/'bin')+os.pathsep+str(runtime/'lib')+os.pathsep+os.environ['PATH']}
    rng = random.Random(8102026)
    tests = []
    for lanes in (1,2,4):
        queue = []
        seq = 1
        lines = []
        for cycle in range(1200):
            reset = cycle == 0 or cycle % 197 == 0
            flush = cycle % 43 == 0
            incount = lanes if cycle % 7 < 4 else rng.randrange(lanes+1)
            outcount = lanes if cycle % 7 < 4 else rng.randrange(lanes+1)
            valid = (1<<incount)-1
            ready = (1<<outcount)-1
            incoming = list(range(seq,seq+lanes))
            seq += lanes
            active = not reset and not flush
            consumed = min(outcount,len(queue)) if active else 0
            capacity = lanes-len(queue)+consumed
            input_ready_count = min(capacity,incount+1) if active else 0
            expected_ready = (1<<input_ready_count)-1
            expected_valid = (1<<len(queue))-1 if active else 0
            mask = (1<<(len(queue)*16))-1 if active else 0
            pack = lambda values: sum(x<<(16*i) for i,x in enumerate(values))
            lines.append(f"check({int(reset)},{int(flush)},{valid},{ready},{lanes*16}'h{pack(incoming):x},{expected_ready},{expected_valid},{lanes*16}'h{pack(queue):x},{lanes*16}'h{mask:x});")
            queue = [] if not active else queue[consumed:]+incoming[:min(capacity,incount)]
        tb = f'''module tb;
localparam L={lanes}, W=L*16;
reg clk=0, reset, flush; reg [L-1:0] vi,ri; reg [W-1:0] di;
wire [L-1:0] vo,ro; wire [W-1:0] dout;
rv32_decode_bundle_register #(.LANES(L),.PAYLOAD_WIDTH(16)) dut(clk,reset,flush,vi,ro,di,vo,ri,dout);
integer count=0;
task check(input rst, fl, input [L-1:0] iv,ir,input [W-1:0] id,
 input [L-1:0] er,ev,input [W-1:0] ed,mask);
begin clk=0;reset=rst;flush=fl;vi=iv;ri=ir;di=id;#2;
if(ro!==er || vo!==ev || (dout & mask)!==(ed & mask)) begin
$display("decode L=%0d vector=%0d ready=%h/%h valid=%h/%h data=%h/%h",L,count,ro,er,vo,ev,dout,ed);$fatal(1);end
clk=1;#2;count=count+1;end endtask
initial begin
{chr(10).join(lines)}
$display("PASS decode lanes=%0d vectors=%0d",L,count);$finish;end
endmodule
'''
        tests.append((f'decode{lanes}',tb,'rtl/cpu_core.v'))
    for entries in (8,64):
        sw = (entries-1).bit_length()
        tw = sw+3+8
        occupied = False
        saved_tag = saved_data = 0
        lines = []
        for cycle in range(2400):
            reset = cycle == 0 or cycle % 397 == 0
            flush = cycle % 61 == 0
            recovery = cycle % 11 == 0
            vi,ri,eligible = (int(rng.randrange(4)!=0) for _ in range(3))
            head = rng.randrange(entries)
            target = (rng.randrange(entries)<<3)|(rng.randrange(256)<<(sw+3))|1
            tag = (rng.randrange(entries)<<3)|(rng.randrange(256)<<(sw+3))|1
            data = rng.getrandbits(32)
            active = not (reset or flush or recovery)
            er = int((not occupied or ri) and eligible and active)
            ev = int(occupied and active)
            lines.append(f"check({int(reset)},{int(flush)},{int(recovery)},{head},{tw}'h{target:x},{vi},{ri},{eligible},{tw}'h{tag:x},32'h{data:x},{er},{ev},32'h{saved_data:x});")
            if reset or flush:
                occupied=False; saved_tag=saved_data=0
            elif recovery:
                old_age = (((saved_tag>>3)&(entries-1))-head)%entries
                target_age = (((target>>3)&(entries-1))-head)%entries
                if occupied and old_age>=target_age: occupied=False
            elif er and vi:
                occupied=True;saved_tag=tag;saved_data=data
            elif ev and ri: occupied=False
        tb = f'''module tb;
localparam SW={sw}, TW={tw};
reg clk=0,reset,flush,recovery,vi,ri,eligible;reg [SW-1:0] head;
reg [TW-1:0] target,tag;reg [31:0] data;wire vo,ro;wire [31:0] dout;
rv32_issue_pipeline_slot #(.PAYLOAD_WIDTH(32),.TAG_WIDTH(TW),.ROB_ENTRIES({entries})) dut(
clk,reset,flush,recovery,head,target,vi,eligible,ro,data,tag,vo,ri,dout);
integer count=0;
task check(input rst,fl,rec,input [SW-1:0] hd,input [TW-1:0] trg,
input iv,ir,elig,input [TW-1:0] itag,input [31:0] id,input er,ev,input [31:0] ed);
begin clk=0;reset=rst;flush=fl;recovery=rec;head=hd;target=trg;vi=iv;ri=ir;eligible=elig;tag=itag;data=id;#2;
if(ro!==er || vo!==ev || (ev && dout!==ed)) begin
$display("issue ROB={entries} vector=%0d ready=%h/%h valid=%h/%h data=%h/%h",count,ro,er,vo,ev,dout,ed);$fatal(1);end
clk=1;#2;count=count+1;end endtask
initial begin
{chr(10).join(lines)}
$display("PASS issue ROB={entries} vectors=%0d",count);$finish;end
endmodule
'''
        tests.append((f'issue{entries}',tb,'rtl/backend/rv32_backend_joint.v'))
    hashes = {str(Path(__file__).resolve()):sha(__file__)}
    results = []
    for name,tb,source in tests:
        path=out/(name+'.v');path.write_text(tb,encoding='utf-8')
        exe=out/(name+'.vvp')
        command=[str(runtime/'bin/iverilog.exe'),'-g2012','-s','tb','-I',str(root/'rtl'),'-o',str(exe),str(path),str(root/source)]
        result=subprocess.run(command,env=env,text=True,capture_output=True)
        (out/(name+'.compile.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        assert result.returncode==0,result.stderr
        result=subprocess.run([str(runtime/'bin/vvp.exe'),str(exe)],env=env,text=True,capture_output=True)
        (out/(name+'.run.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        assert result.returncode==0 and 'PASS' in result.stdout,result.stdout+result.stderr
        print(result.stdout.strip(),flush=True)
        hashes.update({str(p.resolve()):sha(p) for p in (path,root/source,exe)})
        results.append(dict(name=name,status='PASS',vectors=1200 if name.startswith('decode') else 2400))
    report=dict(status='COMPLETE',results=results,vectors=sum(r['vectors'] for r in results),
                source_root=str(root.resolve()),input_sha256=hashes,
                scope='Registered latency, ordered prefix refill, stalls, reset, flush, per-lane eligibility and modular ROB recovery; finite simulation, not formal ISA proof')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.source,a.out)
