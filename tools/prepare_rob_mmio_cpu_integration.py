"""Stage the proved actual ROB64 MMIO predicate in an isolated parallel-match CPU.

Require the immutable bank1 proof certificate for the exact CPU geometry.
Retain the original driver, memory, libraries and every other parameter.
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
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def replace(code,old,new):
    assert code.count(old)==1,old
    return code.replace(old,new)


def adapt(name,code):
    code=replace(code,'    parameter integer ROB_ALLOC_BANKED_WRITE = 0,',
                 '    parameter integer ROB_MMIO_PREDECODE = 0,\n    parameter integer ROB_ALLOC_BANKED_WRITE = 0,')
    if name.endswith('rv32_backend_joint.v'):
        return replace(code,'.ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE),',
                       '.ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .MMIO_PREDECODE(ROB_MMIO_PREDECODE),')
    return replace(code,'.ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE),',
                   '.ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .ROB_MMIO_PREDECODE(ROB_MMIO_PREDECODE),')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baseline-native','outdir'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();source,out=a.source_root.resolve(),a.outdir.resolve()
    assert not out.exists()
    native=read(a.baseline_native)
    assert native['status']=='VERIFIED' and native['cases']==29 and native['added_native_cases']==8 and native['additional_isa_cases']==16
    assert native['all_cycles_identical'] and Path(native['source_roots'][1]).resolve()==source
    base_path=Path(native['gate'])/'build/build_manifest.json';base=read(base_path)
    originals={n:h.lower() for n,h in base['source_sha256'].items()}
    assert len(originals)==43
    component=Path('F:/CPU2026Candidates/rob_mmio_predecode_v2_20261003')
    component_manifest=component/'candidate_manifest.json';cm=read(component_manifest)
    assert cm['baseline_sha256']==originals['rtl/backend/rv32_rob.v']
    assert cm['default_mmio_predecode']==0 and cm['original_payloads_and_ports_preserved']
    proof_path=Path('F:/CPU2026Proofs/rob_mmio_predecode_actual64_bank1_verified_20261003/report.json')
    proof=read(proof_path)
    expected=dict(BE_WIDTH=4,ROB_ENTRIES=64,PHYS_REGS=64,PHYS_ADDR_WIDTH=6,GENERATION_WIDTH=8,
                  CHECKPOINT_WIDTH=192,CHECKPOINT_IMPL=1,STORE_BUFFERED_RETIRE=1,COMMIT_BANKED_READ=1,
                  ALLOC_BANKED_WRITE=1,ROB_CONTROL_REGISTER_BANKS=0,ASAP7_FANOUT_BUFFERS=0,MMIO_PREDECODE=1)
    assert proof['parameters']==expected and proof['actual64_proof'] and proof['status']=='COMPLETE'
    assert proof['independent_verification']=='VERIFIED' and proof['equiv_cells']==29726
    assert proof['all_original_ports_and_active_state_preserved'] and proof['no_input_assumptions'] and proof['no_proof_points_suppressed']
    assert proof['baseline_sha256']==cm['baseline_sha256'] and proof['candidate_sha256']==cm['candidate_sha256']
    assert sha(component/'rtl/backend/rv32_rob.v')==cm['candidate_sha256']
    for key,value in {'ROB_ENTRIES':64,'PHYS_REGS':64,'ROB_COMMIT_BANKED_READ':1,'ROB_ALLOC_BANKED_WRITE':1,'ROB_CONTROL_REGISTER_BANKS':0,'ASAP7_FANOUT_BUFFERS':0,'CDB_WIDTH':3,'ICACHE_TAG_MATCH_PARALLEL':1}.items():
        assert base['parameter_overrides'][key]==value,(key,base['parameter_overrides'])
    evidence=[a.baseline_native.resolve(),component_manifest,proof_path,
              Path('F:/CPU2026Proofs/rob_mmio_predecode_protocol_v2_20261003/report.json'),
              Path('F:/CPU2026Proofs/rob_mmio_predecode_differential_v2_20261003/report.json'),
              Path('F:/CPU2026Proofs/rob_mmio_predecode_formal_aliases_v2_20261003/verified_completion.json'),
              Path('F:/CPU2026Proofs/rob_mmio_directed_v2_20261003/report.json'),
              Path('F:/CPU2026Proofs/rob_mmio_directed_negative_20261003/report.json')]
    for path in evidence:
        for name,want in read(path).get('input_sha256',{}).items():assert sha(name)==want,name
    dependencies=read(source/'measurement_dependencies.json')['input_sha256']
    files=dependencies|originals
    for name,want in files.items():assert sha(source/name)==want.lower(),name
    framework=out/'.deps/RISC-V-CPU-2026';framework.parent.mkdir(parents=True)
    revision='54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(source/'.deps/RISC-V-CPU-2026'),str(framework)],check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision],check=True)
    for name in files:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
    adapters={'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v'}
    changed=adapters|{'rtl/backend/rv32_rob.v'}
    for name in changed:
        backup=out/'baseline'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,backup)
    for name in adapters:
        path=out/name;path.write_text(adapt(name,path.read_text()))
    shutil.copyfile(component/'rtl/backend/rv32_rob.v',out/'rtl/backend/rv32_rob.v')
    assert {n for n,h in originals.items() if sha(out/n)!=h}==changed
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'],text=True).strip()
    sta=out/'.deps/OpenSTA/build/sta';sta.parent.mkdir(parents=True);shutil.copyfile(source/'.deps/OpenSTA/build/sta',sta)
    runtime_rel=Path('.deps/oss-cad-suite-install/oss-cad-suite')
    runtime_source,runtime_target=source/runtime_rel,out/runtime_rel;runtime_target.parent.mkdir(parents=True)
    repair_path=source/'tool_runtime_repair.json';repair=read(repair_path)
    assert repair['status']=='VERIFIED' and repair['frozen_inputs_unchanged']
    esc=lambda p:"'"+str(p).replace("'","''")+"'"
    subprocess.run([shutil.which('pwsh.exe'),'-NoProfile','-Command','New-Item -ItemType Junction -Path '+esc(runtime_target)+' -Target '+esc(runtime_source)+' | Out-Null'],check=True)
    runtime_hashes={n:sha(runtime_target/n) for n in ('bin/verilator_bin.exe','bin/yosys.exe','bin/yosys-abc.exe')}
    assert all(h==repair['runtime_sha256'][n] for n,h in runtime_hashes.items())
    evidence.append(repair_path)
    (out/'measurement_dependencies.json').write_text(json.dumps(dict(status='COMPLETE',source_root=str(source),stage_root=str(out),input_sha256=dependencies),indent=2)+'\n')
    result=dict(status='STAGED',source_root=str(source),baseline_manifest=str(base_path),baseline_native_audit=str(a.baseline_native.resolve()),
                baseline_sha256=originals,staged_sha256={n:sha(out/n) for n in originals},changed_files=sorted(changed),
                parameters=base['parameter_overrides']|dict(ROB_MMIO_PREDECODE=1),default_rob_mmio_predecode=0,
                component_root=str(component),component_sha256=cm['candidate_sha256'],actual_proof_certificate=str(proof_path),
                actual_proof_parameters=expected,measurement_dependencies_sha256=dependencies,framework_revision=revision,opensta_sha256=sha(sta),
                runtime_junction_source=str(runtime_source),runtime_binary_sha256=runtime_hashes,
                validation_evidence_sha256={str(p):sha(p) for p in evidence},cycle_equivalence_required=True,no_cpu_ppa_claim=True,preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='STAGED',changed_files=sorted(changed),actual_proof_points=29726,no_cpu_ppa_claim=True)))


if __name__=='__main__':main()
