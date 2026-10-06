"""Freeze and serialize one course-pinned Windows A95-A105 coherent PPA-gated characterization."""
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
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A105_rob_recovery_row_live')
RUN=Path('F:/CPU2026CourseRuns/ER1_A105_tier3_20261006')
REPORT=ROOT/'reports/ER1_A105_pretest_2026-10-06.md'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES=[ROOT/'tools/run_course_standard_windows.py',ROOT/'tools/prebuild_course_windows.py',
    ROOT/'tools/verilator_windows_time_zero.cpp',ROOT/'tools/prepare_er1_a105_measurement_manager.py',Path(__file__)]

PREPARERS={
    95:'prepare_er1_store_class_compare.py',
    96:'prepare_er1_fast_store_batch.py',
    97:'prepare_er1_rs_elastic_skip_capacity.py',
    98:'prepare_er1_saved_identity_word_mask.py',
    99:'prepare_er1_balanced_saved_identity.py',
    100:'prepare_er1_held_report_identity_query.py',
    101:'prepare_er1_held_identity_row_query.py',
    102:'prepare_er1_report_recovery_prequalification.py',
    103:'prepare_er1_report_recovery_age_width.py',
    104:'prepare_er1_lsq_alloc_fire_distribution.py',
    105:'prepare_er1_rob_recovery_row_live.py',
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
    for number in range(95,106):
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
        'er1_a99_source_progress_20261006.json',
        'er1_a100_background_progress_20261006.json',
        'er1_a101_background_progress_20261006.json',
        'er1_minimal_closing_coverage_20261006.json',
        'er1_a99_ppa_result_20261006.json',
        'er1_a102_a104_source_progress_20261006.json',
        'er1_a105_source_progress_20261006.json']:
        p=ROOT/'build/cpu2026'/proof_name
        progress[str(p)]=sha(p)
    old_a99=Path('F:/CPU2026CourseRuns/ER1_A99_tier3_20261006')
    assert not live(read(old_a99/'dispatch_identity.json')['process_id'])
    assert read(old_a99/'serial_phase_identity.json')['status']=='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED'
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
        'LSQ_SAVED_IDENTITY_WORD_MASK','LSQ_SAVED_IDENTITY_BALANCED_MERGE','LSQ_HELD_LOAD_IDENTITY_QUERY',
        'LSQ_REPORT_RECOVERY_PREQUALIFY','LSQ_ALLOC_FIRE_DISTRIBUTE','ROB_RECOVERY_ROW_LIVE_QUALIFY'):
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
    REPORT.write_text(f'''# A105：恢复链起点/中段/末段结构批次，测量前汇报

目标严格>300MHz、六perf IPC几何平均≥1.1、含SRAM总面积≤36000μm²；完整RV32IM/OoO/顺序提交/MMIO与参数化保持。

## 原结果与新瓶颈

最新完整三指标参考A94：IPC{original['ipc']:.9f}、Fmax{original['fmax_mhz']:.6f}MHz、总面积{original['area_um2']:.6f}μm²，六perf答案通过、19正确性未跑。A99一次PPA为287.802136031478MHz、35915.75847799814μm²，原PID48248终态，门槛未过所以无CPU构建/IPC仿真。频率退化2.447297MHz、面积增加116.7858μm²；不把参考IPC借给A99或A105。当前周期还需缩短超过141.276ps，面积余量84.241522μm²。

新最慢五条均由branch_capture元数据开始，最长数据到达3.414ns：ROB恢复身份行选0.2935ns→recovery_preview0.6154ns→恢复分布0.7736ns→LSQ公开标签bit5（completiondata79）1.823ns→CDB选择2.202ns→PRF旁路2.499ns→分配资格2.982ns→LSQ行写3.253ns→FF。根段在选出9位currentGEN后比较；中段在晚报告选择后用公开tag算恢复资格；尾段分配事件驱动所有metadata/payload行。最长OAI21单门337ps/66负载/27.8877fF，晚分配NAND3约212ps/24.14fF。

## 已完成的整批源码

| 活跃修改 | 作用 |
|---|---|
| A103（修正A102类型后） | 保存/held与head完整候选分别前算原恢复kill资格，晚H/head只选bool；实际apply/producer-valid和全ROBGEN仍门控原target-live更新。 |
| A104 | 原真实LSQ alloc_fire通过功能控制树送到每组最多4行的metadata/payload匹配；公共分配/计数/票据、容量/槽位/GEN/写优先级保持。 |
| A105 | 当前ROB每行提前比较完整GEN与valid，再与槽位相等条件作bool OR；免去先读取9位valid/GEN再比较的串行层，原tagvalid/恢复选择/descriptor与状态保持。 |

A105在合法索引r下等价于tagvalid&&valid[r]&&fullGENmatch；非法索引无hit，两模式均false；tagvalid0两模式均false。因此不借用可达状态假设或删GEN/range。二叉1bitOR与query分发均实际映射/计价，非理想buffer。

A102准备时把age/branch_age误当signedINTEGER32；源声明复查发现实际是unsignedROB_SLOT_WIDTH regs，A103恢复原减法截断和unsigned比较。A102未测试/未采用，旧快照与错误审阅保持且被新证明明确替代。本批只测修正后末端A105。A100/A101第三held查询可选代码保留，课程flag0，保持A99两候选成本，不另测旧报告方向。FAST_STORE_BATCH仍0。A95/A97/A98/A99纯布尔/映射结构继承。

无新增声明FF、SRAM、流水边沿/端口容量；FE4/BE2/整数2/CDB2、ROB32/PRF56/RS8/LSQ16/BTB16、缓存/预测尺寸与完整8ROBGEN/9LSQGEN保持。预计二值输入下周期行为与A94一致，实际IPC仍重测。新增并行GEN比较有组合成本，移除9位读mux也有节省；84μm²余量很紧，不能以无FF或理论并行推定净面积/频率必过。

源级复查涵盖报告candidate/公共tag一致性、原unsigned年龄声明/减法/比较、完整GEN、apply/valid/held/head选择、非2幂/entries1/padding、实际alloc_fire控制等式/无creditloop，以及恢复/提交/数据/错误/状态。仅源码和哈希推导，无逐修改HDL/lint/形式/仿真/综合/STA/单元测试。

## 剩余方向与收益判断

三项针对同链root/middle/tail，可减少读取后的GEN比较、晚标签分类和高控制负载，直接覆盖多处数百ps区间，足以支持一次整批PPA判断；不能把各区间相加预测节省，新瓶颈和mapping可能抵消。再注册恢复/CDB/PRF会改变同周期唤醒/原子入队，IPC余量仅1.37%；扩窗口/大型预测器无本版瓶颈依据且面积紧；删GEN/取消/range不符合语义。CDB轮转/held仲裁进一步改写的净收益证据弱于已完成三项。当前没有额外能说明更明确可观净收益的同路径修改待完成，不宣称穷尽长期架构方案。

## 测量与最终验证范围

新目录{RUN}，冻结{len(names)}文件/其中{len(dependencies)}课程依赖与成功A94逐字一致。原生Windows、无WSL；框架54fc150ffc290f52aa024209ffb9a29d43856f6d，测试29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys0.63/ABC/OpenSTA3.1/Verilator5.020，原ASAP7RVT TT/FakeRAM、latency10、clock2ns和原I/O/uncertainty/load保持。

对话汇报后一次综合/STA；只有Fmax>300且总面积≤36000，才复用同manifest/config/PPA构建一次原课程CPU、运行六perf各1000000周期并核对答案/原动态指令数/GEOMEAN。PPA不通过则终态性能阶段跳过，无构建/IPC，不重启旧任务或覆盖旧证据。

三项实测全部达标后另存正确性证据，复用同CPU一次原19官方正确性（上限10000000周期）及4份既有冻结补充程序（上限200000周期、latency10），不重综合/构建/六perf。四程序解释器共8762指令覆盖45类RV32IM、全部8M、除零/溢出/自然对齐/RAM边界/分支/JALR；补齐官方19没有DIVU/MULH/MULHSU/MULHU的缺口。冻结字节/期望不是当前CPU通过证明，有限测试不等于完整ISA形式证明；关键参数化仍源级审阅。

准备时未开始新测试；11份95至105准备脚本/审阅、完整参考和A99终态/newpath/类型修正/closingcoverage等证据、原工具与本管理器均绑定哈希。主E EU40文件不变，无采用。目标未达成。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源manifest SHA256：{sha(RUN/'source_manifest.json')}
''',encoding='utf-8')
    assert effective['FAST_STORE_BATCH']==0 and effective['RS_ELASTIC_SKIP_CAPACITY']==1
    assert effective['LSQ_SAVED_IDENTITY_WORD_MASK']==effective['LSQ_SAVED_IDENTITY_BALANCED_MERGE']==1
    assert effective['LSQ_HELD_LOAD_IDENTITY_QUERY']==0
    assert effective['LSQ_REPORT_RECOVERY_PREQUALIFY']==effective['LSQ_ALLOC_FIRE_DISTRIBUTE']==effective['ROB_RECOVERY_ROW_LIVE_QUALIFY']==1
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
        intermediate_a102_signed_age_assumption_superseded_by_a103=True,
        closing_coverage_plan=goal['closing_coverage_plan'],closing_coverage_plan_sha256=goal['closing_coverage_plan_sha256'],
        correctness_started_with_characterization=False,full_correctness_and_relevant_coverage_required_before_adoption=True,
        main_active_manifest_sha256=expected_active,memory_at_preparation=memory_status(),
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal.update(status='A105_FROZEN_PPA_GATED_PRETEST_NOT_STARTED',prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,previous_goal_turn_classification=goal['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A103_A105_RECOVERY_ROOT_MIDDLE_TAIL_NATIVE_PRETEST_FROZEN',
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
    goal.update(status='A105_PPA_GATED_CHARACTERIZATION_IN_PROGRESS',active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid,active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN/'dispatch_identity.json'),candidate_tests_started=True,
        pending_source_candidate_tests_started=True,candidate_metrics_belong_to=CANDIDATE.name,
        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        active_measurement_partial_ppa=None,measurement_last_observation=None,
        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_A105_PRETEST_REPORTED_PPA_GATED_NATIVE_SERIAL_DISPATCH')
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
