"""Prepare a concrete program-phase report after verified material timing gain."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from start_reused_frequency_programs_background import ROOT, ACTIVE, read, sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    assert os.name=='nt'
    run=args.run.resolve()
    report=args.report.resolve()
    assert not report.exists()
    active=read(ACTIVE)
    assert Path(active['frozen_run']).resolve()==run
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert active['measurement_process_id'] is None
    timing=read(run/'result/timing_only.json')
    config=read(run/'course_windows_config.json')
    official=read(run/'result/synth/opt/report.json')
    observation=read(run/'measurement_observation.json')
    assert observation['driver_process_live_now'] is False and observation['timing_only_complete']
    assert timing['status']=='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256']==sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert timing['config_sha256']==sha(run/'course_windows_config.json')
    assert timing['toolchain_manifest_sha256']==sha(Path(config['tools_root'])/'toolchain_manifest.json')
    assert timing['official_report_sha256']==sha(run/'result/synth/opt/report.json')
    assert timing['fmax_mhz']==active['current_measured_fmax_mhz']
    assert timing['area_um2']==active['current_measured_area_um2']
    assert timing['fmax_mhz']>=active['measurement_plan']['material_frequency_gain_working_threshold_mhz']
    assert timing['area_um2']<=active['measurement_plan']['original_plus_10_percent_area_um2']
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    for n,h in active['source_sha256'].items():
        assert sha(ROOT/n)==h,n
    frozen=read(run/'source_manifest.json')
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    for name in ('native_build','native_ipc','program_dispatch_identity.json',
        'program_driver_stdout.log','program_driver_stderr.log','result/ipc.json',
        'result/result.json','result/perf.log','result/correctness.log','result/build_host.log','result/failure.json'):
        assert not (run/name).exists(),name
    base=run/'source/.deps/RISC-V-CPU-2026/testcases'
    perf=sorted(x.name for x in base.glob('perf_*') if x.is_dir())
    correctness=sorted(x.name for x in base.glob('correctness_*') if x.is_dir())
    assert len(perf)==6 and len(correctness)==19
    prior=active['previous_measurement']
    gain=100*(timing['fmax_mhz']/prior['current_measured_fmax_mhz']-1)
    original_area_change=100*(timing['area_um2']/active['measurement_plan']['area_reference_um2']-1)
    pending=active.get('pending_source_research',[])
    conditional='、'.join(Path(x['candidate']).name for x in pending) or '无'
    text=f'''# {run.name} 必要程序阶段测试前汇报

当前完整冻结源已完成一次课程timing-only：Fmax **{timing['fmax_mhz']:.6f} MHz**，最低周期 **{timing['minimum_period_ns']} ns**，含SRAM总面积 **{timing['area_um2']:.6f} μm²**。相比直接父版本频率 **{gain:+.4f}%**；原面积基线 **{original_area_change:+.4f}%**，不超过上限50,940.662839。SRAM计价继续包含在总面积。频率已超过300MHz与既有昂贵程序阶段工作门槛350MHz；IPC和完整功能尚未测，不据此宣布Tier3或整体成功。

本阶段只对这一个身份构建一次Windows原生Verilator5.020 CPU，运行6个官方perf及19个官方correctness。**使用--reuse-synth --correctness，复用完全相同综合/STA，不再综合。** 课程原testcase.py、sim.cpp、程序/答案/metrics与latency10不变，IPC分子仍为官方dynamic_instructions，整体为6程序GEOMEAN。无需逐个改动/模块/中间候选仿真。

测试以独立后台program PID执行；主源和冻结源保持，期间后续优化只写独立候选。尚存条件源码候选：{conditional}，未采用、未测，不能继承当前结果。其采用取决于新实际路径支持，不因存在候选便无依据地追加时序跑分。本阶段的目的在于确认已有频率改善下的功能与IPC边界；不是用程序结果代替频率优化。

## 范围

Perf：{', '.join(perf)}。

Correctness：{', '.join(correctness)}。

通过条件为全部官方程序输出正确，并核实周期/指令与来源身份。原IPC±10%下限为0.882115146585，最终Tier3 IPC≥1.0985、含SRAM面积≤36,000、频率≥300；当前面积仍未到Tier3，未知IPC不能沿用旧版本。若程序失败或IPC越界，保存原始结果后按数据修整，不重复无关测试。

## 固定身份与限制

冻结manifest SHA256：`{active['frozen_manifest_sha256']}`。

官方时序/面积report SHA256：`{timing['official_report_sha256']}`。

framework 54fc150ffc290f52aa024209ffb9a29d43856f6d、testcases 29f980727f7d99a1842a58f34091c7579ba3fe85；原生Yosys0.63/课程ABC/OpenSTA3.1/Verilator5.020、ASAP7 RVT TT/FakeRAM、2ns映射及原约束不变，禁止WSL。流程脚本的静态审查已完成，但本报告生成时CPU构建、程序阶段尚未开始。须先在对话汇报本报告，再调用一次原生后台调度。
'''
    report.write_text(text,encoding='utf-8')
    tools=['tools/record_reused_frequency_program_pretest.py',
        'tools/start_reused_frequency_programs_background.py','tools/record_reused_frequency_program_progress.py']
    plan=dict(created_at=datetime.now(timezone.utc).isoformat(),ready_for_dispatch=True,
        scope_finalized=True,reuse_existing_synth=True,full_course_correctness_requested=True,
        native_cpu_builds_planned=1,new_synth_runs_planned=0,perf_cases=perf,correctness_cases=correctness,
        source_manifest_sha256=active['frozen_manifest_sha256'],environment='WINDOWS_NATIVE',wsl_allowed=False,
        no_intermediate_candidate_tests=True,tools_sha256={n:sha(ROOT/n) for n in tools})
    active.update(program_pretest_report=str(report),program_pretest_report_sha256=sha(report),
        program_measurement_plan=plan)
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),report_sha256=sha(report),
        fmax_mhz=timing['fmax_mhz'],area_um2=timing['area_um2'],perf_cases=len(perf),
        correctness_cases=len(correctness),cpu_build_started=False,program_phase_started=False)))


if __name__=='__main__':
    main()
