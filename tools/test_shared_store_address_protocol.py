"""Freeze and test the integrated shared store-address path, not a CPU PPA.

Twelve LSQ configurations cover disabled/enabled probing and admission.
Nine backend configurations contrast late-base wakeups in address modes
0/1/2 at issue widths 1/2/4. Native multi-lane suites remain required.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh protocol output directory')
    filelist = ROOT/'rtl/filelist.f'
    sources = [ROOT/x.split('#',1)[0].strip() for x in filelist.read_text().splitlines()
               if x.split('#',1)[0].strip()]
    ram = ROOT/'.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'
    lsq_tb, backend_tb = [ROOT/'tb/unit'/name for name in ('rv32_lsq_tb.v','rv32_backend_joint_tb.v')]
    inputs = [*sources,ram,filelist,ROOT/'rtl/rv32im_defs.vh',lsq_tb,backend_tb,
              Path(__file__).resolve(),ROOT/'tools/observe_course_perf.py']
    hashes = {}
    frozen = lambda p: out/'source_snapshot'/p.relative_to(ROOT)
    for source in inputs:
        target = frozen(source)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        hashes[str(target)] = sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    iv,vv = [suite/'bin'/name for name in ('iverilog.exe','vvp.exe')]
    hashes[str(iv)],hashes[str(vv)] = sha(iv),sha(vv)
    cases = [('lsq',dict(BE_WIDTH=w,STORE_ADMISSION_BYPASS=a,STORE_ADDRESS_PROBE=p))
             for w in (1,2,4) for a in (0,1) for p in (0,1)]
    cases += [('backend',dict(BE_WIDTH=w,EARLY_STORE_ADDRESS=e,RAT_RECOVERY_IMPL=1,
                              CHECKPOINT_IMPL=1,SHARED_ADDRESS_DIRECTED=1))
              for w in (1,2,4) for e in (0,1,2)]
    results = []
    for kind,params in cases:
        name = kind+'_'+'_'.join(k.lower()+str(v) for k,v in params.items())
        top = 'rv32_lsq_tb' if kind=='lsq' else 'rv32_backend_joint_tb'
        src = [ROOT/'rtl/backend/rv32_lsq.v',lsq_tb] if kind=='lsq' else [*sources,ram,backend_tb]
        image = out/(name+'.vvp')
        cmd = [str(iv),'-g2012','-I',str(out/'source_snapshot/rtl'),'-s',top]
        cmd += [value for k,v in params.items() for value in ('-P',f'{top}.{k}={v}')]
        cmd += ['-o',str(image),*[str(frozen(p)) for p in src]]
        compile_log,sim_log = out/(name+'.compile.log'),out/(name+'.simulation.log')
        with compile_log.open('w') as stream:
            subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        with sim_log.open('w') as stream:
            subprocess.run([str(vv),'-N',str(image)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        text = sim_log.read_text()
        marker = f'PASS: B-08 LSQ BE_WIDTH={params["BE_WIDTH"]}' if kind=='lsq' else \
                 f'PASS: B-09 backend joint BE_WIDTH={params["BE_WIDTH"]}'
        if marker not in text or re.search(r'FAIL|ERROR|FATAL',text):
            raise SystemExit('Protocol regression failed: '+str(sim_log))
        if kind=='backend' and 'PASS: shared store-address backend directed' not in text:
            raise SystemExit('Backend directed checks were not executed')
        if params.get('STORE_ADDRESS_PROBE') and 'PASS: shared store-address LSQ directed checks' not in text:
            raise SystemExit('LSQ directed checks were not executed')
        results.append(dict(name=name,status='PASS',parameters=params,
                            compile_log_sha256=sha(compile_log),simulation_log_sha256=sha(sim_log)))
        print('PASS '+name,flush=True)
    if len(results)!=21:
        raise SystemExit('Incomplete protocol matrix')
    for path,expected in hashes.items():
        if sha(Path(path))!=expected:
            raise SystemExit('Frozen protocol input changed: '+path)
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE',total_cases=len(results),
        input_sha256=hashes,results=results,scope='LSQ address/data ordering, byte/half/word masks, '
        'stale generations, same-edge ALU priority and recovery; backend lane-zero late-base '
        'wakeups, disjoint load release and retained store RS entry at BE1/2/4',
        proves_whole_cpu=False,claims_cpu_ppa=False),indent=2)+'\n')
    print('COMPLETE: 21 integrated shared store-address protocol configurations',flush=True)


if __name__=='__main__':
    main()
