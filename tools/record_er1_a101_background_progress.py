"""Record the A101 source preparation without testing or changing A99."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a99_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A101_held_identity_row_query')
PROOF = ROOT/'build/cpu2026/er1_a101_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A101_held_identity_row_query_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 48248 and live(48248)
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 48248 and phase['status'] in ['SERIAL_TIMING_IN_PROGRESS','SERIAL_PERFORMANCE_IN_PROGRESS']
    state = read(STATE)
    assert state['current_source_candidate'] == 'A100_held_report_identity_query'
    assert state['active_measurement_candidate'] == 'A99_balanced_saved_identity'
    assert sha(CANDIDATE/'candidate.json') == 'ccc8fda2c30ac2dbb869f2f0a273974b64e555e1031ca1ade1073216c92546f7'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A100_held_report_identity_query' and sha(parent/'candidate.json') == candidate['parent_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_held_identity_row_query.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for name,digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    changed = sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes() != (parent/n).read_bytes())
    assert changed == candidate['changed_from_parent_files'] == ['rtl/backend/rv32_lsq.v']
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    assert candidate['parameter_overrides'] == read(parent/'candidate.json')['parameter_overrides']
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    lsq = (CANDIDATE/changed[0]).read_text(encoding='utf-8')
    old = (parent/changed[0]).read_text(encoding='utf-8')
    marker = '            assign load_report_identity_tags_o={head_tag,normal_identity_tree'
    assert lsq[lsq.index(marker):] == old[old.index(marker):]
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    REPORT.write_text('''# A101：在选择暂停报告行之前解码 ROB 查询

A99原监督PID48248记录时仍在原串行任务中运行；157文件快照、工具、候选、准备脚本、审阅及报告冻结检查通过。A101只在独立F盘41源码中改一份LSQ文件，无HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建；原运行源、旧成功脚本和主E EU40源码不改。

A100已把普通/head/held身份独立核对，但held分支仍是保存LSQslot→读取16bit ROBtag→解码12bit bank query→读取9bit当前ROB live/GEN。A101把bank解码移到每个保存LSQ行，原held_reader直接选择28bit的{preparedquery,fulltag}。因此移除选中ROBslot编码后的解码层，标签的全部GEN/valid位保持，读选择仍使用原held票据的slot。

对任何合法LSQ索引r：原输出是tag[r]和decode(tag[r])；新row packet就是{decode(tag[r]),tag[r]}，原reader一热rowhit选择同r，输出相同。非法索引在原reader返回零tag，tag[0]=0保证该候选live为假；新preparedquery可以为零，但标签也为零，资格仍假。原H=true必须存在完整LSQtag匹配的真实行，因此非法私有值不能触发实际事件。H/head晚bool选择、完整8ROBGEN/9LSQGEN、range/live/complete/reported、cancel/reset/flush/recovery保持。

新增声明FF/SRAM/流水边沿/ROB查询数量均为0；沿用A100新增第三查询，本次只扩展其LSQ私有组合读取16→28bit。每组最多16bit掩码控制，可能额外增加12bit路由/OR和一个wordselect驱动。原普通身份query也按同保存ROBtag解码，综合可能共享这些等式，但不能当作面积已下降或时序已改善。A100 normal/head/private输出之后的整个LSQ后缀（含公共query/包与所有状态/helper）逐字不变；backend/core/top以及参数值不变。

当前无A99/A100/A101新指标。最新测量仍A94：IPC1.115262692、含SRAM总面积35798.972678μm²、Fmax290.249433MHz。需约112ps改善，面积余量仅201μm²；新结构有串行依赖依据但净收益待原A99结果判断。A99仅在PPA双门槛通过后测六项IPC。未并行或重复测量，未采用；目标严格>300MHz/IPC≥1.1/总面积含SRAM≤36000μm²及完整RV32IM/OoO/顺序提交/MMIO/参数化保持。采用前仍需集中19正确性与M/GEN/恢复/MMIO/参数覆盖。
''',encoding='utf-8')
    classification = 'PROGRESS_A99_ORIGINAL_LIVE_A101_HELD_ROW_ROB_BANK_QUERY_PREDECODE_NO_NEW_TESTS'
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a99_pid=48248,original_a99_pid_alive_at_record=True,original_a99_phase_observed=phase['status'],
        original_a99_source_manifest_sha256=plan['source_manifest_sha256'],original_a99_frozen_source_check_passed=True,
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,
        changed_files=changed,candidate_source_hashes_valid=True,review_sha256=sha(review),preparer_sha256=sha(preparer),
        all_public_and_lsq_state_suffix_byte_identical=True,new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,new_rob_live_queries=0,
        additional_tests_started=False,candidate_metrics=None,main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        artifacts_sha256={str(p):sha(p) for p in [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'dispatch_identity.json',CANDIDATE/'candidate.json',review,preparer,REPORT]},
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue exact original A99 PID48248 PPA-gated native course measurement, no restart/edit. Pending A101 inherits A100 late-bool independent identities and moves held per-row ROBbankdecode before original LSQslotread. No newtests/metrics. Use original A99 result to select further structural gain; pre-report any new batch and complete correctness coverage before adoption.')
    write(STATE,state)
    print(dict(status=classification,a99_original_pid_alive=True,a101_tests_started=False,proof=str(PROOF),proof_sha256=sha(PROOF),goal_complete=False))


if __name__ == '__main__':
    main()
