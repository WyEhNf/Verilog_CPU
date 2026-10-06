"""Prepare, launch, or observe one immutable historical baseline IPC job.

This uses the existing native course runner and its exact completed synthesis.
It deliberately does not replace the current worktree measurement identity.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from wait_frequency_directed_native import live

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def optional(path):
    try:
        return read(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def check(run):
    config = read(run/'course_windows_config.json')
    timing = read(run/'result/timing_only.json')
    manifest = read(run/'source_manifest.json')
    assert config['environment'] == 'WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert Path(config['source']).resolve() == (run/'source').resolve()
    assert Path(config['out']).resolve() == (run/'result').resolve()
    assert Path(config['source_manifest']).resolve() == (run/'source_manifest.json').resolve()
    assert Path(config['native_build_path']).resolve() == (run/'native_build').resolve()
    assert Path(config['native_ipc_path']).resolve() == (run/'native_ipc').resolve()
    assert config['latency'] == 10
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256'] == sha(run/'source_manifest.json')
    assert timing['config_sha256'] == sha(run/'course_windows_config.json')
    assert timing['toolchain_manifest_sha256'] == sha(Path(config['tools_root'])/'toolchain_manifest.json')
    assert timing['official_report_sha256'] == sha(run/'result/synth/opt/report.json')
    for name, expected in manifest['snapshot_sha256'].items():
        assert sha(run/'source'/name) == expected, name
    cases = run/'source/.deps/RISC-V-CPU-2026/testcases'
    perf = sorted(p.name for p in cases.glob('perf_*') if p.is_dir())
    assert len(perf) == 6
    return config, timing, perf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'observe'))
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    assert os.name == 'nt', 'Windows native only'
    run = args.run.resolve()
    config, timing, perf = check(run)
    plan_path = run/'baseline_program_plan.json'
    dispatch_path = run/'baseline_program_dispatch.json'
    if args.action == 'prepare':
        assert args.report is not None
        report = args.report.resolve()
        assert not report.exists() and not plan_path.exists()
        assert timing['fmax_mhz'] >= 300
        for name in ('native_build', 'native_ipc', 'baseline_program_dispatch.json',
                     'result/ipc.json', 'result/result.json', 'result/failure.json',
                     'result/perf.log', 'result/build_host.log'):
            assert not (run/name).exists(), 'Preserve existing work: '+name
        report.write_text(f'''# ER1 基线 IPC 测量前汇报

新目标：以 ER1 为基础，频率保持 >300 MHz，IPC≥1.1，含 SRAM 总面积≤36,000 μm²。

ER1 已测 Fmax {timing['fmax_mhz']:.8f} MHz、总面积 {timing['area_um2']:.6f} μm²。
当前必须确认 ER1 自身 IPC。仅构建一次原生 Verilator 5.020 CPU，运行六个课程性能基准：{', '.join(perf)}。
复用该冻结版本的综合和 STA，命令使用 --reuse-synth，不再次综合、不运行额外定向测试或 19 程序回归。
本次性能基准仍检查官方答案；全套正确性尚未验证，不据此宣布功能或最终目标完成。

latency=10；分子为原 metrics.json dynamic_instructions，IPC 为六个程序的 GEOMEAN。
所有 RTL、官方脚本、程序、工具、计价和约束保持同一冻结身份；不使用 WSL。
独立后台运行，不修改当前 EU 主源码或其结果。后续优化候选独立保存，确认有可观结构收益后才统一测量。

冻结 manifest SHA256：{timing['source_manifest_sha256']}。
原官方综合 report SHA256：{timing['official_report_sha256']}。
本报告生成时 CPU 构建和程序测量尚未开始；对话汇报后才调度。
''', encoding='utf-8')
        plan = dict(status='PREPARED_NOT_STARTED', created_at=datetime.now(timezone.utc).isoformat(),
                    run=str(run), source_manifest_sha256=timing['source_manifest_sha256'],
                    config_sha256=sha(run/'course_windows_config.json'),
                    timing_only_sha256=sha(run/'result/timing_only.json'),
                    timing_identity_sha256=sha(run/'result/timing_identity.json'),
                    official_report_sha256=timing['official_report_sha256'],
                    runner_sha256=sha(ROOT/'tools/run_course_standard_windows.py'),
                    manager_sha256=sha(__file__), report=str(report), report_sha256=sha(report),
                    native_cpu_builds_planned=1, new_synth_runs_planned=0,
                    full_correctness_requested=False, perf_cases=perf,
                    target=dict(ipc=1.1, total_area_um2=36000, minimum_fmax_mhz=300))
        write(plan_path, plan)
        print(json.dumps(plan, ensure_ascii=False))
        return
    plan = read(plan_path)
    assert plan['source_manifest_sha256'] == timing['source_manifest_sha256']
    assert plan['config_sha256'] == sha(run/'course_windows_config.json')
    assert plan['timing_only_sha256'] == sha(run/'result/timing_only.json')
    assert plan['timing_identity_sha256'] == sha(run/'result/timing_identity.json')
    assert plan['official_report_sha256'] == timing['official_report_sha256']
    assert plan['runner_sha256'] == sha(ROOT/'tools/run_course_standard_windows.py')
    assert plan['manager_sha256'] == sha(__file__)
    assert plan['report_sha256'] == sha(plan['report']) and plan['perf_cases'] == perf
    if args.action == 'start':
        assert not dispatch_path.exists()
        for name in ('native_build', 'native_ipc', 'baseline_program_stdout.log',
                     'baseline_program_stderr.log', 'result/ipc.json', 'result/result.json',
                     'result/failure.json', 'result/perf.log', 'result/build_host.log'):
            assert not (run/name).exists(), 'Never repeat earlier program work: '+name
        command = [sys.executable, '-u', str(ROOT/'tools/run_course_standard_windows.py'),
                   '--config', str(run/'course_windows_config.json'), '--reuse-synth']
        with (run/'baseline_program_stdout.log').open('w', encoding='utf-8') as stdout, \
             (run/'baseline_program_stderr.log').open('w', encoding='utf-8') as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        dispatch = dict(status='BASELINE_IPC_BACKGROUND_DISPATCHED', process_id=process.pid,
                        started_at=datetime.now(timezone.utc).isoformat(), command=command,
                        plan_sha256=sha(plan_path), source_manifest_sha256=timing['source_manifest_sha256'],
                        initial_process_alive=process.poll() is None)
        write(dispatch_path, dispatch)
        print(json.dumps(dispatch, ensure_ascii=False))
        return
    dispatch = read(dispatch_path)
    assert dispatch['plan_sha256'] == sha(plan_path)
    build = optional(run/'native_build/build_identity.json')
    built = bool(build and build.get('status') == 'COMPLETE')
    if built:
        assert build['source_manifest_sha256'] == timing['source_manifest_sha256']
        assert build['verilator_sha256'] == sha(config['verilator'])
        assert build['executable_sha256'] == sha(build['executable'])
    ipc = optional(run/'result/ipc.json')
    if ipc:
        assert built and ipc['status'] == 'COMPLETE' and ipc['latency'] == 10
        assert sorted(r['name'] for r in ipc['results']) == perf
        for row in ipc['results']:
            case = run/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
            assert row['program_sha256'] == sha(case/'program.data')
            assert row['metrics_sha256'] == sha(case/'metrics.json')
            assert row['instructions'] == read(case/'metrics.json')['dynamic_instructions']
            assert row['cycles'] > 0 and math.isclose(row['ipc'], row['instructions']/row['cycles'], rel_tol=1e-12)
        geometric = math.exp(sum(math.log(r['ipc']) for r in ipc['results'])/6)
        assert math.isclose(geometric, ipc['geomean_ipc'], rel_tol=1e-12)
    result = optional(run/'result/result.json')
    identity = optional(run/'result/measurement_identity.json')
    failure = optional(run/'result/failure.json')
    if result:
        assert built and ipc and identity['status'] == 'COMPLETE'
        assert identity['source_manifest_sha256'] == timing['source_manifest_sha256']
        assert identity['result_sha256'] == sha(run/'result/result.json')
        assert identity['ipc_sha256'] == sha(run/'result/ipc.json')
        assert identity['official_report_sha256'] == timing['official_report_sha256']
        assert result['official_perf_expected_results_passed'] and result['official_correctness_suite_not_run']
        assert result['ipc'] == ipc['geomean_ipc']
        assert result['fmax_mhz'] == timing['fmax_mhz'] and result['area_um2'] == timing['area_um2']
    alive = live(dispatch['process_id'])
    observation = dict(status='IN_PROGRESS' if alive else 'COMPLETE' if result else 'FAILED' if failure else 'TERMINAL_INCOMPLETE',
                       observed_at=datetime.now(timezone.utc).isoformat(), process_id=dispatch['process_id'],
                       process_live_now=alive, build_complete=built, ipc_complete=bool(ipc),
                       source_manifest_sha256=timing['source_manifest_sha256'],
                       measured_ipc=ipc['geomean_ipc'] if ipc else None,
                       fmax_mhz=timing['fmax_mhz'], total_area_um2=timing['area_um2'],
                       full_correctness_run=False, new_synth_runs=0, failure=failure)
    write(run/'baseline_program_observation.json', observation)
    print(json.dumps(observation, ensure_ascii=False))


if __name__ == '__main__':
    main()
