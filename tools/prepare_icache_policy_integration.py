"""Stage the verified I-cache replacement tradeoff on the repaired real CPU.

Require39 repair protocols,29+8 native cases and88 I-cache SRAM/replay cases,
then copy43 measured inputs and149 original measurement dependencies. Only
the I-cache and two parameter adapters change; no component PPA is a CPU score.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def replace(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baseline-native','outdir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();source,out=a.source_root.resolve(),a.outdir.resolve();assert not out.exists()
    native=read(a.baseline_native)
    assert native['status']=='VERIFIED' and native['cases']==29 and native['added_native_cases']==8
    assert native['protocol_configurations']==39 and native['known_baseline_addi255_defect_fixed']
    assert Path(native['source_roots'][1]).resolve()==source
    for name,h in native['input_sha256'].items():assert sha(name)==h,name
    base_path=Path(native['gate'])/'build/build_manifest.json';base=read(base_path)
    originals={n:h.lower() for n,h in base['source_sha256'].items()}
    dependencies=read(source/'measurement_dependencies.json')['input_sha256'];files=dependencies|originals
    for name,h in files.items():assert sha(source/name)==h,name
    component=Path('F:/CPU2026Candidates/icache_refill_policy_20261003')
    component_manifest=component/'candidate_manifest.json';cm=read(component_manifest)
    assert cm['baseline_sha256']==originals['rtl/cache/rv32_icache_nonblocking.v']
    for name,h in cm['files_sha256'].items():assert sha(component/name)==h,name
    evidence=[a.baseline_native.resolve(),component_manifest,
              Path('F:/CPU2026Proofs/icache_refill_policy_20261003/report.json'),
              Path('F:/CPU2026Probes/icache_refill_policy_actual128_20261003/independent_component_verification.json')]
    assert read(evidence[2])['status']=='COMPLETE' and len(read(evidence[2])['results'])==88
    assert read(evidence[3])['status']=='VERIFIED'
    for path in evidence:
        for name,h in read(path).get('input_sha256',{}).items():assert sha(name)==h,name
    framework=out/'.deps/RISC-V-CPU-2026';framework.parent.mkdir(parents=True)
    revision='54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(source/'.deps/RISC-V-CPU-2026'),str(framework)],check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision],check=True)
    for name in files:
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,path)
    (out/'measurement_dependencies.json').write_text(json.dumps(dict(status='COMPLETE',source_root=str(source),stage_root=str(out),input_sha256=dependencies),indent=2)+'\n')
    modified={'rtl/cache/rv32_icache_nonblocking.v','rtl/cpu_core.v','rtl/course/student_top.v'}
    for name in modified:
        path=out/'baseline'/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,path)
    shutil.copyfile(component/'rtl/cache/rv32_icache_nonblocking.v',out/'rtl/cache/rv32_icache_nonblocking.v')
    for name in ('rtl/cpu_core.v','rtl/course/student_top.v'):
        path=out/name;code=path.read_text()
        code=replace(code,'    parameter integer ICACHE_MSHRS = 8,',
                     '    parameter integer ICACHE_REFILL_PROTECT_PENDING_HIT = 1,\n    parameter integer ICACHE_MSHRS = 8,')
        if name.endswith('cpu_core.v'):
            code=replace(code,'.MSHR_ENTRIES(ICACHE_MSHRS),',
                         '.MSHR_ENTRIES(ICACHE_MSHRS), .REFILL_PROTECT_PENDING_HIT(ICACHE_REFILL_PROTECT_PENDING_HIT),')
        else:
            code=replace(code,'.ICACHE_MSHRS(ICACHE_MSHRS),',
                         '.ICACHE_MSHRS(ICACHE_MSHRS), .ICACHE_REFILL_PROTECT_PENDING_HIT(ICACHE_REFILL_PROTECT_PENDING_HIT),')
        path.write_text(code)
    assert {n for n,h in originals.items() if sha(out/n)!=h}==modified
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'],text=True).strip()
    sta=out/'.deps/OpenSTA/build/sta';sta.parent.mkdir(parents=True);shutil.copyfile(source/'.deps/OpenSTA/build/sta',sta)
    result=dict(status='STAGED',source_root=str(source),baseline_manifest=str(base_path),
                baseline_native_audit=str(a.baseline_native.resolve()),baseline_sha256=originals,
                staged_sha256={n:sha(out/n) for n in originals},changed_files=sorted(modified),
                parameters=base['parameter_overrides']|dict(ICACHE_REFILL_PROTECT_PENDING_HIT=0),
                component_root=str(component),component_sha256=cm['files_sha256']['rtl/cache/rv32_icache_nonblocking.v'],
                measurement_dependencies_sha256=dependencies,framework_revision=revision,opensta_sha256=sha(sta),
                validation_evidence_sha256={str(path):sha(path) for path in evidence},
                cycle_equivalence_claim=False,no_cpu_ppa_claim=True,preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='STAGED',changed_files=sorted(modified),parameter='ICACHE_REFILL_PROTECT_PENDING_HIT=0'),indent=2))


if __name__=='__main__':main()
