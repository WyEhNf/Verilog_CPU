"""Resolve full-CPU STA identities without changing its physical graph.

The verified course netlist may retain functional state-bank hierarchy. Check
all that hierarchy's named wires and cell pins before pairing printed names.
Use the existing frozen pre-ABC register file; never rerun or change synthesis.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess

from audit_component_timing_identity import declarations, fingerprint, quote
from audit_timing_identity import prepared_registers
from verify_course_axi_area import ROOT, expand_stat_census, sha256, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--cell', action='append', required=True)
    args = parser.parse_args()
    directory, out = args.directory.resolve(), args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh diagnostic directory')
    checked = verify(directory)
    audit = json.loads((directory/'area_audit.json').read_text())
    stats = json.loads((directory/'stat.json').read_text())
    leaves, hierarchy = expand_stat_census(stats)
    functional = {name.removeprefix('\\') for name in stats['modules']}
    modules = json.loads((directory/'design.json').read_text())['modules']
    libraries = [Path(row['path']) for row in audit['libraries']]
    inputs = [directory/name for name in ('design.json', 'mapped.v', 'stat.json',
              'area_audit.json', 'full_timing_audit.json', 'prepared.il')]
    inputs += libraries + [Path(__file__), ROOT/'tools/audit_component_timing_identity.py',
                          ROOT/'tools/audit_timing_identity.py', ROOT/'tools/verify_course_axi_area.py']
    hashes = {str(path):sha256(path) for path in inputs}
    out.mkdir(parents=True)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']

    def run(name, commands):
        script, log = out/(name+'.ys'), out/(name+'.log')
        script.write_text('\n'.join(commands)+'\n')
        print('START full CPU identity '+name, flush=True)
        with log.open('w') as stream:
            subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                           stdout=stream, stderr=subprocess.STDOUT, check=True)
        hashes[str(script)] = sha256(script)
        print('DONE full CPU identity '+name, flush=True)

    normal, original = out/'normal.v', out/'original.v'
    run('names', ['read_json '+quote(directory/'design.json'),
                 'write_verilog -noattr -noexpr '+quote(normal),
                 'write_verilog -noattr -noexpr -norename '+quote(original)])
    graded, reread = out/'graded.json', out/'reexport.json'
    commands = []
    for source, target in ((directory/'mapped.v', graded), (normal, reread)):
        commands += ['design -reset', *['read_liberty -lib -ignore_miss_func '+quote(lib) for lib in libraries],
                     'read_verilog '+quote(source), 'hierarchy -check -top student_top',
                     'check -assert -mapped', 'write_json '+quote(target)]
    run('wiring', commands)
    wiring = fingerprint(graded, functional)
    assert wiring == fingerprint(reread, functional), 'Full CPU physical graph changed'
    a, b = declarations(normal), declarations(original)
    assert len(a) == len(b) == sum(len(modules[n]['cells']) for n in functional)
    resolved = {}
    for (scope, kind, printed), (other_scope, other_kind, name) in zip(a, b):
        assert scope == other_scope and kind == other_kind
        assert modules[scope]['cells'][name]['type'] == kind
        assert (scope, printed) not in resolved
        resolved[(scope, printed)] = name
    flops, inversions = prepared_registers(directory/'prepared.il')
    root = modules['student_top']
    fanout = Counter(bit for cell in root['cells'].values()
                     for pin, bits in cell['connections'].items()
                     if cell['port_directions'][pin] == 'input' and pin != 'CLK'
                     for bit in bits if type(bit) is int)
    aliases = {}
    for name, net in root['netnames'].items():
        if not net['hide_name']:
            for index, bit in enumerate(net['bits']):
                if type(bit) is int:
                    aliases.setdefault(bit, []).append(f'{name}[{index}]')
    rows = []
    for printed in args.cell:
        name = resolved[('student_top', printed)]
        cell = root['cells'][name]
        flop = flops.get(name)
        if flop:
            assert flop[0] == cell['type']
        rows.append(dict(printed=printed, scope='student_top', original=name, cell_type=cell['type'],
                         connections=cell['connections'],
                         outputs={pin:[dict(bit=bit, root_pin_fanout=fanout[bit], aliases=aliases.get(bit, [])) for bit in bits]
                                  for pin, bits in cell['connections'].items()
                                  if cell['port_directions'][pin] == 'output'},
                         prepared_q_signals={pin:inversions.get(signal, signal)
                             for pin, signal in (flop[1] if flop else {}).items() if pin in ('Q', 'QN')}))
    for name, expected in hashes.items():
        assert sha256(Path(name)) == expected, 'Frozen diagnostic input changed: '+name
    hashes.update({str(path):sha256(path) for path in (normal, original, graded, reread, yosys)})
    result = dict(status='COMPLETE', diagnostic_only=True, input_is_full_cpu=True,
                  complete_hierarchical_wiring_identical=True, wiring_fingerprint=wiring,
                  actual_leaf_instances=sum(leaves.values()), functional_modules=len(functional),
                  functional_hierarchy_instances=sum(hierarchy.values()),
                  netlist_sha256=checked['netlist_sha256'], rows=rows, input_sha256=hashes)
    (out/'identity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='COMPLETE',rows=rows),indent=2))


if __name__ == '__main__':
    main()
