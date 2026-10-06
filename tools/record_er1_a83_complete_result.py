"""Bind the original terminal A83 result to its exact course source and CPU."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a83_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a83_complete_result_20261006.json'
REPORT = ROOT/'reports/ER1_A83_result_and_A86_direction_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phases = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phases['supervisor_pid'] == 82452 and not live(82452)
    assert phases['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [p['phase'] for p in phases['phases']] == ['timing','performance']
    assert all(p['returncode'] == 0 for p in phases['phases'])
    state = read(STATE)
    assert state['active_measurement_candidate'] == 'A83_fast_store_identity_preselect'
    assert state['current_source_candidate'] == 'A86_head_store_ack_bypass'
    pending = Path(state['pending_source_candidate'])
    assert sha(pending/'candidate.json') == state['pending_source_candidate_sha256']
    for name,digest in read(pending/'candidate.json')['source_sha256'].items():
        assert sha(pending/name) == digest,name
    source_proof = Path(state['last_source_progress_proof'])
    assert sha(source_proof) == state['last_source_progress_proof_sha256']
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(source_proof)['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest,name
    result = read(RUN/'result/result.json')
    ipc = read(RUN/'result/ipc.json')
    identity = read(RUN/'result/measurement_identity.json')
    timing = read(RUN/'result/timing_only.json')
    ppa = read(RUN/'result/synth/opt/report.json')
    assert result['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert result['environment'] == identity['environment'] == 'WINDOWS_NATIVE'
    assert identity['source_manifest_sha256'] == timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    assert identity['toolchain_manifest_sha256'] == timing['toolchain_manifest_sha256'] == 'c08263a362cd79513f17701b6328f8fb14d41a315539006d7b7dd71113ee3fb5'
    assert sha(RUN/'result/result.json') == identity['result_sha256'] == phases['result_sha256']
    assert sha(RUN/'result/ipc.json') == identity['ipc_sha256']
    assert sha(RUN/'result/synth/opt/report.json') == identity['official_report_sha256'] == timing['official_report_sha256']
    cpu = identity['prebuilt_cpu']
    assert cpu['status'] == 'COMPLETE' and cpu['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert sha(Path(cpu['executable'])) == cpu['executable_sha256']
    assert result['parameter_overrides'] == read(RUN/'source_manifest.json')['parameter_overrides']
    assert result['official_perf_expected_results_passed'] and result['official_correctness_suite_not_run']
    assert not result['official_correctness_suite_passed']
    assert ipc['official_scripts_unmodified'] and ipc['official_sim_cpp_unmodified']
    assert result['latency'] == ipc['latency'] == 10 and len(ipc['results']) == 6
    logs = {}
    for line in (RUN/'result/perf.log').read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)',line)
        if match:logs[match[1]]=(int(match[2]),int(match[3]))
    for row in ipc['results']:
        case = RUN/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
        assert sha(case/'program.data') == row['program_sha256']
        assert sha(case/'metrics.json') == row['metrics_sha256']
        assert read(case/'metrics.json')['dynamic_instructions'] == row['instructions']
        assert logs[row['name']] == (row['instructions'],row['cycles'])
        assert row['ipc'] == row['instructions']/row['cycles']
    assert math.exp(sum(math.log(r['ipc']) for r in ipc['results'])/6) == ipc['geomean_ipc'] == result['ipc']
    assert result['fmax_mhz'] == timing['fmax_mhz'] == ppa['timing']['estimated_fmax_mhz']
    assert result['area_um2'] == timing['area_um2'] == ppa['area']['area_um2']
    area = {k:v for k,v in ppa['area'].items() if isinstance(v,(int,float))}
    assert abs(area['area_um2']-area['logic_area_um2']-area['sram_area_um2']) < 1e-6
    previous = state['last_measured_result']
    assert previous['candidate'] == 'A75_branch_capture_phase_valid'
    metrics = dict(status=result['status'],candidate='A83_fast_store_identity_preselect',run=str(RUN),
        process_id=82452,process_alive=False,terminal_artifact_authority='Original serial rc0/rc0 result and PID absent',
        ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],minimum_period_ns=result['minimum_period_ns'],area_um2=result['area_um2'],
        sram_area_um2=area['sram_area_um2'],sequential_area_um2=area['sequential_area_um2'],combinational_area_um2=area['combinational_area_um2'],
        official_perf_expected_results_passed=True,full_correctness_not_run=True,full_correctness_passed=False,objective_numeric_met=False,
        source_manifest_sha256=plan['source_manifest_sha256'],candidate_sha256=plan['candidate_sha256'],
        result_sha256=identity['result_sha256'],ipc_sha256=identity['ipc_sha256'],ppa_sha256=identity['official_report_sha256'],rows=ipc['results'])
    assert metrics['ipc'] < 1.1 and metrics['fmax_mhz'] < 300
    delta = dict(ipc_relative_percent=(metrics['ipc']/previous['ipc']-1)*100,
        fmax_mhz=metrics['fmax_mhz']-previous['fmax_mhz'],area_um2=metrics['area_um2']-previous['area_um2'],
        ipc_required_relative_gain_percent=(1.1/metrics['ipc']-1)*100,area_margin_um2=36000-metrics['area_um2'],
        period_reduction_to300_ns=metrics['minimum_period_ns']-1000/300)
    critical_path = RUN/'result/synth/opt/critical_paths.json'
    paths = []
    for row in read(critical_path)['checks']:
        anchors=[];seen=set()
        for point in row['source_path']:
            net=point.get('net','')
            if net.startswith('core.') and '/' not in net and net not in seen:
                seen.add(net);anchors.append(dict(net=net,arrival_ns=point['arrival']*1e9))
        paths.append(dict(startpoint=row['startpoint'],endpoint=row['endpoint'],data_arrival_ns=row['data_arrival_time']*1e9,named_anchors=anchors))
    assert len(paths) == 5
    prior_rows = {r['name']:r for r in previous['rows']}
    case_changes = [dict(name=r['name'],old_cycles=prior_rows[r['name']]['cycles'],new_cycles=r['cycles'],
        saved_cycles=prior_rows[r['name']]['cycles']-r['cycles'],ipc=r['ipc']) for r in ipc['results']]
    case_table = '\n'.join(f"| {r['name']} | {r['old_cycles']} | {r['new_cycles']} | {r['saved_cycles']} | {r['ipc']:.6f} |" for r in case_changes)
    REPORT.write_text(f'''# A83 完整课程测量结果与后续方向

原PID82452已结束，串行综合/STA和性能阶段均返回0。冻结157源码/依赖、工具/库/约束、实际CPU二进制、程序镜像/动态指令分子、六项日志周期与几何平均、含SRAM面积均与同一测量身份核对。没有新测试或重启。

| 方案 | IPC | Fmax MHz | 总面积 μm² |
|---|---:|---:|---:|
| A75上次完成 | {previous['ipc']:.8f} | {previous['fmax_mhz']:.5f} | {previous['area_um2']:.5f} |
| A83本次完成 | {metrics['ipc']:.8f} | {metrics['fmax_mhz']:.5f} | {metrics['area_um2']:.5f} |

整批A76–A83使IPC提高{delta['ipc_relative_percent']:.4f}%，面积减少{-delta['area_um2']:.5f}μm²，频率下降{-delta['fmax_mhz']:.5f}MHz。不能把增益或退化单独归因于某个未独立测量的选项。面积组合{area['combinational_area_um2']:.5f}、时序{area['sequential_area_um2']:.5f}、SRAM{area['sram_area_um2']:.5f}μm²；最小周期{metrics['minimum_period_ns']:.9f}ns。

| 程序 | A75周期 | A83周期 | 少用周期 | A83 IPC |
|---|---:|---:|---:|---:|
{case_table}

六项官方性能答案通过。19正确性未运行，完整M/恢复/参数等尚未证明。当前IPC还需相对提高{delta['ipc_required_relative_gain_percent']:.4f}%，周期缩短超过{delta['period_reduction_to300_ns']:.6f}ns，面积余量{delta['area_margin_um2']:.3f}μm²；目标未达成，不采用。

五条最慢路径为同一新链，数据到达4.032/4.032/4.032/4.030/4.030ns：注册内存响应ID→缓存返回/命中选择→LSQ当前响应匹配/完成报告→当前ROB资格→CDB写回→PRF存储地址候选上位与分类→D资源入队→LSQ新行GEN状态。关键命名点为0.7946ns缓存返回LSQ标签、1.597ns加载ROB查询、2.091ns完成选择、2.292nsPRF值分发、2.755ns存储地址高位分类、3.319ns D入队ROB包分发、3.830ns LSQ GEN写控制。旧请求/前递链已不在本次最慢报告中，但不证明所有旧路径都无约束余量问题。

下一项直接修复方向：将快速存储限制为源数据已经保存就绪且当前没有匹配WB的情况，RAM/对齐类别提前从原保存地址加法结果计算；同时将RS容量条件预先算为普通需求和“省一项存储RS”两种，让晚到的真实快完成资格只作最终布尔选择。这样可移走本次实测的写回数据→存储地址分类→需求累加/容量比较串行链，保留实际LSQ地址/数据、完整GEN、原信用和后备RS执行；具体收益与覆盖率仍未知。

独立A84–A86已落盘但未测：A84重叠真实更老前缀退休与一条后续存储授权；A85前移缓存/MMIO确认身份匹配；A86仅让合法当前队首已提交存储当拍上报/释放，暂停保存仍由原行承接。三者不能继承A83这些指标。继续集中发展有依据的修改，不逐改测试；任何后续整批测量仍须先汇报。

频率/面积达标的已测综合最优仍A55R2：IPC1.01714182、306.86245MHz、35480.53090μm²。主E EU40文件保持原快照，所有新工作在F盘，不用WSL。目标仍为严格>300MHz/IPC≥1.1/含SRAM≤36000μm²以及完整架构要求。
''',encoding='utf-8')
    artifacts={str(p):sha(p) for p in [RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'dispatch_identity.json',
        RUN/'serial_phase_identity.json',RUN/'result/result.json',RUN/'result/ipc.json',RUN/'result/timing_only.json',
        RUN/'result/measurement_identity.json',RUN/'result/synth/opt/report.json',critical_path,Path(cpu['executable']),REPORT]}
    proof=dict(status='A83_ORIGINAL_COMPLETED_RESULT_BOUND',recorded_at=datetime.now(timezone.utc).isoformat(),new_tests_started=False,
        original_pid_absent=True,source_file_count=157,source_cpu_ipc_ppa_identity_verified=True,metrics=metrics,
        previous_a75_result=previous,delta_vs_a75=delta,case_cycle_changes=case_changes,critical_paths=paths,
        previous_incumbent=state['best_measured_combined_result'],selected_as_combined_incumbent=False,
        artifacts_sha256=artifacts,full_correctness_suite_not_run=True,pending_source_candidate=str(pending),
        pending_source_has_no_measured_metrics=True,previous_source_progress_proof=str(source_proof),
        previous_source_progress_proof_sha256=sha(source_proof),main_active_manifest_sha256=sha(active),
        main_eu_source_unchanged=True,adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A83_MEASURED_A86_PENDING_SOURCE_NOT_ADOPTED',previous_measured_result=previous,
        last_measured_candidate=metrics['candidate'],last_measured_result=metrics,last_completed_measurement_candidate=metrics['candidate'],
        last_completed_measurement_run=str(RUN),last_completed_measurement_process_id=82452,measurement_completed_at=phases['phases'][-1]['completed_at'],
        measurement_terminal_proof=str(PROOF),measurement_terminal_proof_sha256=sha(PROOF),last_status_result_proof=str(PROOF),
        last_status_result_proof_sha256=sha(PROOF),active_measurement_candidate=None,active_measurement_process_ids=[],measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        candidate_metrics_belong_to=None,candidate_tests_started=False,pending_source_candidate_tests_started=False,
        previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification='PROGRESS_A83_COMPLETE_IPC_GAIN_NEW_CDB_TO_STORE_ADMISSION_CRITICAL_PATH',
        candidates_adopted=False,goal_complete=False,
        next_work='Keep terminal A83 immutable; develop saved-only fast-store eligibility and parallel two-case D admission against actual4.032ns chain, alongside untested A84-A86; no per-edit tests.')
    write(STATE,state)
    print(dict(status=proof['status'],metrics={k:metrics[k] for k in ['ipc','fmax_mhz','area_um2']},delta_vs_a75=delta,
        proof=str(PROOF),proof_sha256=sha(PROOF),critical_sha256=sha(critical_path),pending=pending.name,goal_complete=False))


if __name__ == '__main__':
    main()
