"""Test both I-cache replacement policies against actual original SRAM.

64 original protocols cover line/way/MSHR geometry, epochs, errors and
backpressure.24 directed collisions cover correct replay of an evicted
pending hit, including current128line/8MSHR geometry. Not a CPU proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-root',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();candidate,out=a.candidate_root.resolve(),a.outdir.resolve()
    assert not out.exists();out.mkdir(parents=True)
    snapshot=out/'source_snapshot';hashes={}
    names=['rtl/cache/rv32_icache_nonblocking.v','rtl/rv32im_defs.vh',
           'tb/unit/rv32_icache_sram_tb.v','tb/unit/rv32_icache_refill_policy_tb.v',
           '.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv']
    for name in names:
        source=candidate/name if (candidate/name).exists() else ROOT/name
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        hashes[str(source)]=sha(source);hashes[str(target)]=sha(target)
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite';bins={n:suite/'bin'/(n+'.exe') for n in ('iverilog','vvp')}
    for path in [Path(__file__),*bins.values()]:hashes[str(path)]=sha(path)
    env=dict(os.environ);env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    report=dict(status='RUNNING',results=[],input_sha256=hashes,original_sram=True,
                policy_can_change_miss_count=True,no_cycle_equivalence_claim=True,not_a_cpu_result=True)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def check():
        for name,h in hashes.items():assert sha(name)==h,name
    def case(name,top,parameters):
        check();image=out/(name+'.vvp')
        command=[str(bins['iverilog']),'-g2012','-I',str(snapshot/'rtl'),'-s',top,'-o',str(image)]
        command += [f'-P{top}.{k}={v}' for k,v in parameters.items()]
        command += [str(snapshot/'rtl/cache/rv32_icache_nonblocking.v'),
                    str(snapshot/'.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'),
                    str(snapshot/'tb/unit'/(top+'.v'))]
        for phase,cmd in [('compile',command),('simulate',[str(bins['vvp']),'-N',str(image)])]:
            run=subprocess.run(cmd,env=env,cwd=snapshot,text=True,capture_output=True)
            log=out/(name+'.'+phase+'.log');log.write_text(run.stdout+run.stderr)
            if run.returncode or re.search('FAIL|FATAL|ERROR',run.stdout+run.stderr) or (phase=='simulate' and 'PASS:' not in run.stdout):
                report.update(status='FAILED',failure_log=str(log));save();raise SystemExit(str(log))
        report['results'].append(dict(name=name,status='PASS',parameters=parameters,log_sha256=sha(log)))
        check();save();print('PASS '+name,flush=True)
    for lines in (16,64,128,256):
        for protect in (0,1):
            for ways in (1,2):
                for mshrs in (2,4,8,16):
                    case(f'protocol_l{lines}_w{ways}_m{mshrs}_p{protect}','rv32_icache_sram_tb',
                         dict(LINES=lines,WAYS=ways,MSHRS=mshrs,PROTECT=protect))
            for mshrs in (2,8,16):
                case(f'collision_l{lines}_m{mshrs}_p{protect}','rv32_icache_refill_policy_tb',
                     dict(LINES=lines,MSHRS=mshrs,PROTECT=protect))
    assert len(report['results'])==88
    check();report['status']='COMPLETE';save();print('COMPLETE88 original SRAM protocols and pending-hit refill/replay collisions',flush=True)


if __name__=='__main__':main()
