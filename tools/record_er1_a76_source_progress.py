"""Journal independent A76 ownership review while preserving the original A75 job."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a75_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
TARGET = BASE / 'A76_head_only_load_completion'
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a76_source_progress_20261006.json'
REPORT = ROOT / 'reports/ER1_A76_head_load_source_changes_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A75_branch_capture_phase_valid'
    assert state['active_measurement_candidate'] == 'A75_branch_capture_phase_valid'
    assert state['measurement_process_id'] == 42732
    plan = check()
    dispatch = read(RUN / 'dispatch_identity.json')
    assert dispatch['process_id'] == 42732
    assert sha(RUN / 'dispatch_identity.json') == state['measurement_dispatch_sha256']
    assert dispatch['source_manifest_sha256'] == state['active_measurement_source_manifest_sha256'] == plan['source_manifest_sha256']
    phase = read(RUN / 'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 42732
    original_alive = live(42732)
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256'] == 'b55836ec99fe13c7c4673864c02e911a0f2f73dca44f074eb3d9ee556f23bb31'
    active = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous)['main_active_manifest_sha256']
    main_source = read(active)
    for name, digest in main_source['source_sha256'].items():
        assert sha(ROOT / name) == digest, name
    candidate = read(TARGET / 'candidate.json')
    assert sha(TARGET / 'candidate.json') == '866e76d9d715a6a535d3e8985903ecca42b1678ca687ee13a0ac236831bb6b22'
    parent = Path(candidate['parent_candidate'])
    assert sha(parent / 'candidate.json') == candidate['parent_candidate_sha256'] == 'aa8c79ce1742ca07709b2cc675c33126adea5dea347149f17d7e7ec9ff8ac421'
    script = ROOT / 'tools/prepare_er1_head_only_load_completion.py'
    assert sha(script) == candidate['preparation_script_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(TARGET / name) == digest, name
    review = BASE / 'A76_source_review.json'
    assert read(review)['candidate_sha256'] == sha(TARGET / 'candidate.json')
    top = (TARGET / 'rtl/course/student_top.v').read_text(encoding='utf-8')
    core = (TARGET / 'rtl/cpu_core.v').read_text(encoding='utf-8')
    backend = (TARGET / 'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    lsq = (TARGET / 'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    assert 'GENERATION_WIDTH = 8,' in top
    assert '((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) +\n        GENERATION_WIDTH;' in core
    assert '.TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH)' in backend
    assert 'tag_matches_slot = tag[0] && valid_mem[tag_slot] &&' in lsq
    assert '(tag[TAG_GEN_LSB +: GENERATION_WIDTH] == generation_mem[tag_slot]);' in lsq
    assert 'tag_matches_slot(local_tag,match_row) && response_wait_mem[match_row];' in lsq
    assert 'if(report_event) begin load_reported_mem_write_data[metadata_row]=1\'b1;' in lsq
    assert 'pop_count_calc = metadata_pop_count;' in lsq
    changed = [name for name in candidate['source_sha256']
               if (TARGET / name).read_bytes() != (parent / name).read_bytes()]
    assert changed == candidate['changed_from_parent_files']
    REPORT.write_text('\n'.join([
        '# A76：仅队首加载的当拍完成与回收', '',
        'A75 原测量 PID42732 正在独立冻结目录运行，本轮没有启动新 HDL、仿真、综合或 STA 作业，也没有修改它的源码、工具、配置或测试前报告。', '',
        'A76 将已有加载完成旁路扩展为模式2，仅允许当前队首且标签有效、代数匹配、请求已发出的未完成加载使用本拍缓存返回。原有持有回报身份具有最高优先级。完成端口接受这个队首回报后，LSQ 可以在同一边沿回收，减少原来等待保存 complete 状态的一拍。', '',
        '返回值仍使用原有逐字节前递合并、符号扩展和错误状态；无条件写回原 LSQ 行。若下游暂停，原有完整标签锁定该回报，并在后续读取已保存结果。原有 ROB 当前行、8 位代数检查和实际 CDB/PRF/ROB 接收规则均保留。', '',
        '课程 ROB32/GEN8 导出16位完整标签；LSQ16沿用该宽度，其本地代数由16−4−3导出为9位，没有缩短。模式2启用已有16位持有标签和1位有效状态，共17位声明FF；无新SRAM、结果数据缓冲、完成端口或流水级。组合门面积未知。', '',
        '普通非队首加载保持保存后回报；模式0/1保留原行为。已接受回报先于原有逐行 pop 清除，标量 head/occupancy 与第二行回收使用同一个 pop_count。分配仍依据边沿前容量，恢复期间关闭快返回。', '',
        '之前 A21 的广泛返回旁路批次频率只有247.40275MHz，IPC提升约1.61%，不能当作本候选收益。本次范围更窄，但返回数据到 CDB/PRF/ROB，以及 ready 到 pop/count 的路径仍可能超时。已有独立返回唤醒保持原样，不能再声称一拍依赖唤醒收益。', '',
        '当前只有人工源码、时序所有权和哈希审查证据。A76的IPC、含SRAM面积和频率全部未知，尚未采用；待后续形成有充分依据的完整批次，测试前再汇报。', '',
        '- [候选源码审查](F:/CPU2026Candidates/tier3_er1_20261005/A76_source_review.json)', '',
    ]), encoding='utf-8')
    classification = 'PROGRESS_A76_HEAD_LOAD_ACCEPTED_RETURN_PUBLICATION_RECLAIM_NO_NEW_HDL_JOBS'
    proof = dict(status='SOURCE_A76_PROGRESS_NO_NEW_HDL_EXECUTION',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='VERIFIED_WAIT_ORIGINAL_A75_PID42732_LIVE_DURING_METRIC_REPORT',
        this_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=candidate['parent_candidate_sha256'], source_hashes_valid=True,
        source_file_count=len(candidate['source_sha256']), changed_files=changed,
        preparation_script_sha256=sha(script), review=str(review), review_sha256=sha(review),
        manual_source_ownership_review=True, dynamic_or_formal_equivalence_proven=False,
        effective_tags=dict(rob_generation_bits=8, rob_slot_bits=5, full_tag_bits=16, lsq_slot_bits=4, lsq_generation_bits=9),
        source_cost=dict(new_declared_ff_bits=17, new_sram_bits=0, new_result_buffer_bits=0,
            new_completion_ports=0, new_pipeline_edges=0, actual_gate_cost_unknown=True),
        candidate_metrics=dict(ipc=None, fmax_mhz=None, area_um2=None),
        active_measurement_candidate=state['active_measurement_candidate'], original_process_id=42732,
        original_process_alive=original_alive, active_measurement_phase=phase['status'],
        measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        original_dispatch_sha256=sha(RUN / 'dispatch_identity.json'),
        new_hdl_or_lint_or_formal_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        measured_incumbent=state['best_measured_combined_result'],
        main_eu_source_unchanged=True, main_active_manifest_sha256=sha(active),
        main_source_file_count=len(main_source['source_sha256']),
        report=str(REPORT), report_sha256=sha(REPORT), adopted=False, goal_complete=False)
    write(PROOF, proof)
    state.update(status='A75_CHARACTERIZATION_A76_PENDING_SOURCE_UNTESTED',
        current_source_candidate=TARGET.name, current_prepared_candidate=TARGET.name,
        pending_source_candidate=str(TARGET), pending_source_candidate_sha256=sha(TARGET / 'candidate.json'),
        candidate_manifest_sha256=sha(TARGET / 'candidate.json'), candidate_tests_started=False,
        pending_source_candidate_tests_started=False, candidate_ipc=None, candidate_fmax_mhz=None,
        candidate_area_um2=None, candidate_metrics_belong_to=TARGET.name,
        candidate_correctness_passed=None, candidate_correctness_failed=None,
        candidate_correctness_finished=False, candidate_correctness_not_run=True,
        prepared_run=None, candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        candidates_adopted=False, goal_complete=False,
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF), last_background_progress_sha256=sha(PROOF),
        next_work=['Observe original A75 process and frozen phase/results without restarting.',
            'Continue structural IPC and timing work in isolated descendants; no per-edit HDL testing.',
            'Assess head-return critical-path and measurable cycle opportunity before any later complete batch.',
            'Retain A55R2 until measured >300MHz and <=36000um2 with higher IPC; target IPC1.1.',
            'Prove full RV32IM/OoO/commit/MMIO/parameter requirements before adoption.'])
    # Historical A55 partial PPA fields must not describe the active A75 job.
    for key in ['active_measurement_critical_proof', 'active_measurement_critical_proof_sha256',
                'active_measurement_ppa_progress_report', 'active_measurement_ppa_progress_report_sha256']:
        if state.get(key):
            state['historical_a55_' + key] = state[key]
            state[key] = None
    state['last_completed_measurement_process_id'] = state['last_measured_result']['process_id']
    write(STATE, state)
    print(dict(status=proof['status'], candidate=TARGET.name, proof=str(PROOF), proof_sha256=sha(PROOF),
        original_a75_process_alive=original_alive, new_tests_started=False, main_source_unchanged=True))


if __name__ == '__main__':
    main()
