"""Compare every original ALU output and test execution metadata retention."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    out=args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh ALU metadata test directory')
    candidate=args.candidate_root.resolve() if args.candidate_root else ROOT
    files=[Path('rtl/rv32i_alu.v'),Path('rtl/rv32im_defs.vh'),
           Path('tb/unit/rv32i_alu_metadata_tb.v'),Path(__file__).resolve().relative_to(ROOT),
           Path('tools/observe_course_perf.py')]
    hashes,origins={},{}
    for relative in files:
        original=candidate/relative if (candidate/relative).is_file() else ROOT/relative
        target=out/'source_snapshot'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target)
        hashes[str(target)]=sha(target)
        origins[relative.as_posix()]=dict(path=str(original),sha256=sha(original))
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env=dict(os.environ)
    env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    iv,vv=[suite/'bin'/name for name in ('iverilog.exe','vvp.exe')]
    hashes[str(iv)],hashes[str(vv)]=sha(iv),sha(vv)
    results=[]
    for shift in (0,1):
        image=out/f'shift{shift}.vvp'
        compile_log,sim_log=out/f'shift{shift}.compile.log',out/f'shift{shift}.simulation.log'
        command=[str(iv),'-g2012','-I',str(out/'source_snapshot/rtl'),'-s','rv32i_alu_metadata_tb',
            '-P',f'rv32i_alu_metadata_tb.SHIFT_IMPL={shift}','-o',str(image),
            str(out/'source_snapshot/rtl/rv32i_alu.v'),str(out/'source_snapshot/tb/unit/rv32i_alu_metadata_tb.v')]
        with compile_log.open('w') as stream:
            subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        with sim_log.open('w') as stream:
            subprocess.run([str(vv),'-N',str(image)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        text=sim_log.read_text()
        match=re.search(r'PASS: ALU metadata SHIFT_IMPL=(\d+) checks=(\d+) accepted=(\d+)',text)
        if not match or int(match[1])!=shift or int(match[2])<4000 or int(match[3])<100 or \
                re.search(r'FAIL|FATAL|ERROR',text):
            raise SystemExit('ALU metadata comparison/coverage failed: '+str(sim_log))
        results.append(dict(shift_impl=shift,status='PASS',checks=int(match[2]),accepted=int(match[3]),
            compile_log_sha256=sha(compile_log),simulation_log_sha256=sha(sim_log)))
        print(text.strip(),flush=True)
    for name,expected in hashes.items():
        if sha(Path(name))!=expected:
            raise SystemExit('Frozen ALU metadata input changed: '+name)
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE',results=results,input_sha256=hashes,
        compiled_origins=origins,scope='all original ALU output/ready fields at every checked cycle, '
        'metadata packet identity, backpressure, iterative shifts, stale-result priority and flush; '
        '4000 deterministic random cycles per shift implementation',proves_whole_cpu=False,
        claims_cpu_ppa=False),indent=2)+'\n')


if __name__=='__main__':
    main()
