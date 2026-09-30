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
    stat = json.loads((out / 'stat.json').read_text())['design']
    counts = Counter(audit['leaf_counts'])
    assert dict(counts) == stat['num_cells_by_type'], 'Leaf census mismatch'
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
            'netlist_sha256': audit['netlist_sha256'], 'changed_current_inputs': current_changes,
            'method': 'Actual final leaf counts times unmodified raw Liberty areas, independent Decimal arithmetic'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--require-current', action='store_true')
    args = parser.parse_args()
    result = verify(args.directory, args.require_current)
    (args.directory / 'independent_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
