"""Record algebraic frontend changes and a recovery-fetch ownership investigation."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write, optional
from manage_er1_a55_serial_measurement import check as check_serial
from wait_frequency_directed_native import live

ROOT = Path('E:/Verilog_cpu')
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
REPORT = ROOT / 'reports/ER1_A58_A60_background_progress_2026-10-05.md'
PROOF = ROOT / 'build/cpu2026/er1_a58_a60_background_progress_20261005.json'


def main():
    assert not REPORT.exists() and not PROOF.exists()
    plan = check_serial()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A57_frontend_ras_offset_flags'
    previous_report, previous_proof = Path(state['last_background_progress']), Path(state['last_source_progress_proof'])
    assert sha(previous_report) == state['last_background_progress_sha256']
    assert sha(previous_proof) == state['last_source_progress_proof_sha256']
    dispatch = read(RUN / 'dispatch_identity.json')
    assert sha(RUN / 'dispatch_identity.json') == state['measurement_dispatch_sha256']
    alive = live(dispatch['process_id'])
    phase, result, timing = optional(RUN / 'serial_phase_identity.json'), optional(RUN / 'result/result.json'), optional(RUN / 'result/timing_only.json')
    observation = dict(run=str(RUN), process_id=dispatch['process_id'], process_alive=alive,
        observed_at=datetime.now(timezone.utc).isoformat(), phase=phase['status'] if phase else None,
        result=({k: result.get(k) for k in ('status', 'ipc', 'fmax_mhz', 'area_um2',
            'official_perf_expected_results_passed', 'official_correctness_suite_passed')} if result else None),
        timing=({k: timing.get(k) for k in ('status', 'fmax_mhz', 'area_um2')} if timing else None))
    candidates = []
    for name, digest, preparer in (
        ('A58_predictor_direct_bank_word_index', '253dd9ffc875bc8a2306c721c28964aeae29cd43f18cb8821a37bb2f7e939c9d', 'prepare_er1_predictor_direct_bank_word_index.py'),
        ('A59_frontend_response_word_offset_read', '2f660ab7dac11754b214c3bd8bf779e4226bb94fdd7c4672300ec463de818906', 'prepare_er1_frontend_response_word_offset_read.py'),
        ('A60_frontend_direct_word_bounds', '245f8866cbb07c41749af50ac7632f4982b6b68af6c50aa13c5ce90a30a3472f', 'prepare_er1_frontend_direct_word_bounds.py')):
        path = BASE / name
        candidate = read(path / 'candidate.json')
        review_path = BASE / (name.split('_', 1)[0] + '_source_review.json')
        review = read(review_path)
        parent_path = Path(candidate['parent_candidate'])
        parent = read(parent_path / 'candidate.json')
        assert sha(path / 'candidate.json') == digest == review['candidate_sha256']
        assert sha(ROOT / 'tools' / preparer) == candidate['preparation_script_sha256']
        assert sha(parent_path / 'candidate.json') == candidate['parent_candidate_sha256']
        assert not candidate['tests_started'] and not candidate['adopted']
        assert not review['tests_started'] and not review['adopted']
        assert review['added_ff_bits'] == review['added_sram_bits'] == review['added_pipeline_edges'] == 0
        for rel, source_digest in candidate['source_sha256'].items():
            assert sha(path / rel) == source_digest, (name, rel)
        for rel, source_digest in parent['source_sha256'].items():
            assert sha(parent_path / rel) == source_digest, (parent_path.name, rel)
        changed = [rel for rel, source_digest in candidate['source_sha256'].items() if source_digest != parent['source_sha256'][rel]]
        assert set(changed) == set(candidate['changed_from_parent_files']) == set(review['changed_files'])
        candidates.append(dict(candidate=name, source_root=str(path), candidate_sha256=digest,
            parent_candidate=str(parent_path), source_files_checked=41, changed_files=changed,
            source_review=str(review_path), source_review_sha256=sha(review_path),
            preparation_script_sha256=candidate['preparation_script_sha256'],
            added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
            tests_started=False, adopted=False, ipc=None, fmax_mhz=None, area_um2=None))
    pending_path = Path(candidates[-1]['source_root'])
    frontend = (pending_path / 'rtl/frontend/rv32_fetch_frontend.v').read_text(encoding='utf-8')
    core = (pending_path / 'rtl/cpu_core.v').read_text(encoding='utf-8')
    assert '(!req_pending_reg || response_can_chain)' in frontend
    assert 'assign if_req_epoch_o = epoch_reg;' in frontend
    assert 'next_pc_comb[request_half*16 +: 16]:pc_reg[request_half*16 +: 16]' in frontend
    assert "if (redirect_valid_i) begin\n                req_pending_reg <= 1'b0;" in frontend
    assert '.current_epoch_i(frontend_epoch)' in core
    warnings = [
        'rv32_rob.recovery_saved_owner.data_i from 96 bits to 42 bits.',
        'rv32_rob.recovery_query_tree.signal_i from 44 bits to 18 bits.',
        'rv32_dcache_nonblocking.mshr_action_tree.signal_i from 16 bits to 17 bits.']
    new_log = RUN / 'result/synth.log'
    old_log = Path(state['last_measured_result']['run']) / 'result/synth.log'
    if new_log.exists():
        n, o = new_log.read_text(errors='replace'), old_log.read_text(errors='replace')
        assert all(w in n and w in o for w in warnings)
    active_path = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    active = read(active_path)
    for rel, digest in active['source_sha256'].items():
        assert sha(ROOT / rel) == digest, rel
    known = state['last_measured_result']
    assert known['candidate'] == 'A41_lsq_two_prefix_reclaim'
    assert sha(Path(known['run']) / 'result/result.json') == known['result_sha256']
    REPORT.write_text(f'''# A58–A60 前端控制源码进度

目标保持IPC≥1.1、总面积含SRAM≤36000μm²、频率>300MHz，并保留完整RV32IM/OoO/顺序提交/MMIO/参数化范围。上一目标轮完成串行调度与A56/A57，属于实际进展；本轮新增A58/A59/A60并继续检查恢复后的取指请求所有权。

## 测量与源码身份

A55R2原监督PID{dispatch['process_id']}经查询{'存活' if alive else '已不存在'}，阶段{observation['phase']}。已有完整结果：{observation['result']}；已有时序结果：{observation['timing']}。它仍使用A55冻结源码。本轮没有启动新的HDL/lint/仿真/综合/STA/单元测试，没有重启该进程，没有使用WSL。首次A55内存分配失败现场保持原样。

已测综合最优仍是A41：IPC {known['ipc']:.10f}、频率 {known['fmax_mhz']:.5f}MHz、总面积 {known['area_um2']:.5f}μm²，其中SRAM {known['sram_area_um2']:.5f}μm²；6perf答案通过，完整正确性未运行。目标尚未完成；新A60没有实测指标，没有采用到主E工作区EU RTL。

## 本轮源码实现

|候选|变化|明确删除的依赖|
|---|---|---|
|A58 直接银行字索引|FE4的3位索引为{{W>B,B}}；FE2偶银行用W高低位与/异或，奇银行设置低位；保留越界索引4..6。|银行偏移减法→字索引加法→PC高位进位/指令与查询有效性。|
|A59 响应字常量偏移|每个通道将128位响应行按常量32L右移，再按原始起始字W读32位字，越界自然补零。|起始字＋通道加法→响应指令字读取；动态索引宽度由3变2。|
|A60 直接行内边界|旁路和并行束控制的W+L<4改为W≤3-L，最后一字W+L=3改为W=3-L。|字编号加法→旁路有效、束结束、下一PC和容量控制的字范围判断。|

W是2位起始字，B/L是常量银行/通道编号0..3。所有源代码推导保留FE1/2/4有效与无效字、完整PC回绕/非对齐低位，以及独立参数回退。主前端队列计数/入出队/错误/背压/epoch/重定向/链式请求状态与原接受所有权保持原实现；没有新增FF、SRAM或流水边界。

这些只是源码等式及依赖删除，不是HDL等价证明；旧映射可能已经化简部分逻辑，负载/缓冲/裁剪/总面积/Fmax/IPC均未测量。A58–A60各自parent和全部41个源码文件、准备脚本、审阅记录SHA256均已核对并冻结。

## 进一步的架构调查

现有前端请求PC只在链式回复下一PC与pc_reg之间选择，请求epoch来自epoch_reg；重定向写入PC/epoch所有者，并将req_pending清零。ICache使用frontend_epoch作为当前epoch。该源码说明，目前没有把新重定向的PC/epoch直接作为同拍新请求的专门路径。

下一步审查是否可在重定向接受边界直接发出新取指请求，而同时丢弃旧回复并保存新请求所有权。必须逐项检查前端pending优先、旧epoch回复、行过滤器pending/hit_busy、主ICache流水请求与MSHR代际复用、内存事务身份及GHR修复。现有源码不构成这种改动安全性或一拍整程序收益证明；当前尚未实现，也不绕过正确性或300MHz预算。

此方向考虑完整恢复→取指→译码链条，而不只局部算术。恢复与分配同拍的收益还取决于正确目标指令何时到达译码，不能仅凭branch_pending禁令推断可省一拍。待A55R2实际关键路径与6perf变化出来后，结合这些所有权推导确定下一优先级。

日志中ROB两条端口裁剪和Dcache17位动作输入的三条宽度告警，在A41已存在；本轮只核对相同告警，未把旧告警当作本次新增失败或功能正确性证明。源码/日志哈希证据见进度JSON。

最终必要验证保留全部课程、完整M、恢复代际与恰好一次发射、缓存并发与加载转发/背压、FE1/2/4和参数回退；未测候选在汇报整个可观结构收益批次之前不启动测试。

证据：[A60候选](F:/CPU2026Candidates/tier3_er1_20261005/A60_frontend_direct_word_bounds/candidate.json)、[串行测量前汇报](E:/Verilog_cpu/reports/ER1_A55R2_serial_pretest_2026-10-05.md)。
''', encoding='utf-8')
    proof = dict(status='PROGRESS_A58_A60_SOURCE_AND_REDIRECT_FETCH_OWNERSHIP_INVESTIGATION',
        recorded_at=datetime.now(timezone.utc).isoformat(), previous_goal_turn_classification=state['last_goal_turn_classification'],
        this_goal_turn_classification='PROGRESS_NEW_A58_A59_A60_SOURCE_AND_RECOVERY_FETCH_OWNERSHIP_EVIDENCE',
        objective=dict(ipc_minimum=1.1, total_area_um2_maximum=36000, fmax_mhz_strictly_greater_than=300),
        observation=observation, last_measured_result=known, candidates=candidates,
        serial_source_manifest_sha256=plan['source_manifest_sha256'], serial_plan_sha256=sha(RUN / 'measurement_plan.json'),
        report=str(REPORT), report_sha256=sha(REPORT), previous_report=str(previous_report), previous_report_sha256=sha(previous_report),
        previous_proof=str(previous_proof), previous_proof_sha256=sha(previous_proof),
        original_width_warnings=warnings, baseline_synth_log_sha256=sha(old_log),
        source_ownership_evidence_sha256={rel: sha(pending_path / rel) for rel in (
            'rtl/frontend/rv32_fetch_frontend.v', 'rtl/cpu_core.v', 'rtl/cache/rv32_icache_nonblocking.v')},
        redirect_same_edge_new_request_not_implemented=True, new_hdl_job_started=False,
        pending_candidates_tested=False, main_worktree_rtl_unchanged=True,
        main_worktree_active_record_sha256=sha(active_path), candidates_adopted=False, goal_complete=False)
    write(PROOF, proof)
    pending = candidates[-1]
    state.update(status='A55R2_ACTIVE_A60_PENDING_SOURCE_UNTESTED' if alive else 'A55R2_TERMINAL_A60_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=pending['candidate'], current_source_candidate=pending['candidate'],
        candidate_manifest_sha256=pending['candidate_sha256'], candidate_tests_started=False,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None, candidate_metrics_belong_to=pending['candidate'],
        candidate_correctness_passed=None, candidate_correctness_failed=None,
        candidate_correctness_finished=False, candidate_correctness_not_run=True,
        pending_source_candidate=pending['source_root'], pending_source_candidate_sha256=pending['candidate_sha256'],
        pending_source_candidate_tests_started=False, prepared_run=None, prepared_source_manifest_sha256=None,
        candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        measurement_process_alive=alive, measurement_last_observed_at=observation['observed_at'], measurement_last_observation=observation,
        last_background_progress=str(REPORT), last_background_progress_sha256=sha(REPORT),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        last_goal_turn_classification=proof['this_goal_turn_classification'], candidates_adopted=False, goal_complete=False,
        next_work=['Observe the original A55R2 supervisor and reconcile its same-source metrics when terminal; never restart because of observation timeout.',
                   'Audit same-edge redirected instruction-request ownership across frontend pending/epoch and ICache filter/pipeline/MSHR/transaction identity; implement only with coherent timing/area/correctness reasoning.',
                   'Use new measured critical paths and six-perf IPC changes when available; no pending-source tests before a material-gain batch and pretest report.'])
    write(STATE, state)
    print(dict(status=proof['status'], original_process_id=dispatch['process_id'], process_alive=alive,
        measurement_phase=observation['phase'], pending_candidate=pending['candidate'], report=str(REPORT),
        new_hdl_job_started=False, goal_complete=False))


if __name__ == '__main__':
    main()
