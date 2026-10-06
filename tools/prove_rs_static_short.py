"""Prove the frozen complete 16-entry RS using shared-node SAT cones.

Use the unchanged prepared gold/gate design from the ongoing full proof.
No port, state, equivalence point or input constraint is removed. The -short
option changes SAT cone construction; equiv_status still asserts every point.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-dir', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.proof_dir.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh proof directory')
    stem = 'be4_entries16_wake10_metadata70'
    prepared = source/(stem+'.prepared.json')
    original_script = source/(stem+'.ys')
    design = json.loads(prepared.read_text())['modules']
    assert set(design) == {'gold', 'gate'}
    schema = lambda module: {n:(v['direction'],len(v['bits'])) for n,v in module['ports'].items()}
    assert schema(design['gold']) == schema(design['gate'])
    assert all(c['type'] != '$assume' for m in design.values() for c in m['cells'].values())
    ports = schema(design['gold'])
    del design
    inputs = [prepared, original_script, Path(__file__),
              source/'source_snapshot/original.v', source/'source_snapshot/candidate.v',
              source/'source_snapshot/rtl/rv32im_defs.vh',
              source/'source_snapshot/test_rs_static_allocation.py']
    hashes = {str(p):sha(p) for p in inputs}
    out.mkdir(parents=True)
    script, log = out/'proof.ys', out/'proof.log'
    script.write_text('\n'.join([
        'read_json "'+prepared.as_posix()+'"',
        'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
        'equiv_simple -short -seq 2', 'equiv_induct -seq 4', 'equiv_status -assert'])+'\n')
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    report = dict(status='RUNNING', no_input_assumptions=True, proves_whole_cpu=False,
                  input_sha256=hashes, port_schema=ports,
                  parameters=dict(BE_WIDTH=4,ENTRIES=16,WAKE_WIDTH=10,METADATA_WIDTH=70,
                                  TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,AGE_WIDTH=32,WAKE_MUX_IMPL=1),
                  parameter_change=dict(ALLOC_STATIC_WRITE=[0,1]))
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    print('START unchanged whole RS16 proof with shared-node SAT cones',flush=True)
    with log.open('w') as stream:
        result = subprocess.run([str(yosys),'-T','-s',str(script)],env=env,
                                stdout=stream,stderr=subprocess.STDOUT)
    text = log.read_text()
    for name,expected in hashes.items():
        assert sha(Path(name)) == expected, 'Frozen proof input changed: '+name
    report.update(log_sha256=sha(log),script_sha256=sha(script),yosys_sha256=sha(yosys))
    if result.returncode or 'Equivalence successfully proven!' not in text:
        report.update(status='FAILED',failure_log=str(log));save()
        raise SystemExit('Complete RS16 equivalence not proven')
    count = re.search(r'Found (\d+) \$equiv cells in equiv:',text)
    assert count
    report.update(status='PROVEN',equiv_cells=int(count[1]),unproven_cells=0,
                  method='equiv_simple -short -seq 2; equiv_induct -seq 4; equiv_status -assert')
    save()
    print('PROVEN unchanged whole RS16: '+str(count[1])+' equivalence points',flush=True)


if __name__ == '__main__':
    main()
