"""Independently verify a complete, single-parameter component PPA pair.

Include original library prices, all actual physical leaves, all real SRAM
and timing input hashes. A standalone component is never a whole CPU score.
"""
import argparse
from decimal import Decimal
import gc
import json
from pathlib import Path

from audit_component_timing_identity import verify_component
from verify_course_axi_area import sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--parameter',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    assert not args.out.exists(), 'Preserve previous certificate'
    root=args.directory.resolve();parent=json.loads((root/'report.json').read_text())
    assert parent['status']=='COMPLETE' and len(parent['results'])==2
    for row in parent['compiled_origins'].values():
        assert sha256(row['path'])==row['sha256'], 'Changed component origin: '+row['path']
    paths=sorted(root.glob('*/area_audit.json'))
    assert len(paths)==2
    results=[]
    for path in paths:
        model,functional,libraries,audit,leaves=verify_component(path.parent)
        timing=json.loads((path.parent/'full_timing_audit.json').read_text())
        for name,h in timing['source_sha256'].items():
            assert sha256(name)==h,'Changed full timing input: '+name
        results.append(dict(case=path.parent.name,status='VERIFIED',parameters=audit['settings']['parameters'],
                            area_um2=audit['independent_area_um2'],fmax_mhz=timing['estimated_fmax_mhz'],
                            minimum_period_ns=timing['minimum_period_ns'],sram_instances=len(audit['area']['sram_instances']),
                            functional_modules=len(functional),physical_leaves=sum(leaves.values()),
                            netlist_sha256=audit['netlist_sha256']))
        del model;gc.collect()
    results.sort(key=lambda r:r['parameters'][args.parameter])
    old,new=results
    assert old['parameters'].keys()==new['parameters'].keys()
    changed={key:[old['parameters'][key],new['parameters'][key]] for key in old['parameters']
             if old['parameters'][key]!=new['parameters'][key]}
    assert set(changed)=={args.parameter}
    result=dict(status='VERIFIED',scope=__doc__,cpu_ppa_claim=False,results=results,
                effective_parameter_differences=changed,
                area_change_um2=str(Decimal(new['area_um2'])-Decimal(old['area_um2'])),
                area_relative_change=float(Decimal(new['area_um2'])/Decimal(old['area_um2'])-1),
                frequency_relative_change=new['fmax_mhz']/old['fmax_mhz']-1,
                input_sha256={str(p.resolve()):sha256(p) for p in [root/'report.json',Path(__file__),
                    Path(__file__).with_name('audit_component_timing_identity.py'),*paths]})
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
