"""Freeze unchanged default CPU RTL and evaluate with a pinned current course.

An assessment measures all requested metrics even when a tier gate fails.
Official synthesis/build/testcase/harness/RAM sources are not patched. A native
Windows launcher adapts the official builder to bounded local compilation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
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

ROOT=Path(__file__).resolve().parents[1]
from run_tier_candidate import HOST, BENCHMARKS
UPSTREAM='302f0cf3cccdaa5de084a2120e0d950c663e4cf5'
TESTCASES='29f980727f7d99a1842a58f34091c7579ba3fe85'
CPU_COMMIT='8e2448d9ede31c124f2e9d86b5dec96436d3478f'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()

def prepare(out,framework):
    assert not out.exists(),'Choose a fresh directory; preserve every prior assessment'
    assert git('rev-parse','HEAD',cwd=framework)==UPSTREAM
    assert git('rev-parse','HEAD',cwd=ROOT/'testcases')==TESTCASES
    assert git('rev-parse','HEAD',cwd=framework/'testcases')==TESTCASES
    assert not git('diff',CPU_COMMIT,'--','rtl','verilog','rv32im_defs.vh'),'CPU RTL must remain unchanged'
    assert not git('status','--porcelain',cwd=ROOT/'testcases')
    official=[p.relative_to(framework) for p in (framework/'scripts').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]+[Path('Makefile')]
    for path in official:assert sha(ROOT/path)==sha(framework/path),str(path)
    source=out/'source';source.mkdir(parents=True)
    names=git('ls-files','-z').split('\0')
    chosen=[name for name in names if name and (ROOT/name).is_file() and
            (name.startswith(('rtl/','verilog/','scripts/','tools/')) or
             name in ('rv32im_defs.vh','config.mk','Makefile','configs/tier3.json'))]
    for name in chosen:
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    for name in [*BENCHMARKS,'correctness_array_test1']:
        case=framework/'testcases'/name
        for original in case.rglob('*'):
            if original.is_file():
                target=source/'testcases'/name/original.relative_to(case)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
    host=dict(HOST)
    adapter=out/'native_verilator_driver.exe'
    compiler=Path(host['runtime_bin'])/'g++.exe'
    env=dict(os.environ);env['PATH']=host['runtime_bin']+os.pathsep+host['build_bin']+os.pathsep+env['PATH']
    command=[str(compiler),'-std=c++17','-O2','-static-libgcc','-static-libstdc++',
             str(source/'tools/verilator_python_driver_windows.cpp'),'-o',str(adapter)]
    with (out/'adapter_build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    installed=read('F:/CPU2026CourseTools/win54fc150/toolchain_manifest.json')
    for name in ('yosys','abc','sta'):assert sha(host[name])==installed['tool_sha256'][name]
    for name,value in installed['libraries_sha256'].items():assert sha(Path(host['asap7_lib'])/name)==value
    parameters={k:int(v) for k,v in re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=\s*([0-9]+)',
                (source/'rtl/course/student_top.v').read_text(encoding='utf-8'))}
    manifest=dict(status='PREPARED',source_commit=git('rev-parse','HEAD'),cpu_rtl_reference_commit=CPU_COMMIT,
        cpu_rtl_unchanged=True,parameter_profile='Current HEAD student_top defaults; configs/tier3.json parameters={}',
        parameters=parameters,parameter_overrides={},framework_url='https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026.git',
        framework_commit=UPSTREAM,testcases_commit=TESTCASES,host=host,environment='WINDOWS_NATIVE',
        source_sha256={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()},
        official_sha256={p.as_posix():sha(source/p) for p in official},
        tool_sha256={k:sha(host[k]) for k in ('yosys','abc','sta','verilator')},
        library_sha256=installed['libraries_sha256'],pinned_tool_manifest=installed,
        native_launcher=str(adapter),native_launcher_sha256=sha(adapter),compiler_command=command,
        compiler_sha256=sha(compiler),compiler_log_sha256=sha(out/'adapter_build.log'),
        abc_constraints=dict(driving_cell='INVx1_ASAP7_75t_R',output_load_ff=5.0),clock_period_ns=2.0,latency=10,
        simulation_options=dict(word_sim=1,native_bits=1,split_schedule=1,stable_mdu=0,ico_pair=0,pgo=0),
        assessment_is_not_optimization_acceptance=True,all_metrics_measured_regardless_of_tier_gates=True)
    save(out/'manifest.json',manifest)
    print('PREPARED '+str(out),flush=True)

def verify(out,m):
    for name,value in m['source_sha256'].items():assert sha(out/'source'/name)==value,name
    for name,value in m['tool_sha256'].items():assert sha(m['host'][name])==value,name
    for name,value in m['library_sha256'].items():assert sha(Path(m['host']['asap7_lib'])/name)==value,name
    assert sha(m['native_launcher'])==m['native_launcher_sha256']

def phase(out,name):
    m=read(out/'manifest.json');verify(out,m);source=out/'source';h=m['host']
    assert not (out/(name+'.json')).exists(),'Preserve previous phase, do not restart'
    env=dict(os.environ,PYTHONUNBUFFERED='1')
    env['PATH']=os.pathsep.join([h['runtime_bin'],h['build_bin'],env.get('PATH','')])
    env.update(VERILATOR_ROOT=h['verilator_root'],CPU2026_REAL_VERILATOR=h['verilator'],
        MAKE=str(Path(h['build_bin'])/'make.exe'),SHELL=str(Path(h['build_bin'])/'sh.exe'),
        CPU2026_BUILD_PYTHON=sys.executable,CPU2026_BUILD_DRIVER=str(source/'tools/verilator_low_memory.py'),
        CPU2026_WINDOWS_TIMESTAMP_SOURCE=str(source/'tools/verilator_windows_time_zero.cpp'),
        CPU2026_PGO='0',CPU2026_WORD_SIM='1',CPU2026_STABLE_MDU='0',CPU2026_ICO_PAIR='0',
        CPU2026_NATIVE_BITS='1',CPU2026_SPLIT_SCHEDULE='1',CPU2026_TRACE_DEPTH='1',
        CPU2026_COMPACT_IDS='0',CPU2026_UNROLL_STMTS='1000000',CPU2026_OPT_FAST='-O3')
    if name=='synth':
        command=[sys.executable,str(source/'scripts/synth.py'),'--filelist','verilog/filelist.f',
            '--out',str(out/'synth'),'--mode','opt','--clock-period','2.0',
            '--abc-driving-cell','INVx1_ASAP7_75t_R','--abc-load-ff','5.0','--appimage','',
            '--yosys',h['yosys'],'--abc',h['abc'],'--sta',h['sta'],'--asap7-lib',h['asap7_lib']]
    elif name=='build':
        command=[sys.executable,str(source/'scripts/build.py'),'--filelist','verilog/filelist.f',
            '--out',str(out/'build'),'--jobs','1','--appimage','','--verilator',m['native_launcher'],
            '--cxx',str(Path(h['runtime_bin'])/'g++.exe'),'--ar',str(Path(h['runtime_bin'])/'ar.exe'),
            '--make',str(Path(h['build_bin'])/'make.exe')]
    elif name in ('perf','smoke'):
        b=read(out/'build.json');assert b['status']=='PASSED'
        assert sha(out/'build/sim.exe')==b['executable_sha256']
        command=[sys.executable,str(source/'scripts/testcase.py'),'--testcases',str(source/'testcases'),
            '--sim',str(out/'build/sim.exe'),'--latency','10','--max-cycles','1000000']
        command+=['--kind','perf'] if name=='perf' else ['--kind','correctness','--case','correctness_array_test1']
    else:raise ValueError(name)
    state=dict(status='RUNNING',phase=name,command=command,manifest_sha256=sha(out/'manifest.json'))
    save(out/(name+'.json'),state);print('START '+name,flush=True);start=time.monotonic()
    with (out/(name+'.log')).open('w',encoding='utf-8') as stream:
        result=subprocess.run(command,cwd=source,env=env,stdout=stream,stderr=subprocess.STDOUT)
    state.update(status='PASSED' if result.returncode==0 else 'FAILED',returncode=result.returncode,
        seconds=time.monotonic()-start,log_sha256=sha(out/(name+'.log')))
    verify(out,m)
    if result.returncode==0:
        if name=='synth':
            r=read(out/'synth/opt/report.json');assert r['abc_constraints']==m['abc_constraints']
            state.update(area={k:v for k,v in r['area'].items() if isinstance(v,(float,int))},
                timing={k:v for k,v in r['timing'].items() if isinstance(v,(float,int,str,bool))},
                area_um2=r['area']['area_um2'],fmax_mhz=r['timing']['estimated_fmax_mhz'],
                report_sha256=sha(out/'synth/opt/report.json'),abc_constr_sha256=sha(out/'synth/opt/abc.constr'))
        elif name=='build':state['executable_sha256']=sha(out/'build/sim.exe')
        elif name=='perf':
            rows=[]
            for line in (out/'perf.log').read_text(encoding='utf-8').splitlines():
                match=re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)',line)
                if match:
                    case,inst,cycles,_=match.groups();inst=int(inst);cycles=int(cycles)
                    assert inst==read(source/'testcases'/case/'metrics.json')['dynamic_instructions']
                    rows.append(dict(name=case,instructions=inst,cycles=cycles,ipc=inst/cycles))
            assert sorted(r['name'] for r in rows)==BENCHMARKS
            state.update(results=rows,geomean_ipc=math.exp(sum(math.log(r['ipc']) for r in rows)/6))
    save(out/(name+'.json'),state)
    print(json.dumps(state,ensure_ascii=False),flush=True)
    return result.returncode

def report(out):
    m=read(out/'manifest.json');verify(out,m)
    states={n:read(out/(n+'.json')) if (out/(n+'.json')).exists() else None for n in ('synth','build','perf','smoke')}
    result=dict(framework_commit=m['framework_commit'],source_commit=m['source_commit'],
        cpu_rtl_reference_commit=m['cpu_rtl_reference_commit'],cpu_rtl_unchanged=True,run_directory=str(out),
        parameter_profile=m['parameter_profile'],manifest_sha256=sha(out/'manifest.json'),
        source_tool_library_hashes_verified=True,abc_constraints=m['abc_constraints'],states=states,
        scope='One opt synthesis with official defaults, six original perf programs at latency10, one array1 smoke; no CPU optimization')
    if all(states[n] and states[n]['status']=='PASSED' for n in states):
        area=states['synth']['area_um2'];freq=states['synth']['fmax_mhz'];ipc=states['perf']['geomean_ipc']
        result.update(status='COMPLETED',area_um2=area,fmax_mhz=freq,geomean_ipc=ipc,
            course_tier3_passed=area<=36000 and freq>=300 and ipc>=1.0985,
            target500_passed=area<=36000 and freq>=500 and ipc>=1.0985)
    else:result['status']='INCOMPLETE_OR_FAILED'
    save(out/'assessment.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='states'},ensure_ascii=False,indent=2),flush=True)

def run(out):
    assert not any((out/(n+'.json')).exists() for n in ('synth','build','perf','smoke'))
    # Independent outputs and one worker per tool keep compilation bounded.
    with ThreadPoolExecutor(max_workers=2) as pool:
        synth=pool.submit(phase,out,'synth');build=pool.submit(phase,out,'build')
        build_status=build.result()
        if build_status==0:
            perf_status=phase(out,'perf')
            if perf_status==0:phase(out,'smoke')
        synth.result()
    report(out)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','check','run','synth','build','perf','smoke','report'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--framework',type=Path,default=ROOT/'.deps/RISC-V-CPU-2026')
    a=p.parse_args();out=a.out.resolve()
    if a.action=='prepare':prepare(out,a.framework.resolve())
    elif a.action=='check':verify(out,read(out/'manifest.json'));print('VERIFIED '+str(out))
    elif a.action=='run':run(out)
    elif a.action=='report':report(out)
    else:raise SystemExit(phase(out,a.action))
if __name__=='__main__':main()
