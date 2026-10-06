"""Join original 18+4 passes and the unchanged-executable official Pi follow-up.

No simulator, build or synthesis is invoked. Preserve the original timeout.
"""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a109_closing import check as check_original, OUT as ORIGINAL, PLAN as ORIGINAL_PLAN, protocol_module
from manage_er1_a109_pi_budget_followup import check as check_pi, OUT as PI, PLAN as PI_PLAN
from manage_er1_a109_measurement import RUN, live

OUT = ROOT/'build/cpu2026/er1_a109_combined_closing_20261006.json'


def official_blocks(text):
    matches = list(re.finditer(r'^\[(correctness_[^\]]+)\]$', text, re.MULTILINE))
    return [(match[1], text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)])
            for i, match in enumerate(matches)]


def collect():
    original_plan = check_original()
    pi_plan = check_pi()
    assert sha(ORIGINAL_PLAN) == '0e40e8bd094c403baaf39fecf6f3bbc8673bb9842935293fa5509a47b062cdf1'
    assert sha(PI_PLAN) == 'c5f410cefb793d0cdaa42386cbbf2e1290c9af95f1a71261cc207c4876fc6065'
    original_path = ORIGINAL/'closing_result.json'
    original = read(original_path)
    phase, dispatch = read(ORIGINAL/'phase.json'), read(ORIGINAL/'dispatch_identity.json')
    assert not live(dispatch['process_id']) and not live(103132)
    assert phase['status'] == original['status'] == 'CLOSING_CORRECTNESS_COMPLETE'
    assert phase['result_sha256'] == sha(original_path) == '75e1f5092a3a2d8e3c2257821e9bf798f1d712a62c379573436a3817af20445d'
    assert original['plan_sha256'] == dispatch['plan_sha256'] == sha(ORIGINAL_PLAN)
    assert original['official_returncode'] == 1
    assert original['official_passed_count'] == 18 and original['official_failed_count'] == 1
    assert original['official_all_passed'] is False and original['all_23_passed'] is False
    assert original['edge_all_passed'] is True
    assert original_plan['official_command'][-2:] == ['--max-cycles', '10000000']
    course = RUN/'source/.deps/RISC-V-CPU-2026'
    names = sorted(path.name for path in (course/'testcases').glob('correctness_*') if path.is_dir())
    assert len(names) == 19 and original_plan['official_cases'] == names
    assert original['official_expected_cases'] == original['official_observed_cases'] == names
    stdout, stderr = ORIGINAL/'official_stdout.log', ORIGINAL/'official_stderr.log'
    assert sha(stdout) == original['official_stdout_sha256']
    assert sha(stderr) == original['official_stderr_sha256']
    text = stdout.read_text(encoding='utf-8')
    blocks = official_blocks(text)
    assert [name for name, _ in blocks] == names
    assert re.findall(r'^Results: (\d+) passed, (\d+) failed$', text, re.MULTILINE) == [('18', '1')]
    expected_error = 'FAIL: simulator exited with status 1: FAIL: timeout or finish before exit write response; cycles=10000000'
    assert stderr.read_text(encoding='utf-8').strip() == expected_error
    rows = []
    for name, block in blocks:
        cycles = re.findall(r'^PASS cycles=(\d+)$', block, re.MULTILINE)
        if name == 'correctness_pi':
            assert not cycles and 'PASS' not in block
            continue
        assert len(cycles) == 1 and 0 < int(cycles[0]) <= 10000000, name
        case = course/'testcases'/name
        rows.append(dict(name=name, passed=True, cycles=int(cycles[0]), max_cycles=10000000,
            latency=10, attempt='original_closing', original_attempt_returncode=1,
            program_sha256=sha(case/'program.data'), expected_sha256=sha(case/'expected.txt')))
    assert len(rows) == 18
    edges = original['edge_rows']
    assert len(edges) == 4 and len({row['name'] for row in edges}) == 4
    oj = protocol_module(Path(original_plan['oj_io']))
    for case, row in zip(original_plan['edge_cases'], edges):
        assert row['name'] == case['name'] and row['passed'] and row['returncode'] == 0
        assert row['error'] is None and row['expected_u32'] == case['expected_u32']
        edge_stdout, edge_stderr = ORIGINAL/(row['name']+'.stdout.log'), ORIGINAL/(row['name']+'.stderr.log')
        assert sha(edge_stdout) == row['stdout_sha256'] and sha(edge_stderr) == row['stderr_sha256']
        assert oj.compare_output(edge_stdout.read_text(encoding='utf-8'), Path(case['answer']).read_text(encoding='utf-8')) is None
        assert re.findall(r'^CPU2026 cycles=(\d+)$', edge_stderr.read_text(encoding='utf-8'), re.MULTILINE) == [str(row['cycles'])]
        assert 0 < row['cycles'] <= case['max_cycles'] == 200000
    keys = ['candidate_sha256', 'source_manifest_sha256', 'config_sha256', 'executable_sha256', 'original_result_sha256']
    for key in keys:
        assert pi_plan[key] == original_plan[key], key
    assert pi_plan['case'] == 'correctness_pi' and pi_plan['expected_u32'] == 112
    assert pi_plan['latency'] == original_plan['latency'] == original['latency'] == 10
    command = pi_plan['command']
    assert command[1:] == ['-u', str(course/'scripts/testcase.py'), '--kind', 'correctness',
        '--case', 'correctness_pi', '--testcases', str(course/'testcases'), '--sim', str(Path(original_plan['executable'])),
        '--max-cycles', '48000000', '--latency', '10']
    pi_path = PI/'followup_result.json'
    assert pi_path.exists(), 'Wait for the existing Pi follow-up; do not rerun it'
    pi_result = read(pi_path)
    pi_phase, pi_dispatch = read(PI/'phase.json'), read(PI/'dispatch_identity.json')
    assert not live(pi_dispatch['process_id']), 'Wait for the actual Pi supervisor to exit'
    assert pi_phase['status'] == pi_result['status'] == 'PI_BUDGET_FOLLOWUP_COMPLETE'
    assert pi_phase['result_sha256'] == sha(pi_path)
    assert pi_result['plan_sha256'] == pi_dispatch['plan_sha256'] == sha(PI_PLAN)
    assert pi_result['passed'] is True and pi_phase['passed'] is True and pi_result['returncode'] == 0
    for key in ['source_manifest_sha256', 'executable_sha256']:
        assert pi_result[key] == original_plan[key]
    assert pi_result['max_cycles'] == pi_plan['max_cycles'] == 48000000
    assert pi_result['latency'] == 10 and pi_result['expected_u32'] == 112
    pi_stdout, pi_stderr = PI/'official_stdout.log', PI/'official_stderr.log'
    assert sha(pi_stdout) == pi_result['official_stdout_sha256']
    assert sha(pi_stderr) == pi_result['official_stderr_sha256']
    pi_text = pi_stdout.read_text(encoding='utf-8')
    assert [name for name, _ in official_blocks(pi_text)] == ['correctness_pi']
    assert re.findall(r'^PASS cycles=(\d+)$', pi_text, re.MULTILINE) == [str(pi_result['cycles'])]
    assert re.findall(r'^Results: (\d+) passed, (\d+) failed$', pi_text, re.MULTILINE) == [('1', '0')]
    assert pi_stderr.read_text(encoding='utf-8').strip() == ''
    assert 36025632 <= pi_result['cycles'] <= 48000000
    case = course/'testcases/correctness_pi'
    assert (case/'expected.txt').read_text(encoding='utf-8').strip() == '112'
    rows.append(dict(name='correctness_pi', passed=True, cycles=pi_result['cycles'], max_cycles=48000000,
        latency=10, attempt='pi_budget_followup', attempt_returncode=0,
        program_sha256=sha(case/'program.data'), expected_sha256=sha(case/'expected.txt')))
    rows.sort(key=lambda row: row['name'])
    assert [row['name'] for row in rows] == names
    assert all(pi_result[key] == 0 for key in ['new_cpu_builds', 'new_synth_runs', 'new_perf_runs'])
    paths = [Path(__file__), ORIGINAL_PLAN, original_path, ORIGINAL/'phase.json', ORIGINAL/'dispatch_identity.json',
        stdout, stderr, PI_PLAN, pi_path, PI/'phase.json', PI/'dispatch_identity.json', pi_stdout, pi_stderr,
        PI/'cycle_bound_analysis.json', ROOT/'reports/ER1_A109_pi_cycle_budget_pretest_2026-10-06.md']
    paths += [ORIGINAL/(row['name']+suffix) for row in edges for suffix in ['.stdout.log', '.stderr.log']]
    return dict(status='A109_COMBINED_CLOSING_ALL_19_UNIQUE_OFFICIAL_AND_4_EDGE_PASS',
        source_manifest_sha256=original_plan['source_manifest_sha256'], candidate_sha256=original_plan['candidate_sha256'],
        executable_sha256=original_plan['executable_sha256'], original_result_sha256=original_plan['original_result_sha256'],
        original_attempt=dict(run=str(ORIGINAL), returncode=1, passed=18, failed=1,
            failed_case='correctness_pi', failure_kind='watchdog_timeout', max_cycles=10000000,
            result_sha256=sha(original_path), original_all_23_passed=False),
        pi_followup=dict(run=str(PI), returncode=0, passed=True, cycles=pi_result['cycles'], max_cycles=48000000,
            expected_u32=112, result_sha256=sha(pi_path)),
        official_rows=rows, official_passed_count=19, edge_rows=edges, edge_passed_count=4,
        all_23_passed=True, original_timeout_evidence_preserved=True,
        same_source_config_executable=True, latency=10, additional_cpu_builds=0,
        additional_synthesis_runs=0, performance_repeats=0,
        evidence_sha256={str(path):sha(path) for path in paths}, goal_complete=False)


def validate():
    saved = read(OUT)
    expected = collect()
    assert {key: value for key, value in saved.items() if key != 'recorded_at'} == expected
    return saved


def main():
    assert not OUT.exists(), 'Preserve the first successful combined closing record'
    combined = collect()
    combined['recorded_at'] = datetime.now(timezone.utc).isoformat()
    write(OUT, combined)
    print(dict(status=combined['status'], original_passes=18, pi_followup_cycles=combined['pi_followup']['cycles'],
        official_unique_passes=19, boundary_passes=4, original_timeout_preserved=True,
        proof=str(OUT), proof_sha256=sha(OUT)))


if __name__ == '__main__':
    main()
