"""Freeze the reviewed A42-A55 batch and launch one native course characterization."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a41_measurement import check as check_a41
from wait_frequency_directed_native import live

BASE = Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A55_predictor_bank_local_prefix_history')
RUN = Path('F:/CPU2026CourseRuns/ER1_A55_tier3_20261005')
REPORT = ROOT / 'reports/ER1_A55_pretest_2026-10-05.md'
GOAL = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES = [ROOT / 'tools/run_course_standard_windows.py', ROOT / 'tools/prebuild_course_windows.py',
              ROOT / 'tools/verilator_windows_time_zero.cpp', Path(__file__)]


def check():
    plan = read(RUN / 'measurement_plan.json')
    for path, key in [(RUN / 'source_manifest.json', 'source_manifest_sha256'),
                      (RUN / 'course_windows_config.json', 'config_sha256'),
                      (REPORT, 'pretest_report_sha256'), (CANDIDATE / 'candidate.json', 'candidate_sha256')]:
        assert sha(path) == plan[key], path
    for group in ('host_sha256', 'tool_sha256', 'source_reviews_sha256', 'source_progress_sha256'):
        for path, digest in plan[group].items():
            assert sha(path) == digest, path
    for name, digest in read(RUN / 'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN / 'source' / name) == digest, name
    config = read(RUN / 'course_windows_config.json')
    assert config['environment'] == 'WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert config['latency'] == 10
    assert config['framework_revision'] == '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    assert sha(RUN / 'a41_reference.json') == plan['a41_reference_sha256']
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    check_a41()
    old = read(BASE / 'result/result.json')
    goal = read(GOAL)
    assert goal['current_source_candidate'] == CANDIDATE.name
    assert not goal['candidate_tests_started'] and goal['active_measurement_candidate'] is None
    assert not live(read(BASE / 'dispatch_identity.json')['process_id'])
    assert old['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert old['official_perf_expected_results_passed'] and old['official_correctness_suite_not_run']
    candidate = read(CANDIDATE / 'candidate.json')
    assert not candidate['tests_started'] and not candidate['adopted']
    assert sha(CANDIDATE / 'candidate.json') == goal['pending_source_candidate_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE / name) == digest, name
    reviews = {}
    previous = Path('F:/CPU2026Candidates/tier3_er1_20261005/A41_lsq_two_prefix_reclaim')
    for number in range(42, 56):
        review_path = CANDIDATE.parent / f'A{number}_source_review.json'
        review = read(review_path)
        source = Path(review['candidate'])
        record = read(source / 'candidate.json')
        assert sha(source / 'candidate.json') == review['candidate_sha256']
        assert Path(record['parent_candidate']).resolve() == previous.resolve()
        assert sha(previous / 'candidate.json') == record['parent_candidate_sha256']
        assert not record['tests_started'] and not record['adopted']
        for name, digest in record['source_sha256'].items():
            assert sha(source / name) == digest, (source.name, name)
        reviews[str(review_path)] = sha(review_path)
        previous = source
    assert previous.resolve() == CANDIDATE.resolve()
    progress = {goal['last_background_progress']: goal['last_background_progress_sha256'],
                goal['last_source_progress_proof']: goal['last_source_progress_proof_sha256']}
    for path, digest in progress.items():
        assert sha(path) == digest
    active = read(ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json')
    for name, digest in active['source_sha256'].items():
        assert sha(ROOT / name) == digest, name
    top = (CANDIDATE / 'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b' + key + r'\s*=\s*(\d+)', top)
        assert match and int(match[1]) == value, key
    effective = {}
    for key in ('FE_WIDTH', 'BE_WIDTH', 'INT_ISSUE_WIDTH', 'CDB_WIDTH', 'SERIAL_BACKEND',
                'PREDICTOR_HISTORY_BITS', 'PREDICTOR_COMPACT_BTB_ENTRIES', 'DCACHE_WAYS',
                'DCACHE_MSHRS', 'ICACHE_MSHRS', 'ROB_ENTRIES', 'PHYS_REGS', 'RS_ENTRIES', 'LSQ_ENTRIES'):
        match = re.search(r'\b' + key + r'\s*=\s*(\d+)', top)
        assert match, key
        effective[key] = int(match[1])
    assert effective['FE_WIDTH'] == 4 and effective['SERIAL_BACKEND'] == 0
    assert effective['PREDICTOR_COMPACT_BTB_ENTRIES'] == 16
    # The cumulative candidate profile retains historical keys. Record current
    # effective constants separately rather than relabeling old frozen records.
    effective.update(gshare_entries=256, bimodal_entries=256, chooser_entries=64,
                     btb_entries=16, predictor_banks=4, predictor_metadata_width=16)
    parent = read(BASE / 'source_manifest.json')
    names = sorted(set(parent['snapshot_sha256']) | set(candidate['source_sha256']))
    for name in names:
        source = CANDIDATE / name if name in candidate['source_sha256'] else BASE / 'source' / name
        assert source.exists(), name
        destination = RUN / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    source = RUN / 'source'
    dependencies = [name for name in names if name.startswith('.deps/')]
    for name in dependencies:
        assert sha(source / name) == parent['snapshot_sha256'][name], name
    tests = source / '.deps/RISC-V-CPU-2026/testcases'
    perf = sorted(p.name for p in tests.glob('perf_*') if p.is_dir())
    correctness = sorted(p.name for p in tests.glob('correctness_*') if p.is_dir())
    assert len(perf) == 6 and len(correctness) == 19
    reference = dict(run=str(BASE), source_manifest_sha256=sha(BASE / 'source_manifest.json'),
        result_sha256=sha(BASE / 'result/result.json'), ipc_report_sha256=sha(BASE / 'result/ipc.json'),
        ppa_report_sha256=sha(BASE / 'result/synth/opt/report.json'),
        ipc=old['ipc'], fmax_mhz=old['fmax_mhz'], area_um2=old['area_um2'],
        full_correctness_not_run=True, official_perf_expected_results_passed=True)
    write(RUN / 'a41_reference.json', reference)
    frozen = dict(format='er1-tier3-native-source-v1', status='FROZEN_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(source),
        reference_manifest_sha256=sha(BASE / 'source_manifest.json'), candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(CANDIDATE / 'candidate.json'),
        framework_commit=candidate['framework_commit'], testcases_commit=candidate['testcases_commit'],
        parameter_overrides=candidate['parameter_overrides'], effective_structural_profile=effective,
        materialized_top_defaults=True, snapshot_sha256={name: sha(source / name) for name in names},
        tests_started=False)
    write(RUN / 'source_manifest.json', frozen)
    config = read(BASE / 'course_windows_config.json')
    config.update(source=str(source), source_manifest=str(RUN / 'source_manifest.json'),
        out=str(RUN / 'result'), native_build_path=str(RUN / 'native_build'), native_ipc_path=str(RUN / 'native_ipc'))
    write(RUN / 'course_windows_config.json', config)
    REPORT.write_text(f'''# ER1 A55 累计方案测试前汇报

目标保持频率>300MHz、IPC≥1.1、含 SRAM 总面积≤36000μm²；保留完整 RV32IM、OoO、顺序提交、MMIO 和参数化要求。上一轮完成 A53/A54/A55 与925条官方静态指令的镜像匹配，属于实际进展；本轮完成剩余结构选项审查及同一源码/工具/测试身份冻结。

## 本次测量依据与范围

已测 A41：IPC {old['ipc']:.10f}、频率 {old['fmax_mhz']:.8f}MHz、总面积 {old['area_um2']:.6f}μm²，其中 SRAM {old['area']['sram_area_um2']:.6f}μm²。6项性能答案通过，完整正确性尚未运行。达到 IPC1.1仍需约{(1.1/old['ipc']-1)*100:.5f}%相对提升，面积余量仅{36000-old['area_um2']:.6f}μm²。

累计 A42–A55 改动包含四个互相配合的方向：

|方向|已落地行为|可观结构收益的源码依据|
|---|---|---|
|缓存并行|单路 SRAM 写入时另一物理路继续查询；命中直接响应与等待者/补行回复交叠。|去掉互不冲突操作的全局阻塞；保留每路数据有效性、同拍响应所有权和背压捕获。|
|加载选择|已有注册地址的加载可越过空选择寄存器；背压时仍锁存完整票据与转发快照。|在空选择且已就绪的加载上删掉一次必需的选择捕获等待拍；关闭 live AGU→缓存数据长路径。|
|恢复并行|恢复预览和应用周期允许严格较老、ROB代际仍有效的指令发射。|删掉应用周期全局发射禁令；同一 RS 行在杀除与已接收发射集合中只释放一次。|
|预测及前端|混合方向表、逐指令历史、局部PC、并行束终止/容量控制、提前目标、窄表读取、PC进位分离、银行固定字读取/历史掩码。|平行查询方向表；避免束长先编码再译码、方向→宽目标门控、PC低位→全行指令选择和偏移→高位加法依赖；窄方向表少1152个源码保留反相器。|

这些是已确认的源码依赖或必要等待拍删除，不是已测 IPC/Fmax 增益。A36 的三程序动态记录存在分支恢复、前端空泡和缓存请求活动；计数互相重叠且包含错路径，不能相加成预计收益。静态官方镜像中5个程序存在同一行多条件分支，6个均无M指令；这支持优先方向，不证明动态准确率提升。

## 面积与时序预算

A42新增2个数据来源/有效状态位；A45新增混合表896位、减小BTB节省640位，原有元数据高2位变为有效状态约104位。合计有效状态净增加估算362位，其他本批改动不新增寄存器、SRAM或流水边界。按此前DFF面积0.2916μm²计算，仅这部分约105.5592μm²。窄读取删除1152个源码反相器，对应旧映射字面组件50.38848μm²。这两项不能当作实际总面积加减结果：裁剪、重映射和新组合逻辑均未知。

A41已映射最长区域位于前端PC/方向表/链式请求，数据到达3.19ns。本批针对这一实际区域。新增的注册加载地址→阻塞判断/最老选择/转发→缓存控制，恢复ROB代际查询→较老发射资格，以及opcode→历史计数→gshare查询仍需检查时序。保持300MHz以上是硬条件，不使用历史A41频率给新候选背书。

## 剩余结构选项审查

|选项|当前结论与依据|
|---|---|
|增加流水级|已有测量只剩8MHz频率余量，但IPC仍不足；本批先拆组合依赖，额外边界会增加状态及依赖/恢复延迟，暂缺净IPC收益依据。|
|扩大缓存/MSHR/发射口/预测表|现有缓存已包含合并请求、下一行预取与需求提升；动态miss包含合并，不能当作独立外存事务。扩大资源会增加面积，当前没有可靠独立瓶颈计数支持。|
|加速或删除M单元|静态6perf无M指令，加速M执行不能直接改善这些程序；完整RV32IM要求保留实现。|
|前缀方向串行预测|能形成逐条历史，但会串联方向表访问。本批改用接受前缀此前条件方向恒为0这一事实并行形成历史。|
|恢复与重命名/分配同拍|当前 d_admit/d_replace_credit 受 branch_pending 抑制，恢复写 RAT/free状态/ROB尾部且 RS/LSQ 执行代际杀除。需要统一新旧分配、代际和释放所有权；现有证据不足以量化额外状态与组合预算，保留为后续架构选项。|
|更早ALU结果直接重定向|当前已经在branch_capture_write做早重定向。继续向前会连接ALU数据路径与ROB代际授权、前端请求；尚无新路径时序预算依据。|

本轮没有更多可凭已有证据直接落地并解释面积/时序代价的结构方案，先统一测量累计改动以确定下一瓶颈；以上后续选项没有被永久放弃。

## 冻结身份及执行安排

Windows原生；课程框架54fc150ffc290f52aa024209ffb9a29d43856f6d、课程测试29f980727f7d99a1842a58f34091c7579ba3fe85。Yosys0.63、OpenSTA3.1、Verilator5.020、课程ASAP7 RVT TT和FakeRAM计价/时序模型保持同一锁定身份。latency=10；SRAM计入总面积。不使用WSL。

冻结{len(names)}个文件，其中{len(dependencies)}个课程依赖文件与A41逐字节一致；当前FE4/BE2/整数发射2/CDB2、ROB32/PRF56/RS8/LSQ16、BTB16、gshare256/bimodal256/chooser64。旧累计profile中残留的BTB64/32历史键不代表当前配置，本次manifest另记有效结构常量。

只启动一次标准课程综合/STA/总面积测量、一次原生CPU构建和6个perf程序（各保持官方1000000周期预算并检查答案），不附加19程序回归或单元测试。若同一源码的数值接近/达到目标，再集中运行必要的完整正确性、完整M、恢复代际/恰好一次发射、缓存并发、加载转发/背压及参数回退覆盖，最终采用前必须完成，不能凭6perf或源码推导宣称全功能通过。

运行期间不改变这份冻结源码，继续独立优化。遇到超时观察继续查询同一原始进程，不因为观察超时重新构建或重启。报告生成时尚未执行HDL/仿真/综合/STA；对话汇报后才调度。

候选SHA256：{sha(CANDIDATE / 'candidate.json')}

冻结源码manifest SHA256：{sha(RUN / 'source_manifest.json')}

源码：[A55候选](F:/CPU2026Candidates/tier3_er1_20261005/A55_predictor_bank_local_prefix_history/candidate.json)。同一框架/程序/库/工具/主机脚本哈希、A42–A55审阅证据与A41原结果身份均由 measurement_plan.json 绑定。主E工作区EU RTL没有改变。
''', encoding='utf-8')
    tool_paths = [Path(config[key]) for key in ('yosys', 'abc', 'sta', 'verilator', 'verilator_build_driver')]
    tool_paths.append(Path(config['tools_root']) / 'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan = dict(status='PREPARED_NOT_STARTED', candidate=str(CANDIDATE), candidate_sha256=sha(CANDIDATE / 'candidate.json'),
        source_manifest_sha256=sha(RUN / 'source_manifest.json'), config_sha256=sha(RUN / 'course_windows_config.json'),
        pretest_report=str(REPORT), pretest_report_sha256=sha(REPORT), host_sha256={str(p): sha(p) for p in HOST_FILES},
        tool_sha256={str(p): sha(p) for p in tool_paths}, source_reviews_sha256=reviews, source_progress_sha256=progress,
        a41_reference_sha256=sha(RUN / 'a41_reference.json'), perf_cases=perf, correctness_cases=correctness,
        source_files=len(names), unchanged_course_dependency_files=len(dependencies), effective_structural_profile=effective,
        perf_max_cycles=1000000, native_cpu_builds_planned=1, new_synth_runs_planned=1,
        correctness_started_with_characterization=False, full_correctness_and_relevant_m_coverage_required_before_adoption=True,
        target=dict(ipc=1.1, total_area_um2=36000, strict_minimum_fmax_mhz=300))
    write(RUN / 'measurement_plan.json', plan)
    previous_classification = goal['last_goal_turn_classification']
    goal.update(status='A55_FROZEN_PRETEST_NOT_STARTED', current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=plan['candidate_sha256'], prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'], candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'], candidate_tests_started=False,
        pending_source_candidate_tests_started=False,
        previous_goal_turn_classification=previous_classification,
        last_goal_turn_classification='PROGRESS_A55_CUMULATIVE_ARCHITECTURE_AUDIT_FROZEN_PRETEST',
        next_work=['Report the reviewed cumulative A42-A55 batch before one native course characterization.',
                   'Continue independent optimization while observing the original dispatched PID without restarting.',
                   'Require same-source strict metrics and relevant full RV32IM/recovery/cache/parameter coverage before adoption.'],
        goal_complete=False, candidates_adopted=False)
    write(GOAL, goal)
    check()
    print({key: plan[key] for key in ('status', 'candidate', 'source_files', 'unchanged_course_dependency_files',
        'pretest_report', 'pretest_report_sha256', 'source_manifest_sha256', 'correctness_started_with_characterization')})


def start():
    plan = check()
    assert plan['status'] == 'PREPARED_NOT_STARTED'
    assert not (RUN / 'dispatch_identity.json').exists() and not (RUN / 'result').exists()
    command = [sys.executable, '-u', str(ROOT / 'tools/run_course_standard_windows.py'),
               '--config', str(RUN / 'course_windows_config.json')]
    with (RUN / 'driver_stdout.log').open('w', encoding='utf-8') as stdout, \
         (RUN / 'driver_stderr.log').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    alive = process.poll() is None
    dispatch = dict(status='BACKGROUND_DISPATCHED', process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(), command=command,
        source_manifest_sha256=plan['source_manifest_sha256'], pretest_report_sha256=plan['pretest_report_sha256'],
        host_sha256=plan['host_sha256'], initial_process_alive=alive, environment='WINDOWS_NATIVE',
        full_correctness_started=False)
    write(RUN / 'dispatch_identity.json', dispatch)
    goal = read(GOAL)
    goal.update(status='A55_IMMUTABLE_CHARACTERIZATION_IN_PROGRESS', active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN), measurement_process_id=process.pid, measurement_process_alive=alive,
        active_measurement_process_ids=[process.pid], active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN / 'dispatch_identity.json'),
        pending_source_candidate_tests_started=True, candidate_tests_started=True,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None, candidate_metrics_belong_to=CANDIDATE.name,
        last_goal_turn_classification='PROGRESS_A55_BATCH_AUDIT_PRETEST_REPORTED_NATIVE_DISPATCH')
    write(GOAL, goal)
    print({key: dispatch[key] for key in ('status', 'process_id', 'started_at', 'initial_process_alive',
                                        'environment', 'source_manifest_sha256', 'full_correctness_started')})


def observe():
    check()
    dispatch = read(RUN / 'dispatch_identity.json')
    result = optional(RUN / 'result/result.json')
    metrics = ({key: result.get(key) for key in ('status', 'ipc', 'area_um2', 'fmax_mhz',
        'official_perf_expected_results_passed', 'official_correctness_suite_passed',
        'thread_objective_numeric_requirements_met')} if result else None)
    alive = live(dispatch['process_id'])
    failure = optional(RUN / 'result/failure.json')
    observation = dict(run=str(RUN), process_id=dispatch['process_id'], process_alive=alive,
        observed_at=datetime.now(timezone.utc).isoformat(), result=metrics,
        failure_summary=str(failure)[:1200] if failure else None)
    for name in ('driver_stdout.log', 'driver_stderr.log'):
        path = RUN / name
        observation[name] = [line[:300] for line in path.read_text(errors='replace').splitlines()[-5:]] if path.exists() else []
    goal = read(GOAL)
    if goal.get('active_measurement_source_manifest_sha256') == dispatch['source_manifest_sha256']:
        goal.update(measurement_process_alive=alive, measurement_last_observed_at=observation['observed_at'],
                    measurement_last_observation=observation)
        write(GOAL, goal)
    print(observation)


if __name__ == '__main__':
    assert os.name == 'nt', 'Native Windows only'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'observe'))
    args = parser.parse_args()
    {'prepare': prepare, 'start': start, 'observe': observe}[args.action]()
