"""Freeze and serialize one course-pinned Windows A56-A69 characterization."""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT,read,sha,write,optional
from manage_er1_a55_serial_measurement import check as check_a55r2,memory_status
from wait_frequency_directed_native import live

REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A69_same_edge_redirect_fetch')
RUN=Path('F:/CPU2026CourseRuns/ER1_A69_tier3_20261006')
REPORT=ROOT/'reports/ER1_A69_pretest_2026-10-06.md'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES=[ROOT/'tools/run_course_standard_windows.py',ROOT/'tools/prebuild_course_windows.py',
    ROOT/'tools/verilator_windows_time_zero.cpp',Path(__file__)]


def check():
    plan=read(RUN/'measurement_plan.json')
    for path,key in [(RUN/'source_manifest.json','source_manifest_sha256'),
        (RUN/'course_windows_config.json','config_sha256'),(REPORT,'pretest_report_sha256'),
        (CANDIDATE/'candidate.json','candidate_sha256'),(RUN/'a55r2_reference.json','reference_sha256')]:
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
    check_a55r2()
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
    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A55_predictor_bank_local_prefix_history')
    for number in range(56,70):
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
    progress[str(ROOT/'build/cpu2026/er1_a64_a67_source_progress_20261006.json')]=sha(ROOT/'build/cpu2026/er1_a64_a67_source_progress_20261006.json')
    progress[str(ROOT/'build/cpu2026/er1_recovery_and_redirect_source_audit_20261006.json')]=sha(ROOT/'build/cpu2026/er1_recovery_and_redirect_source_audit_20261006.json')
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
        'RENAME_RETAIN_FREE_POOL','FRONTEND_REDIRECT_REQUEST','RAS_REPEAT_COMPRESSION','RAS_REPEAT_COUNTER_BITS'):
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
    write(RUN/'a55r2_reference.json',reference)
    REPORT.write_text(f'''# ER1 A69 累计方案测试前汇报

目标仍是频率严格大于300MHz、IPC几何平均至少1.1、包含SRAM总面积至多36000μm²，以及完整RV32IM、OoO、顺序提交、MMIO与参数化。当前已测最优A55R2：IPC {original['ipc']:.10f}，频率{original['fmax_mhz']:.8f}MHz，总面积{original['area_um2']:.6f}μm²；六项性能答案通过，完整正确性未运行。IPC还需提升约{(1.1/original['ipc']-1)*100:.5f}%。

本批是A56–A69的集中测量。此前没有逐项执行HDL/lint/仿真/综合/STA/单元测试。主要可观结构收益是统一缩短恢复到正确路径重新重命名的等待：

1. A65保留注册的分支结果捕获，下一拍直接应用完整代际合格的恢复，去掉描述符登记等待拍及274位后端暂存状态。
2. A66使用当前RAT及每个接受写入的old_phys链，不再在后缀回滚末端重复覆盖分支目的映射；完整ROB代际权威不变。A67按在途目的寄存器唯一归属直接统计撤销写入，使数量计算与回收位图解码并行。
3. A68保留已经空闲但尚未分配的候选池P，恢复未预留位图为F减P；逻辑空闲集仍是F，原始free_count/RAT恢复不变。池非空时无需在恢复后再补充一拍。
4. A69在重定向边缘一致地提供新PC/epoch给注册响应Icache，并只按实际新请求fire登记pending。旧响应在重定向当拍仍不可消费，MSHR交易epoch/ID、控制预取例外和AXI源码完整保留。

满足热过滤器命中、请求可接受、空闲池非空、ROB信用和后端入口可用等条件时，源码时间线允许第一条目标束从原先约c+4接受重命名提前到c+2。这是条件性等待路径删除，不能当作所有重定向都节省两拍，也不能把A36旧统计迁移成A69收益。旧A36记录中median/qsort/towers分别有556/10095/89次恢复、1112/20190/178个pending周期，说明恢复占用有实质规模，但统计来自另一源码，且与其他停顿重叠。

A56–A60重排前端固定字、偏移与RAS预译码以缩短组合依赖；A61–A63把完整GEN资格与incoming取消位同RS数据选择，保留所有held-result取消；A64为相同连续RAS返回地址增加24位重复计数。towers静态七层递归支持容量压缩，但BTB已有帮助且错路径RAS未完全修复，单靠压缩的IPC收益不保证显著。

源码状态预算相对A63为24位增加减274位删除，即净减少250位逻辑FF；直接ROB模式另有43位旧描述符不再消费。未新增SRAM或普通流水边界。实际面积并非按这些位数简单相减：八个并行完整GEN成员查询、取消控制、RAS地址比较和新恢复/取指控制均可能增加组合成本。已测面积余量约{36000-original['area_um2']:.3f}μm²，本批总面积未知。

主要时序风险：注册分支tag/head经RAT回滚到映射FF；ROB资格/回收数经free_count恢复；redirect PC到Icache tag/SRAM命令；redirect控制到有效epoch及MSHR/filter ready。没有增加假路径或缩减GEN，是否保持300MHz以上必须测量。

剩余方案评估：

- 精确RAS修复需要保存指针及可能被错路径覆盖的顶部/重复内容；当前无足够面积/动态收益依据。清空RAS不等同修复，也可能损失有效调用历史。
- 更大的预测表、TAGE/loop/agree机制、缓存/MSHR/ROB扩容需要动态冲突或容量瓶颈支持；静态chooser冲突稀疏，不能据此承诺8%以上IPC提升。
- ALU/MDU/LSQ结果直唤醒已存在；重复添加没有收益。六个perf镜像没有M指令，但完整RV32IM必须保留M单元。
- 新增普通流水级增加依赖/恢复延迟；本批先删等待及重复组合依赖。同拍恢复再重命名需建立RAT/free/ROB尾部/GEN释放与新分配的完整转发协议，不能简单取消branch_pending门控。

本批目前没有更多基于已掌握证据、可以直接落地并解释成本的结构改动。先集中表征这14项相互配合的源码改动，确定下一瓶颈；上述后续架构选项仍保留。实际IPC/Fmax/面积未知，尚不能宣称目标达成。

执行仅用Windows原生课程固定链：框架54fc150ffc290f52aa024209ffb9a29d43856f6d、测试29f980727f7d99a1842a58f34091c7579ba3fe85、Yosys0.63/OpenSTA3.1/Verilator5.020、课程ASAP7 RVT TT与FakeRAM模型，latency10，综合映射clock2ns及原始STA约束。SRAM计入面积。不使用WSL。冻结{len(names)}文件，其中{len(dependencies)}课程依赖与A55R2逐字节一致。

为避免此前并行工具前端std::bad_alloc，单一监督进程按原runner选项串行调度一次--timing-only，再以同一manifest/config/工具/报告身份执行一次--reuse-synth。只构建一个CPU并运行六个perf（各原始1000000周期预算及官方答案）；不逐项测试、不同时跑两套大型工具前端、不自动重试或覆盖失败现场。完整19正确性及M/恢复/代际/缓存/参数覆盖仍是最终采用前要求，数值明确改善后再集中执行。

运行时保持本快照不变，继续独立优化；观察超时继续查询原始监督PID，不能当作终止或重新构建依据。主E工作区EU RTL未改动。报告生成时无HDL/构建/仿真/综合/STA作业启动；对话汇报后才调度。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源码manifest SHA256：{sha(RUN/'source_manifest.json')}

全部源码/工具/库/主机脚本、14份审阅和前述进度证据由measurement_plan.json绑定。
''',encoding='utf-8')
    tool_paths=[Path(config[key]) for key in ['yosys','abc','sta','verilator','verilator_build_driver']]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan=dict(status='PREPARED_NOT_STARTED',candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT),pretest_report_sha256=sha(REPORT),reference_sha256=sha(RUN/'a55r2_reference.json'),
        host_sha256={str(p):sha(p) for p in HOST_FILES},tool_sha256={str(p):sha(p) for p in tool_paths},
        source_reviews_sha256=reviews,source_progress_sha256=progress,perf_cases=perf,correctness_cases=correctness,
        source_files=len(names),unchanged_course_dependency_files=len(dependencies),effective_structural_profile=effective,
        serial_tool_phases=True,native_cpu_builds_planned=1,new_synth_runs_planned=1,perf_max_cycles=1000000,
        correctness_started_with_characterization=False,full_correctness_and_relevant_coverage_required_before_adoption=True,
        main_active_manifest_sha256=expected_active,memory_at_preparation=memory_status(),
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal.update(status='A69_FROZEN_SERIAL_PRETEST_NOT_STARTED',prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,previous_goal_turn_classification=goal['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A56_A69_COHERENT_RECOVERY_OWNERSHIP_AUDIT_AND_NATIVE_PRETEST_FROZEN',
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
    goal.update(status='A69_SERIAL_CHARACTERIZATION_IN_PROGRESS',active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid,active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN/'dispatch_identity.json'),candidate_tests_started=True,
        pending_source_candidate_tests_started=True,candidate_metrics_belong_to=CANDIDATE.name,
        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_A69_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH')
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
