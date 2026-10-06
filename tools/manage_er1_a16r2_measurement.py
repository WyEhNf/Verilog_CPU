"""Freeze, report, dispatch once, or observe the unified native A16R2 batch."""
import argparse
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from wait_frequency_directed_native import live

BASE = Path('F:/CPU2026CourseRuns/ER1_native_identifier_compat_20261005')
A8 = Path('F:/CPU2026CourseRuns/ER1_A8_tier3_20261005')
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A16R2_shared_barrel_elastic_dispatch')
RUN = Path('F:/CPU2026CourseRuns/ER1_A16R2_tier3_20261005')
REPORT = ROOT/'reports/ER1_A16R2_pretest_2026-10-05.md'
GOAL_RECORD = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CORRECTNESS_MAX_CYCLES = 10000000
HOST_FILES = [ROOT/'tools/run_course_standard_windows.py', ROOT/'tools/prebuild_course_windows.py',
              ROOT/'tools/verilator_windows_time_zero.cpp', Path(__file__)]


def check():
    plan = read(RUN/'measurement_plan.json')
    for path, key in [(RUN/'source_manifest.json','source_manifest_sha256'),
                      (RUN/'course_windows_config.json','config_sha256'),
                      (REPORT,'pretest_report_sha256'),
                      (CANDIDATE/'candidate.json','candidate_sha256')]:
        assert sha(path) == plan[key], path
    for path, digest in plan['host_sha256'].items():
        assert sha(path) == digest, path
    for name, digest in read(RUN/'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN/'source'/name) == digest, name
    config = read(RUN/'course_windows_config.json')
    assert config['environment'] == 'WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert config['latency'] == 10
    for path, digest in plan['tool_sha256'].items():
        assert sha(path) == digest, path
    assert plan['correctness_max_cycles'] == CORRECTNESS_MAX_CYCLES
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    parent = read(BASE/'source_manifest.json')
    candidate = read(CANDIDATE/'candidate.json')
    assert candidate['tests_started'] is False and candidate['adopted'] is False
    for name, digest in parent['snapshot_sha256'].items():
        assert sha(BASE/'source'/name) == digest, name
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    active = read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name, digest in active['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)', top)
        assert match and int(match[1]) == value, key
    names = sorted(set(parent['snapshot_sha256']) | set(candidate['source_sha256']))
    for name in names:
        src = CANDIDATE/name if name in candidate['source_sha256'] else BASE/'source'/name
        dest = RUN/'source'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    source = RUN/'source'
    framework = source/'.deps/RISC-V-CPU-2026'
    perf = sorted(p.name for p in (framework/'testcases').glob('perf_*') if p.is_dir())
    correctness = sorted(p.name for p in (framework/'testcases').glob('correctness_*') if p.is_dir())
    assert len(perf) == 6 and len(correctness) == 19
    untouched = [name for name in names if name.startswith('.deps/')]
    for name in untouched:
        assert sha(source/name) == parent['snapshot_sha256'][name], name
    assert '--max-cycles' in (framework/'scripts/testcase.py').read_text(encoding='utf-8')
    # Audit and retain the terminal original default-budget failure separately.
    a8_dispatch = read(A8/'dispatch_identity.json')
    assert not live(a8_dispatch['process_id'])
    a8_failure = read(A8/'result/failure.json')
    log = (A8/'result/correctness.log').read_text(encoding='utf-8')
    cases = [dict(name=m[1], result=m[2]) for m in re.finditer(
        r'^\[(correctness_[^\]]+)\]\s*\n(PASS[^\n]*|FAIL:[^\n]*)', log, re.M)]
    assert sorted(row['name'] for row in cases) == correctness
    passed = sum(row['result'].startswith('PASS') for row in cases)
    assert passed == 16 and len(cases)-passed == 3 and 'Results: 16 passed, 3 failed' in log
    ipc = read(A8/'result/ipc.json')
    ppa = read(A8/'result/synth/opt/report.json')
    assert len(ipc['results']) == 6 and ipc['status'] == 'COMPLETE'
    assert math.isclose(math.exp(sum(math.log(r['instructions']/r['cycles']) for r in ipc['results'])/6),
                        ipc['geomean_ipc'], rel_tol=1e-12)
    a8_terminal = dict(status='PERF_PPA_COMPLETE_FULL_CORRECTNESS_FAILED',
        run=str(A8), process_id=a8_dispatch['process_id'], process_alive=False,
        ipc=ipc['geomean_ipc'], fmax_mhz=ppa['timing']['estimated_fmax_mhz'],
        area_um2=ppa['area']['area_um2'], correctness_passed=16, correctness_failed=3,
        correctness_max_cycles=1000000, correctness=cases, failure=a8_failure,
        artifact_sha256={name:sha(A8/name) for name in ('source_manifest.json','result/ipc.json',
            'result/synth/opt/report.json','result/correctness.log','result/failure.json')})
    write(RUN/'a8_terminal_reference.json', a8_terminal)
    frozen = dict(format='er1-tier3-native-source-v1', status='FROZEN_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(source),
        reference_manifest_sha256=sha(BASE/'source_manifest.json'), candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        framework_commit=candidate['framework_commit'], testcases_commit=candidate['testcases_commit'],
        parameter_overrides=candidate['parameter_overrides'], materialized_top_defaults=True,
        snapshot_sha256={name:sha(source/name) for name in names}, tests_started=False)
    write(RUN/'source_manifest.json', frozen)
    config = read(BASE/'course_windows_config.json')
    config.update(source=str(source), source_manifest=str(RUN/'source_manifest.json'),
        out=str(RUN/'result'), native_build_path=str(RUN/'native_build'), native_ipc_path=str(RUN/'native_ipc'))
    write(RUN/'course_windows_config.json', config)
    REPORT.write_text('''# ER1 A16R2 统一测量前汇报

目标：同一冻结版本 Fmax>300MHz、六个官方perf的动态IPC几何平均≥1.1、含SRAM总面积≤36,000μm²，并通过全部25个程序的官方退出答案。
ER1基线：IPC0.76303979，371.41820820MHz，49,638.890694μm²。
A8已测：IPC0.76398585，349.48805461MHz，37,638.051294μm²；六perf答案通过，原默认100万周期correctness为16通过/3超时失败，原日志保留，不能称全通过。

只测A16R2这一个完整组合，不测A9—A15中间候选，不做参数扫描。它继承A8的ready-base load免RS/AGU、直接发射、本地恢复保护及轻量ROB，并包含以下新增修改：

|修改|明确的结构收益依据|代价和仍待测的限制|
|---|---|---|
|A9—A11无用ROB/CDB载荷及选择网络投影|本配置退休包65→33位、ROB广播数据101→1位、直接CDB包157→90位；实际PRF结果、LSQ store数据、全tag/error保留|省略未连接return_value诊断输出，默认完整接口路径仍可选择；实际映射收益未知|
|A12指令行缓冲|16个私有寄存器行，热命中响应从两拍变为一拍，理想连续命中取指间隔2→1|新增声明2650状态位；命中比例和Fmax未知，未命中维持原SRAM/MSHR路径|
|A13依赖load地址直通选择|完整LSQ标签匹配的新AGU load地址同拍进入原请求选择寄存器，省一拍|地址匹配/选择增加组合长度；老store未知地址和数据仍保守阻塞|
|A14两路后端、恢复ER1数据缓存容量|PRF读端口8→4、ALU4→2、完成源6→4、CDB3→2；恢复16KiB Dcache|退休峰值4→2；SRAM预计恢复7,825.666854μm²，比A8增加3,525.849900；不能预言真实IPC或面积已达标|
|A15两项弹性派发队列|R只预留ROB/PRF与队列；D按实际RS/LSQ需求原子准入，ready-base load在RS满时仍能进入LSQ；名义R→D仍一拍|额外声明358状态位、前项mux、容量比较；整包等待及满队列同拍pop不能立即push可能降低吞吐|
|A16R2共享移位器|每个ALU的立即数/寄存器移位共用一套桶形移位器，当前实例4→2，无新增状态或执行拍|5位移位量选择置于桶形移位前，频率成本需测；迭代移位路径及结果时序未变|

A8的rsort周期比ER1增加32.894%，多项容量/流水线同时改变，不能唯一归因于Dcache。本组合用恢复原缓存容量配合减少后端读写选择网络作一次明确的架构取舍。
热取指、依赖load和资源准入都有可定位的等待边沿或容量阻塞削减，后台读端口/执行实例减半有明确结构收益，已足以支持一次组合测量；这些不是IPC≥1.1或面积≤36,000的预测证明。

已检查：稀疏RS/LSQ demand先计数后统一gating，无alloc_fire→valid环；整包只pop一次，R目的寄存器/ROB只分配一次；两项队列同时push/pop使用不同槽；恢复对两项所有lane检查完整ROB代际与严格旧年龄，保留顺序；queued消费者的物理版本受顺序退休生命周期保护。
保留LOCAL_EXEC_RECOVERY=1及原分支取消、LSQ老store阻塞/按字节转发、MMIO地址0x80000000/WSTRBf/实际WDATA退出路径。禁止不带D寄存边界却启用弹性派发的参数组合。
默认关闭新增选项仍有原路径。源级协议检查不是仿真或形式验证；这些新增事务状态需要本轮19correctness确认。

剩余想法筛选：共享ALU全部加法器会把32位operand mux放入唤醒→执行路径，当前频率预算有限，暂不叠加；进一步缩小ROB/PRF/LSQ、增加路数或盲目修改预取器没有动态压力证据；全局删除keep有破坏控制分布的风险；主缓存fill-forward和进一步压窄完成传输只是小幅路径/面积收益，留待本轮定位剩余瓶颈后决定。本轮不继续堆入缺乏相称收益依据的修改。

只运行一次原生Windows固定课程Verilator5.020构建、六perf、19correctness、Yosys0.63/ABC/OpenSTA3.1综合与STA。官方build.py/testcase.py/sim.cpp、程序、答案、metrics、SRAM面积公式与ASAP7 RVT TT库保持原字节。
perf保持latency10及100万周期预算、原metrics动态分子/六项GEOMEAN；correctness单独明确MAX_CYCLES=10,000,000，避免pi的3,117,658条动态指令在两路峰值下也无法通过默认100万周期限额。它只是官方支持的运行上限参数，所有退出答案仍必须PASS，不能将A8原超时改写为通过。
固定提交README-EN.md的自定义示例为MAX_CYCLES=5000000 LATENCY=10，config.mk有100000000注释示例；本轮10000000提供长程序与低IPC的余量。最终记录明确区分perf/correctness预算。
综合请求2ns，课程I/O/uncertainty/load/reset/理想无寄生约束不变，Fmax取正式报告最小可行周期；负2ns slack不能等同于300MHz失败。

课程严格门槛本目标仍为IPC≥1.1、Fmax>300、面积含SRAM≤36,000，不用较弱的课程1.0985/≥300布尔值替代。
修正版保留三处局部保留字matches→load_address_matches改名，并恢复两处MSHR命名端口if_req_pc_i/if_req_epoch_i；相对A16共两个文件改变、39个源码hash项不变。主Icache主体与A11在仅重命名信号后完全一致，所有主缓存子模块命名端口标签与A11相同。旧A12反向改名检查未区分端口标签，因此不足以证明可构建，已补上标签保留检查并修复准备脚本。A16/A16R1失败构建及停止的未完成综合日志全部保留，均没有仿真结果。
冻结和本报告生成时未启动本候选任何CPU/EDA测试；对话汇报后才调度一次。测量期间独立优化继续；本工作树EU和所有旧候选/失败日志不覆盖，未得到同版本全部证据前不宣称目标完成。
''', encoding='utf-8')
    tool_paths = [Path(config[key]) for key in ('yosys','abc','sta','verilator','verilator_build_driver')]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    plan = dict(status='PREPARED_NOT_STARTED', candidate=str(CANDIDATE),
        candidate_sha256=sha(CANDIDATE/'candidate.json'), source_manifest_sha256=sha(RUN/'source_manifest.json'),
        config_sha256=sha(RUN/'course_windows_config.json'), pretest_report=str(REPORT),
        pretest_report_sha256=sha(REPORT), host_sha256={str(p):sha(p) for p in HOST_FILES},
        tool_sha256={str(p):sha(p) for p in tool_paths}, perf_cases=perf, correctness_cases=correctness,
        source_files=len(names), unchanged_course_dependency_files=len(untouched),
        source_reviews_sha256={f'A{i}_source_review.json':sha(CANDIDATE.parent/f'A{i}_source_review.json') for i in range(9,17)},
        identifier_repair_proof_sha256=sha(CANDIDATE.parent/'A16R2_source_review.json'),
        perf_max_cycles=1000000, correctness_max_cycles=CORRECTNESS_MAX_CYCLES,
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300),
        a8_terminal_reference_sha256=sha(RUN/'a8_terminal_reference.json'))
    write(RUN/'measurement_plan.json', plan)
    goal = read(GOAL_RECORD)
    goal.update(status='A16R2_FROZEN_PRETEST_REPORTED_NOT_STARTED', current_prepared_candidate=CANDIDATE.name,
        pending_source_candidate=str(CANDIDATE), pending_source_candidate_sha256=plan['candidate_sha256'],
        pending_source_candidate_tests_started=False, candidate_tests_started=False, candidates_adopted=False,
        candidate_manifest_sha256=plan['candidate_sha256'], prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_pretest_report=str(REPORT), candidate_pretest_report_sha256=sha(REPORT),
        candidate_metrics_belong_to=CANDIDATE.name, candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        candidate_correctness_passed=None, candidate_correctness_failed=None, candidate_correctness_finished=False,
        last_measured_candidate='A8_direct_issue_local_recovery', last_measured_result=a8_terminal,
        previous_goal_turn_classification='PROGRESS_NEW_A8_TERMINAL_CORRECTNESS_EVIDENCE',
        last_goal_turn_classification='PROGRESS_A16R2_SHARED_BARREL_DISPATCH_REVIEW_AND_COHERENT_BATCH_FREEZE',
        goal_complete=False, next_work=['Report A16R2 gains/risks before one dispatch.',
            'Continue independent source optimization during the immutable native measurement.',
            'Audit exact A16R2 six-perf/19-correctness/area-including-SRAM/strict-Fmax requirements.'])
    write(GOAL_RECORD, goal)
    check()
    print({key:plan[key] for key in ('status','candidate','source_files','unchanged_course_dependency_files',
        'pretest_report','source_manifest_sha256','correctness_max_cycles')})


def start():
    plan = check()
    assert plan['status'] == 'PREPARED_NOT_STARTED'
    assert not (RUN/'dispatch_identity.json').exists() and not (RUN/'result').exists()
    command = [sys.executable,'-u',str(ROOT/'tools/run_course_standard_windows.py'),
        '--config',str(RUN/'course_windows_config.json'),'--correctness',
        '--correctness-max-cycles',str(CORRECTNESS_MAX_CYCLES)]
    with (RUN/'driver_stdout.log').open('w',encoding='utf-8') as stdout, (RUN/'driver_stderr.log').open('w',encoding='utf-8') as stderr:
        process = subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch = dict(status='BACKGROUND_DISPATCHED',process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(),command=command,
        source_manifest_sha256=plan['source_manifest_sha256'],pretest_report_sha256=plan['pretest_report_sha256'],
        host_sha256=plan['host_sha256'],initial_process_alive=process.poll() is None,environment='WINDOWS_NATIVE')
    write(RUN/'dispatch_identity.json',dispatch)
    goal = read(GOAL_RECORD)
    goal.update(status='A16R2_IMMUTABLE_MEASUREMENT_IN_PROGRESS',candidate_tests_started=True,
        pending_source_candidate_tests_started=True,active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN),measurement_process_id=process.pid)
    write(GOAL_RECORD,goal)
    print(dispatch)


def observe():
    check()
    dispatch = read(RUN/'dispatch_identity.json')
    observation = dict(run=str(RUN),process_id=dispatch['process_id'],process_alive=live(dispatch['process_id']),
        observed_at=datetime.now(timezone.utc).isoformat(),result=optional(RUN/'result/result.json'),
        failure=optional(RUN/'result/failure.json'))
    for name in ('driver_stdout.log','driver_stderr.log'):
        path = RUN/name
        observation[name] = [line[:250] for line in path.read_text(errors='replace').splitlines()[-5:]] if path.exists() else []
    if observation['result']:
        result = observation['result']
        observation['objective_numeric_met'] = result['ipc'] >= 1.1 and result['fmax_mhz'] > 300 and result['area_um2'] <= 36000
        observation['full_correctness_passed'] = result['official_correctness_suite_passed']
    print(observation)


if __name__ == '__main__':
    assert os.name == 'nt', 'Native Windows only'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','start','observe'))
    args = parser.parse_args()
    {'prepare':prepare,'start':start,'observe':observe}[args.action]()
