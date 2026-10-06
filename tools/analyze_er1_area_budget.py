"""Attribute saved ER1 area and register aliases without invoking HDL tools."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from manage_frozen_baseline_programs import sha, write

RUN = Path('F:/CPU2026CourseRuns/architecture_ER1_20261005')
OUT = Path('F:/CPU2026Proofs/ER1_target_area_budget_20261005.json')


def family(name):
    if '.backend.rob.' in name: return 'ROB'
    if '.backend.rs.' in name: return 'INT_RS'
    if '.backend.prf.' in name: return 'PRF'
    if '.backend.rename.' in name: return 'RENAME'
    if '.backend.lsq.' in name: return 'LSQ'
    if '.backend.' in name: return 'OTHER_BACKEND'
    if '.dcache.' in name: return 'DCACHE'
    if '.icache.' in name: return 'ICACHE'
    if '.predictor' in name or '.g_bank[' in name: return 'PREDICTOR'
    if '.frontend.' in name: return 'FRONTEND'
    if '.axi' in name or 'bridge.' in name: return 'MEMORY_BRIDGE'
    return 'OTHER'


def main():
    assert not OUT.exists()
    directory = RUN/'result/synth/opt'
    area = json.loads((directory/'area.json').read_text())
    stats = json.loads((directory/'stat.json').read_text())
    tree = area['module_tree']
    grouped = defaultdict(lambda: dict(instances=0, area_um2=0., sequential_area_um2=0., sram_area_um2=0.))
    stack = [tree]
    while stack:
        node = stack.pop()
        row = grouped[node['source_module']]
        row['instances'] += 1
        for key in ('area_um2','sequential_area_um2','sram_area_um2'):
            row[key] += node['direct'][key]
        stack.extend(node['children'])
    for key in ('area_um2','sequential_area_um2','sram_area_um2'):
        assert math.isclose(sum(r[key] for r in grouped.values()), area[key], abs_tol=1e-5)
    design = json.loads((directory/'design.json').read_text())
    top = design['modules']['student_top']
    aliases = defaultdict(set)
    for name, net in top['netnames'].items():
        if net.get('hide_name'):
            continue
        for bit in net['bits']:
            if isinstance(bit, int): aliases[bit].add(name)
    # Trace only polarity-restoring one-input inverters, never functional gates.
    followers = defaultdict(set)
    for cell in top['cells'].values():
        kind = cell['type']
        if kind == 'rv32_frequency_inversion':
            inp, out = 'signal_i', 'signal_o'
        elif kind.startswith('INV') and kind.endswith('_ASAP7_75t_R'):
            inp, out = 'A', 'Y'
        else:
            continue
        src, dst = cell['connections'][inp], cell['connections'][out]
        assert len(src) == len(dst) == 1
        if isinstance(src[0], int) and isinstance(dst[0], int): followers[src[0]].add(dst[0])
    counts = Counter()
    examples = defaultdict(list)
    classified = 0
    for cell_name, cell in top['cells'].items():
        if not cell['type'].startswith('DFF'):
            continue
        bits = [b for port,bs in cell['connections'].items() if cell['port_directions'][port]=='output' for b in bs]
        candidates = set()
        frontier = set(bits)
        visited = set()
        for _ in range(4):
            for bit in frontier: candidates.update(aliases.get(bit, ()))
            visited.update(frontier)
            frontier = {b for bit in frontier for b in followers.get(bit, ())} - visited
        # Multiple functional families can alias one register: expose ambiguity.
        families = sorted({family(n) for n in candidates if family(n) != 'OTHER'})
        owner = families[0] if len(families)==1 else 'AMBIGUOUS' if families else 'UNATTRIBUTED'
        counts[owner] += 1
        classified += 1
        if len(examples[owner]) < 8:
            examples[owner].append(dict(cell=cell_name, aliases=sorted(candidates,key=lambda n:(len(n),n))[:6], attributes=cell.get('attributes',{})))
    expected = sum(v for k,v in stats['modules']['\\student_top']['num_cells_by_type'].items() if k.startswith('DFF'))
    assert classified == expected
    result = dict(status='SAVED_REPORT_AREA_BUDGET', original_run=str(RUN),
                  source_manifest_sha256=sha(RUN/'source_manifest.json'),
                  input_sha256={n:sha(directory/n) for n in ('area.json','stat.json','design.json')},
                  measured_area_um2=area['area_um2'], target_area_um2=36000,
                  required_reduction_um2=area['area_um2']-36000,
                  required_reduction_percent=100*(area['area_um2']-36000)/area['area_um2'],
                  logic_budget_if_sram_unchanged_um2=36000-area['sram_area_um2'],
                  exclusive_module_groups=[dict(source_module=k,**v) for k,v in sorted(grouped.items(),key=lambda kv:kv[1]['area_um2'],reverse=True)],
                  top_direct_register_count=classified, top_direct_register_alias_counts=dict(counts),
                  alias_examples=dict(examples),
                  limitations='Alias categories are register evidence only; flattened combinational area cannot be attributed by these counts. Ambiguity retained.',
                  new_synthesis_run=False, new_simulation_run=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write(OUT, result)
    print(json.dumps({k:result[k] for k in ('status','measured_area_um2','required_reduction_um2','logic_budget_if_sram_unchanged_um2','top_direct_register_alias_counts')},ensure_ascii=False))


if __name__ == '__main__':
    main()
