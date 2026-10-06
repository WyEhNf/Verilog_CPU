"""Check the real shared store-address selector against an independent reference.

Random four-state simulation and unrestricted combinational SAT, not a CPU
PPA result or full backend proof. Frozen inputs and geometry are reported.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from observe_course_perf import ROOT, sha


def quote(path):
    return '"'+path.resolve().as_posix()+'"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh proof/test directory')
    sources = [ROOT/'rtl/backend/rv32_store_address_select.v',
               ROOT/'tb/unit/rv32_store_address_select_fixture.v', Path(__file__).resolve(),
               ROOT/'tools/observe_course_perf.py']
    inputs, frozen = {}, []
    for path in sources:
        target = out/'source_snapshot'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path,target)
        frozen.append(target)
        inputs[str(path)] = sha(path)
        inputs[str(target)] = sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    iv, vv, yy = [suite/'bin'/name for name in ('iverilog.exe','vvp.exe','yosys.exe')]
    for path in (iv,vv,yy):
        inputs[str(path)] = sha(path)
    results = []
    for lsq, rs in ((1,1),(4,4),(8,8),(16,16),(32,16)):
        name = f'lsq{lsq}_rs{rs}'
        print('START '+name,flush=True)
        image = out/(name+'.vvp')
        command = [str(iv),'-g2012','-s','rv32_store_address_select_tb',
                   '-P',f'rv32_store_address_select_tb.LSQ_ENTRIES={lsq}',
                   '-P',f'rv32_store_address_select_tb.RS_ENTRIES={rs}',
                   '-o',str(image),str(frozen[0]),str(frozen[1])]
        with (out/(name+'.compile.log')).open('w') as stream:
            subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        run = subprocess.run([str(vv),'-N',str(image)],env=env,text=True,capture_output=True)
        (out/(name+'.simulation.log')).write_text(run.stdout+run.stderr)
        if run.returncode or 'PASS: shared store-address selector' not in run.stdout or \
                any(word in run.stdout+run.stderr for word in ('FAIL','ERROR','FATAL')):
            raise SystemExit('Selector simulation failed: '+name)
        script, log = out/(name+'.ys'), out/(name+'.proof.log')
        commands = ['read_verilog -D SYNTHESIS '+quote(frozen[0])+' '+quote(frozen[1]),
                    f'chparam -set LSQ_ENTRIES {lsq} -set RS_ENTRIES {rs} rv32_store_address_select_miter',
                    'hierarchy -check -top rv32_store_address_select_miter','rename -top proof_top',
                    'prep -top proof_top -flatten','check -assert',
                    'sat -verify -prove equivalent_o 1 -show-inputs -show-outputs']
        script.write_text('\n'.join(commands)+'\n')
        with log.open('w') as stream:
            proof = subprocess.run([str(yy),'-T','-s',str(script)],env=env,stdout=stream,stderr=subprocess.STDOUT)
        text = log.read_text()
        if proof.returncode or 'SAT proof finished - no model found: SUCCESS!' not in text:
            raise SystemExit('Unrestricted selector equivalence NOT proven: '+str(log))
        results.append(dict(name=name,status='PROVEN',lsq_entries=lsq,rs_entries=rs,
                            tag_width=17,random_cases=2000,proof_log_sha256=sha(log),
                            simulation_log_sha256=sha(out/(name+'.simulation.log'))))
        print('PROVEN '+name,flush=True)
    for path,expected in inputs.items():
        if sha(Path(path))!=expected:
            raise SystemExit('Frozen input changed: '+path)
    (out/'report.json').write_text(json.dumps(dict(status='COMPLETE',input_sha256=inputs,results=results,
        scope='unrestricted combinational oldest-LSQ/first-RS selection equivalence plus 2000 random cases per geometry',
        proves_whole_backend=False,claims_cpu_ppa=False),indent=2)+'\n')
    print('COMPLETE: five shared store-address selector geometries',flush=True)


if __name__=='__main__':
    main()
