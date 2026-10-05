"""Freeze A109 completed PPA evidence without repeating a hardware measurement."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a109_measurement import check, live, RUN

PROOF = ROOT/'build/cpu2026/er1_a109_partial_ppa_20261006.json'
REPORT = ROOT/'reports/ER1_A109_partial_PPA_2026-10-06.md'
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 103132
    assert phase['phases'][0]['phase'] == 'timing' and phase['phases'][0]['returncode'] == 0
    timing_path = RUN/'result/timing_only.json'
    timing = read(timing_path)
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert sha(timing_path) == phase['timing_report_sha256']
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    ppa_path = RUN/'result/synth/opt/report.json'
    assert sha(ppa_path) == timing['official_report_sha256']
    official = read(ppa_path)
    area = {key:official['area'][key] for key in ['combinational_area_um2',
             'sequential_area_um2','sram_area_um2','area_um2']}
    assert abs(sum(area[key] for key in ['combinational_area_um2','sequential_area_um2',
               'sram_area_um2'])-area['area_um2']) < 1e-8
    assert official['timing']['timing_analyzed'] and timing['fmax_mhz'] > 300 and area['area_um2'] <= 36000
    checks_path = RUN/'result/synth/opt/critical_paths.json'
    paths = []
    for row in read(checks_path)['checks'][:5]:
        anchors = []
        seen = set()
        for point in row['source_path']:
            net = point.get('net','')
            if net not in seen and any(term in net for term in ['branch_capture_owner.data_o',
                'recovery_preview_tree.signal_i','head_choice_tree.signal_i','g_live.data[',
                'tag_tree.signal_i[21]','selection_tree.signal_i[0]',
                'integer_subtract_tree.signal_i','raw_forward_mask','mmio_exit_request_tree.signal_i']):
                anchors.append(dict(net=net,arrival_ns=point['arrival']*1e9))
                seen.add(net)
        paths.append(dict(startpoint=row['startpoint'],endpoint=row['endpoint'],
            data_arrival_ns=row['data_arrival_time']*1e9,slack_ns=row['slack']*1e9,anchors=anchors))
    state = read(STATE)
    previous = state['last_measured_full_result']
    assert previous['candidate'] == 'A94_localparam_dependency_order'
    partial = dict(candidate='A109_rob_occupancy_distribution',
        candidate_sha256=plan['candidate_sha256'],run=str(RUN),
        source_manifest_sha256=plan['source_manifest_sha256'],status='PPA_COMPLETE_IPC_PENDING',
        fmax_mhz=timing['fmax_mhz'],minimum_period_ns=timing['minimum_period_ns'],
        **area,ipc=None,ipc_still_unknown=True,full_correctness_not_run=True,
        adopted=False,objective_met=False)
    observation = dict(observed_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),
        process_id=103132,process_alive=live(103132),phase=phase['status'],
        final_result_exists=(RUN/'result/result.json').exists())
    REPORT.write_text(f'''# A109：频率和含SRAM面积达到目标，IPC尚待原运行

原课程Windows native测量PID103132的综合/STA阶段returncode0，冻结manifest/工具/源/配置检查保持。只读取同一个原结果，不重启或额外测量。

| 指标 | 原A109实测 |
|---|---:|
| Fmax | {timing['fmax_mhz']:.9f} MHz |
| 最低周期 | {timing['minimum_period_ns']:.9f} ns |
| 总面积（含SRAM） | {area['area_um2']:.9f} um² |
| 组合面积 | {area['combinational_area_um2']:.9f} um² |
| 时序面积 | {area['sequential_area_um2']:.9f} um² |
| SRAM面积 | {area['sram_area_um2']:.9f} um² |
| IPC | 尚未完成，不能继承A94 |

相比A94，频率提高{(timing['fmax_mhz']/previous['fmax_mhz']-1)*100:.4f}%，总面积增加{area['area_um2']-previous['area_um2']:.6f}um²（{(area['area_um2']/previous['area_um2']-1)*100:.4f}%）。含SRAM面积余量{36000-area['area_um2']:.6f}um²。相比A105整批，频率增加{timing['fmax_mhz']-state['last_measured_result']['fmax_mhz']:.6f}MHz，面积减少{state['last_measured_result']['area_um2']-area['area_um2']:.6f}um²。不能把整批改善归因于其中单一修改。

课程报告使用2ns映射/报告时钟、50ps uncertainty、ideal clock/no parasitics；Fmax来自minimum-period搜索，2ns下负slack不等于300MHz未达标。原频率已超过300MHz，时序/面积通过后原manager自动按预汇报计划继续一次CPU构建和六perf，IPC/答案仍未完成。

新top5到达为{', '.join(f"{path['data_arrival_ns']:.3f}" for path in paths)}ns，前3条为branch_capture_tag→recovery_preview→LSQ headchoice→原rawproducer物理身份→RS唤醒/发射→ALU SUB/算术，后2条为LSQ forwarding/request→MMIO请求资格→dcache ready→selection payload写入。原completion data名称是rawproducer共享别名，不代表串行CDB仲裁。ALU仍为一周期结果寄存器，分块prefix是组合层，不是新增流水级。

A110/A111作为独立源候选继续保留，均未测/未采用；当前不派发它们。若原A109六perf答案通过且IPC>=1.1，再先汇报，复用完全相同exe/source/config执行19官方与4现有冻结边界程序，再完成关键参数/架构源审阅与主源采用。目标尚未完成。
''',encoding='utf-8')
    proof = dict(status='PROGRESS_A109_COURSE_PPA_COMPLETE_NUMERIC_FREQUENCY_AREA_PASS_IPC_PENDING',
        classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_observation=observation,partial_ppa=partial,paths=paths,
        timing_report_sha256=sha(timing_path),ppa_sha256=sha(ppa_path),
        critical_paths_sha256=sha(checks_path),config_sha256=sha(RUN/'course_windows_config.json'),
        original_frozen_source_check_passed=True,additional_tests_started=False,
        ipc_not_yet_claimed=True,goal_complete=False,adopted=False,
        artifacts_sha256={str(path):sha(path) for path in [REPORT,Path(__file__),timing_path,
            ppa_path,checks_path,RUN/'source_manifest.json',RUN/'measurement_plan.json']})
    write(PROOF,proof)
    state.update(active_measurement_partial_ppa=partial,active_measurement_partial_metrics=partial,
        active_measurement_critical_proof=str(PROOF),active_measurement_critical_proof_sha256=sha(PROOF),
        active_measurement_ppa_progress_report=str(REPORT),active_measurement_ppa_progress_report_sha256=sha(REPORT),
        measurement_process_alive=observation['process_alive'],measurement_last_observed_at=observation['observed_at'],
        measurement_last_observation=observation,previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification=proof['status'],goal_complete=False,candidates_adopted=False)
    write(STATE,state)
    print(dict(status=proof['status'],observation=observation,partial_ppa=partial,
        proof_sha256=sha(PROOF),goal_complete=False))


if __name__ == '__main__':
    main()
