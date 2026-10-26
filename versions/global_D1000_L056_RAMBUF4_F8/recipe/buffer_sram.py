"""Original RAMBUF4/F8 transformation, with explicit portable input paths.

Consumes Yosys mapped JSON before SRAM boundary buffering. No clock or
non-SRAM connection may change. The output is a Yosys JSON design, not RTL.
"""
import argparse
import copy
import json
from pathlib import Path
import re


def apply(source,lib):
    design=json.loads(source.read_text(encoding='utf-8'))
    modules=design['modules'];top=modules['student_top'];cells=top['cells']
    kind='BUFx4_ASAP7_75t_R';fanout=8
    assert set(modules[kind]['ports'])=={'A','Y'}
    text=lib.read_text(encoding='utf-8');pos=text.index('cell ('+kind+')')
    end=text.find('\n  cell (',pos+10)
    assert re.search(r'function\s*:\s*"A"',text[pos:end if end!=-1 else None])
    old_ram={n:copy.deepcopy(c) for n,c in cells.items() if c['type'].startswith('fakeram_')}
    old_cell_keys=set(cells)
    groups={}
    nextbit=1+max(b for c in cells.values() for bits in c['connections'].values() for b in bits if isinstance(b,int))
    for name,cell in old_ram.items():
        for pin,bits in cell['connections'].items():
            direction=cell.get('port_directions',{}).get(pin,modules[cell['type']]['ports'][pin]['direction'])
            if direction!='input' or pin.lower() in ('clk','clock'):continue
            for index,bit in enumerate(bits):
                if isinstance(bit,int):groups.setdefault(bit,[]).append((name,pin,index))
    added={}

    def buffer(bit,origin):
        nonlocal nextbit
        output=nextbit;nextbit+=1
        name=f'__constr_sram_buffer_{origin}_{len(added)}'
        assert name not in cells
        cell=dict(hide_name=0,type=kind,parameters={},attributes={'keep':'1'},
                  port_directions={'A':'input','Y':'output'},connections={'A':[bit],'Y':[output]})
        cells[name]=cell;added[name]=cell
        top['netnames'][name+'_out']=dict(hide_name=0,bits=[output],attributes={})
        return output

    def tree(bit,sinks,origin):
        output=buffer(bit,origin)
        if len(sinks)<=fanout:
            for name,pin,index in sinks:cells[name]['connections'][pin][index]=output
        else:
            capacity=fanout
            while capacity*fanout<len(sinks):capacity*=fanout
            for offset in range(0,len(sinks),capacity):tree(output,sinks[offset:offset+capacity],origin)

    for bit,sinks in groups.items():
        if len(sinks)>=3:tree(bit,sinks,bit)
    parents={c['connections']['Y'][0]:c['connections']['A'][0] for c in added.values()}

    def resolve(bit):
        seen=set()
        while bit in parents:
            assert bit not in seen
            seen.add(bit);bit=parents[bit]
        return bit

    changes=0
    for name,original in old_ram.items():
        current=cells[name]
        assert current['type']==original['type'] and current['parameters']==original['parameters']
        for pin,bits in original['connections'].items():
            actual=current['connections'][pin];assert len(actual)==len(bits)
            for before,after in zip(bits,actual):
                if before!=after:
                    assert original['port_directions'][pin]=='input' and pin.lower() not in ('clk','clock')
                    assert resolve(after)==before
                    changes+=1
    reference=json.loads(source.read_text(encoding='utf-8'))
    for name in old_cell_keys-set(old_ram):assert cells[name]==reference['modules']['student_top']['cells'][name]
    for name in set(modules)-{'student_top'}:assert modules[name]==reference['modules'][name]
    assert top['ports']==reference['modules']['student_top']['ports']
    return design,dict(buffer_count=len(added),changed_macro_pin_bits=changes,buffer_type=kind,
                       maximum_tree_fanout=fanout,minimum_macro_sinks=3,identity_connectivity_proven=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--invbuf-lib',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():parser.error('preserve existing output; choose a fresh file')
    design,result=apply(args.input,args.invbuf_lib)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
