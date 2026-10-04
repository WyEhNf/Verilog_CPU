"""Trace selected existing mapped drivers backwards; no new hardware runs."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from summarize_course_frequency_native import read, sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--loads',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--indices',type=int,nargs='+',default=[1,4,6,8,9])
    args=parser.parse_args()
    assert not args.out.exists(), 'Preserve earlier source analysis'
    inventory=read(args.loads)
    design_path=args.run/'result/synth/opt/design.json'
    assert inventory['design_sha256']==sha(design_path)
    assert inventory['source_manifest_sha256']==sha(args.run/'source_manifest.json')
    top=read(design_path)['modules']['student_top']
    aliases=defaultdict(list)
    for name, net in top['netnames'].items():
        if net.get('hide_name'):
            continue
        for i, bit in enumerate(net['bits']):
            if isinstance(bit,int):
                aliases[bit].append(name+(f'[{i+net.get("offset",0)}]' if len(net['bits'])>1 else ''))
    drivers={}
    for name, cell in top['cells'].items():
        for port, bits in cell['connections'].items():
            if cell['port_directions'][port]=='output':
                for bit in bits:
                    if isinstance(bit,int):
                        drivers[bit]=(name,port)
    summaries=[]
    for index in args.indices:
        root=inventory['drivers'][index]
        nodes={}
        def walk(bit,depth):
            if not isinstance(bit,int) or bit in nodes:
                return
            names=sorted(set(aliases.get(bit,[])),key=lambda n:(len(n),n))[:8]
            node=dict(bit=bit,depth=depth,aliases=names)
            nodes[bit]=node
            if bit not in drivers:
                node['terminal']='INPUT_OR_UNRESOLVED'
                return
            name, port=drivers[bit]
            cell=top['cells'][name]
            node.update(driver=name,cell=cell['type'],port=port,attributes=cell.get('attributes',{}))
            if depth>=2 and names:
                node['terminal']='NAMED_NET'
                return
            if depth>=9 or len(nodes)>=240 or cell['type'].startswith('DFF') or cell['type'] not in (
                    'rv32_frequency_inversion',) and not cell['type'].endswith('_ASAP7_75t_R'):
                node['terminal']='SEQUENTIAL_HIERARCHICAL_OR_DEPTH_LIMIT'
                return
            inputs=[b for p,bs in cell['connections'].items() if cell['port_directions'][p]=='input' for b in bs]
            node['inputs']=inputs
            for b in inputs:
                walk(b,depth+1)
        walk(root['bit'],0)
        record=dict(index=index,root=root,nodes=list(nodes.values()))
        summaries.append(record)
    result=dict(status='EXISTING_MAPPED_CONE_SOURCE_ANALYSIS',invokes_eda=False,
                source_manifest_sha256=inventory['source_manifest_sha256'],
                design_sha256=inventory['design_sha256'],records=summaries,
                limitation='Bounded top-level backward graph; aliases can reflect shared Boolean expressions, not exclusive semantic ownership.')
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([dict(index=r['index'],root_cell=r['root']['cell'],nodes=len(r['nodes']),
                    named_frontiers=[n['aliases'] for n in r['nodes'] if n['aliases']][:5])
                      for r in summaries],ensure_ascii=False))


if __name__=='__main__':
    main()
