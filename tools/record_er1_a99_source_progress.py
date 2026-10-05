"""Bind the already prepared A99 source to the completed A94 evidence; no tests."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a94_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A99_balanced_saved_identity')
REFERENCE = ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json'
PROOF = ROOT/'build/cpu2026/er1_a99_source_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A99_balanced_report_frequency_profile_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    assert not live(84416)
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 84416 and phase['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [(p['phase'],p['returncode']) for p in phase['phases']] == [('timing',0),('performance',0)]
    assert sha(REFERENCE) == '4f764cfad284d2266046be5b51ad43548da2da305ab07b5b1666b5852ffcfe6c'
    measured = read(REFERENCE)['metrics']
    assert sha(RUN/'result/result.json') == measured['result_sha256']
    assert sha(RUN/'result/ipc.json') == measured['ipc_sha256']
    assert measured['ipc'] >= 1.1 and measured['area_um2'] <= 36000 and measured['fmax_mhz'] < 300
    state = read(STATE)
    assert state['current_source_candidate'] == 'A98_saved_identity_word_mask'
    assert state['active_measurement_candidate'] is None and not state['active_measurement_process_ids']
    assert not state['candidate_tests_started']
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256'] == sha(REFERENCE)
    assert sha(CANDIDATE/'candidate.json') == '9ce4ac5d048d7e5ab8c18854a097ebcb450f1abc18dc25ad339dc60702b32704'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A98_saved_identity_word_mask'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_balanced_saved_identity.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    for name,digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    changed = sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes() != (parent/n).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 4
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in candidate['parameter_overrides'].items():
        m = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert m and int(m[1]) == value, key
    assert candidate['parameter_overrides']['FAST_STORE_BATCH'] == 0
    assert candidate['parameter_overrides']['LSQ_SAVED_IDENTITY_BALANCED_MERGE'] == 1
    lsq = (CANDIDATE/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    assert '(* keep_hierarchy = 1 *)\nmodule rv32_lsq_identity_pair_or' in lsq
    assert 'assign value_o=left_i | right_i;' in lsq
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    REPORT.write_text('''# A99：保持 A94 周期行为的频率配置

A94 原任务已完整结束，原 PID84416 不存在，串行 timing/performance 返回0/0；源码、工具、结果和运行身份通过只读冻结检查。六项性能程序 IPC 几何平均1.115262692，总面积（含 SRAM）35798.972678μm²，Fmax290.249433MHz。IPC、面积已达标；最小周期3.4453125ns，还需减少超过111.979167ps。面积余量201.027322μm²。完整19正确性尚未运行，目标未完成。

## 当前有证据支持的频率批次

A95 用原有低12位进位和高位前缀精确推导保存地址是否属于RAM，避免等待完整高位和后再比较；地址及对齐、实际数据、WB优先级保持。

A97 将保存D有效指令数 V 与 free+k 的固定阈值提前比较；晚 skip 集合 S 只检查常量子集。存在 S 的子集 T 满足 V<=free+|T|，等价于实际需求 V-|S|<=free。实际d_rs_need、整包admit、LSQ容量及信用语义保持。

A98 将保存报告的同一个grant通过原分布树驱动每组最多16位掩码，所有位仍为 grant & 原身份位。A94 _223268_ 驱动61负载/30.94fF、单门373.5ps，后级INV又167.7ps；这是控制负载集中的证据，确切叶掩码到映射门的对应仍是推断。

A99 保留每个二叉OR层为独立纯组合模块；每个节点仍为原 left|right，归纳保证所有包、ROB标签、query位和填充行完全一致。课程16行为4层。A94 query段出现约十级交替AOI/OAI，1.270→1.593ns；阻止跨层与grant掩码融合可能缩短该段，但单层OR驱动及面积成本仍未知。已有课程synth -flatten日志保留keep_hierarchy控制驱动，因此该约束机制与原工具链相容；没有改课程综合脚本。

课程top选FAST_STORE_BATCH=0，保留A96可选功能，使用A94原至多一条快存储和单身份ROB查询。A94已达IPC目标，先避免额外复制比较的面积成本。A95/A97/A98/A99的布尔重写预计与A94二值输入下周期行为相同；这不是新版本IPC实测或完整正确性证明。

## 其他方向与测量边界

额外流水边沿可能破坏同周期唤醒/原子入队并侵蚀仅1.37%的IPC余量；扩容PRF、RS、ROB或预测器没有同版工作负载瓶颈证据，且面积仅剩201μm²。独立held/normal ROB资格的第三查询会复制完整GEN/live逻辑，当前同路径掩码和OR层处理已有直接负载依据，应先判断它们是否移走此瓶颈。宽数据/标签本身没有被削减；完整GEN、ISA、MMIO与顺序提交保持。当前没有额外同路径方案能提供比这批更明确的净收益依据，长期探索不限于这些修改。

本次仅源码/哈希/既有证据记录，无HDL、lint、形式、仿真、综合、STA、单元测试或CPU构建。A99源码41文件已冻结，主E EU40文件不变，所有旧成功脚本与证据不改。上一目标轮为只读指标汇报（NO_PROGRESS），本轮采取实际源状态记录并准备后续批次；不重复启动已完成A94任务。

下一步先在对话汇报，再做一次新目录的原生Windows课程集中测量；无WSL。数值达标且收益明确后，采用前集中验证完整19正确性及M/GEN/恢复/MMIO/参数覆盖。目标仍为Fmax严格>300MHz、IPC≥1.1、总面积含SRAM≤36000μm²。
''',encoding='utf-8')
    classification = 'PROGRESS_A99_A94_CYCLE_FREQUENCY_PROFILE_BALANCED_IDENTITY_NO_TESTS'
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn='NO_PROGRESS_STATUS_METRICS_READ',no_progress_revalidated=True,
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,
        changed_files=changed,source_hashes_verified=True,review_sha256=sha(review),preparation_script_sha256=sha(preparer),
        active_fast_store_batch=0,added_declared_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,
        candidate_metrics=None,additional_tests_started=False,measured_reference=str(REFERENCE),measured_reference_sha256=sha(REFERENCE),
        original_a94_pid=84416,original_a94_pid_alive=False,original_a94_terminal_status=phase['status'],
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        artifacts_sha256={str(p):sha(p) for p in [REFERENCE,CANDIDATE/'candidate.json',review,preparer,REPORT]},
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A94_COMPLETE_PENDING_A99_FREQUENCY_SOURCE',
        current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification='NO_PROGRESS_STATUS_METRICS_READ',last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Pre-report then measure the coherent A95/A97/A98/A99 A94-cycle frequency profile once under identical native course toolchain; optional A96 batch disabled. Keep final numeric and architectural goals intact; full correctness before adoption.')
    write(STATE,state)
    print(dict(status=classification,proof=str(PROOF),proof_sha256=sha(PROOF),candidate_sha256=sha(CANDIDATE/'candidate.json'),tests_started=False))


if __name__ == '__main__':
    main()
