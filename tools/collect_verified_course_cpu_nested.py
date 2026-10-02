"""Run unchanged native/PPA collection with the independently checked nested census.

Only the area census callback differs. Bind the original collector, original
pricing verifier, nested census verifier and this adapter by hash. No netlist,
constraint, SRAM model, source snapshot, or benchmark data is modified.
"""
import argparse
import json
from pathlib import Path

import collect_verified_course_cpu as collector
import verify_course_axi_area as base
import verify_course_axi_area_nested as nested


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--area', type=Path)
    a, _ = parser.parse_known_args()
    assert not a.out.exists(), 'Preserve previous collection'
    paths = [Path(__file__).resolve(), Path(collector.__file__).resolve(),
             Path(base.__file__).resolve(), Path(nested.__file__).resolve()]
    hashes = {str(p):base.sha256(p) for p in paths}
    area = a.area or a.out.parent/'area'
    audit_path = area/'independent_verification_nested.json'
    audit = json.loads(audit_path.read_text())
    assert audit['status'] == 'VERIFIED' and not audit['changed_current_inputs']
    assert audit['verifier_sha256'] == hashes[str(Path(nested.__file__).resolve())]
    validation_path = Path('F:/CPU2026Diagnostics/nested_stat_census_20261003/report.json')
    validation = json.loads(validation_path.read_text())
    assert validation['status'] == 'VERIFIED' and len(validation['negative_cases']) == 8
    assert all(row['status'] == 'REJECTED' for row in validation['negative_cases'])
    for path in (audit_path, validation_path):
        hashes[str(path.resolve())] = base.sha256(path)
    for path, expected in validation['input_sha256'].items():
        assert base.sha256(path) == expected, 'Census validation input changed: '+path
        hashes[path] = expected
    collector.verify = lambda directory: nested.verify(directory, True, a.source_root)
    collector.main()
    result = json.loads(a.out.read_text())
    assert result['netlist_sha256'] == audit['netlist_sha256']
    assert result['area'] == audit['area'] and result['leaf_instances'] == audit['leaf_instances']
    for path, expected in hashes.items():
        assert base.sha256(path) == expected, 'Collection helper changed: '+path
        assert path not in result['input_sha256'] or result['input_sha256'][path] == expected
        result['input_sha256'][path] = expected
    result['hierarchical_stat_scope_correction'] = True
    result['stat_census_method'] = 'Complete recursive physical leaves; global Yosys functional entries checked against top-direct module instances'
    a.out.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
