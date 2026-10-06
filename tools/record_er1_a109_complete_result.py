"""Bind A109 three completed metrics to its original executable and source."""
from datetime import datetime, timezone
import math
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a109_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a109_complete_result_20261006.json'
REPORT = ROOT/'reports/ER1_A109_complete_metrics_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    assert not live(103132), 'Wait for original A109 supervisor'
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE' and phase['supervisor_pid'] == 103132
    assert [(p['phase'],p['returncode']) for p in phase['phases']] == [('timing',0),('performance',0)]
    result_path = RUN/'result/result.json'
    result = read(result_path)
    assert sha(result_path) == phase['result_sha256']
    identity_path = RUN/'result/measurement_identity.json'
    identity = read(identity_path)
    assert identity['status'] == 'COMPLETE' and identity['result_sha256'] == sha(result_path)
    assert identity['source_manifest_sha256'] == plan['source_manifest_sha256']
    ipc_path = RUN/'result/ipc.json'
    ipc = read(ipc_path)
    assert identity['ipc_sha256'] == sha(ipc_path) and ipc['status'] == 'COMPLETE' and len(ipc['results']) == 6
    calculated = math.exp(sum(math.log(row['instructions']/row['cycles']) for row in ipc['results'])/6)
    assert abs(calculated-result['ipc']) < 1e-12
    assert result['official_perf_expected_results_passed'] and result['latency'] == 10
    assert result['official_correctness_suite_not_run'] and not result['official_correctness_suite_passed']
    build_path = RUN/'native_build/build_identity.json'
    build = read(build_path)
    assert build['status'] == 'COMPLETE' and build['source_manifest_sha256'] == plan['source_manifest_sha256']
    executable = Path(build['executable'])
    assert sha(executable) == build['executable_sha256'] == identity['prebuilt_cpu']['executable_sha256']
    official_path = RUN/'result/synth/opt/report.json'
    assert identity['official_report_sha256'] == sha(official_path)
    area = {key:result['area'][key] for key in ['combinational_area_um2',
        'sequential_area_um2','sram_area_um2']}
    assert abs(sum(area.values())-result['area_um2']) < 1e-8
    met = result['fmax_mhz'] > 300 and result['area_um2'] <= 36000 and result['ipc'] >= 1.1
    assert result['thread_objective_numeric_requirements_met'] == met
    state = read(STATE)
    old = state['last_measured_full_result']
    assert old['candidate'] == 'A94_localparam_dependency_order'
    measured = dict(status=result['status'],candidate='A109_rob_occupancy_distribution',
        candidate_sha256=plan['candidate_sha256'],run=str(RUN),process_id=103132,process_alive=False,
        ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],minimum_period_ns=result['minimum_period_ns'],
        area_um2=result['area_um2'],**area,official_perf_expected_results_passed=True,
        full_correctness_not_run=True,full_correctness_passed=False,objective_numeric_met=met,
        source_manifest_sha256=plan['source_manifest_sha256'],result_sha256=sha(result_path),
        ipc_sha256=sha(ipc_path),ppa_sha256=sha(official_path),executable_sha256=sha(executable),rows=ipc['results'])
    REPORT.write_text(f'''# A109 同一次测量三项指标

原PID103132已结束，serial timing/performance均returncode0；冻结41候选源/157测量输入与课程工具检查保持，三项来自相同source manifest/config/CPU，不能与A110/A111源混用。

| 指标 | A109原课程Windows native实测 |
|---|---:|
| IPC（六perf GEOMEAN，latency10） | {result['ipc']:.12f} |
| 总面积（含SRAM） | {result['area_um2']:.9f} um² |
| Fmax | {result['fmax_mhz']:.9f} MHz |
| 最低周期 | {result['minimum_period_ns']:.9f} ns |

组合{area['combinational_area_um2']:.9f}、时序{area['sequential_area_um2']:.9f}、SRAM{area['sram_area_um2']:.9f}um²，总和与总面积一致。课程五份ASAP7RVTTT/FakeRAM、Yosys0.63/ABC/OpenSTA3.1/Verilator5.020固定版本，Windows native、原sim.cpp/testcase/metrics、latency10，ideal/no parasitics最低周期搜索。

相比A94，IPC变化{(result['ipc']/old['ipc']-1)*100:.6f}%，频率变化{(result['fmax_mhz']/old['fmax_mhz']-1)*100:.6f}%，总面积变化{(result['area_um2']/old['area_um2']-1)*100:.6f}%。严格三项数值目标{'达到' if met else '未达到'}；六性能答案通过。完整19课程+4现有冻结边界CPU程序尚未运行，主E源尚未采用，目标还不能宣布完成。

原CPU SHA256：{sha(executable)}。保留原成功结果文件，不重新构建/综合/跑perf；达到数值目标后先在对话汇报，再集中同exe执行19+4，完成架构/参数审阅后采用。A110/A111未测，单独保留，不把它们称为已达标方案。
''',encoding='utf-8')
    classification = 'PROGRESS_A109_ORIGINAL_THREE_METRICS_COMPLETE_'+('NUMERIC_GOAL_PASS_CLOSING_PENDING' if met else 'NUMERIC_GOAL_NOT_MET')
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        measured_result=measured,original_pid_absent=True,original_serial_returncodes=[0,0],
        source_and_executable_frozen_identity_verified=True,official_perf_expected_results_passed=True,
        new_builds_started=False,new_tests_started=False,goal_complete=False,main_source_adopted=False,
        artifacts_sha256={str(path):sha(path) for path in [Path(__file__),REPORT,result_path,identity_path,
            ipc_path,build_path,executable,official_path,RUN/'serial_phase_identity.json',RUN/'source_manifest.json',
            RUN/'course_windows_config.json',ROOT/'build/cpu2026/er1_a109_architecture_source_audit_20261006.json']})
    write(PROOF,proof)
    state.update(previous_measured_result=old,last_measured_full_result=measured,
        last_measured_candidate=measured['candidate'],last_measured_result=measured,
        last_completed_measurement_candidate=measured['candidate'],last_completed_measurement_run=str(RUN),
        last_completed_measurement_process_id=103132,last_completed_measurement_proof=str(PROOF),
        last_completed_measurement_proof_sha256=sha(PROOF),measurement_process_alive=False,
        measurement_completed_at=phase['phases'][-1]['completed_at'],
        measurement_terminal_proof=str(PROOF),measurement_terminal_proof_sha256=sha(PROOF),
        candidate_ipc=result['ipc'],candidate_fmax_mhz=result['fmax_mhz'],candidate_area_um2=result['area_um2'],
        candidate_metrics_belong_to=measured['candidate'],candidate_correctness_not_run=True,
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        goal_complete=False,candidates_adopted=False,
        status='A109_THREE_NUMERIC_GATES_PASS_CLOSING_PENDING' if met else 'A109_MEASUREMENT_COMPLETE_NUMERIC_GOAL_NOT_MET')
    if met:
        state.update(best_measured_combined_candidate=measured['candidate'],best_measured_combined_result=measured,
            best_measured_combined_selection_criterion='Same pinned-course build passes strictFmax>300, totalarea<=36000, IPC>=1.1 and six perf answers; full closing correctness/adoption pending')
    write(STATE,state)
    print(dict(status=classification,measured_result={key:measured[key] for key in ['candidate','ipc',
        'fmax_mhz','area_um2','executable_sha256','objective_numeric_met']},proof=str(PROOF),proof_sha256=sha(PROOF)))


if __name__ == '__main__':
    main()
