"""Attribute frozen A21 timing endpoint using its existing mapped netlist."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import read, sha, write

RUN=Path('F:/CPU2026CourseRuns/ER1_A21_tier3_20261005')
OUT=Path('F:/CPU2026Proofs/ER1_A21_critical_mdu_endpoint_20261005.json')


def main():
    assert not OUT.exists()
    root=RUN/'result/synth/opt'
    design=read(root/'design.json')['modules']['student_top']
    text=(root/'mapped.v').read_text(encoding='utf-8')
    text=text[text.index('module student_top('):]
    text=text[:text.index('\nendmodule')]
    mapped=[(m[1],m[2],m[3]) for m in re.finditer(
        r'^  ([A-Za-z][A-Za-z0-9_$]*) (_[0-9]+_) \(\n(.*?)\n  \);',text,re.M|re.S)]
    private=[(name,cell) for name,cell in sorted(design['cells'].items()) if name.startswith('$')]
    assert len(mapped)==len(private)==235684
    assert all(m[0]==j[1]['type'] for m,j in zip(mapped,private))
    lookup={m[1]:(m,j) for m,j in zip(mapped,private)}
    names=['_432259_','_338495_','_371714_','_372056_','_403561_','_403562_','_430425_']
    records=[]
    for name in names:
        m,j=lookup[name]
        records.append(dict(mapped_cell=name,json_cell=j[0],type=m[0],
            source=j[1].get('attributes',{}).get('src'),connections=j[1]['connections']))
    edges=[('_338495_','Y','_371714_','B'),('_371714_','Y','_372056_','A'),
           ('_372056_','Y','_403561_','B'),('_372056_','Y','_403562_','B'),
           ('_403562_','Y','_430425_','D')]
    for first,p,second,q in edges:
        assert lookup[first][1][1]['connections'][p]==lookup[second][1][1]['connections'][q]
        a=re.search(r'\.'+p+r'\(([^)]+)\)',lookup[first][0][2])[1]
        b=re.search(r'\.'+q+r'\(([^)]+)\)',lookup[second][0][2])[1]
        assert a==b,(first,second,a,b)
    assert 'rv32m_mdu_iterative.v:246.5-296.8' in records[-1]['source']
    assert 'rv32_axi_lite_bridge.v:550.5-563.8' in records[0]['source']
    critical=read(root/'critical_paths.json')['checks'][0]
    assert critical['startpoint']=='_432259_/QN' and critical['endpoint']=='_430425_/D'
    nodes=[]
    for node in critical['source_path']:
        if node.get('instance') in names:
            nodes.append({k:node.get(k) for k in ('instance','pin','cell','arrival','capacitance','slew')})
    proof=dict(status='FROZEN_A21_EXISTING_NETLIST_MDU_ENDPOINT_SOURCE_ATTRIBUTED',
        recorded_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),
        mapped_verilog_sha256=sha(root/'mapped.v'),mapped_design_sha256=sha(root/'design.json'),
        critical_paths_sha256=sha(root/'critical_paths.json'),
        private_top_cell_count=235684,ordered_cell_type_mismatches=0,
        critical_edge_port_connections_verified_in_both_artifacts=edges,
        attributed_cells=records,timing_nodes=nodes,
        endpoint_source_module='rv32m_mdu_iterative',endpoint_state_field_not_identified=True,
        new_hdl_execution=False,new_synthesis=False,new_sta=False,new_cpu_tests=False,
        conclusion='A21 worst reported path ends in the shared iterative MDU clocked state, not an assumed PRF/RS row. Late accept/control drivers have large capacitive load; distribute payload writes into bounded word owners without adding arithmetic/issue pipeline latency.',
        limitation='Source attribution uses identical ordered types for every private top cell and verified interconnect for the selected critical tail. It is not whole-core equivalence and does not predict A36 or future frequency.')
    write(OUT,proof)
    print({k:proof[k] for k in ('status','private_top_cell_count','endpoint_source_module','endpoint_state_field_not_identified','new_sta')})


if __name__=='__main__':main()
