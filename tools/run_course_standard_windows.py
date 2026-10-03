"""Measure one frozen CPU with the course-pinned native Windows toolchain."""
import concurrent.futures
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'tools/course_windows_config.json')
    parser.add_argument('--correctness', action='store_true', help='Run the official full correctness suite once after the CPU build')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Windows native measurement only')
    config = json.loads(args.config.read_text())
    source = Path(config['source'])
    out = Path(config['out'])
    manifest = json.loads(Path(config['source_manifest']).read_text())
    tools_root = Path(config['tools_root'])
    installed = json.loads((tools_root / 'toolchain_manifest.json').read_text())
    assert installed['environment'] == 'WINDOWS_NATIVE'
    assert 'Yosys 0.63' in installed['versions']['yosys']
    assert 'Verilator 5.020' in installed['versions']['verilator']
    tool_files = {name: Path(config[name]) for name in ('yosys', 'abc', 'sta', 'verilator')}
    for name, path in tool_files.items():
        assert path.read_bytes()[:2] == b'MZ', name
        assert sha(path) == installed['tool_sha256'][name], name
    def check_inputs():
        for name, expected in manifest['snapshot_sha256'].items():
            assert sha(source / name) == expected, name
    check_inputs()
    assert not out.exists(), 'Keep earlier measurement artifacts'
    out.mkdir(parents=True)
    env = dict(os.environ)
    # Original course Python children must flush their case names as they
    # run, so a failing case is identifiable without restarting simulation.
    env['PYTHONUNBUFFERED'] = '1'
    env['PATH'] = ';'.join([config['runtime_bin'], config['build_bin'],
                          str(tools_root/'yosys/bin'), str(tools_root/'opensta/bin'),
                          str(tools_root/'verilator/bin'), env['PATH']])
    env['VERILATOR_ROOT'] = str(tools_root/'verilator/share/verilator')
    env['SHELL'] = str(Path(config['build_bin'])/'sh.exe')
    env['TMP'] = env['TEMP'] = 'F:/CPU2026Temp'
    framework = source / '.deps/RISC-V-CPU-2026'
    scripts = framework / 'scripts'
    python = sys.executable
    commands = {
        'build': [python, str(scripts/'build.py'), '--filelist', 'verilog/filelist.f',
                  '--out', str(out/'build'), '--appimage', '',
                  '--verilator', config.get('verilator_build_driver', config['verilator']), '--jobs', '2',
                  '--cxx', str(Path(config['runtime_bin'])/'g++.exe'),
                  '--ar', str(Path(config['runtime_bin'])/'ar.exe'),
                  '--make', str(Path(config['build_bin'])/'make.exe')],
        'perf': [python, str(scripts/'testcase.py'), '--kind', 'perf',
                 '--testcases', str(framework/'testcases'),
                 '--sim', str(out/'build/sim'), '--latency', '10'],
        'synth': [python, str(scripts/'synth.py'), '--filelist', 'verilog/filelist.f',
                  '--out', str(out/'synth'), '--mode', 'opt', '--clock-period', '2.0',
                  '--appimage', '', '--yosys', config['yosys'], '--abc', config['abc'],
                  '--sta', config['sta'], '--asap7-lib', config['asap7_lib']],
    }
    commands['correctness'] = [python, str(scripts/'testcase.py'), '--kind', 'correctness',
                              '--testcases', str(framework/'testcases'),
                              '--sim', str(Path(config['native_build_path'])/'sim'), '--latency', '10']
    prebuilt_record = Path(config['native_build_path'])/'build_identity.json'
    prebuilt = None
    if prebuilt_record.exists():
        prebuilt = json.loads(prebuilt_record.read_text())
        assert prebuilt['status'] == 'COMPLETE', 'Wait for the native CPU build'
        assert prebuilt['source_manifest_sha256'] == sha(config['source_manifest'])
        assert prebuilt['verilator_sha256'] == sha(config['verilator'])
        assert prebuilt['verilator_build_driver_sha256'] == sha(config.get('verilator_build_driver', config['verilator']))
        assert prebuilt['verilator_build_extra_args'] == config.get('verilator_build_extra_args', [])
        assert sha(prebuilt['executable']) == prebuilt['executable_sha256']
        commands['build'] = prebuilt['command']
        commands['perf'][commands['perf'].index('--sim')+1] = prebuilt['executable']
        commands['correctness'][commands['correctness'].index('--sim')+1] = prebuilt['executable']
    identity = dict(status='PREPARED', environment='WINDOWS_NATIVE',
                    source_manifest_sha256=sha(config['source_manifest']),
                    toolchain_manifest_sha256=sha(tools_root/'toolchain_manifest.json'),
                    toolchain=installed, commands=commands,
                    source=str(source), parameter_overrides=manifest['parameter_overrides'],
                    latency=10, official_scripts_unmodified=True,
                    official_sim_cpp_unmodified=True, ipc_numerator='official metrics.json')
    identity['prebuilt_cpu'] = prebuilt
    host_build = [python, str(ROOT/'tools/prebuild_course_windows.py'), '--config', str(args.config.resolve())]
    identity['windows_host_build'] = host_build
    (out/'measurement_identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    def run(name):
        print('START course native ' + name, flush=True)
        began = time.monotonic()
        with (out/(name+'.log')).open('w', encoding='utf-8') as stream:
            result = subprocess.run(commands[name], cwd=source, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{name} failed: inspect {out/(name+".log")}')
        print(f'DONE course native {name} {time.monotonic()-began:.1f}s', flush=True)
    def performance():
        nonlocal prebuilt
        if prebuilt is None:
            with (out/'build_host.log').open('w', encoding='utf-8') as stream:
                result = subprocess.run(host_build, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            if result.returncode:
                # Resume only the documented Windows make/link portability
                # failure, never an RTL/compiler failure with no generated CPU.
                build_root = Path(config['native_build_path'])
                log = (build_root/'build.log').read_text(errors='replace') if (build_root/'build.log').is_file() else ''
                known_host_failure = any(token in log for token in ('ar: command not found', 'ar.exe', 'undefined reference to `sc_time_stamp', 'undefined reference to sc_time_stamp'))
                if not (build_root/'obj/Vstudent_top.mk').is_file() or not known_host_failure:
                    raise RuntimeError(f'CPU build failed: inspect {out/"build_host.log"} and {build_root/"build.log"}')
                with (out/'build_host_resume.log').open('w', encoding='utf-8') as stream:
                    resume = subprocess.run(host_build+['--resume-generated'], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
                if resume.returncode:
                    raise RuntimeError(f'Native CPU make resume failed: inspect {out/"build_host_resume.log"}')
            prebuilt = json.loads(prebuilt_record.read_text())
            assert prebuilt['status'] == 'COMPLETE'
            assert prebuilt['source_manifest_sha256'] == sha(config['source_manifest'])
            assert sha(prebuilt['executable']) == prebuilt['executable_sha256']
            commands['perf'][commands['perf'].index('--sim')+1] = prebuilt['executable']
            commands['correctness'][commands['correctness'].index('--sim')+1] = prebuilt['executable']
            identity['prebuilt_cpu'] = prebuilt
            (out/'measurement_identity.json').write_text(json.dumps(identity, indent=2)+'\n')
        else:
            print('REUSE frozen CPU compiled by native Verilator 5.020', flush=True)
        preipc_path = Path(config['native_ipc_path'])/'identity.json'
        if preipc_path.exists():
            preipc = json.loads(preipc_path.read_text())
            while preipc['status'] == 'PREPARED':
                time.sleep(3)
                preipc = json.loads(preipc_path.read_text())
            assert preipc['status'] == 'COMPLETE' and preipc['latency'] == 10
            assert preipc['source_manifest_sha256'] == sha(config['source_manifest'])
            assert preipc['verilator_sha256'] == sha(config['verilator'])
            assert prebuilt is not None and preipc['executable_sha256'] == prebuilt['executable_sha256']
            assert preipc['log_sha256'] == sha(preipc['log'])
            shutil.copyfile(preipc['log'], out/'perf.log')
            print('REUSE six completed official course IPC cases; no repeat run', flush=True)
        else:
            run('perf')
        text = (out/'perf.log').read_text()
        rows = []
        for line in text.splitlines():
            match = re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)', line)
            if not match:
                continue
            name, inst, cycles, _ = match.groups()
            case = framework/'testcases'/name
            instructions = json.loads((case/'metrics.json').read_text())['dynamic_instructions']
            assert int(inst) == instructions and int(cycles) > 0
            rows.append(dict(name=name, instructions=instructions, cycles=int(cycles),
                             ipc=instructions/int(cycles),
                             program_sha256=sha(case/'program.data'),
                             metrics_sha256=sha(case/'metrics.json')))
        expected = sorted(p.name for p in (framework/'testcases').glob('perf_*') if p.is_dir())
        assert sorted(row['name'] for row in rows) == expected
        assert len(rows) == 6
        ipc = math.exp(sum(math.log(row['ipc']) for row in rows)/len(rows))
        result = dict(status='COMPLETE', latency=10, results=rows, geomean_ipc=ipc,
                      official_scripts_unmodified=True, official_sim_cpp_unmodified=True)
        (out/'ipc.json').write_text(json.dumps(result, indent=2)+'\n')
        # Preserve completed performance even if subsequent correctness fails.
        if args.correctness:
            run('correctness')
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        perf_future = pool.submit(performance)
        synth_future = pool.submit(run, 'synth')
        failures = []
        results = {}
        for name, future in [('ipc', perf_future), ('synth', synth_future)]:
            try:
                results[name] = future.result()
            except Exception as error:
                failures.append(str(error))
        if failures:
            (out/'failure.json').write_text(json.dumps(dict(status='INCOMPLETE', errors=failures), indent=2))
            raise SystemExit('\n'.join(failures))
    check_inputs()
    official = json.loads((out/'synth/opt/report.json').read_text())
    fmax = official['timing']['estimated_fmax_mhz']
    assert fmax > 0 and math.isfinite(fmax)
    record = dict(status='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE',
                  environment='WINDOWS_NATIVE', source=str(source),
                  source_manifest=str(config['source_manifest']),
                  parameter_overrides=manifest['parameter_overrides'],
                  ipc=results['ipc']['geomean_ipc'], latency=10,
                  fmax_mhz=fmax,
                  minimum_period_ns=official['timing']['minimum_period_ns'],
                  area_um2=official['area']['area_um2'],
                  area=official['area'], tools=installed,
                  official_correctness_suite_not_run=not args.correctness,
                  official_correctness_suite_passed=bool(args.correctness),
                  official_perf_expected_results_passed=True,
                  tier3_numeric_requirements_met=(fmax >= 300 and
                      results['ipc']['geomean_ipc'] >= 1.0985 and official['area']['area_um2'] <= 36000))
    (out/'result.json').write_text(json.dumps(record, indent=2)+'\n')
    identity.update(status='COMPLETE', result_sha256=sha(out/'result.json'),
                    official_report_sha256=sha(out/'synth/opt/report.json'),
                    ipc_sha256=sha(out/'ipc.json'))
    (out/'measurement_identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ['status','ipc','fmax_mhz','minimum_period_ns','area_um2']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
