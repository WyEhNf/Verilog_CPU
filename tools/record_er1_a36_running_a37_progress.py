"""Record live immutable measurement plus independent source progress."""
from datetime import datetime, timezone
from pathlib import Path

from manage_er1_a16r2_measurement import check as check16
from manage_er1_a21_measurement import check as check21
from manage_er1_a36_measurement import check as check36
from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from wait_frequency_directed_native import live

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN=Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')
SOURCE=BASE/'A37_mdu_local_payload_owners'
REPORT=ROOT/'reports/ER1_A36_running_A37_source_progress_2026-10-05.md'
OUT=ROOT/'build/cpu2026/er1_a36_running_a37_source_progress_20261005.json'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
EVIDENCE=Path('F:/CPU2026Proofs/ER1_A21_critical_mdu_endpoint_20261005.json')


def main():
    assert not REPORT.exists() and not OUT.exists()
    check16();check21();plan=check36()
    dispatch=read(RUN/'dispatch_identity.json')
    pid=dispatch['process_id']
    assert live(pid), 'Record live measurement only when exact dispatched handle exists.'
    result=optional(RUN/'result/result.json')
    failure=optional(RUN/'result/failure.json')
    assert result is None and failure is None
    assert sha(RUN/'source_manifest.json')==dispatch['source_manifest_sha256']
    candidate=read(SOURCE/'candidate.json')
    assert not candidate['tests_started'] and not candidate['adopted']
    for name,digest in candidate['source_sha256'].items():assert sha(SOURCE/name)==digest,name
    assert sha(Path(candidate['parent_candidate'])/'candidate.json')==candidate['parent_candidate_sha256']
    source_review=BASE/'A37_source_review.json'
    assert read(source_review)['candidate_sha256']==sha(SOURCE/'candidate.json')
    active=read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name,digest in active['source_sha256'].items():assert sha(ROOT/name)==digest,name
    evidence=read(EVIDENCE)
    assert evidence['endpoint_source_module']=='rv32m_mdu_iterative'
    trace=evidence['timing_nodes']
    tail_delays={}
    for name in ['_338495_','_371714_','_372056_']:
        nodes=[n for n in trace if n['instance']==name]
        assert len(nodes)==2
        tail_delays[name]=(nodes[1]['arrival']-nodes[0]['arrival'])*1e9
    tail_sum=sum(tail_delays.values())
    assert abs(tail_sum-1.766)<1e-6
    stage=RUN/'result/synth/opt/elaborated.json'
    assert stage.exists() and stage.stat().st_size>0
    log=(RUN/'driver_stdout.log').read_text(encoding='utf-8',errors='replace').splitlines()
    assert 'START course native synth' in log and 'START course native perf' in log
    REPORT.write_text(f'''# ER1 A36运行中与A37独立源码进度

目标仍是同一源码IPC几何平均≥1.1、Fmax>300MHz、含SRAM总面积≤36,000μm²，以及完整RV32IM/OoO执行/顺序退休/课程MMIO退出。目标未完成。

上一轮仅核对实测指标，未改权威源码，归类为无进展；本轮已重新确认A16R2/A21原测量终止，没有重启。A29–A33已有源码与本轮新增A34命名修复、A35就绪store分配数据、A36 D-cache word response已整合冻结，测试前已在对话汇报并落盘完整A36 pretest报告。

A36一次Windows原生课程测量现处运行中：原派发PID={pid}，本记录生成时核对该PID仍存活，尚无result/failure。源码展开产物elaborated.json已生成（{stage.stat().st_size:,}字节），日志已明确启动综合与native perf。没有把展开通过当成CPU功能、综合或时序通过，没有重启或覆写任何测试。A36 IPC/面积/频率尚无最终结果。

A36快照157项源码/依赖文件，其中116项课程依赖字节与A16R2相同；snapshot SHA256={plan['source_manifest_sha256']}。测试前报告SHA256={plan['pretest_report_sha256']}。主EU源码哈希仍不变。详细结构收益和验证范围见[ER1_A36_pretest_2026-10-05.md](ER1_A36_pretest_2026-10-05.md)。A36中间候选未逐个测试，本次不立即重跑19correctness或M单元。

本轮新增的旧网表证据：A21 mapped.v与design.json顶层全部235,684个私有cell的顺序类型对应，并核对关键后段5条端口连接在两种格式中一致。端点_430425_/D的DFF源码属性属于rv32m_mdu_iterative.v的原时钟状态过程；起点属于AXI reader过程。尚未定位MDU中的具体字段，不能冒称PRF/RS状态。最慢后段_338495_、_371714_、_372056_的门延迟分别为{tail_delays['_338495_']:.3f}/{tail_delays['_371714_']:.3f}/{tail_delays['_372056_']:.3f}ns，合计{tail_sum:.3f}ns，其输出负载53.16/53.52/43.08fF。证据只来自旧结果，没有启动新EDA分析。

在A36后台运行时独立完成A37源码：MDU原先一段时钟条件更新的载荷迁入按16位分发写控制的word owners，launch再分为4个owner控制及4个初值mode分支。phase/counter时钟过程等于原过程删除载荷赋值的投影；全部算术/ready-valid/恢复条件为原文本。载荷初始化、迭代、step31 finishing capture、finishing output的边沿和优先级不变，所有载荷仍不复位。无新增寄存位、流水边界或M运算拍数。MDU取消/完整tag/物理目的/输出背压仍保留。新增的分发反相器和event mux可能增加映射逻辑，实际面积/频率仍未知。

A37尚未启动任何HDL/EDA/CPU/单元测试，未采用；A36快照/manifest/manager/report未编辑。当前最新独立源码：{SOURCE}，candidate SHA256={sha(SOURCE/'candidate.json')}。不把A37结构估算同A16/A21指标混用。

下一步继续观察原A36派发句柄与实际产物，并分析新结果对应的IPC瓶颈、critical path与面积所有者。若A36显示相称收益且值得采用，再对同一冻结源码完成19项课程正确性及全部M、恢复、缓存/FQ背压/错误/region和BTB别名、自然对齐word response、partial-forward/store分配依赖等相关验证。A37仅在明确净收益依据及测试前报告后测量；不得每次源码改动重复完整测试。
''',encoding='utf-8')
    proof=dict(status='PROGRESS_A36_LIVE_IMMUTABLE_MEASUREMENT_AND_A37_SOURCE',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_turn_classification='NO_PROGRESS_METRICS_REPORT_REVALIDATED_TERMINAL_A16_A21',
        active_measurement_run=str(RUN),process_id=pid,exact_dispatch_process_alive=True,
        measurement_snapshot_sha256=plan['source_manifest_sha256'],pretest_report_sha256=plan['pretest_report_sha256'],
        result=None,failure=None,elaborated_json_size=stage.stat().st_size,
        elaborated_json_sha256=sha(stage),native_synth_started=True,native_perf_started=True,
        pending_source=str(SOURCE),candidate_sha256=sha(SOURCE/'candidate.json'),
        source_review_sha256=sha(source_review),critical_mdu_endpoint_evidence_sha256=sha(EVIDENCE),
        old_late_control_gate_delays_ns=tail_delays,old_late_control_delay_sum_ns=tail_sum,
        a37_tests_started=False,a37_extra_ff_bits=0,a37_extra_pipeline_edges=0,
        main_eu_source_changed=False,goal_complete=False,candidates_adopted=False,
        report=str(REPORT),report_sha256=sha(REPORT))
    write(OUT,proof)
    goal=read(GOAL)
    goal.update(status=proof['status'],current_prepared_candidate=SOURCE.name,
        pending_source_candidate=str(SOURCE),pending_source_candidate_sha256=sha(SOURCE/'candidate.json'),
        pending_source_candidate_tests_started=False,active_measurement_candidate=Path(plan['candidate']).name,
        measurement_run=str(RUN),measurement_process_id=pid,measurement_process_alive=True,
        active_measurement_process_ids=[pid],active_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        last_goal_turn_classification=proof['status'],previous_goal_turn_classification=proof['previous_turn_classification'],
        last_background_progress=str(REPORT),last_background_progress_sha256=sha(REPORT),
        goal_complete=False,candidates_adopted=False,
        next_work=['Observe exact original A36 process and stage artifacts without restarting or editing snapshot.',
                   'Continue independent source/netlist work; A37 bounded MDU payload writes are untested.',
                   'Read same-source A36 IPC/area/Fmax when terminal; use measured bottlenecks for next coherent batch.',
                   'Require strict same-source metrics and full relevant correctness/M/recovery/cache/forwarding coverage before adoption.'])
    write(GOAL,goal)
    print({k:proof[k] for k in ('status','process_id','exact_dispatch_process_alive','a37_tests_started','old_late_control_delay_sum_ns','goal_complete')})


if __name__=='__main__':main()
