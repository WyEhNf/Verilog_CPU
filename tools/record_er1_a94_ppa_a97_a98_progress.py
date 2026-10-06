"""Record original A94 PPA and untested A97/A98 source progress."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a94_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PROOF = ROOT/'build/cpu2026/er1_a94_ppa_a97_a98_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A94_PPA_A97_A98_new_path_2026-10-06.md'
ITEMS = [
    ('A97_rs_elastic_skip_capacity','prepare_er1_rs_elastic_skip_capacity.py','4e55dab4cf14ec71314535a1dc92db1e354939842df0a3f3d846366f35fb634f'),
    ('A98_saved_identity_word_mask','prepare_er1_saved_identity_word_mask.py','e7a05310b99a1d483af4245c18dceaaef6ea07fcbdeacb20ce372d65a4e26a21'),
]


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phase = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phase['supervisor_pid'] == state['measurement_process_id'] == 84416
    assert live(84416) and phase['status'] == 'SERIAL_PERFORMANCE_IN_PROGRESS'
    assert len(phase['phases']) == 1 and phase['phases'][0]['phase'] == 'timing' and phase['phases'][0]['returncode'] == 0
    assert state['active_measurement_candidate'] == 'A94_localparam_dependency_order'
    assert state['current_source_candidate'] == 'A96_fast_store_batch'
    timing = read(RUN/'result/timing_only.json')
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    assert sha(RUN/'result/synth/opt/report.json') == timing['official_report_sha256'] == '14b016d53126e9124fb943ebac0b9a70e7692c81889c1cc6f8db1fe71a10e942'
    ppa = read(RUN/'result/synth/opt/report.json')
    assert ppa['timing']['estimated_fmax_mhz'] == timing['fmax_mhz']
    assert ppa['area']['area_um2'] == timing['area_um2']
    assert not (RUN/'result/result.json').exists() and not (RUN/'result/ipc.json').exists()
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for path,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/path) == digest, path
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    parent = BASE/'A96_fast_store_batch'
    records = []
    for name,script,digest in ITEMS:
        root = BASE/name
        c = read(root/'candidate.json')
        assert sha(root/'candidate.json') == digest
        assert Path(c['parent_candidate']).resolve() == parent.resolve()
        assert sha(parent/'candidate.json') == c['parent_candidate_sha256']
        preparer = ROOT/'tools'/script
        assert sha(preparer) == c['preparation_script_sha256']
        for path,expected in c['source_sha256'].items():
            assert sha(root/path) == expected, (name,path)
        changed = sorted(path for path in c['source_sha256'] if (root/path).read_bytes() != (parent/path).read_bytes())
        assert changed == sorted(c['changed_from_parent_files'])
        review = Path(c['source_review'])
        assert read(review)['candidate_sha256'] == digest
        assert not c['tests_started'] and not c['adopted']
        assert c['candidate_ipc'] is c['candidate_area_um2'] is c['candidate_frequency_mhz'] is None
        records.append(dict(candidate=name,candidate_sha256=digest,source_file_count=41,changed_files=changed,
            source_hashes_valid=True,script=str(preparer),script_sha256=sha(preparer),review=str(review),review_sha256=sha(review),
            tests_started=False,metrics=None,adopted=False))
        parent = root
    paths = []
    for path in read(RUN/'result/synth/opt/critical_paths.json')['checks']:
        anchors = []
        seen = set()
        for point in path['source_path']:
            net = point.get('net','')
            if net.startswith('core.') and '/' not in net and net not in seen:
                seen.add(net)
                anchors.append(dict(net=net,arrival_ns=point['arrival']*1e9))
        paths.append(dict(startpoint=path['startpoint'],endpoint=path['endpoint'],
            data_arrival_ns=path['source_path'][-1]['arrival']*1e9,named_anchors=anchors))
    paths.sort(key=lambda x:x['data_arrival_ns'],reverse=True)
    original = read(ROOT/'build/cpu2026/er1_a83_complete_result_20261006.json')['metrics']
    metrics = dict(candidate='A94_localparam_dependency_order',status=timing['status'],
        fmax_mhz=timing['fmax_mhz'],minimum_period_ns=timing['minimum_period_ns'],area_um2=timing['area_um2'],
        sram_area_um2=ppa['area']['sram_area_um2'],sequential_area_um2=ppa['area']['sequential_area_um2'],
        combinational_area_um2=ppa['area']['combinational_area_um2'],ipc=None,ipc_pending=True,
        original_pid=84416,original_pid_alive=True,source_manifest_sha256=plan['source_manifest_sha256'],
        report_sha256=timing['official_report_sha256'],full_correctness_not_run=True,goal_complete=False)
    delta = dict(fmax_mhz=metrics['fmax_mhz']-original['fmax_mhz'],
        frequency_percent=(metrics['fmax_mhz']/original['fmax_mhz']-1)*100,
        area_um2=metrics['area_um2']-original['area_um2'],
        area_margin_um2=36000-metrics['area_um2'],
        minimum_period_reduction_required_ps=(metrics['minimum_period_ns']-1000/300)*1000)
    table = '\n'.join(f"| {index+1} | {p['startpoint']} | {p['endpoint']} | {p['data_arrival_ns']:.6f} |"
        for index,p in enumerate(paths))
    REPORT.write_text(f'''# A94 PPA与新慢路径；A97/A98源码进展

A94原PID84416的timing阶段返回0，当前同监督任务进入performance，复用原综合/STA后构建一次课程CPU。原冻结manifest/config/toolchain/PPA哈希匹配。新完整IPC报告与result尚未生成；没有运行19完整正确性，不把PPA当全部目标完成。

| 已测A94指标 | 数值 |
|---|---:|
| Fmax | {metrics['fmax_mhz']:.9f}MHz |
| 最小周期 | {metrics['minimum_period_ns']:.9f}ns |
| 总面积含SRAM | {metrics['area_um2']:.6f}μm² |
| 组合面积 | {metrics['combinational_area_um2']:.6f}μm² |
| 时序面积 | {metrics['sequential_area_um2']:.6f}μm² |
| SRAM | {metrics['sram_area_um2']:.6f}μm² |
| IPC | 尚未生成 |

对比A83：Fmax提高{delta['fmax_mhz']:.6f}MHz（{delta['frequency_percent']:.4f}%），面积增加{delta['area_um2']:.6f}μm²，时序/SRAM面积相同。面积余量{delta['area_margin_um2']:.6f}μm²。距离严格>300MHz仍需最小周期再缩短超过{delta['minimum_period_reduction_required_ps']:.6f}ps；该数值不是某一条组合延迟可直接相减的保证。

## 新路径（降序）

| 序号 | 起点 | 终点 | 数据到达ns |
|---|---|---|---:|
{table}

五条均从LSQ报告边界计算出发，主要锚点：report_bound0.2831ns→行row_end0.3213ns→report_hold_live0.6385ns/分布0.7101ns→saved report identity query1.593ns→当前ROB live1.811ns→完成源选择2.150ns→LSQ分配选择约2.994/3.004ns→GEN写控制约3.225/3.216ns→FF。原A83内存response-ID→公开LSQ票据→WB值存储地址分类链不再是报告的最慢五条；不声称所有其他路径已排除。

held-live之后的_223268_ AOI21xp33驱动61负载、30.9383fF，单单元延迟373.5ps、slew781.4ps；后级INVx1驱动16负载，延迟167.7ps。另有入队控制_242369_ NAND2xp33驱动40负载、17.079fF，延迟220.5ps。这些真实报告数据比泛泛“再拆流水”更具体；mapped信号的单一源码别名未恢复，不能将上述数值当某项改动必然节省量。

## A97：真实加载/存储省略资格之后只选容量布尔值

A96容量基准B仍先去掉load_without_AGU，所以当前WB→PRFready→加载省略会到需求计数/容量比较。A97复用原保守替换信用的全部保存D有效数V，提前计算V≤free+k，真实省略集合S=d_valid&(load_without_AGU|store_without_AGU)只选固定mask容量条件。原真实d_rs_need严格为d_valid&~S，需求V−popcount(S)。存在子集T⊆S且V≤free+|T|，等价V−popcount(S)≤free，空集用room0；所有非法/无效lane由原d_valid掩掉，不需假定load/store互斥。

原RS/LSQ需求、信用、实际admit/reset/flush/busy/LSQroom以及整个d_admit之后源码逐字不变，因此同输入下接受/分配/pop/指令周期行为相同。无新增FF/SRAM/沿/容量、无同边沿借用资源。默认0保留A96，课程1只在D流水且elastic激活。移动当前load-ready之后的容量算术是频率结构假设，仍未映射测量。

## A98：保存报告身份的16位分组授权掩码

A91把保存/held身份从28bit扩到完整85bit包；其源码仍用一个saved_grant掩码整个候选。新路径中held-live之后的大负载与此位置相符，关联是推断，未宣称一一映射。A98用原保留的control_tree将同一授权位送到ceil(width/16)个叶，逐16bit/末尾不足16bit分组计算同样的grant AND original identity。全部字段/查询布局/任意值、无候选0/held/normal优先级、valid/GEN/捕获/暂停/回收/error/格式器/状态/握手不变；默认0原掩码完整保留，新增WORDS常量位于已修复的WIDTH后。课程85bit分6叶，单叶最多16bit负载，不新增寄存器/内存/边沿。

希望分组缩短过载授权级，但定价缓冲、ABC新共享/新瓶颈可能抵消收益；面积余量仅201.027μm²，不能保证达标。A95直接保存地址分类/A96多存储准备继承，四项都尚无测量，不把A94数值借给A98。A97/A98只作源级推导和41文件冻结，未跑新增HDL/lint/形式/仿真/综合/STA/单元作业。旧A94运行/原PPA/全部成功脚本和报告保持冻结，主E EU40源码未采用。

下一步继续同一A94原监督IPC任务，同时依据新的held报告/入队控制路径考虑有证据的源码改变。新的集中批次先汇报，再一次性测量；明确改善并采用前需完整19正确性及RV32IM/M/GEN/恢复/MMIO/参数覆盖。最终严格>300MHz/IPC≥1.1/含SRAM≤36000μm²目标仍未证实。
''',encoding='utf-8')
    artifacts = [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',
        RUN/'dispatch_identity.json',RUN/'result/timing_only.json',RUN/'result/synth/opt/report.json',
        RUN/'result/synth/opt/critical_paths.json',RUN/'result/synth/opt/timing.rpt',REPORT]
    classification = 'PROGRESS_A94_ORIGINAL_PPA_290MHZ_NEW_HELD_REPORT_PATH_A97_SKIP_CAPACITY_A98_WORD_MASK_NO_NEW_TESTS'
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a94_pid_alive_at_record=True,original_a94_phase_observed=phase,original_frozen_source_check_passed=True,
        original_a94_partial_metrics=metrics,delta_vs_a83=delta,critical_paths=paths,candidates=records,
        candidate_metrics=None,additional_tests_started=False,artifacts_sha256={str(p):sha(p) for p in artifacts},
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        pending_source_candidate=str(parent),pending_source_candidate_sha256=sha(parent/'candidate.json'),
        adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=parent.name,current_prepared_candidate=parent.name,
        candidate_manifest_sha256=sha(parent/'candidate.json'),pending_source_candidate=str(parent),
        pending_source_candidate_sha256=sha(parent/'candidate.json'),pending_source_candidate_tests_started=False,
        pending_source_candidate_has_measured_metrics=False,active_measurement_partial_ppa=metrics,
        candidate_fmax_mhz=metrics['fmax_mhz'],candidate_area_um2=metrics['area_um2'],candidate_ipc=None,
        candidate_metrics_belong_to='A94_localparam_dependency_order',
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue original A94 PID84416 performance phase reusing completed same-source PPA. A94 Fmax290.2494/area35798.9727 is partial result, IPC pending. Pending A98 inherits A95/A96 and adds A97 exact all-lane skip capacity plus measured-stage16bit saved identity grant masks. No new test or source adoption; inspect new held-report/admission path, then pre-report a coherent batch, full correctness/architecture coverage before adoption.')
    write(STATE,state)
    print(dict(status=classification,a94_original_pid_alive=True,a94_partial_metrics=metrics,pending=parent.name,
        proof=str(PROOF),proof_sha256=sha(PROOF),additional_tests_started=False,goal_complete=False))


if __name__ == '__main__':
    main()
