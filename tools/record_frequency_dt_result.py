"""Publish verified DT timing-only results from existing files; run no EDA."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    run=Path('F:/CPU2026CourseRuns/architecture_DT_20261005')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=json.loads(active_path.read_text(encoding='utf-8'))
    assert Path(active['frozen_run'])==run and active['measurement_process_id'] is None
    measured=json.loads((run/'result/timing_only.json').read_text(encoding='utf-8'))
    summary=json.loads(Path('F:/CPU2026Proofs/DT_existing_reports_20261005/summary.json').read_text(encoding='utf-8'))
    paths=json.loads(Path('F:/CPU2026Proofs/DT_mapped_paths_20261005/saved_path_analysis.json').read_text(encoding='utf-8'))
    assert measured['source_manifest_sha256']==sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert measured['official_report_sha256']==sha(run/'result/synth/opt/report.json')
    assert measured['fmax_mhz']==summary['timing']['estimated_fmax_mhz']==active['current_measured_fmax_mhz']
    assert measured['area_um2']==summary['area']['area_um2']==active['current_measured_area_um2']
    assert measured['cpu_build_started'] is False and measured['simulation_started'] is False
    for name in ('native_build','native_ipc','result/ipc.json','result/result.json','directed'):
        assert not (run/name).exists(),name
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    prior=active['previous_measurement']
    freq_change=100*(measured['fmax_mhz']/prior['current_measured_fmax_mhz']-1)
    area_change=100*(measured['area_um2']/prior['current_measured_area_um2']-1)
    report=root/'reports/frequency_DT_measurement_2026-10-05.md'
    assert not report.exists()
    text=f'''# DT 原生课程频率结果（2026-10-05）

DT 仅完成一次 Windows 原生课程综合/STA：**272.2680 MHz**，最低周期 **3.6728515625 ns**，含 SRAM 面积 **51,371.6362 μm²**。相对 DM1 的 302.1540 MHz，频率变化 **{freq_change:.4f}%**，面积变化 **{area_change:+.4f}%**。此次组合未达到预期；没有启动 CPU 构建、IPC 或功能程序。

|指标|DT 实测|含义|
|---|---:|---|
|频率|272.2680 MHz|低于 300 MHz|
|组合面积|32,484.1234 μm²|课程计价|
|时序面积|11,061.8460 μm²|与 DM1 相同|
|SRAM 面积|7,825.666854 μm²|包含在总面积|
|总面积|51,371.6362 μm²|超过原始 +10% 上限 50,940.662839 和 Tier3 上限 36,000|
|IPC|未测|不能沿用 DM1 的 0.78237|
|功能正确性|未测|没有此次版本的正确性结论|

## 已有报告中的五条最慢路径

这些是课程流程发布的五条路径，不是所有时序端点的枚举。都起于 `_622936_/QN`，经 LSQ `selected_lsq_tag[6]`、选择状态查询、候选状态查询、共享控制门和 `request_fire` 到 LSQ 状态寄存器。

|序号|端点|数据到达时间 ns|
|---:|---|---:|
'''
    text+=''.join(f"|{p['rank']}|`{p['endpoint']}`|{p['arrival_ns']:.4f}|\n" for p in paths['paths'])
    text+='''
最大的两段是 `_350899_`（NAND5，220 个直接输入负载，98.3994 fF，1.3177 ns，输出 slew 2.795 ns）和 `_350900_`（INV，36 个负载，0.9104 ns）。二者合计 2.2281 ns，约占最慢数据到达时间的 61.6%。后者的公共网名显示为 AXI `enabled_words` 的第 0 位；扁平优化会合并等价条件，此名称不能单独证明计算字数函数是根因。

实际慢锥包含 LSQ 请求资格、转发/请求掩码与握手状态更新；应控制这些条件的真实负载、缩短控制分发深度。DT 中 completion/PRF 五组修改影响了整体映射，但仅凭最慢五条路径不能把回退分别归因于其中某一组，也不能证明它们全部无收益。因此保留 DT 原始结果，下一组合以已有较好结果的 DM1 为父版本。

## 版本及测量范围

课程工具与库保持固定版本，环境为 Windows 原生，禁止 WSL。课程约束、库、FakeRAM 计价均未修改。请求映射时钟为 2 ns，课程通过周期搜索得到上述最低周期；2 ns 报告的负 slack 不等于 300 MHz 下同样程度的违例。

'''
    text+=f"- 源码 manifest SHA256：`{measured['source_manifest_sha256']}`\n- 工具 manifest SHA256：`{measured['toolchain_manifest_sha256']}`\n- 官方 report SHA256：`{measured['official_report_sha256']}`\n- 原始结果：`{run/'result/timing_only.json'}`\n- 映射路径只读分析：`F:/CPU2026Proofs/DT_mapped_paths_20261005/saved_path_analysis.json`\n"
    report.write_text(text,encoding='utf-8')
    active.update(measurement_report=str(report),current_timing_result_report=str(report),
        frequency_requirement_verified=dict(status='CURRENT_SOURCE_FMAX_BELOW_300',fmax_mhz=measured['fmax_mhz'],
            source_manifest_sha256=measured['source_manifest_sha256'],report=str(report)),
        completion_audit=dict(observed_at=datetime.now(timezone.utc).isoformat(),frequency_300_met=False,
            area_within_10_percent=False,ipc_within_10_percent=None,tier3_area_met=False,tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='DT timing regressed to 272.268 MHz. No CPU build, IPC or correctness run. Prepare a combined measured-DM1 descendant before further measurement.'))
    event=dict(candidate=active['candidate'],run=str(run),source_manifest_sha256=measured['source_manifest_sha256'],
               current_measured_fmax_mhz=measured['fmax_mhz'],current_measured_area_um2=measured['area_um2'],
               current_measured_ipc=None,status=active['status'],report=str(report),report_sha256=sha(report),
               timing_only=True,cpu_build_started=False,simulation_started=False)
    active['last_timing_only_measurement']=event
    active.setdefault('timing_only_measurement_history',[]).append(event)
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':active['status'],'report':str(report),'fmax_mhz':measured['fmax_mhz'],
                      'frequency_change_vs_DM1_percent':freq_change,'new_tests_started':False}))


if __name__=='__main__':main()
