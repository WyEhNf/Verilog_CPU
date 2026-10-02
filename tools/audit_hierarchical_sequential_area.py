"""Price every actual flip-flop across retained functional CPU hierarchy.

Use unmodified raw sequential-library prices and exact prepared cell names.
Signal grouping is diagnostic attribution, not a sum of complete module area.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import re

from verify_course_axi_area import sha256, verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    assert not args.out.exists(), 'Preserve earlier evidence'
    directory=args.directory.resolve()
    checked=verify(directory)
    prepared=directory/'prepared.il'
    preparation=json.loads((directory/'prepare.done.json').read_text())
    assert sha256(prepared)==preparation['output_sha256']['prepared.il']
    flops,inversions={},{}
    module,active,ports=None,None,{}
    with prepared.open() as stream:
        for line in stream:
            if line.startswith('module '):
                module=line.split()[1].lstrip('\\')
            elif line.startswith('  cell '):
                kind,name=line.split()[1:3]
                active=(kind.lstrip('\\'),name.lstrip('\\')) if kind.startswith('\\DFF') or (kind=='$_NOT_' and 'dfflibmap' in name) else None
                ports={}
            elif active and line.startswith('    connect '):
                pin,signal=line.strip().split(' ',2)[1:]
                ports[pin.lstrip('\\')]=signal
            elif active and line.strip()=='end':
                kind,name=active
                if kind=='$_NOT_': inversions[(module,ports['A'])]=ports['Y']
                else: flops[(module,name)]=(kind,dict(ports))
                active=None
    audit=json.loads((directory/'area_audit.json').read_text())
    prices={}
    for entry in audit['libraries']:
        path=Path(entry['path'])
        if '_SEQ_' not in path.name:continue
        assert sha256(path)==entry['sha256']
        for name,body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',path.read_text(),re.S):
            match=re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)',body,re.M)
            assert match
            prices[name]=Decimal(match[1])
    models=json.loads((directory/'design.json').read_text())['modules']
    amounts,counts,unresolved=defaultdict(Decimal),Counter(),[]
    kinds=Counter()
    def visit(module,scope,parents=()):
        assert module not in parents
        for name,cell in models[module]['cells'].items():
            kind=cell['type']
            if kind in prices:
                original=flops.get((module,name))
                signals=[]
                if original:
                    assert original[0]==kind
                    for pin,signal in original[1].items():
                        if pin not in ('Q','QN'):continue
                        signals.append(inversions.get((module,signal),signal))
                if len(signals)==1 and signals[0].startswith('\\') and not signals[0].startswith('\\$'):
                    field=signals[0].split()[0].lstrip('\\')
                    label=scope+field
                    owner=label.rsplit('.',1)[0] if '.' in label else 'student_top'
                else:
                    owner=scope+'UNRESOLVED'
                    if len(unresolved)<30:unresolved.append(dict(scope=scope,module=module,cell=name,signals=signals))
                counts[owner]+=1;amounts[owner]+=prices[kind];kinds[kind]+=1
            elif kind in models and models[kind].get('cells'):
                visit(kind,scope+name+'.',parents+(module,))
    visit('student_top','')
    total=sum(amounts.values(),Decimal(0))
    assert total==Decimal(checked['area']['sequential_area_um2']), 'Not every physical sequential cell was priced'
    assert kinds==Counter({k:v for k,v in audit['leaf_counts'].items() if k in prices})
    groups=[dict(scope=key,flip_flops=counts[key],area_um2=str(value)) for key,value in sorted(amounts.items(),key=lambda item:item[1],reverse=True)]
    result=dict(status='COMPLETE',scope=__doc__,netlist_sha256=checked['netlist_sha256'],
                actual_flip_flops=sum(kinds.values()),sequential_area_um2=str(total),groups=groups,
                unresolved_examples=unresolved,not_complete_module_area=True,
                input_sha256={str(p):sha256(p) for p in [directory/'design.json',prepared,directory/'area_audit.json',Path(__file__).resolve()]})
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='COMPLETE',actual_flip_flops=sum(kinds.values()),area_um2=str(total),largest_groups=groups[:15]),indent=2))


if __name__=='__main__':main()
