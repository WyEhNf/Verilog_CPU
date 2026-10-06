"""Run a Windows-native MSYS2 build command with the host's download proxy."""
import argparse
import os
from pathlib import Path
import subprocess
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('command')
    args = parser.parse_args()
    env = dict(os.environ)
    env['MSYSTEM'] = 'MINGW64'
    env['CHERE_INVOKING'] = '1'
    env['PATH'] = 'F:/c26/msys64/mingw64/bin;F:/c26/msys64/usr/bin;C:/Git/cmd;' + env['PATH']
    for scheme, url in urllib.request.getproxies().items():
        if scheme in ('http', 'https'):
            env[scheme + '_proxy'] = url
    env['SSL_CERT_FILE'] = 'F:/CPU2026CourseTools/54fc150/windows_trusted_roots.pem'
    env['CURL_CA_BUNDLE'] = env['SSL_CERT_FILE']
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(
            ['F:/c26/msys64/usr/bin/bash.exe', '-lc', args.command],
            env=env, stdout=stream, stderr=subprocess.STDOUT)
    print(f'Native Windows command completed: exit={result.returncode}; log={args.log}', flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
