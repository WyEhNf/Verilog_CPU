"""Freeze A41 once, report before native characterization, observe the original PID."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a36_measurement import check as check_a36
from wait_frequency_directed_native import live

BASE = Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A41_lsq_two_prefix_reclaim')
RUN = Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
REPORT = ROOT / 'reports/ER1_A41_pretest_2026-10-05.md'
GOAL_RECORD = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES = [ROOT / 'tools/run_course_standard_windows.py',
              ROOT / 'tools/prebuild_course_windows.py',
              ROOT / 'tools/verilator_windows_time_zero.cpp', Path(__file__)]


def check():
    plan = read(RUN / 'measurement_plan.json')
    for path, key in [(RUN / 'source_manifest.json', 'source_manifest_sha256'),
                      (RUN / 'course_windows_config.json', 'config_sha256'),
                      (REPORT, 'pretest_report_sha256'),
                      (CANDIDATE / 'candidate.json', 'candidate_sha256')]:
        assert sha(path) == plan[key], path
    for path, digest in plan['host_sha256'].items():
        assert sha(path) == digest, path
    for path, digest in plan['tool_sha256'].items():
        assert sha(path) == digest, path
    for name, digest in read(RUN / 'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN / 'source' / name) == digest, name
    config = read(RUN / 'course_windows_config.json')
    assert config['environment'] == 'WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert config['latency'] == 10
    assert config['framework_revision'] == '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    return plan


def prepare():
    assert not RUN.exists() and REPORT.exists()
    check_a36()
    old = read(BASE / 'result/result.json')
    assert old['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert not live(read(BASE / 'dispatch_identity.json')['process_id'])
    candidate = read(CANDIDATE / 'candidate.json')
    assert candidate['tests_started'] is False and candidate['adopted'] is False
    parent = read(BASE / 'source_manifest.json')
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE / name) == digest, name
    active = read(ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json')
    for name, digest in active['source_sha256'].items():
        assert sha(ROOT / name) == digest, name
    top = (CANDIDATE / 'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b' + key + r'\s*=\s*(\d+)', top)
        assert match and int(match[1]) == value, key
    names = sorted(set(parent['snapshot_sha256']) | set(candidate['source_sha256']))
    for name in names:
        src = CANDIDATE / name if name in candidate['source_sha256'] else BASE / 'source' / name
        assert src.exists(), name
        dest = RUN / 'source' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    source = RUN / 'source'
    untouched = [name for name in names if name.startswith('.deps/')]
    for name in untouched:
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
    write(RUN / 'a36_reference.json', reference)
    frozen = dict(format='er1-tier3-native-source-v1', status='FROZEN_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(source),
        reference_manifest_sha256=sha(BASE / 'source_manifest.json'), candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(CANDIDATE / 'candidate.json'),
        framework_commit=candidate['framework_commit'], testcases_commit=candidate['testcases_commit'],
        parameter_overrides=candidate['parameter_overrides'], materialized_top_defaults=True,
        snapshot_sha256={name: sha(source / name) for name in names}, tests_started=False)
    write(RUN / 'source_manifest.json', frozen)
    config = read(BASE / 'course_windows_config.json')
    config.update(source=str(source), source_manifest=str(RUN / 'source_manifest.json'),
        out=str(RUN / 'result'), native_build_path=str(RUN / 'native_build'),
        native_ipc_path=str(RUN / 'native_ipc'))
    write(RUN / 'course_windows_config.json', config)
    tool_paths = [Path(config[key]) for key in ('yosys', 'abc', 'sta', 'verilator', 'verilator_build_driver')]
    tool_paths.append(Path(config['tools_root']) / 'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan = dict(status='PREPARED_NOT_STARTED', candidate=str(CANDIDATE),
        candidate_sha256=sha(CANDIDATE / 'candidate.json'),
        source_manifest_sha256=sha(RUN / 'source_manifest.json'),
        config_sha256=sha(RUN / 'course_windows_config.json'),
        pretest_report=str(REPORT), pretest_report_sha256=sha(REPORT),
        host_sha256={str(p): sha(p) for p in HOST_FILES},
        tool_sha256={str(p): sha(p) for p in tool_paths},
        perf_cases=perf, correctness_cases=correctness, source_files=len(names),
        unchanged_course_dependency_files=len(untouched),
        source_reviews_sha256={f'A{i}_source_review.json': sha(CANDIDATE.parent / f'A{i}_source_review.json')
                               for i in range(37, 42)},
        a36_three_case_profile_sha256=sha('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json'),
        source_progress_sha256=sha(ROOT / 'build/cpu2026/er1_a36_terminal_a39_a41_source_progress_20261005.json'),
        a36_reference_sha256=sha(RUN / 'a36_reference.json'),
        perf_max_cycles=1000000, correctness_started_with_characterization=False,
        full_correctness_and_relevant_m_coverage_required_before_adoption=True,
        target=dict(ipc=1.1, total_area_um2=36000, strict_minimum_fmax_mhz=300))
    write(RUN / 'measurement_plan.json', plan)
    goal = read(GOAL_RECORD)
    goal.update(status='A41_FROZEN_PRETEST_NOT_STARTED',
        current_prepared_candidate=CANDIDATE.name, candidate_manifest_sha256=plan['candidate_sha256'],
        pending_source_candidate=str(CANDIDATE), pending_source_candidate_sha256=plan['candidate_sha256'],
        pending_source_candidate_tests_started=False, candidate_tests_started=False,
        prepared_run=str(RUN), prepared_source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_pretest_report=str(REPORT), candidate_pretest_report_sha256=plan['pretest_report_sha256'],
        last_goal_turn_classification='PROGRESS_A41_BATCH_SOURCE_REVIEW_AND_FROZEN_PRETEST',
        previous_goal_turn_classification='PROGRESS_NEW_A39_A40_A41_SOURCE_AND_PROFILE_ATTRIBUTION',
        next_work=['Report this coherent batch before one native course characterization.',
                   'Keep optimizing independently while the original A41 measurement process runs.',
                   'Require same-source strict metrics and relevant full correctness/M/recovery/cache coverage before adoption.'],
        goal_complete=False, candidates_adopted=False)
    write(GOAL_RECORD, goal)
    check()
    print({key: plan[key] for key in ('status', 'candidate', 'source_files',
        'unchanged_course_dependency_files', 'pretest_report', 'pretest_report_sha256',
        'source_manifest_sha256', 'correctness_started_with_characterization')})


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
    dispatch = dict(status='BACKGROUND_DISPATCHED', process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(), command=command,
        source_manifest_sha256=plan['source_manifest_sha256'],
        pretest_report_sha256=plan['pretest_report_sha256'], host_sha256=plan['host_sha256'],
        initial_process_alive=process.poll() is None, environment='WINDOWS_NATIVE',
        full_correctness_started=False)
    write(RUN / 'dispatch_identity.json', dispatch)
    goal = read(GOAL_RECORD)
    goal.update(status='A41_IMMUTABLE_CHARACTERIZATION_IN_PROGRESS',
        active_measurement_candidate=CANDIDATE.name, measurement_run=str(RUN),
        measurement_process_id=process.pid, measurement_process_alive=process.poll() is None,
        active_measurement_process_ids=[process.pid],
        active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        pending_source_candidate_tests_started=True, candidate_tests_started=True,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        candidate_metrics_belong_to=CANDIDATE.name)
    write(GOAL_RECORD, goal)
    print(dispatch)


def observe():
    check()
    dispatch = read(RUN / 'dispatch_identity.json')
    result = optional(RUN / 'result/result.json')
    metrics = ({key: result.get(key) for key in ('status', 'ipc', 'area_um2', 'fmax_mhz',
        'official_perf_expected_results_passed', 'official_correctness_suite_passed',
        'thread_objective_numeric_requirements_met')} if result else None)
    observation = dict(run=str(RUN), process_id=dispatch['process_id'],
        process_alive=live(dispatch['process_id']), observed_at=datetime.now(timezone.utc).isoformat(),
        result=metrics, failure=optional(RUN / 'result/failure.json'))
    for name in ('driver_stdout.log', 'driver_stderr.log'):
        path = RUN / name
        observation[name] = [line[:250] for line in path.read_text(errors='replace').splitlines()[-5:]] if path.exists() else []
    print(observation)


if __name__ == '__main__':
    assert os.name == 'nt', 'Native Windows only'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'observe'))
    args = parser.parse_args()
    {'prepare': prepare, 'start': start, 'observe': observe}[args.action]()
