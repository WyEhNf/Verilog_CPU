"""Attribute raw leaf area within one verified functional-hierarchy CPU.

Exclusive module totals partition the actual physical design exactly once.
Inclusive module totals overlap and must never be summed. These measurements
describe this specific mapping, not the separately mapped adopted CPU.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import re

from verify_course_axi_area import sha256
from verify_course_axi_area_nested import expand_stat_census, verify


def partition(statistics, prices, sequential, sram):
    leaves, instances = expand_stat_census(statistics)
    modules = {k.removeprefix('\\'): v for k, v in statistics['modules'].items()}
    multiplicities = Counter({'student_top': 1})
    for kind, count in instances.items():
        multiplicities[kind.removeprefix('\\')] += count
    attributed = Counter()
    groups = defaultdict(lambda: dict(instances=0, physical_leaves=0,
        combinational_area_um2=Decimal(0), sequential_area_um2=Decimal(0),
        sram_area_um2=Decimal(0), sram_instances=0))
    rows = []
    inclusive = {}

    def price(counts):
        amounts = dict(combinational_area_um2=Decimal(0),
                       sequential_area_um2=Decimal(0), sram_area_um2=Decimal(0))
        for kind, count in counts.items():
            assert kind in prices, 'Unpriced physical type: ' + kind
            category = ('sram_area_um2' if kind in sram else
                        'sequential_area_um2' if kind in sequential else
                        'combinational_area_um2')
            amounts[category] += prices[kind] * count
        amounts['area_um2'] = sum(amounts.values(), Decimal(0))
        return amounts

    def inside(kind):
        if kind in inclusive:
            return inclusive[kind]
        counts = Counter()
        for child, count in modules[kind]['num_cells_by_type'].items():
            key = child.removeprefix('\\')
            if key in modules:
                counts.update({k: v*count for k, v in inside(key).items()})
            else:
                counts[child] += count
        inclusive[kind] = counts
        return counts

    assert inside('student_top') == leaves
    for kind, row in modules.items():
        count = multiplicities[kind]
        assert count > 0
        direct = Counter({k: v for k, v in row['num_cells_by_type'].items()
                          if k.removeprefix('\\') not in modules})
        weighted = Counter({k: v*count for k, v in direct.items()})
        attributed.update(weighted)
        amounts = price(weighted)
        family_match = re.search(r'\\(rv32\w+)', kind)
        family = family_match.group(1) if family_match else kind
        group = groups[family]
        group['instances'] += count
        group['physical_leaves'] += sum(weighted.values())
        group['sram_instances'] += sum(v for k, v in weighted.items() if k in sram)
        for category in ('combinational_area_um2','sequential_area_um2','sram_area_um2'):
            group[category] += amounts[category]
        rows.append(dict(module=kind, family=family, instances=count,
                         direct_leaves_per_instance=sum(direct.values()),
                         exclusive_all_instances=amounts,
                         inclusive_per_instance=price(inside(kind))))
    assert attributed == leaves, 'Exclusive attribution omitted or double-counted leaves'
    for group in groups.values():
        group['area_um2'] = sum((v for k,v in group.items() if k.endswith('_area_um2')), Decimal(0))
    totals = price(leaves)
    for category in totals:
        assert sum((g[category] for g in groups.values()), Decimal(0)) == totals[category]
    grouped = [dict(family=k, **v) for k,v in sorted(groups.items(), key=lambda p:p[1]['area_um2'], reverse=True)]
    return dict(totals=totals, physical_leaves=sum(leaves.values()),
                sram_instances=sum(v for k,v in leaves.items() if k in sram),
                functional_instances_excluding_top=sum(instances.values()),
                exclusive_groups=grouped, module_details=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists(), 'Preserve previous diagnostic evidence'
    directory = args.directory.resolve()
    checked = verify(directory, True, args.source_root)
    audit = json.loads((directory/'area_audit.json').read_text())
    statistics = json.loads((directory/'stat.json').read_text())
    prices, sequential = {}, set()
    inputs = [Path(__file__).resolve(), Path(__file__).with_name('verify_course_axi_area.py'),
              Path(__file__).with_name('verify_course_axi_area_nested.py'),
              directory/'stat.json', directory/'map.done.json', directory/'area_audit.json',
              directory/'ram/manifest.json']
    for entry in audit['libraries']:
        path = Path(entry['path'])
        assert sha256(path) == entry['sha256']
        inputs.append(path)
        for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)', path.read_text(), re.S):
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            assert match
            amount = Decimal(match[1])
            assert name not in prices or prices[name] == amount
            prices[name] = amount
            if '_SEQ_' in path.name:
                sequential.add(name)
    sram = set(json.loads((directory/'ram/manifest.json').read_text())['macros'])
    # The real Yosys two-level fixture contains reused module definitions.
    # Its four leaves must contribute exactly four prices, not six or two.
    fixture = Path('F:/CPU2026Diagnostics/nested_stat_census_20261003/fixture.json')
    toy = partition(json.loads(fixture.read_text()), {'$and':Decimal('2.5')}, set(), set())
    assert toy['totals']['area_um2'] == Decimal(10)
    assert toy['physical_leaves'] == 4 and toy['functional_instances_excluding_top'] == 6
    inputs.append(fixture)
    result = partition(statistics, prices, sequential, sram)
    for category, value in result['totals'].items():
        assert value == Decimal(checked['area'][category]), category
    assert result['physical_leaves'] == checked['leaf_instances']
    assert result['sram_instances'] == checked['sram_instances']
    result.update(status='VERIFIED', scope=__doc__, directory=str(directory),
                  netlist_sha256=checked['netlist_sha256'],
                  adopted_cpu_area_claim=False, fixture_repeated_instance_test='PASS',
                  input_sha256={str(p.resolve()):sha256(p) for p in inputs})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('module_details','input_sha256')}, indent=2, default=str))


if __name__ == '__main__':
    main()
