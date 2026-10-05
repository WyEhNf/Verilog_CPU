"""Record terminal A16R2/A21 evidence and A22 source work; no tests."""
from datetime import datetime, timezone
import math
from pathlib import Path
import re

from manage_er1_a16r2_measurement import check as check16
from manage_er1_a21_measurement import check as check21
from manage_frozen_baseline_programs import ROOT, read, sha, write
from wait_frequency_directed_native import live

A16=Path('F:/CPU2026CourseRuns/ER1_A16R2_tier3_20261005')
A21=Path('F:/CPU2026CourseRuns/ER1_A21_tier3_20261005')
NEXT=Path('F:/CPU2026Candidates/tier3_er1_20261005/A22_load_return_wake_only')
REPORT=ROOT/'reports/ER1_A21_results_A22_source_progress_2026-10-05.md'
OUT=ROOT/'build/cpu2026/er1_a21_result_a22_source_progress_20261005.json'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def measured(run,checker):
    plan=checker()
    dispatch=read(run/'dispatch_identity.json')
    assert not live(dispatch['process_id'])
    assert not (run/'result/failure.json').exists()
    result=read(run/'result/result.json')
    assert result['status']=='COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert Path(result['source_manifest']).resolve()==(run/'source_manifest.json').resolve()
    assert sha(result['source_manifest'])==plan['source_manifest_sha256']==dispatch['source_manifest_sha256']
    ipc=read(run/'result/ipc.json')
    assert ipc['status']=='COMPLETE' and len(ipc['results'])==6 and ipc['latency']==10
    for row in ipc['results']:
        case=run/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
        assert sha(case/'program.data')==row['program_sha256']
        assert sha(case/'metrics.json')==row['metrics_sha256']
        assert read(case/'metrics.json')['dynamic_instructions']==row['instructions']
        assert row['ipc']==row['instructions']/row['cycles']
    calculated=math.exp(sum(math.log(row['instructions']/row['cycles']) for row in ipc['results'])/6)
    assert math.isclose(calculated,ipc['geomean_ipc'],rel_tol=1e-12)
    ppa=read(run/'result/synth/opt/report.json')
    assert calculated==result['ipc'] and result['fmax_mhz']==ppa['timing']['estimated_fmax_mhz']
    assert result['area_um2']==ppa['area']['area_um2']
    assert math.isclose(ppa['area']['area_um2'],ppa['area']['logic_area_um2']+ppa['area']['sram_area_um2'],rel_tol=1e-12)
    return dict(status=result['status'],candidate=Path(plan['candidate']).name,run=str(run),
        process_id=dispatch['process_id'],process_alive=False,ipc=calculated,fmax_mhz=result['fmax_mhz'],
        area_um2=result['area_um2'],sram_area_um2=ppa['area']['sram_area_um2'],
        official_perf_expected_results_passed=result['official_perf_expected_results_passed'],
        full_correctness_passed=result['official_correctness_suite_passed'],
        full_correctness_not_run=result['official_correctness_suite_not_run'],
        correctness_max_cycles=result['correctness_max_cycles'],
        objective_numeric_met=calculated>=1.1 and result['fmax_mhz']>300 and result['area_um2']<=36000,
        source_manifest_sha256=plan['source_manifest_sha256'],candidate_sha256=plan['candidate_sha256'],
        result_sha256=sha(run/'result/result.json'),ipc_sha256=sha(run/'result/ipc.json'),
        ppa_sha256=sha(run/'result/synth/opt/report.json'),rows=ipc['results'])


def main():
    assert not REPORT.exists() and not OUT.exists()
    a16=measured(A16,check16)
    a21=measured(A21,check21)
    correctness_path=A16/'result/correctness.log'
    log=correctness_path.read_text(encoding='utf-8')
    cases=[dict(name=m[1],result=m[2]) for m in re.finditer(
        r'^\[(correctness_[^\]]+)\]\s*\n(PASS[^\n]*|FAIL:[^\n]*)',log,re.M)]
    expected=sorted(p.name for p in (A16/'source/.deps/RISC-V-CPU-2026/testcases').glob('correctness_*') if p.is_dir())
    assert sorted(row['name'] for row in cases)==expected and len(cases)==19
    assert all(row['result'].startswith('PASS') for row in cases) and 'Results: 19 passed, 0 failed' in log
    assert a16['full_correctness_passed'] and a16['correctness_max_cycles']==10000000
    assert a21['full_correctness_not_run'] and not a21['full_correctness_passed']
    assert not (A21/'result/correctness.log').exists()
    next_candidate=read(NEXT/'candidate.json')
    assert not next_candidate['tests_started'] and not next_candidate['adopted']
    for name,digest in next_candidate['source_sha256'].items():
        assert sha(NEXT/name)==digest,name
    active=read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name,digest in active['source_sha256'].items():
        assert sha(ROOT/name)==digest,name
    critical_path=A21/'result/synth/opt/critical_paths.json'
    critical=read(critical_path)['checks'][0]
    path=critical['source_path']
    assert any('bus.g_response_fifos.data.output_reader' in point['instance'] for point in path)
    assert any('backend.lsq.' in point['instance'] for point in path)
    assert any('g_producer_live_read[3]' in point['instance'] for point in path)
    changes=dict(ipc_pct=100*(a21['ipc']/a16['ipc']-1),
        area_pct=100*(a21['area_um2']/a16['area_um2']-1),
        area_saved_um2=a16['area_um2']-a21['area_um2'],
        fmax_pct=100*(a21['fmax_mhz']/a16['fmax_mhz']-1))
    rows='\n'.join(f"|{new['name']}|{old['cycles']}|{new['cycles']}|{new['ipc']:.8f}|" for old,new in zip(a16['rows'],a21['rows']))
    REPORT.write_text(f'''# ER1 A21结果与A22源码进度

同一冻结版本指标如下；A21未达到频率门槛，不采用。严格目标仍为IPC≥1.1、Fmax>300MHz、总面积含SRAM≤36,000μm²。

|方案|IPC几何平均|总面积μm²（含SRAM）|Fmax MHz|课程答案|
|---|---:|---:|---:|---|
|A16R2|{a16['ipc']:.8f}|{a16['area_um2']:.6f}|{a16['fmax_mhz']:.8f}|六perf+19correctness全部通过|
|A21|{a21['ipc']:.8f}|{a21['area_um2']:.6f}|{a21['fmax_mhz']:.8f}|六perf全部通过，19correctness未启动|

A21相对A16R2：IPC提高{changes['ipc_pct']:.4f}%，面积减少{changes['area_saved_um2']:.6f}μm²（{abs(changes['area_pct']):.4f}%），频率下降{abs(changes['fmax_pct']):.4f}%。实际面积只节省约868μm²，不能声称共享MDU足够填补原3,983μm²面积差距。
A21仍比面积门槛大{a21['area_um2']-36000:.6f}μm²、IPC还需提高{100*(1.1/a21['ipc']-1):.4f}%、频率低于300MHz。不因六perf答案通过或小幅IPC增益启动其长correctness/M单元回归。
两个原驱动PID92584/75320均已核实终止；没有轮询超时重启。原所有构建/测量记录保留。

|程序|A16R2周期|A21周期|A21 IPC|
|---|---:|---:|---:|
{rows}

median退步，qsort周期减少约5.32%，其余多为小收益；组合中同时有多项改动，不能把全部IPC或面积差异唯一归因于某一项。
A16R2新完整证据为19/19正确性PASS，pi6,277,118周期、qsort1,047,097、tak1,063,137；单独使用官方支持的MAX_CYCLES=10,000,000，perf仍latency10/100万上限。全部25课程答案不是全部RV32IM指令/恢复/背压的穷尽覆盖。

A21关键路径为{critical['startpoint']}→{critical['endpoint']}，data arrival {critical['data_arrival_time']*1e9:.4f}ns。路径中可直接辨认总线data响应FIFO选择、Dcache响应、LSQ直通report以及第3完成源的ROB有效性读取；仍未将最后匿名FF伪称为特定语义字段。
三个后半段门的到达时间增量约0.254/0.636/0.876ns，负载约53.16/53.52/43.08fF，表明晚到控制的驱动/扇出还有约1.77ns成本。这里只读取已有STA，未重新综合或跑测试；下一步继续定位这些门所控制的RTL消费者。

独立 **A22_load_return_wake_only** 已完成源码，尚未测试：关闭正式LOAD_COMPLETION_BYPASS，CDB/PRF/ROB完成从原LSQ已存结果开始；新增独立的早期load返回RS唤醒列，保留省一个依赖等待边沿的机会。完整LSQ代际、未退休/请求未完成状态、有效ROBtag、本地取消与reset/flush/recovery共同限定通知，结果沿用原字节转发及符号格式。
旧LSQ完成唤醒和新返回唤醒分两列，防止新返回遮住同拍被接受的旧结果；原每行响应存储及全部metadata时钟逻辑完全不改，正式producer生成/ROB标签验证不改。新增列只有直接物理唤醒及本地恢复配置可开启。无新增状态或名义流水边沿，代价为一列RS匹配/值选择及返回metadata选择；新的实际IPC/频率/面积均未知。
这一修改没有采用到EU主树，也没有修改A21冻结源。下一轮须继续解决约13%以上IPC提升与面积缺口，汇报前不安排A22单独硬件测试。

已从A16R2既有design.json做只读寄存写控制锥归属分析：26,172个word-bank FF中26,169找到唯一最近写控制，3个未归属。这是启发式归属，不能当作完整等价/面积剔除许可；只统计已映射FF，不包括组合逻辑。聚合候选包括BTB3,712FF、主Icache tags2,816FF、L0行2,432FF；是否可压缩仍需协议与路径分析，不能盲删有效状态或忽略SRAM成本。

实测源：A16R2 {a16['source_manifest_sha256']}；A21 {a21['source_manifest_sha256']}。
A22候选manifest：{sha(NEXT/'candidate.json')}。
固定课程工具及官方依赖/程序/答案/metrics均未更改，环境始终Windows原生。目标未完成。
''',encoding='utf-8')
    proof=dict(status='A21_TERMINAL_FREQUENCY_REJECTED_A16R2_ALL25_PASS_A22_SOURCE_PREPARED',
        recorded_at=datetime.now(timezone.utc).isoformat(),a16r2=a16,a21=a21,changes=changes,
        a16r2_correctness=cases,a16r2_correctness_log_sha256=sha(correctness_path),
        a21_critical_path_sha256=sha(critical_path),a21_critical_startpoint=critical['startpoint'],
        a21_critical_endpoint=critical['endpoint'],a21_critical_data_arrival_ns=critical['data_arrival_time']*1e9,
        pending_source_candidate=str(NEXT),pending_source_candidate_sha256=sha(NEXT/'candidate.json'),
        source_review_sha256=sha(NEXT.parent/'A22_source_review.json'),pending_source_tests_started=False,
        mapped_owner_analysis_sha256=sha('F:/CPU2026Proofs/ER1_A16R2_mapped_payload_owner_state_20261005.json'),
        main_eu_source_changed=False,goal_complete=False,candidates_adopted=False,
        report=str(REPORT),report_sha256=sha(REPORT))
    write(OUT,proof)
    goal=read(GOAL)
    goal.update(status=proof['status'],last_measured_candidate=a21['candidate'],last_measured_result=a21,
        best_verified_candidate=a16['candidate'],best_verified_result=a16,
        candidate_metrics_belong_to=a21['candidate'],candidate_manifest_sha256=a21['candidate_sha256'],
        candidate_ipc=a21['ipc'],candidate_fmax_mhz=a21['fmax_mhz'],candidate_area_um2=a21['area_um2'],
        candidate_correctness_passed=None,candidate_correctness_failed=None,candidate_correctness_finished=False,
        candidate_correctness_not_run=True,current_prepared_candidate=NEXT.name,pending_source_candidate=str(NEXT),
        pending_source_candidate_sha256=proof['pending_source_candidate_sha256'],pending_source_candidate_tests_started=False,
        active_measurement_candidate=None,measurement_process_alive=False,active_measurement_process_ids=[],
        last_goal_turn_classification='PROGRESS_A20_A21_IMPLEMENTED_AND_MEASURED_FREQ_FAILURE_A16_ALL25_PASS_A22_WAKE_ONLY_SOURCE',
        last_background_progress=str(REPORT),last_background_progress_sha256=sha(REPORT),
        goal_complete=False,candidates_adopted=False,
        next_work=[
            'Review A22 wake-only metadata/physical lifetime, parallel saved/early wake, full-tag recovery and timing costs; no per-edit tests.',
            'Locate the three high-load anonymous gates after A21 ROB lifetime read from existing mapped netlist before further frequency changes.',
            'Develop a larger IPC gain from frontend/branch recovery latency and area savings from mapped large owner groups, preserving cache capacity when possible.',
            'Report before one coherent next measurement only after material gain evidence; final adoption requires same-source strict metrics and relevant correctness/M/recovery/backpressure scope.'
        ])
    write(GOAL,goal)
    print({key:proof[key] for key in ('status','changes','pending_source_tests_started','goal_complete')})


if __name__=='__main__':
    main()
