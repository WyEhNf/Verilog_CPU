"""Compile the frozen CPU with native Verilator 5.020 while STA is being built."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'tools/course_windows_config.json')
    parser.add_argument('--resume-generated', action='store_true',
                        help='Resume the existing Windows make build with slash-safe host tool paths')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    source = Path(config['source'])
    out = Path(config['native_build_path'])
    assert os.name == 'nt' and (out.exists() if args.resume_generated else not out.exists())
    manifest = json.loads(Path(config['source_manifest']).read_text())
    for name, expected in manifest['snapshot_sha256'].items():
        assert sha(source/name) == expected, name
    env = dict(os.environ)
    env['PATH'] = config['runtime_bin']+';'+config['build_bin']+';'+env['PATH']
    env['VERILATOR_ROOT'] = str(Path(config['tools_root'])/'verilator/share/verilator')
    env['SHELL'] = str(Path(config['build_bin'])/'sh.exe')
    env['TEMP'] = env['TMP'] = 'F:/CPU2026Temp'
    version = subprocess.check_output([config['verilator'], '--version'], env=env, text=True).strip()
    assert 'Verilator 5.020' in version
    if not args.resume_generated:
        out.mkdir()
    command = [sys.executable, str(source/'.deps/RISC-V-CPU-2026/scripts/build.py'),
               '--filelist', 'verilog/filelist.f', '--out', str(out), '--appimage', '',
               '--verilator', config.get('verilator_build_driver', config['verilator']), '--jobs', '2',
               '--cxx', str(Path(config['runtime_bin'])/'g++.exe'),
               '--ar', str(Path(config['runtime_bin'])/'ar.exe'),
               '--make', str(Path(config['build_bin'])/'make.exe')]
    identity = dict(status='PREPARED', command=command, version=version,
                    source_manifest_sha256=sha(config['source_manifest']),
                    verilator_sha256=sha(config['verilator']),
                    verilator_build_driver_sha256=sha(config.get('verilator_build_driver', config['verilator'])),
                    verilator_build_extra_args=config.get('verilator_build_extra_args', []),
                    official_sim_cpp_unmodified=True, official_build_py_unmodified=True)
    record = out/'build_identity.json'
    if args.resume_generated:
        identity = json.loads(record.read_text())
        assert identity['status'] == 'PREPARED'
        assert identity['source_manifest_sha256'] == sha(config['source_manifest'])
        assert identity['verilator_sha256'] == sha(config['verilator'])
        assert identity['verilator_build_driver_sha256'] == sha(config['verilator_build_driver'])
        assert identity['verilator_build_extra_args'] == config['verilator_build_extra_args']
        shim_source = ROOT/'tools/verilator_windows_time_zero.cpp'
        shim_object = out/'windows_time_zero.o'
        shim_command = [str(Path(config['runtime_bin'])/'g++.exe'), '-O2', '-c',
                        str(shim_source), '-o', str(shim_object)]
        subprocess.run(shim_command, env=env, check=True)
        command = [str(Path(config['build_bin'])/'make.exe'), '-C', (out/'obj').as_posix(),
                   '-f', 'Vstudent_top.mk', '-j2',
                   'CXX='+ (Path(config['runtime_bin'])/'g++.exe').as_posix(),
                   'LINK='+ (Path(config['runtime_bin'])/'g++.exe').as_posix(),
                   'AR='+ (Path(config['runtime_bin'])/'ar.exe').as_posix(),
                   'PYTHON3='+ Path(sys.executable).as_posix(),
                   'VM_USER_LDLIBS='+shim_object.as_posix()]
        identity['windows_make_resume'] = command
        identity['windows_make_resume_reason'] = 'Slash-safe native AR paths and the Verilator 5.020 documented time-zero fallback for Windows weak symbols'
        identity['windows_time_zero_fallback'] = dict(command=shim_command,
            source=str(shim_source), source_sha256=sha(shim_source), object_sha256=sha(shim_object),
            course_sim_cpp_unchanged=True)
        log = out/'link_resume.log'
    else:
        log = out/'build.log'
        record.write_text(json.dumps(identity, indent=2)+'\n')
    print('START original course build, native Windows Verilator 5.020', flush=True)
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f'Native course build failed: {log}')
    binary = next(p for p in [out/'sim', out/'sim.exe'] if p.is_file())
    assert binary.read_bytes()[:2] == b'MZ'
    for name, expected in manifest['snapshot_sha256'].items():
        assert sha(source/name) == expected, name
    identity.update(status='COMPLETE', executable=str(binary), executable_sha256=sha(binary))
    record.write_text(json.dumps(identity, indent=2)+'\n')
    print('DONE original course native CPU build', flush=True)


if __name__ == '__main__':
    main()
