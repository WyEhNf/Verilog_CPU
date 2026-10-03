"""Resolve every inventory endpoint through the previously verified naming map."""
from collections import Counter
from pathlib import Path
import csv, json, re
from audit_component_timing_identity import declarations
from audit_cpu_sequential_ownership import prepared_registers
from report_frequency_paths import AREA, OUT, sha, linux, run

PROOF = Path('F:/CPU2026Proofs/frequency_combined_v2_identity_20261003')

def group(signal):
    return re.sub(r'\[\d+(?::\d+)?\]', '[]', signal).replace('\\','').strip()

def subsystem(s):
    for needle, name in [('dcache','Dcache'),('icache','Icache'),('.lsq.','LSQ'),
        ('.rob.','ROB'),('.rs.','RS'),('.prf.','PRF'),('muldiv','MDU'),
        ('.mdu.','MDU'),('frontend','Frontend'),('decode','Decode'),
        ('axi','AXI'),('adapter','AXI'),('rename','Rename'),('rat.','Rename')]:
        if needle in s.lower(): return name
    return 'Backend' if 'backend' in s else 'Top/Other'

def main():
    proof = json.loads((PROOF/'identity.json').read_text())
    assert proof['complete_hierarchical_wiring_identical']
    used = [PROOF/'normal.v',PROOF/'original.v',AREA/'design.json',AREA/'mapped.v',AREA/'prepared.il']
    for p in used:
        assert sha(p) == proof['input_sha256'][str(p.resolve())], str(p)
    print('Verified frozen naming evidence',flush=True)
    model = json.loads((AREA/'design.json').read_text())['modules']
    a,b = declarations(PROOF/'normal.v'), declarations(PROOF/'original.v')
    assert len(a)==len(b)
    names={}
    for (scope,kind,printed),(scope2,kind2,original) in zip(a,b):
        assert scope==scope2 and kind==kind2
        assert model[scope]['cells'][original]['type']==kind
        names[(scope,original)]=printed
    del a,b
    seq={c['type'] for m in model.values() for c in m.get('cells',{}).values() if c['type'].startswith(('DFF','SDFF'))}
    flops,inversions=prepared_registers(AREA/'prepared.il',seq)
    cells={}
    def visit(scope,prefix):
        for name,cell in model[scope]['cells'].items():
            printed=names[(scope,name)]
            path=prefix+printed
            kind=cell['type']
            if kind in model and not model[kind].get('attributes',{}).get('blackbox'):
                visit(kind,path+'/')
            else:
                signal=''
                if (scope,name) in flops:
                    k,ports=flops[(scope,name)]
                    assert k==kind
                    q=next(p for p in ports if p in ('Q','QN'))
                    signal=inversions.get((scope,ports[q]),ports[q]).lstrip('\\')
                cells[path]=(scope,name,kind,(prefix+signal if signal else path))
    visit('student_top','')
    assert len(cells)==proof['actual_leaf_instances'],len(cells)
    def resolve(pin):
        if '/' not in pin: return dict(rtl=pin,kind='port',subsystem='AXI' if pin!='clock' else 'Clock')
        path,port=pin.rsplit('/',1)
        scope,name,kind,signal=cells[path]
        if kind.startswith('fakeram'): signal=path+'/'+port
        return dict(rtl=signal,kind=kind,subsystem=subsystem(signal))
    rows=[]
    for r in csv.DictReader((OUT/'endpoint_paths.tsv').open(),delimiter='\t'):
        r.update({k:float(r[k]) for k in ('arrival_ns','required_ns','slack_ns')})
        r['start']=resolve(r['startpoint']); r['end']=resolve(r['endpoint'])
        r['family']=group(r['end']['rtl'])
        # All clocks are ideal and single-cycle: translating required time from 2 ns to 10/3 ns is exact here.
        r['slack_300_ns']=r['slack_ns']+10/3-2
        rows.append(r)
    rows.sort(key=lambda r:r['arrival_ns'],reverse=True)
    assert len({r['endpoint'] for r in rows})==len(rows)
    for i,r in enumerate(rows,1): r['rank']=i
    families={}; systems={}
    for r in rows:
        families.setdefault(r['family'],[]).append(r)
        systems.setdefault(r['end']['subsystem'],[]).append(r)
    representatives={rs[0]['endpoint']:rs[0] for rs in families.values()}
    # Every endpoint field receives a representative full gate path, not just a global top-N.
    reps=sorted(representatives.values(),key=lambda r:r['arrival_ns'],reverse=True)
    for i,r in enumerate(reps,1): r['representative_id']=i
    (OUT/'resolved_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'representatives.json').write_text(json.dumps(reps,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(paths=len(rows),families=len(families),systems={s:dict(count=len(rs),worst=rs[0]) for s,rs in systems.items()}),ensure_ascii=False,indent=2),flush=True)
    # Save pin fanout for representative path analysis, scoped to physical module connections.
    fanouts={}
    for scope in {v[0] for v in cells.values()}:
        fanouts[scope]=Counter(bit for c in model[scope]['cells'].values() for p,bits in c['connections'].items()
            if c['port_directions'][p]=='input' and p!='CLK' for bit in bits if isinstance(bit,int))
    used_paths=set()
    # All cell metadata stays diagnostic; no source, mapping or constraint changes.
    cell_data={}
    for path,(scope,name,kind,signal) in cells.items():
        cell=model[scope]['cells'][name]
        cell_data[path]=dict(rtl=signal,kind=kind,outputs={p:sum(fanouts[scope][b] for b in bits if isinstance(b,int))
            for p,bits in cell['connections'].items() if cell['port_directions'][p]=='output'})
    (OUT/'cell_identity.json').write_text(json.dumps(cell_data,ensure_ascii=False),encoding='utf-8')
    commands=[]
    for r in reps:
        pin=r['endpoint']; n=r['representative_id']
        cmd=f'get_ports {{{pin}}}' if '/' not in pin else f'get_pins {{{pin}}}'
        commands += [f'set dest [{cmd}]',f'if {{[llength $dest] != 1}} {{error "Unresolved endpoint {n}"}}',
            f'report_checks -to $dest -path_delay max -group_path_count 1 -format json > "{linux(OUT)}/family_{n:04}.json"']
    commands.append(f'puts "FAMILY_REPORTS {len(reps)}"')
    run('families','\n'.join(commands))
    print('COMPLETE representative gate reports',flush=True)

if __name__=='__main__': main()
