"""Trace saved MSHR register D cones to named lifecycle bits; no EDA run."""
import argparse
import hashlib
import json
from pathlib import Path
from census_saved_mapped_fanout import entries


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--design',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    assert not a.out.exists()
    saved=json.loads(a.inputs.read_text(encoding='utf-8'))
    assert saved['design_sha256']==sha(a.design)
    roots=[r for r in saved['records'] if r['bit'] in (860,872,884,896)]
    assert len(roots)==4
    drivers={}
    for name,c in entries(a.design,'cells'):
        inputs=tuple(b for port,bs in c['connections'].items()
                     if c['port_directions'][port]=='input' and port not in ('CLK','clk_i','clock') for b in bs)
        record=(name,c['type'],inputs)
        for port,bs in c['connections'].items():
            if c['port_directions'][port]=='output':
                for b in bs:
                    if isinstance(b,int):
                        drivers[b]=record
    records=[]
    for root in roots:
        bit=root['driver']['connections']['D'][0]
        visited={}
        def walk(b,depth):
            if not isinstance(b,int) or b in visited:
                return
            n=dict(bit=b,depth=depth)
            visited[b]=n
            if b not in drivers:
                n['terminal']='INPUT_OR_UNRESOLVED'
                return
            name,kind,inputs=drivers[b]
            n.update(instance=name,type=kind)
            if name.startswith(('core.','bus.')):
                n['terminal']='NAMED_HIERARCHICAL_BOUNDARY'
            elif kind.startswith('DFF'):
                n['terminal']='EXISTING_REGISTER'
            elif depth>=9 or len(visited)>=600:
                n['terminal']='DEPTH_OR_SIZE_LIMIT'
            else:
                n['inputs']=inputs
                for i in inputs:
                    walk(i,depth+1)
        walk(bit,0)
        named=[n for n in visited.values() if n.get('terminal')=='NAMED_HIERARCHICAL_BOUNDARY']
        records.append(dict(root_register_QN_bit=root['bit'],register=root['driver'],D_bit=bit,
                            nodes=list(visited.values()),named_frontiers=named))
    a.out.mkdir(exist_ok=False)
    result=dict(status='SAVED_REGISTER_INPUT_LOGICAL_CONES',no_hdl_eda_or_program_run=True,
        input=str(a.inputs),input_sha256=sha(a.inputs),design_sha256=saved['design_sha256'],
        source_manifest_sha256=saved['source_manifest_sha256'],records=records,
        limitation='Logical reach to named lifecycle bits; not timing sensitization or formal equivalence. Sequential feedback stops at existing QN nodes.')
    (a.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([dict(QN_bit=r['root_register_QN_bit'],nodes=len(r['nodes']),
        named=[n['instance'] for n in r['named_frontiers']]) for r in records],ensure_ascii=False))


if __name__=='__main__':
    main()
