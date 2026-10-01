"""Diagnostic attribution of actual priced flip-flops in a complete CPU netlist.

Prepared RTLIL retains register identities removed by final clean-purge. Trace
each final FF's exact unchanged cell name through its prepared output inverter.
Direct final Q/QN aliases are a fallback. Unrelated aliases stay ambiguous.
This is not a module-area sum or a replacement for the complete graded audit.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import re

from verify_course_axi_area import sha256, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--outdir', type=Path,
                        help='Write diagnostics here instead of modifying the frozen audit directory')
    parser.add_argument('--cell', action='append', default=[],
                        help='Also report exact prepared/final identity for a selected flip-flop')
    args = parser.parse_args()
    directory = args.directory.resolve()
    out = args.outdir.resolve() if args.outdir else directory
    verified = verify(directory)
    prepared = directory / 'prepared.il'
    preparation = json.loads((directory / 'prepare.done.json').read_text())
    if sha256(prepared) != preparation['output_sha256']['prepared.il']:
        raise SystemExit('Prepared snapshot changed')
    prepared_ffs, prepared_inverters = {}, {}
    active, ports = None, {}
    with prepared.open() as stream:
        for line in stream:
            if line.startswith('  cell '):
                cell_type, cell_name = line.split()[1:3]
                active = (cell_type.lstrip('\\'), cell_name.lstrip('\\')) if (
                    cell_type.startswith('\\DFF') or
                    (cell_type == '$_NOT_' and 'dfflibmap' in cell_name)) else None
                ports = {}
            elif active and line.startswith('    connect '):
                pin, signal = line.strip().split(' ', 2)[1:]
                ports[pin.lstrip('\\')] = signal
            elif active and line.strip() == 'end':
                cell_type, cell_name = active
                if cell_type == '$_NOT_':
                    prepared_inverters[ports['A']] = ports['Y']
                else:
                    prepared_ffs[cell_name] = (cell_type, ports)
                active = None
    audit = json.loads((directory / 'area_audit.json').read_text())
    prices = {}
    for entry in audit['libraries']:
        path = Path(entry['path'])
        if '_SEQ_' not in path.name:
            continue
        for name, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                                     path.read_text(), re.S):
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            if not match:
                raise SystemExit('Missing raw sequential area: ' + name)
            prices[name] = Decimal(match[1])
    design = json.loads((directory / 'design.json').read_text())['modules']['student_top']
    aliases = defaultdict(set)
    for name, net in design['netnames'].items():
        if net['hide_name'] or name.startswith('$'):
            continue
        owner = name.rsplit('.', 1)[0] if '.' in name else 'student_top'
        for bit in net['bits']:
            if type(bit) is int:
                aliases[bit].add(owner)
    inverters = defaultdict(set)
    for cell in design['cells'].values():
        ports = cell['connections']
        if cell['type'].startswith('INV') and set(ports) == {'A', 'Y'}:
            if len(ports['A']) == len(ports['Y']) == 1:
                inverters[ports['A'][0]].add(ports['Y'][0])
    areas, counts = defaultdict(Decimal), Counter()
    ambiguous_examples = []
    selected_cells = []
    for name, cell in design['cells'].items():
        if cell['type'] not in prices:
            continue
        outputs = [bit for pin, bits in cell['connections'].items()
                   if cell['port_directions'].get(pin) == 'output' for bit in bits]
        owners = set()
        if name in prepared_ffs:
            prepared_type, prepared_ports = prepared_ffs[name]
            if prepared_type != cell['type']:
                raise SystemExit('Prepared/final FF type differs: ' + name)
            for pin in ('Q', 'QN'):
                if pin not in prepared_ports:
                    continue
                signal = prepared_ports[pin]
                signal = prepared_inverters.get(signal, signal)
                # A scalar or bit-slice name is safe; do not attribute packed
                # concatenations, constants, or synthesized temporary wires.
                if signal.startswith('\\'):
                    register = signal.split()[0].lstrip('\\')
                    if not register.startswith('$'):
                        owners.add(register.rsplit('.', 1)[0] if '.' in register else 'student_top')
        for bit in outputs:
            owners.update(aliases[bit])
            for opposite in inverters[bit]:
                owners.update(aliases[opposite])
        leaves = {owner for owner in owners if not any(
            other.startswith(owner + '.') for other in owners if other != owner)}
        if len(leaves) > 1:
            # Public top-level ports can alias a child's registered output;
            # the root is its parent even though flattening omits its prefix.
            leaves.discard('student_top')
        if len(leaves) == 1:
            owner = next(iter(leaves))
        elif not leaves:
            owner = 'UNRESOLVED'
        else:
            owner = 'AMBIGUOUS'
            if len(ambiguous_examples) < 20:
                ambiguous_examples.append(dict(cell=name, aliases=sorted(owners)))
        areas[owner] += prices[cell['type']]
        counts[owner] += 1
        if name in args.cell:
            original = prepared_ffs.get(name)
            selected_cells.append(dict(
                cell=name, cell_type=cell['type'], owner=owner,
                final_connections=cell['connections'],
                prepared_connections=original[1] if original else {},
                prepared_q_signals={pin: prepared_inverters.get(signal, signal)
                                    for pin, signal in (original[1] if original else {}).items()
                                    if pin in ('Q', 'QN')}))
    if set(args.cell) != {row['cell'] for row in selected_cells}:
        raise SystemExit('Requested cell is missing or is not an actual priced flip-flop')
    total = sum(areas.values(), Decimal(0))
    if total != Decimal(verified['area']['sequential_area_um2']):
        raise SystemExit('Sequential attribution census does not match independent grade')
    rows = [dict(owner=owner, instances=counts[owner], area_um2=str(area))
            for owner, area in sorted(areas.items(), key=lambda item: item[1], reverse=True)]
    report = dict(status='COMPLETE', diagnostic_only=True, not_a_module_area_sum=True,
                  netlist_sha256=verified['netlist_sha256'], sequential_area_um2=str(total),
                  rows=rows, ambiguous_examples=ambiguous_examples,
                  selected_cells=selected_cells,
                  method='Priced final FFs; identical prepared FF identity/output-inverter trace and final aliases',
                  input_sha256={str(path): sha256(path) for path in (
                      directory / 'design.json', prepared, directory / 'prepare.done.json', directory / 'area_audit.json',
                      directory / 'map.done.json', Path(__file__).resolve())})
    out.mkdir(parents=True, exist_ok=True)
    (out / 'sequential_ownership.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(sequential_area_um2=str(total), rows=rows[:15],
                          selected_cells=selected_cells), indent=2))


if __name__ == '__main__':
    main()
