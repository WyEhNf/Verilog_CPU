"""Record completed EF timing-only evidence without starting another tool run."""
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
    run=Path('F:/CPU2026CourseRuns/architecture_EF_20261005')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    assert Path(active['frozen_run'])==run and active['measurement_process_id'] is None
    measured=read(run/'result/timing_only.json')
    summary=read('F:/CPU2026Proofs/EF_existing_reports_20261005/summary.json')
    paths=read('F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json')
    ea=read('F:/CPU2026CourseRuns/architecture_EA_20261005/result/timing_only.json')
    assert measured['source_manifest_sha256']==sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert measured['official_report_sha256']==sha(run/'result/synth/opt/report.json')==summary['report_sha256']
    assert measured['fmax_mhz']==summary['timing']['estimated_fmax_mhz']==active['current_measured_fmax_mhz']
    assert measured['area_um2']==summary['area']['area_um2']==active['current_measured_area_um2']
    assert not measured['cpu_build_started'] and not measured['simulation_started']
    assert active['current_measured_ipc'] is None
    for name in ('native_build','native_ipc','result/ipc.json','result/result.json','directed'):
        assert not (run/name).exists(),name
    for name,expected in active['source_sha256'].items():
        assert sha(root/name)==expected,name
    comparison=dict(frequency_vs_EA_percent=100*(measured['fmax_mhz']/ea['fmax_mhz']-1),
        area_vs_EA_percent=100*(measured['area_um2']/ea['area_um2']-1),
        area_vs_original_percent=summary['area_change_percent'])
    area=summary['area']
    report=root/'reports/frequency_EF_measurement_2026-10-05.md'
    assert not report.exists()
    text=f'''# EF Windows 原生课程综合结果

EF 完整组合完成一次课程综合/STA：**{measured['fmax_mhz']:.6f} MHz**，最低周期 **{measured['minimum_period_ns']} ns**，含 SRAM 总面积 **{measured['area_um2']:.6f} μm²**。相对 EA，频率 **{comparison['frequency_vs_EA_percent']:+.4f}%**、面积 **{comparison['area_vs_EA_percent']:+.4f}%**。EF 主工作区仍对应本次冻结源；EG/EH 是独立未采用源码备选。

|指标|EF 实测|要求对应|
|---|---:|---|
|频率|{measured['fmax_mhz']:.6f} MHz|超过原 300 MHz 和程序测量前 350 MHz 工作判断值|
|组合面积|{area['combinational_area_um2']:.6f} μm²|课程固定计价|
|时序面积|{area['sequential_area_um2']:.6f} μm²|与 EA 相同；不等于源码声明计数|
|SRAM 面积|{area['sram_area_um2']:.6f} μm²|已计入总面积|
|总面积|{area['area_um2']:.6f} μm²|原基线 {comparison['area_vs_original_percent']:+.4f}%，在 ±10% 内；仍高于 Tier3 的 36,000|
|IPC/功能|未测|IPC 下限 0.882115146585 和 Tier3 1.0985 均未证明；不能沿用 DM1 的 IPC|

## 当前限制路径

只分析课程已生成的五条路径，没有新增 STA，也没有枚举所有端点。端点私有映射名不能直接认定为某个公开字段。

|序号|起点|终点|到达时间 ns|
|---:|---|---|---:|
'''
    text+=''.join(f"|{p['rank']}|`{p['startpoint']}`|`{p['endpoint']}`|{p['arrival_ns']:.4f}|\n" for p in paths['paths'])
    text+='''
第一条的显式层级经过 LSQ report_bound、直接 report grant、RS wake port 5、entry 10 基址 ready、共享 store packet 选择、normal ROB live 查询，末段出现 LSQ mask owner 写控制。关键边界到达：LSQ grant 0.838 ns、RS wake-valid 1.078 ns、共享 probe base-ready 1.319 ns、store packet grant 1.768 ns、normal live 查询 index 1.902 ns、LSQ mask owner 写控制 2.548 ns。可优先让共享探测只读已有注册基址；普通发射旁路不必因此整体延后。EH 较广的快慢通知拆分也能断开这类联系，但对 load/MDU 直接依赖发射有一拍机会代价，暂留备选。

后四条经过 Dcache response_read、响应生命周期/输出选择、LSQ response_query 行号、查询到的 offset、response_extract。第二条的 LSQ 查询 index 在 1.820 ns、row select 在 1.901 ns、offset64 控制在 2.022 ns。最大单门 AOI221xp5 为 0.2913 ns，50 个负载、23.7029 fF；后段另一个 AOI21xp33 为 0.1909 ns、18 个负载。需要分别处理缓存响应选择负载与查询后串行提取，不能只针对第一条改完就宣称全局频率还会提升。

EF 的分配地址删除有实际时序收益，但可能延后 store 地址可用时刻。EG 并行地址备选保留原分配当拍行为；新面积和新频率尚未知。继续做源码结构工作；任何后续测量前先汇报完整组合。当前没有 Verilator CPU 构建、IPC 或功能程序，本次 timing-only 不证明完整正确性。

课程保持 Windows 原生固定 Yosys/ABC/OpenSTA、ASAP7 RVT TT/FakeRAM、2 ns 请求映射时钟、0.05 ns uncertainty、5 fF 输出负载、reset=0、无寄生。2 ns 下的负 slack 不代表 300 MHz 失败；以上频率来自原课程周期搜索。未使用 WSL。

## 原始证据

'''
    text+=f"- 测量：`{run/'result/timing_only.json'}`\n- 源码 manifest SHA256：`{measured['source_manifest_sha256']}`\n- 工具 manifest SHA256：`{measured['toolchain_manifest_sha256']}`\n- 官方 report SHA256：`{measured['official_report_sha256']}`\n- 标量摘要：`F:/CPU2026Proofs/EF_existing_reports_20261005/summary.json`\n- 映射路径分析：`F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json`\n"
    report.write_text(text,encoding='utf-8')
    verified=dict(status='CURRENT_SOURCE_COURSE_FMAX_AT_LEAST_300',fmax_mhz=measured['fmax_mhz'],
        source_manifest_sha256=measured['source_manifest_sha256'],report=str(report),
        scope='Course timing only; IPC, correctness and Tier3 are not verified.')
    active.update(measurement_report=str(report),current_timing_result_report=str(report),
        frequency_requirement_verified=verified,last_verified_frequency_requirement=verified,
        completion_audit=dict(observed_at=datetime.now(timezone.utc).isoformat(),frequency_300_met=True,
            area_within_10_percent=True,ipc_within_10_percent=None,tier3_area_met=False,tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='EF reaches 370.48 MHz and original ±10% area; IPC/correctness unmeasured, Tier3 area unmet. Continue source work on shared probe and cache response paths; report before subsequent measurement.'))
    event=dict(candidate=active['candidate'],run=str(run),source_manifest_sha256=measured['source_manifest_sha256'],
        current_measured_fmax_mhz=measured['fmax_mhz'],current_measured_area_um2=measured['area_um2'],
        current_measured_ipc=None,status=active['status'],report=str(report),report_sha256=sha(report),
        timing_only=True,cpu_build_started=False,simulation_started=False,comparison=comparison)
    assert not any(Path(e['run'])==run for e in active.get('timing_only_measurement_history',[]))
    active['last_timing_only_measurement']=event
    active.setdefault('timing_only_measurement_history',[]).append(event)
    active['source_research_decision']='EF timing gained 12.88% versus EA; two different limiting path classes remain. EG/EH unmeasured; examine narrow registered shared probe and cache response routing before further tests.'
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),fmax_mhz=measured['fmax_mhz'],area_um2=measured['area_um2'],
        comparison=comparison,new_tests_started=False,overall_goal_complete=False)))


if __name__=='__main__':
    main()
