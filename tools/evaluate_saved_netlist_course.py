"""Assess an immutable mapped CPU with current course area, STA and gate simulation.

This preserves the historical mapping recipe. It is not a fresh default-flow
RTL synthesis or an official submission score. Functional standard-cell models
come from the actual Liberty functions; SRAM macros use the official RAM model.
"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from evaluate_current_course import sha, read, save, git, UPSTREAM, TESTCASES
from run_tier_candidate import HOST, BENCHMARKS

ROOT=Path(__file__).resolve().parents[1]
TARGET=Path('F:/CPU2026Experiments/A109_constr_potential_20261008/global_D1000_L056_RAMBUF4_F8')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def environment(out):
    env=dict(os.environ,PYTHONUNBUFFERED='1')
    env['PATH']=os.pathsep.join([HOST['runtime_bin'],HOST['build_bin'],str(Path(HOST['yosys']).parent),
                              str(Path(HOST['sta']).parent),env.get('PATH','')])
    env.update(VERILATOR_ROOT=HOST['verilator_root'],CPU2026_REAL_VERILATOR=HOST['verilator'],
        MAKE=str(Path(HOST['build_bin'])/'make.exe'),SHELL=str(Path(HOST['build_bin'])/'sh.exe'),
        CPU2026_BUILD_PYTHON=sys.executable,CPU2026_BUILD_DRIVER=str(out/'source/tools/verilator_low_memory.py'),
        CPU2026_WINDOWS_TIMESTAMP_SOURCE=str(out/'source/tools/verilator_windows_time_zero.cpp'),
        CPU2026_WORD_SIM='0',CPU2026_NATIVE_BITS='0',CPU2026_SPLIT_SCHEDULE='0',CPU2026_STABLE_MDU='0',
        CPU2026_ICO_PAIR='0',CPU2026_PGO='0',CPU2026_TRACE_DEPTH='1',CPU2026_COMPACT_IDS='0',
        CPU2026_UNROLL_STMTS='1000000',CPU2026_OPT_FAST='-O3')
    return env


def prepare(out,framework):
    assert not out.exists(),'Preserve earlier runs; choose a fresh output directory'
    assert git('rev-parse','HEAD',cwd=framework)==UPSTREAM
    assert git('rev-parse','HEAD',cwd=framework/'testcases')==TESTCASES
    identity=read(TARGET/'identity.json');old=read(TARGET/'result.json')
    parent=Path(identity['source'])
    assert identity['status']==old['status']=='COMPLETE'
    assert sha(TARGET/'report.json')==old['report_sha256']
    assert sha(TARGET/'result.json')==identity['result_sha256']
    assert sha(parent/'design.json')==identity['source_design_sha256']
    assert sha(parent/'result.json')==identity['source_result_sha256']
    for path,expected in identity['frozen_inputs'].items():assert sha(path)==expected,path
    source=out/'source';source.mkdir(parents=True)
    shutil.copytree(framework/'scripts',source/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(TARGET/'ram',out/'ram')
    for name in ('mapped.v','design.json','stat.json') :shutil.copyfile(TARGET/name,out/name)
    for name in ('identity.json','result.json','report.json','synth.ys'):
        dest=out/'historical';dest.mkdir(exist_ok=True);shutil.copyfile(TARGET/name,dest/name)
    (source/'tools').mkdir()
    for name in ('verilator_low_memory.py','cpu2026_build_log.py','cpu2026_pgo.py','verilator_python_driver_windows.cpp',
                 'verilator_windows_time_zero.cpp'):
        shutil.copyfile(ROOT/'tools'/name,source/'tools'/name)
    for name in [*BENCHMARKS,'correctness_array_test1']:
        shutil.copytree(framework/'testcases'/name,source/'testcases'/name)
    installed=read('F:/CPU2026CourseTools/win54fc150/toolchain_manifest.json')
    for name in ('yosys','abc','sta'):assert sha(HOST[name])==installed['tool_sha256'][name]
    libs=sorted(Path(HOST['asap7_lib']).glob('*.lib'))
    assert len(libs)==5
    for lib in libs:assert sha(lib)==installed['libraries_sha256'][lib.name]
    (out/'cells.ys').write_text('\n'.join(['read_liberty -ignore_miss_func "'+p.as_posix()+'"' for p in libs]+
        ['write_verilog -noattr "'+(source/'cells.v').as_posix()+'"'])+'\n',encoding='utf-8')
    with (out/'cells.log').open('w') as stream:
        subprocess.run([HOST['yosys'],'-Q','-T','-s',str(out/'cells.ys')],env=environment(out),
                       stdout=stream,stderr=subprocess.STDOUT,check=True)
    # Use original course memory semantics rather than hand-written storage.
    models=[]
    for name,shape in read(out/'ram/manifest.json')['macros'].items():
        d=shape['depth'];w=shape['width'];a=max(1,(d-1).bit_length())
        models.append(f'''module {name}(input clk,ce_in,we_in,input [{a-1}:0] addr_in,
    input [{w-1}:0] wd_in,output [{w-1}:0] rd_out);
    sram_fakeram #(.DEPTH({d}),.WIDTH({w}),.WRITE_GRANULARITY({w})) storage(
        .clk(clk),.en(ce_in),.we(we_in),.wmask(1'b1),.addr(addr_in),.wdata(wd_in),.rdata(rd_out));
endmodule
''')
    (source/'macros.v').write_text('\n'.join(models),encoding='utf-8')
    (source/'filelist.f').write_text('../mapped.v\ncells.v\nmacros.v\n',encoding='utf-8')
    adapter=out/'native_verilator_driver.exe'
    with (out/'adapter.log').open('w') as stream:
        subprocess.run([str(Path(HOST['runtime_bin'])/'g++.exe'),'-std=c++17','-O2','-static-libgcc',
            '-static-libstdc++',str(source/'tools/verilator_python_driver_windows.cpp'),'-o',str(adapter)],
            env=environment(out),stdout=stream,stderr=subprocess.STDOUT,check=True)
    frozen=[p for folder in (source,out/'ram',out/'historical') for p in folder.rglob('*') if p.is_file()]
    frozen += [out/n for n in ('mapped.v','design.json','stat.json','cells.ys','cells.log','native_verilator_driver.exe')]
    manifest=dict(name=TARGET.name,artifact_directory=str(TARGET),framework_commit=UPSTREAM,
        testcases_commit=TESTCASES,source_cpu='A109; original experiment frozen source manifest '+identity['source_manifest_sha256'],
        mapping_recipe=read(parent/'identity.json'),buffer_identity={k:v for k,v in identity.items() if k not in ('trees','frozen_inputs')},
        source_sha256={p.relative_to(out).as_posix():sha(p) for p in frozen},
        libraries=[dict(path=str(p),sha256=sha(p)) for p in [*libs,*sorted((out/'ram').glob('*.lib'))]],
        tools={k:dict(path=HOST[k],sha256=sha(HOST[k])) for k in ('yosys','abc','sta','verilator')},
        simulation='Zero-delay mapped-netlist functional simulation; original official driver/testcases and RAM; no WORD_SIM',
        official_default_synthesis=False,official_submission_score=False)
    save(out/'manifest.json',manifest)
    print('PREPARED '+str(out),flush=True)


def verify(out):
    m=read(out/'manifest.json')
    for name,expected in m['source_sha256'].items():assert sha(out/name)==expected,name
    if (out/'supplemental_inputs.json').exists():
        for name,expected in read(out/'supplemental_inputs.json')['sha256'].items():assert sha(out/name)==expected,name
    for entry in [*m['libraries'],*m['tools'].values()]:assert sha(entry['path'])==entry['sha256'],entry['path']
    return m


def phase(out,name):
    m=verify(out);statefile=out/(name+'.json');assert not statefile.exists(),'Do not rerun completed/live phases'
    state=dict(status='RUNNING',phase=name,manifest_sha256=sha(out/'manifest.json'))
    save(statefile,state);start=time.monotonic();print('START '+name,flush=True)
    if name=='ppa':
        area=module('course_area',out/'source/scripts/synth_report.py').area_report(
            read(out/'design.json'),read(out/'stat.json'),read(out/'ram/manifest.json')['macros'])
        os.environ['PATH']=environment(out)['PATH']
        timing=module('course_timing',out/'source/scripts/timing.py').analyze(
            HOST['sta'],out,[Path(x['path']) for x in m['libraries']],2.0,'clock')
        save(out/'ppa_report.json',dict(area=area,timing=timing))
        state.update(area_um2=area['area_um2'],fmax_mhz=timing['estimated_fmax_mhz'],
                     report_sha256=sha(out/'ppa_report.json'),returncode=0)
    else:
        source=out/'source'
        if name=='build':
            command=[sys.executable,str(source/'scripts/build.py'),'--filelist',str(source/'filelist.f'),
                '--out',str(out/'build'),'--jobs','1','--appimage','','--verilator',str(out/'native_verilator_driver.exe'),
                '--cxx',str(Path(HOST['runtime_bin'])/'g++.exe'),'--ar',str(Path(HOST['runtime_bin'])/'ar.exe'),
                '--make',str(Path(HOST['build_bin'])/'make.exe')]
        else:
            b=read(out/'build.json');assert b['status']=='PASSED'
            assert sha(out/'build/sim.exe')==b['executable_sha256']
            command=[sys.executable,str(source/'scripts/testcase.py'),'--testcases',str(source/'testcases'),
                '--sim',str(out/'build/sim.exe'),'--latency','10','--max-cycles','1000000']
            command+=['--kind','perf'] if name=='perf' else ['--kind','correctness','--case','correctness_array_test1']
        state['command']=command
        with (out/(name+'.log')).open('w',encoding='utf-8') as stream:
            r=subprocess.run(command,cwd=source,env=environment(out),stdout=stream,stderr=subprocess.STDOUT)
        state.update(returncode=r.returncode,log_sha256=sha(out/(name+'.log')))
        if not r.returncode:
            if name=='build':state['executable_sha256']=sha(out/'build/sim.exe')
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
    verify(out)
    state.update(status='PASSED' if state['returncode']==0 else 'FAILED',seconds=time.monotonic()-start)
    save(statefile,state);print(json.dumps(state),flush=True)
    return state['returncode']


def report(out):
    m=verify(out)
    states={n:read(out/(n+'.json')) if (out/(n+'.json')).exists() else None for n in ('ppa','build','perf','smoke')}
    result=dict(name=m['name'],framework_commit=UPSTREAM,run_directory=str(out),states=states,
        manifest_sha256=sha(out/'manifest.json'),official_default_synthesis=False,official_submission_score=False,
        simulation=m['simulation'],source_tool_library_hashes_verified=True)
    if (out/'supplemental_inputs.json').exists():
        result['supplemental_inputs']=read(out/'supplemental_inputs.json')
        result['supplemental_inputs_sha256']=sha(out/'supplemental_inputs.json')
    if all(v and v['status']=='PASSED' for v in states.values()):
        area=states['ppa']['area_um2'];freq=states['ppa']['fmax_mhz'];ipc=states['perf']['geomean_ipc']
        result.update(status='COMPLETED',area_um2=area,fmax_mhz=freq,geomean_ipc=ipc,
            tier3_thresholds_passed=area<=36000 and freq>=300 and ipc>=1.0985,
            target500_passed=area<=36000 and freq>=500 and ipc>=1.0985)
    else:result['status']='INCOMPLETE_OR_FAILED'
    save(out/'assessment.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='states'},indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','check','ppa','build','perf','smoke','report'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--framework',type=Path,default=ROOT/'.deps/RISC-V-CPU-2026')
    a=p.parse_args();out=a.out.resolve()
    if a.action=='prepare':prepare(out,a.framework.resolve())
    elif a.action=='check':verify(out);print('VERIFIED')
    elif a.action=='report':report(out)
    else:raise SystemExit(phase(out,a.action))


if __name__=='__main__':main()
