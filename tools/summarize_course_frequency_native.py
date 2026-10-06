"""Read existing native course reports; never invoke HDL/EDA/simulation tools."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def cell_caps(libraries):
    """Read explicitly declared output-pin limits, with Liberty units."""
    limits={}
    for entry in libraries:
        path=Path(entry['path'])
        if sha(path)!=entry['sha256']:
            raise ValueError('Reported library changed: '+str(path))
        source=path.read_text(encoding='utf-8')
        unit=re.search(r'capacitive_load_unit\s*\(\s*([\d.eE+\-]+)\s*,\s*(\w+)\s*\)',source)
        if not unit or unit.group(2).lower() not in {'ff','pf','nf','f'}:
            continue
        scale=float(unit.group(1))*{'ff':1.0,'pf':1e3,'nf':1e6,'f':1e15}[unit.group(2).lower()]
        cells=list(re.finditer(r'\bcell\s*\(\s*"?([^"\s)]+)"?\s*\)\s*\{',source))
        for index,cell in enumerate(cells):
            stop=cells[index+1].start() if index+1<len(cells) else len(source)
            body=source[cell.end():stop]
            pins=list(re.finditer(r'\bpin\s*\(\s*"?([^"\s)]+)"?\s*\)\s*\{',body))
            for pin_index,pin in enumerate(pins):
                pin_stop=pins[pin_index+1].start() if pin_index+1<len(pins) else len(body)
                pin_body=body[pin.end():pin_stop]
                cap=re.search(r'\bmax_capacitance\s*:\s*([\d.eE+\-]+)\s*;',pin_body)
                if cap and re.search(r'\bdirection\s*:\s*output\s*;',pin_body):
                    limits[cell.group(1),pin.group(1)]=float(cap.group(1))*scale
    return limits


def path_record(check,limits):
    gates=[]
    points=check.get('source_path',[])
    for prior,point in zip(points,points[1:]):
        if prior.get('instance')!=point.get('instance') or 'capacitance' not in point:
            continue
        delay=(point['arrival']-prior['arrival'])*1e9
        if delay<=0:
            continue
        pin=point['pin'].rsplit('/',1)[-1]
        cap=point['capacitance']*1e15
        limit=limits.get((point['cell'],pin))
        gates.append(dict(cell=point['cell'],pin=point['pin'],net=point.get('net'),
            delay_ns=delay,cap_ff=cap,max_cap_ff=limit,
            cap_ratio=cap/limit if limit and limit>0 else None,
            input_slew_ns=prior.get('slew',0)*1e9,output_slew_ns=point.get('slew',0)*1e9))
    gates.sort(key=lambda gate:gate['delay_ns'],reverse=True)
    overloads=[gate for gate in gates if gate['cap_ratio'] is not None and gate['cap_ratio']>1]
    total_gate_delay=sum(gate['delay_ns'] for gate in gates)
    worst=gates[0] if gates else None
    if overloads:
        recommendation='优先减少超载门最终消费者，局部化有效/选择条件或缩小数据组；不得只在上游加分发后又合并成宽控制。'
    elif worst and ('sram' in worst['cell'].lower() or 'ram' in worst['cell'].lower()):
        recommendation='先核对 SRAM clock/data 边界及宏读延迟，再移动既有寄存边界；保持课程宏和接口约束。'
    else:
        recommendation='结合实际 net/源别名定位串行查询、比较、排序、算术或 mux 链，优先并行预计算；不能单凭门名认定根因。'
    return dict(startpoint=check['startpoint'],endpoint=check['endpoint'],
        arrival_ns=check['data_arrival_time']*1e9,
        required_at_requested_clock_ns=check['required_time']*1e9,
        slack_at_requested_clock_ns=check['slack']*1e9,
        source_clock_edge=check.get('source_clock_edge'),target_clock_edge=check.get('target_clock_edge'),
        measured_gate_delay_ns=total_gate_delay,
        largest_gate_fraction=(worst['delay_ns']/total_gate_delay if total_gate_delay else None),
        slowest_gates=gates[:8],overloaded_gates=overloads,
        overload_count=len(overloads),recommendation=recommendation)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    run=args.run.resolve()
    report_path=run/'result/synth/opt/report.json'
    paths_path=run/'result/synth/opt/critical_paths.json'
    if not report_path.is_file() or not paths_path.is_file():
        raise SystemExit('WAITING_FOR_EXISTING_COURSE_REPORT; no EDA started')
    manifest_path=run/'source_manifest.json'
    identity=read(run/'result/measurement_identity.json')
    if identity['environment']!='WINDOWS_NATIVE' or identity['source_manifest_sha256']!=sha(manifest_path):
        raise ValueError('Native measurement/source identity mismatch')
    config=read(run/'course_windows_config.json')
    tool_manifest=Path(config['tools_root'])/'toolchain_manifest.json'
    if identity['toolchain_manifest_sha256']!=sha(tool_manifest):
        raise ValueError('Pinned toolchain identity changed')
    manifest=read(manifest_path)
    source=Path(manifest['source_root'])
    for name,expected in manifest['snapshot_sha256'].items():
        if sha(source/name)!=expected:
            raise ValueError('Frozen input changed: '+name)
    report=read(report_path)
    for entry in report['inputs']:
        if sha(entry['path'])!=entry['sha256']:
            raise ValueError('Synthesis input changed: '+entry['path'])
    limits=cell_caps(report['libraries'])
    paths=[path_record(check,limits) for check in read(paths_path)['checks']]
    paths.sort(key=lambda item:item['arrival_ns'],reverse=True)
    timing={k:v for k,v in report['timing'].items() if k!='critical_paths'}
    frequency=timing['estimated_fmax_mhz']
    if not frequency or not math.isfinite(frequency):
        raise ValueError('No finite official frequency')
    baseline=read(Path('F:/CPU2026CourseRuns/current_adopted_20261003/result/result.json'))
    ipc_path=run/'result/ipc.json'
    ipc=read(ipc_path) if ipc_path.is_file() else None
    if ipc and (ipc['status']!='COMPLETE' or ipc['latency']!=10 or len(ipc['results'])!=6):
        raise ValueError('Incomplete or incompatible IPC report')
    result_path=run/'result/result.json'
    combined=read(result_path) if result_path.is_file() else None
    result=dict(status='EXISTING_REPORT_SUMMARIZED',run=str(run),source_manifest_sha256=sha(manifest_path),
        report_sha256=sha(report_path),critical_paths_sha256=sha(paths_path),timing=timing,
        area={k:report['area'][k] for k in ['area_um2','logic_area_um2','sequential_area_um2','combinational_area_um2','sram_area_um2']},
        fmax_change_percent=(frequency/baseline['fmax_mhz']-1)*100,
        area_change_percent=(report['area']['area_um2']/baseline['area_um2']-1)*100,
        area_within_10_percent=(abs(report['area']['area_um2']/baseline['area_um2']-1)<=0.1),
        frequency_300_met=(frequency>=300),ipc=(ipc['geomean_ipc'] if ipc else None),
        ipc_change_percent=((ipc['geomean_ipc']/baseline['ipc']-1)*100 if ipc else None),
        ipc_within_10_percent=(abs(ipc['geomean_ipc']/baseline['ipc']-1)<=0.1 if ipc else None),
        tier3_area_met=(report['area']['area_um2']<=36000),
        tier3_ipc_met=(ipc['geomean_ipc']>=1.0985 if ipc else None),
        overall_result_present=bool(combined),official_correctness_suite_passed=(combined.get('official_correctness_suite_passed') if combined else None),
        path_scope='Only paths already published by the official course flow; not an all-endpoint inventory',
        paths=paths,analysis_invokes_eda=False)
    if args.out.exists():
        raise FileExistsError('Preserve existing analysis output: '+str(args.out))
    args.out.mkdir(parents=True)
    (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=['# 现成课程报告：频率、面积与最慢路径','',
        f'冻结批次：[{run.name}]({run.as_posix()}/source_manifest.json)。仅解析已有报告，没有调用 HDL、综合、STA 或仿真工具。','',
        f'官方 Fmax **{frequency:.6f} MHz**，最小周期 **{timing["minimum_period_ns"]:.6f} ns**；300 MHz 门槛：{"已满足" if frequency>=300 else "未满足"}。',
        f'总面积 **{result["area"]["area_um2"]:.3f} µm²**，含 SRAM **{result["area"]["sram_area_um2"]:.3f} µm²**。',
        (f'IPC **{result["ipc"]:.9f}**。' if ipc else 'IPC 尚无完整结果。'),'',
        f'下列 {len(paths)} 条是原课程已经导出的关键路径，按数据到达时间降序；不是全部端点清单。slack 对应请求周期 {timing["clock_period_ns"]} ns，不能直接把负值等同于低于 300 MHz。',
        '数据到达时间含 clock-to-Q 或输入预算；最终 Fmax 以原课程对 setup、clock pulse/period 的最小周期搜索为准。','',
        '| # | 起点 → 终点 | 到达 ns | 最大单门延迟 ns | 该门 net | 该门输出电容/明确上限 fF | 建议 |',
        '|---|---|---:|---:|---|---|---|']
    for rank,path in enumerate(paths,1):
        gate=path['slowest_gates'][0] if path['slowest_gates'] else None
        delay=f'{gate["delay_ns"]:.4f}' if gate else '—'
        cap=(f'{gate["cap_ff"]:.3f}/'+(f'{gate["max_cap_ff"]:.3f}' if gate['max_cap_ff'] is not None else '未给出')) if gate else '—'
        net=str(gate['net'] or gate['pin']).replace('|','&#124;') if gate else '—'
        text.append(f'| {rank} | `{path["startpoint"]}` → `{path["endpoint"]}` | {path["arrival_ns"]:.4f} | {delay} | `{net}` | {cap} | {path["recommendation"]} |')
    text+=['','没有总体结果时，不把局部综合成功当成正确性/IPC/Tier3 通过。JSON 中保留门、net、电容和 slew；建议是基于这些数据的待验证推断。','']
    (args.out/'summary.md').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','frequency_300_met','fmax_change_percent','area_change_percent','ipc','overall_result_present']},ensure_ascii=False))


if __name__=='__main__':
    main()
