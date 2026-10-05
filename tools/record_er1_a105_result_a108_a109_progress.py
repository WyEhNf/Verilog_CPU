"""Bind A105 original terminal PPA and record the complete new source batch."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a105_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
CANDIDATE = BASE/'A109_rob_occupancy_distribution'
PROOF = ROOT/'build/cpu2026/er1_a105_result_a108_a109_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A105_result_A109_frequency_batch_2026-10-06.md'
PREPARERS = {
    106:'prepare_er1_report_recovery_circular_compare.py',
    107:'prepare_er1_allocation_payload_preselect.py',
    108:'prepare_er1_head_report_word_select.py',
    109:'prepare_er1_rob_occupancy_distribution.py',
}


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phase = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phase['supervisor_pid'] == 96096 and not live(96096)
    assert phase['status'] == 'SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED'
    assert [(p['phase'],p['returncode']) for p in phase['phases']] == [('timing',0)]
    timing = read(RUN/'result/timing_only.json')
    ppa = read(RUN/'result/synth/opt/report.json')
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    assert timing['official_report_sha256'] == sha(RUN/'result/synth/opt/report.json')
    assert phase['timing_report_sha256'] == sha(RUN/'result/timing_only.json')
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['ipc'] is None and not timing['cpu_build_started'] and not timing['simulation_started']
    assert not (RUN/'native_build').exists() and not (RUN/'result/ipc.json').exists()
    assert timing['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz'] < 300
    assert timing['area_um2'] == ppa['area']['area_um2'] > 36000
    state = read(STATE)
    assert state['current_source_candidate'] == 'A107_allocation_payload_preselect'
    assert state['active_measurement_candidate'] == 'A105_rob_recovery_row_live'
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    artifacts = {}
    source_chain = []
    parent = BASE/'A105_rob_recovery_row_live'
    for number in range(106,110):
        review_path = BASE/f'A{number}_source_review.json'
        review = read(review_path)
        root = Path(review['candidate'])
        c = read(root/'candidate.json')
        assert sha(root/'candidate.json') == review['candidate_sha256']
        assert Path(c['parent_candidate']).resolve() == parent.resolve()
        assert sha(parent/'candidate.json') == c['parent_candidate_sha256']
        assert not c['tests_started'] and not c['adopted']
        for name, digest in c['source_sha256'].items():
            assert sha(root/name) == digest, (root.name,name)
        preparer = ROOT/'tools'/PREPARERS[number]
        assert sha(preparer) == c['preparation_script_sha256']
        source_chain.append(dict(candidate=str(root),candidate_sha256=sha(root/'candidate.json'),
            changed_files=c['changed_from_parent_files'],review_sha256=sha(review_path),preparer_sha256=sha(preparer)))
        for p in [root/'candidate.json',review_path,preparer]:
            artifacts[str(p)] = sha(p)
        parent = root
    assert parent == CANDIDATE
    assert sha(CANDIDATE/'candidate.json') == '2b31e8b8dea04efc2a8680bb38765e55a1d2724bb01f33c7492300eb2cc9e128'
    candidate = read(CANDIDATE/'candidate.json')
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match[1]) == value,key
    assert candidate['parameter_overrides']['ROB_RECOVERY_ROW_LIVE_QUALIFY'] == 0
    assert candidate['parameter_overrides']['ROB_OCCUPANCY_DISTRIBUTE'] == 1
    assert candidate['parameter_overrides']['LSQ_ALLOC_PAYLOAD_PRESELECT'] == 1
    assert candidate['parameter_overrides']['LSQ_REPORT_RECOVERY_CIRCULAR_COMPARE'] == 1
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest,name
    reference = read(ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json')['metrics']
    prior_ppa = read(ROOT/'build/cpu2026/er1_a99_ppa_result_20261006.json')['metrics']
    paths = read(RUN/'result/synth/opt/critical_paths.json')['checks']
    compact = []
    for path in paths:
        nodes = path['source_path']
        anchors = []
        seen = set()
        for node in nodes:
            net = str(node.get('net',''))
            if net.startswith('core.') and '/' not in net and net not in seen:
                anchors.append(dict(net=net,arrival_ns=node['arrival']*1e9))
                seen.add(net)
        delays = sorted([dict(instance=n['instance'],cell=n['cell'],pin=n['pin'],net=n['net'],
            delay_ps=(n['arrival']-nodes[i-1]['arrival'])*1e12,
            capacitance_ff=n.get('capacitance',0)*1e15,slew_ps=n.get('slew',0)*1e12)
            for i,n in enumerate(nodes) if i],key=lambda x:x['delay_ps'],reverse=True)[:8]
        compact.append(dict(startpoint=path['startpoint'],endpoint=path['endpoint'],
            arrival_ns=path['data_arrival_time']*1e9,anchors=anchors,largest_stage_delays=delays))
    assert len(compact) == 5 and all('execution_recovery_tree.signal_i[13]' in str(p['anchors']) for p in compact)
    # Static mapped-source association, not another synth/STA/formal run.
    design = read(RUN/'result/synth/opt/design.json')['modules']['student_top']
    countbit = design['netnames']['core.g_ooo_backend.backend.execution_recovery_tree.signal_i']['bits'][13]
    inv = [c for c in design['cells'].values() if c['type']=='INVx1_ASAP7_75t_R' and c['connections'].get('Y')==[countbit]]
    assert len(inv) == 1
    qbit = inv[0]['connections']['A'][0]
    ff = [c for c in design['cells'].values() if c['type']=='DFFHQNx1_ASAP7_75t_R' and c['connections'].get('QN')==[qbit]]
    assert len(ff) == 1
    metrics = dict(status='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE_PERFORMANCE_DEFERRED',
        candidate='A105_rob_recovery_row_live',candidate_sha256=plan['candidate_sha256'],run=str(RUN),
        process_id=96096,process_alive=False,ipc=None,ipc_not_measured=True,
        fmax_mhz=timing['fmax_mhz'],minimum_period_ns=timing['minimum_period_ns'],area_um2=timing['area_um2'],
        sram_area_um2=ppa['area']['sram_area_um2'],sequential_area_um2=ppa['area']['sequential_area_um2'],
        combinational_area_um2=ppa['area']['combinational_area_um2'],full_correctness_not_run=True,
        full_correctness_passed=False,cpu_build_started=False,simulation_started=False,
        source_manifest_sha256=plan['source_manifest_sha256'],timing_report_sha256=sha(RUN/'result/timing_only.json'),
        ppa_sha256=sha(RUN/'result/synth/opt/report.json'),objective_numeric_met=False)
    delta = dict(vs_a94_fmax_mhz=metrics['fmax_mhz']-reference['fmax_mhz'],
        vs_a94_area_um2=metrics['area_um2']-reference['area_um2'],
        vs_a99_fmax_mhz=metrics['fmax_mhz']-prior_ppa['fmax_mhz'],
        vs_a99_area_um2=metrics['area_um2']-prior_ppa['area_um2'],
        excess_area_um2=metrics['area_um2']-36000,
        minimum_period_reduction_required_ps=(metrics['minimum_period_ns']-1000/300)*1000)
    REPORT.write_text(f'''# A105原终态与A109完整频率源批次

A105原监督PID96096已不存在，唯一timing阶段返回0，原源码/manifest/config/工具/报告身份已核对。Fmax{metrics['fmax_mhz']:.9f}MHz，最小周期{metrics['minimum_period_ns']:.9f}ns，含SRAM总面积{metrics['area_um2']:.6f}μm²（组合{metrics['combinational_area_um2']:.6f}、时序{metrics['sequential_area_um2']:.6f}、SRAM{metrics['sram_area_um2']:.6f}）。面积超标{delta['excess_area_um2']:.6f}μm²，频率不足；按原PPA门槛未构建CPU、未仿真、IPC未知、19正确性未跑。

相对A99，频率{delta['vs_a99_fmax_mhz']:.6f}MHz、面积+{delta['vs_a99_area_um2']:.6f}μm²；相对最新完整A94，频率{delta['vs_a94_fmax_mhz']:.6f}MHz、面积+{delta['vs_a94_area_um2']:.6f}μm²。不能把A94IPC1.115262692写成A105IPC，也不能把整个批次退化单独归因于某一改动。

五条最慢路径从同一原ROB occupancy bit3起始，到达3.586/3.573/3.553/3.543/3.536ns。最长：原count FF QN177.6ps、33.77fF，INV170.6ps→execution_recovery_tree.signal_i[13]0.3482ns→recovery_preview0.484ns→后端recovery域0.615ns→LSQ/source3 direct payload physbit4(data[72])1.808ns→RS物理唤醒tag域1.916ns→RS entry2 second operand selector2.053ns→lane1 issue select2.427ns→ALU subtract control2.631ns→FF3.586ns。最大门OAI21_225574_529ps、43.73fF、slew1.1ns；另OAI21_229718_192ps、NAND2_223845_185ps。实际最小周期需要缩短超过{delta['minimum_period_reduction_required_ps']:.6f}ps才能严格>300MHz。

旧A99恢复至分配的路径不在当前五条里，不能宣称全部消失。新路径穿过恢复/完成载荷/同周期RS唤醒+发射/ALU，频率必须处理整个跨阶段组合链。原设计JSON中的execution recovery packet位13按W5 age+W5 head+6count+apply解包是countbit3，追溯原INV/FF绑定真实count，未用相似名字猜寄存器。529ps内部driver没有head_choice标签；将它与未分组的最终73bit报告mux联系是结构推断，而非精确RTL映射证据。

在原A105进行时已经冻结A106和A107：A106以共享端点和环形slot比较替代原W-bit unsigned age减法再比较，保持2^W回绕和所有rawcount；A107从原已知稀疏分配plan预选完整LSQ slot/GEN载荷，只在原actualfire消费者使用，分开载荷与晚接受事件。这两个旧关键链方向没有新测试。

A108在原HEAD_LOAD_PACKET_ACTIVE分支把最后73bit head/saved整包选择拆成5个<=16bit选择叶，由原真实控制树传同一bool；所有packet bits逐bit保持。新profile关闭可选A105每行完整GEN比较，恢复原9bit selected currentvalid/fullGEN read，保留代码与所有语义。此结构成本退出当前profile，净面积效果尚未知，不重跑旧A105或单个因素。

A109把同一原occupancy_reg分给ceil(ROB_ENTRIES/4)个恢复比较域及独立lane/public/query域。原count width/unsigned类型/全状态值不变，原count reset/recovery/commit/allocation赋值逐字保持，不复制寄存器、不增加边沿；每个消费者换成等值wire。目标是减轻关键链起点348.2ps大负载，与A108处理中段529ps控制负载配合。A106/A107防止此前链再次成为主瓶颈。新增FF/SRAM/流水边沿全0。

评估其余方向：新增恢复/CDB/issue寄存边界会改变同周期唤醒及分支等待，A94 IPC余量只有约1.37%，当前没有周期代价可控的证据；扩窗口/预测器没有当前性能瓶颈依据且面积紧；缩GEN/减少ISA/取消恢复检查违背要求；源前比较RS唤醒可再去掉CDB-tag选择后比较，但需新源身份/仲裁优先接口和更多比较，在处理明确529ps/348ps负载前没有更直接的净收益证据。ALU算术分段已有9级架构，当前大部分延迟出现在算术之前。此批优先保留周期行为，不能保证映射结果，不能宣称未来架构思路已被穷尽。

本轮未新增HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建。A106-A109源、生成器、审阅全部冻结，A10941文件候选SHA{sha(CANDIDATE/'candidate.json')}；主E40源未采用。下一步先对话报告完整批次和不确定性，再唯一一次原生Windows课程PPA，只有>300MHz且含SRAM面积<=36000才构建一次CPU测六perf。三项实测达标后复用同CPU，集中19课程正确性+4既有冻结边界程序及参数/架构审阅，完成前不采用、不标目标完成。
''',encoding='utf-8')
    for p in [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',
        RUN/'dispatch_identity.json',RUN/'serial_phase_identity.json',RUN/'result/timing_only.json',
        RUN/'result/synth/opt/report.json',RUN/'result/synth/opt/critical_paths.json',RUN/'result/synth/opt/design.json',REPORT]:
        artifacts[str(p)] = sha(p)
    classification = 'PROGRESS_A105_TERMINAL_PPA_FAILURE_NEW_COUNT_CDB_RS_ALU_PATH_AND_A106_A109_COHERENT_SOURCE'
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_pid=96096,original_pid_alive=False,original_terminal_status=phase['status'],metrics=metrics,
        delta=delta,latest_full_three_metrics=reference,critical_paths=compact,
        mapped_count_launch=dict(packet_bit=13,count_bit=3,positive_bit=countbit,negative_ff_bit=qbit),
        new_source_chain=source_chain,pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_has_measured_metrics=False,new_tests_started=False,
        source_ppa_identity_verified=True,source_cpu_ipc_ppa_identity_verified=False,ipc_unknown=True,
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        artifacts_sha256=artifacts,adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A105_PPA_COMPLETE_PERF_DEFERRED_PENDING_A109_COHERENT_FREQUENCY_SOURCE',
        active_measurement_candidate=None,active_measurement_process_ids=[],measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,candidate_tests_started=False,
        current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate_tests_started=False,
        pending_source_candidate_has_measured_metrics=False,candidate_metrics_belong_to=metrics['candidate'],
        candidate_ipc=None,candidate_fmax_mhz=metrics['fmax_mhz'],candidate_area_um2=metrics['area_um2'],
        last_measured_candidate=metrics['candidate'],last_measured_result=metrics,last_measured_full_result=reference,
        last_completed_measurement_candidate=metrics['candidate'],last_completed_measurement_proof=str(PROOF),
        last_completed_measurement_proof_sha256=sha(PROOF),last_source_progress_proof=str(PROOF),
        last_source_progress_proof_sha256=sha(PROOF),previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification=classification,candidates_adopted=False,goal_complete=False,
        next_work='Freeze/pre-report one new A106-A109 coherent frequency batch: exact circular recovery, planned allocation identity, bounded head/saved report choice, real ROB count distribution; original optional per-row GEN mode0. PPA first, perf only if>300/totalarea<=36000. No old-run restart or per-edit tests. All three metrics/correctness/parameter/architecture audit required before adoption.')
    write(STATE,state)
    print(dict(status=classification,metrics=metrics,delta=delta,pending_candidate=CANDIDATE.name,
        new_tests_started=False,proof=str(PROOF),proof_sha256=sha(PROOF)))


if __name__ == '__main__':
    main()
