"""Resolve actual standalone component STA identities across functional hierarchy.

Read-only diagnostic, never a CPU score or a weaker route through the CPU
verifier. Independently check raw prices, every physical leaf, actual SRAM,
source snapshots and the complete hierarchy's named-net/cell-pin fingerprints.
The original graded graph and timing are not changed.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from audit_timing_identity import prepared_registers
from verify_course_axi_area import expand_stat_census, sha256

ROOT = Path(__file__).resolve().parents[1]


def quote(path):
    return '"' + Path(path).resolve().as_posix() + '"'


def verify_component(directory):
    parent = json.loads((directory.parent / 'report.json').read_text())
    audit = json.loads((directory / 'area_audit.json').read_text())
    assert parent['status'] == audit['status'] == 'COMPLETE'
    assert parent['not_a_cpu_result'] and not parent['integrated_into_cpu']
    assert audit['not_a_cpu_result'] and audit['is_test_fixture']
    assert not audit['includes_axi_adapter']
    assert audit['unpriced_leaf_instances'] == audit['unmapped_memory_cells'] == 0
    snapshot = directory.parent / 'source_snapshot'
    for name, expected in parent['snapshot_sha256'].items():
        assert sha256(snapshot / name) == expected, 'Changed frozen source: ' + name
    matches = [row for row in parent['results']
               if row['parameters'] == audit['settings']['parameters']]
    assert len(matches) == 1
    row = matches[0]
    assert sha256(directory / 'mapped.v') == row['netlist_sha256'] == audit['netlist_sha256']
    statistics = json.loads((directory / 'stat.json').read_text())
    leaves, hierarchy = expand_stat_census(statistics)
    assert leaves == Counter(audit['leaf_counts'])
    assert sum(leaves.values()) == audit['leaf_instances']
    assert sum(hierarchy.values()) == audit['functional_hierarchy_instances']
    model = json.loads((directory / 'design.json').read_text())['modules']
    functional = {name.removeprefix('\\') for name in statistics['modules']}
    reached = set()

    def visit(name, parents=()):
        assert name not in parents, 'Recursive physical hierarchy'
        reached.add(name)
        result = Counter()
        for cell in model[name]['cells'].values():
            kind = cell['type']
            if kind in functional:
                result.update(visit(kind, parents + (name,)))
            else:
                result[kind] += 1
        return result

    assert visit('student_top') == leaves
    assert reached == functional, 'Unreachable functional module'
    prices, sram, standards = {}, set(), []
    libraries = []
    for entry in audit['libraries']:
        lib = Path(entry['path'])
        libraries.append(lib)
        assert sha256(lib) == entry['sha256'], 'Changed raw library'
        if lib.parent == snapshot / '.deps/course_asap7_r28/lib':
            standards.append(lib)
            assert sha256(lib) == parent['snapshot_sha256'][lib.relative_to(snapshot).as_posix()]
        else:
            assert lib.parent == directory / 'ram', 'Unexpected library source'
        for kind, body in re.findall(r'\bcell\s*\(\s*([^\s)]+)\s*\)\s*\{(.*?)(?=\bcell\s*\(|\Z)',
                                     lib.read_text(), re.S):
            match = re.search(r'\barea\s*:\s*([0-9.eE+-]+)(?:[ \t]*;|[ \t]*\r?$)', body, re.M)
            assert match, 'Missing raw leaf price'
            price = Decimal(match[1])
            assert kind not in prices or prices[kind] == price
            prices[kind] = price
            if lib.parent == directory / 'ram':
                sram.add(kind)
    assert len(standards) == 5 and sum('_SEQ_' in lib.name for lib in standards) == 1
    assert not (set(leaves) - set(prices)), 'Unpriced physical leaf'
    actual_sram = Counter(item['module'] for item in audit['area']['sram_instances'])
    assert actual_sram == Counter({kind: count for kind, count in leaves.items() if kind in sram})
    assert sum(actual_sram.values()) == row['sram_instances']
    total = sum((prices[kind] * count for kind, count in leaves.items()), Decimal(0))
    assert total == Decimal(audit['independent_area_um2']) == Decimal(row['area_um2'])
    assert abs(total - Decimal(str(audit['area']['area_um2']))) < Decimal('0.00001')
    timing = json.loads((directory / 'full_timing_audit.json').read_text())
    assert timing['status'] == 'COMPLETE' and timing['not_a_cpu_result']
    assert timing['includes_sram'] and timing['omitted_memory_boundaries'] == 0
    assert timing['netlist_sha256'] == audit['netlist_sha256']
    assert timing['estimated_fmax_mhz'] == row['estimated_fmax_mhz']
    return model, functional, libraries, audit, leaves


def declarations(path):
    module, result = None, []
    for line in path.read_text().splitlines():
        start = re.match(r'^module\s+([^\s(]+)', line)
        if start:
            module = start[1].lstrip('\\')
        cell = re.match(r'^  (\\\S+|[A-Za-z_$][\w$]*)\s+(\\\S+|[A-Za-z_$][\w$]*)\s+\($', line)
        if cell:
            result.append((module, cell[1].lstrip('\\'), cell[2].lstrip('\\')))
    return result


def fingerprint(path, functional):
    raw_modules = json.loads(path.read_text())['modules']
    # Re-reading escaped parameterized module identifiers can retain the
    # writer's leading escape in JSON. Normalize that namespace explicitly,
    # and reject collisions rather than ignoring an unmatched module.
    modules = {name.removeprefix('\\'): module for name, module in raw_modules.items()}
    assert len(modules) == len(raw_modules), 'Ambiguous reread module namespace'
    digest = hashlib.sha256()
    for name in sorted(functional):
        module = modules[name]
        reps = {}
        for netname, net in module['netnames'].items():
            for index, bit in enumerate(net['bits']):
                if type(bit) is int:
                    label = netname + '\0' + str(index)
                    reps[bit] = min(label, reps.get(bit, label))

        def bits(values):
            return [reps[bit] if type(bit) is int else 'constant:' + bit for bit in values]

        digest.update(name.encode())
        for netname, net in sorted(module['netnames'].items()):
            digest.update(json.dumps([netname, net.get('offset', 0), net.get('upto', 0), bits(net['bits'])]).encode())
        for cellname, cell in sorted(module['cells'].items()):
            digest.update(json.dumps([cellname, cell['type'], sorted(cell.get('parameters', {}).items()),
                [[pin, bits(value)] for pin, value in sorted(cell['connections'].items())]]).encode())
        for portname, port in sorted(module['ports'].items()):
            digest.update(json.dumps([portname, port['direction'], bits(port['bits'])]).encode())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--cell', action='append', required=True,
                        help='Printed cell in the root module; all hierarchy is checked')
    args = parser.parse_args()
    directory, out = args.directory.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh component identity diagnostic directory')
    modules, functional, libraries, audit, leaves = verify_component(directory)
    inputs = [directory / name for name in ('design.json', 'mapped.v', 'stat.json',
                                           'area_audit.json', 'full_timing_audit.json', 'map.ys')]
    inputs += [directory.parent / 'report.json', Path(__file__),
               ROOT / 'tools/audit_timing_identity.py', ROOT / 'tools/verify_course_axi_area.py',
               *libraries]
    hashes = {str(path): sha256(path) for path in inputs}
    out.mkdir(parents=True)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']

    def run(name, commands):
        script, log = out / (name + '.ys'), out / (name + '.log')
        script.write_text('\n'.join(commands) + '\n')
        print('START component diagnostic ' + name, flush=True)
        with log.open('w') as stream:
            subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        print('DONE component diagnostic ' + name, flush=True)
        hashes[str(script)] = sha256(script)

    normal, original = out / 'normal.v', out / 'original.v'
    run('names', ['read_json ' + quote(directory / 'design.json'),
                 'write_verilog -noattr -noexpr ' + quote(normal),
                 'write_verilog -noattr -noexpr -norename ' + quote(original)])
    commands = []
    graded, reread = out / 'graded.json', out / 'reexport.json'
    for source, target in ((directory / 'mapped.v', graded), (normal, reread)):
        commands += ['design -reset', *['read_liberty -lib -ignore_miss_func ' + quote(lib) for lib in libraries],
                     'read_verilog ' + quote(source), 'hierarchy -check -top student_top',
                     'check -assert -mapped', 'write_json ' + quote(target)]
    run('wiring', commands)
    wiring = fingerprint(graded, functional)
    assert wiring == fingerprint(reread, functional), 'Full hierarchical physical wiring differs'
    normal_cells, original_cells = declarations(normal), declarations(original)
    assert len(normal_cells) == len(original_cells) == sum(len(modules[name]['cells']) for name in functional)
    resolved = {}
    for (scope, kind, printed), (original_scope, original_kind, name) in zip(normal_cells, original_cells):
        assert scope == original_scope and kind == original_kind
        assert modules[scope]['cells'][name]['type'] == kind
        key = (scope, printed)
        assert key not in resolved
        resolved[key] = name
    commands = (directory / 'map.ys').read_text().splitlines()
    abc = [index for index, command in enumerate(commands) if command.startswith('abc ')]
    assert len(abc) == 1
    prepared = out / 'prepared.il'
    run('registers', commands[:abc[0]] + ['write_rtlil ' + quote(prepared)])
    flops, inversions = prepared_registers(prepared)
    root = modules['student_top']
    fanout = Counter(bit for cell in root['cells'].values()
                     for pin, bits in cell['connections'].items()
                     if cell['port_directions'][pin] == 'input' and pin != 'CLK'
                     for bit in bits if type(bit) is int)
    rows = []
    for printed in args.cell:
        name = resolved[('student_top', printed)]
        cell = root['cells'][name]
        flop = flops.get(name)
        if flop:
            assert flop[0] == cell['type']
        rows.append(dict(printed=printed, scope='student_top', original=name, cell_type=cell['type'],
                         connections=cell['connections'],
                         outputs={pin: [dict(bit=bit, root_pin_fanout=fanout[bit]) for bit in bits]
                                  for pin, bits in cell['connections'].items()
                                  if cell['port_directions'][pin] == 'output'},
                         prepared_q_signals={pin: inversions.get(signal, signal)
                                            for pin, signal in (flop[1] if flop else {}).items()
                                            if pin in ('Q', 'QN')}))
    for name, expected in hashes.items():
        assert sha256(Path(name)) == expected, 'Changed diagnostic input: ' + name
    hashes.update({str(path): sha256(path) for path in (prepared, normal, original, graded, reread, yosys)})
    report = dict(status='COMPLETE', diagnostic_only=True, not_a_cpu_result=True,
                  complete_hierarchical_wiring_identical=True, wiring_fingerprint=wiring,
                  actual_leaf_instances=sum(leaves.values()), functional_modules=len(functional),
                  netlist_sha256=audit['netlist_sha256'], rows=rows, input_sha256=hashes)
    (out / 'identity.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status='COMPLETE', rows=rows), indent=2))


if __name__ == '__main__':
    main()
