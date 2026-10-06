"""Check ordinary ADDI255 and explicit legacy fetch behavior, plus old protocols."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    source,out=args.source_root.resolve(),args.outdir.resolve()
    assert not out.exists()
    out.mkdir(parents=True)
    names=['rtl/frontend/rv32_fetch_frontend.v','rtl/predictor/rv32_banked_predictor.v',
           'rtl/predictor/rv32_branch_predictor.v','rtl/rv32im_defs.vh',
           'tb/unit/rv32_fetch_frontend_tb.v','tb/unit/rv32_banked_predictor_tb.v',
           'tb/unit/rv32_frontend_legal_addi_tb.v','tb/unit/rv32_indexed_history_predictor_tb.v',
           'tb/unit/rv32_predictor_legal_addi_tb.v']
    snapshot=out/'source_snapshot';hashes={}
    for name in names:
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
        hashes[str(source/name)]=sha(source/name);hashes[str(target)]=sha(target)
    hashes[str(Path(__file__))]=sha(__file__)
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env=dict(os.environ);env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    bins={n:suite/'bin'/(n+'.exe') for n in ['iverilog','vvp']}
    for path in bins.values():hashes[str(path)]=sha(path)
    report=dict(status='RUNNING',results=[],input_sha256=hashes,whole_cpu_claim=False)
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def case(name,top,params,rtl):
        for path,value in hashes.items():assert sha(path)==value
        command=[str(bins['iverilog']),'-g2012','-I',str(snapshot/'rtl'),'-s',top,'-o',str(out/(name+'.vvp'))]
        command += [f'-P{top}.{k}={v}' for k,v in params.items()]
        command += [str(snapshot/n) for n in rtl]+[str(snapshot/'tb/unit'/(top+'.v'))]
        for phase,cmd in [('compile',command),('simulate',[str(bins['vvp']),'-N',str(out/(name+'.vvp'))])]:
            run=subprocess.run(cmd,env=env,cwd=source,text=True,capture_output=True)
            log=out/(name+'.'+phase+'.log');log.write_text(run.stdout+run.stderr)
            if run.returncode or re.search(r'FAIL|FATAL|ERROR',run.stdout+run.stderr):
                report.update(status='FAILED',failure_log=str(log));save();raise SystemExit(str(log))
            if phase=='simulate':assert 'PASS:' in run.stdout
        report['results'].append(dict(name=name,status='PASS',parameters=params,log_sha256=sha(log)))
        save();print('PASS '+name,flush=True)
    for width in (1,2,4):
        for meta in (0,1):
            case(f'frontend_w{width}_meta{meta}','rv32_fetch_frontend_tb',dict(FE_WIDTH=width,PREDICTOR_META=meta),['rtl/frontend/rv32_fetch_frontend.v'])
            for legacy in (0,1):
                case(f'addi255_w{width}_meta{meta}_legacy{legacy}','rv32_frontend_legal_addi_tb',
                     dict(WIDTH=width,META=meta,LEGACY=legacy),['rtl/frontend/rv32_fetch_frontend.v'])
        # The replicated-reference TB predates history mode and leaves its
        # history/training inputs floating. Use the independent model TB for 2.
        for mode in (0,1):
            case(f'predictor_w{width}_mode{mode}','rv32_banked_predictor_tb',dict(WIDTH=width,DIRECT_BRANCH_TARGET=mode),
                 ['rtl/predictor/rv32_banked_predictor.v','rtl/predictor/rv32_branch_predictor.v'])
        for bits in (1,4,6):
            case(f'predictor_w{width}_history{bits}','rv32_indexed_history_predictor_tb',
                 dict(WIDTH=width,HISTORY_BITS=bits),
                 ['rtl/predictor/rv32_banked_predictor.v','rtl/predictor/rv32_branch_predictor.v'])
        for legacy in (0,1):
            case(f'predictor_addi_w{width}_legacy{legacy}','rv32_predictor_legal_addi_tb',
                 dict(WIDTH=width,LEGACY=legacy),
                 ['rtl/predictor/rv32_banked_predictor.v','rtl/predictor/rv32_branch_predictor.v'])
    for path,value in hashes.items():assert sha(path)==value
    assert len(report['results']) == 39
    report['status']='COMPLETE';save();print('COMPLETE39 frontend/legacy/predictor protocol configurations',flush=True)


if __name__=='__main__':main()
