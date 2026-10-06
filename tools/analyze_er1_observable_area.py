"""Conservative output dependency census of the existing mapped ER1 CPU.

Every observed cell output pulls in all cell inputs, including FF D/CLK and
all RAM inputs. Hierarchical cells are indivisible. This can overestimate live
logic; it must not underestimate it. No HDL/EDA/program execution occurs.
"""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from manage_frozen_baseline_programs import sha, write

RUN=Path('F:/CPU2026CourseRuns/architecture_ER1_20261005')
OUT=Path('F:/CPU2026Proofs/ER1_observable_area_20261005.json')


def main():
    assert not OUT.exists()
    directory=RUN/'result/synth/opt'
    modules=json.loads((directory/'design.json').read_text())['modules']
    stats=json.loads((directory/'stat.json').read_text())['modules']
    area=json.loads((directory/'area.json').read_text())
    top=modules['student_top']
    cells=list(top['cells'].items())
    drivers=defaultdict(list)
    inputs=[]
    prices=[]
    sequential=[]
    for index,(name,cell) in enumerate(cells):
        kind=cell['type']
        module=modules[kind]
        attrs=module.get('attributes',{})
        stat=stats.get(kind,stats.get('\\'+kind))
        price=float(stat['area']) if stat else float(attrs['area'])
        seq=float(stat['sequential_area']) if stat else price if kind.startswith('DFF') else 0.
        prices.append(price);sequential.append(seq)
        inp=set()
        for port,bits in cell['connections'].items():
            direction=cell['port_directions'][port]
            assert direction in ('input','output'), (name,port,direction)
            for bit in bits:
                if isinstance(bit,int):
                    if direction=='input':inp.add(bit)
                    else:drivers[bit].append(index)
        inputs.append(inp)
    assert math.isclose(sum(prices),area['area_um2'],abs_tol=1e-4), (sum(prices),area['area_um2'])
    pending=[b for p in top['ports'].values() if p['direction']=='output' for b in p['bits'] if isinstance(b,int)]
    observed_bits=set()
    live_cells=set()
    while pending:
        bit=pending.pop()
        if bit in observed_bits:continue
        observed_bits.add(bit)
        for index in drivers.get(bit,()):
            if index in live_cells:continue
            live_cells.add(index)
            pending.extend(inputs[index]-observed_bits)
    dead_groups=defaultdict(lambda:dict(cells=0,area_um2=0.,sequential_area_um2=0.,samples=[]))
    dead_src=Counter()
    dead_names=[]
    for index,(name,cell) in enumerate(cells):
        if index in live_cells:continue
        row=dead_groups[cell['type']]
        row['cells']+=1;row['area_um2']+=prices[index];row['sequential_area_um2']+=sequential[index]
        if len(row['samples'])<4:row['samples'].append(name)
        dead_names.append(name)
        if cell['type'].startswith('DFF'):dead_src[cell.get('attributes',{}).get('src','NO_SRC')]+=1
    dead_area=sum(r['area_um2'] for r in dead_groups.values())
    result=dict(status='SAVED_MAPPED_CONSERVATIVE_OUTPUT_DEPENDENCY_CENSUS', original_run=str(RUN),
                source_manifest_sha256=sha(RUN/'source_manifest.json'),
                input_sha256={n:sha(directory/n) for n in ('design.json','stat.json','area.json')},
                output_ports=sorted(n for n,p in top['ports'].items() if p['direction']=='output'),
                total_area_um2=area['area_um2'], top_cell_count=len(cells), observable_cells=len(live_cells),
                unobserved_cell_count=len(cells)-len(live_cells), unobserved_area_um2=dead_area,
                unobserved_sequential_area_um2=sum(r['sequential_area_um2'] for r in dead_groups.values()),
                conservative_observable_area_um2=area['area_um2']-dead_area,
                unobserved_groups=[dict(cell_type=k,**v) for k,v in sorted(dead_groups.items(),key=lambda kv:kv[1]['area_um2'],reverse=True)],
                unobserved_ff_source_counts=dict(dead_src), unobserved_top_cell_names=dead_names,
                scope='All top outputs, complete FF feedback and macro input dependencies. Does not authorize removing architecturally observable state inside a used hierarchical cell.',
                limitation='Existing physical mapping census, not a newly mapped candidate area/frequency/IPC. RTL pruning needs source ownership review.',
                new_synthesis_run=False,new_simulation_run=False)
    write(OUT,result)
    print(json.dumps({k:result[k] for k in ('status','total_area_um2','unobserved_cell_count','unobserved_area_um2','unobserved_sequential_area_um2','conservative_observable_area_um2','unobserved_ff_source_counts')},ensure_ascii=False))


if __name__=='__main__':main()
