"""Freeze and serialize one course-pinned Windows A95-A99 PPA-gated characterization."""
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
from manage_er1_a94_measurement import check as check_a94
from wait_frequency_directed_native import live

REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A94_tier3_20261006')
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A99_balanced_saved_identity')
RUN=Path('F:/CPU2026CourseRuns/ER1_A99_tier3_20261006')
REPORT=ROOT/'reports/ER1_A99_pretest_2026-10-06.md'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES=[ROOT/'tools/run_course_standard_windows.py',ROOT/'tools/prebuild_course_windows.py',
    ROOT/'tools/verilator_windows_time_zero.cpp',ROOT/'tools/prepare_er1_a99_measurement_manager.py',Path(__file__)]

PREPARERS={
    95:'prepare_er1_store_class_compare.py',
    96:'prepare_er1_fast_store_batch.py',
    97:'prepare_er1_rs_elastic_skip_capacity.py',
    98:'prepare_er1_saved_identity_word_mask.py',
    99:'prepare_er1_balanced_saved_identity.py',
}



def check():
    plan=read(RUN/'measurement_plan.json')
    for path,key in [(RUN/'source_manifest.json','source_manifest_sha256'),
        (RUN/'course_windows_config.json','config_sha256'),(REPORT,'pretest_report_sha256'),
        (CANDIDATE/'candidate.json','candidate_sha256'),(RUN/'a94_reference.json','reference_sha256')]:
        assert sha(path)==plan[key],path
    for group in ['host_sha256','tool_sha256','source_reviews_sha256','source_scripts_sha256','source_progress_sha256']:
        for path,digest in plan[group].items():assert sha(Path(path))==digest,path
    for name,digest in read(RUN/'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN/'source'/name)==digest,name
    c=read(RUN/'course_windows_config.json')
    assert c['environment']=='WINDOWS_NATIVE' and c['wsl_allowed'] is False and c['latency']==10
    assert c['framework_revision']=='54fc150ffc290f52aa024209ffb9a29d43856f6d'
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    check_a94()
    dispatch=read(REFERENCE/'dispatch_identity.json')
    assert not live(dispatch['process_id'])
    original=read(REFERENCE/'result/result.json')
    assert original['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert original['official_perf_expected_results_passed']
    terminal=read(ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json')['metrics']
    assert terminal['candidate']=='A94_localparam_dependency_order'
    assert sha(REFERENCE/'result/result.json')==terminal['result_sha256']
    assert sha(REFERENCE/'result/ipc.json')==terminal['ipc_sha256']
    assert sha(REFERENCE/'result/synth/opt/report.json')==terminal['ppa_sha256']
    assert original['ipc']==terminal['ipc'] and original['fmax_mhz']==terminal['fmax_mhz']
    assert original['area_um2']==terminal['area_um2']
    goal=read(GOAL)
    assert goal['current_source_candidate']==CANDIDATE.name and not goal['candidate_tests_started']
    assert goal['active_measurement_candidate'] is None and not goal['active_measurement_process_ids']
    candidate=read(CANDIDATE/'candidate.json')
    assert sha(CANDIDATE/'candidate.json')==goal['pending_source_candidate_sha256']
    assert not candidate['tests_started'] and not candidate['adopted']
    reviews={};scripts={}
    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A94_localparam_dependency_order')
    for number in range(95,100):
        review_path=CANDIDATE.parent/f'A{number}_source_review.json'
        review=read(review_path);source=Path(review['candidate']);record=read(source/'candidate.json')
        assert sha(source/'candidate.json')==review['candidate_sha256']
        assert Path(record['parent_candidate']).resolve()==previous.resolve()
        assert sha(previous/'candidate.json')==record['parent_candidate_sha256']
        assert not record['tests_started'] and not record['adopted']
        for name,digest in record['source_sha256'].items():assert sha(source/name)==digest,(source.name,name)
        preparer=ROOT/'tools'/PREPARERS[number]
        assert sha(preparer)==record['preparation_script_sha256'],preparer
        scripts[str(preparer)]=sha(preparer)
        reviews[str(review_path)]=sha(review_path)
        previous=source
    assert previous.resolve()==CANDIDATE.resolve()
    progress={goal['last_source_progress_proof']:goal['last_source_progress_proof_sha256']}
    for proof_name in ['er1_a94_complete_result_20261006.json',
        'er1_a95_background_progress_20261006.json',
        'er1_a96_background_progress_20261006.json',
        'er1_a94_ppa_a97_a98_progress_20261006.json',
        'er1_a99_source_progress_20261006.json']:
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
        'RAS_REPEAT_MATCH_PREDECODE','FRONTEND_RAS_PARALLEL_CONTROL','BRANCH_CAPTURE_PHASE_VALID',
        'LOAD_COMPLETION_BYPASS','LSQ_PICK_LOCAL_VALIDITY','LSQ_FORWARD_ONEHOT','LSQ_PICK_ONEHOT',
        'FAST_STORE_COMPLETE','FAST_STORE_ADDRESS_PREDECODE','FAST_STORE_IDENTITY_PRESELECT',
        'ROB_STORE_PREFIX_ADMISSION','LSQ_STORE_ACK_SOURCE_QUERY','LSQ_HEAD_STORE_ACK_BYPASS',
        'FAST_STORE_SAVED_OPERANDS','LSQ_SAVED_REPORT_PRIORITY','LSQ_HEAD_LOAD_IDENTITY_QUERY',
        'LSQ_ALLOC_SLOT_PRESELECT','LSQ_HEAD_LOAD_PACKET_PRESELECT','LSQ_RESPONSE_SOURCE_QUERY',
        'FAST_STORE_WB_DATA','FAST_STORE_CLASS_COMPARE','FAST_STORE_BATCH','RS_ELASTIC_SKIP_CAPACITY',
        'LSQ_SAVED_IDENTITY_WORD_MASK','LSQ_SAVED_IDENTITY_BALANCED_MERGE'):
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
    assert len(names)==157 and len(dependencies)==116
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
    write(RUN/'a94_reference.json',reference)
    REPORT.write_text(f'''# A99：保持 A94 周期行为的频率批次，测量前汇报

目标仍为Fmax严格>300MHz、课程六性能IPC几何平均≥1.1、含SRAM总面积≤36000μm²；完整RV32IM、OoO、顺序提交、MMIO和参数化保留。

## 参考与改动

原A94监督PID84416已结束，timing/performance返回0/0，完整身份及原课程程序已核对。参考IPC{original['ipc']:.9f}、Fmax{original['fmax_mhz']:.6f}MHz、总面积{original['area_um2']:.6f}μm²；六性能答案通过、19正确性未跑。周期3.4453125ns，需要缩短超过111.979167ps；面积余量201.027322μm²。A99未测，不能借用参考指标。

| 源码修改 | 作用与状态 |
|---|---|
| A95 | 用原低12位carry与高位prefix精确推导保存地址RAM类别，保留原sum/实际地址/对齐和WB优先级。 |
| A96 | 可选并行快存储功能保留；本次课程profile关闭FAST_STORE_BATCH，保持A94单身份和至多一条快存储，控制组合面积。 |
| A97 | 保存D需求与free+k提前计算，晚load/store跳过资格只选布尔容量，保持原实际RS需求、原子admit与信用。 |
| A98 | 保存报告grant分布到最多16位一组；每位仍为原grant & identity。 |
| A99 | 保留每个二叉OR为独立组合层，原每节点left|right、所有query/包/填充位保持。 |

无新增声明FF、SRAM、流水边沿或端口容量，FE4/BE2/整数2/CDB2、ROB32/PRF56/RS8/LSQ16/BTB16、缓存/预测表与完整GEN位数不改。这些布尔重写预计二值输入下周期行为与A94相同，但新IPC及完整正确性仍需实测。

## 可观收益依据和剩余风险

A94关键路径：LSQ边界/held资格0.6385ns→hold分布0.7101ns→saved身份query1.593ns→ROB live1.811ns→完成选择2.185ns→分配控制约3.004ns→GEN3.247ns→FF3.385ns。报告相关_223268_为61负载/30.94fF，单门373.5ps，后继INV167.7ps；后段另有40负载NAND耗220.5ps。当前周期只需减少约112ps。

A98限制报告grant叶掩码负载；A99阻止原名义4层OR被跨层因式合成为约十级交替AOI/OAI；A97同时移走晚ready后计数/减法/容量比较。三项覆盖同链不同串行因素，有依据支持一次集中PPA判断。门到源变量的部分归属为推断，不能把单门耗时直接相加当预测节省。额外缓冲、OR层、映射变化及新瓶颈可能使面积/频率不达标；201μm²余量很小。

源码推导逐项核对原mask/OR递推、query位域、包格式、held/head/grant优先级、GEN/取消/恢复、实际fire/信用以及保存地址carry/sign/RAM分类。仅源码阅读、哈希与既有证据；本报告生成时未运行HDL/lint/形式/仿真/综合/STA/单元测试。

额外流水沿会改变同周期唤醒和原子入队，当前IPC余量仅1.37%；扩容和更复杂预测器没有当前性能瓶颈证据且面积受限。第三份held/normal ROB资格会复制GEN/live逻辑，在已有掩码/OR负载问题尚未判断前净收益依据较弱。当前已完成能直接支撑收益的同路径修改，之后继续以新结果探索其他路径，不把这批当穷尽长期方案。

## 集中测量规范

新任务目录{RUN}；冻结{len(names)}文件，{len(dependencies)}课程依赖逐字匹配成功A94。Windows原生、无WSL，框架54fc150ffc290f52aa024209ffb9a29d43856f6d，测试29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys0.63/ABC/OpenSTA3.1/Verilator5.020，原ASAP7 RVT TT/FakeRAM、latency10、clock2ns映射和原I/O/uncertainty/load不改。

对话汇报后只启动一次综合/STA。只有实测Fmax>300MHz且含SRAM面积≤36000μm²，才复用同一PPA、同manifest/config工具，构建一次原课程CPU并运行六项perf（各1000000周期、原分子/答案/几何平均）。PPA不达标则终止该批并记录，无CPU构建/性能仿真、无自动重试，不借用A94IPC。数值三目标改善确认后，采用前集中验证完整19正确性及M/GEN/恢复/MMIO/参数覆盖。

旧成功生成器/管理器/证明/报告、A94结果和测量源保持冻结。A99每一步源码审阅与准备脚本、五份源进度证据、全部依赖及本管理器哈希绑定。主E EU40源保持，无采用。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源manifest SHA256：{sha(RUN/'source_manifest.json')}
''',encoding='utf-8')
    assert effective['FAST_STORE_BATCH']==0 and effective['RS_ELASTIC_SKIP_CAPACITY']==1
    assert effective['LSQ_SAVED_IDENTITY_WORD_MASK']==effective['LSQ_SAVED_IDENTITY_BALANCED_MERGE']==1
    tool_paths=[Path(config[key]) for key in ['yosys','abc','sta','verilator','verilator_build_driver']]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan=dict(status='PREPARED_NOT_STARTED',candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT),pretest_report_sha256=sha(REPORT),reference_sha256=sha(RUN/'a94_reference.json'),
        host_sha256={str(p):sha(p) for p in HOST_FILES},tool_sha256={str(p):sha(p) for p in tool_paths},
        source_reviews_sha256=reviews,source_scripts_sha256=scripts,source_progress_sha256=progress,perf_cases=perf,correctness_cases=correctness,
        source_files=len(names),unchanged_course_dependency_files=len(dependencies),effective_structural_profile=effective,
        serial_tool_phases=True,native_cpu_builds_planned=1,new_synth_runs_planned=1,perf_max_cycles=1000000,
        performance_only_after_fmax_above300_and_total_area_at_most36000=True,
        correctness_started_with_characterization=False,full_correctness_and_relevant_coverage_required_before_adoption=True,
        main_active_manifest_sha256=expected_active,memory_at_preparation=memory_status(),
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal.update(status='A99_FROZEN_PPA_GATED_PRETEST_NOT_STARTED',prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,previous_goal_turn_classification=goal['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A95_A99_A94_CYCLE_FREQUENCY_NATIVE_PRETEST_FROZEN',
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
    goal.update(status='A99_PPA_GATED_CHARACTERIZATION_IN_PROGRESS',active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid,active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN/'dispatch_identity.json'),candidate_tests_started=True,
        pending_source_candidate_tests_started=True,candidate_metrics_belong_to=CANDIDATE.name,
        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        active_measurement_partial_ppa=None,measurement_last_observation=None,
        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_A99_PRETEST_REPORTED_PPA_GATED_NATIVE_SERIAL_DISPATCH')
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
            if not (timing['fmax_mhz']>300 and timing['area_um2']<=36000):
                record.update(status='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED',
                    timing_report_sha256=sha(RUN/'result/timing_only.json'),
                    performance_deferred_reason='Measured frequency/area gate did not pass; preserve source evidence without an unnecessary CPU build or performance simulation.',
                    fmax_mhz=timing['fmax_mhz'],area_um2=timing['area_um2'])
                write(RUN/'serial_phase_identity.json',record)
                print('DONE SERIAL timing; performance deferred by measured PPA gate',flush=True)
                return
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
