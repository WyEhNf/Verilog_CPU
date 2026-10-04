"""Read the existing DT mapped JSON, one entry at a time; run no EDA."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path('F:/CPU2026CourseRuns/architecture_DT_20261005/result/synth/opt')
OUT = Path('F:/CPU2026Proofs/DT_request_net_20261005')


def entries(section):
    top = active = False
    name = None
    block = []
    with (ROOT / 'design.json').open(encoding='utf-8') as stream:
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
    target_names = {'_093964_', '_093963_', '_093950_', '_093948_',
                    '_093869_', '_092667_', '_006324_'}
    target_bits = {}
    for name, data in entries('netnames'):
        if name in target_names or ('bus.enabled_words$func$' in name):
            target_bits[name] = data['bits']
    # mapped.v renumbers private wires. Its public enabled_words result bit
    # survives in design.json; follow its INV input to find the 220-load net.
    alias = next(n for n in target_bits if 'bus.enabled_words$func$' in n)
    result_bit = target_bits[alias][0]
    bit = None
    for name, data in entries('cells'):
        if data['type'] == 'INVx1_ASAP7_75t_R' and data['connections'].get('Y') == [result_bit]:
            bit = data['connections']['A'][0]
            break
    if bit is None:
        raise ValueError('No mapped inverter driving the named result')
    target_bits['mapped_NAND5_output'] = [bit]
    target_bits['mapped_INV_output'] = [result_bit]
    consumers, source = [], None
    output_bits = set()
    for name, data in entries('cells'):
        ports = data.get('connections', {})
        directions = data.get('port_directions', {})
        if any(bit in values and directions.get(port) == 'input'
               for port, values in ports.items()):
            consumers.append({'instance': name, **data})
            for port, values in ports.items():
                if directions.get(port) == 'output':
                    output_bits.update(values)
        if any(bit in values and directions.get(port) == 'output'
               for port, values in ports.items()):
            source = {'instance': name, **data}
    wanted = set(output_bits)
    wanted.update(b for values in target_bits.values() for b in values)
    aliases = []
    for name, data in entries('netnames'):
        hit = [(i, b) for i, b in enumerate(data['bits']) if b in wanted]
        if hit and not name.startswith('_'):
            aliases.append({'name': name, 'matched_bit_positions': hit,
                            'attributes': data.get('attributes', {})})
    OUT.mkdir(parents=True, exist_ok=False)
    result = dict(existing_reports_only=True, no_tests_run=True,
                  target_bits=target_bits, source=source,
                  consumer_count=len(consumers), consumers=consumers, aliases=aliases)
    (OUT / 'net_trace.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'consumer_count': len(consumers),
                      'consumer_types': Counter(c['type'] for c in consumers),
                      'named_aliases': aliases}, indent=2))


if __name__ == '__main__':
    main()
