"""Record A100 source while the original A99 measurement is still live."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a99_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A100_held_report_identity_query')
PROOF = ROOT/'build/cpu2026/er1_a100_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A100_independent_held_report_identity_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 48248 and live(48248)
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 48248 and phase['status'] in ['SERIAL_TIMING_IN_PROGRESS','SERIAL_PERFORMANCE_IN_PROGRESS']
    state = read(STATE)
    assert state['current_source_candidate'] == 'A99_balanced_saved_identity'
    assert state['active_measurement_candidate'] == 'A99_balanced_saved_identity'
    assert state['active_measurement_source_manifest_sha256'] == plan['source_manifest_sha256']
    assert sha(CANDIDATE/'candidate.json') == '9f2025e9d7e5a07055d68f88d81f98805ff3540552ddaa939076cdf750ee83b4'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A99_balanced_saved_identity'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256'] == plan['candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_held_report_identity_query.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    for name,digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    changed = sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes() != (parent/n).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 4
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in candidate['parameter_overrides'].items():
        m = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert m and int(m[1]) == value, key
    assert candidate['parameter_overrides']['LSQ_HELD_LOAD_IDENTITY_QUERY'] == 1
    assert candidate['parameter_overrides']['FAST_STORE_BATCH'] == 0
    lsq = (CANDIDATE/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    original = (parent/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    marker = '    generate if(REPORT_ROB_PREDECODE!=0) begin:g_report_rob_query'
    assert lsq[lsq.index(marker):] == original[original.index(marker):]
    for start,end in [('    wire report_hold_live=','    generate if(LOAD_COMPLETION_BYPASS!=0)'),
        ('                assign report_hold_matches[report_row]=','                if(HELD_LOAD_IDENTITY_ACTIVE!=0)')]:
        a=lsq[lsq.index(start):lsq.index(end,lsq.index(start))]
        if 'HELD_LOAD_IDENTITY_ACTIVE' in end:
            old_end='                if(HEAD_LOAD_IDENTITY_ACTIVE!=0)'
        else:
            old_end=end
        b=original[original.index(start):original.index(old_end,original.index(start))]
        assert a == b, start
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    REPORT.write_text('''# A100：普通、暂停保持和队首报告独立核对身份

记录时A99原监督PID48248仍存在；原157文件快照、候选/工具/准备脚本/报告和源证据通过冻结检查。A100仅在独立F盘41源码目录生成，未改变原A99运行或主E EU40文件。没有启动新的HDL/lint/形式/仿真/综合/STA/单元测试。

A94已测IPC1.115262692、含SRAM面积35798.972678μm²、频率290.249433MHz；A99尚未产生新指标。A100不借用这些指标。

## 结构改动

原资格路径先用较晚的held-live在16行grant之间切换，再掩码/合并28位ROB身份和query，之后读取当前ROB valid与完整8bit GEN。新模式普通报告的28位身份树只依赖原普通priority；held身份则用保存的完整LSQ票据中的slot提前读取原rob_tag_mem，并产生原低/高bank query；队首身份保持。三份当前ROB valid/GEN独立核对，原held/head选择只控制一个live资格位。

不新增完整85位数据包副本，不改原public报告包、query、valid、held捕获、range/GEN/complete检查、回收/入队、错误/恢复和顺序提交。声明FF、SRAM和流水边沿增量均为0；新增一份9位ROB live读取（课程ROB32）和28位普通身份树（LSQ16），组合面积可能增加。FAST_STORE_BATCH仍0，ISA/GEN/队列/cache/预测容量不减。

## 等价推导

H=held-live。H=0时原saved_grant逐行等于普通priority P，新normal树每位采用同P&identity与相同OR递推，因此candidate0与原tag/query一致。队首候选与选择保持。

H=1时至少一个原held_match为真。原函数要求tag有效、当前LSQvalid、slot相同且完整LSQGEN相同，所有不同真实行的slot值不同，故至多一行匹配，其行号严格为保存held_tag中的slot。原held树因此输出该行rob_tag_mem及其原bank解码；新held_reader读取同一保存行、直接解码同位域，因此第三候选身份一致。这个证明不移除原range/live/complete/reported或全GEN门槛，也不依赖假设某条不可达路径。

后端所有候选保留tag[0]、ROBslot范围、当前ROBvalid及全部8GEN比较；仅由原H/head在各自结果之间选择。实际load事件/reset/flush/recovery/cancel/CDB暂停条件仍原代码。未被选的私有query可不同，不能凭它创建完成事件。原public query之后的整个LSQ后缀（含状态更新和helper）逐字不变。

## 收益判断与后续

A94从held资格0.6385/0.7101ns经过saved query1.593ns、ROBlive1.811ns、完成选择2.185ns到分配GEN/FF3.385ns。A100把held选择从宽身份/ROB查询之前移动到bool结果之后，有直接串行依赖收益依据；但普通priority路径、新读取扇出、额外面积或其他路径可能主导。面积余量201μm²很小，不宣称必然达标。

A99已预报后启动当前集中PPA；只有其Fmax>300且总面积≤36000才会构建CPU和测六项IPC。A100是等待期间独立准备的下一方案，不并行启动测量、不修改已冻结运行；先用原A99结果判断新瓶颈与净面积余量。若需要新批，先汇报，采用前仍集中验证完整19正确性及M/GEN/恢复/MMIO/参数覆盖。目标仍严格>300MHz/IPC≥1.1/含SRAM≤36000μm²，未达成。
''',encoding='utf-8')
    classification = 'PROGRESS_A99_ORIGINAL_LIVE_A100_INDEPENDENT_HELD_NORMAL_HEAD_FULLGEN_NO_NEW_TESTS'
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a99_pid=48248,original_a99_pid_alive_at_record=True,original_a99_phase_observed=phase['status'],
        original_a99_source_manifest_sha256=plan['source_manifest_sha256'],original_a99_frozen_source_check_passed=True,
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,
        candidate_source_hashes_valid=True,changed_files=changed,review_sha256=sha(review),preparation_script_sha256=sha(preparer),
        original_public_query_and_lsq_state_suffix_byte_identical=True,original_held_range_generation_checks_byte_identical=True,
        added_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,extra_rob_live_queries=1,
        additional_tests_started=False,candidate_metrics=None,
        artifacts_sha256={str(p):sha(p) for p in [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'dispatch_identity.json',review,preparer,CANDIDATE/'candidate.json',REPORT]},
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue original A99 PID48248 PPA-gated native course run without editing or restarting it. Pending A100 splits held/normal/head qualification before late bool selection, no tests/metrics; use A99 result to decide whether this extra query has needed net frequency/area gain. Full goal and correctness scope preserved.')
    write(STATE,state)
    print(dict(status=classification,a99_original_pid_alive=True,a100_tests_started=False,proof=str(PROOF),proof_sha256=sha(PROOF),goal_complete=False))


if __name__ == '__main__':
    main()
