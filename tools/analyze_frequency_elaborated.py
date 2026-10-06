"""Read existing Yosys JSON snapshots; do not invoke any hardware tool."""
from pathlib import Path
from collections import Counter
import json,hashlib,gc

BASE=Path('F:/CPU2026CourseRuns/current_adopted_20261003/result/synth/opt/elaborated.json')
NEW=Path('F:/CPU2026CourseRuns/architecture_L1_20261004/result/synth/opt/elaborated.json')
OUT=Path('E:/Verilog_cpu/reports/frequency_research_20261003/L1_elaborated_comparison.json')

def inspect(path):
    with path.open() as f:
        data=json.load(f)
    modules=data['modules']
    memo={}
    def summary(name,active=()):
        if name in memo:return memo[name]
        if name in active:raise ValueError('Recursive module hierarchy')
        mod=modules[name]
        kinds=Counter();regs=Counter();used=Counter({name:1})
        for cell in mod.get('cells',{}).values():
            typ=cell['type']
            if typ in modules and not modules[typ].get('attributes',{}).get('blackbox'):
                ck,cr,cu=summary(typ,active+(name,))
                kinds.update(ck);regs.update(cr);used.update(cu)
            else:
                kinds[typ]+=1
                if typ.startswith(('$dff','$adff','$sdff')):
                    regs[typ]+=len(cell['connections']['Q'])
        memo[name]=kinds,regs,used
        return memo[name]
    types,flops,used=summary('student_top')
    ranked=[]
    # This file is hierarchical, so top-level ports alone have one reference.
    # Rank local nets of each reachable implementation, not only student_top.
    for module_name in used:
        ranked.extend(local_nets(modules[module_name],module_name))
    ranked.sort(key=lambda r:-r['weighted_input_references'])
    result=dict(path=str(path),leaf_cells=sum(types.values()),cell_types=dict(types),
                explicit_ff_bits=sum(flops.values()),explicit_ff_bits_by_type=dict(flops),
                priced_BUFx16f_cells=types['BUFx16f_ASAP7_75t_R'],
                reachable_implementation_instances=dict(used),
                high_reference_nets=ranked[:30],
                caveat='Hierarchical RTL intermediate only; explicit FF excludes un-mapped memories. Local mux select/FF control weighted by bus width, not Liberty capacitance, mapped fanout, timing or area; cross-module load not reconstructed')
    del modules,data,memo
    gc.collect()
    return result

def local_nets(module,module_name):
    loads=Counter();aliases={}
    for name,cell in module['cells'].items():
        typ=cell['type']
        for port,bits in cell['connections'].items():
            if cell.get('port_directions',{}).get(port)!='input':
                continue
            weight=1
            if typ=='$mux' and port=='S':
                weight=len(cell['connections']['Y'])
            elif typ.startswith(('$dff','$adff','$sdff')) and port in ('EN','ARST','SRST'):
                weight=len(cell['connections']['Q'])
            for bit in bits:
                if isinstance(bit,int):loads[bit]+=weight
    excluded=set()
    for name,port in module.get('ports',{}).items():
        if name in ('clk','clock','reset','reset_i','clk_i'):
            excluded.update(b for b in port['bits'] if isinstance(b,int))
    chosen=dict((bit,count) for bit,count in loads.most_common(150) if bit not in excluded)
    for name,net in module['netnames'].items():
        if name.startswith('$'):continue
        for index,bit in enumerate(net['bits']):
            if bit in chosen:
                label=name if len(net['bits'])==1 else name+'['+str(index)+']'
                aliases.setdefault(bit,[]).append(label)
    return [dict(module=module_name,bit=b,weighted_input_references=n,aliases=aliases.get(b,[])[:8]) for b,n in sorted(chosen.items(),key=lambda p:-p[1])[:3]]

def main():
    before=inspect(BASE)
    after=inspect(NEW)
    result=dict(status='EXISTING_INTERMEDIATE_NETLIST_ANALYSIS',baseline=before,candidate=after,
                explicit_ff_bit_delta=after['explicit_ff_bits']-before['explicit_ff_bits'],
                priced_buffer_delta=after['priced_BUFx16f_cells']-before['priced_BUFx16f_cells'],
                new_tests_started=False)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','explicit_ff_bit_delta','priced_buffer_delta')}))
    print(json.dumps(dict(candidate_buffers=after['priced_BUFx16f_cells'],candidate_explicit_ff_bits=after['explicit_ff_bits'],top_nets=after['high_reference_nets'][:6])))

if __name__=='__main__':
    main()
