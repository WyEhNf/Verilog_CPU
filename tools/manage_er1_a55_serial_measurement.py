"""A55R2: same frozen RTL/tools; serialize synth/STA then CPU build and six IPC cases."""
import argparse
import ctypes
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a55_measurement import check as check_a55
from wait_frequency_directed_native import live

FAILED = Path('F:/CPU2026CourseRuns/ER1_A55_tier3_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A55_predictor_bank_local_prefix_history')
REPORT = ROOT / 'reports/ER1_A55R2_serial_pretest_2026-10-05.md'
GOAL = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'


def memory_status():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ('total_physical', 'available_physical',
                'total_commit', 'available_commit', 'total_virtual', 'available_virtual', 'extended_virtual')]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return {name: getattr(status, name) for name, kind in status._fields_ if name not in ('length', 'extended_virtual')}


def check():
    plan = read(RUN / 'measurement_plan.json')
    for path, key in [(RUN / 'source_manifest.json', 'source_manifest_sha256'),
                      (RUN / 'course_windows_config.json', 'config_sha256'),
                      (REPORT, 'pretest_report_sha256'), (CANDIDATE / 'candidate.json', 'candidate_sha256'),
                      (RUN / 'failed_a55_evidence.json', 'failure_evidence_sha256')]:
        assert sha(path) == plan[key], path
    for group in ('host_sha256', 'tool_sha256', 'original_evidence_sha256'):
        for path, digest in plan[group].items():
            assert sha(path) == digest, path
    for name, digest in read(RUN / 'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN / 'source' / name) == digest, name
    c = read(RUN / 'course_windows_config.json')
    assert c['environment'] == 'WINDOWS_NATIVE' and c['wsl_allowed'] is False and c['latency'] == 10
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    original = check_a55()
    dispatch = read(FAILED / 'dispatch_identity.json')
    assert not live(dispatch['process_id'])
    assert (FAILED / 'result/failure.json').exists() and not (FAILED / 'result/result.json').exists()
    synth_log = FAILED / 'result/synth.log'
    build_log = FAILED / 'native_build/build.log'
    assert 'std::bad_alloc' in synth_log.read_text(errors='replace')
    assert 'std::bad_alloc' in build_log.read_text(errors='replace')
    goal = read(GOAL)
    assert goal['current_source_candidate'] == CANDIDATE.name
    parent = read(FAILED / 'source_manifest.json')
    for name, digest in parent['snapshot_sha256'].items():
        assert sha(FAILED / 'source' / name) == digest, name
        destination = RUN / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FAILED / 'source' / name, destination)
    evidence_files = [FAILED / 'dispatch_identity.json', FAILED / 'measurement_plan.json',
                      FAILED / 'source_manifest.json', FAILED / 'result/failure.json', synth_log, build_log,
                      FAILED / 'driver_stdout.log', FAILED / 'driver_stderr.log']
    evidence = dict(status='A55_PARALLEL_ATTEMPT_TERMINAL_BAD_ALLOC_NO_METRICS',
        recorded_at=datetime.now(timezone.utc).isoformat(), original_pid=dispatch['process_id'], original_pid_live=False,
        original_result_missing=True, synth_and_verilator_frontends_bad_alloc=True,
        files_sha256={str(p): sha(p) for p in evidence_files}, memory_at_recording=memory_status(),
        simultaneous_memory_pressure_is_a_hypothesis=True, source_expansion_cause_not_excluded=True,
        original_attempt_preserved=True, rtl_and_tool_versions_unchanged=True,
        mitigation='Use original --timing-only then --reuse-synth sequentially in one new supervised attempt.')
    write(RUN / 'failed_a55_evidence.json', evidence)
    source_manifest = dict(parent)
    source_manifest.update(created_at=datetime.now(timezone.utc).isoformat(), source_root=str(RUN / 'source'),
        original_a55_source_manifest_sha256=sha(FAILED / 'source_manifest.json'),
        byte_identical_to_original_a55_snapshot=True, tests_started=False)
    write(RUN / 'source_manifest.json', source_manifest)
    config = read(FAILED / 'course_windows_config.json')
    config.update(source=str(RUN / 'source'), source_manifest=str(RUN / 'source_manifest.json'),
        out=str(RUN / 'result'), native_build_path=str(RUN / 'native_build'), native_ipc_path=str(RUN / 'native_ipc'))
    write(RUN / 'course_windows_config.json', config)
    available = evidence['memory_at_recording']['available_commit'] / (1024**3)
    REPORT.write_text(f'''# A55R2 串行测量前汇报

继续完成原目标：IPC≥1.1、包含SRAM总面积≤36000μm²、频率>300MHz，以及完整RV32IM/OoO/顺序提交/MMIO/参数化要求。

A55原PID{dispatch['process_id']}已不存在，result/failure.json明确记录失败。综合日志与Verilator构建日志均出现std::bad_alloc，没有IPC/PPA结果。记录时可提交内存余量约{available:.3f}GiB；同时运行两个大型工具前端可能触发资源不足，但尚不能排除新源码展开导致的内存增长。原作业全部文件保留，未重启。

新运行A55R2的157个源码/课程依赖文件与原A55快照逐字节一致，候选、标准工具和库版本、约束、官方程序、latency=10、FakeRAM面积算法均保持原身份。唯一执行变化是使用原课程Windows runner已有阶段选项串行执行：

1. --timing-only：一次课程综合/STA/含SRAM面积统计，期间不构建CPU。
2. 确認同一manifest/config/工具/综合报告身份后，--reuse-synth：复用刚完成的综合/STA结果，一次原生CPU构建与6个perf程序。每项仍是官方1000000周期预算并检查答案。

这是同一个完整PPA+IPC测量分两阶段调度，目标和覆盖没有缩小。监督进程只调度每阶段一次；遇到真实终止失败保留现场，不自动无限重试。监测超时继续观察原监督PID。原主机runner和工具二进制不修改，保持Windows原生环境。

A42–A55累计结构收益、面积估算、新路径和架构审查见[A55原测试前汇报](E:/Verilog_cpu/reports/ER1_A55_pretest_2026-10-05.md)。结构删去等待拍/串联依赖的依据成立，实际新IPC/Fmax/面积仍未知；已测最优仍为A41，不能把原指标写到A55R2名下。初次表征不加19程序回归；最终采用前仍需同源码的严格数值及完整正确性/M/恢复/缓存/参数验证。

报告生成时A55R2尚未开始执行任何HDL/构建/程序测量；对话汇报后才启动。候选SHA256：{sha(CANDIDATE / 'candidate.json')}。新manifest SHA256：{sha(RUN / 'source_manifest.json')}。冻结身份及失败现场哈希绑定于measurement_plan.json和failed_a55_evidence.json。
''', encoding='utf-8')
    old_evidence = {str(FAILED / 'measurement_plan.json'): sha(FAILED / 'measurement_plan.json'),
                    str(ROOT / 'reports/ER1_A55_pretest_2026-10-05.md'): original['pretest_report_sha256']}
    old_evidence.update(evidence['files_sha256'])
    plan = dict(status='PREPARED_NOT_STARTED', candidate=str(CANDIDATE), candidate_sha256=sha(CANDIDATE / 'candidate.json'),
        source_manifest_sha256=sha(RUN / 'source_manifest.json'), config_sha256=sha(RUN / 'course_windows_config.json'),
        pretest_report=str(REPORT), pretest_report_sha256=sha(REPORT), failure_evidence_sha256=sha(RUN / 'failed_a55_evidence.json'),
        host_sha256=dict(original['host_sha256'], **{str(Path(__file__)): sha(Path(__file__))}),
        tool_sha256=original['tool_sha256'], original_evidence_sha256=old_evidence,
        perf_cases=original['perf_cases'], correctness_cases=original['correctness_cases'],
        source_files=original['source_files'], unchanged_course_dependency_files=original['unchanged_course_dependency_files'],
        effective_structural_profile=original['effective_structural_profile'], serial_tool_phases=True,
        native_cpu_builds_planned=1, new_synth_runs_planned=1, perf_max_cycles=1000000,
        correctness_started_with_characterization=False, target=original['target'])
    write(RUN / 'measurement_plan.json', plan)
    goal.update(status='A55R2_FROZEN_SERIAL_PRETEST_NOT_STARTED',
        active_measurement_candidate=None, active_measurement_process_ids=[], measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None, prepared_run=str(RUN),
        prepared_source_manifest_sha256=plan['source_manifest_sha256'], candidate_pretest_report=str(REPORT),
        candidate_pretest_report_sha256=plan['pretest_report_sha256'],
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        historical_failed_a55_run=str(FAILED), historical_failed_a55_process_id=dispatch['process_id'],
        historical_failed_a55_failure_sha256=sha(FAILED / 'result/failure.json'),
        previous_goal_turn_classification='PROGRESS_NEW_A53_A54_A55_AND_A52_RECONCILED_STATIC_OFFICIAL_IMAGE_EVIDENCE',
        last_goal_turn_classification='PROGRESS_A55_TERMINAL_FAILURE_DIAGNOSED_SAME_SOURCE_SERIAL_ATTEMPT_PREPARED',
        goal_complete=False, candidates_adopted=False)
    write(GOAL, goal)
    check()
    print({k: plan[k] for k in ('status', 'source_manifest_sha256', 'pretest_report', 'serial_tool_phases', 'source_files')})


def start():
    plan = check()
    assert not (RUN / 'dispatch_identity.json').exists() and not (RUN / 'result').exists()
    command = [sys.executable, '-u', str(Path(__file__)), 'run-phases']
    with (RUN / 'driver_stdout.log').open('w', encoding='utf-8') as stdout, \
         (RUN / 'driver_stderr.log').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch = dict(status='SERIAL_BACKGROUND_DISPATCHED', process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(), command=command,
        source_manifest_sha256=plan['source_manifest_sha256'], pretest_report_sha256=plan['pretest_report_sha256'],
        initial_process_alive=process.poll() is None, serial_tool_phases=True, full_correctness_started=False)
    write(RUN / 'dispatch_identity.json', dispatch)
    goal = read(GOAL)
    goal.update(status='A55R2_SERIAL_CHARACTERIZATION_IN_PROGRESS', active_measurement_candidate=CANDIDATE.name,
        measurement_run=str(RUN), measurement_process_id=process.pid, active_measurement_process_ids=[process.pid],
        measurement_process_alive=dispatch['initial_process_alive'],
        active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        measurement_dispatch_sha256=sha(RUN / 'dispatch_identity.json'), candidate_tests_started=True,
        pending_source_candidate_tests_started=True, candidate_metrics_belong_to=CANDIDATE.name,
        last_goal_turn_classification='PROGRESS_A55_BATCH_PRETEST_AND_DIAGNOSED_RESOURCE_MITIGATION_SERIAL_DISPATCH')
    write(GOAL, goal)
    print(dispatch)


def run_phases():
    plan = check()
    assert not (RUN / 'serial_phase_identity.json').exists()
    record = dict(status='SERIAL_TIMING_IN_PROGRESS', supervisor_pid=os.getpid(),
                  source_manifest_sha256=plan['source_manifest_sha256'], phases=[])
    write(RUN / 'serial_phase_identity.json', record)
    for phase, flag in [('timing', '--timing-only'), ('performance', '--reuse-synth')]:
        if phase == 'performance':
            timing = read(RUN / 'result/timing_only.json')
            assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
            assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
            assert timing['config_sha256'] == plan['config_sha256']
            assert sha(RUN / 'result/synth/opt/report.json') == timing['official_report_sha256']
            record.update(status='SERIAL_PERFORMANCE_IN_PROGRESS', timing_report_sha256=sha(RUN / 'result/timing_only.json'))
            write(RUN / 'serial_phase_identity.json', record)
            check()
        command = [sys.executable, '-u', str(ROOT / 'tools/run_course_standard_windows.py'),
                   '--config', str(RUN / 'course_windows_config.json'), flag]
        print('START SERIAL ' + phase, flush=True)
        with (RUN / f'{phase}_stdout.log').open('w', encoding='utf-8') as stdout, \
             (RUN / f'{phase}_stderr.log').open('w', encoding='utf-8') as stderr:
            result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW)
        record['phases'].append(dict(phase=phase, command=command, returncode=result.returncode,
            completed_at=datetime.now(timezone.utc).isoformat(), memory_after_phase=memory_status()))
        if result.returncode:
            record.update(status='SERIAL_' + phase.upper() + '_FAILED')
            write(RUN / 'serial_phase_identity.json', record)
            raise SystemExit(result.returncode)
        write(RUN / 'serial_phase_identity.json', record)
        print('DONE SERIAL ' + phase, flush=True)
    record.update(status='SERIAL_CHARACTERIZATION_COMPLETE', result_sha256=sha(RUN / 'result/result.json'))
    write(RUN / 'serial_phase_identity.json', record)


def observe():
    check()
    dispatch = read(RUN / 'dispatch_identity.json')
    alive = live(dispatch['process_id'])
    result = optional(RUN / 'result/result.json')
    timing = optional(RUN / 'result/timing_only.json')
    phase = optional(RUN / 'serial_phase_identity.json')
    metrics = ({k: result.get(k) for k in ('status', 'ipc', 'fmax_mhz', 'area_um2',
        'official_perf_expected_results_passed', 'official_correctness_suite_passed', 'thread_objective_numeric_requirements_met')}
        if result else None)
    observation = dict(run=str(RUN), process_id=dispatch['process_id'], process_alive=alive,
        observed_at=datetime.now(timezone.utc).isoformat(), phase=phase['status'] if phase else None,
        result=metrics, timing=({k: timing.get(k) for k in ('status', 'fmax_mhz', 'area_um2')} if timing else None))
    for phase_name in ('timing', 'performance'):
        for stream_name in ('stdout', 'stderr'):
            p = RUN / f'{phase_name}_{stream_name}.log'
            if p.exists(): observation[p.name] = [line[:250] for line in p.read_text(errors='replace').splitlines()[-3:]]
    goal = read(GOAL)
    goal.update(measurement_process_alive=alive, measurement_last_observed_at=observation['observed_at'],
                measurement_last_observation=observation)
    write(GOAL, goal)
    print(observation)


if __name__ == '__main__':
    assert os.name == 'nt', 'Native Windows only'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'run-phases', 'observe'))
    args = parser.parse_args()
    {'prepare': prepare, 'start': start, 'run-phases': run_phases, 'observe': observe}[args.action]()
