#!/usr/bin/env python3
"""Run an existing native simulator with its configured MinGW runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DLLS = ('libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('binary', type=Path)
    parser.add_argument('simulator_arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This launcher is for Windows native development only')
    binary = args.binary.resolve()
    if not binary.is_file():
        parser.error(f'Simulator not found: {binary}')
    config = json.loads((ROOT / 'tools/course_windows_config.json').read_text(encoding='utf-8'))
    runtime = Path(config['runtime_bin'])
    libraries = {}
    for name in RUNTIME_DLLS:
        path = runtime / name
        if not path.is_file():
            parser.error(f'Configured runtime is incomplete: {path}')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        # Windows searches the executable directory before PATH. Do not
        # silently accept a conflicting DLL next to the simulator.
        adjacent = binary.parent / name
        if adjacent.is_file() and hashlib.sha256(adjacent.read_bytes()).hexdigest() != digest:
            parser.error(f'Conflicting runtime DLL next to simulator: {adjacent}')
        libraries[name] = {'path': str(path), 'sha256': digest}
    environment = os.environ.copy()
    environment['PATH'] = os.pathsep.join([str(runtime), config['build_bin'],
                                          environment.get('PATH', '')])
    command = [str(binary), *args.simulator_arguments]
    if args.dry_run:
        print(json.dumps({'command': command, 'runtime_libraries': libraries,
                          'global_environment_changed': False}, indent=2))
        return 0
    return subprocess.call(command, cwd=ROOT, env=environment)


if __name__ == '__main__':
    sys.exit(main())
