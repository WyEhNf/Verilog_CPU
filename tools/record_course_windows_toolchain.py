"""Bind the installed native Windows tools to the course's exact source commits."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT/'tools/course_windows_config.json').read_text())
    base = Path(config['tools_root'])
    env = dict(os.environ)
    env['PATH'] = config['runtime_bin'] + ';' + config['build_bin'] + ';' + env['PATH']
    def output(args):
        return subprocess.check_output(args, env=env, text=True).strip()
    expected = {
        'yosys': '70a11c6bf0e8dd669f56c7da3587f78b405138e2',
        'yosys/abc': '8e401543d3ecf65e3a3631c7a271793a4d356cb0',
        'opensta': 'f89887b59600cd3a2a10c3de31bda4235d904cdf',
        'cudd': 'f54f533303640afd5dbe47a05ebeabb3066f2a25',
        'verilator': '5c5314b39cd888f427807d626e1502cbf222c292',
    }
    source_dirs = {name: base/'src'/('opensta-sparse' if name == 'opensta' else name)
                   for name in expected}
    commits = {name: output(['git', '-C', str(source_dirs[name]), 'rev-parse', 'HEAD'])
               for name in expected}
    assert commits == expected
    modifications = {name: output(['git', '-C', str(source_dirs[name]), 'diff', '--stat'])
                     for name in expected}
    modified_files = {name: output(['git', '-C', str(source_dirs[name]), 'diff', '--name-only']).splitlines()
                      for name in expected}
    # The course Docker recipe also runs autoreconf. Its generated build files
    # depend on the host Autoconf/Automake version, while CUDD code stays pinned.
    generated = {'Makefile.in', 'aclocal.m4', 'config.h.in', 'configure',
                 'build-aux/compile', 'build-aux/config.guess', 'build-aux/config.sub',
                 'build-aux/depcomp', 'build-aux/install-sh', 'build-aux/missing',
                 'build-aux/test-driver', 'build-aux/ltmain.sh',
                 'build-aux/ar-lib',
                 'm4/libtool.m4', 'm4/ltoptions.m4', 'm4/ltsugar.m4',
                 'm4/ltversion.m4', 'm4/lt~obsolete.m4'}
    assert all(not files or (name == 'cudd' and set(files) <= generated) or
               (name == 'opensta' and set(files) <= {'doc/Messages.md', 'doc/OpenSTA.md'})
               for name, files in modified_files.items()), modified_files
    versions = {
        'yosys': output([config['yosys'], '-V']),
        'abc': output([config['abc'], '-c', 'version']),
        'opensta': output([config['sta'], '-version']),
        'verilator': output([config['verilator'], '--version']),
    }
    assert 'Yosys 0.63' in versions['yosys'] and 'Verilator 5.020' in versions['verilator']
    tools = {name: Path(config[name]) for name in ('yosys', 'abc', 'sta', 'verilator')}
    assert all(path.read_bytes()[:2] == b'MZ' for path in tools.values())
    def sha(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    libraries = {p.name: sha(p) for p in Path(config['asap7_lib']).glob('*.lib')}
    assert len(libraries) == 5
    audit = json.loads((ROOT/'build/cpu2026/course_requirements_audit_20261003.json').read_text())
    assert libraries == {r['file']: r['measured_lib_sha256'] for r in audit['asap7_libraries']}
    record = dict(status='COURSE_PINNED_TOOLS_INSTALLED', environment='WINDOWS_NATIVE',
                  wsl_used_for_this_build=False, commits=commits, versions=versions,
                  source_modifications=modifications, modified_files=modified_files,
                  algorithm_source_unchanged=True,
                  tool_sha256={name: sha(path) for name, path in tools.items()},
                  libraries_sha256=libraries, compiler=output(['g++.exe', '--version']),
                  windows_build_support_sha256={p.name: sha(p) for p in [
                      ROOT/'tools/build_pinned_course_tools_windows.sh',
                      ROOT/'tools/abc_link_windows.mk',
                      ROOT/'tools/fix_opensta_windows_generation.py',
                      ROOT/'tools/verilator_course_windows.cpp',
                      ROOT/'tools/verilator_windows_time_zero.cpp',
                      Path(config['verilator_build_driver']),
                      base/'build-headers/FlexLexer.h']},
                  verilator_build_extra_args=config.get('verilator_build_extra_args', []),
                  support_dependencies=output(['F:/c26/msys64/usr/bin/pacman.exe', '-Q']),
                  installation_mode='Native Windows MinGW; fixed course source commits, not Linux Docker binaries')
    (base/'toolchain_manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(dict(environment=record['environment'], versions=versions), indent=2))


if __name__ == '__main__':
    main()
