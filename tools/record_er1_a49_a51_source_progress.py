"""Record frontend/predictor frequency source work without starting measurement."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write
from manage_er1_a41_measurement import check as check_a41
from wait_frequency_directed_native import live

ROOT = Path('E:/Verilog_cpu')
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
REPORT = ROOT / 'reports/ER1_A49_A51_frequency_source_progress_2026-10-05.md'
PROOF = ROOT / 'build/cpu2026/er1_a49_a51_source_progress_20261005.json'
CRITICAL = Path('F:/CPU2026Proofs/ER1_A41_critical_frontend_owner_20261005.json')


def main():
    assert not REPORT.exists() and not PROOF.exists()
    plan = check_a41()
    state = read(STATE)
    previous_report = Path(state['last_background_progress'])
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_report) == state['last_background_progress_sha256']
    assert sha(previous_proof) == state['last_source_progress_proof_sha256']
    assert state['current_source_candidate'] == 'A48_lsq_registered_address_bypass'
    assert state['last_goal_turn_classification'] == 'PROGRESS_NEW_A47_A48_SOURCE_A45_A46_HASH_REVIEW_AND_STATE_RECONCILIATION'
    measured = read(RUN / 'result/result.json')
    ipc = read(RUN / 'result/ipc.json')
    ppa = read(RUN / 'result/synth/opt/report.json')
    assert measured['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert measured['official_perf_expected_results_passed'] and measured['official_correctness_suite_not_run']
    assert not measured['thread_objective_numeric_requirements_met']
    assert measured['ipc'] == ipc['geomean_ipc'] == state['last_measured_result']['ipc']
    assert measured['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz'] == state['last_measured_result']['fmax_mhz']
    assert measured['area_um2'] == ppa['area']['area_um2'] == state['last_measured_result']['area_um2']
    assert not live(51000)
    assert len(ipc['results']) == 6
    for row in ipc['results']:
        folder = RUN / 'source/.deps/RISC-V-CPU-2026/testcases' / row['name']
        assert sha(folder / 'program.data') == row['program_sha256']
        assert sha(folder / 'metrics.json') == row['metrics_sha256']
    candidates = []
    for name, digest, preparer in (
        ('A49_frontend_parallel_bundle_control', '6520c064a14fe19ee6210420518e13600841a502087f1df15e5dd934b2e62237', 'prepare_er1_frontend_parallel_bundle_control.py'),
        ('A50_predictor_direction_independent_target', 'fb3cd52f7a9f24c0c9bd746efb68b7625db0c9ff790ffd83ba9592e11d283e94', 'prepare_er1_predictor_direction_independent_target.py'),
        ('A51_predictor_narrow_direction_read', '41a2f090d9f02e78f85b85752f5712ecf606fee1bb158b60cf4a6a67cb5ea387', 'prepare_er1_predictor_narrow_direction_read.py')):
        p = BASE / name
        c = read(p / 'candidate.json')
        review_path = BASE / (name.split('_', 1)[0] + '_source_review.json')
        review = read(review_path)
        assert sha(p / 'candidate.json') == digest == review['candidate_sha256']
        assert sha(ROOT / 'tools' / preparer) == c['preparation_script_sha256']
        assert not c['tests_started'] and not c['adopted']
        assert not review['tests_started'] and not review['adopted']
        assert review['added_ff_bits'] == review['added_sram_bits'] == review['added_pipeline_edges'] == 0
        parent = Path(c['parent_candidate'])
        parent_record = read(parent / 'candidate.json')
        assert sha(parent / 'candidate.json') == c['parent_candidate_sha256']
        for rel, source_digest in c['source_sha256'].items():
            assert sha(p / rel) == source_digest, (name, rel)
        for rel, source_digest in parent_record['source_sha256'].items():
            assert sha(parent / rel) == source_digest, (str(parent), rel)
        changed = [rel for rel, source_digest in c['source_sha256'].items()
                   if source_digest != parent_record['source_sha256'][rel]]
        assert set(changed) == set(c['changed_from_parent_files']) == set(review['changed_files'])
        assert len(c['source_sha256']) == 41
        candidates.append(dict(candidate=name, source_root=str(p), candidate_sha256=digest,
            parent=str(parent), parent_candidate_sha256=c['parent_candidate_sha256'],
            source_files_checked=41, changed_files=changed, source_review=str(review_path),
            source_review_sha256=sha(review_path), preparation_script_sha256=c['preparation_script_sha256'],
            added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
            tests_started=False, adopted=False, ipc=None, fmax_mhz=None, area_um2=None))
    active_path = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    active = read(active_path)
    for rel, digest in active['source_sha256'].items():
        assert sha(ROOT / rel) == digest, rel
    critical = read(CRITICAL)
    assert critical['source_manifest_sha256'] == sha(RUN / 'source_manifest.json')
    for name, key in (('mapped.v', 'mapped_verilog_sha256'), ('design.json', 'mapped_design_sha256'), ('critical_paths.json', 'critical_paths_sha256')):
        assert sha(RUN / 'result/synth/opt' / name) == critical[key]
    stack = [ppa['area']['module_tree']]
    inverter_area = None
    while stack:
        module = stack.pop()
        if module.get('source_module') == 'rv32_frequency_inversion':
            inverter_area = module['direct_area_um2']
            break
        stack.extend(module.get('children', []))
    assert inverter_area == 0.04374
    removed_literal_area = 1152 * inverter_area
    report = f'''# ER1 A49–A51 频率源码优化进度（未测试）

目标保持 IPC≥1.1、包含 SRAM 的总面积≤36000 μm²、频率>300 MHz，并保留完整 RV32IM、OoO、顺序提交、MMIO 与参数化要求。

当前累积源码候选为 A51。上一目标轮已完成 A47/A48，因此归类为实际进展；本轮新增 A49/A50/A51，完成源码差异与快照哈希检查，仍没有启动 HDL、lint、仿真、综合、STA 或单元测试。

## 已测结果没有更新

Windows 原生课程标准工具链下，最后已测候选仍是 A41：IPC **{measured['ipc']:.10f}**（6 项 perf 几何平均）、总面积 **{measured['area_um2']:.5f} μm²**（含 SRAM **{measured['area']['sram_area_um2']:.5f} μm²**）、估算频率 **{measured['fmax_mhz']:.5f} MHz**。6 项性能答案通过，完整正确性回归未运行；IPC 尚未达到目标。原 PID51000 已不存在，没有重新启动测量。新候选没有 IPC/面积/频率数值，主 E: 工作区 EU RTL 哈希未改变。

## 新增源码方案

|候选|变化|对关键路径的作用|
|---|---|---|
|A49 并行前端束控制|直接从有效前缀判断终止指令；目标/顺序 PC 使用互斥事件选择。容量由各有效指令与固定剩余容量阈值并行比较。|下一 PC 避开先编码 bundle_count 再译码的串联路径；回复容量避开 occupancy+bundle_count 加法。原入队/出队计数与全部状态所有者保持原样。|
|A50 提前形成直接目标|直接条件分支 PC+立即数目标不再等待方向表输出；预测方向只在前端最后决定是否采用目标。|删除方向表→预测器32位目标选择的一层串行控制。仅在压缩目标元数据且非串行后端的核心配置中启用。|
|A51 窄方向表直接行选择|保留每4行一组的索引分发与平衡 OR 树；2/3位表的行命中直接驱动数据掩码。|删除窄表行选择上的两级保留反相器。宽 BTB/缓存/ROB/LSQ/负载数据读取保持原实现。|

三项都不增加 FF、SRAM 或流水级。A51 的课程混合表共有256+256+64行，源码中少1152个保留反相器；A41 映射中该反相器模块面积为 {inverter_area:.5f} μm²，其字面组件合计 **{removed_literal_area:.5f} μm²**。这不是综合后实际门数或总面积节省的结论；重映射、裁剪、驱动尺寸和其他逻辑变化仍需测量。

## 源码推导及限制

A49 中，有效指令仍是行内且无响应错误的连续前缀，终止于第一条预测跳转/旧式停机哨兵、取指宽度或缓存行末尾。无错误时恰好一条有效指令结束该束；跳转与哨兵同在一条指令时沿用原来的跳转目标优先，哨兵单独出现时使用顺序 PC；响应错误沿用默认 PC+4。每个有效位置均能放入队列，等价于原有占用加束长不超过容量，且没有新增同拍出队容量抵扣。该推导依赖原有可达队列占用0..FQ_DEPTH；不宣称任意损坏状态或未测 HDL 的等价证明。

A50 中，只有“有效直接条件分支且预测不跳转”的原始目标线值发生变化：呈现候选 PC+立即数，原来呈现 PC+4。前端此时选择顺序 PC，且压缩元数据保存的条件分支/JAL/非控制目标均为0。JALR 命中/未命中目标、页检查、保存低12位与 RAS 覆盖保持相同。核心以 COMPACT_TARGET_ACTIVE 限定激活；默认参数、完整目标元数据、串行后端与直接目标模式0保持原契约。该模式显式改变预测器候选目标契约，不能声称开启模式后全部原始目标线在每种输入下相同。

A51 中，原单叶选择树的两次反相输出等于行命中，新掩码直接使用同一命中；索引分发、行相等判断、填充零行与 OR 树一致。三个调用分别宽3、3、2，行命中最多驱动3个数据掩码。所有方向表训练、饱和/冷行行为、预测时索引与元数据、并行反馈、历史修复源代码不变。新读取模块没有状态，默认参数回退到原读取模块。

A41 已有映射证据把最长路径定位于前端 PC/BHT/链式取指请求区域，数据到达为3.19ns；本批次针对该区域。该证据不能量化 A51 的 Fmax，也不能证明经过之前 A42–A48 改动后仍是同一最慢路径。新的加载选择/转发和恢复代际查询路径尚未测量。

## 后续工作

继续检查银行查询 PC 的形成：相邻字地址只有低位加法与跨行进位，是否可把晚到的偏移控制从整个 PC 加法中分离。结合现有程序数据审视剩余可实施方案的收益与面积代价，完成整个批次的依据后在测试前汇报，仍只使用当前 Windows 原生课程工具链。

后续必要覆盖包括 FE1/2/4、各行起始字、有效前缀/容量边界、跳转与哨兵/响应错误、取指背压和链式请求、元数据与 RAS/JALR 页检查、方向表同时训练/读取及参数回退；还需保留此前 A42–A48 的缓存并发、加载转发/背压、恢复恰好一次发射及完整 RV32IM 验证。源码审阅与哈希检查不能代替最终正确性及性能证据，目标仍未完成。

证据：[A41 已测结果](F:/CPU2026CourseRuns/ER1_A41_tier3_20261005/result/result.json)；[A51 当前候选](F:/CPU2026Candidates/tier3_er1_20261005/A51_predictor_narrow_direction_read/candidate.json)。独立 A49/A50/A51_source_review.json 记录各项源码依据、哈希与未知项。
'''
    REPORT.write_text(report, encoding='utf-8')
    proof = dict(status='PROGRESS_A49_A51_FREQUENCY_SOURCE_UNTESTED', recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification=state['last_goal_turn_classification'],
        this_goal_turn_classification='PROGRESS_NEW_A49_A50_A51_SOURCE_AND_NATIVE_FROZEN_EVIDENCE_REVIEW',
        objective=dict(ipc_minimum=1.1, total_area_um2_maximum=36000, fmax_mhz_strictly_greater_than=300),
        last_measured_result=state['last_measured_result'], best_verified_result=state['best_verified_result'],
        measured_result_sha256=sha(RUN / 'result/result.json'), measured_ipc_sha256=sha(RUN / 'result/ipc.json'),
        measured_ppa_sha256=sha(RUN / 'result/synth/opt/report.json'), frozen_host_scripts_sha256=plan['host_sha256'],
        critical_proof=str(CRITICAL), critical_proof_sha256=sha(CRITICAL),
        a41_inversion_module_direct_area_um2=inverter_area,
        removed_source_inverters_before_pruning=1152, removed_literal_inverter_component_um2=removed_literal_area,
        actual_area_frequency_savings_not_measured=True, candidates=candidates,
        report=str(REPORT), report_sha256=sha(REPORT), previous_report=str(previous_report),
        previous_report_sha256=sha(previous_report), previous_proof=str(previous_proof), previous_proof_sha256=sha(previous_proof),
        tests_started_this_goal_turn=False, new_measurement_started=False, wsl_used=False,
        original_a41_pid_present=False, main_worktree_rtl_unchanged=True, main_worktree_candidate=active['candidate'],
        main_worktree_active_record_sha256=sha(active_path), candidate_metrics_measured=False, goal_complete=False,
        next_work=[
            'Audit exact bank query PC bit partition / carry-select factoring without changing valid or invalid predictions.',
            'Review remaining actionable architecture options against available program evidence and area cost before the final coherent batch report.',
            'Report before any native measurement and preserve full RV32IM/OoO/in-order correctness and the strict numeric objective.'])
    write(PROOF, proof)
    pending = candidates[-1]
    state.update(status='A41_COMPLETE_A51_PENDING_SOURCE_UNTESTED',
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
    print(dict(status=proof['status'], pending_candidate=pending['candidate'], report=str(REPORT),
        proof=str(PROOF), new_measurement_started=False, goal_complete=False))


if __name__ == '__main__':
    main()
