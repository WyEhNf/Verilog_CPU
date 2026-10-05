"""Bind original completed A75 performance/STA and retain untested A78 source."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a75_measurement import check, live, RUN

STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a75_complete_result_20261006.json'
REPORT = ROOT / 'reports/ER1_A75_result_and_A78_direction_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN / 'dispatch_identity.json')
    phases = read(RUN / 'serial_phase_identity.json')
    assert dispatch['process_id'] == phases['supervisor_pid'] == 42732
    assert not live(42732)
    assert phases['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [phase['phase'] for phase in phases['phases']] == ['timing','performance']
    assert all(phase['returncode'] == 0 for phase in phases['phases'])
    state = read(STATE)
    assert state['current_source_candidate'] == 'A78_lsq_forward_onehot'
    assert state['active_measurement_candidate'] == 'A75_branch_capture_phase_valid'
    pending = Path(state['pending_source_candidate'])
    assert sha(pending/'candidate.json') == state['pending_source_candidate_sha256']
    for name,digest in read(pending/'candidate.json')['source_sha256'].items():
        assert sha(pending/name) == digest,name
    source_proof = Path(state['last_source_progress_proof'])
    assert sha(source_proof) == state['last_source_progress_proof_sha256']
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(source_proof)['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest,name
    result = read(RUN/'result/result.json')
    ipc = read(RUN/'result/ipc.json')
    identity = read(RUN/'result/measurement_identity.json')
    timing = read(RUN/'result/timing_only.json')
    ppa = read(RUN/'result/synth/opt/report.json')
    assert result['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert result['environment'] == identity['environment'] == 'WINDOWS_NATIVE'
    assert identity['source_manifest_sha256'] == timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert identity['toolchain_manifest_sha256'] == timing['toolchain_manifest_sha256'] == 'c08263a362cd79513f17701b6328f8fb14d41a315539006d7b7dd71113ee3fb5'
    assert timing['config_sha256'] == plan['config_sha256']
    assert sha(RUN/'result/result.json') == identity['result_sha256'] == phases['result_sha256']
    assert sha(RUN/'result/ipc.json') == identity['ipc_sha256']
    assert sha(RUN/'result/synth/opt/report.json') == identity['official_report_sha256'] == timing['official_report_sha256']
    cpu = identity['prebuilt_cpu']
    assert cpu['status'] == 'COMPLETE' and cpu['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert sha(Path(cpu['executable'])) == cpu['executable_sha256']
    assert result['parameter_overrides'] == read(RUN/'source_manifest.json')['parameter_overrides']
    assert result['official_perf_expected_results_passed'] and result['official_correctness_suite_not_run']
    assert not result['official_correctness_suite_passed']
    assert ipc['official_scripts_unmodified'] and ipc['official_sim_cpp_unmodified']
    assert result['latency'] == ipc['latency'] == 10 and len(ipc['results']) == 6
    log_rows = {}
    for line in (RUN/'result/perf.log').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)',line)
        if match: log_rows[match[1]] = (int(match[2]),int(match[3]))
    for row in ipc['results']:
        case = RUN/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
        assert sha(case/'program.data') == row['program_sha256']
        assert sha(case/'metrics.json') == row['metrics_sha256']
        assert read(case/'metrics.json')['dynamic_instructions'] == row['instructions']
        assert log_rows[row['name']] == (row['instructions'],row['cycles'])
        assert row['ipc'] == row['instructions']/row['cycles']
    assert math.exp(sum(math.log(row['ipc']) for row in ipc['results'])/6) == ipc['geomean_ipc'] == result['ipc']
    assert result['fmax_mhz'] == timing['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz']
    assert result['area_um2'] == timing['area_um2'] == ppa['area']['area_um2']
    area = {key:value for key,value in ppa['area'].items() if isinstance(value,(int,float))}
    assert abs(area['area_um2']-area['logic_area_um2']-area['sram_area_um2']) < 1e-6
    before = state['last_measured_result']
    assert before['candidate'] == 'A69_same_edge_redirect_fetch'
    incumbent = state['best_measured_combined_result']
    metrics = dict(status=result['status'],candidate='A75_branch_capture_phase_valid',run=str(RUN),
        process_id=42732,process_alive=False,terminal_artifact_authority='Original serial rc0/rc0 result and PID absent',
        ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],minimum_period_ns=result['minimum_period_ns'],area_um2=result['area_um2'],
        sram_area_um2=area['sram_area_um2'],sequential_area_um2=area['sequential_area_um2'],
        combinational_area_um2=area['combinational_area_um2'],
        official_perf_expected_results_passed=True,full_correctness_not_run=True,full_correctness_passed=False,
        objective_numeric_met=False,source_manifest_sha256=plan['source_manifest_sha256'],candidate_sha256=plan['candidate_sha256'],
        result_sha256=identity['result_sha256'],ipc_sha256=identity['ipc_sha256'],ppa_sha256=identity['official_report_sha256'],rows=ipc['results'])
    assert metrics['fmax_mhz'] < 300 and metrics['ipc'] < 1.1
    delta = dict(ipc_relative_percent=(metrics['ipc']/before['ipc']-1)*100,
        fmax_mhz=metrics['fmax_mhz']-before['fmax_mhz'],
        area_um2=metrics['area_um2']-before['area_um2'],
        ipc_required_relative_gain_percent=(1.1/metrics['ipc']-1)*100,
        period_reduction_to300_ns=metrics['minimum_period_ns']-1000/300,
        area_margin_um2=36000-metrics['area_um2'])
    previous_rows = {row['name']:row for row in read(Path(before['run'])/'result/ipc.json')['results']}
    case_lines = []
    changes = []
    for row in ipc['results']:
        prior = previous_rows[row['name']]
        assert row['program_sha256'] == prior['program_sha256'] and row['instructions'] == prior['instructions']
        saved = prior['cycles']-row['cycles']
        changes.append(dict(name=row['name'],cycles_before=prior['cycles'],cycles_after=row['cycles'],cycles_saved=saved))
        case_lines.append(f"| {row['name']} | {prior['cycles']} | {row['cycles']} | {saved} |")
    REPORT.write_text('\n'.join([
        '# A75 集中测量结果与下一步', '',
        '原始PID42732已正常结束；综合/STA与性能串行阶段返回码均为0。Windows原生课程固定工具、库、冻结157文件、配置、实际sim.exe、六项程序与计数均绑定复核，没有重跑测试。', '',
        '| 指标 | A69 | A75 | 频率/面积合规的当前最优A55R2 |', '|---|---:|---:|---:|',
        f"| 六项IPC几何平均 | {before['ipc']:.8f} | {metrics['ipc']:.8f} | {incumbent['ipc']:.8f} |",
        f"| 综合/STA估算频率 MHz | {before['fmax_mhz']:.5f} | {metrics['fmax_mhz']:.5f} | {incumbent['fmax_mhz']:.5f} |",
        f"| 含SRAM面积 μm² | {before['area_um2']:.5f} | {metrics['area_um2']:.5f} | {incumbent['area_um2']:.5f} |", '',
        f"A75频率增加{delta['fmax_mhz']:.5f}MHz，但仍比300MHz低{300-metrics['fmax_mhz']:.5f}MHz；最小周期还需缩短超过{delta['period_reduction_to300_ns']*1000:.3f}ps。面积余量{delta['area_margin_um2']:.3f}μm²。IPC相对A69仅增加{delta['ipc_relative_percent']:.6f}%，距离1.1仍需相对提升{delta['ipc_required_relative_gain_percent']:.4f}%。", '',
        'A70–A75集中批次只有qsort减少33周期，其余五项完全相同。恢复ROB信用/第二LSQ回报回收的预期IPC收益没有在这组程序中兑现；不能将时序改善当作IPC改善，也不能继续拿旧A36的重叠停顿计数声称现有候选能达到1.1。', '',
        '| 程序 | A69周期 | A75周期 | 减少周期 |', '|---|---:|---:|---:|',*case_lines,'',
        '六项性能程序均通过，完整19项正确性与RV32IM/恢复/参数专项尚未验证。A75不满足频率与IPC目标，未采用；合规约束下最优仍是A55R2。', '',
        '最新五条STA慢路径均由LSQ请求选择、二次状态读取、逐字节前递到状态寄存器，最长数据到达3.282ns。A77提前计算并随原选择树传递直接旁路资格；A78将最年轻重叠存储选择改为等价的互斥掩码。二者无新增FF/SRAM/边沿，针对这次已测瓶颈，但尚未测试。', '',
        'A76队首返回完成/回收及其17位持有标签状态也尚未测试。A76–A78累计IPC、面积、频率未知，不能套用A75指标。继续审查有实际周期收益的结构修改，形成完整批次后再测试前汇报。', '',
        f'- [A75原结果]({(RUN/"result/result.json").as_posix()})',
        f'- [A75 IPC]({(RUN/"result/ipc.json").as_posix()})',
        '- [A77–A78源级审查报告](E:/Verilog_cpu/reports/ER1_A75_partial_PPA_A77_A78_source_changes_2026-10-06.md)', '',
    ]),encoding='utf-8')
    artifact_paths = [RUN/'result/result.json',RUN/'result/ipc.json',RUN/'result/measurement_identity.json',
        RUN/'result/timing_only.json',RUN/'result/synth/opt/report.json',RUN/'result/synth/opt/critical_paths.json',
        RUN/'result/perf.log',RUN/'source_manifest.json',RUN/'serial_phase_identity.json',
        RUN/'course_windows_config.json',Path(cpu['executable']),REPORT]
    proof = dict(status='A75_COMPLETE_RESULT_FREQ299_IPC_GAIN_NEGLIGIBLE',recorded_at=datetime.now(timezone.utc).isoformat(),
        new_tests_started=False,original_pid_absent=True,source_file_count=157,source_cpu_ipc_ppa_identity_verified=True,
        metrics=metrics,previous_a69_result=before,delta_vs_a69=delta,case_cycle_changes=changes,
        previous_incumbent=incumbent,artifacts_sha256={str(p):sha(p) for p in artifact_paths},
        full_correctness_suite_not_run=True,selected_as_combined_incumbent=False,
        pending_source_candidate=state['current_source_candidate'],pending_source_has_no_measured_metrics=True,
        previous_source_progress_proof=str(source_proof),previous_source_progress_proof_sha256=sha(source_proof),
        adopted_to_main=False,main_eu_source_unchanged=True,goal_complete=False)
    write(PROOF,proof)
    state.update(status='A75_COMPLETE_FREQ299_A78_PENDING_SOURCE_UNTESTED',last_measured_candidate=metrics['candidate'],
        last_measured_result=metrics,active_measurement_candidate=None,active_measurement_process_ids=[],
        measurement_process_alive=False,last_completed_measurement_process_id=42732,
        measurement_completed_at=phases['phases'][-1]['completed_at'],measurement_terminal_proof=str(PROOF),
        measurement_terminal_proof_sha256=sha(PROOF),last_measured_pretest_report=state['measurement_pretest_report'],
        last_measured_pretest_report_sha256=state['measurement_pretest_report_sha256'],
        previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A75_COMPLETE_RESULT_BOUND_A77_A78_MEASURED_LSQ_TIMING_DIRECTION',
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        goal_complete=False,candidates_adopted=False,
        next_work=['Continue source review and timing changes in untested A78 descendants against measured LSQ path.',
            'Investigate removing ready-store RS/AGU/ordinary-completion waits with exact LSQ/ROB ownership.',
            'Report before one materially justified native complete-batch measurement; no per-edit testing.',
            'Retain A55R2 until measured >300MHz and <=36000um2 with higher IPC, target1.1.',
            'Prove full architecture/correctness/parameter requirements before adoption.'])
    for key in ['active_measurement_partial_metrics','active_measurement_critical_proof','active_measurement_critical_proof_sha256',
                'active_measurement_ppa_progress_report','active_measurement_ppa_progress_report_sha256']:
        state['last_a75_'+key]=state.get(key)
        state[key]=None
    write(STATE,state)
    print(dict(status=proof['status'],metrics={k:metrics[k] for k in ['ipc','fmax_mhz','area_um2']},
        delta_vs_a69=delta,proof=str(PROOF),proof_sha256=sha(PROOF),pending_candidate=state['current_source_candidate'],
        best_combined_candidate=state['best_measured_combined_candidate'],new_tests_started=False))


if __name__ == '__main__':
    main()
