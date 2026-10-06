"""Record A106 exact circular classifier while observing original A105."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a105_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A106_report_recovery_circular_compare')
PROOF = ROOT/'build/cpu2026/er1_a106_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A106_exact_circular_recovery_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 96096
    alive = live(dispatch['process_id'])
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 96096
    if not alive:
        assert phase['status'] in ['SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED', 'SERIAL_CHARACTERIZATION_COMPLETE', 'SERIAL_TIMING_FAILED', 'SERIAL_PERFORMANCE_FAILED']
    state = read(STATE)
    assert state['current_source_candidate'] == 'A105_rob_recovery_row_live'
    assert state['active_measurement_candidate'] == 'A105_rob_recovery_row_live'
    assert sha(CANDIDATE/'candidate.json') == 'b73997a083925df36f827bc80dd3c9117b8d72f53c66d66bf6a97bd2c90f8e93'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A105_rob_recovery_row_live'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_report_recovery_circular_compare.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    changed = sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes() != (parent/n).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files'])
    assert len(changed) == 3 and not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)', top)
        assert match and int(match[1]) == value, key
    backend = (CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    old_backend = (parent/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    marker = '            wire [ROB_LIVE_WIDTH-1:0] live_state;'
    assert backend[backend.index(marker):] == old_backend[old_backend.index(marker):]
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    observation = dict(observed_at=datetime.now(timezone.utc).isoformat(), run=str(RUN),
        process_id=96096, process_alive=alive, phase=phase['status'],
        timing=optional(RUN/'result/timing_only.json'), result=optional(RUN/'result/result.json'))
    REPORT.write_text('''# A106：恢复年龄判定改为等价环形位置比较

A105原监督PID96096继续单独使用冻结源、原课程工具和原日志，未重启、未改测量脚本。此记录附带当前原进程观察，A106指标不继承任何旧版IPC/面积/频率。上一报告轮只核对了同一原进程仍活跃，分类为verified wait；本轮新增独立源快照与源级推导，分类为progress。

令W=原ROB_SLOT_WIDTH，M=2^W。原unsigned W-bit age=(slot-head) mod M：slot>=head时age=slot-head，slot<head时age=M+slot-head。Wrapped组的年龄全部晚于unwrapped组；同组只需普通slot比较。因此age>branch_age完全等价于(slot_wrap&&!branch_wrap)||((slot_wrap==branch_wrap)&&(slot>branch_slot))，无候选年龄减法。

年龄>=occupancy等价于unwrapped_position>=head+occupancy。共享端点E以max(W,COUNT_WIDTH)+1位无符号加法保留任何原二值count，不截断溢出。E=q*M+e；q=0时outside=slot_wrap||slot>=e，q=1时outside=slot_wrap&&slot>=e，q>=2时outside=false。每个候选只有W位slot>=e比较。端点加法、turn和branch_wrap可先行并共享，而非放在选中候选之后。这包括occupancy0、M及大于M，故不借用可达状态；非2幂ROB仍按原2^W回绕而非改为ROB_ENTRIES回绕。entries1使用原W>=1定义，也成立。

仅三文件增加flag及替换私有LSQ报告恢复classifier：core/backend默认0保留A103原年龄式，course profile1启用新式。原candidate完整GEN/currentlive/range、head/可选held布尔选择、actual recovery apply、producer_valid、producer targetlive更新、CDB/PRF/RS/LSQ/ROB所有状态后缀保持。backend从候选live_state声明至原末尾逐字相同。新增FF/SRAM/流水边沿均0，原ISA/窗口/提交/MMIO/全GEN/参数维度不缩减。

A99关键链包含恢复资格经CDB/PRF旁路回到LSQ分配，其最高到达3.414ns，PPA周期3.474609375ns，距300MHz需至少141.276ps。A106移除已提前到各候选的减法再比较链，提供下一个不改变周期行为的结构方向；组合面积可能增加或减小，且是否仍为A105瓶颈尚未知，因此本轮不开始测试。

准备器、41源码、审阅和本记录冻结。未运行HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建；主E EU40源不变。继续原A105，结果出现后按实测路径决定A106及其余有依据的修改是否组成下一批。新测量前先汇报；仍仅在PPA>300MHz且含SRAM面积<=36000后测六perf，全部三项与19原正确性+4冻结边界程序及参数/架构审阅完成后才能采用。
''', encoding='utf-8')
    classification = 'PROGRESS_A106_EXACT_UNSIGNED_CIRCULAR_CLASSIFIER_NO_NEW_TESTS_ORIGINAL_A105_OBSERVED'
    proof = dict(status=classification, classification='PROGRESS', recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_turn_classification='VERIFIED_WAIT_ORIGINAL_A105_PID96096_CONFIRMED_LIVE',
        original_a105_observation=observation, original_a105_source_manifest_sha256=plan['source_manifest_sha256'],
        original_a105_frozen_source_check_passed=True, candidate=str(CANDIDATE),
        candidate_sha256=sha(CANDIDATE/'candidate.json'), source_file_count=41, changed_files=changed,
        candidate_source_hashes_valid=True, review_sha256=sha(review), preparer_sha256=sha(preparer),
        downstream_candidate_live_read_and_state_suffix_byte_identical=True,
        new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0, additional_tests_started=False,
        candidate_metrics=None, main_active_manifest_sha256=sha(active), main_eu_source_unchanged=True,
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
        last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification='VERIFIED_WAIT_ORIGINAL_A105_PID96096_CONFIRMED_LIVE',
        last_goal_turn_classification=classification, measurement_process_alive=alive,
        measurement_last_observed_at=observation['observed_at'], measurement_last_observation=observation,
        candidates_adopted=False, goal_complete=False,
        next_work='Continue original A105 PID96096 coherent PPA-gated measurement without edits/restart. Pending A106 removes exact unsigned candidate age subtraction using circular slot order and shared unsigned endpoint. No new tests or metrics. Inspect A105 original terminal result/new path before deciding the next material batch; pre-report before measuring, preserve all goal/correctness/parameter requirements before adoption.')
    write(STATE, state)
    print(dict(status=classification, original_a105_observation=observation,
        a106_tests_started=False, proof=str(PROOF), proof_sha256=sha(PROOF), goal_complete=False))


if __name__ == '__main__':
    main()
