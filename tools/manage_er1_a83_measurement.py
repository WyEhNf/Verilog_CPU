"""Freeze and serialize one course-pinned Windows A76-A83 characterization."""
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
from manage_er1_a75_measurement import check as check_a75
from wait_frequency_directed_native import live

REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A75_tier3_20261006')
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A83_fast_store_identity_preselect')
RUN=Path('F:/CPU2026CourseRuns/ER1_A83_tier3_20261006')
REPORT=ROOT/'reports/ER1_A83_pretest_2026-10-06.md'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES=[ROOT/'tools/run_course_standard_windows.py',ROOT/'tools/prebuild_course_windows.py',
    ROOT/'tools/verilator_windows_time_zero.cpp',Path(__file__)]


def check():
    plan=read(RUN/'measurement_plan.json')
    for path,key in [(RUN/'source_manifest.json','source_manifest_sha256'),
        (RUN/'course_windows_config.json','config_sha256'),(REPORT,'pretest_report_sha256'),
        (CANDIDATE/'candidate.json','candidate_sha256'),(RUN/'a75_reference.json','reference_sha256')]:
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
    check_a75()
    dispatch=read(REFERENCE/'dispatch_identity.json')
    assert not live(dispatch['process_id'])
    original=read(REFERENCE/'result/result.json')
    assert original['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert original['official_perf_expected_results_passed']
    terminal=read(ROOT/'build/cpu2026/er1_a75_complete_result_20261006.json')['metrics']
    assert terminal['candidate']=='A75_branch_capture_phase_valid'
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
    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A75_branch_capture_phase_valid')
    for number in range(76,84):
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
    for proof_name in ['er1_a76_source_progress_20261006.json',
        'er1_a75_partial_ppa_a77_a78_source_progress_20261006.json',
        'er1_a75_complete_result_20261006.json',
        'er1_ready_store_source_opportunity_20261006.json']:
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
        'FAST_STORE_COMPLETE','FAST_STORE_ADDRESS_PREDECODE','FAST_STORE_IDENTITY_PRESELECT'):
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
    write(RUN/'a75_reference.json',reference)
    REPORT.write_text(f'''# ER1 A83：A76–A83 集中测量前汇报

目标保持频率严格大于300MHz、六项性能程序IPC几何平均至少1.1、含SRAM总面积至多36000μm²，并保留完整RV32IM、乱序执行、顺序提交、MMIO及参数化。

已测综合最优A55R2：IPC1.01714182、Fmax306.86245MHz、面积35480.53090μm²。最新完整测量A75：IPC{original['ipc']:.8f}、Fmax{original['fmax_mhz']:.5f}MHz、面积{original['area_um2']:.5f}μm²；六项性能答案通过，19正确性尚未跑，未采用。A75尚需IPC相对提高{(1.1/original['ipc']-1)*100:.4f}%，最小周期缩短超过{(original['minimum_period_ns']-1000/300)*1000:.3f}ps，面积余量{36000-original['area_um2']:.3f}μm²。

本批包含八项已经冻结的源码改动，没有逐改执行HDL/lint/形式/仿真/综合/STA/单元测试：

1. A76仅让队首加载通过原响应握手直接发布完成，并在真实上报握手后回收。保留已暂停报告身份、完整LSQ/ROB代数、错误/格式/前递结果；一般非队首仍走原保存路径。原加载唤醒已有旁路，因此收益是正式完成/队首释放通常少一拍，不声称又省一个唤醒边沿。新增原有旁路的17位保持身份，未增结果缓存或SRAM。
2. A77把原请求行的直接选择资格随原完整请求包传递，删除选中行后的第二次状态数组读。同一当前行GEN比较为代数恒等关系；已保存请求的真正GEN/liveness检查保留。
3. A78将逐字节最年轻存储前递改写为互斥并行掩码：最高已绕回物理行优先，否则最高普通行；未知存储阻塞、每字节独立赢家和暂停快照保留。
4. A79对已就绪、合法大小/立即数且自然对齐的普通RAM存储，在实际LSQ分配边沿标记ROB执行完成，最多一条每拍。原RS/ALU路径通常需再经两个边沿。只省执行阶段，真正写内存仍由原ROB队首授权、LSQ/缓存及原确认完成。MMIO和未就绪存储继续原路径。
5. A80在原PRF存储地址候选选择前判RAM和对齐标志，再用完全相同的WB/回退优先级选择3位结果，避免新的选完32位地址再判资格的串行依赖。原加法与地址选择不变。
6. A81对有效独立backend显式存储数据覆盖保留原ALU更新：非零覆盖不可走快完成。core两个调用点恒传0，因此不缩小课程覆盖。
7. A82用互斥并行最老请求掩码选择原完整叶包，保留全部无效时最右叶值、slot别名、地址/GEN/资格；默认及其他几何保留原请求树。
8. A83提前从保存D元数据选择第一条潜在存储身份，随后才施加原就绪、地址类别和实际分配条件；ROB32/BE2比较通道从64份减到32份，全部8GEN/valid/row及存储类型检查保留。第一条潜在存储未就绪时，后面的存储走原RS/ALU，可能较A82占用更多RS，这是明确面积取舍。参数0保留原最低就绪行选择和多通道比较。

可观收益的依据是两项真正减少执行/正式完成等待的结构机会，以及同一实测最慢链的三个串行选择改写；不是给小表达式修改逐次重测。A75五条最慢路径数据到达均3.282ns，共用LSQ地址→最老请求→二次状态读→直接请求→重叠→字节前递→寄存器：选择控制0.7442–1.0430ns、二次状态及可见选择1.110–1.548ns、重叠到前递2.138–2.937ns。A82、A77、A78分别针对这些依赖；区间不等于保证可省的时间。A79的两边沿和A76的一边沿也不等于每条程序必然减少同样周期，实际覆盖和头阻塞可能掩盖收益。累计IPC1.1、频率及面积仍完全未知。

除A76继承17位保持身份外，本批没有新增声明FF、SRAM、常规流水边沿、缓存容量、PRF/CDB端口。新增RAM资格、标签选择和全身份目标检查仍耗组合门，不能用无新增FF推定面积必然达标。保持FE4/BE2/整数2/CDB2、ROB32/PRF56/RS8/LSQ16、缓存/MSHR/预测表和ROB8位GEN。没有false-path、代数缩位、ISA缩减或错序存储旁路。

人工审查包括：当拍实际LSQ分配和原D整包入队、存储显式数据覆盖、SB/SH/SW大小/对齐/12位负数及32位绕回、原PRF存储/WB优先级、当前ROB valid/row/全GEN、复用/恢复/普通完成及分配退休优先级、暂停加载报告身份和前递结果、LSQ循环最老/最年轻优先级与无请求包。只对core合法解码元组保证源级一致推导，不声称任意相互矛盾的独立trace标志组合等价。未来完整验证还需覆盖width1/2/4、LSQ1/2/4/8/16/32、各选项0和回退模式、MMIO退出、全部M指令、缓存及恢复重用。

剩余方向已经按源码与已有数据评估：

- 扩ROB/PRF/RS/LSQ/cache/预测表：当前仅341μm²面积余量；现有旧A36三个摘要没有当前D就绪存储数、具体容量停顿因果或动态方向错误分布，不能把旧错误路径与重叠停顿相加当收益。暂不加入没有覆盖/成本依据的扩容。
- 部分D包入队：需要改变原原子资源分配及满替换信用规则，当前缺乏RS阻塞占比的同版本动态证据。此次先删除可证明无须RS执行的就绪存储需求。
- 更早解决分支或更激进加载完成：把PRF/WB/RS排名、比较、GEN检查、完成ready和恢复/取指串在同拍可能重新引入A69退化。A76仅选择已是年龄最老的队首，保留暂停报告。
- 精确RAS检查点、更大/新预测器：需要动态错误分布和更大状态预算；目前不声称已穷尽长期架构改造，也不缩小IPC1.1目标。
- 重复加普通取指请求链、RS当前唤醒或加载唤醒旁路：原设计已经有这些机制；没有遗漏的一拍可直接再省。原缓存仍是单LSQ请求/拍，hit响应合并已有实现。
- 更广泛任意潜在存储选择：A82为避免晚地址资格后标签选择复制了两个ROB身份通道。A83采用早身份单通道抑制新增面积与晚标签路径；先集中表征这一明确取舍，后续按新数据调整。

目前基于A75实测链和当前源码、能直接解释资格/身份/成本的这一批修改已完成；其余方向需要新同版本数据判断收益。故准备一次整批测量，而不是逐项测试。不能预先承诺三项达标。

只用Windows原生课程链：框架54fc150ffc290f52aa024209ffb9a29d43856f6d、测试29f980727f7d99a1842a58f34091c7579ba3fe85、Yosys0.63、OpenSTA3.1、Verilator5.020、课程ASAP7 RVT TT/FakeRAM、latency10。clock映射2ns、原STA约束与输出负载不变，SRAM计入面积，不用WSL。冻结{len(names)}文件，其中{len(dependencies)}课程依赖与已完成A75逐字节相同。

一次原生监督任务串行执行--timing-only，再按同一manifest/config/toolchain/报告--reuse-synth，只构建一次CPU并跑六项原性能程序各1000000周期；保留答案判定与IPC分子/几何平均规范。无并行大型前端、逐改测试、自动重试或结果覆盖。完整19正确性及M/恢复/参数专项仍须在数值明确改善、采用前集中验证。

报告生成时没有启动HDL或构建任务；先在对话汇报再调度。F盘测量快照保持冻结，运行时继续在独立候选研究IPC与面积。主E工作区EU40源码不改动。旧A75结果和管理器不覆盖不重启；PID查询超时不能用于重启任何原任务。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源码manifest SHA256：{sha(RUN/'source_manifest.json')}

measurement_plan.json绑定全部源码/工具/库/主机脚本、八份审阅、源进度记录和终态A75测量依据。
''',encoding='utf-8')
    tool_paths=[Path(config[key]) for key in ['yosys','abc','sta','verilator','verilator_build_driver']]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan=dict(status='PREPARED_NOT_STARTED',candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT),pretest_report_sha256=sha(REPORT),reference_sha256=sha(RUN/'a75_reference.json'),
        host_sha256={str(p):sha(p) for p in HOST_FILES},tool_sha256={str(p):sha(p) for p in tool_paths},
        source_reviews_sha256=reviews,source_progress_sha256=progress,perf_cases=perf,correctness_cases=correctness,
        source_files=len(names),unchanged_course_dependency_files=len(dependencies),effective_structural_profile=effective,
        serial_tool_phases=True,native_cpu_builds_planned=1,new_synth_runs_planned=1,perf_max_cycles=1000000,
        correctness_started_with_characterization=False,full_correctness_and_relevant_coverage_required_before_adoption=True,
        main_active_manifest_sha256=expected_active,memory_at_preparation=memory_status(),
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal.update(status='A83_FROZEN_SERIAL_PRETEST_NOT_STARTED',prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,previous_goal_turn_classification=goal['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A76_A83_OWNERSHIP_CRITICAL_PATH_AREA_TRADEOFF_NATIVE_PRETEST_FROZEN',
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
    goal.update(status='A83_SERIAL_CHARACTERIZATION_IN_PROGRESS',active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid,active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN/'dispatch_identity.json'),candidate_tests_started=True,
        pending_source_candidate_tests_started=True,candidate_metrics_belong_to=CANDIDATE.name,
        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_A83_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH')
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
