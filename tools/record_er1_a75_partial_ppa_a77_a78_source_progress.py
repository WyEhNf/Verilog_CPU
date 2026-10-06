"""Bind A75 measured STA to independent A77/A78 source progress, without jobs."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a75_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a75_partial_ppa_a77_a78_source_progress_20261006.json'
REPORT = ROOT / 'reports/ER1_A75_partial_PPA_A77_A78_source_changes_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A76_head_only_load_completion'
    assert state['active_measurement_candidate'] == 'A75_branch_capture_phase_valid'
    assert state['measurement_process_id'] == 42732
    plan = check()
    dispatch = read(RUN / 'dispatch_identity.json')
    assert dispatch['process_id'] == 42732
    assert sha(RUN / 'dispatch_identity.json') == state['measurement_dispatch_sha256']
    assert plan['source_manifest_sha256'] == state['active_measurement_source_manifest_sha256']
    phase = read(RUN / 'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 42732
    assert phase['phases'][0]['returncode'] == 0
    original_alive = live(42732)
    timing_path = RUN / 'result/timing_only.json'
    timing = read(timing_path)
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert sha(RUN / 'result/synth/opt/report.json') == timing['official_report_sha256']
    critical = RUN / 'result/synth/opt/critical_paths.json'
    assert sha(critical) == 'bde33e7b095e85fe0477c5992475d330ef5efd988bdc439f15096fb2bf2ac3ac'
    paths = []
    for item in read(critical)['checks']:
        anchors = []
        seen = set()
        for point in item['source_path']:
            net = point.get('net', '')
            if net.startswith('core.') and '/' not in net and net not in seen:
                seen.add(net)
                anchors.append(dict(net=net, arrival_ns=point['arrival']*1e9))
        paths.append(dict(startpoint=item['startpoint'], endpoint=item['endpoint'],
            data_arrival_ns=item['data_arrival_time']*1e9, named_anchors=anchors))
    assert len(paths) == 5 and all(row['data_arrival_ns'] == 3.282 for row in paths)
    area = read(RUN / 'result/synth/opt/report.json')['area']
    assert area['area_um2'] == timing['area_um2']
    measured = dict(candidate='A75_branch_capture_phase_valid', source_manifest_sha256=plan['source_manifest_sha256'],
        run=str(RUN), status='COURSE_TIMING_AREA_COMPLETE_IPC_PENDING', ipc=None,
        fmax_mhz=timing['fmax_mhz'], minimum_period_ns=timing['minimum_period_ns'], area_um2=timing['area_um2'],
        sram_area_um2=area['sram_area_um2'], sequential_area_um2=area['sequential_area_um2'],
        combinational_area_um2=area['combinational_area_um2'],
        fmax_above300=False, area_at_most36000=True, full_correctness_not_run=True,
        adopted=False, objective_met=False)
    assert measured['fmax_mhz'] < 300 and measured['area_um2'] <= 36000
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256'] == 'b15354287b04618e970942463c5156b3248a92f456a7ace32145a5a412ab842d'
    active = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous)['main_active_manifest_sha256']
    main_source = read(active)
    for name, digest in main_source['source_sha256'].items():
        assert sha(ROOT / name) == digest, name
    candidates = []
    for name, script, expected in [
        ('A77_lsq_pick_local_validity','prepare_er1_lsq_pick_local_validity.py','e3f9d51d28dada5bc375bb887cb664e3a554de6613c3032f2da66b45b26ed52d'),
        ('A78_lsq_forward_onehot','prepare_er1_lsq_forward_onehot.py','26e2af0ad1acef1121dbdcbb2f9f1811c88fc085f81fc1701459cfd4250d113c')]:
        root = BASE / name
        candidate = read(root / 'candidate.json')
        assert sha(root / 'candidate.json') == expected
        parent = Path(candidate['parent_candidate'])
        assert sha(parent / 'candidate.json') == candidate['parent_candidate_sha256']
        assert sha(ROOT / 'tools' / script) == candidate['preparation_script_sha256']
        for file, digest in candidate['source_sha256'].items():
            assert sha(root / file) == digest, file
        review = BASE / (name.split('_',1)[0]+'_source_review.json')
        assert read(review)['candidate_sha256'] == expected
        assert candidate['tests_started'] is False and candidate['adopted'] is False
        assert sorted(file for file in candidate['source_sha256']
                if (root/file).read_bytes() != (parent/file).read_bytes()) == sorted(candidate['changed_from_parent_files'])
        candidates.append(dict(candidate=name, source_root=str(root), candidate_sha256=expected,
            source_file_count=len(candidate['source_sha256']), source_hashes_valid=True,
            parent_candidate_sha256=candidate['parent_candidate_sha256'],
            preparation_script_sha256=sha(ROOT / 'tools' / script), review=str(review), review_sha256=sha(review),
            changed_files=candidate['changed_from_parent_files'], tests_started=False, adopted=False))
    final_root = BASE / candidates[-1]['candidate']
    helper = final_root / 'rtl/common/rv32_asap7_fanout.v'
    helper_text = helper.read_text(encoding='utf-8')
    assert 'assign value_o=mux_tree[1];' in helper_text
    assert 'assign mux_tree[node_id]=mux_tree[2*node_id] | mux_tree[2*node_id+1];' in helper_text
    classification = 'PROGRESS_A75_MEASURED_LSQ_BOTTLENECK_A77_LOCAL_PICK_VALIDITY_A78_ONEHOT_FORWARD_NO_NEW_HDL_JOBS'
    REPORT.write_text('\n'.join([
        '# A75 部分实测与 A77–A78 源码优化', '',
        'A75原冻结测量的综合/STA阶段已经完成：估算频率299.240210MHz，最小周期3.341796875ns，含SRAM面积35658.771398μm²；IPC仍待原性能阶段给出。尚未超过300MHz，不能采用。', '',
        '其面积分量为组合20133.25956μm²、时序7581.6μm²、SRAM7943.911838μm²。比A69频率提高69.54079MHz，面积减少14.58μm²；这是整个A70–A75批次结果，不能归因于某一项单独修改。', '',
        '五条最慢路径均为LSQ地址→请求资格与最老请求选择→按选中行二次读状态→直接旁路选择→字节重叠与前递→状态寄存器，数据到达均为3.282ns。原A69的恢复/完成ready/RAS链不再是报告的最慢路径。', '',
        '| 候选 | 已落盘修改 | 成本与限制 |', '|---|---|---|',
        '| A77 | 在各LSQ行提前计算原有直接旁路资格，随完全相同的行别名与请求选择树传递；删除选完行后第二次读状态和同一当前行的代数等值比较。 | 无新增FF/SRAM/边沿，保留已保存请求的代数检查、实际资格及所有握手。观察到的1.110–1.548ns区间不是保证可省的时间。 |',
        '| A78 | 将逐字节最年轻重叠存储选择表达为互斥并行掩码：优先最高物理行的已绕回类别，否则最高普通行；数据使用原有8位掩码OR树。 | 无新增FF/SRAM/边沿，保留每字节独立赢家、未知存储阻塞、窗口/字节合并、暂停快照；默认/其他几何继续原选择树。组合映射成本未知。 |', '',
        'A77/A78继承尚未测试的A76队首返回完成旁路，其17位声明FF成本不应重复计数。A77/A78为同边沿时序表达改写，没有可声称的IPC增益；A76的IPC收益也尚未测量。三者累计频率、总面积和IPC全部未知。', '',
        '人工归纳关系确认原选择树的行身份/代数/载荷一致，逐字节前递保持原有循环年龄优先级。尚未运行HDL检查、形式验证、仿真、综合、STA或单元测试，不能据此声称已证明完整等价或达到目标。主实现40个文件保持原哈希。', '',
        '原A75 PID42732及冻结源/工具/配置/报告保留，性能阶段复用同一次综合，未重复综合；本轮没有启动任何新测量。后续集中测试前仍先汇报完整依据和风险。', '',
        '- [A77审查](F:/CPU2026Candidates/tier3_er1_20261005/A77_source_review.json)',
        '- [A78审查](F:/CPU2026Candidates/tier3_er1_20261005/A78_source_review.json)', '',
    ]), encoding='utf-8')
    proof = dict(status='A75_PARTIAL_MEASURED_PPA_A77_A78_SOURCE_PROGRESS', recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='VERIFIED_WAIT_ORIGINAL_A75_PID42732_LIVE_DURING_METRIC_REPORT',
        this_goal_turn_classification=classification, previous_source_progress_proof=str(previous),
        previous_source_progress_proof_sha256=sha(previous), measured_a75_partial_result=measured,
        measured_artifacts_sha256={str(timing_path):sha(timing_path),str(critical):sha(critical),
            str(RUN/'result/synth/opt/report.json'):sha(RUN/'result/synth/opt/report.json'),
            str(RUN/'source_manifest.json'):sha(RUN/'source_manifest.json')},
        measured_critical_paths=paths, pending_candidates=candidates,
        pending_candidate=candidates[-1]['candidate'], pending_candidate_metrics=dict(ipc=None,fmax_mhz=None,area_um2=None),
        this_batch_source_cost=dict(new_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
            inherited_a76_declared_ff_bits=17,actual_gate_cost_unknown=True),
        event_selector_helper_sha256=sha(helper), original_a75_process_id=42732,
        original_a75_process_alive=original_alive, original_a75_phase=phase['status'],
        original_a75_dispatch_sha256=sha(RUN/'dispatch_identity.json'),
        new_hdl_or_lint_or_formal_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        measured_incumbent=state['best_measured_combined_result'], report=str(REPORT),report_sha256=sha(REPORT),
        main_eu_source_unchanged=True,main_active_manifest_sha256=sha(active),
        main_source_file_count=len(main_source['source_sha256']),adopted=False,goal_complete=False)
    write(PROOF,proof)
    last = candidates[-1]
    state.update(status='A75_PERFORMANCE_A78_PENDING_SOURCE_UNTESTED',
        current_source_candidate=last['candidate'],current_prepared_candidate=last['candidate'],
        pending_source_candidate=last['source_root'],pending_source_candidate_sha256=last['candidate_sha256'],
        candidate_manifest_sha256=last['candidate_sha256'],candidate_tests_started=False,
        pending_source_candidate_tests_started=False,candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        candidate_metrics_belong_to=last['candidate'],candidates_adopted=False,goal_complete=False,
        active_measurement_partial_metrics=measured,
        active_measurement_critical_proof=str(PROOF),active_measurement_critical_proof_sha256=sha(PROOF),
        active_measurement_ppa_progress_report=str(REPORT),active_measurement_ppa_progress_report_sha256=sha(REPORT),
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        next_work=['Collect original A75 performance/result and confirm source/tool/config/program/binary identities.',
            'Continue isolated timing/IPC work against measured LSQ path; no per-edit HDL tests.',
            'Review complete A76-A78 structural gain and new fast-return path before any later measurement.',
            'Retain A55R2 incumbent until >300MHz and <=36000um2 with higher IPC, target1.1.',
            'Prove all architecture/correctness/parameter requirements before adopting a qualifying candidate.'])
    write(STATE,state)
    print(dict(status=proof['status'],candidate=last['candidate'],proof=str(PROOF),proof_sha256=sha(PROOF),
        original_a75_process_alive=original_alive,new_tests_started=False,main_source_unchanged=True))


if __name__ == '__main__':
    main()
