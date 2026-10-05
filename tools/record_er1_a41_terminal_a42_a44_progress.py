"""Record completed A41 and source-only A42-A44 without starting a measurement."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write
from manage_er1_a41_measurement import check as check_a41
from wait_frequency_directed_native import live

ROOT=Path('E:/Verilog_cpu')
BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN=Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
OLD=Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')
CRITICAL=Path('F:/CPU2026Proofs/ER1_A41_critical_frontend_owner_20261005.json')
REPORT=ROOT/'reports/ER1_A41_terminal_A42_A44_source_progress_2026-10-05.md'
PROOF=ROOT/'build/cpu2026/er1_a41_terminal_a42_a44_source_progress_20261005.json'
STATE=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not REPORT.exists() and not PROOF.exists()
    plan=check_a41()
    dispatch=read(RUN/'dispatch_identity.json')
    assert dispatch['process_id']==51000 and not live(dispatch['process_id'])
    measured=read(RUN/'result/result.json')
    ipc=read(RUN/'result/ipc.json')
    ppa=read(RUN/'result/synth/opt/report.json')
    manifest=read(RUN/'source_manifest.json')
    assert measured['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert measured['official_perf_expected_results_passed']
    assert measured['official_correctness_suite_not_run']
    assert not measured['thread_objective_numeric_requirements_met']
    assert measured['ipc']==ipc['geomean_ipc']
    assert measured['area_um2']==ppa['area']['area_um2']
    assert measured['fmax_mhz']==ppa['timing']['estimated_fmax_mhz']
    assert len(ipc['results'])==6
    assert sha(RUN/'source_manifest.json')=='74bf209fd0a9b8288d429acd569401d2d56830b61901d29464e15395fcc228ea'
    for row in ipc['results']:
        assert row['ipc']==row['instructions']/row['cycles']
        folder=RUN/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
        assert sha(folder/'program.data')==row['program_sha256']
        assert sha(folder/'metrics.json')==row['metrics_sha256']
    previous=read(OLD/'result/result.json')
    old_rows={row['name']:row for row in read(OLD/'result/ipc.json')['results']}
    rows=[]
    for row in ipc['results']:
        older=old_rows[row['name']]
        assert row['instructions']==older['instructions']
        assert row['program_sha256']==older['program_sha256']
        assert row['metrics_sha256']==older['metrics_sha256']
        rows.append(dict(row,a36_cycles=older['cycles'],a36_ipc=older['ipc'],
            cycles_change_percent=100*(row['cycles']/older['cycles']-1)))
    critical=read(CRITICAL)
    assert critical['source_manifest_sha256']==sha(RUN/'source_manifest.json')
    for rel,key in (('mapped.v','mapped_verilog_sha256'),('design.json','mapped_design_sha256'),
                    ('critical_paths.json','critical_paths_sha256')):
        assert sha(RUN/'result/synth/opt'/rel)==critical[key]
    assert not critical['new_sta'] and not critical['new_cpu_tests']
    candidates=[]
    for name,review in (
        ('A42_dcache_way_parallel_query','A42_source_review.json'),
        ('A43_dcache_hit_response_coissue','A43_source_review.json'),
        ('A44_frontend_local_response_pc','A44_source_review.json')):
        p=BASE/name; c=read(p/'candidate.json'); d=read(BASE/review)
        assert not c['tests_started'] and not c['adopted']
        assert d['candidate_sha256']==sha(p/'candidate.json')
        for rel,digest in c['source_sha256'].items():
            assert sha(p/rel)==digest,rel
        assert sha(Path(c['parent_candidate'])/'candidate.json')==c['parent_candidate_sha256']
        candidates.append(dict(candidate=name,source_root=str(p),candidate_sha256=sha(p/'candidate.json'),
            source_files=len(c['source_sha256']),source_review=str(BASE/review),source_review_sha256=sha(BASE/review),
            changed_files=c['changed_from_parent_files'],added_ff_bits=d['added_ff_bits'],
            added_sram_bits=d['added_sram_bits'],added_pipeline_edges=d['added_pipeline_edges'],
            tests_started=False,adopted=False,ipc=None,fmax_mhz=None,area_um2=None))
    active=read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for rel,digest in active['source_sha256'].items():
        assert sha(ROOT/rel)==digest,rel
    terminal=dict(status=measured['status'],candidate='A41_lsq_two_prefix_reclaim',run=str(RUN),
        process_id=51000,process_alive=False,
        terminal_artifact_authority='result/result.json and original PID confirmed absent',
        ipc=measured['ipc'],fmax_mhz=measured['fmax_mhz'],minimum_period_ns=measured['minimum_period_ns'],
        area_um2=measured['area_um2'],sram_area_um2=measured['area']['sram_area_um2'],
        sequential_area_um2=measured['area']['sequential_area_um2'],
        combinational_area_um2=measured['area']['combinational_area_um2'],
        official_perf_expected_results_passed=True,full_correctness_not_run=True,full_correctness_passed=False,
        objective_numeric_met=False,source_manifest_sha256=sha(RUN/'source_manifest.json'),
        candidate_sha256=manifest['candidate_manifest_sha256'],result_sha256=sha(RUN/'result/result.json'),
        ipc_sha256=sha(RUN/'result/ipc.json'),ppa_sha256=sha(RUN/'result/synth/opt/report.json'),rows=ipc['results'])
    comparison=dict(ipc_change_percent=100*(measured['ipc']/previous['ipc']-1),
        frequency_change_percent=100*(measured['fmax_mhz']/previous['fmax_mhz']-1),
        area_change_percent=100*(measured['area_um2']/previous['area_um2']-1),
        area_margin_um2=36000-measured['area_um2'],frequency_margin_mhz=measured['fmax_mhz']-300,
        required_ipc_gain_percent=100*(1.1/measured['ipc']-1))
    table='\n'.join(f"| {row['name']} | {row['a36_cycles']} | {row['cycles']} | {row['cycles_change_percent']:+.3f}% | {row['ipc']:.6f} |" for row in rows)
    report=f'''# ER1：A41 实测完成，A42–A44 源码进展

记录时间：{datetime.now(timezone.utc).isoformat()}。原 A41 进程 PID 51000 已确认不存在，结果状态为 COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE；没有重新启动任何旧测量。

| 方案 | 综合 IPC | 总面积，含 SRAM（μm²） | 频率（MHz） |
|---|---:|---:|---:|
| A36 | {previous['ipc']:.9f} | {previous['area_um2']:.6f} | {previous['fmax_mhz']:.6f} |
| A41 | {measured['ipc']:.9f} | {measured['area_um2']:.6f} | {measured['fmax_mhz']:.6f} |
| 目标 | ≥1.1 | ≤36000 | >300 |

A41 的面积、频率已满足数值目标；IPC 尚未达标，还需相对提高 {comparison['required_ipc_gain_percent']:.3f}%。相对 A36，IPC {comparison['ipc_change_percent']:+.3f}%，频率 {comparison['frequency_change_percent']:+.3f}%，面积 {comparison['area_change_percent']:+.3f}%。面积余量 {comparison['area_margin_um2']:.6f} μm²，频率余量 {comparison['frequency_margin_mhz']:.6f} MHz。

测量采用原 Windows 原生课程工具链、固定课程框架 54fc150ffc290f52aa024209ffb9a29d43856f6d、原程序及 dynamic_instructions 分子、latency=10、六项 IPC 几何平均。157 个源快照文件及冻结的主机脚本、工具、库哈希再次核对。SRAM {measured['area']['sram_area_um2']:.6f} μm²，时序单元 {measured['area']['sequential_area_um2']:.6f} μm²，组合逻辑 {measured['area']['combinational_area_um2']:.6f} μm²。

六个性能程序的官方答案校验通过；19 项完整正确性套件、完整 M 扩展和针对新旁路/恢复/缓存行为的覆盖尚未执行。未采用 A41，也未将目标标记完成。

| 程序 | A36 周期 | A41 周期 | 周期变化 | A41 IPC |
|---|---:|---:|---:|---:|
{table}

median 明显改善，但 qsort 退步。A37–A41 是一批联合变化，因此不能把某程序的周期变化单独归因于 gshare、LSQ 回收或恢复发射中的某一项；尚无 A41 分项事件画像。后续需要根据真实分支/访存停顿归因选择更大收益的架构变化。

## 本轮源码工作，没有新测试

- A42：将数据 SRAM 的读有效和数据来源按 way 记录。前一 store 写一个 way 时，下一 load 可以查询 tag，并读取其他 way；所选 way 未读到数据则延后读取，命中旁路也必须检查该 way 数据有效。两路配置仅增加 2 个状态位，SRAM 宏、容量、端口不变。此前已准备，本轮继续复核。
- A43：当拍命中旁路交给 LSQ，同时让 waiter 或返回的 miss 响应进入原有响应寄存器。valid 不依赖 ready；背压时命中保留在寄存器中、其他 load 响应仍由原生产者持有。失败的 dirty-victim writeback 也参与 waiter 仲裁，避免 waiter 被消费后其数据被更高优先级失败响应覆盖。没有增加状态、响应端口或流水边界。
- A44：预测查询、RAS 和取指包 PC 使用现有前端待处理请求 PC，避免先等待 Icache 响应 PC 选择。响应接受增加 pending、完整 PC 相等检查，并保留原 epoch/line 身份检查。只在同步非阻塞缓存且 OoO 配置启用；其他配置保留原来源。没有增加 PC 寄存器或流水边界。

三者都保存为独立冻结候选，A42/A43/A44 的 IPC、面积、频率未知。源码检查及哈希不能证明 HDL 等价或正确性。主 E:/Verilog_cpu 活动 EU 源码保持原哈希。

## 当前关键路径及下一步

从已存在的 A41 mapped.v、design.json 和 critical_paths.json 读取，最慢路径到达时间 3.190 ns，路径经过 Icache line-filter 响应选择、frontend.bundle_pc、gshare bank_training_index、BHT 查询以及 chained if_req_pc。私有顶层单元 209126 个，对照映射文本/JSON 的排序类型全部一致，选定相邻路径连线在两份产物中核对；没有重新综合或 STA。起终点 FF 的精确业务字段未识别，不据此作更强结论。

A44 旨在去掉这段路径中的晚到 PC 选择，并为后续 IPC 改动留出频率余量；新路径和总面积需要今后测量，不能声称已有频率收益。A42/A43 消除的是已定位的请求/响应串行条件，实际碰撞次数尚未知。

下一步继续检查 load 的 allocation→selection→cache query 边界，以及在现有面积余量内加入 bimodal/gshare 自适应选择的可行性。方向预测候选应保留预测时 gshare 行索引、低 6 位历史 checkpoint 和两种原始方向；现有 16 位元数据在 history≤6 时有 2 个高位可用，可评估双表、按 PC 选择器和缩小 indirect-only BTB 的面积交换。必须先复核恢复历史掩码、完整反馈 lane 身份、频率路径和面积预算，不能把联合批次的 qsort 退步当成单项因果证据。

另外，代码本身已有四项 speculative RAS；不重复添加已有结构。RISC-V 的 x1/x5 call/return 提示规则见[官方 ISA](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)，BOOM 的 RAS 定义见[官方文档](https://docs.boom-core.org/en/latest/sections/terminology.html)。这些资料不能证明本核 IPC。qsort 静态反汇编没有大规模递归 call/return，不把扩展 RAS 作为当前首要收益来源。

本轮不启动 A42–A44 的 HDL/仿真/综合/STA/单元回归。先发展完整批次及收益依据，测试前另行汇报。目标仍为 IPC≥1.1、总面积≤36000 μm²、频率>300 MHz，并保留 RV32IM/OoO/顺序提交等完整要求。

证据：{RUN/'result/result.json'}；{RUN/'result/ipc.json'}；{RUN/'result/synth/opt/report.json'}；{CRITICAL}。A42/A43/A44 来源与哈希见对应 candidate.json、A42_source_review.json、A43_source_review.json、A44_source_review.json。
'''
    REPORT.write_text(report,encoding='utf-8')
    proof=dict(status='PROGRESS_A41_TERMINAL_A42_A44_SOURCE_UNTESTED',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='VERIFIED_WAIT_ORIGINAL_A41_PID_51000_CONFIRMED_LIVE_DURING_USER_METRICS_REPORT',
        this_goal_turn_classification='PROGRESS_NEW_A43_A44_SOURCE_A42_REVIEW_A41_TERMINAL_AND_TIMING_ATTRIBUTION',
        objective=dict(ipc_minimum=1.1,total_area_um2_maximum=36000,fmax_mhz_strictly_greater_than=300),
        last_measurement=terminal,comparison_to_a36=comparison,benchmark_comparison=rows,
        candidates=candidates,source_snapshot_files_checked=len(manifest['snapshot_sha256']),
        frozen_host_scripts_sha256=plan['host_sha256'],critical_path_proof=str(CRITICAL),
        critical_path_proof_sha256=sha(CRITICAL),current_timing_arrival_ns=3.19,
        precise_start_end_state_fields_not_identified=True,
        report=str(REPORT),report_sha256=sha(REPORT),
        source_work_tests_started_this_turn=False,original_a41_completed=True,new_measurement_started=False,
        main_worktree_source_unchanged=True,main_worktree_candidate=active['candidate'],goal_complete=False,
        next_work=['Audit allocation-to-cache load shortcut without unknown-store speculation or added state.',
            'Develop bimodal/gshare chooser using exact feedback/checkpoint protocol and explicit area/frequency trade.',
            'Report a coherent high-gain batch before future native measurement; no repeated per-edit testing.'])
    write(PROOF,proof)
    state=read(STATE)
    state['previous_measured_result']=state.get('last_measured_result')
    pending=candidates[-1]
    state.update(status='A41_COMPLETE_A44_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=pending['candidate'],candidate_manifest_sha256=pending['candidate_sha256'],
        candidate_tests_started=False,candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        candidate_metrics_belong_to=pending['candidate'],candidate_correctness_passed=None,
        candidate_correctness_failed=None,candidate_correctness_finished=False,candidate_correctness_not_run=True,
        measurement_process_alive=False,active_measurement_candidate=None,active_measurement_process_ids=[],
        active_measurement_source_manifest_sha256=None,
        last_measured_candidate=terminal['candidate'],last_measured_result=terminal,
        best_measured_combined_candidate=terminal['candidate'],
        pending_source_candidate=pending['source_root'],pending_source_candidate_sha256=pending['candidate_sha256'],
        pending_source_candidate_tests_started=False,
        last_background_progress=str(REPORT),last_background_progress_sha256=sha(REPORT),
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_goal_turn_classification=proof['this_goal_turn_classification'],
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        candidates_adopted=False,goal_complete=False,next_work=proof['next_work'])
    write(STATE,state)
    print(dict(status=proof['status'],ipc=terminal['ipc'],fmax_mhz=terminal['fmax_mhz'],area_um2=terminal['area_um2'],
        pending_candidate=pending['candidate'],report=str(REPORT),proof=str(PROOF),goal_complete=False))


if __name__=='__main__':
    main()
