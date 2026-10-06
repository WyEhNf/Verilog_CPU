"""Read completed native PPA/STA artifacts, preserving pending-source and IPC identities."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import read, sha, write, optional
from manage_er1_a55_serial_measurement import check
from wait_frequency_directed_native import live

ROOT = Path('E:/Verilog_cpu')
RUN = Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
OUT = ROOT / 'build/cpu2026/er1_a55r2_partial_ppa_20261005.json'
REPORT = ROOT / 'reports/ER1_A55R2_partial_PPA_2026-10-05.md'


def main():
    assert not OUT.exists() and not REPORT.exists()
    plan = check()
    state = read(STATE)
    timing = read(RUN / 'result/timing_only.json')
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    assert timing['official_report_sha256'] == sha(RUN / 'result/synth/opt/report.json')
    paths_file = RUN / 'result/synth/opt/critical_paths.json'
    paths = read(paths_file)['checks']
    first = paths[0]
    named, increments = [], []
    previous = 0
    for node in first['source_path']:
        arrival = node.get('arrival', previous)
        delta = arrival - previous
        previous = arrival
        if delta > 0:
            increments.append(dict(instance=node['instance'], cell=node['cell'],
                delay_ns=delta*1e9, arrival_ns=arrival*1e9, capacitance_ff=node.get('capacitance', 0)*1e15))
        net = node.get('net', '')
        if net and not re.fullmatch(r'_\d+_', net) and (not named or named[-1]['net'] != net):
            named.append(dict(net=net, arrival_ns=arrival*1e9))
    assert 'g_nonblocking_dcache' in first['startpoint']
    assert any('query_request_lru' in n['net'] for n in named)
    assert any('g_apply_issue.live_read' in n['net'] for n in named)
    assert any('mdu_payload_selector' in n['net'] for n in named)
    dispatch = read(RUN / 'dispatch_identity.json')
    alive = live(dispatch['process_id'])
    phase = read(RUN / 'serial_phase_identity.json')
    result = optional(RUN / 'result/result.json')
    partial = dict(candidate='A55_predictor_bank_local_prefix_history', run=str(RUN),
        source_manifest_sha256=plan['source_manifest_sha256'],
        status=timing['status'], fmax_mhz=timing['fmax_mhz'], area_um2=timing['area_um2'],
        minimum_period_ns=timing['minimum_period_ns'], ipc=None, full_correctness_passed=False)
    old = state['last_measured_result']
    REPORT.write_text(f'''# A55R2 已完成PPA与实际关键路径

同一课程Windows原生工具/库/约束与冻结A55源码下，综合/STA已完成：估算Fmax **{timing['fmax_mhz']:.8f}MHz**，最小周期 **{timing['minimum_period_ns']:.8f}ns**，含SRAM总面积 **{timing['area_um2']:.6f}μm²**。比A41频率变化{timing['fmax_mhz']-old['fmax_mhz']:.8f}MHz（{(timing['fmax_mhz']/old['fmax_mhz']-1)*100:.5f}%），面积变化{timing['area_um2']-old['area_um2']:.6f}μm²。对严格300MHz与36000μm²上限的余量分别是{timing['fmax_mhz']-300:.8f}MHz和{36000-timing['area_um2']:.6f}μm²。

该结果绑定A55R2 manifest，不属于独立未测A60。IPC仍待当前运行完成，本记录不替换已完成三指标的A41；完整正确性/M/恢复/缓存/参数覆盖仍未完成，目标IPC≥1.1/面积≤36000/频率>300尚未证明。记录时原监督PID{dispatch['process_id']}{'存活' if alive else '已不存在'}，阶段{phase['status']}，完整result文件{'存在' if result else '不存在'}。

已保存STA最差slack路径起点是Dcache分组元数据寄存器，经过query_request_lru、bypass_load_hit、LSQ返回标记匹配和返回唤醒选择、RS物理唤醒/发射载荷、g_apply_issue.live_read、MDU入口载荷选择。第一条最差slack路径数据到达 **{first['data_arrival_time']*1e9:.5f}ns**；五条保存路径中最大数据到达{max(p['data_arrival_time'] for p in paths)*1e9:.5f}ns。不同终点setup预算不同，因此最大数据到达与最差slack并非同一排序。

这改变了优化优先级：A56–A60独立前端简化仍保留，但新的频率工作应优先审查RS选出指令之后才做ROB有效/代际查询、恢复资格再进入MDU入口的串联路径。考虑把恢复存活资格从已选指令改为每个RS注册行提前计算；必须保持完整代际与严格较老的资格、恰好一次发射，不能简单删除GEN检查或加false_path。增加读取视图的组合成本、ROB行扇出和当前519μm²左右预算需同时审查；方案尚未实现。

重定向同拍取指调查保留为IPC相关架构方向，待实际6perf结果和PC/epoch/filter/MSHR所有权推导后决定。此分析只读取已有STA JSON与综合报告，不重新运行HDL/综合/STA/CPU，也未把STA命名节点当作完整RTL连线等价证明。端点仍以工具私有实例名记录，尚未解析其业务寄存器身份。

数据：[课程时序阶段结果](F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005/result/timing_only.json)、[关键路径证据](E:/Verilog_cpu/build/cpu2026/er1_a55r2_partial_ppa_20261005.json)。
''', encoding='utf-8')
    proof = dict(status='A55R2_SAME_SOURCE_PPA_COMPLETE_IPC_PENDING_CRITICAL_REGION_CHANGED',
        recorded_at=datetime.now(timezone.utc).isoformat(), partial_metrics=partial,
        timing_only_sha256=sha(RUN / 'result/timing_only.json'), official_report_sha256=timing['official_report_sha256'],
        critical_paths_sha256=sha(paths_file), top_paths=[{k: p[k] for k in ('startpoint', 'endpoint',
            'data_arrival_time', 'required_time', 'slack')} for p in paths], named_path_nodes=named,
        largest_cell_increments=sorted(increments, key=lambda n: n['delay_ns'], reverse=True)[:12],
        original_process_id=dispatch['process_id'], original_process_alive=alive, phase=phase['status'],
        pending_source_candidate=state['current_source_candidate'], pending_source_metrics_unknown=True,
        report=str(REPORT), report_sha256=sha(REPORT), new_hdl_execution=False, new_sta=False,
        no_false_path_added=True, complete_goal_not_proven=True)
    write(OUT, proof)
    state.update(active_measurement_partial_metrics=partial, measurement_process_alive=alive,
        active_measurement_critical_proof=str(OUT), active_measurement_critical_proof_sha256=sha(OUT),
        active_measurement_ppa_progress_report=str(REPORT), active_measurement_ppa_progress_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_NEW_A58_A59_A60_AND_COMPLETED_A55R2_PPA_CRITICAL_REGION_CHANGED',
        next_work=['Observe original A55R2 performance process; reconcile exact six-perf IPC and same-source PPA when terminal.',
                   'Prioritize measured Dcache return->RS issue->ROB live-generation check->MDU entry path; audit earlier per-RS-row recovery eligibility with full GEN/exact-once ownership and area/fanout budget.',
                   'Retain A56-A60 and redirect-fetch ownership work independently; no new HDL jobs before a coherent material-gain batch and pretest report.'],
        goal_complete=False)
    write(STATE, state)
    print(dict(status=proof['status'], partial_metrics=partial, original_process_alive=alive,
               measurement_phase=phase['status'], report=str(REPORT)))


if __name__ == '__main__':
    main()
