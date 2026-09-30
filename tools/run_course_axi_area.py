"""Fully synthesize the frozen, real course AXI student_top (not a core-only sum).

The course supplies SRAM lowering and area accounting. Use the same flattened
opt/default ABC sequence, with native Windows Yosys and explicit RTL headers.
No mapped core is reused and no zero-area memory or adapter boundary is allowed.
"""
import argparse
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from run_course_sram_area import ROOT, FRAMEWORK, digest, digest_bytes, load_course, quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--clock-period', type=float, default=10 / 3)
    parser.add_argument('--mode', choices=('opt', 'diagnose'), default='opt')
    parser.add_argument('--abc-script', choices=('standard', 'classic-area'), default='standard')
    parser.add_argument('--reuse-prepared-run', type=Path,
                        help='Reuse hash-verified elaboration/preparation, but run ABC anew')
    parser.add_argument('--lib-dir', type=Path, default=ROOT / '.deps/course_asap7_r28/lib')
    args = parser.parse_args()
    if not 0 < args.clock_period < float('inf'):
        parser.error('finite positive clock period required')
    build = json.loads(args.build_manifest.read_text(encoding='utf-8-sig'))
    if build.get('format') != 'course-axi-frozen-build-v1':
        raise SystemExit('A frozen course AXI build is required')
    if build['configuration'] not in ('student_top source defaults; no -G overrides',
                                       'student_top source defaults plus explicit -G overrides'):
        raise SystemExit('Unsupported frozen build configuration')
    defaults = {key: int(value) for key, value in re.findall(
        r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)',
        (ROOT / 'rtl/course/student_top.v').read_text())}
    overrides = build.get('parameter_overrides', {})
    if build['configuration'].endswith('no -G overrides') and overrides:
        raise ValueError('Unexpected overrides in a default build')
    for key, value in overrides.items():
        if key not in defaults or type(value) is not int or value < 0:
            raise ValueError('Unsupported frozen override: ' + key)
    parameters = defaults | overrides
    frozen = {name: value.lower() for name, value in build['source_sha256'].items()}
    input_root = ROOT

    def check_inputs():
        for name, expected in frozen.items():
            if digest(input_root / name) != expected:
                raise ValueError('Frozen input changed: ' + name)
        if digest(Path(build['executable'])) != build['executable_sha256'].lower():
            raise ValueError('Frozen executable changed')
        if digest(Path(build['generated_driver'])) != build['generated_driver_sha256'].lower():
            raise ValueError('Frozen observation driver changed')

    check_inputs()
    libs = sorted(args.lib_dir.resolve().glob('*.lib'))
    seq = [path for path in libs if '_SEQ_' in path.name]
    if len(libs) != 5 or len(seq) != 1:
        raise SystemExit('Five course RVT TT libraries required')
    sys.path.insert(0, str(FRAMEWORK / 'scripts'))
    course_build = load_course('build')
    sources = course_build.read_sources(ROOT / 'verilog/filelist.f')
    fakeram, reporter = load_course('fakeram'), load_course('synth_report')
    flow_inputs = [Path(__file__), ROOT / 'tools/run_course_sram_area.py',
                   FRAMEWORK / 'scripts/build.py', FRAMEWORK / 'scripts/toolchain.py',
                   FRAMEWORK / 'scripts/fakeram.py',
                   FRAMEWORK / 'scripts/synth_report.py', FRAMEWORK / 'scripts/synth.py',
                   FRAMEWORK / 'scripts/timing.py', FRAMEWORK / 'scripts/timing.tcl',
                   fakeram.RAM_SOURCE, *libs]
    for path in flow_inputs:
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    settings = dict(mode=args.mode, abc_script=args.abc_script, clock_port='clock',
                    clock_period_ns=args.clock_period, top='student_top',
                    parameters=parameters, parameter_overrides=overrides,
                    includes_axi_adapter=True, configuration=build['configuration'],
                    framework_revision=subprocess.check_output(
                        ['git', '-C', str(FRAMEWORK), 'rev-parse', 'HEAD'], text=True).strip())
    out = args.outdir.resolve()
    snapshot_root = out / 'source_snapshot'
    # Copy verified, immutable inputs before running expensive synthesis. All
    # Yosys source/header/library reads below use these copies, so later RTL
    # development cannot silently contaminate or invalidate a live candidate.
    check_inputs()
    for name, expected in frozen.items():
        destination = snapshot_root / name
        if destination.exists():
            if digest(destination) != expected:
                raise ValueError('Existing snapshot differs: ' + name)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        if digest(destination) != expected:
            raise ValueError('Snapshot copy differs: ' + name)
    input_root = snapshot_root
    check_inputs()
    sources = [snapshot_root / path.relative_to(ROOT) for path in sources]
    libs = [snapshot_root / path.relative_to(ROOT) for path in libs]
    seq = [path for path in libs if '_SEQ_' in path.name]
    frozen_ram_source = snapshot_root / fakeram.RAM_SOURCE.relative_to(ROOT)
    manifest = dict(source_sha256=frozen, settings=settings,
                    source_snapshot_root=str(snapshot_root),
                    build_manifest=str(args.build_manifest.resolve()),
                    build_manifest_sha256=digest(args.build_manifest),
                    executable_sha256=build['executable_sha256'])
    reuse = args.reuse_prepared_run.resolve() if args.reuse_prepared_run else None
    if reuse:
        if reuse == out:
            raise ValueError('Preparation reuse requires a distinct output directory')
        previous = json.loads((reuse / 'run_manifest.json').read_text())
        previous_sources = previous['source_sha256']
        # Only this orchestration file may differ: exact Yosys command equality
        # below proves that its reused stages have identical semantics.
        orchestrator = Path(__file__).relative_to(ROOT).as_posix()
        if (set(previous_sources) != set(frozen) or
                any(previous_sources[name] != expected for name, expected in frozen.items()
                    if name != orchestrator)):
            raise ValueError('Preparation source/library inputs differ')
        if ({key: value for key, value in previous['settings'].items() if key != 'abc_script'} !=
                {key: value for key, value in settings.items() if key != 'abc_script'}):
            raise ValueError('Preparation configuration differs')
        if (previous['build_manifest_sha256'] != manifest['build_manifest_sha256'] or
                previous['executable_sha256'] != manifest['executable_sha256']):
            raise ValueError('Preparation frozen simulation candidate differs')
        previous_root = Path(previous['source_snapshot_root'])
        for name, expected in previous_sources.items():
            if digest(previous_root / name) != expected:
                raise ValueError('Preparation snapshot changed: ' + name)
        manifest['reused_preparation'] = dict(
            directory=str(reuse),
            run_manifest_sha256=digest(reuse / 'run_manifest.json'),
            prepared_il_sha256=digest(reuse / 'prepared.il'))
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / 'run_manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise SystemExit('Inputs changed; use a new output directory')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']

    def run(name, commands, outputs):
        script = '\n'.join(commands) + '\n'
        script_path = out / (name + '.ys')
        marker = out / (name + '.done.json')
        expected = digest_bytes(script)
        check_inputs()
        if marker.exists():
            previous = json.loads(marker.read_text())
            if (previous['script_sha256'] == expected and
                    all(path.exists() and digest(path) == previous['output_sha256'].get(path.name)
                        for path in outputs)):
                print('RESUME ' + name, flush=True)
                return
            raise ValueError('Completed stage changed; use a new output directory: ' + name)
        if reuse and name in ('elaborate', 'prepare'):
            previous_script = reuse / (name + '.ys')
            previous_marker = reuse / (name + '.done.json')
            previous = json.loads(previous_marker.read_text())
            normalized = script.replace(out.as_posix(), reuse.as_posix())
            if (previous_script.read_text() != normalized or
                    digest_bytes(previous_script.read_text()) != previous['script_sha256']):
                raise ValueError('Reused stage commands differ: ' + name)
            for path in outputs:
                original = reuse / path.name
                if digest(original) != previous['output_sha256'].get(path.name):
                    raise ValueError('Reused stage output changed: ' + path.name)
                shutil.copyfile(original, path)
                if digest(path) != digest(original):
                    raise ValueError('Reused stage copy differs: ' + path.name)
            script_path.write_text(script)
            marker.write_text(json.dumps(dict(
                script_sha256=expected, seconds=0,
                reused_from=str(reuse), original_marker_sha256=digest(previous_marker),
                original_seconds=previous['seconds'],
                output_sha256={path.name: digest(path) for path in outputs})) + '\n')
            print('REUSE verified ' + name, flush=True)
            return
        script_path.write_text(script)
        start = time.monotonic()
        print('START ' + name, flush=True)
        with (out / (name + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script_path)],
                           cwd=snapshot_root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        check_inputs()
        marker.write_text(json.dumps(dict(script_sha256=expected,
                                          seconds=time.monotonic() - start,
                                          output_sha256={path.name: digest(path) for path in outputs})) + '\n')
        print('DONE ' + name, flush=True)

    run('elaborate', [
        *['read_verilog -sv -D SYNTHESIS -I rtl ' + quote(path)
          for path in sources if path != frozen_ram_source],
        'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(frozen_ram_source),
        *(['chparam ' + ' '.join('-set ' + key + ' ' + str(value)
                                 for key, value in sorted(overrides.items())) + ' student_top'] if overrides else []),
        'hierarchy -check -top student_top', 'proc', 'memory_collect',
        'write_json ' + quote(out / 'elaborated.json'),
    ], [out / 'elaborated.json'])
    elaborated = json.loads((out / 'elaborated.json').read_text())
    top = elaborated['modules']['student_top']
    if top['ports'].get('clock', {}).get('direction') != 'input':
        raise ValueError('The actual course AXI clock port is missing')
    if not any('rv32_axi_lite_bridge' in cell['type'] for cell in top['cells'].values()):
        raise ValueError('The actual AXI adapter is missing from the top')
    effective = {key: int(value, 2) for key, value in top.get('parameter_default_values', {}).items()}
    if effective != parameters:
        raise ValueError('Elaborated parameters differ from the frozen build: ' + repr(effective))
    prepared, wrappers, ram_libs, macros = fakeram.prepare_memories(elaborated, out / 'ram')
    del elaborated, top
    all_libs = [*libs, *ram_libs]
    libargs = ' '.join('-liberty ' + quote(path) for path in libs)
    all_libargs = ' '.join('-liberty ' + quote(path) for path in all_libs)
    libreads = ['read_liberty -lib -ignore_miss_func ' + quote(path) for path in all_libs]
    run('prepare', [
        'read_json ' + quote(prepared), 'read_verilog ' + quote(wrappers), *libreads,
        'hierarchy -check -top student_top', 'synth -top student_top -noabc ' +
        ('-flatten' if args.mode == 'opt' else '-hieropt'),
        'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
        'dfflibmap -liberty ' + quote(seq[0]), 'write_rtlil ' + quote(out / 'prepared.il'),
    ], [out / 'prepared.il'])
    abc = 'abc ' + libargs + f' -D {args.clock_period * 1000:.9g}'
    if args.abc_script == 'classic-area':
        abc = 'abc ' + libargs + ' -script "+strash;scorr;dc2;dretime;strash;map -a"'
    run('map', [
        'read_rtlil ' + quote(out / 'prepared.il'),
        abc, 'clean',
        'delete t:$scopeinfo', 'clean -purge',
        'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
        'check -assert -mapped',
        'tee -o ' + quote(out / 'stat.json') + ' stat -json ' + all_libargs,
        'write_json ' + quote(out / 'design.json'),
        'write_verilog -noattr -noexpr ' + quote(out / 'mapped.v'),
        'design -reset', *libreads, 'read_verilog ' + quote(out / 'mapped.v'),
        'hierarchy -check -top student_top', 'check -assert -mapped',
    ], [out / 'stat.json', out / 'design.json', out / 'mapped.v'])
    design = json.loads((out / 'design.json').read_text())
    stats = json.loads((out / 'stat.json').read_text())
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
    check_inputs()
    if digest(args.build_manifest) != manifest['build_manifest_sha256']:
        raise ValueError('Frozen build manifest changed during synthesis')
    result = dict(status='COMPLETE', area=area, independent_area_um2=float(independent),
                  leaf_instances=sum(leaves.values()), leaf_counts=dict(leaves),
                  unpriced_leaf_instances=0, unmapped_memory_cells=0,
                  external_ram_included=False, timing_analyzed=False,
                  includes_axi_adapter=True, netlist_sha256=digest(out / 'mapped.v'),
                  run_manifest=str(manifest_path), sram_model=fakeram.MODEL, settings=settings,
                  libraries=[dict(path=str(path), sha256=digest(path)) for path in all_libs])
    (out / 'area_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in area.items()
                      if key not in ('module_tree', 'sram_instances')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
