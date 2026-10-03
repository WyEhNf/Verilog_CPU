"""Locate surviving state in one verified mapped CPU, including kept hierarchy.

Attribute sequential-cell area only. Combinational/SRAM area remains separate;
no field count is presented as an achievable savings estimate. Original final
cells are matched by scope/name/type to the frozen pre-ABC register identities.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import re

from verify_course_axi_area import verify, sha256, expand_stat_census


def prepared_registers(path, sequential):
    flops, inversions = {}, {}
    scope, active, ports = None, None, {}
    with path.open() as stream:
        for line in stream:
            if line.startswith('module '): scope = line.split()[1].lstrip('\\')
            elif line.startswith('  cell '):
                kind, name = [s.lstrip('\\') for s in line.split()[1:3]]
                active = (scope, name, kind) if kind in sequential or (kind == '$_NOT_' and 'dfflibmap' in name) else None
                ports = {}
            elif active and line.startswith('    connect '):
                pin, signal = line.strip().split(' ', 2)[1:]
                ports[pin.lstrip('\\')] = signal
            elif active and line.strip() == 'end':
                module, name, kind = active
                if kind == '$_NOT_':
                    key = (module, ports['A'])
                    assert key not in inversions or inversions[key] == ports['Y']
                    inversions[key] = ports['Y']
                else:
                    key = (module, name)
                    assert key not in flops
                    flops[key] = (kind, dict(ports))
                active = None
    return flops, inversions


def field_name(signal):
    # RTLIL escaped identifier followed by an optional bit select. Memory row
    # selectors belong to the identifier and are collapsed only for grouping.
    match = re.fullmatch(r'\\(\S+)(?:\s+\[\d+(?::\d+)?\])?', signal)
    if not match: return None
    return re.sub(r'\[\d+\]', '[]', match[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    directory, out = args.directory.resolve(), args.outdir.resolve()
    assert not out.exists(), 'preserve diagnostic evidence'
    checked = verify(directory)
    inputs = [Path(__file__).resolve(), Path(__file__).with_name('verify_course_axi_area.py')]
    manifest_path = directory / 'run_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    inputs.append(manifest_path)
    for name, digest in manifest['source_sha256'].items():
        origin = args.source_root.resolve() / name
        assert sha256(origin) == digest.lower(), 'Frozen source differs: ' + name
        inputs.append(origin)
    inputs += [directory / n for n in ('area_audit.json','stat.json','design.json',
                                      'prepared.il','prepare.done.json','map.done.json')]
    for marker_name in ('prepare', 'map'):
        marker = json.loads((directory / f'{marker_name}.done.json').read_text())
        for name, digest in marker['output_sha256'].items():
            assert sha256(directory / name) == digest, name
    audit = json.loads((directory / 'area_audit.json').read_text())
    sequential, prices = set(), {}
    for entry in audit['libraries']:
        path = Path(entry['path'])
        if '_SEQ_' not in path.name: continue
        assert sha256(path) == entry['sha256']
        inputs.append(path)
        for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)', path.read_text(), re.S):
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            assert match
            sequential.add(name); prices[name] = Decimal(match[1])
    assert sequential
    hashes = {str(p): sha256(p) for p in inputs}
    print('START scope-aware frozen prepared register scan', flush=True)
    flops, inversions = prepared_registers(directory / 'prepared.il', sequential)
    model = json.loads((directory / 'design.json').read_text())['modules']
    statistics = json.loads((directory / 'stat.json').read_text())
    leaves, hierarchy = expand_stat_census(statistics)
    functional = {name.lstrip('\\') for name in statistics['modules']}
    expected = Counter({kind: count for kind, count in leaves.items() if kind in sequential})
    rows, groups, counts, scopes = [], defaultdict(lambda: [0, Decimal(0)]), Counter(), Counter()

    def visit(module, instance_path, parents=()):
        assert module not in parents
        scopes[module] += 1
        for name, cell in model[module]['cells'].items():
            kind = cell['type']
            if kind in functional:
                visit(kind, instance_path + '/' + name, parents + (module,))
            elif kind in sequential:
                key = (module, name)
                assert key in flops and flops[key][0] == kind, key
                ports = flops[key][1]
                output_pins = [p for p, direction in cell['port_directions'].items() if direction == 'output']
                assert len(output_pins) == 1
                pin = output_pins[0]
                signal = inversions.get((module, ports[pin]), ports[pin])
                logical = field_name(signal)
                group = ((instance_path + '/' if module != 'student_top' else '') + logical
                         if logical else 'UNRESOLVED/' + module)
                groups[group][0] += 1; groups[group][1] += prices[kind]
                counts[kind] += 1
                rows.append(dict(instance=instance_path + '/' + name, scope=module,
                                 type=kind, logical_signal=signal, grouped_field=group,
                                 area_um2=str(prices[kind])))

    visit('student_top', 'student_top')
    assert counts == expected, 'final hierarchical sequential census differs'
    expected_scopes = Counter({'student_top':1})
    expected_scopes.update({k.lstrip('\\'):v for k,v in hierarchy.items()})
    assert scopes == expected_scopes, 'hierarchy multiplicity differs'
    area = sum((prices[k] * v for k,v in counts.items()), Decimal(0))
    assert area == Decimal(checked['area']['sequential_area_um2'])
    assert sum((v[1] for v in groups.values()), Decimal(0)) == area
    # Separate count diagnostics for frequently suspected duplicate payloads.
    interesting = {}
    for fragment in ('rob.pc_mem','rob.inst_mem','rob.value_mem','rob.store_addr_mem',
                     'rob.store_data_mem','rob.checkpoint_mem','rob.generation_mem',
                     'backend.rob_pc_mem','backend.rob_imm_mem','rs.age_mem','rs.metadata_mem'):
        matches = [dict(field=k, cells=v[0], area_um2=str(v[1])) for k,v in groups.items() if fragment in k]
        interesting[fragment] = dict(cells=sum(x['cells'] for x in matches), matches=matches)
    grouped = [dict(field=k, sequential_cells=v[0], area_um2=str(v[1]))
               for k,v in sorted(groups.items(), key=lambda row:row[1][1], reverse=True)]
    out.mkdir(parents=True)
    details = out / 'physical_registers.json'
    details.write_text(json.dumps(rows, indent=2) + '\n')
    hashes[str(details)] = sha256(details)
    for path, value in hashes.items(): assert sha256(Path(path)) == value, path
    report = dict(status='VERIFIED', directory=str(directory), netlist_sha256=checked['netlist_sha256'],
        diagnostic_only=True, sequential_area_um2=str(area), sequential_cells=sum(counts.values()),
        leaf_counts=dict(counts), actual_physical_leaves=checked['leaf_instances'],
        actual_sram_instances=checked['sram_instances'], includes_all_sequential_instances=True,
        unresolved_sequential_cells=sum(v[0] for k,v in groups.items() if k.startswith('UNRESOLVED/')),
        groups=grouped, selected_state_fields=interesting, input_sha256=hashes,
        scope='Actual surviving sequential cells, exact frozen scope/name/type identities and raw prices. No combinational attribution, hypothetical area savings, or timing/IPC claims.')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('input_sha256','groups')} | {'largest_fields':grouped[:30]},indent=2))


if __name__ == '__main__': main()
