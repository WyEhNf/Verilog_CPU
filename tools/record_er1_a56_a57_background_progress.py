"""Keep measured/active/pending identities separate after failure mitigation and RAS work."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write, optional
from manage_er1_a55_serial_measurement import check as check_serial
from wait_frequency_directed_native import live

ROOT = Path('E:/Verilog_cpu')
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
REPORT = ROOT / 'reports/ER1_A55R2_A56_A57_background_progress_2026-10-05.md'
PROOF = ROOT / 'build/cpu2026/er1_a55r2_a56_a57_background_progress_20261005.json'


def main():
    assert not REPORT.exists() and not PROOF.exists()
    plan = check_serial()
    state = read(STATE)
    dispatch = read(RUN / 'dispatch_identity.json')
    assert sha(RUN / 'dispatch_identity.json') == state['measurement_dispatch_sha256']
    assert dispatch['process_id'] == state['measurement_process_id'] == 102644
    alive = live(dispatch['process_id'])
    phase = optional(RUN / 'serial_phase_identity.json')
    result = optional(RUN / 'result/result.json')
    timing = optional(RUN / 'result/timing_only.json')
    observation = dict(run=str(RUN), process_id=dispatch['process_id'], process_alive=alive,
        observed_at=datetime.now(timezone.utc).isoformat(), phase=phase['status'] if phase else None,
        result=({k: result.get(k) for k in ('status', 'ipc', 'fmax_mhz', 'area_um2',
            'official_perf_expected_results_passed', 'official_correctness_suite_passed')} if result else None),
        timing=({k: timing.get(k) for k in ('status', 'fmax_mhz', 'area_um2')} if timing else None))
    candidates = []
    for name, digest, preparer in (
        ('A56_frontend_ras_predecode', '277c0c6f7d085631445838a86beb87607b274aaefc702773405d55f543887ab1', 'prepare_er1_frontend_ras_predecode.py'),
        ('A57_frontend_ras_offset_flags', '468b71cb2192ffdd5bff1808f18ac01e297d28b5e6de456f47c4edc66553c6a9', 'prepare_er1_frontend_ras_offset_flags.py')):
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
        changed = [rel for rel, source_digest in candidate['source_sha256'].items()
                   if source_digest != parent['source_sha256'][rel]]
        assert set(changed) == set(candidate['changed_from_parent_files']) == set(review['changed_files'])
        assert set(changed) == {'rtl/cpu_core.v', 'rtl/course/student_top.v'}
        candidates.append(dict(candidate=name, source_root=str(path), candidate_sha256=digest,
            source_review=str(review_path), source_review_sha256=sha(review_path), source_files_checked=41,
            parent_candidate=str(parent_path), preparation_script_sha256=candidate['preparation_script_sha256'],
            added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
            tests_started=False, adopted=False, ipc=None, fmax_mhz=None, area_um2=None))
    previous_report = Path(state['last_background_progress'])
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_report) == state['last_background_progress_sha256']
    assert sha(previous_proof) == state['last_source_progress_proof_sha256']
    active_path = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    active = read(active_path)
    for rel, digest in active['source_sha256'].items():
        assert sha(ROOT / rel) == digest, rel
    known = state['last_measured_result']
    assert known['candidate'] == 'A41_lsq_two_prefix_reclaim'
    assert sha(Path(known['run']) / 'result/result.json') == known['result_sha256']
    phase_text = f"监督PID{dispatch['process_id']}经查询{'存活' if alive else '已不存在'}；当前阶段{observation['phase']}。"
    REPORT.write_text(f'''# A55R2 测量与 A56–A57 独立源码进度

目标保持 IPC≥1.1、含SRAM总面积≤36000μm²、频率>300MHz，以及完整RV32IM/OoO/顺序提交/MMIO/参数化范围。

上一目标轮新增A53/A54/A55和官方静态镜像证据，属于实际进展。本轮完成累计结构选项审查、测试前汇报、首次测量失败诊断、相同源码的串行调度，以及独立A56/A57源码优化，归类为实际进展。

## 测量状态

首次A55监督PID78272已终止；Yosys与Verilator均报std::bad_alloc，没有IPC/PPA结果。A55R2保留相同157个源码/课程文件和工具/约束身份，改为先--timing-only，再--reuse-synth构建一次CPU并运行6perf，以降低并发内存需求。可提交内存不足只是基于日志与现场的假设，源码展开成本原因未排除。原失败现场未修改。

{phase_text} 本记录只读取现有进程/阶段文件，没有重启或新开一组测量。A55R2的已观察指标：{observation['result']}；时序阶段指标：{observation['timing']}。冻结运行使用A55，不包含新的A56/A57。

已测综合最优仍为A41：IPC **{known['ipc']:.10f}**、总面积 **{known['area_um2']:.5f}μm²**（包含SRAM **{known['sram_area_um2']:.5f}μm²**）、频率 **{known['fmax_mhz']:.5f}MHz**。6perf答案通过，完整正确性未运行；目标尚未完成。A55R2没有最终指标时不能把A41结果改名给它。

## 新增独立源码

A56将RAS调用/返回识别从“按PC选择32位指令，再解码”改为“对四个固定行内字解码，按通道选择2位标志”。调用与返回比较完全沿用原字段，越界查询标志为00。RAS有效查询、非空判断、目标、接受触发、先调用后返回再跳转的前缀优先、四项栈内容/指针/计数及状态写优先保持原行为。删除的ras_inst只是组合临时变量，未增加或删除时序状态。

A57再把通道偏移改为固定标志向量右移。对起始字W和常量通道L，先把8位标志向量F右移2L，再按W选择2位，等于旧查询(F>>(2(W+L)))&3；越界W+L≥4时两者均00。有效性 W+L<4 改为 W≤3-L。PC→字偏移加法→标志选择/有效判断依赖被删除。模式0保留32位原读取，模式1保留A56，课程模式2启用A57；适用于FE1/2/4。

两项都不新增FF、SRAM或流水级，父版本所有RAS状态所有者与后续CPU代码保持原样。这里仅优化控制路径，并未实现RAS检查点恢复或增加深度。源代码推导针对定义的二值输入，不是HDL等价或任意X状态证明。重映射、驱动尺寸、译码成本及IPC/Fmax/总面积均未知；A56/A57尚未执行HDL/lint/仿真/综合/STA/单元测试。

后续必要覆盖包括FE1/2/4各起始字/通道/越界字、JAL与JALR调用rd1/5、返回rd0/rs1=1或5/imm0及funct3过滤、空/满/环绕栈、调用/返回/跳转前缀顺序、接受/背压/错误/复位/重定向和模式回退。最终采用还需同一源码严格指标及完整课程/M/恢复/缓存正确性验证。

## 下一步

继续观察原串行监督进程，并在独立副本审查其余前端控制依赖。完成A55R2后按实际关键路径和6perf变化确定下一优先级；不对未测A57承诺数值。主E工作区EU RTL哈希未变，没有采用新候选。

证据：[串行测试前汇报](E:/Verilog_cpu/reports/ER1_A55R2_serial_pretest_2026-10-05.md)、[A57候选](F:/CPU2026Candidates/tier3_er1_20261005/A57_frontend_ras_offset_flags/candidate.json)。
''', encoding='utf-8')
    proof = dict(status='PROGRESS_A55_SERIAL_ATTEMPT_A56_A57_SOURCE_UNTESTED', recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='PROGRESS_NEW_A53_A54_A55_AND_A52_RECONCILED_STATIC_OFFICIAL_IMAGE_EVIDENCE',
        this_goal_turn_classification='PROGRESS_A55_BATCH_AUDIT_RESOURCE_FAILURE_SERIAL_DISPATCH_AND_NEW_A56_A57_SOURCE',
        objective=dict(ipc_minimum=1.1, total_area_um2_maximum=36000, fmax_mhz_strictly_greater_than=300),
        last_measured_result=known, observation=observation,
        serial_source_manifest_sha256=plan['source_manifest_sha256'], serial_pretest_report_sha256=plan['pretest_report_sha256'],
        serial_plan_sha256=sha(RUN / 'measurement_plan.json'), failure_evidence_sha256=plan['failure_evidence_sha256'],
        new_candidates=candidates, pending_candidates_tested=False,
        report=str(REPORT), report_sha256=sha(REPORT), previous_report=str(previous_report),
        previous_report_sha256=sha(previous_report), previous_proof=str(previous_proof), previous_proof_sha256=sha(previous_proof),
        main_worktree_rtl_unchanged=True, main_worktree_candidate=active['candidate'],
        main_worktree_active_record_sha256=sha(active_path), new_candidates_adopted=False, goal_complete=False)
    write(PROOF, proof)
    pending = candidates[-1]
    state.update(status='A55R2_ACTIVE_A57_PENDING_SOURCE_UNTESTED' if alive else 'A55R2_TERMINAL_A57_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=pending['candidate'], current_source_candidate=pending['candidate'],
        candidate_manifest_sha256=pending['candidate_sha256'], candidate_tests_started=False,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None, candidate_metrics_belong_to=pending['candidate'],
        candidate_correctness_passed=None, candidate_correctness_failed=None,
        candidate_correctness_finished=False, candidate_correctness_not_run=True,
        pending_source_candidate=pending['source_root'], pending_source_candidate_sha256=pending['candidate_sha256'],
        pending_source_candidate_tests_started=False, prepared_run=None, prepared_source_manifest_sha256=None,
        candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        measurement_pretest_report=str(REPORT.parent / 'ER1_A55R2_serial_pretest_2026-10-05.md'),
        measurement_pretest_report_sha256=plan['pretest_report_sha256'],
        measurement_process_alive=alive, measurement_last_observed_at=observation['observed_at'],
        measurement_last_observation=observation,
        last_background_progress=str(REPORT), last_background_progress_sha256=sha(REPORT),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        last_goal_turn_classification=proof['this_goal_turn_classification'], candidates_adopted=False, goal_complete=False,
        next_work=['Observe the original A55R2 supervisor and reconcile the same-source terminal result when available; never restart because an observation times out.',
                   'Continue independent frontend control optimization, using A55R2 measured critical paths and six-case IPC changes when available.',
                   'No A56/A57 HDL execution before a coherent material-gain batch and pretest report; preserve full RV32IM/OoO/in-order/MMIO and strict numeric objective.'])
    write(STATE, state)
    print(dict(status=proof['status'], active_process_id=dispatch['process_id'], process_alive=alive,
        measurement_phase=observation['phase'], pending_candidate=pending['candidate'], report=str(REPORT),
        pending_candidate_tested=False, goal_complete=False))


if __name__ == '__main__':
    main()
