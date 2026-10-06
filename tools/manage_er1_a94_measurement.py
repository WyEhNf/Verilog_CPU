"""Freeze and serialize one course-pinned Windows A84-A94 characterization."""
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
from manage_er1_a83_measurement import check as check_a83
from wait_frequency_directed_native import live

REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A83_tier3_20261006')
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A94_localparam_dependency_order')
RUN=Path('F:/CPU2026CourseRuns/ER1_A94_tier3_20261006')
REPORT=ROOT/'reports/ER1_A94_pretest_2026-10-06.md'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES=[ROOT/'tools/run_course_standard_windows.py',ROOT/'tools/prebuild_course_windows.py',
    ROOT/'tools/verilator_windows_time_zero.cpp',Path(__file__)]

PREPARERS={
    84:'prepare_er1_rob_store_prefix_admission.py',
    85:'prepare_er1_store_ack_source_query.py',
    86:'prepare_er1_head_store_ack_bypass.py',
    87:'prepare_er1_saved_store_operands_parallel_admission.py',
    88:'prepare_er1_saved_load_report_priority.py',
    89:'prepare_er1_load_report_identity_prequalification.py',
    90:'prepare_er1_lsq_allocation_slot_preselect.py',
    91:'prepare_er1_head_load_packet_preselect.py',
    92:'prepare_er1_load_response_source_query.py',
    93:'prepare_er1_fast_store_wb_data.py',
    94:'prepare_er1_localparam_dependency_order.py',
}



def check():
    plan=read(RUN/'measurement_plan.json')
    for path,key in [(RUN/'source_manifest.json','source_manifest_sha256'),
        (RUN/'course_windows_config.json','config_sha256'),(REPORT,'pretest_report_sha256'),
        (CANDIDATE/'candidate.json','candidate_sha256'),(RUN/'a83_reference.json','reference_sha256')]:
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
    check_a83()
    dispatch=read(REFERENCE/'dispatch_identity.json')
    assert not live(dispatch['process_id'])
    original=read(REFERENCE/'result/result.json')
    assert original['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert original['official_perf_expected_results_passed']
    terminal=read(ROOT/'build/cpu2026/er1_a83_complete_result_20261006.json')['metrics']
    assert terminal['candidate']=='A83_fast_store_identity_preselect'
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
    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A83_fast_store_identity_preselect')
    for number in range(84,95):
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
    for proof_name in ['er1_a83_complete_result_20261006.json',
        'er1_a84_background_progress_20261006.json',
        'er1_a85_a86_background_progress_20261006.json',
        'er1_a87_a90_source_progress_20261006.json',
        'er1_a91_a92_source_progress_20261006.json',
        'er1_a92_failed_a93_a94_progress_20261006.json']:
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
        'FAST_STORE_WB_DATA'):
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
    write(RUN/'a83_reference.json',reference)
    REPORT.write_text(f'''# ER1 A94：修正后累计方案测量前汇报

目标不变：频率严格>300MHz、六项课程性能程序IPC几何平均≥1.1、总面积（含SRAM）≤36000μm²；保留完整RV32IM、OoO、顺序提交、MMIO与参数化。

## 已有结果与失败边界

最新完整测量A83：IPC{original['ipc']:.8f}、Fmax{original['fmax_mhz']:.5f}MHz、含SRAM面积{original['area_um2']:.5f}μm²，六项性能答案通过，19项正确性未运行。还需IPC提高{(1.1/original['ipc']-1)*100:.4f}%，最小周期缩短超过{(original['minimum_period_ns']-1000/300)*1000:.3f}ps，面积余量{36000-original['area_um2']:.3f}μm²。已测频率/面积达标且IPC最高仍A55R2：1.01714182、306.86245MHz、35480.53090μm²。

原A92监督PID97984已终止，SERIAL_TIMING_FAILED，timing返回1：课程Yosys无法确定位宽参数HEAD_LOAD_PACKET_ACTIVE，因为新常量被更早的宽度表达式引用。没有PPA/IPC，不能把前端失败当频率下降。失败证据、旧源码、管理器、准备/审阅脚本和结果日志保持冻结。A94是独立修正后新源码、新目录、新监督任务；成功A83仍作工具/依赖/指标参考。

## 整批已完成的修改

| 候选 | 改动与用途 |
|---|---|
| A84 | 原退休前缀之后的普通存储授权与前缀退休重叠；存储本身仍等原注册sent，MMIO/error/更老阻塞和单授权口保留。 |
| A85 | 缓存/MMIO ACK候选身份各自提前作完整LSQ GEN/valid/row/sent/wait核对，真实事件保持缓存优先级。 |
| A86 | 实际已提交队首存储合法ACK可在原ready边沿正式上报/释放；暂停捕获与其他行原路径保留，省一条ACK捕获后等待机会。 |
| A87 | 快存储基于保存PRF就绪/地址类别，容量普通/减一项提前计算，晚资格只选bool；保留原真实分配和D替换信用。 |
| A88 | held/head-fast优先级不变，普通加载排序只依赖保存完成行，消除新响应对未使用全局wrap/prefix的依赖。 |
| A89 | 保存/held与队首完整ROB身份并行核对当前valid/全部8bit GEN，晚选择只选资格，恢复/cancel/实际事件不变。 |
| A90 | 保存D稀疏内存需求与tail提前确定LSQ分配槽；整包admit证明任何实际fire时计划等于原fire，原fire门控原状态写入。 |
| A91 | 保存/held完整报告包和query、队首元数据提前读取选择；实际返回选准备包，原格式器值/error、valid、hold及回收不变。 |
| A92 | 缓存保存/命中旁路完整LSQ候选票据并行比较，真实源有效位门控匹配；公开响应优先级/数据/错误/状态原样。 |
| A93 | 数据ready由原保存ready且无WB拓宽为保存ready或合法匹配WB；基址仍须保存ready且无WB，因此不把WB数据值放回地址加法/类别链。 |
| A94 | 移动原完整常量声明块到宽度/active引用之前，修正A91的HEAD_LOAD_PACKET_ACTIVE与A87的PARALLEL_STORE_ADDRESS前向依赖。纯声明顺序修复，无额外性能收益声明。 |

A93保留原快存储资格（同输入R&&!W蕴含R||W），并覆盖数据当前WB就绪机会。actual LSQ数据继续使用原PRF最高WB优先级；explicit-data非零、MMIO或基址未就绪仍走原RS，完整GEN与顺序存储副作用不变。不能据此保证聚合IPC。

## 可观收益依据

A83最慢五条4.032/4.030ns同链：内存response-ID→cache旁路→公开LSQ票据0.7946ns→匹配/wrap1.260ns→报告ROB query1.597ns→live读取1.785ns→完成选择2.091ns→PRF写回值2.292ns→WB存储地址类别2.755ns→D入队3.319ns→分配槽选择3.626ns→GEN写控制3.830ns→FF4.032ns。

这批同时移走新响应进入普通排序、先选票据再比较、先选报告再核对live、WB值进入快存储地址类别、实际admit后再算分配槽等多个串行依赖，目标是让晚事件只选择提前准备的资格并门控原写入。A84/A86另有真实存储等待机会，A93拓宽数据WB快路径。预计值得一次整批表征；各区间不能直接相加算节省，映射/Fanout/新瓶颈与实际工作负载收益仍未知。

无新增声明FF/SRAM/常规流水边沿/端口容量；FE4/BE2/整数2/CDB2、ROB32/PRF56/RS8/LSQ16、缓存/MSHR/预测表、8ROBGEN/9LSQGEN保持。双身份查询/比较、完整候选包和队首读可能增加组合面积，不以无FF推定面积达标。无false-path、缩GEN、删ISA或越序内存副作用。

源级检查覆盖整包admit/替换信用、容量代数/单快存储、所有WB优先级、地址carry/sign/对齐/RAM界、完整身份/held/head/saved报告与所有包/query位域、ACK暂停/错误、缓存来源优先级、稀疏分配及真实fire、恢复/顺序提交、修正后常量依赖顺序。仅源级推导与哈希冻结；没有逐修改HDL/lint/形式/仿真/综合/STA/单元测试，尚未确认A94编译通过或完整正确性。私有查询/计划输入由core原信号生成，必须与真实包/整包分配一致。

## 其他方向及本次范围

原RS/加载唤醒、取指请求、cache命中同发机制已启用，没有直接待删的新等待边沿。扩容PRF/RS/ROB/缓存或增加大型预测器缺同版本瓶颈与成本依据，当前余量仅352.966μm²；部分D入队、任意非队首正式完成/授权和再次拆流水会修改暂停/提交协议，目前没有新证据支持。cache格式/前递/扇出可能成为下一瓶颈，但需这批映射结果判断。

当前有证据支持的同链修改已落盘，声明顺序修复已检查，没有额外能直接说明可观收益的同链改动待完成。这不代表穷尽长期架构方案或降低目标。运行时继续独立分析新的IPC/面积机会，不改测量快照。

## 测量规范

Windows原生，禁止WSL：框架54fc150ffc290f52aa024209ffb9a29d43856f6d、测试29f980727f7d99a1842a58f34091c7579ba3fe85、Yosys0.63/ABC/OpenSTA3.1/Verilator5.020、课程ASAP7 RVT TT/FakeRAM、latency10。映射clock2ns、原I/O/uncertainty/负载保持，报告真实Fmax和含SRAM总面积。冻结{len(names)}文件，其中{len(dependencies)}课程依赖与成功A83逐字相同。

一次新监督任务：串行--timing-only，然后依据同一manifest/config/toolchain/report --reuse-synth，仅一次综合/STA及一次CPU构建；六项原perf各1000000周期、核对答案、动态指令分子和GEOMEAN。完整19正确性以及M/恢复/GEN/MMIO/参数覆盖在明确改善并采用前集中验证。无并行大型前端、无自动重试、无重启旧PID/覆盖旧结果。主E EU40文件保持快照，运行在F盘。

本报告生成时尚未启动新HDL或构建，先在对话汇报后调度。measurement_plan绑定11份准备脚本/源码审阅、A83参考、A92失败/A93/A94进度证据、主机工具/库/脚本与完整源。候选之间不互借指标。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源manifest SHA256：{sha(RUN/'source_manifest.json')}
''',encoding='utf-8')
    tool_paths=[Path(config[key]) for key in ['yosys','abc','sta','verilator','verilator_build_driver']]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan=dict(status='PREPARED_NOT_STARTED',candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT),pretest_report_sha256=sha(REPORT),reference_sha256=sha(RUN/'a83_reference.json'),
        host_sha256={str(p):sha(p) for p in HOST_FILES},tool_sha256={str(p):sha(p) for p in tool_paths},
        source_reviews_sha256=reviews,source_scripts_sha256=scripts,source_progress_sha256=progress,perf_cases=perf,correctness_cases=correctness,
        source_files=len(names),unchanged_course_dependency_files=len(dependencies),effective_structural_profile=effective,
        serial_tool_phases=True,native_cpu_builds_planned=1,new_synth_runs_planned=1,perf_max_cycles=1000000,
        correctness_started_with_characterization=False,full_correctness_and_relevant_coverage_required_before_adoption=True,
        main_active_manifest_sha256=expected_active,memory_at_preparation=memory_status(),
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal.update(status='A94_FROZEN_SERIAL_PRETEST_NOT_STARTED',prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,previous_goal_turn_classification=goal['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A84_A94_CORRECTED_CUMULATIVE_NATIVE_PRETEST_FROZEN',
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
    goal.update(status='A94_SERIAL_CHARACTERIZATION_IN_PROGRESS',active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid,active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN/'dispatch_identity.json'),candidate_tests_started=True,
        pending_source_candidate_tests_started=True,candidate_metrics_belong_to=CANDIDATE.name,
        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_A94_CORRECTED_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH')
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
