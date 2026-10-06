"""Bind original A99 terminal PPA and its deferred performance; no new tests."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a99_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a99_ppa_result_20261006.json'
REPORT = ROOT/'reports/ER1_A99_PPA_new_recovery_path_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan=check();phase=read(RUN/'serial_phase_identity.json');dispatch=read(RUN/'dispatch_identity.json')
    assert dispatch['process_id']==phase['supervisor_pid']==48248 and not live(48248)
    assert phase['status']=='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED'
    assert [(p['phase'],p['returncode']) for p in phase['phases']]==[('timing',0)]
    timing=read(RUN/'result/timing_only.json');ppa=read(RUN/'result/synth/opt/report.json')
    assert timing['source_manifest_sha256']==plan['source_manifest_sha256']
    assert timing['config_sha256']==plan['config_sha256']
    assert timing['official_report_sha256']==sha(RUN/'result/synth/opt/report.json')
    assert phase['timing_report_sha256']==sha(RUN/'result/timing_only.json')
    assert timing['status']=='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['ipc'] is None and not timing['cpu_build_started'] and not timing['simulation_started']
    assert not (RUN/'native_build').exists() and not (RUN/'result/ipc.json').exists()
    assert timing['fmax_mhz']==ppa['timing']['estimated_fmax_mhz']<300
    assert timing['area_um2']==ppa['area']['area_um2']<=36000
    state=read(STATE);pending=Path(state['pending_source_candidate'])
    assert pending.name=='A101_held_identity_row_query'
    assert sha(pending/'candidate.json')==state['pending_source_candidate_sha256']
    previous=Path(state['last_source_progress_proof'])
    assert sha(previous)==state['last_source_progress_proof_sha256']
    active=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active)==plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():assert sha(ROOT/name)==digest,name
    reference=read(ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json')['metrics']
    paths=read(RUN/'result/synth/opt/critical_paths.json')['checks']
    compact=[]
    for path in paths:
        anchors=[];seen=set();nodes=path['source_path']
        for node in nodes:
            net=str(node.get('net',''))
            if net.startswith('core.') and '/' not in net and net not in seen:
                anchors.append(dict(net=net,arrival_ns=node['arrival']*1e9));seen.add(net)
        delays=sorted([dict(cell=n['cell'],pin=n['pin'],net=n['net'],delay_ps=(n['arrival']-nodes[i-1]['arrival'])*1e12,
            capacitance_ff=n.get('capacitance',0)*1e15) for i,n in enumerate(nodes) if i],key=lambda x:x['delay_ps'],reverse=True)[:8]
        compact.append(dict(startpoint=path['startpoint'],endpoint=path['endpoint'],arrival_ns=path['data_arrival_time']*1e9,anchors=anchors,largest_stage_delays=delays))
    assert len(compact)==5 and all('branch_capture_owner.data_o[76]' in str(p['anchors']) for p in compact)
    metrics=dict(status='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE_PERFORMANCE_DEFERRED',
        candidate='A99_balanced_saved_identity',candidate_sha256=plan['candidate_sha256'],run=str(RUN),process_id=48248,process_alive=False,
        ipc=None,ipc_not_measured=True,fmax_mhz=timing['fmax_mhz'],minimum_period_ns=timing['minimum_period_ns'],area_um2=timing['area_um2'],
        sram_area_um2=ppa['area']['sram_area_um2'],sequential_area_um2=ppa['area']['sequential_area_um2'],
        combinational_area_um2=ppa['area']['combinational_area_um2'],full_correctness_not_run=True,full_correctness_passed=False,
        cpu_build_started=False,simulation_started=False,source_manifest_sha256=plan['source_manifest_sha256'],
        timing_report_sha256=sha(RUN/'result/timing_only.json'),ppa_sha256=sha(RUN/'result/synth/opt/report.json'),objective_numeric_met=False)
    delta=dict(fmax_mhz=metrics['fmax_mhz']-reference['fmax_mhz'],area_um2=metrics['area_um2']-reference['area_um2'],
        area_margin_um2=36000-metrics['area_um2'],minimum_period_reduction_required_ps=(metrics['minimum_period_ns']-1000/300)*1000)
    REPORT.write_text(f'''# A99终态：PPA未改善，停止性能阶段，转向新恢复路径

原监督PID48248已不存在，串行timing返回0，原源manifest/config/工具/报告身份一致。A99 Fmax{metrics['fmax_mhz']:.9f}MHz、最小周期{metrics['minimum_period_ns']:.9f}ns、含SRAM面积{metrics['area_um2']:.6f}μm²；IPC未测。频率不达标，按预报门槛没有CPU构建、性能仿真或完整正确性测试，也没有重启旧任务。

相对A94：频率{delta['fmax_mhz']:.6f}MHz、面积+{delta['area_um2']:.6f}μm²；SRAM相同，时序面积增加1.1664μm²。面积余量仅{delta['area_margin_um2']:.6f}μm²，周期还需缩短超过{delta['minimum_period_reduction_required_ps']:.6f}ps。最新完整三指标仍A94 IPC1.115262692/290.249433MHz/35798.972678μm²；不把A94IPC写成A99实测，也不能单独归因于这批某一修改。

最慢五条现在均由branch_capture_owner.data_o[76]开始，最长到达3.414ns：ROB恢复身份查询0.2935ns→recovery_preview0.6154ns→恢复分布0.7736ns→completion source3 data[79]1.823ns→第二CDB来源选择2.202ns→PRF写地址2.361ns→PRF旁路资格2.499ns→入队共同资格2.982ns→LSQ第5行load/forward状态写3.253/3.274ns→FF3.414ns。最长单门OAI21_223892_337ps/27.89fF，入队NAND3_240947_212ps/24.14fF，恢复后NAND2_222278_199.5ps/14.75fF。

旧A94 held报告路径已不在这五条中，但这里只覆盖五条最慢路径，不能据此声称所有报告路径已达300MHz。当前关键链转到恢复→选公开LSQ报告ROB标签→后端恢复资格→CDB/PRF旁路→入队。课程直接payload为TAG16+PHYS6+flags4+value32+addr32=90bit，data[79]对应标签bit5（ROBslot位）；这与后端对选中producer_tag做恢复年龄计算的源码串行依赖相符。

A100/A101是此前报告身份方向的未测备用，新增第三份ROB资格会增加面积，对现在主瓶颈不够直接；下一频率profile先关闭其可选HELD_LOAD_IDENTITY_QUERY（功能与源代码保留），继续用A99原两候选，优先把候选恢复资格在晚报告选择前算好，让晚选择只选bool，并检查入队资格控制负载。不得继续机械测试旧方向或扩大窗口/削GEN/删ISA。当前无新测试派发。

四份既有补充程序最小集合已经核对：与原19正确性一起用于三指标达标后的最终验证，不重生成、不重复综合构建或六perf；它们共8762条解释器指令覆盖45类操作与必要边界。主E EU源未采用/未变，所有成功脚本与历史证据冻结。目标未达成，继续频率结构优化；新批仍先汇报再测。
''',encoding='utf-8')
    classification='PROGRESS_A99_PPA_TERMINAL_287MHZ_PERF_DEFERRED_NEW_RECOVERY_SELECTED_TAG_PATH'
    proof=dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_pid=48248,original_pid_alive=False,original_terminal_status=phase['status'],metrics=metrics,delta_vs_a94=delta,
        latest_full_three_metrics=reference,critical_paths=compact,new_tests_started=False,source_cpu_ipc_ppa_identity_verified=False,
        source_ppa_identity_verified=True,ipc_unknown=True,main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        pending_source_candidate=str(pending),pending_source_candidate_has_measured_metrics=False,adopted_to_main=False,goal_complete=False,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        artifacts_sha256={str(p):sha(p) for p in [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',
            RUN/'dispatch_identity.json',RUN/'serial_phase_identity.json',RUN/'result/timing_only.json',RUN/'result/synth/opt/report.json',
            RUN/'result/synth/opt/critical_paths.json',REPORT]})
    write(PROOF,proof)
    state.update(status='ER1_A99_PPA_COMPLETE_PERF_DEFERRED_PENDING_A101_SOURCE',
        active_measurement_candidate=None,active_measurement_process_ids=[],measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,candidate_tests_started=False,pending_source_candidate_tests_started=False,
        candidate_metrics_belong_to='A99_balanced_saved_identity',candidate_ipc=None,candidate_fmax_mhz=metrics['fmax_mhz'],candidate_area_um2=metrics['area_um2'],
        last_measured_candidate='A99_balanced_saved_identity',last_measured_result=metrics,last_measured_full_result=reference,
        last_completed_measurement_candidate='A99_balanced_saved_identity',last_completed_measurement_proof=str(PROOF),last_completed_measurement_proof_sha256=sha(PROOF),
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='New A99 critical is recovery -> selected public LSQtag -> producer recovery classification -> CDB/PRF -> atomicadmit/LSQwrite. Prepare independent per-candidate recovery classification and local admission fanout; optional A100/A101 held query disabled for next frequency profile to control84um2 area margin. No new test until supported coherent source and pre-report.')
    write(STATE,state)
    print(dict(status=classification,metrics=metrics,delta_vs_a94=delta,proof=str(PROOF),proof_sha256=sha(PROOF)))


if __name__ == '__main__':
    main()
