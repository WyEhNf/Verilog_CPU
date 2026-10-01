"""Frozen backend matrix for the optional RS/ALU metadata storage layout.

A candidate root may override specific project files before integration. All
compiled files are frozen; the report identifies their actual origin. This
is lane-zero protocol evidence, not a native benchmark or a CPU PPA result.
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
    parser.add_argument('--candidate-root', type=Path)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh metadata protocol directory')
    candidate = args.candidate_root.resolve() if args.candidate_root else ROOT
    filelist = ROOT/'rtl/filelist.f'
    relative_sources = [Path(line.split('#',1)[0].strip()) for line in filelist.read_text().splitlines()
                        if line.split('#',1)[0].strip()]
    ram = Path('.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv')
    testbench = Path('tb/unit/rv32_backend_joint_tb.v')
    relative_inputs = [*relative_sources,ram,Path('rtl/rv32im_defs.vh'),testbench,
                       Path('rtl/filelist.f'),Path('tools/observe_course_perf.py'),
                       Path(__file__).resolve().relative_to(ROOT)]
    snapshot = out/'source_snapshot'
    inputs, origins = {}, {}
    for relative in relative_inputs:
        original = candidate/relative if (candidate/relative).is_file() else ROOT/relative
        destination = snapshot/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,destination)
        inputs[str(destination)] = sha(destination)
        origins[relative.as_posix()] = dict(path=str(original),sha256=sha(original))
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    iv,vv = [suite/'bin'/name for name in ('iverilog.exe','vvp.exe')]
    inputs[str(iv)],inputs[str(vv)] = sha(iv),sha(vv)
    configurations = [dict(BE_WIDTH=w,CHECKPOINT_IMPL=1,RAT_RECOVERY_IMPL=r,EARLY_STORE_ADDRESS=e,
        COMPLETION_BYPASS=c,STORE_BUFFERED_RETIRE=s,PREDICTOR_META=p,RS_ISSUE_METADATA=m)
        for w in (1,2,4) for r in (0,1) for e in (0,1,2) for c in (0,2)
        for s in (0,1) for p in (0,1) for m in (0,1)]
    configurations += [dict(BE_WIDTH=w,CHECKPOINT_IMPL=0,RAT_RECOVERY_IMPL=1,EARLY_STORE_ADDRESS=e,
        COMPLETION_BYPASS=0,STORE_BUFFERED_RETIRE=s,PREDICTOR_META=0,RS_ISSUE_METADATA=m)
        for w in (1,2,4) for e in (0,1,2) for s in (0,1) for m in (0,1)]
    configurations += [dict(BE_WIDTH=w,CHECKPOINT_IMPL=1,RAT_RECOVERY_IMPL=1,EARLY_STORE_ADDRESS=e,
        COMPLETION_BYPASS=0,STORE_BUFFERED_RETIRE=0,PREDICTOR_META=0,RS_ISSUE_METADATA=m,
        SHARED_ADDRESS_DIRECTED=1) for w in (1,2,4) for e in (0,1,2) for m in (0,1)]
    if args.smoke:
        configurations = [dict(BE_WIDTH=w,CHECKPOINT_IMPL=1,RAT_RECOVERY_IMPL=1,
            EARLY_STORE_ADDRESS=2,COMPLETION_BYPASS=0,STORE_BUFFERED_RETIRE=0,
            PREDICTOR_META=1,RS_ISSUE_METADATA=m,SHARED_ADDRESS_DIRECTED=1)
            for w in (1,2,4) for m in (0,1)]
    results = []
    for config in configurations:
        name = '_'.join(k.lower()+str(v) for k,v in config.items())
        image = out/(name+'.vvp')
        cmd = [str(iv),'-g2012','-I',str(snapshot/'rtl'),'-s','rv32_backend_joint_tb']
        cmd += [value for k,v in config.items() for value in ('-P',f'rv32_backend_joint_tb.{k}={v}')]
        cmd += ['-o',str(image),*[str(snapshot/p) for p in [*relative_sources,ram,testbench]]]
        compile_log,sim_log = out/(name+'.compile.log'),out/(name+'.simulation.log')
        with compile_log.open('w') as stream:
            subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        with sim_log.open('w') as stream:
            subprocess.run([str(vv),'-N',str(image)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        text = sim_log.read_text()
        marker = re.search(r'PASS: RS metadata scoreboard mode=(\d+) issues=(\d+) branches=(\d+)',text)
        if not marker or tuple(map(int,marker.groups()))[0]!=config['RS_ISSUE_METADATA'] or \
                min(map(int,marker.groups()[1:]))<1 or re.search(r'FAIL|ERROR|FATAL',text) or \
                f'PASS: B-09 backend joint BE_WIDTH={config["BE_WIDTH"]}' not in text:
            raise SystemExit('Metadata protocol/scoreboard failed: '+str(sim_log))
        if config.get('SHARED_ADDRESS_DIRECTED') and 'PASS: shared store-address backend directed' not in text:
            raise SystemExit('Shared-AGU directed checks did not execute')
        results.append(dict(name=name,status='PASS',parameters=config,
            issue_metadata_checks=int(marker[2]),branch_metadata_checks=int(marker[3]),
            compile_log_sha256=sha(compile_log),simulation_log_sha256=sha(sim_log)))
        print('PASS '+name,flush=True)
    expected_cases = 6 if args.smoke else 342
    if len(results)!=expected_cases:
        raise SystemExit('Incomplete metadata matrix')
    for path,expected in inputs.items():
        if sha(Path(path))!=expected:
            raise SystemExit('Frozen metadata input changed: '+path)
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE',total_cases=len(results),
        candidate_root=str(candidate),compiled_origins=origins,input_sha256=inputs,results=results,
        scope='lane-zero RAW/WAR/WAW, completion, recovery and shared-store-address protocols; '
              'dispatch full-tag scoreboards for issue and branch prediction metadata',
        proves_whole_cpu=False,claims_cpu_ppa=False),indent=2)+'\n')
    print(f'COMPLETE: {len(results)} RS/ALU metadata protocol configurations',flush=True)


if __name__=='__main__':
    main()
