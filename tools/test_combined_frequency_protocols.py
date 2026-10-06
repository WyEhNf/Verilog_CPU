"""One final protocol batch for the fully integrated frequency candidate.

No parameter sweep: the changed interfaces are exercised at their selected
configuration, plus the existing independent pipeline transaction scoreboards.
"""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
from combined_frequency_transform import sha, replace

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=a.source.resolve();out=a.out.resolve()
    assert not out.exists();out.mkdir(parents=True)
    runtime=root/'.deps/oss-cad-suite-install/oss-cad-suite'
    env=os.environ | {'PATH':str(runtime/'bin')+os.pathsep+str(runtime/'lib')+os.pathsep+os.environ['PATH']}
    sources=[(root/'verilog'/s.strip()).resolve() for s in (root/'verilog/filelist.f').read_text().splitlines() if s.strip() and not s.strip().startswith('#')]
    sources.append(root/'.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv')
    sources.append(ROOT/'tb/models/rv32im_memory_model.v')
    inputs={str(s):sha(s) for s in sources}
    inputs[str(Path(__file__).resolve())]=sha(__file__)
    cases=[]
    for name in ('rv32_dcache_sram_tb','rv32_dcache_hash_tb'):
        p=ROOT/'tb/unit'/(name+'.v');s=p.read_text();inputs[str(p)]=sha(p)
        s=replace(s,'rv32_dcache_nonblocking #(', 'rv32_dcache_nonblocking #(.LOCAL_SRAM_COMMANDS(1), .LOCAL_ACTION_DECODE(1), ')
        params=dict(TAG_SRAM=1,STATIC_UPDATES=2,REGISTERED_INDEX=1,LOCAL_METADATA_QUERY=1,CACHE_WAYS=2)
        params.update(dict(MERGE_DELAY=16) if 'sram' in name else dict(CACHE_LINES=1024,INDEX_HASH=1,PREFETCH=1))
        cases.append((name,s,params))
    p=ROOT/'tb/unit/rv32_fetch_frontend_tb.v';s=p.read_text();inputs[str(p)]=sha(p)
    s=replace(s,'rv32_fetch_frontend #(', 'rv32_fetch_frontend #(.QUEUE_PAYLOAD_BANKS(1), .NARROW_OCCUPANCY(1), .LEGACY_SENTINEL_HALT(1), ')
    cases.append(('rv32_fetch_frontend_tb',s,dict(FE_WIDTH=4,PREDICTOR_META=1)))
    p=Path('F:/CPU2026Candidates/icache_mshr_state_banks_20261003/tb/unit/rv32_icache_sram_tb.v')
    inputs[str(p)]=sha(p)
    cases.append(('rv32_icache_sram_tb',p.read_text(),dict(LINES=128,WAYS=2,MSHRS=8,PROTECT=1)))
    p=ROOT/'tb/unit/rv32_rob_tb.v';s=p.read_text();inputs[str(p)]=sha(p)
    s=replace(s,'rv32_rob #(', 'rv32_rob #(.MMIO_PREDECODE(1), ')
    cases.append(('rv32_rob_tb',s,dict(BE_WIDTH=4,ROB_ENTRIES=64,COMMIT_BANKED_READ=1,ALLOC_BANKED_WRITE=1)))
    results=[]
    for name,code,params in cases:
        tb=out/(name+'.v');tb.write_text(code,encoding='utf-8')
        exe=out/(name+'.vvp')
        cmd=[str(runtime/'bin/iverilog.exe'),'-g2012','-s',name,'-I',str(root/'rtl'),'-o',str(exe)]
        cmd += ['-P'+name+'.'+k+'='+str(v) for k,v in params.items()]
        cmd += [str(tb)]+[str(s) for s in sources]
        for phase,command in [('compile',cmd),('run',[str(runtime/'bin/vvp.exe'),'-N',str(exe)])]:
            r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=300)
            log=out/(name+'.'+phase+'.log');log.write_text(r.stdout+r.stderr,encoding='utf-8')
            assert r.returncode==0,(name,phase,r.stdout[-3000:],r.stderr[-3000:])
            if phase=='run':
                assert 'PASS' in r.stdout and not re.search(r'FAIL|FATAL|ERROR',r.stdout+r.stderr),(name,r.stdout[-3000:])
                print(name+': '+r.stdout.splitlines()[-1],flush=True)
            inputs[str(log)]=sha(log)
        inputs[str(tb)]=sha(tb);inputs[str(exe)]=sha(exe)
        results.append(dict(name=name,status='PASS',parameters=params))
    subprocess.run([sys.executable,str(ROOT/'tools/test_pipeline8_boundaries.py'),'--source',str(root),'--out',str(out/'pipeline_boundaries')],env=env,check=True)
    p=out/'pipeline_boundaries/report.json';b=json.loads(p.read_text());inputs[str(p)]=sha(p);inputs.update(b['input_sha256'])
    for p,h in inputs.items():assert sha(p)==h,p
    result=dict(status='COMPLETE',source_root=str(root),results=results,pipeline_vectors=b['vectors'],input_sha256=inputs,
                scope='One combined final protocol batch; no cycle-equivalence or formal ISA claim')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('COMPLETE combined protocol batch',flush=True)


if __name__=='__main__':main()
