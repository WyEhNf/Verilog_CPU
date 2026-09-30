"""Price a fully mapped cpu_core with the course's own area_report function."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.directory.resolve()
    manifest = json.loads((out / 'run_manifest.json').read_text())
    if manifest['mapping_options']['abc_mode'] != 'course':
        raise SystemExit('Expected course library/ABC mapping')
    for name, expected in manifest['source_sha256'].items():
        if digest(root / name) != expected:
            raise SystemExit('Frozen synthesis input changed: ' + name)
    libdir = Path(manifest['mapping_options']['lib_dir'])
    libs = sorted(libdir.glob('*.lib'))
    framework = root / '.deps/RISC-V-CPU-2026'
    framework_revision = subprocess.check_output(
        ['git', '-C', str(framework), 'rev-parse', 'HEAD'], text=True).strip()
    module_files = [out / ('mapped_' + line.split('\t', 1)[0] + '.il')
                    for line in (out / 'modules.tsv').read_text().splitlines()]
    libargs = ' '.join('-liberty ' + path.as_posix() for path in libs)
    script = '\n'.join([
        *['read_liberty -lib -ignore_miss_func ' + p.as_posix() for p in libs],
        *['read_rtlil ' + p.as_posix() for p in module_files],
        'hierarchy -check -top cpu_core',
        'select -assert-none t:$* t:$paramod* %d',
        # Only rename the root; all CPU ports and instance multiplicities stay.
        'rename cpu_core student_top',
        'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
        'check -assert -mapped',
        f'tee -o {out.as_posix()}/course_stat.json stat -json {libargs}',
        f'write_json {out.as_posix()}/course_design.json',
        f'write_verilog -noattr -noexpr {out.as_posix()}/course_mapped.v',
    ]) + '\n'
    script_path = out / 'course_area.ys'
    script_path.write_text(script, encoding='utf-8')
    suite = root / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    with (out / 'course_area.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script_path)],
                       cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    spec = importlib.util.spec_from_file_location('course_synth_report', framework / 'scripts/synth_report.py')
    course_report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(course_report)
    design = json.loads((out / 'course_design.json').read_text())
    statistics = json.loads((out / 'course_stat.json').read_text())
    area = course_report.area_report(design, statistics, {})
    leaves = Counter()
    def visit(kind, ancestors=()):
        if kind in ancestors:
            raise ValueError('Recursive hierarchy')
        for cell in design['modules'][kind].get('cells', {}).values():
            child = cell['type']
            if child.endswith('_ASAP7_75t_R') and 'area' in design['modules'].get(child, {}).get('attributes', {}):
                leaves[child] += 1
            else:
                visit(child, ancestors + (kind,))
    visit('student_top')
    independent = sum((Decimal(str(design['modules'][cell]['attributes']['area'])) * count
                       for cell, count in leaves.items()), Decimal(0))
    if abs(independent - Decimal(str(area['area_um2']))) > Decimal('0.00001'):
        raise ValueError('Independent leaf pricing and official reporting differ')
    # Yosys 0.68 includes hierarchy-instance entries in this dictionary while
    # num_cells and area describe leaf cells. Compare the priced leaf subset.
    stat_leaves = {kind: count for kind, count in statistics['design']['num_cells_by_type'].items()
                   if kind.endswith('_ASAP7_75t_R')}
    if dict(leaves) != stat_leaves or sum(leaves.values()) != statistics['design']['num_cells']:
        raise ValueError('Independent leaf counts and Yosys counts differ')
    for name, expected in manifest['source_sha256'].items():
        if digest(root / name) != expected:
            raise ValueError('Input changed during reporting: ' + name)
    result = dict(status='COMPLETE', area=area,
                  independent_area_um2=float(independent), leaf_instances=sum(leaves.values()),
                  unpriced_leaf_instances=0, unmapped_memory_cells=0,
                  external_ram_included=False, framework_revision=framework_revision,
                  mapping_options=manifest['mapping_options'],
                  run_manifest=str(out / 'run_manifest.json'),
                  framework_sources={name: digest(framework / 'scripts' / name)
                                     for name in ('fakeram.py', 'synth_report.py', 'synth.py')},
                  mapped_module_sha256={p.name: digest(p) for p in module_files},
                  course_netlist_sha256=digest(out / 'course_mapped.v'),
                  reporter_sha256=digest(Path(__file__)),
                  mapping='Per-module memory expansion/ABC mapping, hierarchy retained; '
                          'course r28 unmodified libraries and area_report; tie cells included. '
                          'This is not the official flattened opt netlist. No timing score established.')
    (out / 'course_area_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('area', 'mapped_module_sha256')}, indent=2))
    print(json.dumps({k: v for k, v in area.items() if k not in ('module_tree', 'sram_instances')}, indent=2))


if __name__ == '__main__':
    main()
