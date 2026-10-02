"""Original frontend protocols and complete sequential equivalence of banks.

Keep every output, queue field and input behavior. No environment assumptions,
output masking, changed simulator model or excluded implementation state.
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


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def quote(path):
    return '"'+Path(path).resolve().as_posix()+'"'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    candidate,out=args.candidate_root.resolve(),args.outdir.resolve()
    assert not out.exists()
    snapshot=out/'source_snapshot';snapshot.mkdir(parents=True)
    origins={snapshot/'original.v':candidate/'baseline/rv32_fetch_frontend.v',
             snapshot/'candidate.v':candidate/'rtl/frontend/rv32_fetch_frontend.v',
             snapshot/'tb.v':candidate/'tb/unit/rv32_fetch_frontend_tb.v',
             snapshot/'rtl/rv32im_defs.vh':ROOT/'rtl/rv32im_defs.vh',
             snapshot/'test_frontend_payload_banks.py':Path(__file__)}
    hashes={}
    for target,source in origins.items():
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        hashes[str(source)]=sha(source);hashes[str(target)]=sha(target)
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env=dict(os.environ);env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    bins={n:suite/'bin'/(n+'.exe') for n in ['iverilog','vvp','yosys']}
    for path in bins.values():hashes[str(path)]=sha(path)
    report=dict(status='RUNNING',input_sha256=hashes,results=[],no_input_assumptions=True,
                proves_whole_cpu=False,no_outputs_or_state_fields_omitted=True)
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def verify():
        for path,value in hashes.items():assert sha(path)==value,'Changed proof input: '+path
    def run(command,path):
        verify()
        with path.open('w') as stream:
            completed=subprocess.run(command,cwd=snapshot,env=env,stdout=stream,stderr=subprocess.STDOUT)
        verify()
        if completed.returncode:
            report.update(status='FAILED',failure_log=str(path));save()
            raise SystemExit('Frontend validation failed: '+str(path))
    for width in (1,2,4):
        for metadata in (0,1):
            stem=f'protocol_fe{width}_meta{metadata}'
            image=out/(stem+'.vvp');log=out/(stem+'.simulation.log')
            run([str(bins['iverilog']),'-g2012','-I','rtl','-s','rv32_fetch_frontend_tb',
                 '-P',f'rv32_fetch_frontend_tb.FE_WIDTH={width}','-P',f'rv32_fetch_frontend_tb.PREDICTOR_META={metadata}',
                 '-o',str(image),str(snapshot/'candidate.v'),str(snapshot/'tb.v')],out/(stem+'.compile.log'))
            run([str(bins['vvp']),'-N',str(image)],log)
            text=log.read_text();assert f'PASS: A-04 frontend FE_WIDTH={width}' in text and not re.search('FAIL|FATAL|ERROR',text)
            report['results'].append(dict(status='PASS',phase='protocol',width=width,depth=8,metadata=metadata,log_sha256=sha(log)))
            save();print('PASS '+stem,flush=True)
    for width,depth,metadata in [(1,4,0),(2,8,0),(4,16,0),(4,16,1),(4,4,1),(4,32,0)]:
        stem=f'formal_fe{width}_fq{depth}_meta{metadata}'
        config=dict(FE_WIDTH=width,FQ_DEPTH=depth,EPOCH_WIDTH=4,PREDICTOR_META=metadata)
        params=' '.join(f'-set {key} {value}' for key,value in config.items())
        commands=[]
        for label,filename in [('gold','original.v'),('gate','candidate.v')]:
            commands += ['read_verilog -I rtl '+quote(snapshot/filename),
                'chparam '+params+(' -set QUEUE_PAYLOAD_BANKS 1' if label=='gate' else '')+' rv32_fetch_frontend',
                'hierarchy -check -top rv32_fetch_frontend','rename -top '+label,
                'proc','memory_map','setattr -mod -unset keep_hierarchy','flatten '+label,
                'opt_expr -keepdc','opt_clean','setattr -mod -unset top','design -stash '+label,'design -reset']
        prepared=out/(stem+'.prepared.json')
        commands += ['design -copy-from gold -as gold gold','design -copy-from gate -as gate gate',
                     'write_json '+quote(prepared),'equiv_make gold gate equiv','hierarchy -check -top equiv',
                     'check -assert','equiv_simple -short -seq 2','equiv_induct -seq 4','equiv_status -assert']
        script,log=out/(stem+'.ys'),out/(stem+'.log');script.write_text('\n'.join(commands)+'\n')
        report['active_case']=stem;save();print('START '+stem,flush=True)
        run([str(bins['yosys']),'-T','-s',str(script)],log)
        text=log.read_text();assert 'Equivalence successfully proven!' in text and 'ERROR:' not in text
        models=json.loads(prepared.read_text())['modules']
        schema=lambda m:{n:(v['direction'],len(v['bits'])) for n,v in m['ports'].items()}
        assert schema(models['gold'])==schema(models['gate'])
        state_names=[n for n in models['gold']['netnames'] if re.fullmatch(r'fq_\w+\[\d+\]',n)]
        assert state_names
        for name in state_names:
            assert name in models['gate']['netnames']
            assert len(models['gold']['netnames'][name]['bits'])==len(models['gate']['netnames'][name]['bits'])
        count=int(re.search(r'Found (\d+) \$equiv cells in equiv:',text)[1])
        report['results'].append(dict(status='PROVEN',phase='formal',parameters=config,equiv_cells=count,
                preserved_queue_state_aliases=len(state_names),prepared_sha256=sha(prepared),script_sha256=sha(script),log_sha256=sha(log)))
        save();print('PROVEN '+stem,flush=True)
    verify();report.update(status='COMPLETE',active_case=None);save()
    print('COMPLETE six original protocols and six complete frontend proofs including actual4/16',flush=True)


if __name__=='__main__':
    main()
