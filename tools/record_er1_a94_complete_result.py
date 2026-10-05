"""Bind the completed original A94 measurement; do not start tests."""
from datetime import datetime, timezone
import math
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a94_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json'
REPORT = ROOT/'reports/ER1_A94_complete_result_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    state = read(STATE)
    dispatch = read(RUN/'dispatch_identity.json')
    phases = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phases['supervisor_pid'] == state['measurement_process_id'] == 84416
    assert not live(84416) and phases['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [(p['phase'],p['returncode']) for p in phases['phases']] == [('timing',0),('performance',0)]
    result = read(RUN/'result/result.json')
    ipc = read(RUN/'result/ipc.json')
    identity = read(RUN/'result/measurement_identity.json')
    timing = read(RUN/'result/timing_only.json')
    ppa = read(RUN/'result/synth/opt/report.json')
    build = read(RUN/'native_build/build_identity.json')
    assert result['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert ipc['status'] == identity['status'] == build['status'] == 'COMPLETE'
    assert sha(RUN/'result/result.json') == identity['result_sha256'] == phases['result_sha256']
    assert sha(RUN/'result/ipc.json') == identity['ipc_sha256']
    assert sha(RUN/'result/synth/opt/report.json') == identity['official_report_sha256'] == timing['official_report_sha256']
    assert identity['source_manifest_sha256'] == build['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    assert identity['prebuilt_cpu']['executable_sha256'] == build['executable_sha256'] == sha(build['executable'])
    assert Path(build['executable']).read_bytes()[:2] == b'MZ'
    assert result['official_perf_expected_results_passed']
    assert result['official_correctness_suite_not_run'] and not result['official_correctness_suite_passed']
    assert identity['ipc_numerator'] == 'official metrics.json' and result['latency'] == ipc['latency'] == 10
    assert ipc['official_scripts_unmodified'] and ipc['official_sim_cpp_unmodified']
    assert sorted(r['name'] for r in ipc['results']) == plan['perf_cases'] and len(ipc['results']) == 6
    old = read(ROOT/'build/cpu2026/er1_a83_complete_result_20261006.json')['metrics']
    old_rows = {r['name']:r for r in old['rows']}
    for row in ipc['results']:
        reference = old_rows[row['name']]
        assert row['instructions'] == reference['instructions'] and row['cycles'] > 0
        assert row['program_sha256'] == reference['program_sha256'] and row['metrics_sha256'] == reference['metrics_sha256']
        assert row['ipc'] == row['instructions']/row['cycles']
    geometric = math.exp(sum(math.log(r['ipc']) for r in ipc['results'])/6)
    assert math.isclose(geometric,ipc['geomean_ipc'],rel_tol=1e-14)
    assert result['ipc'] == ipc['geomean_ipc']
    assert result['fmax_mhz'] == timing['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz']
    assert result['area_um2'] == timing['area_um2'] == ppa['area']['area_um2']
    assert result['ipc'] >= 1.1 and result['area_um2'] <= 36000 and result['fmax_mhz'] < 300
    assert not result['thread_objective_numeric_requirements_met']
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    pending = Path(state['pending_source_candidate'])
    assert pending.name == 'A98_saved_identity_word_mask' and sha(pending/'candidate.json') == state['pending_source_candidate_sha256']
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    metrics = dict(status=result['status'],candidate='A94_localparam_dependency_order',run=str(RUN),
        process_id=84416,process_alive=False,terminal_artifact_authority='Original serial rc0/rc0 result and PID absent',
        ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],minimum_period_ns=timing['minimum_period_ns'],area_um2=result['area_um2'],
        sram_area_um2=ppa['area']['sram_area_um2'],sequential_area_um2=ppa['area']['sequential_area_um2'],
        combinational_area_um2=ppa['area']['combinational_area_um2'],official_perf_expected_results_passed=True,
        full_correctness_not_run=True,full_correctness_passed=False,objective_numeric_met=False,
        source_manifest_sha256=plan['source_manifest_sha256'],candidate_sha256=plan['candidate_sha256'],
        result_sha256=sha(RUN/'result/result.json'),ipc_sha256=sha(RUN/'result/ipc.json'),ppa_sha256=sha(RUN/'result/synth/opt/report.json'),
        rows=ipc['results'])
    delta = dict(ipc=result['ipc']-old['ipc'],ipc_percent=(result['ipc']/old['ipc']-1)*100,
        fmax_mhz=result['fmax_mhz']-old['fmax_mhz'],frequency_percent=(result['fmax_mhz']/old['fmax_mhz']-1)*100,
        area_um2=result['area_um2']-old['area_um2'],area_margin_um2=36000-result['area_um2'],
        ipc_drop_margin_percent=(1-1.1/result['ipc'])*100,
        minimum_period_reduction_required_ps=(timing['minimum_period_ns']-1000/300)*1000)
    table = '\n'.join(f"| {r['name']} | {r['instructions']} | {r['cycles']} | {r['ipc']:.8f} |" for r in ipc['results'])
    REPORT.write_text(f'''# A94完整三指标结果

原监督PID84416已不存在，timing/performance各返回0，完整结果和源码manifest/配置/PPA/IPC/课程程序哈希/原native sim.exe身份匹配。只读取既有终态，没有启动测试或重建任务。

**IPC {result['ipc']:.9f}；Fmax {result['fmax_mhz']:.9f}MHz；总面积含SRAM {result['area_um2']:.6f}μm²。** 六性能答案通过，完整19正确性未运行，尚未采用。IPC和面积达标，频率尚未严格>300MHz；目标仍未达成。

对比A83：IPC提高{delta['ipc_percent']:.4f}%，频率提高{delta['frequency_percent']:.4f}%（{delta['fmax_mhz']:.6f}MHz），面积增加{delta['area_um2']:.6f}μm²，时序/SRAM面积相同。面积余量{delta['area_margin_um2']:.6f}μm²，IPC到1.1可下降余量{delta['ipc_drop_margin_percent']:.4f}%，周期还需缩短超过{delta['minimum_period_reduction_required_ps']:.6f}ps。

| 程序 | 动态指令 | 周期 | IPC |
|---|---:|---:|---:|
{table}

IPC使用原课程metrics.json分子、原程序和latency10，每程序原1000000周期上限，几何平均重新核对。最慢路径仍见前一份PPA进度证明：LSQ报告边界/held→saved identity query→当前ROB资格→完成选择→入队/分配GEN控制，最大数据到达约3.385ns。_223268_驱动61负载、373.5ps单元延迟，后级INV167.7ps；同源stage组合过载是新优化依据，不当作保证节省。

当前待测A98继承A95直接地址分类、A96多存储准备，并新增A97容量前算/A98报告掩码分组；四项尚无实测。A94已满足IPC，下一批优先保持其周期行为，在频率配置关闭A96额外多存储路径（保留该选项供后续权衡），继续纯等价的容量/报告驱动/合并优化，以控制201μm²余量并专注频率；不改变最终目标或删功能。

原Windows课程工具、库、报告约束、完整RV32IM/OoO/顺序提交/MMIO/参数化保持；无WSL。主E EU40源码哈希相同。频率/面积达标的已测最优仍A55R2（IPC1.01714182、306.86245MHz、35480.53090μm²），IPC不足不能当最终方案。新批先汇报再集中测量，目标数值明确改善后、采用前仍需完整19正确性及M/GEN/恢复/MMIO/参数覆盖。
''',encoding='utf-8')
    artifacts = [RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'dispatch_identity.json',RUN/'serial_phase_identity.json',
        RUN/'result/result.json',RUN/'result/ipc.json',RUN/'result/timing_only.json',RUN/'result/measurement_identity.json',
        RUN/'result/synth/opt/report.json',RUN/'result/synth/opt/critical_paths.json',RUN/'native_build/build_identity.json',Path(build['executable']),REPORT]
    proof = dict(status='A94_COMPLETE_METRICS_SOURCE_CPU_IPC_PPA_IDENTITY_BOUND',recorded_at=datetime.now(timezone.utc).isoformat(),
        new_tests_started=False,original_pid_absent=True,source_cpu_ipc_ppa_identity_verified=True,metrics=metrics,
        previous_a83_result=old,delta_vs_a83=delta,artifacts_sha256={str(p):sha(p) for p in artifacts},
        full_correctness_suite_not_run=True,pending_source_candidate=str(pending),pending_source_has_no_measured_metrics=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A94_COMPLETE_PENDING_A98_FREQUENCY_SOURCE',previous_measured_result=state['last_measured_result'],
        last_measured_candidate=metrics['candidate'],last_measured_result=metrics,candidate_ipc=metrics['ipc'],
        candidate_fmax_mhz=metrics['fmax_mhz'],candidate_area_um2=metrics['area_um2'],candidate_metrics_belong_to=metrics['candidate'],
        active_measurement_candidate=None,active_measurement_process_ids=[],measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,candidate_tests_started=False,pending_source_candidate_tests_started=False,
        candidate_correctness_passed=False,candidate_correctness_finished=False,candidate_correctness_not_run=True,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_completed_measurement_proof=str(PROOF),last_completed_measurement_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A94_FULL_IPC1_115262_FMAX290_249_AREA35798_IDENTITY_BOUND_FREQUENCY_ONLY_REMAINING',
        candidates_adopted=False,goal_complete=False,
        next_work='Keep completed original A94 PID84416/results immutable. IPC/area target achieved in measured candidate, frequency below300. Prepare cycle-equivalent frequency profile with A96 optional batch disabled and A95/A97/A98 plus measured-stage balanced identity aggregation. Do not start tests until supported changes exhausted and pre-reported; full correctness/architecture coverage before adoption.')
    write(STATE,state)
    print(dict(status=proof['status'],metrics={k:metrics[k] for k in ['ipc','fmax_mhz','area_um2']},proof=str(PROOF),proof_sha256=sha(PROOF),new_tests_started=False,goal_complete=False))


if __name__ == '__main__':
    main()
