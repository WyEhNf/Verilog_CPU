"""Read-only independent completion audit of adopted source and both correctness attempts."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path('E:/Verilog_cpu')
RUN = Path('F:/CPU2026CourseRuns/ER1_A109_tier3_20261006')
CLOSING = Path('F:/CPU2026CourseRuns/ER1_A109_closing_20261006')
PI = Path('F:/CPU2026CourseRuns/ER1_A109_pi_budget_20261006')
COMBINED = ROOT/'build/cpu2026/er1_a109_combined_closing_20261006.json'
OUT = ROOT/'build/cpu2026/er1_a109_independent_current_state_audit_20261006.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    assert not OUT.exists(), 'Preserve the first successful independent audit'
    proof_path = ROOT/'build/cpu2026/er1_a109_goal_completion_audit_20261006.json'
    active_path = ROOT/'build/cpu2026/active_er1_a109_implementation_20261006.json'
    proof, active = read(proof_path), read(active_path)
    for name, digest in proof['requirement_evidence_sha256'].items():
        assert sha(name) == digest, name
    candidate = Path(active['candidate'])
    candidate_manifest = read(candidate/'candidate.json')
    sources = candidate_manifest['source_sha256']
    assert len(sources) == 41 and sources == active['source_sha256'] == proof['current_main_41_source_sha256']
    for name, digest in sources.items():
        assert sha(ROOT/name) == sha(candidate/name) == sha(RUN/'source'/name) == digest, name
    backup = Path(active['previous_source_backup'])
    old = read(backup/'backup_manifest.json')['source_sha256']
    assert len(old) == 40 and old == proof['backup_old_40_source_sha256']
    for name, digest in old.items():
        assert sha(backup/name) == digest, name
    assert set(sources)-set(old) == {'rv32im_defs.vh'}
    assert sum(old[name] != sources[name] for name in old) == 20
    manifest = read(RUN/'source_manifest.json')
    assert len(manifest['snapshot_sha256']) == 157
    assert manifest['framework_commit'] == '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    assert manifest['testcases_commit'] == '29f980727f7d99a1842a58f34091c7579ba3fe85'
    for name, digest in manifest['snapshot_sha256'].items():
        assert sha(RUN/'source'/name) == digest, name
    config = read(RUN/'course_windows_config.json')
    assert config['environment'] == 'WINDOWS_NATIVE' and config['wsl_allowed'] is False and config['latency'] == 10
    build = read(RUN/'native_build/build_identity.json')
    identity = read(RUN/'result/measurement_identity.json')
    assert build['status'] == identity['status'] == 'COMPLETE'
    assert build['source_manifest_sha256'] == identity['source_manifest_sha256'] == sha(RUN/'source_manifest.json')
    assert sha(build['executable']) == build['executable_sha256'] == active['executable_sha256']
    assert identity['prebuilt_cpu']['executable_sha256'] == build['executable_sha256']
    result = read(RUN/'result/result.json')
    assert sha(RUN/'result/result.json') == identity['result_sha256']
    ppa_path = RUN/'result/synth/opt/report.json'
    assert sha(ppa_path) == identity['official_report_sha256']
    ppa = read(ppa_path)
    area = ppa['area']
    for key in ['combinational_area_um2','sequential_area_um2','sram_area_um2','area_um2']:
        assert area[key] == result['area'][key]
    assert abs(sum(area[key] for key in ['combinational_area_um2','sequential_area_um2','sram_area_um2'])-result['area_um2']) < 1e-8
    srams = area['sram_instances']
    assert len(srams) == len({row['instance'] for row in srams}) == 93
    assert abs(sum(row['area_um2'] for row in srams)-area['sram_area_um2']) < 1e-8
    assert ppa['sram_model']['area_per_bit_um2'] == 0.0419904
    timing = ppa['timing']
    assert timing['timing_analyzed'] and timing['clock_uncertainty_ns'] == 0.05
    assert timing['estimated_fmax_mhz'] == result['fmax_mhz']
    assert timing['minimum_period_ns'] == result['minimum_period_ns']
    assert abs(1000/timing['minimum_period_ns']-result['fmax_mhz']) < 1e-9
    serial = read(RUN/'serial_phase_identity.json')
    assert serial['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [(row['phase'],row['returncode']) for row in serial['phases']] == [('timing',0),('performance',0)]
    ipc = read(RUN/'result/ipc.json')
    assert sha(RUN/'result/ipc.json') == identity['ipc_sha256']
    assert len(ipc['results']) == 6 and ipc['latency'] == 10
    course = RUN/'source/.deps/RISC-V-CPU-2026'
    names = sorted(path.name for path in (course/'testcases').glob('perf_*') if path.is_dir())
    assert sorted(row['name'] for row in ipc['results']) == names
    raw = (RUN/'result/perf.log').read_text(encoding='utf-8')
    observed = re.findall(r'^(perf_\S+)\s+(\d+)\s+(\d+)\s+[0-9.]+$',raw,re.MULTILINE)
    assert sorted((name,int(inst),int(cycles)) for name,inst,cycles in observed) == sorted((row['name'],row['instructions'],row['cycles']) for row in ipc['results'])
    for row in ipc['results']:
        case = course/'testcases'/row['name']
        assert sha(case/'program.data') == row['program_sha256']
        assert sha(case/'metrics.json') == row['metrics_sha256']
        assert read(case/'metrics.json')['dynamic_instructions'] == row['instructions']
        assert row['cycles'] > 0 and row['ipc'] == row['instructions']/row['cycles']
    computed_ipc = math.exp(sum(math.log(row['ipc']) for row in ipc['results'])/6)
    assert abs(computed_ipc-result['ipc']) < 1e-12
    assert result['official_perf_expected_results_passed']
    plan = read(CLOSING/'closing_plan.json')
    closing = read(CLOSING/'closing_result.json')
    phase = read(CLOSING/'phase.json')
    assert phase['status'] == closing['status'] == 'CLOSING_CORRECTNESS_COMPLETE'
    assert sha(CLOSING/'closing_result.json') == phase['result_sha256']
    combined = read(COMBINED)
    assert sha(COMBINED) == active['closing_result_sha256']
    assert combined['original_timeout_evidence_preserved'] and combined['all_23_passed']
    for name,digest in combined['evidence_sha256'].items():
        assert sha(name) == digest, name
    assert sha(CLOSING/'closing_plan.json') == closing['plan_sha256']
    for name, digest in plan['frozen_sha256'].items():
        assert sha(name) == digest, name
    assert closing['executable_sha256'] == plan['executable_sha256'] == build['executable_sha256']
    text = (CLOSING/'official_stdout.log').read_text(encoding='utf-8')
    official_names = sorted(path.name for path in (course/'testcases').glob('correctness_*') if path.is_dir())
    assert len(official_names) == 19 and re.findall(r'^\[(correctness_[^\]]+)\]$',text,re.MULTILINE) == official_names == plan['official_cases']
    assert len(re.findall(r'^PASS cycles=\d+$',text,re.MULTILINE)) == 18
    assert 'Results: 18 passed, 1 failed' in text and closing['official_returncode'] == 1
    assert closing['official_passed_count'] == 18 and closing['official_failed_count'] == 1
    assert closing['all_23_passed'] is False and closing['official_all_passed'] is False
    blocks = list(re.finditer(r'^\[(correctness_[^\]]+)\]$',text,re.MULTILINE))
    unique_rows = {}
    for i,block in enumerate(blocks):
        body = text[block.end():blocks[i+1].start() if i+1 < len(blocks) else len(text)]
        cycles = re.findall(r'^PASS cycles=(\d+)$',body,re.MULTILINE)
        if block[1] == 'correctness_pi':
            assert not cycles and 'PASS' not in body
        else:
            assert len(cycles) == 1 and 0 < int(cycles[0]) <= 10000000
            unique_rows[block[1]] = (int(cycles[0]),10000000,'original_closing')
    error = (CLOSING/'official_stderr.log').read_text(encoding='utf-8').strip()
    assert error == 'FAIL: simulator exited with status 1: FAIL: timeout or finish before exit write response; cycles=10000000'
    pi_plan, pi_result, pi_phase = read(PI/'followup_plan.json'), read(PI/'followup_result.json'), read(PI/'phase.json')
    for name,digest in pi_plan['frozen_sha256'].items():
        assert sha(name) == digest, name
    assert sha(PI/'followup_result.json') == pi_phase['result_sha256']
    assert pi_result['plan_sha256'] == sha(PI/'followup_plan.json')
    assert pi_result['status'] == pi_phase['status'] == 'PI_BUDGET_FOLLOWUP_COMPLETE'
    assert pi_result['passed'] is True and pi_result['returncode'] == 0 and pi_phase['passed'] is True
    for key in ['source_manifest_sha256','executable_sha256','config_sha256','original_result_sha256']:
        assert pi_plan[key] == plan[key], key
    assert pi_result['executable_sha256'] == build['executable_sha256']
    assert pi_result['max_cycles'] == pi_plan['max_cycles'] == 48000000
    assert pi_result['latency'] == pi_plan['latency'] == 10 and pi_result['expected_u32'] == 112
    pi_text = (PI/'official_stdout.log').read_text(encoding='utf-8')
    assert re.findall(r'^\[(correctness_[^\]]+)\]$',pi_text,re.MULTILINE) == ['correctness_pi']
    assert re.findall(r'^PASS cycles=(\d+)$',pi_text,re.MULTILINE) == [str(pi_result['cycles'])]
    assert re.findall(r'^Results: (\d+) passed, (\d+) failed$',pi_text,re.MULTILINE) == [('1','0')]
    assert sha(PI/'official_stdout.log') == pi_result['official_stdout_sha256']
    assert sha(PI/'official_stderr.log') == pi_result['official_stderr_sha256']
    assert not (PI/'official_stderr.log').read_text(encoding='utf-8').strip()
    assert 36025632 <= pi_result['cycles'] <= 48000000
    unique_rows['correctness_pi'] = (pi_result['cycles'],48000000,'pi_budget_followup')
    assert sorted(unique_rows) == official_names
    assert {row['name']:(row['cycles'],row['max_cycles'],row['attempt']) for row in combined['official_rows']} == unique_rows
    for row in combined['official_rows']:
        case = course/'testcases'/row['name']
        assert row['program_sha256'] == sha(case/'program.data')
        assert row['expected_sha256'] == sha(case/'expected.txt')
    assert (course/'testcases/correctness_pi/expected.txt').read_text(encoding='utf-8').strip() == '112'
    assert combined['original_attempt']['result_sha256'] == sha(CLOSING/'closing_result.json')
    assert combined['pi_followup']['result_sha256'] == sha(PI/'followup_result.json')
    assert sha(CLOSING/'official_stdout.log') == closing['official_stdout_sha256']
    assert sha(CLOSING/'official_stderr.log') == closing['official_stderr_sha256']
    assert len(closing['edge_rows']) == 4
    for case,row in zip(plan['edge_cases'],closing['edge_rows']):
        assert case['name'] == row['name'] and row['returncode'] == 0
        stdout,stderr = CLOSING/(row['name']+'.stdout.log'),CLOSING/(row['name']+'.stderr.log')
        assert sha(stdout) == row['stdout_sha256'] and sha(stderr) == row['stderr_sha256']
        assert [line.strip() for line in stdout.read_text(encoding='utf-8').splitlines() if line.strip()] == [str(case['expected_u32'])]
        assert re.findall(r'^CPU2026 cycles=(\d+)$',stderr.read_text(encoding='utf-8'),re.MULTILINE) == [str(row['cycles'])]
        assert 0 < row['cycles'] <= case['max_cycles']
    architecture = read(ROOT/'build/cpu2026/er1_a109_architecture_source_audit_20261006.json')
    for name,digest in architecture['source_sha256'].items():
        assert sources[name] == digest == sha(ROOT/name)
    required = set('ADD ADDI AND ANDI AUIPC BEQ BGE BGEU BLT BLTU BNE DIV DIVU JAL JALR LB LBU LH LHU LUI LW MUL MULH MULHSU MULHU OR ORI REM REMU SB SH SLL SLLI SLT SLTI SLTIU SLTU SRA SRAI SRL SRLI SUB SW XOR XORI'.split())
    assert set(architecture['required_decoded_ops']) == required and len(required) == 45
    assert architecture['parameter_profile'] == active['materialized_top_defaults']
    assert result['ipc'] >= 1.1 and result['area_um2'] <= 36000 and result['fmax_mhz'] > 300
    report = ROOT/'reports/ER1_A109_Tier3_verified_2026-10-06.md'
    assert report.exists() and all((ROOT/name).exists() for name in ['reports/parameter_sensitivity.md','reports/architecture_exploration.md','docs/final_project_requirements.md'])
    audit = dict(status='CURRENT_ADOPTED_A109_FULL_OBJECTIVE_INDEPENDENTLY_VERIFIED',
        verified_at=datetime.now(timezone.utc).isoformat(),ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],area_um2=result['area_um2'],
        sram_area_um2=area['sram_area_um2'],sram_instances=93,main_source_files=41,backup_source_files=40,
        same_measured_source_and_executable_verified=True,official_six_perf_verified=True,official_19_correctness_verified=True,
        official_19_verified_across_two_attempts=True,original18_pass1_pi_timeout_preserved=True,
        pi_followup_cycles=pi_result['cycles'],pi_followup_max_cycles=48000000,
        frozen_four_boundary_verified=True,architecture_and_parameter_source_review_bound_to_current_files=True,
        report_and_historical_parameter_tradeoff_deliverables_preserved=True,
        new_builds_or_hardware_tests_run=False,arbitrary_parameter_dynamic_proof_claimed=False,full_isa_formal_proof_claimed=False,
        evidence_sha256={str(path):sha(path) for path in [Path(__file__),proof_path,active_path,report,ppa_path,RUN/'result/ipc.json',CLOSING/'closing_result.json',COMBINED,PI/'followup_result.json',PI/'followup_plan.json',PI/'official_stdout.log',PI/'official_stderr.log']})
    OUT.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print({key:value for key,value in audit.items() if key != 'evidence_sha256'})


if __name__ == '__main__':
    main()
