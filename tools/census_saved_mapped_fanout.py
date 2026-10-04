"""Count saved mapped input-pin loads; do not invoke any HDL/EDA tool."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def entries(path, section):
    top = active = False
    name = None
    block = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('    "student_top": {'):
                top = True
            elif top and line.startswith('    }'):
                return
            if not top:
                continue
            if line.startswith('      "' + section + '": {'):
                active = True
                continue
            if not active:
                continue
            if line.startswith('      }'):
                return
            if line.startswith('        "'):
                name = json.loads(line.strip().rsplit(': {', 1)[0])
                block = ['{\n']
            elif name is not None:
                if line.startswith('        }'):
                    block.append('}\n')
                    yield name, json.loads(''.join(block))
                    name = None
                else:
                    block.append(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    fanout = Counter()
    drivers = {}
    cells = 0
    types = Counter()
    for name, cell in entries(args.json, 'cells'):
        cells += 1
        types[cell['type']] += 1
        for port, values in cell.get('connections',{}).items():
            if cell['port_directions'].get(port) == 'input':
                fanout.update(bit for bit in values if isinstance(bit,int))
            elif cell['port_directions'].get(port) == 'output':
                for bit in values:
                    if isinstance(bit,int):
                        drivers[bit] = dict(instance=name,type=cell['type'],port=port)
    ranked = sorted((dict(bit=bit,input_pin_loads=loads,driver=drivers[bit])
                     for bit,loads in fanout.items() if bit in drivers and loads>=32),
                    key=lambda row:row['input_pin_loads'],reverse=True)
    wanted = {row['bit'] for row in ranked[:250]}
    aliases = defaultdict(list)
    for name, entry in entries(args.json,'netnames'):
        if name.startswith(('$abc$', '$auto$')):
            continue
        for pos, bit in enumerate(entry['bits']):
            if bit in wanted:
                aliases[bit].append(dict(name=name,position=pos,
                    source=entry.get('attributes',{}).get('src')))
    rows = [{**row,'aliases':aliases[row['bit']]} for row in ranked[:250]]
    wanted = {row['bit'] for row in rows}
    consumer_counts = {bit:Counter() for bit in wanted}
    consumer_samples = defaultdict(list)
    for name, cell in entries(args.json,'cells'):
        for port, values in cell.get('connections',{}).items():
            if cell['port_directions'].get(port) != 'input':
                continue
            for bit in values:
                if bit in wanted:
                    consumer_counts[bit][cell['type']] += 1
                    if len(consumer_samples[bit])<6:
                        consumer_samples[bit].append(dict(instance=name,type=cell['type'],port=port))
    for row in rows:
        row['consumer_types']=consumer_counts[row['bit']]
        row['consumer_samples']=consumer_samples[row['bit']]
    with args.json.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    result=dict(status='SAVED_MAPPED_LOAD_CENSUS_ONLY',input=str(args.json),input_sha256=digest,
                no_hdl_eda_or_program_run=True,top_level_cells=cells,cell_types=types,
                driven_bits_with_32_or_more_input_pin_loads=len(ranked),ranked_loads=rows,
                limitations='Counts direct student_top input-pin connections in the existing mapped JSON. Kept module ports may represent hierarchical loads. No new timing, cell capacitance, all-endpoint path report or DY frequency/area result.')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    assert not args.out.exists()
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],cells=cells,over_32=len(ranked),
        top=[dict(input_pin_loads=r['input_pin_loads'],driver_type=r['driver']['type'],
                  aliases=r['aliases'][:2]) for r in rows[:18]]),indent=2))


if __name__=='__main__':main()
