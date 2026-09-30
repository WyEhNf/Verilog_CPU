"""Run the course opt/diagnose area flow on a frozen CPU simulation candidate.

The course owns all reserved SRAM names, wrappers, macro libraries and area
accounting. This adapter only selects cpu_core parameters, supplies its header
path and renames the root to student_top. Frequency is a separate, still
required audit; an area report from this command is not a complete tier score.
"""
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
import time

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / '.deps/RISC-V-CPU-2026'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_course(name):
    spec = importlib.util.spec_from_file_location('course_' + name, FRAMEWORK / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the defining module through sys.modules.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def quote(path):
    return '"' + Path(path).as_posix().replace('"', '\\"') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--mode', choices=('opt', 'diagnose'), default='opt')
    parser.add_argument('--abc-script', choices=('standard', 'classic-area'), default='standard')
    parser.add_argument('--clock-period', type=float, default=10 / 3)
    parser.add_argument('--lib-dir', type=Path, default=ROOT / '.deps/course_asap7_r28/lib')
    args = parser.parse_args()
    if not 0 < args.clock_period < float('inf'):
        parser.error('finite positive clock period required')
    build = json.loads(args.build_manifest.read_text(encoding='utf-8-sig'))
    frozen = dict(build['source_sha256'])
    frozen = {name: value.lower() for name, value in frozen.items()}
    for name, expected in frozen.items():
        if digest(ROOT / name) != expected:
            raise SystemExit('Candidate source differs from build: ' + name)
    executable = Path(build['executable'])
    if digest(executable) != build['executable_sha256'].lower():
        raise SystemExit('Candidate executable differs from build')
    libs = sorted(args.lib_dir.resolve().glob('*.lib'))
    seq = [path for path in libs if '_SEQ_' in path.name]
    if len(libs) != 5 or len(seq) != 1:
        raise SystemExit('Five course RVT TT libraries required')
    sources = [ROOT / line.split('#', 1)[0].strip()
               for line in (ROOT / 'rtl/filelist.f').read_text().splitlines()
               if line.split('#', 1)[0].strip()]
    fakeram, report_module = load_course('fakeram'), load_course('synth_report')
    top_params = set(re.findall(r'parameter integer (\w+)\s*=', (ROOT / 'rtl/cpu_core.v').read_text()))
    parameters = {}
    for name, value in build['parameters'].items():
        rtl_name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', name).upper()
        if rtl_name in top_params:
            parameters[rtl_name] = int(value)
        elif name not in ('MemoryLatency', 'IMemoryOutstanding', 'DMemoryOutstanding'):
            raise SystemExit('Unrecognized frozen parameter: ' + name)
    flow_inputs = [Path(__file__), fakeram.RAM_SOURCE, FRAMEWORK / 'scripts/fakeram.py',
                   FRAMEWORK / 'scripts/synth_report.py', FRAMEWORK / 'scripts/synth.py', *libs]
    for path in flow_inputs:
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    settings = dict(mode=args.mode, abc_script=args.abc_script,
                    clock_period_ns=args.clock_period, parameters=parameters,
                    framework_revision=subprocess.check_output(
                        ['git', '-C', str(FRAMEWORK), 'rev-parse', 'HEAD'], text=True).strip())
    manifest = dict(source_sha256=frozen, settings=settings,
                    build_manifest=str(args.build_manifest.resolve()),
                    executable_sha256=build['executable_sha256'])
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / 'run_manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise SystemExit('Inputs changed; use a new output directory')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']

    def run(name, commands):
        script = '\n'.join(commands) + '\n'
        script_path = out / (name + '.ys')
        marker = out / (name + '.done.json')
        expected = digest_bytes(script)
        if marker.exists() and json.loads(marker.read_text())['script_sha256'] == expected:
            print('RESUME ' + name, flush=True)
            return
        script_path.write_text(script)
        start = time.monotonic()
        print('START ' + name, flush=True)
        with (out / (name + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([str(suite / 'bin/yosys.exe'), '-T', '-s', str(script_path)],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        marker.write_text(json.dumps(dict(script_sha256=expected,
                                          seconds=time.monotonic() - start)) + '\n')
        print('DONE ' + name, flush=True)

    run('elaborate', [
        *['read_verilog -sv -D SYNTHESIS -I rtl ' + quote(path) for path in sources],
        'read_verilog -sv -noblackbox -D SYNTHESIS ' + quote(fakeram.RAM_SOURCE),
        'chparam ' + ' '.join('-set ' + key + ' ' + str(value) for key, value in parameters.items()) + ' cpu_core',
        'hierarchy -check -top cpu_core',
        'rename cpu_core student_top', 'proc', 'memory_collect',
        'write_json ' + quote(out / 'elaborated.json'),
    ])
    prepared, wrappers, ram_libs, macros = fakeram.prepare_memories(
        json.loads((out / 'elaborated.json').read_text()), out / 'ram')
    all_libs = [*libs, *ram_libs]
    libargs = ' '.join('-liberty ' + quote(path) for path in libs)
    all_libargs = ' '.join('-liberty ' + quote(path) for path in all_libs)
    libreads = ['read_liberty -lib -ignore_miss_func ' + quote(path) for path in all_libs]
    abc = 'abc ' + libargs + f' -D {args.clock_period * 1000:.9g}'
    if args.abc_script == 'classic-area':
        abc = 'abc ' + libargs + ' -script "+strash;scorr;dc2;dretime;strash;map -a"'
    # Split the official script at the ABC boundary so a long map can resume
    # without changing or repeating elaboration/memory expansion.
    run('prepare', [
        'read_json ' + quote(prepared), 'read_verilog ' + quote(wrappers), *libreads,
        'hierarchy -check -top student_top',
        'synth -top student_top -noabc ' + ('-flatten' if args.mode == 'opt' else '-hieropt'),
        'check -assert', 'select -assert-none a:init t:$dlatch* t:$_DLATCH*',
        'dfflibmap -liberty ' + quote(seq[0]), 'write_rtlil ' + quote(out / 'prepared.il'),
    ])
    run('map', [
        'read_rtlil ' + quote(out / 'prepared.il'), abc, 'clean',
        'delete t:$scopeinfo', 'clean -purge',
        'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L',
        'check -assert -mapped',
        'tee -o ' + quote(out / 'stat.json') + ' stat -json ' + all_libargs,
        'write_json ' + quote(out / 'design.json'),
        'write_verilog -noattr -noexpr ' + quote(out / 'mapped.v'),
        'design -reset', *libreads, 'read_verilog ' + quote(out / 'mapped.v'),
        'hierarchy -check -top student_top', 'check -assert -mapped',
    ])
    design = json.loads((out / 'design.json').read_text())
    stats = json.loads((out / 'stat.json').read_text())
    area = report_module.area_report(design, stats, macros)
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
    for name, expected in frozen.items():
        if digest(ROOT / name) != expected:
            raise ValueError('input changed during synthesis: ' + name)
    result = dict(status='COMPLETE', area=area, independent_area_um2=float(independent),
                  leaf_instances=sum(leaves.values()), leaf_counts=dict(leaves),
                  unpriced_leaf_instances=0, unmapped_memory_cells=0,
                  external_ram_included=False, timing_analyzed=False,
                  netlist_sha256=digest(out / 'mapped.v'), run_manifest=str(manifest_path),
                  sram_model=fakeram.MODEL, settings=settings,
                  libraries=[dict(path=str(path), sha256=digest(path)) for path in all_libs])
    (out / 'area_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in area.items()
                      if key not in ('module_tree', 'sram_instances')}, indent=2), flush=True)


def digest_bytes(value):
    return hashlib.sha256(value.encode()).hexdigest()


if __name__ == '__main__':
    main()
