"""Wait on the existing Pi process, then execute the prepared read-only/backup workflow once."""
from datetime import datetime, timezone
from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write

PREPARATION=ROOT/'build/cpu2026/er1_a109_combined_adoption_preparation_20261006.json'
DISPATCH=ROOT/'build/cpu2026/er1_a109_combined_adoption_wait_dispatch_20261006.json'
RESULT=ROOT/'build/cpu2026/er1_a109_combined_adoption_wait_result_20261006.json'
PI=Path('F:/CPU2026CourseRuns/ER1_A109_pi_budget_20261006')


def open_existing_pi(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetProcessTimes.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x100000|0x1000,False,pid)
    if not handle:
        error=ctypes.get_last_error()
        if error==87:
            return kernel,None,None
        raise ctypes.WinError(error)
    length=wintypes.DWORD(32768)
    image=ctypes.create_unicode_buffer(length.value)
    assert kernel.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(length))
    assert image.value.lower()==sys.executable.lower()
    times=[wintypes.FILETIME() for _ in range(4)]
    assert kernel.GetProcessTimes(handle,*[ctypes.byref(value) for value in times])
    ticks=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
    created=ticks/10000000-11644473600
    dispatch=read(PI/'dispatch_identity.json')
    assert abs(created-datetime.fromisoformat(dispatch['started_at']).timestamp())<1
    return kernel,handle,ticks


def main():
    assert not DISPATCH.exists() and not RESULT.exists(), 'Never launch this workflow twice'
    assert sha(PREPARATION)=='685f2da82681905a6f5cb91fa5fd3d98f31190c4ec40a1af1690010e269d7db3'
    preparation=read(PREPARATION)
    for name,digest in preparation['evidence_sha256'].items():
        assert sha(name)==digest,name
    pid=preparation['pi_followup_process_id']
    kernel,handle,creation_ticks=open_existing_pi(pid)
    dispatch=dict(status='WAITING_EXISTING_PI_NO_NEW_HARDWARE_RUNS',started_at=datetime.now(timezone.utc).isoformat(),
        existing_pi_pid=pid,existing_pi_creation_filetime=creation_ticks,
        existing_pi_alive=handle is not None,preparation_sha256=sha(PREPARATION),
        watcher_sha256=sha(Path(__file__)),watcher_pid=os.getpid())
    write(DISPATCH,dispatch)
    print(dispatch,flush=True)
    if handle is not None:
        try:
            while True:
                wait=kernel.WaitForSingleObject(handle,50000)
                if wait==0:
                    break
                assert wait==258, 'Unexpected Windows process-handle wait failure'
        finally:
            kernel.CloseHandle(handle)
    terminal=read(PI/'followup_result.json')
    assert terminal['passed'] is True and terminal['returncode']==0, 'Pi must strictly match original112 before adoption'
    scripts=['record_er1_a109_combined_closing.py','adopt_er1_a109_combined_verified.py',
        'audit_er1_a109_combined_adopted_current_state.py','finalize_er1_a109_verified_goal_evidence.py']
    stages=[]
    for name in scripts:
        path=ROOT/'tools'/name
        assert sha(path)==preparation['evidence_sha256'][str(path)],name
        completed=subprocess.run([sys.executable,'-u',str(path)],cwd=ROOT)
        stages.append(dict(script=str(path),returncode=completed.returncode))
        assert completed.returncode==0,name
    output=dict(status='A109_PREPARED_COMBINED_WORKFLOW_COMPLETE_ROOT_GOAL_AUDIT_REQUIRED',
        completed_at=datetime.now(timezone.utc).isoformat(),stages=stages,
        final_completion_sha256=sha(ROOT/'build/cpu2026/er1_a109_final_completion_20261006.json'),
        new_cpu_builds=0,new_hardware_tests=0)
    write(RESULT,output)
    print(output,flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        if not RESULT.exists():
            write(RESULT,dict(status='COMBINED_WORKFLOW_STOPPED_WITHOUT_GOAL_COMPLETION',
                error=repr(error),stopped_at=datetime.now(timezone.utc).isoformat()))
        raise
