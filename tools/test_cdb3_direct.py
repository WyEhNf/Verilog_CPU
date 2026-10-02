"""Exercise the existing direct completion network with4 issue lanes and3 CDBs.

The unchanged independent reference TB checks arbitration, all payloads,
backpressure, live filtering and flush across1/2/6/9 producers. This is an
additional parameter configuration, not a wholeCPU correctness or IPC claim.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=Path('F:/CPU2026Proofs/cdb3_direct_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    assert not OUT.exists();OUT.mkdir(parents=True)
    snapshot=OUT/'source_snapshot';hashes={}
    names=['rtl/backend/rv32_completion_network.v','rtl/rv32im_defs.vh','tb/unit/rv32_completion_direct_tb.v']
    for name in names:
        path=snapshot/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,path)
        hashes[str(ROOT/name)]=sha(ROOT/name);hashes[str(path)]=sha(path)
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite';env=dict(os.environ)
    env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    bins={n:suite/'bin'/(n+'.exe') for n in ('iverilog','vvp')}
    for path in [Path(__file__),*bins.values()]:hashes[str(path)]=sha(path)
    report=dict(status='RUNNING',results=[],input_sha256=hashes,BE_WIDTH=4,CDB_WIDTH=3,BYPASS=2,whole_cpu_claim=False)
    def save():(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    for count in (1,2,6,9):
        stem=f'be4_cdb3_sources{count}';image=OUT/(stem+'.vvp')
        compile_command=[str(bins['iverilog']),'-g2012','-I',str(snapshot/'rtl'),'-s','rv32_completion_direct_tb',
                         '-Prv32_completion_direct_tb.BE_WIDTH=4','-Prv32_completion_direct_tb.CDB_WIDTH=3',
                         f'-Prv32_completion_direct_tb.SOURCES={count}','-o',str(image),
                         str(snapshot/names[0]),str(snapshot/names[2])]
        for phase,command in [('compile',compile_command),('simulate',[str(bins['vvp']),'-N',str(image)])]:
            run=subprocess.run(command,env=env,cwd=snapshot,text=True,capture_output=True)
            log=OUT/(stem+'.'+phase+'.log');log.write_text(run.stdout+run.stderr)
            if run.returncode or re.search('FAIL|FATAL|ERROR',run.stdout+run.stderr) or (phase=='simulate' and 'PASS: direct CDB' not in run.stdout):
                report.update(status='FAILED',failure_log=str(log));save();raise SystemExit(str(log))
        report['results'].append(dict(status='PASS',sources=count,log_sha256=sha(log)))
        for name,h in hashes.items():assert sha(name)==h,name
        save();print(run.stdout.strip(),flush=True)
    report['status']='COMPLETE';save()


if __name__=='__main__':main()
