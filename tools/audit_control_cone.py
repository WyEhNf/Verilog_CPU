"""Trace an identified physical control gate to its real sequential boundaries.

Read-only analysis of the frozen graded netlist. This attributes dependencies,
not logic ownership, module area, or a replacement timing result.
"""
import argparse
from collections import Counter, defaultdict, deque
import json
from pathlib import Path

from verify_course_axi_area import sha256, verify


def prepared_registers(path):
    flops, inverters = {}, {}
    active, ports = None, {}
    with path.open() as stream:
        for line in stream:
            if line.startswith('  cell '):
                kind, name = line.split()[1:3]
                active = (kind.lstrip('\\'), name.lstrip('\\')) if (
                    kind.startswith('\\DFF') or
                    (kind == '$_NOT_' and 'dfflibmap' in name)) else None
                ports = {}
            elif active and line.startswith('    connect '):
                pin, signal = line.strip().split(' ', 2)[1:]
                ports[pin.lstrip('\\')] = signal
            elif active and line.strip() == 'end':
                kind, name = active
                if kind == '$_NOT_':
                    inverters[ports['A']] = ports['Y']
                else:
                    flops[name] = ports
                active = None
    return {name: {pin: inverters.get(value, value) for pin, value in ports.items()
                   if pin in ('Q', 'QN')} for name, ports in flops.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--printed-cell', required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    checked = verify(directory)
    preparation = json.loads((directory / 'prepare.done.json').read_text())
    if sha256(directory / 'prepared.il') != preparation['output_sha256']['prepared.il']:
        raise SystemExit('Prepared register-identity snapshot changed')
    identities = json.loads(args.identity.read_text())
    if (not identities['complete_physical_wiring_identical'] or
            identities['netlist_sha256'] != checked['netlist_sha256']):
        raise SystemExit('Printed identity does not refer to this complete physical graph')
    identified = next(row for row in identities['rows'] if row['printed'] == args.printed_cell)
    model = json.loads((directory / 'design.json').read_text())['modules']['student_top']
    registers = prepared_registers(directory / 'prepared.il')
    cells = model['cells']
    chosen = cells[identified['original']]
    if chosen['type'] != identified['cell_type'] or chosen['connections'] != identified['connections']:
        raise SystemExit('Selected identity differs from the actual physical cell')
    driver, sinks = {}, defaultdict(list)
    for name, cell in cells.items():
        for pin, bits in cell['connections'].items():
            for bit in bits:
                if type(bit) is not int or pin == 'CLK':
                    continue
                if cell['port_directions'][pin] == 'output':
                    if bit in driver and driver[bit] != (name, pin):
                        raise SystemExit('Multiple physical drivers')
                    driver[bit] = (name, pin)
                else:
                    sinks[bit].append((name, pin))
    ports = defaultdict(list)
    for name, port in model['ports'].items():
        for index, bit in enumerate(port['bits']):
            ports[bit].append(dict(port=name, direction=port['direction'], index=index))

    def boundary(name):
        return name in registers or cells[name]['type'].startswith('fakeram_asap7_')

    def trace(bits, upstream):
        queue, seen_bits, seen_cells, stops, top = deque(bits), set(), set(), {}, {}
        while queue:
            bit = queue.popleft()
            if type(bit) is not int or bit in seen_bits:
                continue
            seen_bits.add(bit)
            links = [driver[bit]] if upstream and bit in driver else ([] if upstream else sinks[bit])
            for name, pin in links:
                if boundary(name):
                    stops[name] = dict(cell=name, cell_type=cells[name]['type'],
                                       prepared_q_signals=registers.get(name, {}))
                    continue
                if name in seen_cells:
                    continue
                seen_cells.add(name)
                direction = 'input' if upstream else 'output'
                queue.extend(v for p, vs in cells[name]['connections'].items()
                             if p != 'CLK' and cells[name]['port_directions'][p] == direction for v in vs)
            for row in ports.get(bit, []):
                if row['direction'] == ('input' if upstream else 'output'):
                    top[(row['port'], row['index'])] = row
        owners = Counter()
        for row in stops.values():
            signals = list(row['prepared_q_signals'].values())
            owner = signals[0].split(' [')[0] if len(signals) == 1 else row['cell_type']
            owners[owner] += 1
        return dict(combinational_dependencies=len(seen_cells), sequential_boundaries=len(stops),
                    register_groups=[dict(register=name, bits=count) for name, count in owners.most_common()],
                    top_ports=list(top.values()), boundaries=list(stops.values()))

    inputs = [bit for pin, bits in chosen['connections'].items()
              if chosen['port_directions'][pin] == 'input' and pin != 'CLK' for bit in bits]
    outputs = [bit for pin, bits in chosen['connections'].items()
               if chosen['port_directions'][pin] == 'output' for bit in bits]
    result = dict(status='COMPLETE', diagnostic_only=True, not_a_module_area_sum=True,
                  physical_cell=identified, netlist_sha256=checked['netlist_sha256'],
                  upstream=trace(inputs, True), downstream=trace(outputs, False),
                  input_sha256={str(path.resolve()): sha256(path) for path in (
                      directory / 'design.json', directory / 'prepared.il',
                      directory / 'prepare.done.json', args.identity, Path(__file__))})
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / 'control_cone.json').write_text(json.dumps(result, indent=2) + '\n')
    for direction in ('upstream', 'downstream'):
        part = result[direction]
        print(direction, json.dumps({k: v for k, v in part.items() if k != 'boundaries'}, indent=2))


if __name__ == '__main__':
    main()
