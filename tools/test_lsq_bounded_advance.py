"""Verify protocols and complete sequential LSQ after literal function SAT.

Retain every output and all memory fields, including public state aliases.
Do not assume legal input sequences, suppress outputs, or delete state fields.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"'+Path(path).resolve().as_posix()+'"'


def free_memory():
    class Memory(ctypes.Structure):
        _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
            (name,ctypes.c_ulonglong) for name in
            ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
    return memory.avail_phys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args = parser.parse_args()
    candidate,out = args.candidate_root.resolve(),args.outdir.resolve()
    assert not out.exists()
    literal_path = candidate/'literal_proof/report.json'
    literal = json.loads(literal_path.read_text())
    assert literal['status'] == 'COMPLETE' and len(literal['results']) == 8
    for path, expected in literal['input_sha256'].items():
        assert sha(path) == expected
    for row in literal['compiled_origins'].values():
        assert sha(row['path']) == row['sha256']
    snapshot = out/'source_snapshot'
    snapshot.mkdir(parents=True)
    origins = {snapshot/'original.v':candidate/'baseline/rv32_lsq.v',
               snapshot/'candidate.v':candidate/'rtl/backend/rv32_lsq.v',
               snapshot/'tb.v':candidate/'tb/unit/rv32_lsq_tb.v',
               snapshot/'rtl/rv32im_defs.vh':ROOT/'rtl/rv32im_defs.vh',
               snapshot/Path(__file__).name:Path(__file__).resolve()}
    hashes = {str(literal_path):sha(literal_path)}
    for target,source in origins.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        hashes[str(source)],hashes[str(target)] = sha(source),sha(target)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    bins = {n:suite/'bin'/(n+'.exe') for n in ('iverilog','vvp','yosys')}
    for path in bins.values(): hashes[str(path)] = sha(path)
    report = dict(status='RUNNING',input_sha256=hashes,results=[],no_input_assumptions=True,
                  proves_whole_cpu=False,no_outputs_or_state_fields_omitted=True)

    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')

    def verify_inputs():
        for path,expected in hashes.items(): assert sha(path) == expected,path

    def run(command,log):
        verify_inputs()
        with log.open('w') as stream:
            p = subprocess.run(command,cwd=snapshot,env=env,stdout=stream,stderr=subprocess.STDOUT)
        verify_inputs()
        if p.returncode:
            report.update(status='FAILED',failure_log=str(log));save()
            raise SystemExit('LSQ validation failed: '+str(log))

    for width in (1,2,4):
        for bypass in (0,1):
            for probe in (0,1):
                stem = f'protocol_be{width}_admit{bypass}_probe{probe}'
                params = dict(BE_WIDTH=width,STORE_ADMISSION_BYPASS=bypass,STORE_ADDRESS_PROBE=probe)
                image,log = out/(stem+'.vvp'),out/(stem+'.simulation.log')
                options = [x for k,v in params.items() for x in ('-P',f'rv32_lsq_tb.{k}={v}')]
                run([str(bins['iverilog']),'-g2012','-I','rtl','-s','rv32_lsq_tb',*options,
                     '-o',str(image),str(snapshot/'candidate.v'),str(snapshot/'tb.v')],out/(stem+'.compile.log'))
                run([str(bins['vvp']),'-N',str(image)],log)
                text = log.read_text()
                assert 'PASS: B-08' in text and not re.search('FAIL|FATAL|ERROR',text)
                report['results'].append(dict(status='PASS',phase='protocol',parameters=params,log_sha256=sha(log)))
                save();print('PASS '+stem,flush=True)
    cases = [(1,4,16,12,0,0,1),(2,8,32,16,0,0,1),(4,8,32,16,1,1,1),
             (4,2,8,12,0,1,1),(1,1,8,12,0,0,1),
             (4,16,64,17,0,1,1),(4,16,64,17,1,1,1),(2,8,32,16,0,0,0)]
    for width,depth,rob,tag,bypass,probe,direct in cases:
        stem = f'formal_be{width}_lsq{depth}_rob{rob}_tag{tag}_admit{bypass}_probe{probe}_direct{direct}'
        report['active_case'] = stem;report['phase'] = 'wait_memory';save()
        threshold = 8_192_000_000 if depth >= 16 else 6_144_000_000
        print('WAIT memory '+stem,flush=True)
        while free_memory() < threshold: time.sleep(30)
        params = dict(BE_WIDTH=width,LSQ_ENTRIES=depth,ROB_ENTRIES=rob,TAG_WIDTH=tag,
                      ROB_TAG_WIDTH=tag,STORE_ADMISSION_BYPASS=bypass,STORE_ADDRESS_PROBE=probe)
        settings = ' '.join(f'-set {k} {v}' for k,v in params.items())
        commands = []
        for label,filename in [('gold','original.v'),('gate','candidate.v')]:
            commands += ['read_verilog -I rtl '+quote(snapshot/filename),
                'chparam '+settings+(f' -set DIRECT_ADVANCE {direct}' if label=='gate' else '')+' rv32_lsq',
                'hierarchy -check -top rv32_lsq','rename -top '+label,'proc','memory_map',
                'opt_expr -keepdc','opt_clean','setattr -mod -unset top','design -stash '+label,'design -reset']
        prepared = out/(stem+'.prepared.json')
        commands += ['design -copy-from gold -as gold gold','design -copy-from gate -as gate gate',
            'write_json '+quote(prepared),'equiv_make gold gate equiv','hierarchy -check -top equiv',
            'check -assert','equiv_simple -short -seq 2','equiv_induct -seq 4','equiv_status -assert']
        script,log = out/(stem+'.ys'),out/(stem+'.log')
        script.write_text('\n'.join(commands)+'\n')
        report['phase']='formal';save();print('START '+stem,flush=True)
        run([str(bins['yosys']),'-T','-s',str(script)],log)
        text = log.read_text()
        assert 'Equivalence successfully proven!' in text and 'ERROR:' not in text
        models = json.loads(prepared.read_text())['modules']
        schema = lambda m:{n:(v['direction'],len(v['bits'])) for n,v in m['ports'].items()}
        assert schema(models['gold']) == schema(models['gate'])
        fields = [n for n in models['gold']['netnames'] if re.fullmatch(r'\w+_mem\[\d+\]',n)]
        assert fields
        for name in fields:
            assert name in models['gate']['netnames']
            assert len(models['gold']['netnames'][name]['bits']) == len(models['gate']['netnames'][name]['bits'])
        report['results'].append(dict(status='PROVEN',phase='formal',parameters=dict(params,DIRECT_ADVANCE=direct),
            equiv_cells=int(re.search(r'Found (\d+) \$equiv cells in equiv:',text)[1]),
            preserved_state_aliases=len(fields),prepared_sha256=sha(prepared),script_sha256=sha(script),log_sha256=sha(log)))
        save();print('PROVEN '+stem,flush=True)
    verify_inputs();report.update(status='COMPLETE',active_case=None,phase='complete');save()
    print('COMPLETE12 protocol and8 complete sequential LSQ equivalence cases',flush=True)


if __name__ == '__main__':
    main()
