"""Attribute mapped combinational area to its reachable sequential consumers.

Read-only diagnostic for a fully flattened, independently priced CPU netlist.
Shared cones stay shared: they are not charged once per consumer or presented
as independent module PPA. Stop traversal at every flip-flop and SRAM boundary.
"""
import argparse
from collections import Counter, defaultdict, deque
from decimal import Decimal
import json
from pathlib import Path
import re

from audit_timing_identity import prepared_registers
from verify_course_axi_area import verify, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    directory, out = args.directory.resolve(), args.outdir.resolve()
    verified = verify(directory)
    if verified['functional_hierarchy_instances']:
        raise SystemExit('This diagnostic requires a fully flattened functional design')
    prep = directory / 'prepared.il'
    marker = json.loads((directory / 'prepare.done.json').read_text())
    assert sha256(prep) == marker['output_sha256']['prepared.il']
    flops, inversions = prepared_registers(prep)
    audit = json.loads((directory / 'area_audit.json').read_text())
    model = json.loads((directory / 'design.json').read_text())['modules']['student_top']
    prices, sequential = {}, set()
    for entry in audit['libraries']:
        path = Path(entry['path'])
        assert sha256(path) == entry['sha256']
        for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)', path.read_text(), re.S):
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            assert match, name
            prices[name] = Decimal(match[1])
            if re.search(r'\b(?:ff|latch)\s*\(', body):
                sequential.add(name)
    srams = {entry['module'] for entry in audit['area']['sram_instances']}
    cells = model['cells']
    comb = {name: cell for name, cell in cells.items()
            if cell['type'] not in sequential | srams}
    drivers = {}
    for name, cell in comb.items():
        assert cell['type'] in prices
        for pin, bits in cell['connections'].items():
            if cell['port_directions'][pin] == 'output':
                for bit in bits:
                    if isinstance(bit, int):
                        assert bit not in drivers, ('Multiple drivers', bit)
                        drivers[bit] = name
    owners = {}
    reaches = dict.fromkeys(comb, 0)

    def seed(bits, owner):
        if owner not in owners:
            owners[owner] = 1 << len(owners)
        for bit in bits:
            if bit in drivers:
                reaches[drivers[bit]] |= owners[owner]

    for name, cell in cells.items():
        if cell['type'] in sequential:
            identity = flops.get(name)
            owner = 'UNRESOLVED_REGISTER'
            if identity:
                assert identity[0] == cell['type']
                signals = [inversions.get(s, s) for pin, s in identity[1].items()
                           if pin in ('Q', 'QN')]
                candidates = {s.split()[0].lstrip('\\').rsplit('.', 1)[0]
                              for s in signals if s.startswith('\\') and not s.startswith('\\$')}
                if len(candidates) == 1:
                    owner = next(iter(candidates))
            for pin, bits in cell['connections'].items():
                if cell['port_directions'][pin] == 'input' and pin != 'CLK':
                    seed(bits, owner)
        elif cell['type'] in srams:
            for pin, bits in cell['connections'].items():
                if cell['port_directions'][pin] == 'input' and pin.lower() != 'clk':
                    seed(bits, 'SRAM:' + name.rsplit('.', 1)[0])
    for name, port in model['ports'].items():
        if port['direction'] == 'output':
            seed(port['bits'], 'TOP_OUTPUTS')
    predecessors = {}
    remaining = Counter()
    for name, cell in comb.items():
        inputs = {drivers[bit] for pin, bits in cell['connections'].items()
                  if cell['port_directions'][pin] == 'input'
                  for bit in bits if bit in drivers}
        predecessors[name] = inputs
        remaining.update(inputs)
    queue = deque(name for name in comb if not remaining[name])
    visited = 0
    while queue:
        consumer = queue.popleft()
        visited += 1
        for producer in predecessors[consumer]:
            reaches[producer] |= reaches[consumer]
            remaining[producer] -= 1
            if remaining[producer] == 0:
                queue.append(producer)
    assert visited == len(comb), 'Combinational cycle or incomplete graph traversal'
    areas, counts = defaultdict(Decimal), Counter()
    for name, cell in comb.items():
        areas[reaches[name]] += prices[cell['type']]
        counts[reaches[name]] += 1
    total = sum(areas.values(), Decimal(0))
    assert total == Decimal(verified['area']['combinational_area_um2'])
    rows = []
    for mask, area in sorted(areas.items(), key=lambda item: item[1], reverse=True):
        consumers = [owner for owner, flag in owners.items() if mask & flag]
        rows.append(dict(consumers=consumers, shared=len(consumers) > 1,
                         cells=counts[mask], area_um2=str(area)))
    report = dict(status='COMPLETE', diagnostic_only=True,
                  method='Exact combinational DAG, unique area per gate, sequential and SRAM boundaries',
                  not_a_module_area_sum=True, netlist_sha256=verified['netlist_sha256'],
                  total_combinational_area_um2=str(total), rows=rows,
                  input_sha256={str(p): sha256(p) for p in (
                      prep, directory / 'design.json', directory / 'area_audit.json', Path(__file__))})
    out.mkdir(parents=True, exist_ok=True)
    (out / 'logic_ownership.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(total_combinational_area_um2=str(total), top_cones=rows[:15]), indent=2))


if __name__ == '__main__':
    main()
