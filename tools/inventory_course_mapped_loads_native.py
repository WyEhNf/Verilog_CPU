"""Read mapped JSON/Liberty input loads; no HDL/EDA/simulation invocation."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from summarize_course_frequency_native import cell_caps, read, sha


def input_caps(libraries):
    result={}
    for entry in libraries:
        source=Path(entry['path']).read_text(encoding='utf-8')
        unit=re.search(r'capacitive_load_unit\s*\(\s*([\d.eE+\-]+)\s*,\s*(\w+)\s*\)',source)
        if not unit or unit.group(2).lower() not in {'ff','pf','nf','f'}:
            continue
        scale=float(unit.group(1))*{'ff':1.,'pf':1e3,'nf':1e6,'f':1e15}[unit.group(2).lower()]
        cells=list(re.finditer(r'\bcell\s*\(\s*"?([^"\s)]+)"?\s*\)\s*\{',source))
        for i,cell in enumerate(cells):
            body=source[cell.end():cells[i+1].start() if i+1<len(cells) else len(source)]
            pins=list(re.finditer(r'\bpin\s*\(\s*"?([^"\s)]+)"?\s*\)\s*\{',body))
            for j,pin in enumerate(pins):
                pin_body=body[pin.end():pins[j+1].start() if j+1<len(pins) else len(body)]
                cap=re.search(r'(?<!\w)capacitance\s*:\s*([\d.eE+\-]+)\s*;',pin_body)
                if cap and re.search(r'\bdirection\s*:\s*input\s*;',pin_body):
                    result[cell.group(1),pin.group(1)]=float(cap.group(1))*scale
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Preserve prior inventory: '+str(args.out))
    report_path=args.run/'result/synth/opt/report.json'
    design_path=args.run/'result/synth/opt/design.json'
    report=read(report_path)
    identity=read(args.run/'result/measurement_identity.json')
    if identity['environment']!='WINDOWS_NATIVE' or identity['source_manifest_sha256']!=sha(args.run/'source_manifest.json'):
        raise ValueError('Native source identity mismatch')
    limits=cell_caps(report['libraries'])  # also checks each library identity
    capacities=input_caps(report['libraries'])
    modules=read(design_path)['modules']
    cache={}
    visiting=set()

    def loads(kind):
        if kind in cache:
            return cache[kind]
        if kind in visiting:
            raise ValueError('Unexpected recursive module: '+kind)
        visiting.add(kind)
        values=defaultdict(lambda:[0,0.,0])
        for cell in modules[kind]['cells'].values():
            child=modules.get(cell['type'])
            normal=bool(child and child.get('cells'))
            child_loads=loads(cell['type']) if normal else None
            for port,bits in cell['connections'].items():
                if cell['port_directions'][port]!='input':
                    continue
                for index,bit in enumerate(bits):
                    if not isinstance(bit,int):
                        continue
                    if normal:
                        inner=child['ports'][port]['bits'][index]
                        value=child_loads.get(inner,[0,0.,0])
                    else:
                        name=port if len(bits)==1 else f'{port}[{index}]'
                        cap=capacities.get((cell['type'],name))
                        value=[1,cap if cap is not None else 0.,int(cap is None)]
                    target=values[bit]
                    for i in range(3):
                        target[i]+=value[i]
        visiting.remove(kind)
        cache[kind]=dict(values)
        return cache[kind]

    top=modules['student_top']
    top_loads=loads('student_top')
    # These are the course's actual top-output loads; clock stays ideal.
    for port in top['ports'].values():
        if port['direction']=='output':
            for bit in port['bits']:
                if isinstance(bit,int):
                    value=top_loads.setdefault(bit,[0,0.,0])
                    value[0]+=1
                    value[1]+=report['timing']['output_load_ff']
    aliases=defaultdict(list)
    for name,net in top['netnames'].items():
        if net.get('hide_name'):
            continue
        for index,bit in enumerate(net['bits']):
            if isinstance(bit,int):
                aliases[bit].append(name+(f'[{index+net.get("offset",0)}]' if len(net['bits'])>1 else ''))
    records=[]
    for name,cell in top['cells'].items():
        for port,bits in cell['connections'].items():
            if cell['port_directions'][port]!='output':
                continue
            for index,bit in enumerate(bits):
                if not isinstance(bit,int) or bit not in top_loads:
                    continue
                count,cap,unknown=top_loads[bit]
                maximum=limits.get((cell['type'],port))
                records.append(dict(driver=name,cell=cell['type'],port=port,bit=bit,
                    known_cap_ff=cap,input_pin_count=count,unknown_cap_pins=unknown,
                    max_cap_ff=maximum,known_cap_ratio=(cap/maximum if maximum else None),
                    aliases=sorted(set(aliases[bit]),key=lambda item:(len(item),item))[:12],
                    driver_attributes=cell.get('attributes',{})))
    records.sort(key=lambda item:item['known_cap_ff'],reverse=True)
    selected={item['bit']:item for item in records[:100]}
    for item in selected.values():
        item['immediate_sink_samples']=[]
        item['immediate_sink_type_counts']={}
    for name,cell in top['cells'].items():
        for port,bits in cell['connections'].items():
            if cell['port_directions'][port]!='input':
                continue
            for bit in bits:
                if not isinstance(bit,int) or bit not in selected:
                    continue
                record=selected[bit]
                counts=record['immediate_sink_type_counts']
                counts[cell['type']]=counts.get(cell['type'],0)+1
                if len(record['immediate_sink_samples'])>=20:
                    continue
                output_names=[]
                for out_port,out_bits in cell['connections'].items():
                    if cell['port_directions'][out_port]=='output':
                        for out_bit in out_bits:
                            output_names.extend(aliases.get(out_bit,[])[:2])
                record['immediate_sink_samples'].append(dict(instance=name,cell=cell['type'],port=port,
                    output_aliases=output_names[:8],attributes=cell.get('attributes',{})))
    result=dict(status='EXISTING_MAPPED_LOAD_INVENTORY',analysis_invokes_eda=False,
        source_manifest_sha256=identity['source_manifest_sha256'],
        report_sha256=sha(report_path),design_sha256=sha(design_path),
        scope='Top module driven nets, recursively counted child input-pin loads. Internal owner drivers and pass-through external loads are not a full-net inventory. Sum of explicitly declared nominal capacitance, excluding unknown pins; this is not the directional capacitance used by STA. Unknown pin counts remain explicit.',
        top_count=len(records),drivers=records[:100])
    args.out.mkdir(parents=True)
    (args.out/'loads.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],top_count=result['top_count'],
        first=[{key:item[key] for key in ['cell','known_cap_ff','input_pin_count','unknown_cap_pins','aliases']} for item in records[:8]]),ensure_ascii=False))


if __name__=='__main__':
    main()
