"""Record timing-directed independent A73-A75 source work without HDL jobs."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a69_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT / 'build/cpu2026/er1_a73_a75_source_progress_20261006.json'
REPORT = ROOT / 'reports/ER1_A73_A75_source_changes_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A72_branch_capture_redirect_ready'
    assert state['active_measurement_candidate'] is None and not state['active_measurement_process_ids']
    assert state['last_measured_candidate'] == 'A69_same_edge_redirect_fetch'
    assert not live(44708)
    plan = check()
    terminal = Path(state['measurement_terminal_proof'])
    assert sha(terminal) == state['measurement_terminal_proof_sha256']
    complete = read(terminal)
    for path, digest in complete['artifacts_sha256'].items():
        assert sha(Path(path)) == digest, path
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    active = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous)['main_active_manifest_sha256']
    main_record = read(active)
    for name, digest in main_record['source_sha256'].items():
        assert sha(ROOT / name) == digest, name
    candidates = []
    for name, script, digest in [
        ('A73_ras_predecode_repeat_match', 'prepare_er1_ras_predecode_repeat_match.py', 'd512c60d6bf10f13e6e7d599de0635585669d067090573ef3dc79fe0d8d3403a'),
        ('A74_ras_parallel_control', 'prepare_er1_ras_parallel_control.py', '9fb62b6caa8188db58abfe22a66817a125abd4af5c41a3a196e2f4cc555da73e'),
        ('A75_branch_capture_phase_valid', 'prepare_er1_branch_capture_phase_valid.py', 'aa8c79ce1742ca07709b2cc675c33126adea5dea347149f17d7e7ec9ff8ac421'),
    ]:
        root = BASE / name
        manifest = read(root / 'candidate.json')
        assert sha(root / 'candidate.json') == digest
        assert sha(Path(manifest['parent_candidate']) / 'candidate.json') == manifest['parent_candidate_sha256']
        assert sha(ROOT / 'tools' / script) == manifest['preparation_script_sha256']
        for file, expected in manifest['source_sha256'].items():
            assert sha(root / file) == expected, file
        review = BASE / (name.split('_', 1)[0] + '_source_review.json')
        assert read(review)['candidate_sha256'] == digest
        candidates.append(dict(candidate=name, source_root=str(root), candidate_sha256=digest,
            source_file_count=len(manifest['source_sha256']), source_hashes_valid=True,
            parent_candidate_sha256=manifest['parent_candidate_sha256'],
            preparation_script_sha256=sha(ROOT / 'tools' / script), review=str(review), review_sha256=sha(review),
            changed_files=manifest['changed_from_parent_files'], tests_started=False, adopted=False))
    helper = BASE / candidates[-1]['candidate'] / 'rtl/common/rv32_asap7_fanout.v'
    helper_text = helper.read_text(encoding='utf-8')
    assert 'assign cancel_o=active_i && apply && (!tag_i[0] || age>=occupancy ||' in helper_text
    classification = 'PROGRESS_A73_A75_RAS_PREDECODE_PARALLEL_PREFIX_AND_DIRECT_CAPTURE_PHASE_NO_HDL_TESTS'
    REPORT.write_text('\n'.join([
        '# A73–A75：基于 A69 STA 的源码修改', '',
        'A69 已完成原始集中测量：IPC1.05184611，总面积35673.35140 μm²（含SRAM），估算频率229.69942 MHz，六项性能程序通过，完整正确性尚未验证。频率不达标，未采用；满足频率和面积条件的已测综合最优仍是A55R2。', '',
        'A69五条最慢路径具有共同主干，最长数据到达4.293ns。A72已专化重定向捕获ready，删除普通完成网络ready输入。本轮继续处理该路径末端和恢复相位依赖。', '',
        '| 候选 | 修改 | 依据与限制 |', '|---|---|---|',
        '| A73 | 各取指位置提前比较返回PC与RAS栈顶；晚到的已接受调用掩码只选一位相等结果。共享两种PC高位比较。 | 原路径RAS地址选择控制到达约3.578ns，之后仍有约0.715ns。删除晚到32位选择后再比较的依赖；不意味着保存整个区间。新增组合门成本未知。 |',
        '| A74 | RAS事件以并行首事件掩码表达，字边界用常数比较，响应接受作为最后的局部门控。 | 保持首个调用/返回/预测跳转终止取指束、调用优先、空栈返回不弹出的原规则；必要的较早分支方向依赖仍保留。 |',
        '| A75 | 在直接恢复模式下，捕获逻辑查询ALU取消前的已保存结果有效位；保留完整ROB有效位与8位代数检查。 | 捕获要求恢复队列为空；直接apply唯一来源是非空队列，所以捕获相位取消恒为0。实际执行、消费、取消、唤醒和完成端口仍使用原规则。 |', '',
        '三项修改没有增加声明的FF、SRAM或流水边沿；组合门映射面积和频率仍未知。没有加入false-path约束，也没有用较少标签代数位替代原检查。主实现40个源码文件保持原哈希。', '',
        '仅完成源码、哈希、布尔和相位关系审查；本轮未运行HDL检查、形式验证、仿真、综合、STA或单元测试，未证明等价或达到300MHz。完整源级论证和未来集中验证范围在各候选审查中。', '',
        '- [A73审查](F:/CPU2026Candidates/tier3_er1_20261005/A73_source_review.json)',
        '- [A74审查](F:/CPU2026Candidates/tier3_er1_20261005/A74_source_review.json)',
        '- [A75审查](F:/CPU2026Candidates/tier3_er1_20261005/A75_source_review.json)', '',
        'IPC距1.1仍有约4.58%的相对差距（以A69实测为基准）；这些等价时序改写没有可声称的IPC增益，A70/A71的调度回收增益也尚未测量。下一次集中测量前先汇报完整批次依据与风险。', '',
    ]), encoding='utf-8')
    proof = dict(status='SOURCE_A73_A75_PROGRESS_NO_NEW_HDL_EXECUTION',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification=state['last_goal_turn_classification'], this_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        measured_terminal_proof=str(terminal), measured_terminal_proof_sha256=sha(terminal),
        measured_a69_result=complete['metrics'], measured_incumbent=state['best_measured_combined_result'],
        pending_candidates=candidates, pending_candidate=candidates[-1]['candidate'],
        pending_candidate_metrics=dict(ipc=None, fmax_mhz=None, area_um2=None),
        source_cost=dict(new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0, actual_gate_cost_unknown=True),
        direct_cancel_apply_zero_source_verified=True, cancel_helper_sha256=sha(helper),
        previous_original_job_terminal=True, original_pid_absent=True,
        new_hdl_or_lint_or_formal_or_simulation_or_synthesis_or_sta_or_unit_job_started=False,
        report=str(REPORT), report_sha256=sha(REPORT), main_eu_source_unchanged=True,
        main_active_manifest_sha256=sha(active), main_source_file_count=len(main_record['source_sha256']),
        adopted=False, goal_complete=False)
    write(PROOF, proof)
    last = candidates[-1]
    state.update(status='A69_COMPLETE_A75_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=last['candidate'], current_source_candidate=last['candidate'],
        pending_source_candidate=last['source_root'], pending_source_candidate_sha256=last['candidate_sha256'],
        candidate_manifest_sha256=last['candidate_sha256'], candidate_tests_started=False,
        pending_source_candidate_tests_started=False, candidate_ipc=None, candidate_fmax_mhz=None,
        candidate_area_um2=None, candidate_metrics_belong_to=last['candidate'],
        candidate_correctness_passed=None, candidate_correctness_failed=None,
        candidate_correctness_finished=False, candidate_correctness_not_run=True,
        candidates_adopted=False, goal_complete=False,
        previous_goal_turn_classification=state['last_goal_turn_classification'], last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF), last_background_progress_sha256=sha(PROOF),
        next_work=['Review remaining measured-critical timing dependencies and the complete A70-A75 source batch.',
            'Report before one justified native pinned-course measurement; no per-edit testing.',
            'Retain A55R2 incumbent until measured frequency/area conditions and higher IPC are both met.',
            'Continue toward IPC1.1 and prove complete RV32IM/OoO/commit/MMIO/parameter requirements before adoption.'])
    write(STATE, state)
    print(dict(status=proof['status'], pending_candidate=last['candidate'], proof=str(PROOF),
        proof_sha256=sha(PROOF), report=str(REPORT), new_tests_started=False, main_source_unchanged=True))


if __name__ == '__main__':
    main()
