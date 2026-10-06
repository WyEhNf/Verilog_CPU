"""Publish the completed EA native course result; read-only analysis, no EDA."""
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
    root=Path('E:/Verilog_cpu')
    run=Path('F:/CPU2026CourseRuns/architecture_EA_20261005')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    assert Path(active['frozen_run'])==run and active['measurement_process_id'] is None
    measured=read(run/'result/timing_only.json')
    summary=read('F:/CPU2026Proofs/EA_existing_reports_20261005/summary.json')
    paths=read('F:/CPU2026Proofs/EA_mapped_paths_20261005/saved_path_analysis.json')
    dm1=read('F:/CPU2026CourseRuns/architecture_DM1_20261005/result/result.json')
    assert measured['source_manifest_sha256']==sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert measured['official_report_sha256']==sha(run/'result/synth/opt/report.json')==summary['report_sha256']
    assert measured['fmax_mhz']==summary['timing']['estimated_fmax_mhz']==active['current_measured_fmax_mhz']
    assert measured['area_um2']==summary['area']['area_um2']==active['current_measured_area_um2']
    assert measured['cpu_build_started'] is False and measured['simulation_started'] is False
    assert active['current_measured_ipc'] is None and summary['ipc'] is None
    for name in ('native_build','native_ipc','result/ipc.json','result/result.json','directed'):
        assert not (run/name).exists(),name
    for name,expected in active['source_sha256'].items():
        assert sha(root/name)==expected,name
    changes=dict(frequency_vs_DM1_percent=100*(measured['fmax_mhz']/dm1['fmax_mhz']-1),
        area_vs_DM1_percent=100*(measured['area_um2']/dm1['area_um2']-1),
        area_vs_original_percent=summary['area_change_percent'])
    area=summary['area']
    report=root/'reports/frequency_EA_measurement_2026-10-05.md'
    assert not report.exists()
    text=f'''# EA Windows 原生课程综合结果

EA 八组组合完成一次课程综合/STA：**{measured['fmax_mhz']:.6f} MHz**，最低周期 **{measured['minimum_period_ns']} ns**，含 SRAM 总面积 **{measured['area_um2']:.6f} μm²**。相对完整实测 DM1，频率变化 **{changes['frequency_vs_DM1_percent']:+.4f}%**、总面积变化 **{changes['area_vs_DM1_percent']:+.4f}%**。本次未启动 CPU 构建、IPC 或功能程序；不能沿用 DM1 的 IPC。

|指标|EA 实测|要求对应|
|---|---:|---|
|频率|{measured['fmax_mhz']:.6f} MHz|超过原 300 MHz；未达到昂贵程序测量前的 350 MHz 工作判断值|
|组合面积|{area['combinational_area_um2']:.6f} μm²|原课程计价|
|时序面积|{area['sequential_area_um2']:.6f} μm²|实际映射 cell 面积，不是源码新增状态数|
|SRAM 面积|{area['sram_area_um2']:.6f} μm²|已计入总面积|
|总面积|{area['area_um2']:.6f} μm²|相对原基线 {changes['area_vs_original_percent']:+.4f}%，在 ±10% 内；仍超过 Tier3 的 36,000|
|IPC|未测|±10% 下限 0.882115146585、Tier3 1.0985 均未证明|
|功能正确性|未测|没有当前 EA 的程序验证结论|

## 已保存的五条最慢路径

这些是原课程导出的五条路径，非所有端点枚举。公共层级明确经过 LSQ report_bound、report row selection、预解码 normal ROB live 查询、completion source 选择、PRF port 4 旁路，再进入 `g_backend_lane_io[2].g_store_alloc_simm12.address_adder`。最末端寄存器为私有映射名，没有仅凭后缀猜测它的字段。

|序号|起点|终点|到达时间 ns|
|---:|---|---|---:|
'''
    text+=''.join(f"|{p['rank']}|`{p['startpoint']}`|`{p['endpoint']}`|{p['arrival_ns']:.4f}|\n" for p in paths['paths'])
    text+='''
最慢路径的 PRF `read_data_o[129]` 在 2.3777 ns 到达；分配加法器 `sum_o[30]` 在 2.8773 ns 到达，最后端点 2.9859 ns。PRF 后还有约 0.6082 ns 的加法/写入后缀。最大单门是 PRF 写地址 AOI21，0.1102 ns，11 个负载；这五条路径不再以 DT 的 1.3177 ns、220 负载共享 NAND5 为最大段。不能据此宣称全网表已经没有其他高扇出。

当前主要问题是一串小延迟组合步骤相加。继续对这条路径盲目加缓冲不能替代消除阶段之间的长联系。ED 源码备选关闭分配当拍的 store 提前地址，同时把无效地址 payload 固定为零，删除四个可选分配加法器；保留共享探测和普通 AGU。它直接切断本次报告中出现的后缀，仍需用下一完整组合的结果判断全局新瓶颈。

ED 没有新增状态或普通流水线级数，但地址可用时间和 younger-load 放行可能延迟，尤其多条 store 竞争每拍一个共享探测器时。EB/EC 针对共享探测锥，当前最慢五条没有选择它们的直接证据，因此暂存而不混入。EA 结果不够支撑启动昂贵程序测试；后续先完成源码范围和汇报，再做一次组合频率测量。

课程请求映射时钟为 2 ns；该时钟下约 -1.046 ns 的 slack 不等于 300 MHz 未通过。最终 328.205128 MHz 是原课程周期搜索结果。所有课程约束、ASAP7 RVT TT、FakeRAM 库/面积与工具版本保持固定，环境为 Windows 原生，未使用 WSL。

## 原始证据

'''
    text+=f"- 测量：`{run/'result/timing_only.json'}`\n- 源码 manifest SHA256：`{measured['source_manifest_sha256']}`\n- 工具 manifest SHA256：`{measured['toolchain_manifest_sha256']}`\n- 官方 report SHA256：`{measured['official_report_sha256']}`\n- 只读标量/路径摘要：`F:/CPU2026Proofs/EA_existing_reports_20261005/summary.json`\n- 映射路径分析：`F:/CPU2026Proofs/EA_mapped_paths_20261005/saved_path_analysis.json`\n"
    report.write_text(text,encoding='utf-8')
    verified=dict(status='CURRENT_SOURCE_COURSE_FMAX_AT_LEAST_300',fmax_mhz=measured['fmax_mhz'],
        source_manifest_sha256=measured['source_manifest_sha256'],report=str(report),
        scope='Course timing only; IPC, correctness and Tier3 are not verified.')
    active.update(measurement_report=str(report),current_timing_result_report=str(report),
        frequency_requirement_verified=verified,last_verified_frequency_requirement=verified,
        completion_audit=dict(observed_at=datetime.now(timezone.utc).isoformat(),frequency_300_met=True,
            area_within_10_percent=True,ipc_within_10_percent=None,tier3_area_met=False,tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='EA timing passes 300 MHz, area is within original ±10%. IPC/correctness unmeasured; Tier3 area unmet. Improve confirmed allocation store-address chain before further measurement.'))
    event=dict(candidate=active['candidate'],run=str(run),source_manifest_sha256=measured['source_manifest_sha256'],
        current_measured_fmax_mhz=measured['fmax_mhz'],current_measured_area_um2=measured['area_um2'],
        current_measured_ipc=None,status=active['status'],report=str(report),report_sha256=sha(report),
        timing_only=True,cpu_build_started=False,simulation_started=False,comparison=changes)
    active['last_timing_only_measurement']=event
    active.setdefault('timing_only_measurement_history',[]).append(event)
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),fmax_mhz=measured['fmax_mhz'],area_um2=measured['area_um2'],
                         comparison=changes,new_tests_started=False,overall_goal_complete=False)))


if __name__=='__main__':
    main()
