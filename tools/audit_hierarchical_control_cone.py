"""Trace verified root control gates to registers and hierarchy boundaries.

Functional module ports are explicit stopping points, not combinational
shortcuts. This reports dependencies only, never RTL ownership or module area.
"""
import argparse
from collections import Counter, defaultdict, deque
import json
from pathlib import Path

from audit_control_cone import prepared_registers
from verify_course_axi_area import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--cell', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists(), 'Preserve existing evidence'
    identity = json.loads(args.identity.read_text())
    assert identity['status'] == 'COMPLETE' and identity['input_is_full_cpu']
    assert identity['complete_hierarchical_wiring_identical']
    for name, expected in identity['input_sha256'].items():
        assert sha256(name) == expected, 'Changed identity evidence: ' + name
    names = [Path(name) for name in identity['input_sha256']]
    design, = [p for p in names if p.name == 'design.json']
    prepared, = [p for p in names if p.name == 'prepared.il']
    modules = json.loads(design.read_text())['modules']
    root = modules['student_top']
    cells = root['cells']
    registers = prepared_registers(prepared)
    driver, sinks, ports = {}, defaultdict(list), defaultdict(list)
    for name, cell in cells.items():
        for pin, bits in cell['connections'].items():
            if pin == 'CLK':
                continue
            for bit in bits:
                if type(bit) is not int:
                    continue
                if cell['port_directions'][pin] == 'output':
                    assert bit not in driver or driver[bit] == (name, pin), 'Multiple physical drivers'
                    driver[bit] = (name, pin)
                else:
                    sinks[bit].append((name, pin))
    for name, port in root['ports'].items():
        for index, bit in enumerate(port['bits']):
            ports[bit].append((name, port['direction'], index))

    def is_boundary(name):
        cell = cells[name]
        model = modules.get(cell['type'], {})
        functional = bool(model.get('cells'))
        return name in registers or functional or cell['type'].startswith('fakeram_asap7_')

    def trace(bits, upstream):
        queue, seen_bits, seen_cells, stops, reached = deque(bits), set(), set(), {}, set()
        while queue:
            bit = queue.popleft()
            if type(bit) is not int or bit in seen_bits:
                continue
            seen_bits.add(bit)
            links = [driver[bit]] if upstream and bit in driver else ([] if upstream else sinks[bit])
            for name, pin in links:
                if is_boundary(name):
                    row = stops.setdefault(name, dict(cell_type=cells[name]['type'], pins=[],
                        prepared_q_signals=registers.get(name, {})))
                    if pin not in row['pins']:
                        row['pins'].append(pin)
                    continue
                if name in seen_cells:
                    continue
                seen_cells.add(name)
                direction = 'input' if upstream else 'output'
                queue.extend(v for p, values in cells[name]['connections'].items()
                             if p != 'CLK' and cells[name]['port_directions'][p] == direction for v in values)
            reached.update(row for row in ports[bit] if row[1] == ('input' if upstream else 'output'))
        groups = Counter()
        for name, row in stops.items():
            q = list(row['prepared_q_signals'].values())
            group = q[0].split(' [')[0] if len(q) == 1 else 'hierarchy_or_memory:' + name
            groups[group] += 1
        return dict(combinational_cells=len(seen_cells), boundary_cells=len(stops),
                    groups=dict(groups.most_common()), boundaries=stops, top_ports=sorted(reached))

    rows = []
    for printed in args.cell:
        identified, = [r for r in identity['rows'] if r['printed'] == printed]
        cell = cells[identified['original']]
        assert cell['connections'] == identified['connections'] and cell['type'] == identified['cell_type']
        inputs = [b for p, bs in cell['connections'].items() if p != 'CLK' and cell['port_directions'][p] == 'input' for b in bs]
        outputs = [b for p, bs in cell['connections'].items() if cell['port_directions'][p] == 'output' for b in bs]
        rows.append(dict(printed=printed, upstream=trace(inputs, True), downstream=trace(outputs, False)))
    result = dict(status='COMPLETE', read_only=True, scope=__doc__,
                  netlist_sha256=identity['netlist_sha256'], rows=rows,
                  input_sha256={str(p.resolve()):sha256(p) for p in
                    [args.identity, design, prepared, Path(__file__), Path(__file__).with_name('audit_control_cone.py')]})
    for name, expected in identity['input_sha256'].items():
        assert sha256(name) == expected, 'Changed identity evidence during trace: ' + name
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    for row in rows:
        print(json.dumps({k: ({key:value for key,value in v.items() if key != 'boundaries'}
                            if k in ('upstream','downstream') else v) for k,v in row.items()}, indent=2))


if __name__ == '__main__':
    main()
