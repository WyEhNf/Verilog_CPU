"""Resolve CPU timing names only when a read-only re-export is byte identical.

Require equality of the entire original physical Verilog and fresh normal
export before pairing normal/norename names. No mapping, optimization, library
substitution or graph alteration is run. Fail closed on any byte difference.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from audit_cpu_sequential_ownership import prepared_registers

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def declarations(path):
    scope=None
    with path.open() as stream:
        for line in stream:
            start=re.match(r'^module\s+([^\s(]+)',line)
            if start:scope=start[1].lstrip('\\')
            cell=re.match(r'^  (\\\S+|[A-Za-z_$][\w$]*)\s+(\\\S+|[A-Za-z_$][\w$]*)\s+\($',line)
            if cell:yield scope,cell[1].lstrip('\\'),cell[2].lstrip('\\')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cpu',type=Path)
    parser.add_argument('--outdir',type=Path,required=True)
    parser.add_argument('--cell',action='append',required=True)
    args=parser.parse_args()
    cpu,out=args.cpu.resolve(),args.outdir.resolve()
    assert not out.exists()
    result_path=cpu/'verified_cpu_result.json'
    verified=json.loads(result_path.read_text())
    assert verified['status']=='VERIFIED'
    inputs=dict(verified['input_sha256'])
    inputs[str(result_path)]=sha(result_path)
    for path,h in inputs.items():assert sha(path)==h.lower(),path
    area=cpu/'area'
    assert sha(area/'mapped.v')==verified['netlist_sha256']
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    binary=suite/'bin/yosys.exe'
    for path in (area/'design.json',area/'prepared.il',area/'timing.rpt',binary,
                 Path(__file__).resolve(),ROOT/'tools/audit_cpu_sequential_ownership.py'):
        inputs[str(path)]=sha(path)
    out.mkdir(parents=True)
    normal,original=out/'normal.v',out/'original.v'
    script,log=out/'names.ys',out/'names.log'
    q=lambda p:'"'+p.as_posix()+'"'
    script.write_text('\n'.join(['read_json '+q(area/'design.json'),
        'write_verilog -noattr -noexpr '+q(normal),
        'write_verilog -noattr -noexpr -norename '+q(original)])+'\n')
    env=dict(os.environ)
    env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    print('START readonly name export',flush=True)
    with log.open('w') as stream:
        subprocess.run([str(binary),'-T','-s',str(script)],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
    assert sha(normal)==sha(area/'mapped.v'), 'Re-export differs: do not infer name identity from ordering'
    print('VERIFIED byte-identical full physical netlist export',flush=True)
    modules=json.loads((area/'design.json').read_text())['modules']
    pairs={};seen=set();count=0
    a,b=iter(declarations(normal)),iter(declarations(original))
    while True:
        left,right=next(a,None),next(b,None)
        if left is None or right is None:
            assert left is right is None;break
        scope,kind,printed=left
        other_scope,other_kind,name=right
        assert scope==other_scope and kind==other_kind
        assert (scope,name) not in seen and modules[scope]['cells'][name]['type']==kind
        seen.add((scope,name));count+=1
        if scope=='student_top' and printed in args.cell:
            assert printed not in pairs
            pairs[printed]=(name,modules[scope]['cells'][name])
    assert count==sum(len(m['cells']) for m in modules.values())
    assert set(pairs)==set(args.cell)
    seq={cell['type'] for name,cell in pairs.values() if cell['type'].startswith('DFF')}
    flops,inversions=prepared_registers(area/'prepared.il',seq)
    root=modules['student_top'];bits=set()
    for name,cell in pairs.values():
        bits.update(v for pin,values in cell['connections'].items() if cell['port_directions'][pin]=='output' for v in values if type(v) is int)
    fanout=Counter()
    for cell in root['cells'].values():
        for pin,values in cell['connections'].items():
            if cell['port_directions'][pin]=='input' and pin!='CLK':
                fanout.update(v for v in values if v in bits)
    aliases={v:[] for v in bits}
    for name,net in root['netnames'].items():
        if not net['hide_name']:
            for i,v in enumerate(net['bits']):
                if v in bits:aliases[v].append(f'{name}[{i}]')
    rows=[]
    for printed in args.cell:
        name,cell=pairs[printed];flop=flops.get(('student_top',name))
        signals={}
        if flop:
            assert flop[0]==cell['type']
            for pin,signal in flop[1].items():
                if pin in ('Q','QN'):signals[pin]=inversions.get(('student_top',signal),signal)
        rows.append(dict(printed=printed,original=name,cell_type=cell['type'],connections=cell['connections'],
            prepared_q_signals=signals,outputs={pin:[dict(bit=v,root_pin_fanout=fanout[v],aliases=aliases.get(v,[])) for v in values]
                for pin,values in cell['connections'].items() if cell['port_directions'][pin]=='output'}))
    for path,h in inputs.items():assert sha(path)==h.lower(),path
    for path in (script,log,normal,original):inputs[str(path)]=sha(path)
    report=dict(status='VERIFIED',diagnostic_only=True,input_is_full_cpu=True,
                complete_physical_netlist_byte_identical=True,no_synthesis_or_mapping_run=True,
                name_pairs_checked=count,physical_leaves=verified['leaf_instances'],sram_instances=verified['sram_instances'],
                netlist_sha256=verified['netlist_sha256'],rows=rows,input_sha256=inputs)
    (out/'identity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','complete_physical_netlist_byte_identical','physical_leaves','sram_instances','rows')},indent=2))


if __name__=='__main__':main()
