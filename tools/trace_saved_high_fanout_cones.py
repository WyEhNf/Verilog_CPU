"""Trace private mapped control nets to named boundaries in saved JSON only."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from census_saved_mapped_fanout import entries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json',type=Path,required=True)
    p.add_argument('--census',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    census=json.loads(a.census.read_text(encoding='utf-8'))
    starts=census['ranked_loads'][:4]
    edges=defaultdict(list)
    for name,c in entries(a.json,'cells'):
        inp=set()
        out=[]
        for port,values in c.get('connections',{}).items():
            direction=c['port_directions'].get(port)
            if direction=='input' and port not in ('CLK','clock','clk_i'):
                inp.update(v for v in values if isinstance(v,int))
            elif direction=='output':
                out.extend(v for v in values if isinstance(v,int))
        edge=(name,c['type'],tuple(out))
        for v in inp:
            edges[v].append(edge)
    results=[]
    wanted=set()
    for start in starts:
        visited={start['bit']:0}
        frontier={start['bit']}
        boundaries=[]
        seq=[]
        for depth in range(1,7):
            nxt=set()
            for v in sorted(frontier):
                for name,kind,outputs in edges.get(v,[]):
                    is_seq=kind.startswith('DFF') or 'sram' in kind.lower()
                    if name.startswith(('core.','bus.')):
                        if len(boundaries)<120:
                            boundaries.append(dict(depth=depth,instance=name,type=kind,input_bit=v,outputs=outputs))
                        wanted.add(v)
                        wanted.update(outputs)
                        # Named primitive boundaries are the intended RTL
                        # locality point; avoid flooding their wider cone.
                        continue
                    if is_seq:
                        if len(seq)<50:
                            seq.append(dict(depth=depth,instance=name,type=kind,outputs=outputs))
                        wanted.update(outputs)
                        continue
                    for out in outputs:
                        if out not in visited:
                            visited[out]=depth
                            nxt.add(out)
            frontier=nxt
            if not frontier:
                break
        results.append(dict(start=start,visited_bits=len(visited),boundaries=boundaries,
                            sequential_stops=seq))
    aliases=defaultdict(list)
    for name,n in entries(a.json,'netnames'):
        if name.startswith(('$abc$','$auto$')):
            continue
        for pos,bit in enumerate(n['bits']):
            if bit in wanted:
                aliases[bit].append(dict(name=name,position=pos))
    data=dict(status='SAVED_MAPPED_LOGICAL_CONE_TRACE_ONLY',no_hdl_eda_or_program_run=True,
              input=str(a.json),roots=results,aliases=dict(aliases),
              limitation='Top-level mapped connectivity, up to six combinational gates and stopping at named boundaries/clocked cells. Reachability alone is not sensitization, delay, correctness or DY/DZ timing evidence.')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    assert not a.out.exists()
    a.out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    for r in results:
        print(json.dumps(dict(loads=r['start']['input_pin_loads'],root_type=r['start']['driver']['type'],
            boundaries=r['boundaries'][:30],seq_count=len(r['sequential_stops']))))


if __name__=='__main__':main()
