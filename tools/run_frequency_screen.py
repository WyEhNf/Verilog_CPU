"""Whole-CPU synthesis/STA screening before any expensive native validation.

Use unchanged course SRAM lowering, libraries, ABC and timing constraints.
Results are explicitly unvalidated candidates, never verified CPU results.
"""
from pathlib import Path
from collections import Counter
from decimal import Decimal
import argparse, json, os, subprocess, time, shutil
from run_course_sram_area import load_course, quote, digest, ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',type=Path);ap.add_argument('out',type=Path)
    a=ap.parse_args();stage=a.stage.resolve();out=a.out.resolve()
    assert not out.exists(),'Preserve earlier measurements'
    out.mkdir(parents=True)
    candidate=json.loads((stage/'candidate.json').read_text())
    files=candidate['source_sha256'];params=candidate['parameters']
    ram=stage/'.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv'
    original=Path('F:/CPU2026Candidates/frequency_combined_v2_20261003')
    course_timing=stage/'.deps/RISC-V-CPU-2026/scripts/timing.tcl'
    shutil.copyfile(original/'.deps/RISC-V-CPU-2026/scripts/timing.tcl',course_timing)
    files=files | {course_timing.relative_to(stage).as_posix():digest(course_timing)}
    def check():
        for name,h in files.items():assert digest(stage/name)==h.lower(),name
    check()
    libs=sorted(Path('F:/CPU2026Integration/frequency_combined_v2_20261003/area/source_snapshot/.deps/course_asap7_r28/lib').glob('*.lib'))
    assert len(libs)==5
    seq=next(p for p in libs if '_SEQ_' in p.name)
    tool=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env=dict(os.environ);env['PATH']=str(tool/'bin')+os.pathsep+str(tool/'lib')+os.pathsep+env['PATH']
    env['TEMP']=env['TMP']='F:/CPU2026Temp'
    def run(name,commands):
        script=out/(name+'.ys');script.write_text('\n'.join(commands)+'\n')
        print('START '+name,flush=True);t=time.monotonic()
        with (out/(name+'.log')).open('w',encoding='utf-8') as f:
            subprocess.run([str(tool/'bin/yosys.exe'),'-T','-s',str(script)],cwd=stage,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
        check();print(f'DONE {name} {time.monotonic()-t:.1f}s',flush=True)
    sources=[(stage/'verilog'/line.strip()).resolve() for line in (stage/'verilog/filelist.f').read_text().splitlines() if line.strip() and not line.strip().startswith('#')]
    run('elaborate',[
        *['read_verilog -sv -D SYNTHESIS -I rtl '+quote(p) for p in sources if p!=ram],
        'read_verilog -sv -noblackbox -D SYNTHESIS '+quote(ram),
        'chparam '+' '.join('-set '+k+' '+str(v) for k,v in sorted(params.items()))+' student_top',
        'hierarchy -check -top student_top','proc','memory_collect','write_json '+quote(out/'elaborated.json')])
    fakeram=load_course('fakeram');reporter=load_course('synth_report')
    prepared,wrappers,ramlibs,macros=fakeram.prepare_memories(json.loads((out/'elaborated.json').read_text()),out/'ram')
    del prepared
    all_libs=libs+ramlibs
    libreads=['read_liberty -lib -ignore_miss_func '+quote(p) for p in all_libs]
    libargs=' '.join('-liberty '+quote(p) for p in libs)
    allargs=' '.join('-liberty '+quote(p) for p in all_libs)
    run('prepare',['read_json '+quote(out/'ram/prepared.json'),'read_verilog '+quote(wrappers),*libreads,
        'hierarchy -check -top student_top','synth -top student_top -noabc -flatten','check -assert',
        'select -assert-none a:init t:$dlatch* t:$_DLATCH*','dfflibmap -liberty '+quote(seq),'write_rtlil '+quote(out/'prepared.il')])
    run('map',['read_rtlil '+quote(out/'prepared.il'),'abc '+libargs+' -D 2000','clean','delete t:$scopeinfo','clean -purge',
        'hilomap -hicell TIEHIx1_ASAP7_75t_R H -locell TIELOx1_ASAP7_75t_R L','check -assert -mapped',
        'tee -o '+quote(out/'stat.json')+' stat -json '+allargs,'write_json '+quote(out/'design.json'),
        'write_verilog -noattr -noexpr '+quote(out/'mapped.v')])
    model=json.loads((out/'design.json').read_text());stats=json.loads((out/'stat.json').read_text())
    area=reporter.area_report(model,stats,macros);leaves=Counter()
    def visit(kind,parents=()):
        assert kind not in parents
        for c in model['modules'][kind]['cells'].values():
            k=c['type'];attrs=model['modules'][k].get('attributes',{})
            if k in macros or k.endswith('_ASAP7_75t_R'):
                assert 'area' in attrs;leaves[k]+=1
            else:visit(k,parents+(kind,))
    visit('student_top')
    independent=sum(Decimal(str(model['modules'][k]['attributes']['area']))*n for k,n in leaves.items())
    assert abs(independent-Decimal(str(area['area_um2'])))<Decimal('0.00001')
    assert sum(leaves.values())==stats['design']['num_cells']
    assert sum(leaves[k] for k in macros)==37
    settings=dict(clock_period_ns=2,parameters=params,abc_script='standard',mode='opt',top='student_top',includes_axi_adapter=True)
    (out/'run_manifest.json').write_text(json.dumps(dict(source_snapshot_root=str(stage),source_sha256=files,settings=settings),indent=2)+'\n')
    result=dict(status='COMPLETE',candidate_unvalidated=True,area=area,independent_area_um2=str(independent),
        leaf_instances=sum(leaves.values()),leaf_counts=dict(leaves),unpriced_leaf_instances=0,unmapped_memory_cells=0,
        settings=settings,netlist_sha256=digest(out/'mapped.v'),libraries=[dict(path=str(p),sha256=digest(p)) for p in all_libs])
    (out/'area_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('AREA '+str(independent),flush=True)
    print('START full timing',flush=True)
    subprocess.run([str(Path(os.environ.get('CONDA_PREFIX','C:/Users/admin/miniconda3'))/'python.exe'),
        str(ROOT/'tools/run_course_full_timing.py'),str(out),'--clock-port','clock',
        '--sta',str(original/'.deps/OpenSTA/build/sta')],check=True)
    timing=json.loads((out/'timing_values.json').read_text());check()
    screening=dict(status='SYNTHESIS_TIMING_SCREEN_COMPLETE',functional_validation='DEFERRED',ipc='NOT_MEASURED',
        area_um2=str(independent),fmax_mhz=timing['estimated_fmax_mhz'],minimum_period_ns=timing['minimum_period_ns'],
        frequency_gain_percent=(timing['estimated_fmax_mhz']/candidate['base_frequency_mhz']-1)*100,
        source_root=str(stage),candidate_sha256=digest(stage/'candidate.json'),netlist_sha256=digest(out/'mapped.v'),
        sram_instances=37,course_mapping_and_timing_unchanged=True,no_simulation_tests_run=True)
    (out/'screening.json').write_text(json.dumps(screening,indent=2)+'\n')
    print(json.dumps(screening,indent=2),flush=True)

if __name__=='__main__':main()
