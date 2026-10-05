"""Record completed A16R2 IPC and independent A17R1 source work; no tests."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re
from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a16r2_measurement import RUN, CANDIDATE, GOAL_RECORD, check
from wait_frequency_directed_native import live

NEXT = Path('F:/CPU2026Candidates/tier3_er1_20261005/A17R1_shared_iterative_mdu')
REPORT = ROOT/'reports/ER1_A16R2_IPC_A17R1_source_progress_2026-10-05.md'
OUT = ROOT/'build/cpu2026/er1_a16r2_ipc_a17r1_source_progress_20261005.json'


def main():
    assert not REPORT.exists() and not OUT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    alive = live(dispatch['process_id'])
    ipc_path = RUN/'result/ipc.json'
    ipc = read(ipc_path)
    assert ipc['status'] == 'COMPLETE' and ipc['latency'] == 10 and len(ipc['results']) == 6
    for row in ipc['results']:
        case = RUN/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
        assert sha(case/'program.data') == row['program_sha256']
        assert sha(case/'metrics.json') == row['metrics_sha256']
        assert read(case/'metrics.json')['dynamic_instructions'] == row['instructions']
        assert row['ipc'] == row['instructions']/row['cycles']
    computed = math.exp(sum(math.log(r['instructions']/r['cycles']) for r in ipc['results'])/6)
    assert math.isclose(computed,ipc['geomean_ipc'],rel_tol=1e-12)
    next_candidate = read(NEXT/'candidate.json')
    assert next_candidate['tests_started'] is False and next_candidate['adopted'] is False
    for name, digest in next_candidate['source_sha256'].items():
        assert sha(NEXT/name) == digest, name
    active = read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name, digest in active['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    identity = read(RUN/'result/measurement_identity.json')
    assert identity['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert identity['perf_max_cycles'] == 1000000 and identity['correctness_max_cycles'] == 10000000
    assert identity['prebuilt_cpu']['status'] == 'COMPLETE'
    assert sha(identity['prebuilt_cpu']['executable']) == identity['prebuilt_cpu']['executable_sha256']
    ppa = optional(RUN/'result/synth/opt/report.json')
    correctness_path = RUN/'result/correctness.log'
    log = correctness_path.read_text(encoding='utf-8') if correctness_path.exists() else ''
    correctness = [dict(name=m[1],result=m[2]) for m in re.finditer(
        r'^\[(correctness_[^\]]+)\]\s*\n(PASS[^\n]*|FAIL:[^\n]*)',log,re.M)]
    passed = sum(row['result'].startswith('PASS') for row in correctness)
    failed = len(correctness)-passed
    finished = 'Results:' in log
    a8 = read(RUN/'a8_terminal_reference.json')
    goal = read(GOAL_RECORD)
    changes = dict(ipc_vs_a8_pct=100*(computed/a8['ipc']-1),
                   ipc_vs_er1_pct=100*(computed/goal['baseline']['ipc']-1),
                   required_ipc_increase_pct=100*(1.1/computed-1))
    table = '\n'.join(f"|{r['name']}|{r['instructions']}|{r['cycles']}|{r['ipc']:.8f}|" for r in ipc['results'])
    phase_text = (f"Fmax {ppa['timing']['estimated_fmax_mhz']:.8f}MHz，总面积{ppa['area']['area_um2']:.6f}μm²（含SRAM）" if ppa else
                  '综合/STA尚无完整报告；频率和含SRAM总面积未知，不能继承A8数字')
    REPORT.write_text(f'''# ER1 A16R2 IPC实测与A17R1源码进度

A16R2六个官方perf答案全部通过，IPC几何平均 **{computed:.8f}**。
相对A8提高 **{changes['ipc_vs_a8_pct']:.4f}%**，相对ER1提高 **{changes['ipc_vs_er1_pct']:.4f}%**。
距离IPC≥1.1还需提高 **{changes['required_ipc_increase_pct']:.4f}%**；{phase_text}。目标未完成。

|程序|官方动态指令数|周期|IPC|
|---|---:|---:|---:|
{table}

快照时原驱动PID{dispatch['process_id']}存活={alive}；correctness已收到{passed}通过/{failed}失败，整套结束={finished}。
perf仍为latency10、100万周期上限；correctness单独记录1000万周期上限、原程序和答案。A8原100万预算16通过/3超时失败的日志仍保留。
两次早期机械错误分别为SV保留字matches及MSHR端口标签误改，在仿真前失败；A16/A16R1构建与中止的未完成综合日志保留。
A16R2只修复这些错误；主Icache主体与A11在只改信号名后完全相同，所有子模块命名端口标签逐项相同。已有完整CPU构建证据，不将源级逆替换当成可构建证明。

已实现的本轮组合包括：一拍热指令行缓冲、依赖load地址直通选择、实际资源原子准入的两项弹性派发、两路后端/四个PRF读端口、恢复ER1数据缓存容量、ROB/CDB窄载荷及共享桶形移位器。当前IPC有明显收益，但median/qsort仍较低，load完成到写回的剩余等待需要进一步分析；towers比A8增加周期，不能称每项都提升。

测量期间继续优化：已准备独立 **A17R1_shared_iterative_mdu**，尚未构建/仿真/综合/STA，也未采用。
六个官方perf完整.text的静态M指令数均为0，逐条同时核对反汇编助记符与opcode/funct7，perf_multiply为软件移位/加法。
新候选仅将顶层MUL_IMPL=0→2，选择现有完整RV32M共享32步迭代引擎，所有40个其余源码hash项不变。
保留全部八个M操作、带符号高半部、除零/溢出、完整ROB tag/物理目的、背压与本地恢复。代价是M密集程序吞吐降低；迭代比较/减法/符号修正可能成为新关键路径。静态M-free代码不能代替动态IPC、实际面积/频率或控制流证明。
六perf不覆盖M操作，最终采用这个配置仍需相关现有M单元检查与恢复/背压覆盖，不能仅凭25个课程答案宣称全RV32IM覆盖。

未向正在测量的A16R2添加该改动，测量源及本轮宿主脚本hash均保持冻结；EU主工作树源码hash保持原值。
没有启动A17R1或任何中间候选测试，没有参数扫描。完整目标仍是IPC≥1.1、Fmax>300MHz、含SRAM总面积≤36,000μm²和正确性。

实测源manifest：{plan['source_manifest_sha256']}。
A16R2候选manifest：{plan['candidate_sha256']}。
A17R1候选manifest：{sha(NEXT/'candidate.json')}。
''',encoding='utf-8')
    proof = dict(status='A16R2_SIX_PERF_COMPLETE_OTHER_PHASES_OBSERVED_A17R1_SOURCE_PREPARED',
        recorded_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),process_id=dispatch['process_id'],process_alive=alive,
        measured_candidate=str(CANDIDATE),source_manifest_sha256=plan['source_manifest_sha256'],
        ipc=computed,official_perf_expected_results_passed=True,ipc_report_sha256=sha(ipc_path),changes=changes,
        ppa_report_available=bool(ppa),fmax_mhz=ppa['timing']['estimated_fmax_mhz'] if ppa else None,
        area_um2=ppa['area']['area_um2'] if ppa else None,
        correctness=correctness,correctness_passed=passed,correctness_failed=failed,correctness_finished=finished,
        correctness_log_snapshot_sha256=sha(correctness_path) if correctness_path.exists() else None,
        prepared_candidate=str(NEXT),prepared_candidate_sha256=sha(NEXT/'candidate.json'),
        prepared_candidate_tests_started=False,prepared_candidate_adopted=False,
        isa_mix_proof_sha256=sha('F:/CPU2026Proofs/ER1_official_perf_static_instruction_mix_20261005.json'),
        source_review_sha256=sha(NEXT.parent/'A17R1_source_review.json'),
        a16r2_measurement_source_changed=False,main_worktree_source_changed=False,goal_complete=False,
        report=str(REPORT),report_sha256=sha(REPORT))
    write(OUT,proof)
    goal.update(status='A16R2_PERF_COMPLETE_PPA_CORRECTNESS_OBSERVED_A17R1_SOURCE_PREPARED',
        candidate_metrics_belong_to=CANDIDATE.name,candidate_ipc=computed,
        candidate_fmax_mhz=proof['fmax_mhz'],candidate_area_um2=proof['area_um2'],
        candidate_correctness_passed=passed,candidate_correctness_failed=failed,candidate_correctness_finished=finished,
        current_prepared_candidate=NEXT.name,pending_source_candidate=str(NEXT),
        pending_source_candidate_sha256=sha(NEXT/'candidate.json'),pending_source_candidate_tests_started=False,
        last_goal_turn_classification='PROGRESS_A16_SHARED_BARREL_ATOMIC_DISPATCH_REPAIRS_UNIFIED_IPC_GAIN_AND_A17R1_MDU_AREA_TRADEOFF',
        last_background_progress=str(REPORT),last_background_progress_sha256=sha(REPORT),
        next_work=['Observe the same live A16R2 driver92584 through official PPA and19correctness; do not restart on polling timeouts.',
                   'Continue load completion/branch stall analysis independently; A17R1 remains untested and unadopted.',
                   'Use measured bottlenecks/area budget to assemble next material candidate and report before one unified measurement.',
                   'Audit strict final IPC>=1.1, Fmax>300, area-including-SRAM<=36000, and required correctness scope.'])
    write(GOAL_RECORD,goal)
    print({key:proof[key] for key in ('status','process_id','process_alive','ipc','fmax_mhz','area_um2',
        'correctness_passed','correctness_failed','prepared_candidate_tests_started')})


if __name__ == '__main__':
    main()
