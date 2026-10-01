"""Resolve STA's printed cell names to the frozen Yosys/prepared identities.

The default Verilog writer renames hidden objects. Re-export the exact frozen
JSON both with and without that naming conversion, verify complete named-net
and cell-pin connectivity (including alias equivalences), and pair the unchanged
cell declarations. This does not alter the
graded netlist, timing constraints, libraries, or area.
"""
import argparse
from collections import Counter
import hashlib
import json
from itertools import zip_longest
import os
from pathlib import Path
import re
import subprocess

from verify_course_axi_area import sha256, verify


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--cell', action='append', required=True)
    args = parser.parse_args()
    directory, out = args.directory.resolve(), args.outdir.resolve()
    checked = verify(directory)
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
        rows.append(dict(printed=printed, original=original, cell_type=cell['type'],
                         connections=cell['connections'], outputs=outputs))
    result = dict(status='COMPLETE', diagnostic_only=True, netlist_sha256=checked['netlist_sha256'],
                  normal_reexport_byte_identical=byte_identical,
                  complete_physical_wiring_identical=True, wiring_fingerprint=graded_graph,
                  leaf_instances=len(resolved), rows=rows,
                  input_sha256={str(path): sha256(path) for path in (
                      directory / 'design.json', directory / 'mapped.v', script, connectivity_script,
                      originals, reexported, yosys, Path(__file__))},
                  original_name_verilog_sha256=sha256(identity))
    (out / 'identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status='COMPLETE', rows=rows), indent=2))


if __name__ == '__main__':
    main()
