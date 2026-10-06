#!/usr/bin/env python3
"""Time selected original OJ inputs with the package wall/memory limits."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('binary',type=Path)
    ap.add_argument('outdir',type=Path)
    ap.add_argument('--cases',default='16,17,21')
    ap.add_argument('--wall-seconds',type=float,default=100)
    a=ap.parse_args()
    binary=a.binary.resolve();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'tools/course_windows_config.json').read_text())
    env=dict(os.environ)
    env['PATH']=';'.join([config['runtime_bin'],config['build_bin'],
        str(ROOT/'.deps/oss-cad-suite-install/oss-cad-suite/bin'),
        str(ROOT/'.deps/oss-cad-suite-install/oss-cad-suite/lib'),env['PATH']])
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);api=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    rows=[]
    archive=ROOT/'3201.zip'
    with zipfile.ZipFile(archive) as z:
        for case in map(int,a.cases.split(',')):
            input_name=next(n for n in z.namelist() if n.endswith('/'+str(case)+'.in'))
            answer_name=input_name[:-3]+'.ans'
            data=z.read(input_name);answer=z.read(answer_name).decode().strip()
            stdout=out/(str(case)+'.stdout');stderr=out/(str(case)+'.stderr');image=out/(str(case)+'.in')
            image.write_bytes(data)
            start=time.monotonic();peak=0;timed_out=False
            print(f'Running original OJ point {case}, wall cap {a.wall_seconds:g}s',flush=True)
            with image.open('rb') as inp,stdout.open('wb') as output,stderr.open('wb') as errors:
                process=subprocess.Popen([str(binary)],stdin=inp,stdout=output,stderr=errors,env=env,
                    cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
                handle=kernel.OpenProcess(0x0410,False,process.pid)
                while process.poll() is None:
                    counters=Counters();counters.cb=ctypes.sizeof(counters)
                    if handle and api.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):
                        peak=max(peak,counters.PeakWorkingSetSize)
                    if time.monotonic()-start>=a.wall_seconds:
                        timed_out=True;process.kill();process.wait();break
                    time.sleep(.05)
                if handle:kernel.CloseHandle(handle)
            elapsed=time.monotonic()-start
            text=stdout.read_text().strip();error=stderr.read_text()
            cycles=re.search(r'CPU2026 cycles=(\d+)',error)
            status='TIMEOUT' if timed_out else ('PASS' if process.returncode==0 and text==answer else 'FAIL')
            row={'testpoint':case,'status':status,'elapsed_seconds':elapsed,'peak_rss_bytes':peak,
                'runtime_memory_limit_bytes':335544320,'memory_within_limit':peak<=335544320,
                'exit_code':process.returncode,'answer':answer,'stdout':text,'stderr':error,
                'cycles':int(cycles[1]) if cycles else None,'input_sha256':hashlib.sha256(data).hexdigest()}
            rows.append(row);print(json.dumps(row),flush=True)
            (out/'runtime.json').write_text(json.dumps({'binary':str(binary),
                'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                'wall_limit_seconds':a.wall_seconds,'clock_and_memory_driver_unchanged':True,'results':rows},indent=2)+'\n')
    return 0 if all(r['status']=='PASS' and r['memory_within_limit'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
