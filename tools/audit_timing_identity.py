"""Resolve STA's printed cell names to the frozen Yosys/prepared identities.

The default Verilog writer renames hidden objects. Re-export the exact frozen
JSON both with and without that naming conversion, verify complete named-net
and cell-pin connectivity (including alias equivalences), and pair the unchanged
cell declarations. This does not alter the
graded netlist, timing constraints, libraries, or area.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from itertools import zip_longest
import os
from pathlib import Path
import re
import subprocess

from verify_course_axi_area import expand_stat_census, sha256, verify


ROOT = Path(__file__).resolve().parents[1]


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def declarations(path):
    # Noattr/noexpr writers produce one leaf declaration in this exact form.
    return [(kind.lstrip('\\'), name.lstrip('\\')) for kind, name in re.findall(
        r'^  (\\\S+|[A-Za-z_$][\w$]*)\s+(\\\S+|[A-Za-z_$][\w$]*)\s+\($',
        path.read_text(), re.M)]


def wiring_fingerprint(path):
    model = json.loads(path.read_text())['modules']['student_top']
    representatives = {}
    for name, net in model['netnames'].items():
        for index, bit in enumerate(net['bits']):
            if type(bit) is int:
                label = name + '\0' + str(index)
                representatives[bit] = min(label, representatives.get(bit, label))

    def bits(values):
        return [representatives[v] if type(v) is int else 'constant:' + v for v in values]

    nets, cells, ports = (hashlib.sha256() for _ in range(3))
    for name, net in sorted(model['netnames'].items()):
        nets.update(json.dumps([name, net.get('offset', 0), net.get('upto', 0), bits(net['bits'])]).encode())
    for name, cell in sorted(model['cells'].items()):
        cells.update(json.dumps([name, cell['type'], sorted(cell.get('parameters', {}).items()),
                                 [[pin, bits(value)] for pin, value in sorted(cell['connections'].items())]]).encode())
    for name, port in sorted(model['ports'].items()):
        ports.update(json.dumps([name, port['direction'], bits(port['bits'])]).encode())
    return dict(net_alias_classes=nets.hexdigest(), cell_pin_connectivity=cells.hexdigest(),
                top_ports=ports.hexdigest(), leaves=len(model['cells']))


def verify_standalone_cache(directory):
    """Validate the preserved complete standalone probe, never a CPU score.

    This separate diagnostic route cannot bypass the default CPU verifier.
    Require both the completed parent probe and independent physical pricing.
    """
    parent = json.loads((directory.parent / 'report.json').read_text())
    audit = json.loads((directory / 'area_audit.json').read_text())
    if parent['status'] != 'COMPLETE' or not parent['not_a_cpu_result'] or \
            parent['integrated_into_cpu'] or audit['status'] != 'COMPLETE' or \
            not audit['is_test_fixture'] or not audit['not_a_cpu_result'] or \
            audit['includes_axi_adapter'] or audit['unpriced_leaf_instances'] or \
            audit['unmapped_memory_cells']:
        raise SystemExit('Not a completed, fully priced standalone Cache probe')
    snapshot = directory.parent / 'source_snapshot'
    for name, expected in parent['snapshot_sha256'].items():
        if sha256(snapshot / name) != expected:
            raise SystemExit('Standalone frozen source changed: ' + name)
    rows = [row for row in parent['results']
            if row['parameters'] == audit['settings']['parameters']]
    if len(rows) != 1 or rows[0]['netlist_sha256'] != audit['netlist_sha256'] or \
            sha256(directory / 'mapped.v') != audit['netlist_sha256']:
        raise SystemExit('Standalone probe/netlist configuration mismatch')
    statistics = json.loads((directory / 'stat.json').read_text())
    leaves, hierarchy = expand_stat_census(statistics)
    if leaves != Counter(audit['leaf_counts']) or sum(leaves.values()) != audit['leaf_instances'] or \
            sum(hierarchy.values()) != audit['functional_hierarchy_instances']:
        raise SystemExit('Standalone physical census changed')
    model = json.loads((directory / 'design.json').read_text())['modules']['student_top']
    if hierarchy or Counter(cell['type'] for cell in model['cells'].values()) != leaves:
        raise SystemExit('Diagnostic currently requires an actual flat Cache netlist')
    prices, standard, sram = {}, [], set()
    for entry in audit['libraries']:
        lib = Path(entry['path'])
        if sha256(lib) != entry['sha256']:
            raise SystemExit('Standalone raw library changed: ' + str(lib))
        if lib.parent == snapshot / '.deps/course_asap7_r28/lib':
            standard.append(lib)
            if sha256(lib) != parent['snapshot_sha256'][lib.relative_to(snapshot).as_posix()]:
                raise SystemExit('Standalone standard library is not frozen original')
        elif lib.parent != directory / 'ram':
            raise SystemExit('Unexpected standalone raw library location')
        for kind, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                                     lib.read_text(), re.S):
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            if not match:
                raise SystemExit('Standalone leaf has no raw price: ' + kind)
            price = Decimal(match[1])
            if kind in prices and prices[kind] != price:
                raise SystemExit('Standalone conflicting raw price: ' + kind)
            prices[kind] = price
            if lib.parent == directory / 'ram':
                sram.add(kind)
    if len(standard) != 5 or sum('_SEQ_' in lib.name for lib in standard) != 1 or set(leaves) - set(prices):
        raise SystemExit('Standalone five-library/all-leaf requirement violated')
    actual_sram = Counter(row['module'] for row in audit['area']['sram_instances'])
    if actual_sram != Counter({kind: count for kind, count in leaves.items() if kind in sram}) or \
            sum(actual_sram.values()) != rows[0]['sram_instances']:
        raise SystemExit('Standalone actual SRAM census differs')
    total = sum((prices[kind] * count for kind, count in leaves.items()), Decimal(0))
    if total != Decimal(audit['independent_area_um2']) or total != Decimal(rows[0]['area_um2']) or \
            abs(total - Decimal(str(audit['area']['area_um2']))) >= Decimal('0.00001'):
        raise SystemExit('Standalone independent raw-price total differs')
    return dict(netlist_sha256=audit['netlist_sha256'], leaf_instances=sum(leaves.values()),
                not_a_cpu_result=True, actual_sram_instances=sum(actual_sram.values()))


def prepared_registers(path):
    """Extract exact original FF identities and the dfflibmap output inversion."""
    flipflops, inversions = {}, {}
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
                    inversions[ports['A']] = ports['Y']
                else:
                    flipflops[name] = (kind, dict(ports))
                active = None
    return flipflops, inversions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--cell', action='append', required=True)
    parser.add_argument('--standalone-cache', action='store_true',
                        help='Diagnostic only: validate a complete standalone Cache probe, never CPU PPA')
    parser.add_argument('--recreate-prepared-registers', action='store_true',
                        help='Standalone only: replay the preserved pre-ABC preparation into the diagnostic directory')
    args = parser.parse_args()
    directory, out = args.directory.resolve(), args.outdir.resolve()
    if args.recreate_prepared_registers and not args.standalone_cache:
        parser.error('Prepared replay is only supported for the standalone Cache diagnostic')
    if args.standalone_cache and out.exists():
        raise SystemExit('Choose a fresh standalone diagnostic directory')
    checked = verify_standalone_cache(directory) if args.standalone_cache else verify(directory)
    out.mkdir(parents=True, exist_ok=True)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    renamed, identity = out / 'normal_names.v', out / 'original_names.v'
    script = out / 'identity.ys'
    script.write_text('\n'.join([
        'read_json ' + quote(directory / 'design.json'),
        'write_verilog -noattr -noexpr ' + quote(renamed),
        'write_verilog -noattr -noexpr -norename ' + quote(identity),
    ]) + '\n')
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    frozen_inputs = [directory / name for name in ('design.json', 'mapped.v', 'stat.json', 'area_audit.json')]
    if args.standalone_cache:
        frozen_inputs.append(directory.parent / 'report.json')
    original_hashes = {str(path): sha256(path) for path in frozen_inputs}
    prepared_ffs, inversions = {}, {}
    if args.recreate_prepared_registers:
        original_script = directory / 'map.ys'
        commands = original_script.read_text().splitlines()
        boundaries = [index for index, command in enumerate(commands) if command.startswith('abc ')]
        if len(boundaries) != 1:
            raise SystemExit('Preserved standalone map has no unique original ABC boundary')
        preparation, prepared = out / 'register_identity.ys', out / 'prepared.il'
        preparation.write_text('\n'.join(commands[:boundaries[0]] +
            ['write_rtlil ' + quote(prepared)]) + '\n')
        print('START diagnostic original pre-ABC register identity replay', flush=True)
        with (out / 'register_identity.log').open('w') as log:
            subprocess.run([str(yosys), '-T', '-s', str(preparation)], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        prepared_ffs, inversions = prepared_registers(prepared)
        frozen_inputs += [original_script, preparation, prepared]
        print('DONE diagnostic register identity replay; graded outputs unchanged', flush=True)
    with (out / 'identity.log').open('w') as log:
        subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    byte_identical = sha256(renamed) == checked['netlist_sha256']
    # read_json can choose another equivalent public alias when printing a
    # connection. Validate all named net equivalence classes and every physical
    # cell pin, not just the selected endpoint or a positional name guess.
    connectivity_script = out / 'connectivity.ys'
    originals, reexported = out / 'graded_reread.json', out / 'reexport_reread.json'
    libraries = [Path(row['path']) for row in json.loads((directory / 'area_audit.json').read_text())['libraries']]
    commands = []
    for verilog, destination in ((directory / 'mapped.v', originals), (renamed, reexported)):
        commands.extend(['design -reset',
                         *['read_liberty -lib -ignore_miss_func ' + quote(lib) for lib in libraries],
                         'read_verilog ' + quote(verilog), 'hierarchy -check -top student_top',
                         'check -assert -mapped', 'write_json ' + quote(destination)])
    connectivity_script.write_text('\n'.join(commands) + '\n')
    with (out / 'connectivity.log').open('w') as log:
        subprocess.run([str(yosys), '-T', '-s', str(connectivity_script)], env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    graded_graph, exported_graph = wiring_fingerprint(originals), wiring_fingerprint(reexported)
    if graded_graph != exported_graph:
        raise SystemExit('Re-export changes complete physical wiring/alias connectivity')
    normal_cells, original_cells = declarations(renamed), declarations(identity)
    if len(normal_cells) != len(original_cells) or len(normal_cells) != checked['leaf_instances']:
        raise SystemExit('Leaf declaration census differs')
    model = json.loads((directory / 'design.json').read_text())['modules']['student_top']
    resolved = {}
    for (kind, printed), (original_kind, original) in zip(normal_cells, original_cells):
        if kind != original_kind or original not in model['cells'] or model['cells'][original]['type'] != kind:
            raise SystemExit('Re-exported identity/type mismatch')
        if printed in resolved:
            raise SystemExit('Duplicate printed leaf identity')
        resolved[printed] = original
    if set(resolved.values()) != set(model['cells']):
        raise SystemExit('Original JSON leaf identity census differs')
    fanout = Counter()
    for cell in model['cells'].values():
        for pin, bits in cell['connections'].items():
            if cell['port_directions'][pin] == 'input' and pin != 'CLK':
                fanout.update(bit for bit in bits if type(bit) is int)
    aliases = {}
    for name, net in model['netnames'].items():
        if net['hide_name']:
            continue
        for index, bit in enumerate(net['bits']):
            if type(bit) is int:
                aliases.setdefault(bit, []).append(f'{name}[{index}]')
    rows = []
    for printed in args.cell:
        original = resolved[printed]
        cell = model['cells'][original]
        outputs = {pin: [dict(bit=bit, fanout=fanout[bit], aliases=aliases.get(bit, []))
                         for bit in bits]
                   for pin, bits in cell['connections'].items() if cell['port_directions'][pin] == 'output'}
        register = prepared_ffs.get(original)
        if register and register[0] != cell['type']:
            raise SystemExit('Replayed/final FF type differs: ' + original)
        rows.append(dict(printed=printed, original=original, cell_type=cell['type'],
                         connections=cell['connections'], outputs=outputs,
                         prepared_q_signals={pin: inversions.get(signal, signal)
                            for pin, signal in (register[1] if register else {}).items()
                            if pin in ('Q', 'QN')}))
    for name, expected in original_hashes.items():
        if sha256(Path(name)) != expected:
            raise SystemExit('Original mapped diagnostic input changed: ' + name)
    result = dict(status='COMPLETE', diagnostic_only=True, netlist_sha256=checked['netlist_sha256'],
                  normal_reexport_byte_identical=byte_identical,
                  complete_physical_wiring_identical=True, wiring_fingerprint=graded_graph,
                  leaf_instances=len(resolved), rows=rows,
                  input_sha256={str(path): sha256(path) for path in (
                      directory / 'design.json', directory / 'mapped.v', script, connectivity_script,
                      originals, reexported, yosys, Path(__file__))},
                  original_name_verilog_sha256=sha256(identity))
    result['input_sha256'].update({str(path): sha256(path) for path in frozen_inputs})
    result['not_a_cpu_result'] = bool(args.standalone_cache)
    result['standalone_cache_diagnostic'] = bool(args.standalone_cache)
    (out / 'identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status='COMPLETE', rows=rows), indent=2))


if __name__ == '__main__':
    main()
