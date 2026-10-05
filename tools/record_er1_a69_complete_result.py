"""Bind the completed original A69 measurement; no tool runs/restarts."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a69_measurement import check, live, RUN

STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a69_complete_result_20261006.json'
REPORT = ROOT / 'reports/ER1_A69_result_and_A72_direction_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN / 'dispatch_identity.json')
    phases = read(RUN / 'serial_phase_identity.json')
    assert dispatch['process_id'] == phases['supervisor_pid'] == 44708
    assert not live(44708)
    assert phases['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [phase['phase'] for phase in phases['phases']] == ['timing', 'performance']
    assert all(phase['returncode'] == 0 for phase in phases['phases'])
    state = read(STATE)
    assert state['current_source_candidate'] == 'A72_branch_capture_redirect_ready'
    assert state['active_measurement_candidate'] == 'A69_same_edge_redirect_fetch'
    result = read(RUN / 'result/result.json')
    ipc = read(RUN / 'result/ipc.json')
    identity = read(RUN / 'result/measurement_identity.json')
    timing = read(RUN / 'result/timing_only.json')
    ppa = read(RUN / 'result/synth/opt/report.json')
    assert result['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert result['environment'] == identity['environment'] == 'WINDOWS_NATIVE'
    assert identity['source_manifest_sha256'] == timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert identity['toolchain_manifest_sha256'] == timing['toolchain_manifest_sha256'] == 'c08263a362cd79513f17701b6328f8fb14d41a315539006d7b7dd71113ee3fb5'
    assert timing['config_sha256'] == plan['config_sha256']
    assert sha(RUN / 'result/result.json') == identity['result_sha256'] == phases['result_sha256']
    assert sha(RUN / 'result/ipc.json') == identity['ipc_sha256']
    assert sha(RUN / 'result/synth/opt/report.json') == identity['official_report_sha256'] == timing['official_report_sha256']
    cpu = identity['prebuilt_cpu']
    assert cpu['status'] == 'COMPLETE' and cpu['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert sha(Path(cpu['executable'])) == cpu['executable_sha256']
    assert result['parameter_overrides'] == read(RUN / 'source_manifest.json')['parameter_overrides']
    assert result['official_perf_expected_results_passed'] and result['official_correctness_suite_not_run']
    assert not result['official_correctness_suite_passed']
    assert ipc['official_scripts_unmodified'] and ipc['official_sim_cpp_unmodified']
    assert result['latency'] == ipc['latency'] == 10
    assert len(ipc['results']) == 6
    log = (RUN / 'result/perf.log').read_text(encoding='utf-8')
    log_rows = {}
    for line in log.splitlines():
        match = re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)', line)
        if match:
            log_rows[match[1]] = (int(match[2]), int(match[3]))
    for row in ipc['results']:
        case = RUN / 'source/.deps/RISC-V-CPU-2026/testcases' / row['name']
        assert sha(case / 'program.data') == row['program_sha256']
        assert sha(case / 'metrics.json') == row['metrics_sha256']
        assert read(case / 'metrics.json')['dynamic_instructions'] == row['instructions']
        assert log_rows[row['name']] == (row['instructions'], row['cycles'])
        assert row['ipc'] == row['instructions'] / row['cycles']
    assert math.exp(sum(math.log(row['ipc']) for row in ipc['results']) / 6) == ipc['geomean_ipc'] == result['ipc']
    assert result['fmax_mhz'] == timing['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz']
    assert result['area_um2'] == timing['area_um2'] == ppa['area']['area_um2']
    area = {key: value for key, value in ppa['area'].items() if isinstance(value, (int, float))}
    assert abs(area['area_um2'] - area['logic_area_um2'] - area['sram_area_um2']) < 1e-6
    previous = state['best_measured_combined_result']
    metrics = dict(status=result['status'], candidate='A69_same_edge_redirect_fetch', run=str(RUN),
        process_id=44708, process_alive=False, terminal_artifact_authority='Original completed result/phase records and PID absent',
        ipc=result['ipc'], fmax_mhz=result['fmax_mhz'], minimum_period_ns=result['minimum_period_ns'],
        area_um2=result['area_um2'], sram_area_um2=area['sram_area_um2'],
        sequential_area_um2=area['sequential_area_um2'], combinational_area_um2=area['combinational_area_um2'],
        official_perf_expected_results_passed=True, full_correctness_not_run=True, full_correctness_passed=False,
        objective_numeric_met=False, source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_sha256=plan['candidate_sha256'], result_sha256=identity['result_sha256'],
        ipc_sha256=identity['ipc_sha256'], ppa_sha256=identity['official_report_sha256'], rows=ipc['results'])
    assert not (metrics['ipc'] >= 1.1 and metrics['fmax_mhz'] > 300 and metrics['area_um2'] <= 36000)
    delta = dict(ipc_relative_percent=(metrics['ipc']/previous['ipc']-1)*100,
        fmax_mhz=metrics['fmax_mhz']-previous['fmax_mhz'],
        fmax_relative_percent=(metrics['fmax_mhz']/previous['fmax_mhz']-1)*100,
        area_um2=metrics['area_um2']-previous['area_um2'],
        ipc_required_relative_gain_percent=(1.1/metrics['ipc']-1)*100)
    prior_rows = {row['name']: row for row in read(Path(previous['run']) / 'result/ipc.json')['results']}
    case_lines = []
    for row in ipc['results']:
        before = prior_rows[row['name']]
        assert before['program_sha256'] == row['program_sha256']
        case_lines.append(f"| {row['name']} | {before['cycles']} | {row['cycles']} | {row['ipc']:.6f} | {(row['ipc']/before['ipc']-1)*100:+.3f}% |")
    REPORT.write_text('\n'.join([
        '# A69 集中测量结果与 A72 修复方向', '',
        'A69 原始串行作业已正常结束。课程标准 Windows 原生工具、库、六项程序和冻结源码均绑定复核；没有重跑测试。', '',
        '| 指标 | A55R2 | A69 |', '|---|---:|---:|',
        f"| 六项 IPC 几何平均 | {previous['ipc']:.8f} | {metrics['ipc']:.8f} |",
        f"| 综合与 STA 估算频率 / MHz | {previous['fmax_mhz']:.5f} | {metrics['fmax_mhz']:.5f} |",
        f"| 总面积（含 SRAM）/ μm² | {previous['area_um2']:.5f} | {metrics['area_um2']:.5f} |", '',
        f"A69 IPC 提高 {delta['ipc_relative_percent']:.3f}%，总面积增加 {delta['area_um2']:.3f} μm²；频率下降 {abs(delta['fmax_relative_percent']):.3f}%，不能采用。频率和面积满足目标的已测综合最优记录仍是 A55R2。A69 IPC 距 1.1 尚需提高 {delta['ipc_required_relative_gain_percent']:.3f}%。", '',
        '六项性能程序均通过；完整19项正确性、RV32IM/恢复/参数专项覆盖仍未完成。没有将候选写入主实现。', '',
        '| 程序 | A55R2 周期 | A69 周期 | A69 IPC | IPC 变化 |', '|---|---:|---:|---:|---:|',
        *case_lines, '',
        '新 STA 的五条最慢路径共享主要通路，最长数据到达4.293 ns：pending recovery tag → ROB full-GEN qualification → MDU cancellation/ordinary completion live-ready → redirect-dependent ICache response → predictor query → RAS。2 ns映射约束下报告负裕量，目标300 MHz仍需实际路径缩短；没有加入 false-path。', '',
        '独立源码工作：A70 在有效直接恢复边沿计算准确的下一周期 ROB 信用；A71 允许当前单报告端口上报的第二项已完成加载同时参与两项前缀回收；A72 将分支捕获中的通用 ALU ready 按现有 valid+redirect+!pending 条件展开为等价的重定向优先规则。A72 保留实际 ALU 消费规则与全部有效性/代数检查，删除完成网络 ready 对捕获逻辑的结构依赖。', '',
        'A70–A72 均未运行 HDL/仿真/综合/STA；未证明频率已恢复，收益也未测得。三项修改不增加声明的 FF/SRAM/流水边沿，但新增或改写组合门的映射成本与剩余路径仍待评估。', '',
        f'- [A69 结果]({(RUN / "result/result.json").as_posix()})',
        f'- [A69 IPC]({(RUN / "result/ipc.json").as_posix()})',
        f'- [A69 时序路径]({(RUN / "result/synth/opt/critical_paths.json").as_posix()})',
        f'- [A72 源码审查](F:/CPU2026Candidates/tier3_er1_20261005/A72_source_review.json)',
        '', '后续先继续检查恢复到前端的剩余依赖，再汇报并安排有充分依据的下一次集中测量。', '',
    ]), encoding='utf-8')
    artifacts = {str(path): sha(path) for path in [RUN / 'result/result.json', RUN / 'result/ipc.json',
        RUN / 'result/measurement_identity.json', RUN / 'result/synth/opt/report.json', RUN / 'result/perf.log',
        RUN / 'source_manifest.json', RUN / 'serial_phase_identity.json', Path(cpu['executable']), REPORT]}
    proof = dict(status='A69_COMPLETE_RESULT_WITH_FREQUENCY_REGRESSION', recorded_at=datetime.now(timezone.utc).isoformat(),
        new_tests_started=False, original_pid_absent=True, source_file_count=157,
        source_cpu_ipc_ppa_identity_verified=True, metrics=metrics, previous_incumbent=previous,
        delta_vs_a55r2=delta, artifacts_sha256=artifacts, full_correctness_suite_not_run=True,
        selected_as_combined_incumbent=False, pending_source_candidate=state['current_source_candidate'],
        pending_source_has_no_measured_metrics=True, adopted_to_main=False, goal_complete=False)
    write(PROOF, proof)
    state.update(status='A69_COMPLETE_FREQ_REGRESSION_A72_PENDING_SOURCE_UNTESTED',
        last_measured_candidate=metrics['candidate'], last_measured_result=metrics,
        active_measurement_candidate=None, active_measurement_process_ids=[], measurement_process_alive=False,
        measurement_completed_at=phases['phases'][-1]['completed_at'], measurement_terminal_proof=str(PROOF),
        measurement_terminal_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A69_COMPLETE_RESULT_BOUND_FREQ_REGRESSION_A72_SOURCE_PENDING',
        last_background_progress=str(PROOF), last_background_progress_sha256=sha(PROOF),
        goal_complete=False, candidates_adopted=False,
        next_work=['Continue removing remaining recovery-to-frontend timing dependencies in independent candidates.',
            'Report before the next justified coherent native measurement; do not retest after each edit.',
            'Retain A55R2 incumbent until a measured candidate meets frequency/area and improves IPC.',
            'Before adoption prove all objective metrics and complete required RV32IM/OoO/commit/MMIO/parameter correctness.'])
    write(STATE, state)
    print(dict(status=proof['status'], metrics={k: metrics[k] for k in ['ipc','fmax_mhz','area_um2']},
        delta_vs_a55r2=delta, proof=str(PROOF), proof_sha256=sha(PROOF),
        best_combined_candidate=state['best_measured_combined_candidate'], pending_candidate=state['current_source_candidate'], new_tests_started=False))


if __name__ == '__main__':
    main()
