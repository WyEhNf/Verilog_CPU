"""Read frozen A41 STA/netlist artifacts; do not invoke HDL or timing tools."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import read, sha, write

RUN = Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
OUT = Path('F:/CPU2026Proofs/ER1_A41_critical_frontend_owner_20261005.json')


def main():
    assert not OUT.exists()
    root = RUN/'result/synth/opt'
    design = read(root/'design.json')['modules']['student_top']
    verilog = (root/'mapped.v').read_text(encoding='utf-8')
    text = verilog[verilog.index('module student_top('):]
    text = text[:text.index('\nendmodule')]
    mapped = [(m[1],m[2],m[3]) for m in re.finditer(
        r'^  ([A-Za-z][A-Za-z0-9_$]*) (_[0-9]+_) \(\n(.*?)\n  \);',text,re.M|re.S)]
    private = [(name,cell) for name,cell in sorted(design['cells'].items()) if name.startswith('$')]
    assert len(mapped) == len(private)
    assert all(m[0] == j[1]['type'] for m,j in zip(mapped,private))
    lookup = {m[1]:(m,j) for m,j in zip(mapped,private)}
    critical = read(root/'critical_paths.json')['checks']
    first = critical[0]
    start = first['startpoint'].split('/')[0]
    end = first['endpoint'].split('/')[0]
    nodes = first['source_path']
    increments = []
    previous = 0
    for node in nodes:
        arrival = node.get('arrival',previous)
        delta = arrival - previous
        previous = arrival
        if delta > 0:
            increments.append(dict(instance=node['instance'],pin=node['pin'],cell=node['cell'],
                delay_ns=delta*1e9,arrival_ns=arrival*1e9,
                capacitance_ff=node.get('capacitance',0)*1e15,
                slew_ns=node.get('slew',0)*1e9))
    largest = sorted(increments,key=lambda n:n['delay_ns'],reverse=True)[:12]
    names = list(dict.fromkeys([start,end]+[n['instance'] for n in largest if n['instance'] in lookup]))
    records = []
    for name in names:
        m,j = lookup[name]
        outputs = {b for port,bits in j[1]['connections'].items()
            if j[1]['port_directions'][port]=='output' for b in bits}
        aliases = []
        for signal, net in design['netnames'].items():
            if signal.startswith(('_','$')):
                continue
            overlap = [(i,b) for i,b in enumerate(net['bits']) if b in outputs]
            if overlap:
                aliases.append(dict(signal=signal,bits=overlap))
        records.append(dict(mapped_cell=name,json_cell=j[0],type=m[0],
            source=j[1].get('attributes',{}).get('src'),
            connections=j[1]['connections'],output_aliases=aliases))
    verified = []
    for a,b in zip(nodes,nodes[1:]):
        if a['instance'] == b['instance'] or a['instance'] not in lookup or b['instance'] not in lookup:
            continue
        ap=a['pin'].split('/')[-1]; bp=b['pin'].split('/')[-1]
        ja=lookup[a['instance']][1][1]; jb=lookup[b['instance']][1][1]
        assert ja['connections'][ap] == jb['connections'][bp]
        ma=re.search(r'\.'+ap+r'\(([^)]+)\)',lookup[a['instance']][0][2])[1]
        mb=re.search(r'\.'+bp+r'\(([^)]+)\)',lookup[b['instance']][0][2])[1]
        assert ma == mb
        verified.append([a['pin'],b['pin']])
    proof = dict(status='A41_FROZEN_EXISTING_FRONTEND_CRITICAL_PATH_SOURCE_ATTRIBUTION',
        recorded_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),
        mapped_verilog_sha256=sha(root/'mapped.v'),mapped_design_sha256=sha(root/'design.json'),
        critical_paths_sha256=sha(root/'critical_paths.json'),
        private_top_cell_count=len(private),ordered_cell_type_mismatches=0,
        top_paths=[{k:c[k] for k in ('startpoint','endpoint','data_arrival_time','required_time','slack')} for c in critical[:5]],
        largest_cell_increments=largest,attributed_cells=records,
        critical_edge_port_connections_verified_in_both_artifacts=verified,
        new_hdl_execution=False,new_synthesis=False,new_sta=False,new_cpu_tests=False,
        limitation='Existing artifact attribution only. No whole-core equivalence, no IPC causal attribution and no future frequency prediction.')
    write(OUT,proof)
    print({k:proof[k] for k in ('status','private_top_cell_count','new_sta')})
    print('worst',proof['top_paths'][0])
    for record in records:
        print({k:record[k] for k in ('mapped_cell','source','output_aliases')})


if __name__=='__main__':
    main()
