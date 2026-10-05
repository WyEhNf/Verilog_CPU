"""Journal frozen A79-A83 source work against terminal measured A75, no jobs."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a75_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a79_a83_source_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A79_A83_source_progress_2026-10-06.md'
ITEMS = [
    ('A79_ready_ram_store_complete', 'prepare_er1_ready_ram_store_complete.py', 'f7d8733c830c1e3a6e488034a4c6fc9dc52c09d0bc55bd7c0d172e1a52a02c0a'),
    ('A80_fast_store_address_predecode', 'prepare_er1_fast_store_address_predecode.py', '17afbcc548938f8def7c416dda7550dde38cf637987de549447fe065d3f0bee5'),
    ('A81_fast_store_original_data_contract', 'prepare_er1_fast_store_original_data_contract.py', 'b908da4e20d11a9f604c62bbab2377f2145b8108fbbc4b507b9a1284d78a7baf'),
    ('A82_lsq_pick_onehot', 'prepare_er1_lsq_pick_onehot.py', 'c9716c1e338830f96e6eb06a6e31f9376a23b6dd54ac93331c0fa456d821fa1d'),
    ('A83_fast_store_identity_preselect', 'prepare_er1_fast_store_identity_preselect.py', 'f4101372d47ec5f690e93b555f63b7cc0f777ed97499251f28c7a0a228922447'),
]


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A78_lsq_forward_onehot'
    assert state['active_measurement_candidate'] is None and not state['active_measurement_process_ids']
    assert state['measurement_process_alive'] is False
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phase = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phase['supervisor_pid'] == 42732
    assert not live(42732)
    assert phase['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [p['returncode'] for p in phase['phases']] == [0, 0]
    terminal = ROOT/'build/cpu2026/er1_a75_complete_result_20261006.json'
    assert sha(terminal) == '3124ca9883c4e769d494d0f345de5c35be5c57a974e50c4d13951556658b44d4'
    measured = read(terminal)['metrics']
    assert measured == state['last_measured_result']
    assert measured['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert sha(RUN/'result/result.json') == measured['result_sha256']
    assert sha(RUN/'result/ipc.json') == measured['ipc_sha256']
    assert sha(RUN/'result/synth/opt/report.json') == measured['ppa_sha256']
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_proof) == state['last_source_progress_proof_sha256'] == '1cb6a2e6db1cd239c3d7d404026a0372ee1e0adf3af280a8e45bf73fa785f10f'
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous_proof)['main_active_manifest_sha256'] == 'b6a3b95f37c0ac207706c28ddc9caa17d5665d5527beade404033bb08fd147d1'
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    audit = Path(state['last_architectural_source_audit'])
    assert sha(audit) == state['last_architectural_source_audit_sha256'] == '4bd4c780e22c74ea12251a8a791120e9f47f6618ee828eef6160a9b24ef1cb16'
    records = []
    previous = BASE/'A78_lsq_forward_onehot'
    for name, script, expected in ITEMS:
        root = BASE/name
        candidate = read(root/'candidate.json')
        assert sha(root/'candidate.json') == expected
        assert Path(candidate['parent_candidate']).resolve() == previous.resolve()
        assert sha(previous/'candidate.json') == candidate['parent_candidate_sha256']
        assert sha(ROOT/'tools'/script) == candidate['preparation_script_sha256']
        for file, digest in candidate['source_sha256'].items():
            assert sha(root/file) == digest, (name, file)
        assert len(candidate['source_sha256']) == 41
        changed = sorted(file for file in candidate['source_sha256'] if (root/file).read_bytes() != (previous/file).read_bytes())
        assert changed == sorted(candidate['changed_from_parent_files'])
        review = Path(candidate['source_review'])
        assert read(review)['candidate_sha256'] == expected
        assert candidate['tests_started'] is False and candidate['adopted'] is False
        assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
        records.append(dict(candidate=name, candidate_sha256=expected, source_file_count=41, source_hashes_valid=True,
            parent_candidate_sha256=candidate['parent_candidate_sha256'], changed_files=changed,
            preparation_script=str(ROOT/'tools'/script), preparation_script_sha256=sha(ROOT/'tools'/script),
            review=str(review), review_sha256=sha(review), tests_started=False, adopted=False))
        previous = root
    candidate = read(previous/'candidate.json')
    profile = candidate['enabled_profile']
    assert candidate['parameter_overrides']['FAST_STORE_IDENTITY_PRESELECT'] == 1
    assert profile['rob_generation_bits'] == 8 and profile['load_report_hold_identity_bits'] == 17
    assert profile['fast_store_full_identity_comparisons_at_rob32_be2'] == 32
    classification = 'PROGRESS_A79_A83_READY_STORE_EXECUTION_BYPASS_LSQ_CRITICAL_PATH_AND_COMPACT_IDENTITY_NO_HDL_JOBS'
    REPORT.write_text('''# ER1 A79–A83 源码进展

目标保持频率严格大于300MHz、六项性能程序IPC几何平均至少1.1、含SRAM总面积不超过36000μm²；完整RV32IM、乱序执行、顺序提交、MMIO和参数化继续要求。

已完成测量仍是A75：IPC1.0518853869、Fmax299.2402104MHz、面积35658.771398μm²。其原Windows监督进程42732已结束，两阶段返回0；不重启。已有频率/面积达标最优A55R2仍是1.01714182/306.86245MHz/35480.53090μm²。两者六项性能通过、完整19正确性未跑，尚未达到目标。

| 候选 | 已落盘修改 | 收益依据和限制 |
|---|---|---|
| A79 | 已就绪、自然对齐、合法大小/立即数的普通RAM存储，在实际LSQ分配边沿完成ROB执行阶段；保留完整身份检查和原顺序写内存/确认。 | 最多一条存储每拍，通常少两拍RS/ALU执行等待并省RS条目；覆盖率与程序周期收益未知。无新FF/SRAM。 |
| A80 | 在原PRF存储地址候选选择前，分别计算RAM/半字/字对齐标志，按同一WB优先级选择三位结果。 | 避免新的最终32位地址选择后再判资格的依赖；原地址加法/选值未变，新增门成本未知。 |
| A81 | 显式存储数据非零时继续原RS/ALU覆盖规则。 | core原输入恒0，不减少课程快路径覆盖；保留有效独立组件数据覆盖契约。 |
| A82 | LSQ完整请求包改为原循环最老顺序的互斥并行选择，含全部无效时原最右叶值。 | 对准A75实测0.7442–1.0430ns请求树依赖；与A77删除二次状态读、A78字节前递选择共同覆盖已测主干。该区间不等于保证节省。 |
| A83 | 先从已保存D元数据选择第一条潜在存储身份，再施加原就绪/地址/实际分配条件；ROB只复制一个完整身份比较通道。 | ROB32/BE2的目标比较从64份减至32份，保留全部8GEN位；新增早期标签选择，首存储未就绪时后续存储走原RS/ALU。面积/IPC/时序取舍未测。 |

A76队首加载完成旁路继承17位声明FF，其他A77–A83改写无新增FF/SRAM/流水边沿。LSQ/缓存仍持有原数据，真实存储必须经ROB队首授权。MMIO、未就绪地址或数据及不支持模式保留原路径；恢复、GEN复用、普通完成优先级不能被绕开。core合法存储的rd_we/branch/halt均0；不声称任意相互矛盾的独立trace元数据动态等价。

这里只做人工布尔/优先级/身份/握手审查和文件哈希，没有运行HDL、lint、形式、仿真、综合、STA或单元测试。主E工作区40文件与EU原快照一致，所有候选为F盘独立41文件快照，没有采用。

下一步先整理完整A76–A83测前报告与课程原生Windows快照。收益依据是新执行等待旁路与实测LSQ长链改写，不能推定IPC1.1或频率/面积已经达标。当前仍需IPC相对提高约4.5741%，周期至少缩短8.464ps，面积余量341.23μm²。正式启动集中测量前在对话汇报；不逐改测试、不使用WSL。完整正确性和相关参数/恢复/M专项在采用前仍须证明。
''', encoding='utf-8')
    proof = dict(status=classification, recorded_at=datetime.now(timezone.utc).isoformat(), new_tests_started=False,
        previous_status_only_turn_revalidated=True, original_a75_pid_absent=True, original_a75_terminal_proof=str(terminal),
        original_a75_terminal_proof_sha256=sha(terminal), last_measured_candidate=measured['candidate'],
        last_measured_metrics={k:measured[k] for k in ['ipc','fmax_mhz','area_um2','source_manifest_sha256']},
        candidates=records, pending_source_candidate=str(previous), pending_source_candidate_sha256=sha(previous/'candidate.json'),
        pending_source_metrics=None, main_active_manifest_sha256=sha(active), main_source_file_count=len(read(active)['source_sha256']),
        main_active_source_unchanged=True, previous_source_progress_proof=str(previous_proof),
        previous_source_progress_proof_sha256=sha(previous_proof), historical_store_opportunity_audit=str(audit),
        historical_store_opportunity_audit_sha256=sha(audit), report=str(REPORT), report_sha256=sha(REPORT),
        full_correctness_not_run=True, adopted=False, goal_complete=False)
    write(PROOF, proof)
    state.update(status='ER1_A83_SOURCE_PREPARED_NOT_TESTED', current_prepared_candidate=previous.name,
        current_source_candidate=previous.name, candidate_manifest_sha256=sha(previous/'candidate.json'),
        pending_source_candidate=str(previous), pending_source_candidate_sha256=sha(previous/'candidate.json'),
        candidate_tests_started=False, pending_source_candidate_tests_started=False, candidate_ipc=None,
        candidate_fmax_mhz=None, candidate_area_um2=None, candidate_metrics_belong_to=None,
        candidate_correctness_not_run=True, candidate_correctness_passed=False, candidate_correctness_finished=False,
        prepared_run=None, prepared_source_manifest_sha256=None, candidate_pretest_report=None,
        candidate_pretest_report_sha256=None, previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification=classification, previous_source_progress_proof=str(previous_proof),
        previous_source_progress_proof_sha256=sha(previous_proof), last_source_progress_proof=str(PROOF),
        last_source_progress_proof_sha256=sha(PROOF), candidates_adopted=False, goal_complete=False,
        next_work='Finish coherent A76-A83 source/ownership/area tradeoff review, freeze a new Windows serial course snapshot, report before any measurement; no per-edit tests.')
    write(STATE, state)
    print(dict(status=classification, pending=previous.name, candidates_verified=len(records), new_tests_started=False,
        proof=str(PROOF), proof_sha256=sha(PROOF), report=str(REPORT), goal_complete=False))


if __name__ == '__main__':
    main()
