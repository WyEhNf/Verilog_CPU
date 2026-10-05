"""Persist source progress A45-A48; retain A41 as the last measured result."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write
from manage_er1_a41_measurement import check as check_a41
from wait_frequency_directed_native import live

ROOT = Path('E:/Verilog_cpu')
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
REPORT = ROOT / 'reports/ER1_A45_A48_source_progress_2026-10-05.md'
PROOF = ROOT / 'build/cpu2026/er1_a45_a48_source_progress_20261005.json'
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not REPORT.exists() and not PROOF.exists()
    plan = check_a41()
    state = read(STATE)
    measured = read(RUN / 'result/result.json')
    ipc = read(RUN / 'result/ipc.json')
    ppa = read(RUN / 'result/synth/opt/report.json')
    assert measured['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert measured['official_perf_expected_results_passed']
    assert measured['official_correctness_suite_not_run']
    assert measured['ipc'] == ipc['geomean_ipc'] == state['last_measured_result']['ipc']
    assert measured['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz'] == state['last_measured_result']['fmax_mhz']
    assert measured['area_um2'] == ppa['area']['area_um2'] == state['last_measured_result']['area_um2']
    assert not measured['thread_objective_numeric_requirements_met']
    assert not live(51000)
    assert len(ipc['results']) == 6
    for row in ipc['results']:
        folder = RUN / 'source/.deps/RISC-V-CPU-2026/testcases' / row['name']
        assert row['ipc'] == row['instructions'] / row['cycles']
        assert sha(folder / 'program.data') == row['program_sha256']
        assert sha(folder / 'metrics.json') == row['metrics_sha256']
    previous_report = Path(state['last_background_progress'])
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_report) == state['last_background_progress_sha256']
    assert sha(previous_proof) == state['last_source_progress_proof_sha256']
    candidates = []
    for name, expected_sha in (
        ('A45_hybrid_direction_predictor', '8050116cef15b6fc69155461a511adcde455e0cc9ba077356b21d372a6fe919c'),
        ('A46_lsq_empty_selection_bypass', '35e272bcba0109dd8334f0873e786b2d2257436651c1fc4357ef35c90c8bd0db'),
        ('A47_recovery_apply_older_issue', '2eb6b10305971e605be0b25a726e47c6b912c479967d98d302c93d6bcfa7187d'),
        ('A48_lsq_registered_address_bypass', 'c3dec0d955c9d6a2e72a0bc3ec1c71d61cc110eb5f1427472059c3da390e90b0')):
        p = BASE / name
        c = read(p / 'candidate.json')
        review_path = BASE / (name.split('_', 1)[0] + '_source_review.json')
        review = read(review_path)
        assert sha(p / 'candidate.json') == expected_sha == review['candidate_sha256']
        assert not c['tests_started'] and not c['adopted']
        assert not review['tests_started'] and not review['adopted']
        parent = Path(c['parent_candidate'])
        parent_record = read(parent / 'candidate.json')
        assert sha(parent / 'candidate.json') == c['parent_candidate_sha256']
        for rel, digest in c['source_sha256'].items():
            assert sha(p / rel) == digest, (name, rel)
        for rel, digest in parent_record['source_sha256'].items():
            assert sha(parent / rel) == digest, (str(parent), rel)
        changed = [rel for rel, digest in c['source_sha256'].items()
                   if digest != parent_record['source_sha256'][rel]]
        assert set(changed) == set(c['changed_from_parent_files']) == set(review['changed_files'])
        assert len(c['source_sha256']) == 41
        candidates.append(dict(candidate=name, source_root=str(p), candidate_sha256=expected_sha,
            parent=str(parent), parent_candidate_sha256=c['parent_candidate_sha256'],
            source_files_checked=41, changed_files=changed, source_review=str(review_path),
            source_review_sha256=sha(review_path), preparation_script_sha256=c['preparation_script_sha256'],
            tests_started=False, adopted=False, ipc=None, fmax_mhz=None, area_um2=None))
    active_path = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    active = read(active_path)
    for rel, digest in active['source_sha256'].items():
        assert sha(ROOT / rel) == digest, rel
    final = BASE / candidates[-1]['candidate']
    lsq = (final / 'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    backend = (final / 'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    top = (final / 'rtl/course/student_top.v').read_text(encoding='utf-8')
    assert 'REQUEST_PIPELINE!=0 && EMPTY_SELECTION_BYPASS!=2' in lsq
    assert 'parameter integer LSQ_EMPTY_SELECTION_BYPASS = 2,' in top
    assert 'parameter integer RECOVERY_APPLY_OLDER_ISSUE = 1,' in top
    assert 'RECOVERY_ISSUE_RELEASE(RECOVERY_APPLY_ISSUE_ACTIVE)' in backend
    gap = (1.1 / measured['ipc'] - 1) * 100
    report = f'''# ER1 A45–A48 源码优化进度（未测试）

目标保持为 IPC≥1.1、包含 SRAM 的总面积≤36000 μm²、频率>300 MHz，保留完整 RV32IM、乱序执行、顺序提交、MMIO 与参数化要求。

## 已测量结果仍为 A41

Windows 原生课程标准工具链；6 项 perf IPC 几何平均；课程 ASAP7/FakeRAM 综合与 STA 口径。

|指标|A41 已测值|目标|
|---|---:|---:|
|IPC|{measured['ipc']:.10f}|≥1.1|
|总面积|{measured['area_um2']:.5f} μm²|≤36000 μm²|
|其中 SRAM|{measured['area']['sram_area_um2']:.5f} μm²|已计入总面积|
|估算 Fmax|{measured['fmax_mhz']:.5f} MHz|>300 MHz|

6 项性能用例答案均通过；完整正确性回归未运行。IPC 尚需相对提升 {gap:.3f}%。A41 的结果不能当作后续候选的结果；本轮没有新测试或新测量。原测量 PID51000 已不存在，没有重启该任务。主 E: 工作区的 EU RTL 哈希保持不变。

## 累积源码方案

|候选|具体改动|已有依据与限制|
|---|---|---|
|A45 混合方向预测|并行查询 bimodal、gshare 和 PC 选择器；用预测时保存的两种方向训练选择器，保持准确的 gshare 索引与恢复检查点。BTB32→16 为新增表腾出状态预算。|A41 对 median 改善而 qsort 退步，证明程序表现不同，但联合批次不能归因于 gshare。混合机制有文献依据；实际误预测率和 IPC 增益未知。|
|A46 空加载选择槽直通|已有完整地址、身份及顺序条件的加载，在 LSQ 选择寄存器为空时当周期送缓存；阻塞时保存原请求和转发快照。|删除一个必要选择等待边界；原 AGU 地址透传同时连接了新的长组合路径，频率风险尚未测量。|
|A47 恢复应用周期继续执行更老指令|检查当前 ROB 有效性、完整代际与恢复年龄范围；RS 的有效位、占用计数、释放事件和负载所有者共同删除已被执行单元接受的保留行；允许替换已取消的 ALU 结果和 MDU 发射槽。|删除恢复应用周期的全局发射暂停；实际有多少可执行的更老指令未知。增加两路9位 ROB 状态读与组合控制，未增加寄存器、SRAM 或流水级。|
|A48 直通只读已登记地址|课程使用 LSQ_EMPTY_SELECTION_BYPASS2，裁掉用于请求选择的当前 AGU 地址透传，年龄/危险判断/最老选择/缓存地址均从已登记地址开始。|切断 A46 新增的 AGU 数据到缓存地址路径；已有地址的排队加载保留直通机会。选择/转发到缓存的路径仍须后续测量。|

A48 累积包含 A42 的缓存非写入路查询、A43 的命中回复与后续回复并发、A44 的本地前端响应 PC，以及上述 A45–A47。A46 的模式1仍可显式选择；当前累积候选选用模式2。

## 关键所有权检查

A47 只在实际恢复应用事件、直接 RS 发射和本地选择性执行恢复模式下开放。新指令必须严格早于恢复分支并位于恢复时 ROB 占用范围，当前代际必须相等。被取消的旧结果先失去输出有效性，然后新接受的完整结果写入原有数据/元数据/预测所有者。保留的旧结果继续遵守原有背压；已取消的移位状态不再更新旧数据；MDU 内部乘除执行器保持原源代码。恢复期间仍不分配新 RS 行，新的释放不会依赖单纯的 offer 或 ready。

A48 的源码时间线：新 AGU 地址在边沿写入 LSQ，随后周期经空槽直通发出；A41 在该边沿把实时 AGU 地址写入选择槽，随后周期发出。对于选择槽空、缓存 ready、当前加载获选的条件，两者请求边沿相同。这是条件化的源码分析，不是新的测量；占用槽、分配快路、仲裁与缓存背压可改变调度。已有地址的等待加载可节省选择边界。

A45 使用原16位元数据的低8位保存 gshare 索引，中6位保存历史检查点，高2位保存原始方向；宽度不扩展。新增896表状态位、BTB减少640位、此前常量元数据可能新增104位有效状态，净增约360位是准备阶段估计，仅对应约104.98 μm²触发器部分，不能代表综合总面积。控制、读选择、缓冲与常量裁剪仍未知。

上述源文件和父候选41个源文件快照均已核对哈希；查看并审核差异、写候选快照属于源码准备。没有调用 HDL/lint/仿真/综合/STA/单元测试，因此不宣称功能等价、IPC 已提高或 Fmax 已达标。

## 下一步

继续检查混合预测器的并行读出、方向选择与下一 PC 形成能否减少组合层次；检查新恢复年龄/代际读是否能在不增加时钟边界的情况下分担选择负担。整理完整批次的收益依据和未知项，测试前另行汇报，仍仅使用当前 Windows 原生课程工具链。

未来覆盖重点为恢复预览/应用的恰好一次发射、双 ALU 与共享 MDU、取消/保留结果和持续背压、ROB 环绕/代际复用/嵌套恢复，以及加载地址进入所有者、空槽/占用槽/背压、未知与重叠存储和逐字节转发。混合预测须覆盖选择器饱和、预测到反馈期间训练变化、同/不同银行双反馈、检查点修复和参数回退。完整 RV32IM/正确性要求仍待完成，目标保持未完成。

混合方向预测机制参考：[Scott McFarling, Combining Branch Predictors, WRL TN-36 (1993)](https://ftp.zx.net.nz/pub/archive/ftp.digital.com/pub/compaq/WRL/research-reports/WRL-TN-36.pdf)。文献支持机制，不证明本 CPU 的收益。

结果来源：[A41 result.json](F:/CPU2026CourseRuns/ER1_A41_tier3_20261005/result/result.json)。当前源码：[A48 candidate.json](F:/CPU2026Candidates/tier3_er1_20261005/A48_lsq_registered_address_bypass/candidate.json)。各候选详情与哈希见独立 A45/A46/A47/A48_source_review.json。
'''
    REPORT.write_text(report, encoding='utf-8')
    proof = dict(status='PROGRESS_A45_A48_SOURCE_UNTESTED', recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='NO_PROGRESS_STATUS_REPORT_ONLY_A41_RECONFIRMED',
        this_goal_turn_classification='PROGRESS_NEW_A47_A48_SOURCE_A45_A46_HASH_REVIEW_AND_STATE_RECONCILIATION',
        no_progress_revalidated_next_safe_action='Implemented A47 then A48, not a repeated status restatement.',
        objective=dict(ipc_minimum=1.1, total_area_um2_maximum=36000, fmax_mhz_strictly_greater_than=300),
        last_measured_result=state['last_measured_result'], best_verified_result=state['best_verified_result'],
        measured_result_sha256=sha(RUN / 'result/result.json'),
        measured_ipc_sha256=sha(RUN / 'result/ipc.json'), measured_ppa_sha256=sha(RUN / 'result/synth/opt/report.json'),
        frozen_host_scripts_sha256=plan['host_sha256'], candidates=candidates,
        report=str(REPORT), report_sha256=sha(REPORT), previous_report=str(previous_report),
        previous_report_sha256=sha(previous_report), previous_proof=str(previous_proof), previous_proof_sha256=sha(previous_proof),
        tests_started_this_goal_turn=False, new_measurement_started=False, wsl_used=False,
        original_a41_pid_present=False, main_worktree_rtl_unchanged=True,
        main_worktree_candidate=active['candidate'], main_worktree_active_record_sha256=sha(active_path),
        candidate_metrics_measured=False, goal_complete=False,
        next_work=[
            'Develop frequency factoring for hybrid direction lookup and frontend next-PC without extra fetch edges.',
            'Audit registered-address direct LSQ control and recovery generation/age routing costs before a coherent batch measurement.',
            'Report the completed high-gain batch before any native measurement; preserve full objective and complete meaningful correctness coverage before adoption.'])
    write(PROOF, proof)
    pending = candidates[-1]
    state.update(status='A41_COMPLETE_A48_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=pending['candidate'], current_source_candidate=pending['candidate'],
        candidate_manifest_sha256=pending['candidate_sha256'], candidate_tests_started=False,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        candidate_metrics_belong_to=pending['candidate'], candidate_correctness_passed=None,
        candidate_correctness_failed=None, candidate_correctness_finished=False, candidate_correctness_not_run=True,
        pending_source_candidate=pending['source_root'], pending_source_candidate_sha256=pending['candidate_sha256'],
        pending_source_candidate_tests_started=False, prepared_run=None, prepared_source_manifest_sha256=None,
        candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        active_measurement_candidate=None, active_measurement_process_ids=[], measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,
        last_background_progress=str(REPORT), last_background_progress_sha256=sha(REPORT),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_goal_turn_classification=proof['this_goal_turn_classification'],
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        candidates_adopted=False, goal_complete=False, next_work=proof['next_work'])
    write(STATE, state)
    print(dict(status=proof['status'], pending_candidate=pending['candidate'],
        report=str(REPORT), proof=str(PROOF), new_measurement_started=False, goal_complete=False))


if __name__ == '__main__':
    main()
