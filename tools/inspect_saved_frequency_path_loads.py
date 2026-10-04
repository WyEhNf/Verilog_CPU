"""Inspect selected gates/aliases/consumers in saved mapped JSON, never EDA."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import re
from pathlib import Path
from census_saved_mapped_fanout import entries


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--roots',nargs='+',required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--path-analysis',type=Path)
    a=p.parse_args()
    assert not a.out.exists()
    path=a.run/'result/synth/opt/design.json'
    measured=json.loads((a.run/'result/timing_only.json').read_text(encoding='utf-8'))
    assert measured['source_manifest_sha256']==sha(a.run/'source_manifest.json')
    assert measured['official_report_sha256']==sha(a.run/'result/synth/opt/report.json')
    roots={}
    for name,c in entries(path,'cells'):
        if name in a.roots:
            roots[name]=c
    resolved={name:name for name in roots}
    if set(roots)!=set(a.roots):
        assert a.path_analysis is not None, 'Private Verilog gate names need an explicit saved path correspondence'
        saved=json.loads(a.path_analysis.read_text(encoding='utf-8'))
        models={name:saved['relevant_instances'][name] for name in a.roots}
        public_ports={}
        wanted_names=set()
        for name,model in models.items():
            specs={}
            for port,value in model['ports'].items():
                if port=='Y' or not value.startswith(('core.','bus.')):
                    continue
                match=re.fullmatch(r'(.*?)\s+\[(\d+)\]',value)
                spec=(match[1],int(match[2])) if match else (value,None)
                specs[port]=spec
                wanted_names.add(spec[0])
            public_ports[name]=specs
        public_bits={}
        for name,n in entries(path,'netnames'):
            if name in wanted_names:
                public_bits[name]=n['bits']
        signatures={}
        for name,specs in public_ports.items():
            signatures[name]={}
            for port,(net,index) in specs.items():
                bs=public_bits[net]
                if index is None:
                    assert len(bs)==1,(net,bs)
                    index=0
                signatures[name][port]=bs[index]
        candidates=defaultdict(list)
        fanouts=Counter()
        for name,c in entries(path,'cells'):
            for port,bs in c['connections'].items():
                if c['port_directions'][port]=='input':
                    fanouts.update(b for b in bs if isinstance(b,int))
            for old,signature in signatures.items():
                if not signature or c['type']!=models[old]['type']:
                    continue
                if all(c['connections'].get(port)==[bit] for port,bit in signature.items()):
                    candidates[old].append((name,c))
        expected_load={d['instance']:d['fanout'] for d in saved['dominant_segments']}
        for old,rows in candidates.items():
            matching=[(name,c) for name,c in rows if fanouts[c['connections']['Y'][0]]==expected_load[old]]
            assert len(matching)==1,(old,[(n,fanouts[c['connections']['Y'][0]]) for n,c in rows])
            name,c=matching[0]
            roots[name]=c
            resolved[old]=name
        # Resolve any intervening private inverter from the already matched
        # input driver, using exact named-Verilog topology and measured load.
        unresolved=set(a.roots)-set(resolved)
        for name,c in entries(path,'cells'):
            if not unresolved:
                break
            for old in list(unresolved):
                model=models[old]
                if model['type']!=c['type'] or not c['type'].startswith('INV'):
                    continue
                for other,m in models.items():
                    if other in resolved and m['ports'].get('Y')==model['ports'].get('A'):
                        bit=roots[resolved[other]]['connections']['Y'][0]
                        if c['connections'].get('A')==[bit] and fanouts[c['connections']['Y'][0]]==expected_load[old]:
                            roots[name]=c
                            resolved[old]=name
                            unresolved.remove(old)
                            break
        assert not unresolved,unresolved
    wanted=set()
    outputs=set()
    for c in roots.values():
        for port,bits in c['connections'].items():
            wanted.update(b for b in bits if isinstance(b,int))
            if c['port_directions'][port]=='output':
                outputs.update(b for b in bits if isinstance(b,int))
    aliases=defaultdict(list)
    for name,n in entries(path,'netnames'):
        if name.startswith(('$abc$','$auto$')):
            continue
        for pos,b in enumerate(n['bits']):
            if b in wanted:
                aliases[b].append(dict(name=name,position=pos,offset=n.get('offset',0),
                    hidden=n.get('hide_name',0),source=n.get('attributes',{}).get('src')))
    consumers=defaultdict(list)
    drivers={}
    for name,c in entries(path,'cells'):
        for port,bits in c['connections'].items():
            if c['port_directions'][port]=='output':
                for b in bits:
                    if b in wanted:
                        drivers[b]=dict(instance=name,type=c['type'],port=port,connections=c['connections'])
            elif c['port_directions'][port]=='input':
                for b in bits:
                    if b in outputs:
                        consumers[b].append(dict(instance=name,type=c['type'],port=port,connections=c['connections']))
    records=[]
    for name,c in roots.items():
        record=dict(instance=name,type=c['type'],ports={})
        for port,bits in c['connections'].items():
            record['ports'][port]=[dict(bit=b,aliases=aliases.get(b,[]),driver=drivers.get(b),
                direct_input_pin_loads=len(consumers.get(b,[])),consumers=consumers.get(b,[])) for b in bits]
        records.append(record)
    a.out.mkdir(exist_ok=False)
    data=dict(status='SELECTED_EXISTING_PATH_GATE_LOAD_ANALYSIS',no_hdl_eda_or_program_run=True,
        run=str(a.run),source_manifest_sha256=measured['source_manifest_sha256'],
        official_report_sha256=measured['official_report_sha256'],design_sha256=sha(path),records=records,
        verilog_to_json_gate_names=resolved,
        correspondence='Exact public input-port bits + cell type + saved STA direct-load count; inverter additionally matched through exact parent output topology.',
        limitation='Saved top-level logical connections and aliases only. Alias presence is evidence of bit equality, not proof of exclusive RTL ownership or timing sensitization.')
    (a.out/'summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    compact=[]
    for r in records:
        compact.append(dict(instance=r['instance'],type=r['type'],ports={
            port:[dict(bit=b['bit'],aliases=[x['name']+'['+str(x['position']+x['offset'])+']' for x in b['aliases'][:8]],
                direct_input_pin_loads=b['direct_input_pin_loads'],
                consumer_types=dict(Counter(x['type'] for x in b['consumers']))) for b in bs]
            for port,bs in r['ports'].items()}))
    print(json.dumps(compact,ensure_ascii=False))


if __name__=='__main__':
    main()
