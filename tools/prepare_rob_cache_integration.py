"""Stage verified ROB completion selection and Cache group geometry together.

Preserve the verified completion2 CPU source and all measurement dependencies.
All component findings are prerequisites, not estimates of the joint CPU PPA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def replace(code,before,after):
    assert code.count(before)==1,'Ambiguous integration anchor: '+before
    return code.replace(before,after)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--baseline-result',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    source,out=args.source_root.resolve(),args.outdir.resolve()
    assert not out.exists()
    verified=read(args.baseline_result)
    assert verified['status']=='VERIFIED' and verified['all_correctness_cases']==29
    assert Path(verified['evaluated_source_root']).resolve()==source
    for name,h in verified['input_sha256'].items():assert sha(name)==h,'Baseline evidence changed: '+name
    base_manifest=Path(verified['directory'])/'build/build_manifest.json'
    base=read(base_manifest);originals={n:h.lower() for n,h in base['source_sha256'].items()}
    dependencies=read(source/'measurement_dependencies.json')['input_sha256']
    files=dependencies|originals
    for name,h in files.items():assert sha(source/name)==h.lower(),'Frozen source changed: '+name
    rob=Path('F:/CPU2026Candidates/rob_parallel_completion_v3_20261003')
    cache=Path('F:/CPU2026Candidates/dcache_metadata_geometry_20261003')
    evidence=[Path('F:/CPU2026Probes/rob_parallel_completion_actual64_v3_20261003/independent_component_verification.json'),
              Path('F:/CPU2026Probes/dcache_metadata_geometry_actual_20261003/independent_component_verification.json')]
    for path in evidence:assert read(path)['status']=='VERIFIED'
    formal=Path('F:/CPU2026Proofs/rob_parallel_completion_formal_v3_20261003/report.json')
    protocol=Path('F:/CPU2026Proofs/rob_parallel_completion_protocol_v3_20261003/report.json')
    differential=Path('F:/CPU2026Proofs/rob_parallel_completion_differential_v4_20261003/report.json')
    cache_protocol=Path('F:/CPU2026Proofs/dcache_metadata_geometry_full_20261003/report.json')
    for path in [formal,protocol,differential,cache_protocol]:assert read(path)['status']=='COMPLETE'
    assert len(read(formal)['results'])==8 and len(read(protocol)['results'])==48
    assert read(differential)['total_cycles']==48000
    replacements={'rtl/backend/rv32_rob.v':rob/'rtl/backend/rv32_rob.v',
                  'rtl/cache/rv32_dcache_nonblocking.v':cache/'rtl/cache/rv32_dcache_nonblocking.v'}
    expected={'rtl/backend/rv32_rob.v':'b53248f75ae46efc4b0d14f1d3ab7089213eb5ce46708997caf0aa603bdc783e',
              'rtl/cache/rv32_dcache_nonblocking.v':'05091f47249c3d05c383e6d7a803c128f78fc1b8fc30a624d89195e3f4ac080f'}
    for name,path in replacements.items():assert sha(path)==expected[name]
    framework=out/'.deps/RISC-V-CPU-2026'
    framework.parent.mkdir(parents=True)
    revision='54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(source/'.deps/RISC-V-CPU-2026'),str(framework)],check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision],check=True)
    for name in files:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
    modified=set(replacements)|{'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v'}
    for name in modified:
        backup=out/'baseline'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,backup)
    for name,path in replacements.items():shutil.copyfile(path,out/name)
    for name in modified-set(replacements):
        path=out/name;code=path.read_text()
        code=replace(code,'    parameter integer ROB_ALLOC_BANKED_WRITE = 0,',
                     '    parameter integer ROB_ALLOC_BANKED_WRITE = 0,\n    parameter integer ROB_COMPLETION_PARALLEL_WRITE = 0,')
        if name.endswith('rv32_backend_joint.v'):
            code=replace(code,'.ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE),',
                         '.ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .COMPLETION_PARALLEL_WRITE(ROB_COMPLETION_PARALLEL_WRITE),')
        else:
            code=replace(code,'.ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE),',
                         '.ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .ROB_COMPLETION_PARALLEL_WRITE(ROB_COMPLETION_PARALLEL_WRITE),')
            code=replace(code,'    parameter integer DCACHE_LOCAL_ACTION_DECODE = 0,',
                         '    parameter integer DCACHE_LOCAL_ACTION_DECODE = 0,\n    parameter integer DCACHE_METADATA_GROUP_ROWS = 16,')
            if name.endswith('cpu_core.v'):
                code=replace(code,'.LOCAL_ACTION_DECODE(DCACHE_LOCAL_ACTION_DECODE)\n',
                             '.LOCAL_ACTION_DECODE(DCACHE_LOCAL_ACTION_DECODE), .METADATA_GROUP_ROWS(DCACHE_METADATA_GROUP_ROWS)\n')
            else:
                code=replace(code,'.DCACHE_LOCAL_ACTION_DECODE(DCACHE_LOCAL_ACTION_DECODE),',
                             '.DCACHE_LOCAL_ACTION_DECODE(DCACHE_LOCAL_ACTION_DECODE), .DCACHE_METADATA_GROUP_ROWS(DCACHE_METADATA_GROUP_ROWS),')
        path.write_text(code)
    assert {n for n,h in originals.items() if sha(out/n)!=h}==modified
    assert all(sha(source/n)==h.lower() for n,h in files.items())
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'],text=True).strip()
    sta=out/'.deps/OpenSTA/build/sta';sta.parent.mkdir(parents=True);shutil.copyfile(source/'.deps/OpenSTA/build/sta',sta)
    assert sha(sta)==sha(source/'.deps/OpenSTA/build/sta')
    result=dict(status='STAGED',source_root=str(source),baseline_manifest=str(base_manifest),
                baseline_result=str(args.baseline_result.resolve()),baseline_sha256=originals,
                staged_sha256={n:sha(out/n) for n in originals},changed_files=sorted(modified),
                parameters=base['parameter_overrides']|dict(ROB_COMPLETION_PARALLEL_WRITE=1,DCACHE_METADATA_GROUP_ROWS=64),
                measurement_dependencies_sha256={n:sha(out/n) for n in dependencies},
                framework_revision=revision,opensta_sha256=sha(sta),
                validation_evidence_sha256={str(p):sha(p) for p in [*evidence,formal,protocol,differential,cache_protocol]},
                main_source_unchanged=True,no_cpu_ppa_claim=True,preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='STAGED',changed_files=sorted(modified),compiled_inputs=len(originals)),indent=2))


if __name__=='__main__':main()
