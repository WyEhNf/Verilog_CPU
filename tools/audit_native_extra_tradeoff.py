"""Extend a verified 29-case parameter comparison with eight ADDI and16 ISA cases.

Recheck all frozen inputs, tie each additional suite to its actual executable
manifest and compare retirements/signatures. Cycles may change with the one
parameter already checked by compare_course_snapshot_tradeoff.py.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--comparison',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();assert not a.out.exists()
    comparison=read(a.comparison)
    assert comparison['status']=='VERIFIED' and comparison['cases']==29
    assert comparison['all_exits_and_retirement_counts_identical']
    assert len(comparison['effective_parameter_differences'])==1
    inputs={}
    def record(path,expected=None):
        path=Path(path).resolve();actual=sha(path)
        assert expected is None or expected.lower()==actual,str(path)
        assert str(path) not in inputs or inputs[str(path)]==actual
        inputs[str(path)]=actual
    record(a.comparison)
    for path,h in comparison['input_sha256'].items():record(path,h)
    source=Path(comparison['evaluated_source_root']).resolve()
    extra_reports=[]
    for which in ('gold','gate'):
        root=Path(comparison[which]).resolve()
        mp=root/'build/build_manifest.json';record(mp);manifest=read(mp)
        record(manifest['executable'],manifest['executable_sha256'])
        suites={}
        for name,count in [('legal_addi_native',8),('arch_native',16)]:
            path=root/name/'report.json';record(path);report=read(path)
            assert report['status']=='COMPLETE' and len(report['results'])==count and report['memory_latency']==20
            assert report['input_sha256'][str(mp)]==sha(mp)
            for path,h in report['input_sha256'].items():record(path,h)
            assert len({r['name'] for r in report['results']})==count
            assert all(r['status']=='PASS' for r in report['results'])
            if count==8:assert all(r['result']==256 for r in report['results'])
            else:
                assert report['instruction_types']==45
                assert Path(report['source_root']).resolve()==source
                assert report['parameter_overrides']==manifest['parameter_overrides']
            suites[name]=report
        extra_reports.append(suites)
    rows=[]
    for suite,fields in [('legal_addi_native',('status','instret','result')),
                         ('arch_native',('status','expected_u32','native_instret','oracle_instructions_through_exit_store'))]:
        by_name={r['name']:r for r in extra_reports[1][suite]['results']}
        for left in extra_reports[0][suite]['results']:
            right=by_name[left['name']]
            for field in fields:assert left[field]==right[field],(suite,left['name'],field)
            rows.append(dict(suite=suite,name=left['name'],cycles=[left['cycles'],right['cycles']],architectural_values_identical=True))
    record(__file__)
    for path,h in inputs.items():assert sha(path)==h,path
    result=dict(status='VERIFIED',cases=29,added_native_cases=8,additional_isa_cases=16,
                gold=comparison['gold'],gate=comparison['gate'],evaluated_source_root=str(source),
                effective_parameter_differences=comparison['effective_parameter_differences'],
                benchmark_geomean_ipc=comparison['benchmark_geomean_ipc'],
                all_retirement_and_exits_identical=True,cycle_equivalence_claim=False,
                original_results=comparison['results'],additional_results=rows,input_sha256=inputs,cpu_ppa_claim=False)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','cases','added_native_cases','additional_isa_cases','effective_parameter_differences','benchmark_geomean_ipc')},indent=2))


if __name__=='__main__':main()
