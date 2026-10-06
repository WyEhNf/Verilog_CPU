"""Read existing reports/netlists only; never invoke simulation or EDA tools."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('F:/CPU2026CourseRuns/current_adopted_20261003/result/synth/opt')
OUT = Path('E:/Verilog_cpu/reports/frequency_research_20261003')


def main():
    checks = json.loads((ROOT / 'critical_paths.json').read_text())['checks']
    # The JSON formatter rounds to four significant digits; the text report
    # retains the useful 0.0001 ns precision and actual hierarchical fanout.
    precise = {}
    row_pattern = re.compile(r'^\s*(?:(\d+)\s+([\d.]+)\s+)?([\d.]+)\s+([\d.-]+)\s+([\d.-]+)\s+[v^]\s+(\S+)\s+\((\S+)\)')
    for line in (ROOT / 'timing.rpt').read_text().splitlines():
        row = row_pattern.match(line)
        if row:
            if row[1] is not None:
                precise.setdefault(row[6], dict(fanout=int(row[1]), capacitance_ff=float(row[2]),
                                                slew_ns=float(row[3]), delay_ns=float(row[4]),
                                                arrival_ns=float(row[5])))
            else:
                precise.setdefault(row[6], dict(arrival_ns=float(row[5])))
    paths, dominant, wanted = [], {}, set()
    for rank, check in enumerate(checks, 1):
        segments = []
        previous = None
        for point in check['source_path']:
            if previous is not None and previous.get('instance') == point.get('instance'):
                delay = (point['arrival'] - previous['arrival']) * 1e9
                if delay > 0:
                    segment = dict(instance=point['instance'], cell=point['cell'],
                                   net=point.get('net'), delay_ns=delay,
                                   arrival_ns=point['arrival'] * 1e9,
                                   capacitance_ff=point.get('capacitance', 0) * 1e15,
                                   slew_ns=point.get('slew', 0) * 1e9)
                    segment.update(precise.get(point['pin'], {}))
                    segments.append(segment)
                    if delay > dominant.get(point['instance'], {}).get('delay_ns', -1):
                        dominant[point['instance']] = segment
            if point.get('net'):
                wanted.add(point['net'].lstrip('\\'))
            previous = point
        paths.append(dict(rank=rank, startpoint=check['startpoint'], endpoint=check['endpoint'],
                          arrival_ns=precise.get(check['endpoint'], {}).get('arrival_ns', check['source_path'][-1]['arrival'] * 1e9),
                          segments=segments))
    critical_cells = {p['startpoint'].rsplit('/', 1)[0] for p in paths}
    critical_cells |= {p['endpoint'].rsplit('/', 1)[0] for p in paths}
    critical_cells |= set(dominant)
    fanouts, consumers, instances, aliases = Counter(), defaultdict(list), {}, []
    top = False
    cell = None
    with (ROOT / 'mapped.v').open(encoding='utf-8') as source:
        for line in source:
            if line.startswith('module '):
                top = bool(re.match(r'^module\s+student_top[\s(]', line))
            if not top:
                continue
            match = re.match(r'^  (\S+) (\S+) \($', line.rstrip())
            if match:
                cell = dict(type=match[1].lstrip('\\'), name=match[2].lstrip('\\'), ports={})
                continue
            if cell:
                port = re.match(r'^    \.(\w+)\((.*?)\)[,]?\s*$', line.rstrip())
                if port:
                    cell['ports'][port[1]] = port[2].strip().lstrip('\\')
                if line.strip() == ');':
                    if cell['name'] in critical_cells:
                        instances[cell['name']] = cell
                    for port, value in cell['ports'].items():
                        if port in ('Y', 'Q', 'QN'):
                            continue
                        if value in wanted:
                            fanouts[value] += 1
                            if len(consumers[value]) < 24:
                                consumers[value].append(dict(instance=cell['name'], type=cell['type'], port=port))
                    cell = None
                continue
            if line.startswith('  assign '):
                names = set(re.findall(r'(?<!\w)_\d+_(?!\w)', line))
                if names & wanted and ('core.' in line or '_003871_' in line or '_026479_' in line):
                    aliases.append(line.strip())
    for entry in dominant.values():
        entry['root_direct_load_pins'] = fanouts[entry['net'].lstrip('\\')]
        entry['consumer_sample'] = consumers[entry['net'].lstrip('\\')]
    summary = dict(input_reports_only=True, no_tools_or_tests_run=True,
                   input_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ('critical_paths.json', 'mapped.v')},
                   reported_paths=len(paths), paths=paths,
                   dominant_segments=sorted(dominant.values(), key=lambda x: x['delay_ns'], reverse=True),
                   relevant_instances=instances, aliases=aliases,
                   caution='Only the paths already reported by the course run are covered; root direct pin counts exclude internal loads behind preserved hierarchy.')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'saved_path_analysis.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(reported_paths=len(paths),
                          paths=[{k: v for k, v in p.items() if k != 'segments'} for p in paths],
                          dominant_segments=[{k: v for k, v in s.items() if k != 'consumer_sample'} for s in summary['dominant_segments'][:10]],
                          endpoint_registers={k: v for k, v in instances.items() if k in critical_cells and v['type'].startswith('DFF')},
                          aliases=aliases[:12]), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
