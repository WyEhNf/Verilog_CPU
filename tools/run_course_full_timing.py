"""Time a complete course-mapped netlist, including every generated SRAM macro.

Uses the original course timing.tcl and its ns/fF constraints via the project's
WSL OpenSTA build. No memory boundaries, data paths or output ports are omitted.
The selected reset port receives the same inactive-reset constraint that the
course applies to its reset port. No buffering, netlist rewrite or area change
is performed by this audit.
"""
import argparse
import json
import math
from pathlib import Path, PureWindowsPath
import re
import shlex
import subprocess

from run_course_sram_area import ROOT, FRAMEWORK, digest, load_course


def linux_path(path):
    path = PureWindowsPath(Path(path).resolve())
    if not re.fullmatch('[A-Za-z]:', path.drive):
        raise ValueError('WSL requires an absolute drive-letter path: ' + str(path))
    return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--sta', type=Path, default=ROOT / '.deps/OpenSTA/build/sta')
    parser.add_argument('--clock-port', default='clk')
    parser.add_argument('--reset-port', default='reset')
    args = parser.parse_args()
    out = args.directory.resolve()
    area = json.loads((out / 'area_audit.json').read_text())
    manifest = json.loads((out / 'run_manifest.json').read_text())
    if area['status'] != 'COMPLETE' or area['unpriced_leaf_instances'] or area['unmapped_memory_cells']:
        raise SystemExit('Complete, fully priced area netlist required')
    source_root = Path(manifest.get('source_snapshot_root', ROOT))
    inputs = {source_root / name: expected for name, expected in manifest['source_sha256'].items()}
    inputs[out / 'mapped.v'] = area['netlist_sha256']
    inputs.update({Path(entry['path']): entry['sha256'] for entry in area['libraries']})
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise SystemExit('Frozen area input changed: ' + str(path))
    course_timing = load_course('timing')
    timing_tcl = (source_root / '.deps/RISC-V-CPU-2026/scripts/timing.tcl'
                  if manifest.get('source_snapshot_root') else FRAMEWORK / 'scripts/timing.tcl')
    inputs[timing_tcl] = digest(timing_tcl)
    inputs[Path(__file__)] = digest(Path(__file__))
    inputs[args.sta.resolve()] = digest(args.sta.resolve())
    period = area['settings']['clock_period_ns']
    word = course_timing.tcl_word
    commands = [
        'set report_dir ' + word(linux_path(out)),
        'set clock_port ' + word(args.clock_port), f'set clock_period {period:.12g}',
        *['read_liberty ' + word(linux_path(entry['path'])) for entry in area['libraries']],
        'set_cmd_units -time ns -capacitance fF',
        'read_verilog ' + word(linux_path(out / 'mapped.v')),
        'link_design student_top',
        'set reset_port [get_ports -quiet ' + word(args.reset_port) + ']',
        'if {[llength $reset_port] != 1} {error "Expected one selected reset input"}',
        'set_case_analysis 0 $reset_port',
        'source ' + word(linux_path(timing_tcl)),
    ]
    script = out / 'full_timing.tcl'
    script.write_text('if {[catch {\n' + '\n'.join(commands) +
                      '\n} message]} {\n puts stderr "Timing analysis failed: $message"\n exit 1\n}\nexit 0\n')
    sta = linux_path(args.sta)
    command = 'cd ' + shlex.quote(linux_path(out)) + ' && exec ' + shlex.quote(sta) + \
              ' -no_init -exit full_timing.tcl'
    with (out / 'full_timing.log').open('w', encoding='utf-8') as log:
        completed = subprocess.run(['wsl.exe', '--exec', 'sh', '-c', command],
                                   stdout=log, stderr=subprocess.STDOUT)
    text = (out / 'full_timing.log').read_text()
    if completed.returncode or re.search(r'(?m)^Error(?: \d+)?:', text):
        raise SystemExit('OpenSTA failed; inspect ' + str(out / 'full_timing.log'))
    values = json.loads((out / 'timing_values.json').read_text())
    frequency = values.get('estimated_fmax_mhz')
    if frequency is None or not math.isfinite(frequency) or frequency <= 0:
        raise SystemExit('No proven positive frequency')
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise SystemExit('Input changed during timing: ' + str(path))
    version = subprocess.check_output(['wsl.exe', '--exec', sta, '-version'], text=True).strip()
    result = dict(status='COMPLETE', timing_analyzed=True, **values,
                  clock_period_ns=period, clock_port=args.clock_port, reset_port=args.reset_port, reset_value=0,
                  input_delay_ns=0.2, output_delay_ns=0.2, clock_uncertainty_ns=0.05,
                  output_load_ff=5.0, clock_model='ideal', interconnect='no_parasitics',
                  includes_sram=True, omitted_memory_boundaries=0,
                  is_test_fixture=bool(area.get('is_test_fixture', False)),
                  not_a_cpu_result=bool(area.get('not_a_cpu_result', False)),
                  area_um2=area['area']['area_um2'], netlist_sha256=area['netlist_sha256'],
                  opensta_version=version,
                  source_sha256={str(path): expected for path, expected in inputs.items()},
                  critical_paths=json.loads((out / 'critical_paths.json').read_text()),
                  area_report=str(out / 'area_audit.json'))
    (out / 'full_timing_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(values, indent=2))


if __name__ == '__main__':
    main()
