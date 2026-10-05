"""Read host-side cycle observations from the exact already-built A36 model."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys

from manage_er1_a36_measurement import check as check36
from manage_frozen_baseline_programs import ROOT, read, sha, write
from wait_frequency_directed_native import live

RUN=Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')
OUT=Path('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005')
REPORT=ROOT/'reports/ER1_A36_three_case_profile_pretest_2026-10-05.md'
CASES=['perf_median','perf_qsort','perf_towers']
MODEL=RUN/'native_build/obj'
CORE='student_top__DOT__core__DOT__'
BACK=CORE+'g_ooo_backend__DOT__backend__DOT__'
SAMPLES=[
    ('samples','1'),
    ('frontend_empty',f'!r->{CORE}fetch_valid'),
    ('trace_present',f'!!r->{CORE}trace_valid'),
    ('trace_all_blocked',f'r->{CORE}trace_valid && !r->{BACK}trace_ready_r'),
    ('branch_pending',f'!!r->{BACK}branch_pending'),
    ('branch_pending_with_ready_rs',f'r->{BACK}branch_pending && r->{BACK}rs_issue_valid'),
    ('rs_any_ready',f'!!r->{BACK}rs_issue_valid'),
    ('rs_any_issue',f'!!(r->{BACK}rs_issue_valid & r->{BACK}rs_issue_ready)'),
    ('rs_issue_lanes',f'__builtin_popcount(unsigned(r->{BACK}rs_issue_valid & r->{BACK}rs_issue_ready))'),
    ('rob_full',f'r->{BACK}rob__DOT__occupancy_reg>=32'),
    ('rs_full',f'r->{BACK}rs__DOT__occupancy_reg>=8'),
    ('lsq_full',f'r->{BACK}lsq__DOT__occupancy_reg>=16'),
    ('rob_occupancy_sum',f'r->{BACK}rob__DOT__occupancy_reg'),
    ('rs_occupancy_sum',f'r->{BACK}rs__DOT__occupancy_reg'),
    ('lsq_occupancy_sum',f'r->{BACK}lsq__DOT__occupancy_reg'),
    ('primary_icache_hit_events',f'r->{CORE}ic_event_hit'),
    ('primary_icache_miss_events',f'r->{CORE}ic_event_miss'),
    ('dcache_hit_events',f'r->{CORE}dc_event_hit'),
    ('dcache_miss_events',f'r->{CORE}dc_event_miss'),
]


def env():
    value=dict(os.environ)
    value['PATH']='F:/c26/msys64/mingw64/bin;F:/c26/msys64/usr/bin;'+value.get('PATH','')
    return value


def check():
    check36()
    plan=read(OUT/'plan.json')
    for p,h in plan['frozen_inputs_sha256'].items():assert sha(p)==h,p
    assert not live(read(RUN/'dispatch_identity.json')['process_id'])
    assert read(RUN/'result/result.json')['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert sha(OUT/'profile_driver.cpp')==plan['profile_driver_sha256']
    return plan


def prepare():
    assert not OUT.exists() and not REPORT.exists()
    check36()
    assert not live(read(RUN/'dispatch_identity.json')['process_id'])
    result=read(RUN/'result/result.json')
    assert result['ipc']==0.9918977910385353 and result['area_um2']<36000
    official=RUN/'source/.deps/RISC-V-CPU-2026/scripts/sim.cpp'
    original=official.read_text(encoding='utf-8')
    prefix='#include "Vstudent_top___024root.h"\n'
    source=prefix+original
    declarations='''        uint64_t profile_values[19]={};
        uint64_t profile_branch_events=0;
        bool profile_previous_pending=false;
'''
    assert source.count('        Vstudent_top top{&context};\n')==1
    source=source.replace('        Vstudent_top top{&context};\n','        Vstudent_top top{&context};\n'+declarations)
    sample='''            if (!top.reset && !top.rootp->student_top__DOT__core__DOT__halted) {
                auto* r=top.rootp;
'''
    for i,(name,expression) in enumerate(SAMPLES):sample+=f'                profile_values[{i}]+=uint64_t({expression});\n'
    sample+=f'''                bool pending=r->{BACK}branch_pending;
                if(pending && !profile_previous_pending) ++profile_branch_events;
                profile_previous_pending=pending;
            }}
'''
    assert source.count('            top.clock = 1;\n')==1
    source=source.replace('            top.clock = 1;\n',sample+'            top.clock = 1;\n')
    dump='        std::cerr << "PROFILE_JSON={";\n'
    for i,(name,_) in enumerate(SAMPLES):
        lead='' if i==0 else ','
        dump+=f'        std::cerr << "{lead}\\"{name}\\":" << profile_values[{i}];\n'
    dump+=f'''        std::cerr << ",\\"branch_pending_rising_events\\":" << profile_branch_events;
        std::cerr << ",\\"accepted_predictor_feedback\\":" << top.rootp->{CORE}pred_count;
        std::cerr << ",\\"correct_predictor_feedback\\":" << top.rootp->{CORE}pred_correct;
        std::cerr << ",\\"final_debug_instret\\":" << top.debug_instret;
        std::cerr << ",\\"final_debug_cycles\\":" << top.debug_core_cycles << "}}" << '\\n';
'''
    assert source.count('        top.final();\n')==1
    source=source.replace('        top.final();\n',dump+'        top.final();\n')
    assert source.replace(prefix,'',1).replace(declarations,'',1).replace(sample,'',1).replace(dump,'',1)==original
    header=(MODEL/'Vstudent_top___024root.h').read_text(encoding='utf-8')
    for _,expression in SAMPLES:
        for field in re.findall(r'r->(\w+)',expression):assert field in header,field
    OUT.mkdir(parents=True)
    (OUT/'profile_driver.cpp').write_text(source,encoding='utf-8')
    files=[official,MODEL/'Vstudent_top___024root.h',MODEL/'Vstudent_top.h',MODEL/'Vstudent_top__ALL.a',
        MODEL/'verilated.o',MODEL/'verilated_vcd_c.o',MODEL/'verilated_threads.o',RUN/'native_build/windows_time_zero.o',
        RUN/'native_build/sim.exe',RUN/'native_build/build_identity.json',RUN/'result/result.json',RUN/'result/ipc.json',
        Path(__file__),Path('F:/c26/msys64/mingw64/bin/g++.exe')]
    for name in CASES:
        p=RUN/'source/.deps/RISC-V-CPU-2026/testcases'/name
        files.extend(p/n for n in ['program.data','expected.txt','metrics.json'])
    REPORT.write_text('''# A36三项低IPC程序定向采样前汇报

A36已实测IPC几何平均0.9918977910、总面积含SRAM35,686.138058μm²、Fmax297.24238026MHz，六perf答案全PASS。面积显著改善并达到门槛，IPC仍需约10.9%，有实际可观收益，值得定位剩余动态停顿；暂不重复19项正确性或所有中间候选测试。

本次仅对已测A36的median/qsort/towers三项低IPC程序各采样一次。复用已编译的Verilator5.020 CPU模型archive和runtime对象，只编译/链接一个旁路C++观察驱动；没有新的Verilog生成、RTL修改、CPU模型编译、综合或STA。原sim.cpp、sim.exe、模型archive和所有A36结果保持冻结。新增驱动等于官方sim.cpp仅增加root header、host-side只读计数和stderr JSON输出；反向删除这三处插入逐字恢复原驱动。不增加eval、tick、timeInc、内存步骤或CPU寄存器写入。

通过原官方oj_io准备相同stdin，latency10、MAX_CYCLES1,000,000、程序/答案/动态指令分子不变；逐项要求stdout退出答案与原课程一致，官方CPU2026 cycles必须与原A36三项完全相等。不同则不把采样作为同源码证据。不会把采样获得的三个IPC替代六项GEOMEAN。

现有ENABLE_CACHE_STATS=0，不能读取恒零的RTL统计寄存器。新增host计数在原posedge之前采样已eval的fetch/trace/RS/occupancy/branch pending/cache event信号，记录前端空、派发完全受阻、RS issue、ROB/RS/LSQ满及占用、branch pending及其与ready RS的重叠。读取现有predictor反馈正确率和最终debug值。只采样reset=0且core halted=0的周期，样本数与外部内存完成周期可能不同；各类停顿重叠，不能相加成总损失。

branch_pending_with_ready_rs只是“存在就绪条目”的上界，不证明它比恢复分支更老。I-cache事件来自原primary cache，不包含全部L0过滤命中。predictor反馈统计保留原同bank优先规则，不等于完整所有执行分支数量。这些边界将随结果记录。

所有采样在对话汇报本文件后开始，只用于决定下一项IPC架构改动。当前A38已独立完成指令SRAM offered-read和每宏命令分发源码，尚未测量；本采样不验证A37/A38，不采用或宣称目标完成。Windows原生，不使用WSL。
''',encoding='utf-8')
    plan=dict(status='PROFILE_PREPARED_NOT_STARTED',created_at=datetime.now(timezone.utc).isoformat(),
        run=str(RUN),cases=CASES,profile_driver_sha256=sha(OUT/'profile_driver.cpp'),
        frozen_inputs_sha256={str(p):sha(p) for p in files},report=str(REPORT),report_sha256=sha(REPORT),
        latency=10,max_cycles=1000000,rtl_model_recompiled=False,new_synthesis=False,new_sta=False,
        observations_do_not_modify_model=True,expected_cycles={r['name']:r['cycles'] for r in read(RUN/'result/ipc.json')['results'] if r['name'] in CASES})
    write(OUT/'plan.json',plan);check()
    print({k:plan[k] for k in ('status','cases','rtl_model_recompiled','report','expected_cycles')})


def build():
    plan=check()
    assert not (OUT/'build.json').exists()
    config=read(RUN/'course_windows_config.json')
    include=Path(config['tools_root'])/'verilator/share/verilator/include'
    compiler='F:/c26/msys64/mingw64/bin/g++.exe'
    obj=OUT/'profile_driver.o';exe=OUT/'profile.exe'
    compile_cmd=[compiler,'-std=c++17','-O2','-DVM_TRACE=1','-DVM_TRACE_VCD=1','-DVM_TRACE_FST=0',
        '-DVM_COVERAGE=0','-DVM_SC=0','-I'+str(MODEL),'-I'+str(include),'-I'+str(include/'vltstd'),
        '-c',str(OUT/'profile_driver.cpp'),'-o',str(obj)]
    link_cmd=[compiler,str(obj),str(MODEL/'verilated.o'),str(MODEL/'verilated_vcd_c.o'),
        str(MODEL/'verilated_threads.o'),str(MODEL/'Vstudent_top__ALL.a'),str(RUN/'native_build/windows_time_zero.o'),
        '-pthread','-lpthread','-latomic','-o',str(exe)]
    with (OUT/'build.log').open('w',encoding='utf-8') as log:
        for cmd in [compile_cmd,link_cmd]:subprocess.run(cmd,check=True,env=env(),stdout=log,stderr=subprocess.STDOUT)
    record=dict(status='HOST_OBSERVER_ONLY_BUILT',commands=[compile_cmd,link_cmd],profile_executable_sha256=sha(exe),
        object_sha256=sha(obj),original_model_archive_sha256=plan['frozen_inputs_sha256'][str(MODEL/'Vstudent_top__ALL.a')],
        model_recompiled=False,tests_started=False)
    write(OUT/'build.json',record);check()
    print({k:record[k] for k in ('status','model_recompiled','tests_started')})


def run():
    plan=check();build_record=read(OUT/'build.json')
    assert not (OUT/'result.json').exists() and not (OUT/'started.json').exists()
    exe=OUT/'profile.exe';assert sha(exe)==build_record['profile_executable_sha256']
    scripts=RUN/'source/.deps/RISC-V-CPU-2026/scripts'
    sys.path.insert(0,str(scripts))
    from oj_io import prepare_case, compare_output
    write(OUT/'started.json',dict(started_at=datetime.now(timezone.utc).isoformat(),cases=CASES))
    results=[]
    for name in CASES:
        case=RUN/'source/.deps/RISC-V-CPU-2026/testcases'/name
        data,answer=prepare_case(case,plan['max_cycles'],plan['latency'])
        process=subprocess.run([str(exe)],input=data,text=True,capture_output=True,env=env(),check=True)
        (OUT/(name+'.stdout')).write_text(process.stdout,encoding='utf-8')
        (OUT/(name+'.stderr')).write_text(process.stderr,encoding='utf-8')
        assert not compare_output(process.stdout,answer),name
        cycles=int(re.search(r'^CPU2026 cycles=(\d+)$',process.stderr,re.M)[1])
        assert cycles==plan['expected_cycles'][name],(name,cycles,plan['expected_cycles'][name])
        import json
        observations=json.loads(re.search(r'^PROFILE_JSON=(\{.*\})$',process.stderr,re.M)[1])
        results.append(dict(name=name,cycles=cycles,official_answer_passed=True,cycles_exact_a36=True,observations=observations))
        write(OUT/'progress.json',dict(completed=len(results),results=results))
        print(name,cycles,observations,flush=True)
    check()
    write(OUT/'result.json',dict(status='THREE_CASE_HOST_PROFILE_COMPLETE',results=results,
        same_model_as_a36=True,model_recompiled=False,new_synthesis=False,new_sta=False,
        recorded_at=datetime.now(timezone.utc).isoformat(),plan_sha256=sha(OUT/'plan.json')))


if __name__=='__main__':
    assert os.name=='nt'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','build','run'])
    {'prepare':prepare,'build':build,'run':run}[parser.parse_args().action]()
