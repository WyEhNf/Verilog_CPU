"""Reuse the strict hierarchy audit with one real module, plus all24 extra cases."""
import argparse
import json
from pathlib import Path
import sys

import audit_functional_hierarchy as original
from prepare_icache_selective_hierarchy import MODULES, ATTRIBUTE, read, sha


def main():
    parser = argparse.ArgumentParser()
    for arg in ('gold','gate','gold-source','gate-source','out'):
        parser.add_argument('--'+arg,type=Path,required=True)
    a = parser.parse_args()
    assert not a.out.exists()
    base_out = a.out.with_name('hierarchy_original29_audit.json')
    assert not base_out.exists()
    original.MODULES, original.ATTRIBUTE = MODULES, ATTRIBUTE
    saved = sys.argv
    sys.argv = [saved[0]]
    for arg in ('gold','gate','gold-source','gate-source'):
        sys.argv += ['--'+arg,str(getattr(a,arg.replace('-','_')))]
    sys.argv += ['--out',str(base_out)]
    try:
        original.main()
    finally:
        sys.argv = saved
    result = read(base_out)
    inputs = result['input_sha256']
    def record(path, expected=None):
        path=Path(path).resolve(); actual=sha(path)
        assert expected is None or actual == expected.lower(), str(path)
        assert str(path) not in inputs or inputs[str(path)] == actual
        inputs[str(path)] = actual
    record(base_out)
    for helper in (__file__,original.__file__,Path(__file__).with_name('prepare_icache_selective_hierarchy.py')):
        record(helper)
    extras=[]
    for root,source in ((a.gold,a.gold_source),(a.gate,a.gate_source)):
        mp=(root/'build/build_manifest.json').resolve(); manifest=read(mp)
        suites={}
        for suite,count in (('legal_addi_native',8),('arch_native',16)):
            rp=root/suite/'report.json';record(rp); r=read(rp)
            assert r['status']=='COMPLETE' and len(r['results'])==count
            assert len({row['name'] for row in r['results']})==count
            assert r['memory_latency']==20 and r['input_sha256'][str(mp)]==sha(mp)
            for name,h in r['input_sha256'].items():record(name,h)
            assert all(row['status']=='PASS' for row in r['results'])
            if count==8:
                assert all(row['result']==256 for row in r['results'])
            else:
                assert r['instruction_types']==45
                assert Path(r['source_root']).resolve()==source.resolve()
                assert r['parameter_overrides']==manifest['parameter_overrides']
            suites[suite]=r
        extras.append(suites)
    for suite,fields in (
        ('legal_addi_native',('status','instret','result','cycles')),
        ('arch_native',('status','expected_u32','native_instret','oracle_instructions_through_exit_store','cycles'))):
        right={r['name']:r for r in extras[1][suite]['results']}
        for left in extras[0][suite]['results']:
            for field in fields:
                assert left[field]==right[left['name']][field],(suite,left['name'],field)
    stage=read(a.gate_source/'staging_manifest.json')
    for name,h in stage['validation_evidence_sha256'].items():
        record(name,h)
        for p,v in read(name).get('input_sha256',{}).items():record(p,v)
    for name,h in inputs.items():assert sha(name)==h,name
    result.update(scope=__doc__,added_native_cases=8,additional_isa_cases=16,
                  all_cycles_identical=True,all_retirement_and_exits_identical=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='VERIFIED',cases=53,
                         ipc=result['benchmark_geomean_ipc'],all_cycles_identical=True)))


if __name__ == '__main__':
    main()
