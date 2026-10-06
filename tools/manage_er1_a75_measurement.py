"""Freeze and serialize one course-pinned Windows A70-A75 characterization."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT,read,sha,write,optional
from manage_er1_a55_serial_measurement import memory_status
from manage_er1_a69_measurement import check as check_a69
from wait_frequency_directed_native import live

REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A69_tier3_20261006')
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A75_branch_capture_phase_valid')
RUN=Path('F:/CPU2026CourseRuns/ER1_A75_tier3_20261006')
REPORT=ROOT/'reports/ER1_A75_pretest_2026-10-06.md'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES=[ROOT/'tools/run_course_standard_windows.py',ROOT/'tools/prebuild_course_windows.py',
    ROOT/'tools/verilator_windows_time_zero.cpp',Path(__file__)]


def check():
    plan=read(RUN/'measurement_plan.json')
    for path,key in [(RUN/'source_manifest.json','source_manifest_sha256'),
        (RUN/'course_windows_config.json','config_sha256'),(REPORT,'pretest_report_sha256'),
        (CANDIDATE/'candidate.json','candidate_sha256'),(RUN/'a69_reference.json','reference_sha256')]:
        assert sha(path)==plan[key],path
    for group in ['host_sha256','tool_sha256','source_reviews_sha256','source_progress_sha256']:
        for path,digest in plan[group].items():assert sha(Path(path))==digest,path
    for name,digest in read(RUN/'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN/'source'/name)==digest,name
    c=read(RUN/'course_windows_config.json')
    assert c['environment']=='WINDOWS_NATIVE' and c['wsl_allowed'] is False and c['latency']==10
    assert c['framework_revision']=='54fc150ffc290f52aa024209ffb9a29d43856f6d'
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    check_a69()
    dispatch=read(REFERENCE/'dispatch_identity.json')
    assert not live(dispatch['process_id'])
    original=read(REFERENCE/'result/result.json')
    assert original['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert original['official_perf_expected_results_passed']
    goal=read(GOAL)
    assert goal['current_source_candidate']==CANDIDATE.name and not goal['candidate_tests_started']
    assert goal['active_measurement_candidate'] is None and not goal['active_measurement_process_ids']
    candidate=read(CANDIDATE/'candidate.json')
    assert sha(CANDIDATE/'candidate.json')==goal['pending_source_candidate_sha256']
    assert not candidate['tests_started'] and not candidate['adopted']
    reviews={};scripts={}
    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A69_same_edge_redirect_fetch')
    for number in range(70,76):
        review_path=CANDIDATE.parent/f'A{number}_source_review.json'
        review=read(review_path);source=Path(review['candidate']);record=read(source/'candidate.json')
        assert sha(source/'candidate.json')==review['candidate_sha256']
        assert Path(record['parent_candidate']).resolve()==previous.resolve()
        assert sha(previous/'candidate.json')==record['parent_candidate_sha256']
        assert not record['tests_started'] and not record['adopted']
        for name,digest in record['source_sha256'].items():assert sha(source/name)==digest,(source.name,name)
        reviews[str(review_path)]=sha(review_path)
        previous=source
    assert previous.resolve()==CANDIDATE.resolve()
    progress={goal['last_source_progress_proof']:goal['last_source_progress_proof_sha256']}
    for proof_name in ['er1_a70_source_progress_20261006.json',
        'er1_a69_partial_ppa_a71_a72_source_progress_20261006.json',
        'er1_a69_complete_result_20261006.json']:
        p=ROOT/'build/cpu2026'/proof_name
        progress[str(p)]=sha(p)
    active_path=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    expected_active=read(Path(goal['last_source_progress_proof']))['main_active_manifest_sha256']
    assert sha(active_path)==expected_active
    for name,digest in active['source_sha256'].items():assert sha(ROOT/name)==digest,name
    top=(CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in candidate['parameter_overrides'].items():
        m=re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert m and int(m[1])==value,key
    effective={}
    for key in ('FE_WIDTH','BE_WIDTH','INT_ISSUE_WIDTH','CDB_WIDTH','SERIAL_BACKEND',
        'PREDICTOR_HISTORY_BITS','PREDICTOR_COMPACT_BTB_ENTRIES','DCACHE_WAYS','DCACHE_MSHRS',
        'ICACHE_MSHRS','ROB_ENTRIES','PHYS_REGS','RS_ENTRIES','LSQ_ENTRIES',
        'RECOVERY_DIRECT_APPLY','RAT_SUFFIX_BRANCH_MAPPING','ROB_UNIQUE_RECLAIM_COUNT',
        'RENAME_RETAIN_FREE_POOL','FRONTEND_REDIRECT_REQUEST','RAS_REPEAT_COMPRESSION','RAS_REPEAT_COUNTER_BITS',
        'RECOVERY_ROB_CREDIT','LSQ_SECOND_REPORT_RECLAIM','BRANCH_CAPTURE_REDIRECT_READY',
        'RAS_REPEAT_MATCH_PREDECODE','FRONTEND_RAS_PARALLEL_CONTROL','BRANCH_CAPTURE_PHASE_VALID'):
        m=re.search(r'\b'+key+r'\s*=\s*(\d+)',top);assert m,key;effective[key]=int(m[1])
    effective.update(gshare_entries=256,bimodal_entries=256,chooser_entries=64,btb_entries=16,
        predictor_banks=4,predictor_metadata_width=16,rob_generation_bits=8)
    parent=read(REFERENCE/'source_manifest.json')
    names=sorted(set(parent['snapshot_sha256'])|set(candidate['source_sha256']))
    for name in names:
        source=CANDIDATE/name if name in candidate['source_sha256'] else REFERENCE/'source'/name
        assert source.exists(),name
        destination=RUN/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
    dependencies=[name for name in names if name.startswith('.deps/')]
    for name in dependencies:assert sha(RUN/'source'/name)==parent['snapshot_sha256'][name],name
    tests=RUN/'source/.deps/RISC-V-CPU-2026/testcases'
    perf=sorted(p.name for p in tests.glob('perf_*') if p.is_dir())
    correctness=sorted(p.name for p in tests.glob('correctness_*') if p.is_dir())
    assert len(perf)==6 and len(correctness)==19
    frozen=dict(format='er1-tier3-native-source-v1',status='FROZEN_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(RUN/'source'),
        reference_manifest_sha256=sha(REFERENCE/'source_manifest.json'),candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),framework_commit=candidate['framework_commit'],
        testcases_commit=candidate['testcases_commit'],parameter_overrides=candidate['parameter_overrides'],
        effective_structural_profile=effective,materialized_top_defaults=True,
        snapshot_sha256={name:sha(RUN/'source'/name) for name in names},tests_started=False)
    write(RUN/'source_manifest.json',frozen)
    config=read(REFERENCE/'course_windows_config.json')
    config.update(source=str(RUN/'source'),source_manifest=str(RUN/'source_manifest.json'),
        out=str(RUN/'result'),native_build_path=str(RUN/'native_build'),native_ipc_path=str(RUN/'native_ipc'))
    write(RUN/'course_windows_config.json',config)
    reference=dict(run=str(REFERENCE),source_manifest_sha256=sha(REFERENCE/'source_manifest.json'),
        result_sha256=sha(REFERENCE/'result/result.json'),ipc_report_sha256=sha(REFERENCE/'result/ipc.json'),
        ppa_report_sha256=sha(REFERENCE/'result/synth/opt/report.json'),ipc=original['ipc'],
        fmax_mhz=original['fmax_mhz'],area_um2=original['area_um2'],
        official_perf_expected_results_passed=True,full_correctness_not_run=True)
    write(RUN/'a69_reference.json',reference)
    REPORT.write_text(f'''# ER1 A75：A70–A75 集中测量前汇报

目标保持频率严格大于300MHz、六项IPC几何平均至少1.1、含SRAM总面积至多36000μm²，并保留完整RV32IM、OoO、严格顺序提交、MMIO和参数化要求。

当前频率/面积符合目标的已测综合最优仍是A55R2：IPC1.01714182，Fmax306.86245MHz，总面积35480.53090μm²。最近完成的A69为IPC{original['ipc']:.8f}、Fmax{original['fmax_mhz']:.5f}MHz、总面积{original['area_um2']:.5f}μm²；六项性能程序通过，但频率低于目标，未采用。完整19正确性及相关专项覆盖仍未完成。以A69为基准，IPC还需相对提高{(1.1/original['ipc']-1)*100:.4f}%。

本批累计六项源码改动，没有逐项执行HDL/lint/形式/仿真/综合/STA/单元测试：

1. A70在充分限定的直接恢复apply边沿，把现有ROB信用寄存器写成min(BE_WIDTH,ROB_ENTRIES-1-branch_age)，减少旧占用数的保守滞后。实际分配容量、GEN和其他信用保护不变。
2. A71在原来两项前缀回收机制中，允许第二项已完成加载通过当拍原始单报告端口握手满足上报条件；没有新增完成端口，存储仍遵守原始队首确认顺序。
3. A72在valid+redirect+!pending条件下，通用ALU ready等于现有重定向优先规则。捕获改用这个等价表达式，实际ALU ready/消费不变，切断普通完成队列ready对捕获的结构依赖。
4. A73在取指位置尚未被最终调用选择时就计算返回PC是否匹配RAS栈顶。FE1/2/4共享PC高位及高位+1比较，最终只选择一位相等结果；调用返回、计数、溢出和原地址写入规则不变。
5. A74用并行首事件掩码表达原RAS循环，字边界改为常数比较，响应接受置于最终局部门控。先前调用/返回/预测跳转终止前缀的语义保留。
6. A75只在直接恢复且A72启用时，让捕获查询ALU取消前的已保存有效位。捕获必须pending=0，而直接ROB apply唯一来源是pending=1，因此捕获相位cancel恒为0；所有真实执行、完成、唤醒、消费和8位GEN检查保持原样。其他配置退回原输入。

主要收益依据来自已经测量的A69最慢路径，而不是泛化经验或位数估算。五条最慢路径共享主干：注册pending tag→ROB完整GEN资格→MDU取消/普通完成ready→重定向相关Icache响应→预测器→RAS。最长数据到达4.293ns。A72与A75在源图上删除普通完成ready和恢复apply到新分支捕获的反馈依赖；A73/A74缩短RAS末端晚到控制传播。A69中RAS地址选择控制到达约3.578ns，后续约0.715ns，但不能把整个区间当作可保存延迟。当前三项针对已测严重退化的结构性依赖已完成，值得集中重新表征；实际改善大小和是否恢复到300MHz以上未知。

这六项没有新增声明的FF/SRAM/普通或恢复流水边沿。新增信用/回收组合门、早期地址比较和电气扇出仍会改变面积；A69面积余量仅{36000-original['area_um2']:.3f}μm²，不能承诺面积达标。原SRAM、缓存容量、MSHR数量、预测表、ROB/PRF/RS/LSQ深度、FE4/BE2/双整数/CDB2及8位ROB代数保持相同。

源码审查范围包含直接恢复容量0/1/2/满/绕回、LSQ队首及第二项报告握手/停顿/恢复、全部取指位置和PC高位进位/全32位绕回、RAS空/满/计数溢出、先前调用/返回/taken事件、恢复相位与新捕获互斥、旧GEN/重复重定向、width1/2/4和选项0回退。当前是布尔/算术/相位与哈希论证，不是形式或动态等价证明。本批没有加入false-path、忽略恢复或减少标签代数位。

剩余想法已评估：

- 扩PRF：六项925条与实际镜像绑定的反汇编中，只有rsort写过的架构寄存器种类使静态物理容量可能先于ROB32受限；其他程序缺乏扩容收益依据。free-pool滞后不等同物理容量不足，因此先不花面积扩PRF。
- 精确RAS修复：恢复指针仍不能保证被错路径覆盖的地址/重复计数正确。增加逐分支完整检查点会显著增加面积；缺乏当前动态返回错误分布，暂不实现没有成本收益依据的修复。
- 提前到原始RS/ALU输入解决分支：会把load wake、RS rank、分支比较、GEN检查和取指串在同拍，需要额外预测/撤销或转发协议；不能简单移走结果寄存器。
- 扩ROB/LSQ/cache/预测表或引入loop/TAGE：需要当前动态容量/命中/方向错误分布支持。A36旧记录不能充当A75动态瓶颈，也不能把互相重叠的停顿相加。
- 已有ALU/MDU/LSQ直唤醒和原始存储地址早发机制，重复加入旁路没有依据。六项perf没有M指令，仍必须保留完整M扩展功能。
- 给恢复到取指路径增加普通等待拍可能恢复时序，却可能放弃A69已测IPC收益；先表征这批删除无效串行依赖的改写。

目前没有剩余基于这组已测最慢路径、能直接落地并解释正确性与成本的修改。先集中测量A70–A75，再按真实新瓶颈继续推进；长期架构选项没有被宣称穷尽，IPC1.1也没有被缩减为当前较低结果。

测试只用Windows原生课程标准链：框架54fc150ffc290f52aa024209ffb9a29d43856f6d、测试29f980727f7d99a1842a58f34091c7579ba3fe85、Yosys0.63、OpenSTA3.1、Verilator5.020、课程ASAP7 RVT TT及FakeRAM模型，latency10；映射clock2ns和原STA约束保持相同，SRAM计入总面积，不用WSL。冻结{len(names)}文件，{len(dependencies)}课程依赖与A69逐字节一致。

原监督模式串行执行一次--timing-only，再用同一源码manifest/config/工具/报告身份执行一次--reuse-synth；只构建一个CPU并运行六项官方perf，各1000000周期及原始答案。无并行大型工具前端、逐改测试、自动重试或失败覆盖。完整19正确性与M/恢复/代际/缓存/参数专项仍须在采用前完成，待数值明确改善后集中验证。

报告生成时没有HDL/构建/仿真/综合/STA作业启动。先在对话汇报后才调度；运行中保持本快照不变，在独立候选继续优化IPC及面积。主E工作区EU RTL不改动。PID查询超时不能用于重启原作业。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源码manifest SHA256：{sha(RUN/'source_manifest.json')}

全部源码、库、工具、主机脚本、六份审阅和源级/实测证据绑定在measurement_plan.json。
''',encoding='utf-8')
    tool_paths=[Path(config[key]) for key in ['yosys','abc','sta','verilator','verilator_build_driver']]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan=dict(status='PREPARED_NOT_STARTED',candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT),pretest_report_sha256=sha(REPORT),reference_sha256=sha(RUN/'a69_reference.json'),
        host_sha256={str(p):sha(p) for p in HOST_FILES},tool_sha256={str(p):sha(p) for p in tool_paths},
        source_reviews_sha256=reviews,source_progress_sha256=progress,perf_cases=perf,correctness_cases=correctness,
        source_files=len(names),unchanged_course_dependency_files=len(dependencies),effective_structural_profile=effective,
        serial_tool_phases=True,native_cpu_builds_planned=1,new_synth_runs_planned=1,perf_max_cycles=1000000,
        correctness_started_with_characterization=False,full_correctness_and_relevant_coverage_required_before_adoption=True,
        main_active_manifest_sha256=expected_active,memory_at_preparation=memory_status(),
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal.update(status='A75_FROZEN_SERIAL_PRETEST_NOT_STARTED',prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,previous_goal_turn_classification=goal['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A70_A75_CRITICAL_PATH_PHASE_AUDIT_AND_NATIVE_PRETEST_FROZEN',
        goal_complete=False,candidates_adopted=False)
    write(GOAL,goal)
    check()
    print({k:plan[k] for k in ['status','candidate','source_files','unchanged_course_dependency_files',
        'pretest_report','pretest_report_sha256','source_manifest_sha256','serial_tool_phases']})


def start():
    plan=check()
    assert not (RUN/'dispatch_identity.json').exists() and not (RUN/'result').exists()
    command=[sys.executable,'-u',str(Path(__file__)),'run-phases']
    with (RUN/'driver_stdout.log').open('w',encoding='utf-8') as stdout,(RUN/'driver_stderr.log').open('w',encoding='utf-8') as stderr:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch=dict(status='SERIAL_BACKGROUND_DISPATCHED',process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(),command=command,
        source_manifest_sha256=plan['source_manifest_sha256'],pretest_report_sha256=plan['pretest_report_sha256'],
        initial_process_alive=process.poll() is None,serial_tool_phases=True,full_correctness_started=False)
    write(RUN/'dispatch_identity.json',dispatch)
    goal=read(GOAL)
    goal.update(status='A75_SERIAL_CHARACTERIZATION_IN_PROGRESS',active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid,active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN/'dispatch_identity.json'),candidate_tests_started=True,
        pending_source_candidate_tests_started=True,candidate_metrics_belong_to=CANDIDATE.name,
        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_A75_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH')
    write(GOAL,goal)
    print(dispatch)


def run_phases():
    plan=check()
    assert not (RUN/'serial_phase_identity.json').exists()
    record=dict(status='SERIAL_TIMING_IN_PROGRESS',supervisor_pid=os.getpid(),
        source_manifest_sha256=plan['source_manifest_sha256'],phases=[])
    write(RUN/'serial_phase_identity.json',record)
    for phase,flag in [('timing','--timing-only'),('performance','--reuse-synth')]:
        if phase=='performance':
            timing=read(RUN/'result/timing_only.json')
            assert timing['status']=='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
            assert timing['source_manifest_sha256']==plan['source_manifest_sha256']
            assert timing['config_sha256']==plan['config_sha256']
            assert sha(RUN/'result/synth/opt/report.json')==timing['official_report_sha256']
            record.update(status='SERIAL_PERFORMANCE_IN_PROGRESS',timing_report_sha256=sha(RUN/'result/timing_only.json'))
            write(RUN/'serial_phase_identity.json',record);check()
        command=[sys.executable,'-u',str(ROOT/'tools/run_course_standard_windows.py'),
            '--config',str(RUN/'course_windows_config.json'),flag]
        print('START SERIAL '+phase,flush=True)
        with (RUN/f'{phase}_stdout.log').open('w',encoding='utf-8') as stdout,(RUN/f'{phase}_stderr.log').open('w',encoding='utf-8') as stderr:
            result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        record['phases'].append(dict(phase=phase,command=command,returncode=result.returncode,
            completed_at=datetime.now(timezone.utc).isoformat(),memory_after_phase=memory_status()))
        if result.returncode:
            record.update(status='SERIAL_'+phase.upper()+'_FAILED');write(RUN/'serial_phase_identity.json',record)
            raise SystemExit(result.returncode)
        write(RUN/'serial_phase_identity.json',record);print('DONE SERIAL '+phase,flush=True)
    record.update(status='SERIAL_CHARACTERIZATION_COMPLETE',result_sha256=sha(RUN/'result/result.json'))
    write(RUN/'serial_phase_identity.json',record)


def observe():
    check()
    dispatch=read(RUN/'dispatch_identity.json');alive=live(dispatch['process_id'])
    result=optional(RUN/'result/result.json');timing=optional(RUN/'result/timing_only.json')
    phase=optional(RUN/'serial_phase_identity.json');failure=optional(RUN/'result/failure.json')
    observation=dict(run=str(RUN),process_id=dispatch['process_id'],process_alive=alive,
        observed_at=datetime.now(timezone.utc).isoformat(),phase=phase['status'] if phase else None,
        result=({k:result.get(k) for k in ['status','ipc','fmax_mhz','area_um2','official_perf_expected_results_passed',
            'official_correctness_suite_passed','thread_objective_numeric_requirements_met']} if result else None),
        timing=({k:timing.get(k) for k in ['status','fmax_mhz','area_um2']} if timing else None),
        failure_summary=str(failure)[:1000] if failure else None)
    for phase_name in ['timing','performance']:
        for stream in ['stdout','stderr']:
            p=RUN/f'{phase_name}_{stream}.log'
            if p.exists():observation[p.name]=[line[:260] for line in p.read_text(errors='replace').splitlines()[-3:]]
    goal=read(GOAL)
    if goal.get('active_measurement_source_manifest_sha256')==dispatch['source_manifest_sha256']:
        goal.update(measurement_process_alive=alive,measurement_last_observed_at=observation['observed_at'],measurement_last_observation=observation)
        write(GOAL,goal)
    print(observation)


if __name__=='__main__':
    assert os.name=='nt','Native Windows only'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','start','run-phases','observe'])
    action=parser.parse_args().action
    {'prepare':prepare,'start':start,'run-phases':run_phases,'observe':observe}[action]()
