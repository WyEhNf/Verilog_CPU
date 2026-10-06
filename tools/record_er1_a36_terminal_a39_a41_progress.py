"""Record terminal A36 evidence and distinct, untested A39-A41 source progress."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write

ROOT = Path('E:/Verilog_cpu')
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')
PROFILE_ROOT = Path('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005')
REPORT = ROOT / 'reports/ER1_A36_terminal_A39_A41_source_progress_2026-10-05.md'
PROOF = ROOT / 'build/cpu2026/er1_a36_terminal_a39_a41_source_progress_20261005.json'
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not REPORT.exists() and not PROOF.exists()
    measured = read(RUN / 'result/result.json')
    ipc = read(RUN / 'result/ipc.json')
    manifest = read(RUN / 'source_manifest.json')
    assert measured['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert measured['official_perf_expected_results_passed']
    assert measured['official_correctness_suite_not_run']
    assert not measured['thread_objective_numeric_requirements_met']
    source = Path(measured['source'])
    for name, digest in manifest['snapshot_sha256'].items():
        assert sha(source / name) == digest, name
    frozen_scripts = {
        'tools/run_course_standard_windows.py': '2571b2a5f7df360a8b8262c866f0fa7bc26aa3637759ffb942cb0b6cf4910b2a',
        'tools/prebuild_course_windows.py': '80b98daf0d79cffca49709aa142102ec23cf2f6e5f7420c18d24d9e798d00be1',
        'tools/verilator_windows_time_zero.cpp': '2cda7110112c75f7f9d39dfbb45ca4789b98585bfb7ddcc32614458c570c62df',
        'tools/manage_er1_a36_measurement.py': 'a8604b0e3ca23763796340c83b854488f2945d02ab14c75df2e4061cdb2d49e0',
    }
    for name, digest in frozen_scripts.items():
        assert sha(ROOT / name) == digest, name
    profile = read(PROFILE_ROOT / 'result.json')
    plan = read(PROFILE_ROOT / 'plan.json')
    assert profile['status'] == 'THREE_CASE_HOST_PROFILE_COMPLETE'
    assert profile['same_model_as_a36'] and not profile['model_recompiled']
    assert not profile['new_synthesis'] and not profile['new_sta']
    assert profile['plan_sha256'] == sha(PROFILE_ROOT / 'plan.json')
    official_cycles = {row['name']: row['cycles'] for row in ipc['results']}
    for row in profile['results']:
        assert row['official_answer_passed'] and row['cycles_exact_a36']
        assert row['cycles'] == official_cycles[row['name']]
        assert row['observations']['final_debug_cycles'] == row['cycles']
        assert row['observations']['samples'] == row['cycles'] - 11

    candidates = []
    reviews = []
    for name, review_name in [
        ('A37_mdu_local_payload_owners', 'A37_source_review.json'),
        ('A38_instruction_sram_command_lanes', 'A38_source_review.json'),
        ('A39_recovery_preview_older_issue', 'A39_source_review.json'),
        ('A40_compact_gshare_parallel_feedback', 'A40_source_review.json'),
        ('A41_lsq_two_prefix_reclaim', 'A41_source_review.json'),
    ]:
        candidate = BASE / name
        c = read(candidate / 'candidate.json')
        assert not c['tests_started'] and not c['adopted']
        for filename, digest in c['source_sha256'].items():
            assert sha(candidate / filename) == digest, filename
        reviews.append(read(BASE / review_name))
        candidates.append(dict(candidate=name, source_root=str(candidate),
            candidate_sha256=sha(candidate / 'candidate.json'),
            parent=c['parent_candidate'], changed_files=c['changed_from_parent_files'],
            source_review=str(BASE / review_name), source_review_sha256=sha(BASE / review_name),
            tests_started=False, adopted=False, ipc=None, area_um2=None, fmax_mhz=None))
    active = read(ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json')
    main_mismatches = [name for name, digest in active['source_sha256'].items()
                       if not (ROOT / name).exists() or sha(ROOT / name) != digest]
    assert not main_mismatches, main_mismatches

    terminal = dict(status=measured['status'], candidate='A36_dcache_word_response',
        run=str(RUN), process_id=92848, process_alive=False,
        terminal_artifact_authority='result/result.json; original manager observe confirms original process missing',
        ipc=measured['ipc'], fmax_mhz=measured['fmax_mhz'],
        minimum_period_ns=measured['minimum_period_ns'], area_um2=measured['area_um2'],
        sram_area_um2=measured['area']['sram_area_um2'],
        sequential_area_um2=measured['area']['sequential_area_um2'],
        combinational_area_um2=measured['area']['combinational_area_um2'],
        official_perf_expected_results_passed=True,
        full_correctness_not_run=True, full_correctness_passed=False,
        objective_numeric_met=False,
        source_manifest_sha256=sha(RUN / 'source_manifest.json'),
        candidate_sha256=manifest['candidate_manifest_sha256'],
        result_sha256=sha(RUN / 'result/result.json'), ipc_sha256=sha(RUN / 'result/ipc.json'),
        ppa_sha256=sha(RUN / 'result/synth/opt/report.json'), rows=ipc['results'])
    critical = read(RUN / 'result/synth/opt/critical_paths.json')['checks'][0]
    observations = []
    for row in profile['results']:
        o = row['observations']
        observations.append(dict(name=row['name'], samples=o['samples'],
            frontend_empty_fraction=o['frontend_empty']/o['samples'],
            branch_pending_fraction=o['branch_pending']/o['samples'],
            trace_all_blocked_fraction=o['trace_all_blocked']/o['samples'],
            lsq_full_fraction=o['lsq_full']/o['samples'],
            mean_lsq_occupancy=o['lsq_occupancy_sum']/o['samples'],
            selected_predictor_feedback=o['accepted_predictor_feedback'],
            selected_correct_feedback=o['correct_predictor_feedback'],
            selected_feedback_correct_fraction=o['correct_predictor_feedback']/o['accepted_predictor_feedback'],
            cycles_exact_a36=True, official_answer_passed=True))
    proof = dict(status='PROGRESS_A36_TERMINAL_THREE_CASE_EVIDENCE_A39_A41_SOURCE_UNTESTED',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='NO_PROGRESS_METRICS_REPORT_REVALIDATED_TERMINAL_A36_A16R2',
        this_goal_turn_classification='PROGRESS_NEW_A39_A40_A41_SOURCE_AND_PROFILE_ATTRIBUTION',
        objective=dict(fmax_mhz_strictly_greater_than=300, ipc_minimum=1.1, total_area_um2_maximum=36000),
        last_measurement=terminal, candidates=candidates,
        a36_source_snapshot_files_checked=len(manifest['snapshot_sha256']),
        frozen_host_scripts_sha256=frozen_scripts,
        profile_result=str(PROFILE_ROOT / 'result.json'),
        profile_result_sha256=sha(PROFILE_ROOT / 'result.json'),
        profile_plan_sha256=sha(PROFILE_ROOT / 'plan.json'),
        profile_report=plan['report'], profile_report_sha256=plan['report_sha256'],
        profile_scope='three existing-model cases, readonly host observers, exact original cycles and official answers',
        profile_observations=observations, counters_overlap_and_are_not_additive_lost_cycles=True,
        rs_ready_during_pending_is_not_proof_of_older_survivor=True,
        primary_icache_counters_exclude_filter_hits=True,
        current_timing_endpoint=critical['endpoint'], current_timing_arrival_ns=critical['data_arrival_time']*1e9,
        critical_paths_sha256=sha(RUN / 'result/synth/opt/critical_paths.json'),
        main_worktree_candidate=active['candidate'], main_worktree_source_unchanged=True,
        candidate_tests_started_this_turn=False, goal_complete=False,
        next_work=[
            'Review the combined A41 architecture before any new HDL measurement. Reuse existing native frozen evidence, never restart terminal runs.',
            'Resolve median/qsort/towers memory and branch priorities: inspect miss-event semantics, demand/MSHR merging and store/load service; existing frontend request chaining and LSQ selection full replacement already work and are not new proposals.',
            'Consider further structural wins only when backed by source/timing/profile evidence; A39/A40/A41 IPC and mapped area/frequency remain unknown.',
            'Once the coherent candidate has material-gain evidence and the remaining actionable architecture has been assessed, report before one native course-standard measurement.',
            'Final adoption still needs same-source Fmax>300, IPC>=1.1, area incl SRAM<=36000 and full relevant correctness/M/selective-recovery/cache/backpressure coverage.'
        ])
    rows = '\n'.join(f"| {r['name']} | {r['instructions']} | {r['cycles']} | {r['ipc']:.6f} |" for r in ipc['results'])
    profrows = '\n'.join(
        f"| {o['name']} | {o['branch_pending_fraction']*100:.2f}% | {o['selected_feedback_correct_fraction']*100:.2f}% | {o['lsq_full_fraction']*100:.2f}% | {o['mean_lsq_occupancy']:.3f} |"
        for o in observations)
    text = f'''# ER1：A36 终态测量与 A39–A41 源码进展

记录时间：{proof['recorded_at']}。目标保持 **Fmax >300 MHz、IPC ≥1.1、包含 SRAM 的总面积 ≤36,000 μm²**。目标尚未完成。

## 已测结果与验证范围

A36 原测量已经结束；原 PID 92848 已不存在，原 manager 的 observe 再次确认终态和完整结果，没有重启。课程指定版本 Windows 原生工具链、原六项 perf、latency=10、官方答案和动态指令分子保持不变。

| 指标 | A36 | 目标 | 状态 |
| --- | ---: | ---: | --- |
| IPC 几何平均 | {measured['ipc']:.8f} | ≥1.1 | 还需提升 {(1.1/measured['ipc']-1)*100:.2f}% |
| Fmax | {measured['fmax_mhz']:.6f} MHz | >300 MHz | 还差约 {300-measured['fmax_mhz']:.6f} MHz |
| 总面积 | {measured['area_um2']:.6f} μm² | ≤36,000 μm² | 达标，余量 {36000-measured['area_um2']:.6f} μm² |
| SRAM 面积 | {measured['area']['sram_area_um2']:.6f} μm² | 计入总面积 | 已计入 |

逻辑面积 {measured['area']['logic_area_um2']:.6f} μm²（组合 {measured['area']['combinational_area_um2']:.6f}、时序 {measured['area']['sequential_area_um2']:.6f}）。最小周期 {measured['minimum_period_ns']:.10f} ns。六项 perf 退出答案全部通过；19 项完整正确性与新增 M/恢复覆盖未运行，不据此宣称完整 RV32IM 验证。

| 程序 | 参考动态指令数 | 官方仿真周期 | IPC |
| --- | ---: | ---: | ---: |
{rows}

原始结果：[result.json](F:/CPU2026CourseRuns/ER1_A36_tier3_20261005/result/result.json)、[IPC](F:/CPU2026CourseRuns/ER1_A36_tier3_20261005/result/ipc.json)。全部 {len(manifest['snapshot_sha256'])} 个冻结源文件重新核对哈希一致。旧完全验证候选 A16R2 仍独立保留（IPC 0.94636559、Fmax 367.420165 MHz、总面积 39,982.760814 μm²），不能把它的频率或正确性与 A36 指标拼接。

## 当前真实关键路径

当前 A36 最慢路径是 `{critical['startpoint']}` → `{critical['endpoint']}`，数据到达 {critical['data_arrival_time']*1e9:.3f} ns；最后地址门驱动八个 SRAM 宏端口，40 fF，延迟 0.479 ns。A38 已针对该实际新路径去掉 hit-acceptance 对读地址的依赖，并让每个命令叶节点驱动单个宏，原容量、宏数量及读延迟不变。A37 对旧 MDU 高扇出路径的修改也保留，但不能把旧 A21 的瓶颈当作 A36 新瓶颈。

## 一次三程序观察结果

此前已先报告后执行一次 median/qsort/towers 观察；复用 A36 已构建模型，只加入只读宿主 C++ 计数。没有 RTL 重新生成、模型重编译、综合或 STA。三个程序答案通过，周期分别 9452/159725/5815，与原 A36 完全一致。观察已经结束，不重复运行。

| 程序 | 分支 pending 周期占比 | 银行选择反馈正确比例 | LSQ 满占比 | LSQ 平均占用 |
| --- | ---: | ---: | ---: | ---: |
{profrows}

统计分母是排除复位/停机后的 active samples（恰为官方 cycles−11），不替代官方 IPC 分母。停顿计数相互重叠，不能相加成为可回收周期；pending 时 ready RS 可能是错误路径较年轻指令，不能算作较老存活指令。预测计数包含 branch/JAL/JALR、同银行仲裁，不是单独条件方向准确率。主 I-cache 计数不包含 L0 filter 命中。D-cache miss-event 含义尚需继续从原源码归因，不据 752 次事件直接断言 752 次外存读。

证据：[三程序结果](F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json)。

## 本轮已实现源码

以下均是独立 F 盘源码候选，继承 A37/A38，**没有启动 HDL 构建、lint、仿真、综合、STA 或单元测试，没有采用到主工作树，性能指标全部未知**。

1. **A39：恢复 preview 期间较老指令继续执行。** 使用已经登记且获 ROB 验证的误预测分支，只有有效 RS 选择、环形年龄严格小于分支且在 ROB 占用内的指令可以发射；只在 descriptor 未准备好的 preview 那拍放行。apply 那拍仍禁止发射，因为 RS 的 flush 优先级会忽略正常 issue-release，简单同时放行会重复发射。共享 ALU/MDU 的 issue-valid、RS ready 和 MDU 选择资格保持一致。不新增状态或流水拍。ISSUE_PIPELINE/非选择恢复配置保留原回退。
2. **A40：紧凑 gshare、逐路准确索引训练、同拍历史恢复。** 延伸原紧凑目标/间接 BTB 到模式 2；预测时保存的每路索引随同该路有效完整标签反馈一起被同一银行 grant 选择，不用当前历史或另一条分支的索引。提前重定向同拍使用该分支的 checkpoint 加实际方向恢复 GHR，保留原 preview 方式的寄存历史。256 个 BHT 计数器和 6 位历史不缩减；仅间接 BTB 参数化 16/32/64，本配置 32 项。释放 1,280 位，新增元数据及历史声明上界 848 位；按可用位计算约净减少 644 位 /187.79 μm² 的 FF 组件。**这是状态账，不是综合总面积或 IPC 提升保证。** 表读、XOR、控制树需以后统一测量。
3. **A41：LSQ 连续两条回收。** 保留原队首回收条件；若紧随其后的条目是已完成且此前已经成功报告的 load，可同拍清空两行、head 前进两格、occupancy 减二。第二条不能是 store，不扩宽 load report/store ack，不提前提交，不加容量或状态，不绕过 reset/flush/恢复；allocation 仍按原寄存空闲量。解决每拍可分配两条而只回收一条的结构限制，收益未测。

候选：[A39](F:/CPU2026Candidates/tier3_er1_20261005/A39_recovery_preview_older_issue/candidate.json)、[A40](F:/CPU2026Candidates/tier3_er1_20261005/A40_compact_gshare_parallel_feedback/candidate.json)、[A41](F:/CPU2026Candidates/tier3_er1_20261005/A41_lsq_two_prefix_reclaim/candidate.json)。逐项源码论证与待验证场景：[A39 review](F:/CPU2026Candidates/tier3_er1_20261005/A39_source_review.json)、[A40 review](F:/CPU2026Candidates/tier3_er1_20261005/A40_source_review.json)、[A41 review](F:/CPU2026Candidates/tier3_er1_20261005/A41_source_review.json)。

## 继续工作的边界

下一步继续检查合并候选的真实前端、预测恢复和内存服务瓶颈，再确定测试批次。前端已经实现当拍 response/request chaining，LSQ 选择寄存器已允许原操作结束当拍替换，都不再当作新优化。仍有 D-cache miss/合并语义、存储服务和实际分支行为可以从既有数据与源码分析，因此本轮不提前开测。

与方向预测有关的通用依据是 [BOOM 官方 backing predictor 文档](https://docs.boom-core.org/en/latest/sections/branch-prediction/backing-predictor.html)：预测索引使用 PC 与全局历史的组合；投机历史需要快照和误预测恢复。这支持历史管理方式，不证明本 CPU 的 gshare 实际准确率、面积或 IPC。

主 E 盘工作树保持 EU，所有其记录的源文件哈希一致；冻结 A36、旧测量、宿主脚本保持原身份。优化目标不缩减为仅面积达标，下一次测试前仍先汇报。最终通过还需要同源三指标及完整正确性和 M、选择恢复、cache/转发、回压等相关覆盖。
'''
    REPORT.write_text(text, encoding='utf-8')
    proof['report'] = str(REPORT)
    proof['report_sha256'] = sha(REPORT)
    proof['recording_script_sha256'] = sha(Path(__file__))
    write(PROOF, proof)
    state = read(STATE)
    state.update(status=proof['status'], current_prepared_candidate=candidates[-1]['candidate'],
        candidate_manifest_sha256=candidates[-1]['candidate_sha256'],
        candidates_adopted=False, candidate_tests_started=False,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        candidate_metrics_belong_to=candidates[-1]['candidate'],
        candidate_correctness_passed=None, candidate_correctness_failed=None,
        candidate_correctness_finished=False, candidate_correctness_not_run=True,
        last_measured_candidate=terminal['candidate'], last_measured_result=terminal,
        measurement_run=str(RUN), measurement_process_id=None,
        measurement_process_alive=False, active_measurement_candidate=None,
        active_measurement_process_ids=[], active_measurement_source_manifest_sha256=None,
        prepared_run=None, prepared_source_manifest_sha256=None,
        candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        pending_source_candidate=candidates[-1]['source_root'],
        pending_source_candidate_sha256=candidates[-1]['candidate_sha256'],
        pending_source_candidate_tests_started=False,
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        last_goal_turn_classification=proof['this_goal_turn_classification'],
        last_background_progress=str(REPORT), last_background_progress_sha256=sha(REPORT),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_existing_model_profile=proof['profile_result'],
        last_existing_model_profile_sha256=proof['profile_result_sha256'],
        next_work=proof['next_work'], goal_complete=False)
    write(STATE, state)
    print(dict(status=proof['status'], report=str(REPORT), proof=str(PROOF),
        current_prepared_candidate=state['current_prepared_candidate'],
        last_measured_candidate=terminal['candidate'], ipc=terminal['ipc'],
        fmax_mhz=terminal['fmax_mhz'], area_um2=terminal['area_um2'],
        tests_started_this_turn=False, goal_complete=False))


if __name__ == '__main__':
    main()
