"""Audit a complete hierarchical AXI netlist with an already mapped CPU core.

This is an actual linked, fully priced netlist, not an estimated adapter sum.
The frozen elaborated top supplies the exact connections and adapter parameters.
Core parameter/source identity is checked before reusing its mapped implementation.
Global cross-boundary ABC optimization is deliberately NOT claimed.
"""
import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess

from run_course_sram_area import ROOT, digest, load_course, quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-run', type=Path, required=True)
    parser.add_argument('--core-run', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    full, core, out = (path.resolve() for path in (args.full_run, args.core_run, args.outdir))
    if out.exists():
        raise SystemExit('Use a new output directory')
    manifest = json.loads((full / 'run_manifest.json').read_text())
    core_manifest = json.loads((core / 'run_manifest.json').read_text())
    core_audit = json.loads((core / 'area_audit.json').read_text())
    if core_audit['status'] != 'COMPLETE' or core_audit['unpriced_leaf_instances']:
        raise ValueError('Fully priced core required')
    frozen = dict(manifest['source_sha256'])
    for name, value in core_manifest['source_sha256'].items():
        if name in frozen and frozen[name] != value:
            raise ValueError('New course CPU source differs from mapped core: ' + name)
        frozen[name] = value
    frozen[Path(__file__).relative_to(ROOT).as_posix()] = digest(Path(__file__))
    artifact_inputs = {
        str(full / 'elaborated.json'): digest(full / 'elaborated.json'),
        str(core / 'design.json'): digest(core / 'design.json'),
        str(core / 'area_audit.json'): digest(core / 'area_audit.json'),
        str(core / 'mapped.v'): core_audit['netlist_sha256'],
        str(core / 'ram/manifest.json'): digest(core / 'ram/manifest.json'),
        **{entry['path']: entry['sha256'] for entry in core_audit['libraries']},
    }

    def check_inputs():
        for name, expected in frozen.items():
            if digest(ROOT / name) != expected.lower():
                raise ValueError('Frozen source changed: ' + name)
        for name, expected in artifact_inputs.items():
            if digest(Path(name)) != expected.lower():
                raise ValueError('Frozen artifact changed: ' + name)

    check_inputs()
    elaborated = json.loads((full / 'elaborated.json').read_text())
    mapped = json.loads((core / 'design.json').read_text())
    top = elaborated['modules']['student_top']
    core_type, bus_type = (top['cells'][name]['type'] for name in ('core', 'bus'))
    actual_core = elaborated['modules'][core_type]
    actual_params = {key: int(value, 2)
                     for key, value in actual_core['parameter_default_values'].items()}
    for key, value in core_manifest['settings']['parameters'].items():
        if actual_params.get(key) != value:
            raise ValueError('Mapped core parameter mismatch: ' + key)
    old_core = mapped['modules']['student_top']
    shape = lambda module: {key: (port['direction'], len(port['bits']))
                            for key, port in module['ports'].items()}
    if shape(actual_core) != shape(old_core):
        raise ValueError('Mapped core interface differs from elaborated core')
    # Replace only the elaborated CPU implementation. Root wiring, the derived
    # AXI module and its actual parameters come unchanged from current RTL.
    modules = {name: module for name, module in mapped['modules'].items() if name != 'student_top'}
    modules[core_type] = old_core
    modules['student_top'] = top
    modules[bus_type] = elaborated['modules'][bus_type]
    combined = {'creator': mapped.get('creator', ''), 'modules': modules}
    out.mkdir(parents=True)
    (out / 'combined.json').write_text(json.dumps(combined))
    del elaborated, mapped, combined, modules
    settings = dict(manifest['settings'], mode='incremental-hierarchical',
                    mapped_core_reused=True, global_flatten_optimization=False,
                    parameters=actual_params)
    run_manifest = dict(source_sha256=frozen, artifact_sha256=artifact_inputs, settings=settings,
                        frozen_elaboration=str(full), frozen_core=str(core))
    (out / 'run_manifest.json').write_text(json.dumps(run_manifest, indent=2) + '\n')
    libs = [Path(entry['path']) for entry in core_audit['libraries']]
    seq = next(path for path in libs if '_SEQ_' in path.name)
    standard = [path for path in libs if '_ASAP7_' not in path.name and '_RVT_' in path.name]
    if len(standard) != 5:
        raise ValueError('Five raw standard-cell libraries required')
    libargs = ' '.join('-liberty ' + quote(path) for path in standard)
    all_libargs = ' '.join('-liberty ' + quote(path) for path in libs)
    libreads = ['read_liberty -lib -ignore_miss_func ' + quote(path) for path in libs]
    script = '\n'.join([
        'read_json ' + quote(out / 'combined.json'),
        'hierarchy -check -top student_top', 'synth -top student_top -noabc',
        'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
        'dfflibmap -liberty ' + quote(seq),
        'abc ' + libargs + f" -D {settings['clock_period_ns'] * 1000:.9g}",
        'clean', 'delete t:$scopeinfo', 'clean -purge',
        'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
        'check -assert -mapped',
        'tee -o ' + quote(out / 'stat.json') + ' stat -json ' + all_libargs,
        'write_json ' + quote(out / 'design.json'),
        'write_verilog -noattr -noexpr ' + quote(out / 'mapped.v'),
        'design -reset', *libreads, 'read_verilog ' + quote(out / 'mapped.v'),
        'hierarchy -check -top student_top', 'check -assert -mapped',
    ]) + '\n'
    (out / 'map.ys').write_text(script)
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    print('START full hierarchical AXI mapping', flush=True)
    with (out / 'map.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(out / 'map.ys')],
                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    design = json.loads((out / 'design.json').read_text())
    stats = json.loads((out / 'stat.json').read_text())
    macros = json.loads((core / 'ram/manifest.json').read_text())['macros']
    reporter = load_course('synth_report')
    area = reporter.area_report(design, stats, macros)
    leaves = Counter()

    def visit(kind, ancestors=()):
        if kind in ancestors:
            raise ValueError('recursive hierarchy')
        for cell in design['modules'][kind].get('cells', {}).values():
            child = cell['type']
            attrs = design['modules'].get(child, {}).get('attributes', {})
            if child in macros or child.endswith('_ASAP7_75t_R'):
                if 'area' not in attrs:
                    raise ValueError('unpriced cell ' + child)
                leaves[child] += 1
            else:
                visit(child, ancestors + (kind,))

    visit('student_top')
    independent = sum((Decimal(str(design['modules'][kind]['attributes']['area'])) * count
                       for kind, count in leaves.items()), Decimal(0))
    if abs(independent - Decimal(str(area['area_um2']))) > Decimal('0.00001'):
        raise ValueError('course and independent area sums disagree')
    if sum(leaves.values()) != stats['design']['num_cells']:
        raise ValueError('independent and Yosys leaf counts disagree')
    if stats['design']['num_memories'] or stats['design']['num_memory_bits']:
        raise ValueError('unmapped memory objects remain')
    if len(area['sram_instances']) != 16:
        raise ValueError('SRAM instances changed unexpectedly')
    check_inputs()
    result = dict(status='COMPLETE', area=area, independent_area_um2=float(independent),
                  leaf_instances=sum(leaves.values()), leaf_counts=dict(leaves),
                  unpriced_leaf_instances=0, unmapped_memory_cells=0,
                  includes_axi_adapter=True, external_ram_included=False, timing_analyzed=False,
                  settings=settings, sram_model=core_audit['sram_model'],
                  libraries=core_audit['libraries'], netlist_sha256=digest(out / 'mapped.v'),
                  run_manifest=str(out / 'run_manifest.json'))
    (out / 'area_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in area.items()
                      if key not in ('module_tree', 'sram_instances')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
