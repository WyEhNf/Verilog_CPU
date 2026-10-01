"""Independently reprice a flattened course AXI area audit from raw Liberty.

No synthesis, area normalization, capacity substitution, or zero-area blackbox
exclusion is performed. Only actual mapped leaf counts are priced.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def expand_stat_census(statistics, top='student_top'):
    """Check every Yosys module census, including preserved functional hierarchy.

    Yosys 0.68 reports physical leaves in num_cells, but its type dictionary
    also contains functional submodule instance entries. Do not simply discard
    those entries: expand all reachable modules with their real multiplicities
    and require the complete global dictionary to match leaves plus hierarchy.
    """
    modules = {name.removeprefix('\\'): row
               for name, row in statistics['modules'].items()}
    assert len(modules) == len(statistics['modules']), 'Ambiguous module names'
    assert top in modules, 'Missing statistics top'
    memo = {}

    def checked_counts(row):
        raw = row['num_cells_by_type']
        assert all(type(value) is int and value > 0 for value in raw.values()), \
            'Invalid cell multiplicity'
        return Counter(raw)

    def visit(kind, ancestors=()):
        assert kind not in ancestors, 'Recursive statistics hierarchy'
        if kind in memo:
            return memo[kind]
        row = modules[kind]
        direct = checked_counts(row)
        direct_leaves, direct_modules = Counter(), Counter()
        leaves, hierarchy = Counter(), Counter()
        assert row['num_memories'] == row['num_memory_bits'] == row['num_processes'] == 0, \
            'Unmapped module objects'
        for child, count in direct.items():
            normalized = child.removeprefix('\\')
            if normalized not in modules:
                direct_leaves[child] += count
                leaves[child] += count
                continue
            direct_modules[child] += count
            hierarchy[child] += count
            nested_leaves, nested_hierarchy = visit(normalized, ancestors + (kind,))
            leaves.update({name: value * count for name, value in nested_leaves.items()})
            hierarchy.update({name: value * count for name, value in nested_hierarchy.items()})
        assert sum(direct_leaves.values()) == row['num_cells'], 'Module leaf total mismatch'
        assert sum(direct_modules.values()) == row['num_submodules'], 'Module instance total mismatch'
        memo[kind] = leaves, hierarchy
        return memo[kind]

    leaves, hierarchy = visit(top)
    assert set(memo) == set(modules), 'Unreachable functional statistics module'
    design = statistics['design']
    assert checked_counts(design) == leaves + hierarchy, 'Global expanded type census mismatch'
    assert sum(leaves.values()) == design['num_cells'], 'Global leaf total mismatch'
    assert sum(hierarchy.values()) == design['num_submodules'], 'Global instance total mismatch'
    assert design['num_memories'] == design['num_memory_bits'] == design['num_processes'] == 0, \
        'Unmapped design objects'
    return leaves, hierarchy


def verify(directory, require_current=False):
    if not __debug__:
        raise ValueError('Verification requires Python assertions; do not use -O')
    out = Path(directory).resolve()
    audit = json.loads((out / 'area_audit.json').read_text())
    manifest = json.loads((out / 'run_manifest.json').read_text())
    assert audit['status'] == 'COMPLETE', 'Synthesis is incomplete'
    assert audit['settings'] == manifest['settings'], 'Configuration mismatch'
    assert manifest['settings']['mode'] == 'opt', 'Expected flattened netlist'
    assert audit['includes_axi_adapter'], 'AXI adapter omitted'
    assert not audit['external_ram_included'], 'External testbench RAM included'
    assert audit['unpriced_leaf_instances'] == 0, 'Unpriced leaves'
    assert audit['unmapped_memory_cells'] == 0, 'Unmapped memories'
    snapshot = Path(manifest['source_snapshot_root'])
    current_changes = []
    for name, expected in manifest['source_sha256'].items():
        assert sha256(snapshot / name) == expected.lower(), 'Snapshot changed: ' + name
        if not (ROOT / name).is_file() or sha256(ROOT / name) != expected.lower():
            current_changes.append(name)
    if require_current:
        assert not current_changes, 'Working inputs differ: ' + ', '.join(current_changes)
    build_path = Path(manifest['build_manifest'])
    assert sha256(build_path) == manifest['build_manifest_sha256'], 'Build manifest changed'
    build = json.loads(build_path.read_text(encoding='utf-8-sig'))
    assert sha256(build['executable']) == build['executable_sha256'].lower(), 'Executable changed'
    assert sha256(build['generated_driver']) == build['generated_driver_sha256'].lower(), 'Driver changed'
    for name, expected in build['source_sha256'].items():
        assert manifest['source_sha256'][name] == expected.lower(), 'Build/area input mismatch: ' + name
    marker = json.loads((out / 'map.done.json').read_text())
    script_digest = hashlib.sha256((out / 'map.ys').read_text().encode('utf-8')).hexdigest()
    assert script_digest == marker['script_sha256'], 'Mapping script changed'
    for name, expected in marker['output_sha256'].items():
        assert sha256(out / name) == expected, 'Mapped output changed: ' + name
    assert marker['output_sha256']['mapped.v'] == audit['netlist_sha256'], 'Netlist mismatch'
    statistics = json.loads((out / 'stat.json').read_text())
    stat = statistics['design']
    stat_leaves, stat_hierarchy = expand_stat_census(statistics)
    counts = Counter(audit['leaf_counts'])
    assert counts == stat_leaves, 'Leaf census mismatch'
    assert sum(counts.values()) == stat['num_cells'] == audit['leaf_instances']
    assert stat['num_memories'] == stat['num_memory_bits'] == 0
    prices, sequential = {}, set()
    for entry in audit['libraries']:
        path = Path(entry['path'])
        assert sha256(path) == entry['sha256'], 'Liberty changed: ' + str(path)
        cells = re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                           path.read_text(), flags=re.S)
        for name, body in cells:
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)',
                              body, flags=re.M)
            assert match, 'Missing raw Liberty area: ' + name
            value = Decimal(match[1])
            assert name not in prices or prices[name] == value, 'Conflicting Liberty cell'
            prices[name] = value
            if '_SEQ_' in path.name:
                sequential.add(name)
    macros = json.loads((out / 'ram/manifest.json').read_text())
    coefficient = Decimal(str(macros['model']['area_per_bit_um2']))
    for name, shape in macros['macros'].items():
        formula = (coefficient * shape['depth'] * shape['width']).quantize(Decimal('.000001'))
        assert prices[name] == formula == Decimal(str(shape['area_um2'])), 'SRAM formula mismatch'
    assert not (set(counts) - set(prices)), 'Unpriced actual leaf type'
    sram_names = set(macros['macros'])
    instances = Counter(entry['module'] for entry in audit['area']['sram_instances'])
    assert instances == Counter({name: count for name, count in counts.items() if name in sram_names})
    components = {'combinational_area_um2': Decimal(0), 'sequential_area_um2': Decimal(0),
                  'sram_area_um2': Decimal(0)}
    for name, count in counts.items():
        key = ('sram_area_um2' if name in sram_names else
               'sequential_area_um2' if name in sequential else 'combinational_area_um2')
        components[key] += prices[name] * count
    components['logic_area_um2'] = components['combinational_area_um2'] + components['sequential_area_um2']
    components['area_um2'] = components['logic_area_um2'] + components['sram_area_um2']
    for key, value in components.items():
        assert abs(value - Decimal(str(audit['area'][key]))) < Decimal('.00001'), 'Area mismatch: ' + key
    return {'status': 'VERIFIED', 'directory': str(out), 'settings': manifest['settings'],
            'area': {key: str(value) for key, value in components.items()},
            'leaf_instances': sum(counts.values()), 'sram_instances': sum(instances.values()),
            'functional_hierarchy_instances': sum(stat_hierarchy.values()),
            'netlist_sha256': audit['netlist_sha256'], 'changed_current_inputs': current_changes,
            'verifier_sha256': sha256(__file__),
            'stat_census_method': 'Recursive functional-module expansion; full leaf and hierarchy type/total equality',
            'method': 'Actual final leaf counts times unmodified raw Liberty areas, independent Decimal arithmetic'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--require-current', action='store_true')
    args = parser.parse_args()
    result = verify(args.directory, args.require_current)
    (args.directory / 'independent_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
