"""Wait on a verified native build and run its prepared finite cases once."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def live(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        error=ctypes.get_last_error()
        if error in (0,87):return False
        raise OSError(error,'Cannot inspect original course driver')
    try:
        code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value==259
    finally:kernel.CloseHandle(handle)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--driver-pid',type=int,required=True)
    args=parser.parse_args()
    assert os.name=='nt'
    config=json.loads(args.config.read_text(encoding='utf-8'))
    build=Path(config['native_build_path'])/'build_identity.json'
    status=args.out/'wait_status.json'
    if status.exists():raise FileExistsError('Preserve original directed waiting record')
    def record(phase,**extra):
        status.write_text(json.dumps(dict(status=phase,driver_pid=args.driver_pid,
            config=str(args.config.resolve()),**extra),indent=2)+'\n',encoding='utf-8')
    record('WAITING_FOR_NATIVE_BUILD')
    while True:
        try:
            identity=json.loads(build.read_text(encoding='utf-8'))
        except (FileNotFoundError,json.JSONDecodeError):
            identity={}
        if identity.get('status')=='COMPLETE':break
        if not live(args.driver_pid):
            record('BUILD_NOT_COMPLETE_DRIVER_TERMINAL')
            raise SystemExit('Original course driver ended before completing native CPU')
        time.sleep(2)
    cases=json.loads((args.out/'cases.json').read_text(encoding='utf-8'))['cases']
    record('RUNNING_PREPARED_CASES',case_count=len(cases),case_names=[case['name'] for case in cases])
    command=[sys.executable,'-u',str(Path(__file__).with_name('frequency_directed_cases_native.py')),
             '--out',str(args.out.resolve()),'--config',str(args.config.resolve())]
    result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1])
    record('COMPLETE' if result.returncode==0 else 'FAILED',returncode=result.returncode)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
