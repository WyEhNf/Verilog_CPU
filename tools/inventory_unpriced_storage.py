"""Expand unpriced storage instances; no ideal-density or zero-cost pricing."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def inventory(manifest, logic):
    rows = []
    names = set()
    for item in manifest['memories']:
        name = item['instance']
        if name in names:
            raise ValueError('duplicate storage instance: ' + name)
        names.add(name)
        params = item['parameters']
        shape = {key.lower(): int(params[key], 2)
                 for key in ('WIDTH', 'SIZE', 'RD_PORTS', 'WR_PORTS')}
        if shape['width'] <= 0 or shape['size'] <= 0:
            raise ValueError('invalid storage geometry')
        rows.append(dict(instance=name, **shape,
                         bits=shape['width'] * shape['size'],
                         classification=('read_only_requires_rom_or_logic_mapping'
                                         if shape['wr_ports'] == 0 else
                                         'writable_requires_legal_physical_binding'),
                         physical_macro=None, area_um2=None))
    count = len(rows)
    if count != manifest['memory_boundaries'] or count != logic['unpriced_leaves']:
        raise ValueError('inventory and logic audit boundary counts disagree')
    combo = Decimal(str(logic['combinational_standard_cell_area_um2']))
    seq = Decimal(str(logic['sequential_standard_cell_area_um2']))
    known = Decimal(str(logic['known_timed_standard_cell_area_um2']))
    if combo + seq != known:
        raise ValueError('standard cell components do not sum')
    ports = Counter((r['rd_ports'], r['wr_ports']) for r in rows)
    return dict(status='INCOMPLETE' if rows else 'COMPLETE',
                known_standard_cell_area_um2=float(known),
                combinational_standard_cell_area_um2=float(combo),
                sequential_standard_cell_area_um2=float(seq),
                external_ram_included=False,
                logical_storage_instances=count,
                logical_storage_bits=sum(r['bits'] for r in rows),
                read_only_instances=sum(r['wr_ports'] == 0 for r in rows),
                read_only_bits=sum(r['bits'] for r in rows if r['wr_ports'] == 0),
                port_histogram=[dict(rd_ports=rd, wr_ports=wr, instances=n)
                                for (rd, wr), n in sorted(ports.items())],
                sram_area_um2=None if rows else 0,
                total_area_um2=None if rows else float(known),
                tier3_remaining_budget_um2=float(Decimal(36000) - known),
                note='Logical arrays are not physical macros. ROM/logic mapping, '
                     'SRAM bindings, adapters and an accepted FakeRAM model '
                     'are required before total pricing.',
                entries=sorted(rows, key=lambda row: (-row['bits'], row['instance'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('logic_audit', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    logic_bytes = args.logic_audit.read_bytes()
    result = inventory(json.loads(manifest_bytes), json.loads(logic_bytes))
    result['inputs'] = {str(path): hashlib.sha256(data).hexdigest()
                        for path, data in ((args.manifest, manifest_bytes),
                                           (args.logic_audit, logic_bytes))}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'entries'}, indent=2))
    for row in result['entries'][:12]:
        print(f"{row['instance']}: {row['size']}x{row['width']} "
              f"{row['rd_ports']}R{row['wr_ports']}W ({row['bits']} bits)")


if __name__ == '__main__':
    main()
