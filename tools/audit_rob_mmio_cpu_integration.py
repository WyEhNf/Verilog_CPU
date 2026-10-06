"""Audit the isolated ROB MMIO predecode CPU against its frozen baseline.

Require the exact actual64 bank1 full proof, unchanged original driver/memory,
all 43 compiled inputs and exactly four intended changes. All 53 native cases
must preserve cycles, retirement counts and architecture-visible outcomes.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from prepare_rob_mmio_cpu_integration import adapt


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gold','gate','gold-source','gate-source','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args()
    assert not a.out.exists()
    inputs={}
    def record(path,expected=None):
        path=Path(path).resolve();h=sha(path)
        assert expected is None or h==expected.lower(),str(path)
        assert str(path) not in inputs or inputs[str(path)]==h
        inputs[str(path)]=h
    stage_path=a.gate_source/'staging_manifest.json';record(stage_path);stage=read(stage_path)
    assert stage['default_rob_mmio_predecode']==0 and stage['cycle_equivalence_required']
    adapters={'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v'}
    changed_names=adapters|{'rtl/backend/rv32_rob.v'}
    assert set(stage['changed_files'])==changed_names
    for name in adapters:
        assert adapt(name,(a.gold_source/name).read_text())==(a.gate_source/name).read_text(),name
    component=Path(stage['component_root']);cm=read(component/'candidate_manifest.json')
    record(component/'candidate_manifest.json')
    assert sha(a.gold_source/'rtl/backend/rv32_rob.v')==cm['baseline_sha256']
    assert sha(a.gate_source/'rtl/backend/rv32_rob.v')==cm['candidate_sha256']==stage['component_sha256']
    proof_path=Path(stage['actual_proof_certificate']);record(proof_path);proof=read(proof_path)
    assert proof['status']=='COMPLETE' and proof['independent_verification']=='VERIFIED' and proof['actual64_proof']
    assert proof['no_input_assumptions'] and proof['no_proof_points_suppressed'] and proof['all_original_ports_and_active_state_preserved']
    expected_proof=dict(BE_WIDTH=4,ROB_ENTRIES=64,PHYS_REGS=64,PHYS_ADDR_WIDTH=6,GENERATION_WIDTH=8,CHECKPOINT_WIDTH=192,
                        CHECKPOINT_IMPL=1,STORE_BUFFERED_RETIRE=1,COMMIT_BANKED_READ=1,ALLOC_BANKED_WRITE=1,
                        ROB_CONTROL_REGISTER_BANKS=0,ASAP7_FANOUT_BUFFERS=0,MMIO_PREDECODE=1)
    assert proof['parameters']==stage['actual_proof_parameters']==expected_proof and proof['equiv_cells']==29726
    assert proof['baseline_sha256']==cm['baseline_sha256'] and proof['candidate_sha256']==cm['candidate_sha256']
    counts=dict(benchmark=6,basic=5,simulator=17,boundary=1)
    manifests=[];profiles=[];reports=[];extras=[];edges=[]
    for index,(root,source) in enumerate(((a.gold,a.gold_source),(a.gate,a.gate_source))):
        root,source=root.resolve(),source.resolve()
        manifest_path=root/'build/build_manifest.json';record(manifest_path);m=read(manifest_path)
        assert m['format']=='course-axi-frozen-build-v1' and len(m['source_sha256'])==43
        for name,h in m['source_sha256'].items():record(source/name,h)
        record(m['executable'],m['executable_sha256']);record(m['generated_driver'],m['generated_driver_sha256'])
        original=(source/'.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
        observed=Path(m['generated_driver']).read_text()
        line='        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
        assert observed.count(line)==1 and observed.replace(line,'')==original
        header=(source/'rtl/course/student_top.v').read_text().split(') (',1)[0]
        defaults={k:int(v) for k,v in re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)',header)}
        assert set(m['parameter_overrides'])<=set(defaults)
        if index:assert defaults['ROB_MMIO_PREDECODE']==0
        effective=defaults|m['parameter_overrides']
        for key,value in dict(BE_WIDTH=4,ROB_ENTRIES=64,PHYS_REGS=64,GENERATION_WIDTH=8,CHECKPOINT_IMPL=1,STORE_BUFFERED_RETIRE=1,ROB_COMMIT_BANKED_READ=1,ROB_ALLOC_BANKED_WRITE=1,ROB_CONTROL_REGISTER_BANKS=0,ASAP7_FANOUT_BUFFERS=0).items():
            assert effective[key]==value,key
        profiles.append(defaults|m['parameter_overrides']);manifests.append(m)
        suites={}
        for suite,count in counts.items():
            path=root/(suite+'.json');record(path);r=read(path)
            assert r['status']=='COMPLETE' and r['suite']==suite and len(r['results'])==count
            assert Path(r['build_manifest']).resolve()==manifest_path and Path(r['evaluated_source_root']).resolve()==source
            assert r['pi_excluded'] and r['evaluates_current_worktree']==(not r['current_source_differences'])
            mem=r['external_memory']
            assert mem['latency_cycles']==20 and mem['external_ram_bytes']==268435456
            assert mem['word_bytes']==4 and mem['shared_ar_r'] and mem['exit_at_b_handshake']
            for name,h in r['source_sha256'].items():record(name,h)
            assert len({row['name'] for row in r['results']})==count
            assert sum(row['cycles'] for row in r['results'])==r['total_cycles']
            assert sum(row['instret'] for row in r['results'])==r['total_instret']
            for row in r['results']:
                assert row['status']=='passed' and row['expected_u32']==row['return_u32']
                assert row['cycles']>0 and row['instret']>0
                assert math.isclose(row['ipc'],row['instret']/row['cycles'],rel_tol=1e-12)
                record(row['image'])
            geomean=math.exp(sum(math.log(row['instret']/row['cycles']) for row in r['results'])/count)
            assert math.isclose(geomean,r['geomean_ipc'],rel_tol=1e-12)
            if suite=='benchmark':assert {row['name'] for row in r['results']}=={'median','multiply','qsort','rsort','towers','vvadd'}
            suites[suite]=r
        reports.append(suites)
        for rel,bucket,count in [('legal_addi_native/report.json',extras,8),('arch_native/report.json',edges,16)]:
            path=root/rel;record(path);r=read(path)
            assert r['status']=='COMPLETE' and len(r['results'])==count and r['memory_latency']==20
            for name,h in r['input_sha256'].items():record(name,h)
            assert r['input_sha256'][str(manifest_path)]==sha(manifest_path)
            assert all(row['status']=='PASS' for row in r['results'])
            if count==8:assert all(row['result']==256 for row in r['results'])
            else:
                assert r['instruction_types']==45 and Path(r['source_root']).resolve()==source
                assert r['parameter_overrides']==m['parameter_overrides']
            bucket.append(r)
    old,new=({n:h.lower() for n,h in m['source_sha256'].items()} for m in manifests)
    assert old.keys()==new.keys()
    changed={n:[old[n],new[n]] for n in old if old[n]!=new[n]}
    assert set(changed)==changed_names
    assert old==stage['baseline_sha256'] and new==stage['staged_sha256']
    assert set(profiles[1])-set(profiles[0])=={'ROB_MMIO_PREDECODE'}
    assert all(profiles[0][k]==profiles[1][k] for k in profiles[0]) and profiles[1]['ROB_MMIO_PREDECODE']==1
    assert manifests[0]['generated_driver_sha256']==manifests[1]['generated_driver_sha256']
    assert manifests[0]['external_memory']==manifests[1]['external_memory']
    rows=[]
    for suite in counts:
        left,right=reports[0][suite],reports[1][suite]
        assert left['external_memory']==right['external_memory']
        by_name={row['name']:row for row in right['results']}
        for row in left['results']:
            other=by_name[row['name']]
            for field in ('expected_u32','return_u32','instret','cycles'):assert row[field]==other[field],(suite,row['name'],field)
            assert Path(row['image']).resolve()==Path(other['image']).resolve()
            rows.append(dict(suite=suite,name=row['name'],cycles=[row['cycles'],other['cycles']],instret=row['instret'],return_u32=row['return_u32']))
    for bucket,fields in [(extras,('name','status','instret','result','cycles')),
                          (edges,('name','status','expected_u32','native_instret','oracle_instructions_through_exit_store','cycles'))]:
        for left,right in zip(bucket[0]['results'],bucket[1]['results']):
            for field in fields:assert left[field]==right[field],(field,left,right)
    for path,h in stage['validation_evidence_sha256'].items():
        record(path,h)
        for name,digest in read(path).get('input_sha256',{}).items():record(name,digest)
    for name,h in stage['measurement_dependencies_sha256'].items():record(a.gate_source/name,h)
    for name,h in stage['runtime_binary_sha256'].items():record(a.gate_source/'.deps/oss-cad-suite-install/oss-cad-suite'/name,h)
    record(Path(__file__));record(Path(__file__).with_name('prepare_rob_mmio_cpu_integration.py'),stage['preparer_sha256'])
    for name,h in inputs.items():assert sha(name)==h,name
    result=dict(status='VERIFIED',cases=29,added_native_cases=8,additional_isa_cases=16,
                gold=str(a.gold.resolve()),gate=str(a.gate.resolve()),source_roots=[str(a.gold_source.resolve()),str(a.gate_source.resolve())],
                effective_parameter_change={'ROB_MMIO_PREDECODE':[0,1]},compiled_input_differences=changed,
                all_shared_parameters_identical=True,all_retirement_and_exits_identical=True,
                all_cycles_identical=all(row['cycles'][0]==row['cycles'][1] for row in rows),
                baseline_geomean_ipc=reports[0]['benchmark']['geomean_ipc'],benchmark_geomean_ipc=reports[1]['benchmark']['geomean_ipc'],
                cycle_equivalence_claim=True,actual64_bank1_proof_points=proof['equiv_cells'],results=rows,input_sha256=inputs,cpu_ppa_claim=False)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','cases','added_native_cases','additional_isa_cases','effective_parameter_change','benchmark_geomean_ipc','all_cycles_identical')},indent=2))


if __name__=='__main__':main()
