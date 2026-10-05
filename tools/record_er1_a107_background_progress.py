"""Record the A107 allocation boundary change without additional measurement."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a105_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A107_allocation_payload_preselect')
PROOF = ROOT/'build/cpu2026/er1_a107_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A107_allocation_event_and_payload_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 96096
    alive = live(96096)
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 96096
    if not alive:
        assert phase['status'] in ['SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED', 'SERIAL_CHARACTERIZATION_COMPLETE', 'SERIAL_TIMING_FAILED', 'SERIAL_PERFORMANCE_FAILED']
    state = read(STATE)
    assert state['current_source_candidate'] == 'A106_report_recovery_circular_compare'
    assert state['active_measurement_candidate'] == 'A105_rob_recovery_row_live'
    assert sha(CANDIDATE/'candidate.json') == '225ee7905cbba7104a4825b751aeecf25429291ae4e64f32f9cb7595086ff44d'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A106_report_recovery_circular_compare'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_allocation_payload_preselect.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    changed = sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes() != (parent/n).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 4
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)', top)
        assert match and int(match[1]) == value, key
    lsq = (CANDIDATE/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    old = (parent/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    marker = '        for(payload_row=0;payload_row<LSQ_ENTRIES;payload_row=payload_row+1) begin:g_payload_row'
    assert lsq[lsq.index(marker):] == old[old.index(marker):]
    start = '    always @* begin\n        // Allocation/response temporaries retain unconditional defaults.'
    end = '    // Admission is resolved beside bounded output groups.'
    assert lsq[lsq.index(start):lsq.index(end)] == old[old.index(start):old.index(end)]
    backend = (CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert '.alloc_plan_valid_i(d_lsq_need)' in backend
    assert 'assign lsq_alloc_valid=d_lsq_need & {BE_WIDTH{d_admit}};' in backend
    assert '(d_lsq_demand<=lsq_free_count)' in backend
    assert 'LSQ_ALLOC_SLOT_PRESELECT_ACTIVE=(LSQ_ALLOC_SLOT_PRESELECT!=0) &&\n        (DISPATCH_PIPELINE!=0) && (DISPATCH_ELASTIC!=0);' in backend
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    observation = dict(observed_at=datetime.now(timezone.utc).isoformat(), run=str(RUN), process_id=96096,
        process_alive=alive, phase=phase['status'], timing=optional(RUN/'result/timing_only.json'),
        result=optional(RUN/'result/result.json'))
    REPORT.write_text('''# A107：分配标签载荷先行，真实分配事件仍是唯一写入门槛

本轮以A106为父快照，再分离LSQ分配的预备完整身份与晚到接受事件。原A105继续单独测量；A106和A107均未启动测试，三项指标未知。当前原进程观察与冻结身份附于JSON记录，主E EU40源不变。

A99关键路径后段在实际分配票据valid处经过212ps NAND3和112ps INV，到d_rob_value_tree.signal_i[0]为2.982ns，再进入LSQ load状态写入链。这个别名是LSQ分配tag，不是ROB宽数据读取。A104已分布部分实际fire负载，但票据仍把晚fire编码进整个标签，又被独立实际write事件门控。

新私有alloc_payload_tag从既有planned sparse-lane slot和同一generation_next完整行调用原make_lsq_tag，先得到{fullGEN,slot,kind,valid1}。public alloc_lsq_tag/fire/count/ready原组合过程逐字保持；private载荷仅替换三个真实事件消费者：backend ROB-to-LSQ map、store RS link以及LSQ allocation-load selection。这三个消费者的原写入/选择条件均蕴含actual alloc_fire，未放宽资源/flush/recovery门槛。

原ALLOC_SLOT_PRESELECT契约是只要有任何真实fire，plan==fire。backend elastic d_admit以整个稀疏memory bundle需求<=当前free为门槛，因此admit时全部need同序fire，否则没有fire；plan=d_lsq_need，actualvalid=d_lsq_need&d_admit。对应实际lane的原slot与planned slot均为tail加之前fire/plan数量，回绕与截断相同；从相同GEN-next行使用原make函数得到逐bit相等的标签。不改变GEN0原组合行为，也不截断9位LSQGEN。空/未fire载荷可以不同，但原event_select遮罩或word_bank write门槛不观察它。

core/backend新flag默认0，course1；实际启用还要求原slot preselection的elastic+pipeline guard。LSQ自身flag与旧slotflag共同启用，否则private直接等于public旧tag。公开标签在flush期间的旧非零行为仍保持。LSQ所有payload行、metadata、回收、选择/响应/hold、GEN状态owners及helpers后缀逐字相同，原allocator过程也逐字相同；backend map/link事件及所有时序状态不改。

这种变换从载荷网络拿掉晚fire、稀疏槽位编码、GEN读取的串行依赖，真实接受只走原事件网络。活跃profile旧publictag的未使用查询可能被裁掉，但面积和频率以实际综合为准。新增FF/SRAM/流水边沿均0，现有窗口/ISA/OoO/顺序commit/MMIO/cache/预测规模保留。对BE1/2/4及旧LSQ合法power-of-two/entries1几何，实际fire始终受free_count限制，未分配的越界计划槽位不能制造事件。

目前A106提供恢复分类的算术链缩短，A107提供分配边界事件/载荷分离；两项为下一批源级方案，不借用A94或A105指标。暂不测试：等待A105原始终态与新路径再判断后续批次。新测试前先汇报；仅PPA>300MHz且含SRAM面积<=36000后测六perf，三项达标后复用同CPU集中19课程正确性+4既有冻结边界程序，并做参数/架构审阅。目标尚未完成，未采用。
''', encoding='utf-8')
    classification = 'PROGRESS_A107_PLANNED_FULLGEN_ALLOCATION_PAYLOAD_SEPARATE_FROM_REAL_EVENT_NO_NEW_TESTS'
    proof = dict(status=classification, classification='PROGRESS', recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a105_observation=observation, original_a105_source_manifest_sha256=plan['source_manifest_sha256'],
        original_a105_frozen_source_check_passed=True, candidate=str(CANDIDATE),
        candidate_sha256=sha(CANDIDATE/'candidate.json'), source_file_count=41, changed_files=changed,
        candidate_source_hashes_valid=True, review_sha256=sha(review), preparer_sha256=sha(preparer),
        lsq_public_allocator_byte_identical=True, lsq_payload_metadata_state_suffix_byte_identical=True,
        backend_atomic_sparse_plan_contract_source_bound=True, new_ff_bits=0, new_sram_bits=0,
        new_pipeline_edges=0, additional_tests_started=False, candidate_metrics=None,
        main_active_manifest_sha256=sha(active), main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous), previous_source_progress_proof_sha256=sha(previous),
        artifacts_sha256={str(p):sha(p) for p in [RUN/'measurement_plan.json', RUN/'source_manifest.json',
            RUN/'course_windows_config.json', RUN/'dispatch_identity.json', CANDIDATE/'candidate.json',
            review, preparer, REPORT]}, adopted_to_main=False, goal_complete=False)
    write(PROOF, proof)
    state.update(current_source_candidate=CANDIDATE.name, current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'), pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'), pending_source_candidate_tests_started=False,
        pending_source_candidate_has_measured_metrics=False, last_source_progress_proof=str(PROOF),
        last_source_progress_proof_sha256=sha(PROOF), last_background_progress=str(PROOF),
        last_background_progress_sha256=sha(PROOF), previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification=classification, measurement_process_alive=alive,
        measurement_last_observed_at=observation['observed_at'], measurement_last_observation=observation,
        candidates_adopted=False, goal_complete=False,
        next_work='Continue frozen original A105 PID96096 PPA-gated run. Pending A107 includes A106 circular recovery plus planned fullGEN allocation payload under original real events. No new tests/metrics. Bind original A105 terminal/new path before selecting further supported work and pre-reporting a coherent next batch. Preserve full numerical/architecture/correctness/parameterization scope before adoption.')
    write(STATE, state)
    print(dict(status=classification, original_a105_observation=observation, a107_tests_started=False,
        proof=str(PROOF), proof_sha256=sha(PROOF), goal_complete=False))


if __name__ == '__main__':
    main()
