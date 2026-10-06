"""Publish one completed timing-only result from existing evidence, without EDA."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--summary',type=Path,required=True)
    parser.add_argument('--paths',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    run=args.run.resolve()
    assert Path(active['frozen_run']).resolve()==run and active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert not args.report.exists(),'Preserve an existing result report'
    assert not any(Path(e['run']).resolve()==run for e in active.get('timing_only_measurement_history',[]))
    measured=read(run/'result/timing_only.json')
    summary=read(args.summary)
    paths=read(args.paths)
    prior=read(active['previous_identity_backup'])['previous_identity']
    ref=read(Path(prior['frozen_run'])/'result/timing_only.json')
    assert measured['status']=='COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert measured['source_manifest_sha256']==sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert summary['source_manifest_sha256']==measured['source_manifest_sha256']
    assert measured['official_report_sha256']==sha(run/'result/synth/opt/report.json')==summary['report_sha256']
    assert paths['input_sha256']['critical_paths.json']==summary['critical_paths_sha256']
    assert paths['input_sha256']['mapped.v']==sha(run/'result/synth/opt/mapped.v')
    assert measured['fmax_mhz']==summary['timing']['estimated_fmax_mhz']==active['current_measured_fmax_mhz']
    assert measured['area_um2']==summary['area']['area_um2']==active['current_measured_area_um2']
    assert measured['config_sha256']==sha(run/'course_windows_config.json')
    config=read(run/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert measured['toolchain_manifest_sha256']==sha(Path(config['tools_root'])/'toolchain_manifest.json')
    assert not measured['cpu_build_started'] and not measured['simulation_started']
    assert active['current_measured_ipc'] is None
    for name in ('native_build','native_ipc','result/ipc.json','result/result.json','directed_cases'):
        assert not (run/name).exists(),name
    for name,expected in active['source_sha256'].items():
        assert sha(root/name)==expected,name
    cm=read(Path(active['candidate'])/'candidate.json')
    assert sha(Path(active['candidate'])/'candidate.json')==active['candidate_manifest_sha256']
    comparison=dict(frequency_vs_reference_percent=100*(measured['fmax_mhz']/ref['fmax_mhz']-1),
        area_vs_reference_percent=100*(measured['area_um2']/ref['area_um2']-1),
        area_vs_original_percent=summary['area_change_percent'],reference_run=prior['frozen_run'])
    area=summary['area']
    name=run.name
    text=f'''# {name} Windows 原生课程综合结果

完整组合完成一次课程综合/STA：**{measured['fmax_mhz']:.6f} MHz**，最低周期 **{measured['minimum_period_ns']} ns**，含 SRAM 总面积 **{measured['area_um2']:.6f} μm²**。相对 {Path(prior['frozen_run']).name}，频率 **{comparison['frequency_vs_reference_percent']:+.4f}%**、面积 **{comparison['area_vs_reference_percent']:+.4f}%**。这些数字仅属于当前冻结源；后台另存的候选不继承结果。

|指标|本次结果|范围|
|---|---:|---|
|Fmax|{measured['fmax_mhz']:.6f} MHz|课程周期搜索，300 MHz 门槛{'已满足' if measured['fmax_mhz']>=300 else '未满足'}|
|组合面积|{area['combinational_area_um2']:.6f} μm²|固定课程计价|
|时序面积|{area['sequential_area_um2']:.6f} μm²|实际映射结果|
|SRAM 面积|{area['sram_area_um2']:.6f} μm²|计入总面积|
|总面积|{area['area_um2']:.6f} μm²|原基线 {comparison['area_vs_original_percent']:+.4f}%，±10% {'以内' if summary['area_within_10_percent'] else '以外'}；Tier3 面积{'满足' if summary['tier3_area_met'] else '未满足'}|
|IPC、功能|未测|不得使用旧版本 IPC；完整目标未证明|

源码记录 {len(cm['implemented_groups'])} 组；普通整数流水线 10 级，源码声明新增状态 {cm['new_declared_sequential_state_bits']} 位。源码审查不是全核等价或功能证明。没有 CPU 构建、IPC 或功能程序，没有中间候选测量。只读取已有报告，未重新调用综合/STA。

## 已报告限制路径

下列仅为课程导出的 {len(paths['paths'])} 条路径，按到达时间降序，不是全部端点。到达时间含 clock-to-Q/输入预算；Fmax 还受 setup、clock pulse/period 约束，以原周期搜索为准。私有门名不能直接认定公开字段。下一结构决策需结合这些实际映射层级与负载。

|序号|起点|终点|到达 ns|
|---:|---|---|---:|
'''
    text+=''.join(f"|{i}|`{p['startpoint']}`|`{p['endpoint']}`|{p['arrival_ns']:.4f}|\n"
                  for i,p in enumerate(sorted(paths['paths'],key=lambda p:p['arrival_ns'],reverse=True),1))
    text+='''
原课程工具、ASAP7 RVT TT/FakeRAM、2 ns 请求映射时钟、0.05 ns uncertainty、5 fF 负载、reset=0 和无寄生模型保持，Windows 原生、未使用 WSL。2 ns 负 slack 不能直接解释成 300 MHz 失败。

原面积/IPC ±10% 与最终 Tier3 36,000 / 1.0985 / 300 仍需满足。频率结果不能替代 IPC 或正确性；后续测量仍先汇报，复用相同综合身份。

## 原始证据

'''
    text+=f"- 测量：`{run/'result/timing_only.json'}`\n- 冻结 manifest SHA256：`{measured['source_manifest_sha256']}`\n- 工具 manifest SHA256：`{measured['toolchain_manifest_sha256']}`\n- 官方 report SHA256：`{measured['official_report_sha256']}`\n- 标量摘要：`{args.summary.resolve()}`\n- 映射路径：`{args.paths.resolve()}`\n- 测试前范围：`{active['pretest_report']}`\n"
    args.report.write_text(text,encoding='utf-8')
    verified=dict(status=('CURRENT_SOURCE_COURSE_FMAX_AT_LEAST_300' if summary['frequency_300_met'] else
                          'CURRENT_SOURCE_COURSE_FMAX_BELOW_300'),fmax_mhz=measured['fmax_mhz'],
        source_manifest_sha256=measured['source_manifest_sha256'],report=str(args.report.resolve()),
        scope='Course timing only; IPC, correctness and Tier3 are not verified.')
    active.update(measurement_report=str(args.report.resolve()),current_timing_result_report=str(args.report.resolve()),
        frequency_requirement_verified=verified,
        completion_audit=dict(observed_at=datetime.now(timezone.utc).isoformat(),
            frequency_300_met=summary['frequency_300_met'],area_within_10_percent=summary['area_within_10_percent'],
            ipc_within_10_percent=None,tier3_area_met=summary['tier3_area_met'],tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='Timing-only complete. Read mapped limiting paths and decide next source scope; IPC/correctness and full Tier3 remain unverified or unmet.'))
    if summary['frequency_300_met']:
        active['last_verified_frequency_requirement']=verified
    event=dict(candidate=active['candidate'],run=str(run),source_manifest_sha256=measured['source_manifest_sha256'],
        current_measured_fmax_mhz=measured['fmax_mhz'],current_measured_area_um2=measured['area_um2'],
        current_measured_ipc=None,status=active['status'],report=str(args.report.resolve()),report_sha256=sha(args.report),
        timing_only=True,cpu_build_started=False,simulation_started=False,comparison=comparison)
    active['last_timing_only_measurement']=event
    active.setdefault('timing_only_measurement_history',[]).append(event)
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(args.report.resolve()),fmax_mhz=measured['fmax_mhz'],
        area_um2=measured['area_um2'],comparison=comparison,new_tests_started=False,overall_goal_complete=False)))


if __name__=='__main__':
    main()
