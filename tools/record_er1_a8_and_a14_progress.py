"""Audit completed A8 phases and record source progress; run no hardware tools."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re
from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a8_measurement import RUN, CANDIDATE, GOAL_RECORD, check
from wait_frequency_directed_native import live

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
NEXT=BASE/'A14_two_wide_backend_er1_dcache'
REPORT=ROOT/'reports/ER1_A8_results_A14_source_progress_2026-10-05.md'
OUT=ROOT/'build/cpu2026/er1_a8_results_a14_source_progress_20261005.json'


def main():
    assert not REPORT.exists() and not OUT.exists()
    plan=check()
    candidate=read(NEXT/'candidate.json')
    assert candidate['tests_started'] is False and candidate['adopted'] is False
    for name,digest in candidate['source_sha256'].items():assert sha(NEXT/name)==digest,name
    ipc_path=RUN/'result/ipc.json';ipc=read(ipc_path)
    assert ipc['status']=='COMPLETE' and ipc['latency']==10 and len(ipc['results'])==6
    for row in ipc['results']:
        case=RUN/'source/.deps/RISC-V-CPU-2026/testcases'/row['name']
        assert sha(case/'program.data')==row['program_sha256']
        assert sha(case/'metrics.json')==row['metrics_sha256']
        assert read(case/'metrics.json')['dynamic_instructions']==row['instructions']
        assert row['ipc']==row['instructions']/row['cycles']
    computed=math.exp(sum(math.log(row['instructions']/row['cycles']) for row in ipc['results'])/6)
    assert math.isclose(computed,ipc['geomean_ipc'],rel_tol=1e-12)
    report_path=RUN/'result/synth/opt/report.json';ppa=read(report_path)
    area=ppa['area'];timing=ppa['timing']
    assert math.isclose(area['area_um2'],sum(area[k] for k in
        ('combinational_area_um2','sequential_area_um2','sram_area_um2')),abs_tol=1e-6)
    assert math.isclose(area['sram_area_um2'],4299.816954,abs_tol=1e-6)
    baseline=read(GOAL_RECORD)['baseline']
    dispatch=read(RUN/'dispatch_identity.json')
    alive=live(dispatch['process_id'])
    log_path=RUN/'result/correctness.log';log=log_path.read_text(encoding='utf-8')
    matches=list(re.finditer(r'^\[(correctness_[^\]]+)\]\s*\n(PASS[^\n]*|FAIL:[^\n]*)',log,re.M))
    correctness=[dict(name=m[1],result=m[2]) for m in matches]
    pending=(re.findall(r'^\[(correctness_[^\]]+)\]',log,re.M) or [None])[-1]
    finished='Results:' in log
    passed=sum(row['result'].startswith('PASS') for row in correctness)
    failed=len(correctness)-passed
    table='\n'.join(f"|{r['name']}|{r['instructions']}|{r['cycles']}|{r['ipc']:.8f}|" for r in ipc['results'])
    changes=dict(ipc_pct=100*(computed/baseline['ipc']-1),
        area_pct=100*(area['area_um2']/baseline['area_um2']-1),
        fmax_pct=100*(timing['estimated_fmax_mhz']/baseline['fmax_mhz']-1))
    REPORT.write_text(f'''# ER1 A8 实测与 A14 独立源码进度

A8六perf已完成：IPC几何平均 **{computed:.8f}**。课程综合/STA已完成：
总面积 **{area['area_um2']:.6f} μm²（含SRAM）**，Fmax **{timing['estimated_fmax_mhz']:.8f} MHz**。
相对ER1，IPC {changes['ipc_pct']:+.4f}%，总面积 {changes['area_pct']:+.4f}%，频率 {changes['fmax_pct']:+.4f}%。
频率满足>300；面积还差{area['area_um2']-36000:.6f}μm²，IPC还需提高{100*(1.1/computed-1):.4f}%。目标未达成。

面积分解：组合{area['combinational_area_um2']:.6f}，时序{area['sequential_area_um2']:.6f}，SRAM{area['sram_area_um2']:.6f} μm²。
SRAM37个：32×256x8、4×256x20、1×128x128；本次实际宏形状/面积符合A2容量预算。

|程序|动态指令数|周期|IPC|
|---|---:|---:|---:|
{table}

median、multiply、qsort、towers减少周期；rsort和vvadd增加周期。
rsort的244978周期比ER1的184341增加32.894%；不能将整个变化唯一归因为D-cache缩容，ROB/PRF/RS容量与流水线也同时改变。
此次大幅面积收益没有转化为总体IPC收益，下一步必须解决供给和依赖延迟，并重新平衡逻辑带宽与缓存容量。

记录时驱动PID{dispatch['process_id']}存活={alive}，十九项correctness已收到{passed}通过/{failed}失败，整套结束={finished}，最新用例={pending}。
当前日志中pi/qsort可能达到默认1,000,000周期上限；尚不能将超时证明为功能错误或证明为仅限额问题。
官方metrics：pi3,117,658、qsort1,097,111、tak1,221,227条动态指令。输出仍必须通过。
课程固定提交README-EN.md明确给出MAX_CYCLES=5000000的自定义测试示例，config.mk也给出MAX_CYCLES=100000000注释示例。
后续统一验证将明确记录合理周期预算、保持latency10及原脚本/答案，不覆盖这次默认限额失败日志，不将其改写为通过。
参考：[官方固定提交说明](https://github.com/ACMClassCourse-2025/RISC-V-CPU-2026/blob/54fc150ffc290f52aa024209ffb9a29d43856f6d/README-EN.md)。

独立后续候选已实现，均未测试/未采用，A8冻结源码完全未改：

|候选修改|具体结构变化|限制|
|---|---|---|
|A9—A11无用ROB/CDB载荷投影|移除无调用方消费者的载荷及其选择/广播通道，保留PRF架构写回值与实际LSQ/AXI store数据|不是所有诊断接口等价；映射收益未测|
|A12 16行指令缓冲|注册命中从两拍到一拍；未命中原Icache主体仅端口重命名；保留epoch、全PC身份及背压|新增声明2650位状态；命中比例、频率、面积未测|
|A13依赖型load地址直通选择|有效完整LSQ标签匹配的AGU load地址同拍进入原选择寄存器，省一拍；旧store未知地址/data仍阻塞|组合路径变长，需保持频率>300MHz|
|A14单一两路后端组合|FE4/BE2/INT2/CDB2、ROB32/PRF56/RS8/LSQ16、恢复ER1 Dcache1024行2路|PRF读端口8→4、ALU4→2，但退休峰值4→2；SRAM相对A8增加3525.8499μm²，必须由逻辑削减偿付|

A14只是一个具体结构tradeoff，不是参数扫描结果，也没有继承A8的任何IPC/频率/面积数字。
两路峰值2IPC高于1.1目标不等于实际能达标；继续源级面积压缩和瓶颈分析，再汇报下一次完整组合的收益依据和验证范围。
本记录没有启动新的CPU构建、仿真、综合、STA、定向测试或回归。仅读取既有结果并实现独立候选。

原始结果：{ipc_path}；{report_path}；{log_path}。
活动测量源码manifest SHA256：{plan['source_manifest_sha256']}。
最新候选manifest SHA256：{sha(NEXT/'candidate.json')}。
''',encoding='utf-8')
    proof=dict(status='A8_PERF_PPA_COMPLETE_CORRECTNESS_OBSERVED_A14_SOURCE_PREPARED',
        recorded_at=datetime.now(timezone.utc).isoformat(),measurement_run=str(RUN),
        measured_candidate=str(CANDIDATE),source_manifest_sha256=plan['source_manifest_sha256'],
        process_id=dispatch['process_id'],process_alive=alive,
        ipc=computed,fmax_mhz=timing['estimated_fmax_mhz'],area_um2=area['area_um2'],
        ipc_report_sha256=sha(ipc_path),official_ppa_report_sha256=sha(report_path),
        measurement_identity_sha256=sha(RUN/'result/measurement_identity.json'),
        correctness_log_snapshot_sha256=sha(log_path),correctness_snapshot=correctness,
        correctness_finished=finished,correctness_passed=passed,correctness_failed=failed,
        official_correctness_default_max_cycles=1000000,
        cycle_budget_source='Course pinned README-EN.md lines293-294 and config.mk line47',
        course_documents_sha256={n:sha(ROOT/'.deps/RISC-V-CPU-2026'/n)
            for n in ('README-EN.md','README-ZH.md','config.mk')},
        prepared_candidate=str(NEXT),prepared_candidate_sha256=sha(NEXT/'candidate.json'),
        source_reviews={f'A{i}_source_review.json':sha(BASE/f'A{i}_source_review.json') for i in range(9,15)},
        previous_goal_turn_classification='PROGRESS_NEW_A8_OFFICIAL_IPC_EVIDENCE',
        this_goal_turn_classification='PROGRESS_A12_A13_A14_IMPLEMENTED_A8_PPA_AND_COURSE_LIMIT_EVIDENCE',
        new_tests_started=False,measurement_source_changed=False,goal_complete=False,
        report=str(REPORT),report_sha256=sha(REPORT),changes_vs_er1_pct=changes)
    write(OUT,proof)
    goal=read(GOAL_RECORD)
    goal.update(status='A8_PERF_PPA_COMPLETE_CORRECTNESS_IN_PROGRESS' if alive else 'A8_MEASUREMENT_TERMINAL_A14_SOURCE_PREPARED',
        candidate_ipc=computed,candidate_fmax_mhz=timing['estimated_fmax_mhz'],candidate_area_um2=area['area_um2'],
        candidate_metrics_belong_to='A8_direct_issue_local_recovery',
        current_prepared_candidate=NEXT.name,pending_source_candidate=str(NEXT),
        pending_source_candidate_sha256=proof['prepared_candidate_sha256'],pending_source_candidate_tests_started=False,
        active_measurement_candidate=CANDIDATE.name,measurement_process_id=dispatch['process_id'],
        last_background_progress=str(REPORT),last_background_progress_sha256=sha(REPORT),
        last_goal_turn_classification=proof['this_goal_turn_classification'],
        candidate_correctness_passed=passed,candidate_correctness_failed=failed,
        candidate_correctness_finished=finished,goal_complete=False,
        next_work=[
            'Observe original A8 driver95760 through terminal correctness result; preserve default1M failures.',
            'Continue area reduction and load/frontend latency work in independent A14; do not inherit A8 metrics.',
            'Derive next unified measurement gain evidence and report before tests; use explicit course-supported correctness cycle budget.',
            'Final same-frozen-source six-perf/19-correctness/full-PPA audit for IPC>=1.1, Fmax>300, area<=36000 including SRAM.'
        ])
    write(GOAL_RECORD,goal)
    print({k:proof[k] for k in ('status','process_id','process_alive','ipc','fmax_mhz','area_um2',
        'correctness_passed','correctness_failed','correctness_finished','new_tests_started')})


if __name__=='__main__':main()
