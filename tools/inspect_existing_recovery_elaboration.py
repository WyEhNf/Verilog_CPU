"""Inspect saved elaborated ROB port widths/wiring only; never invoke tools."""
import argparse
import hashlib
import json
from pathlib import Path


def selected_entries(path):
    module=section=name=None
    keep=False
    block=[]
    wanted_cells={'recovery_query_tree','recovery_saved_owner'}
    wanted_nets={'chosen_age','chosen_slot','head_recovery_index','occupancy_reg',
        'recovery_preview_kill','recovery_preview_domains','recovery_saved_payload'}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('    "') and line.rstrip().endswith(': {'):
                module=json.loads(line.strip().rsplit(': {',1)[0])
                section=None
            if module is None or not module.endswith('\\rv32_rob'):
                continue
            if line.startswith('      "cells": {'):
                section='cells'
            elif line.startswith('      "netnames": {'):
                section='netnames'
            elif line.startswith('      }'):
                section=None
            if section not in ('cells','netnames'):
                continue
            if line.startswith('        "'):
                name=json.loads(line.strip().rsplit(': {',1)[0])
                keep=name in (wanted_cells if section=='cells' else wanted_nets)
                block=['{\n'] if keep else []
            elif keep:
                if line.startswith('        }'):
                    block.append('}\n')
                    yield module,section,name,json.loads(''.join(block))
                    keep=False
                else:
                    block.append(line)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    assert not args.out.exists()
    records={}
    for module,section,name,data in selected_entries(args.json):
        records.setdefault(module,{'cells':{},'netnames':{}})[section][name]=data
    outcomes=[]
    for module,data in records.items():
        nets=data['netnames']
        cells=data['cells']
        chosen_age=nets['chosen_age']['bits']
        chosen_slot=nets['chosen_slot']['bits']
        head=nets['head_recovery_index']['bits']
        occupancy=nets['occupancy_reg']['bits']
        preview=nets['recovery_preview_domains']['bits']
        kill=nets['recovery_preview_kill']['bits']
        slot_width=len(head)
        count_width=len(occupancy)
        query=cells['recovery_query_tree']['connections']['signal_i']
        saved=cells['recovery_saved_owner']['connections']['data_i']
        expected_query=occupancy+chosen_age[:count_width]+head+[preview[2]]
        expected_saved=kill+chosen_age[:slot_width]+chosen_slot[:slot_width]
        outcomes.append(dict(module=module,slot_width=slot_width,count_width=count_width,
            query_width=len(query),expected_query_width=len(expected_query),
            actual_query_bits=query,expected_query_bits=expected_query,
            query_all_fields_connected_exactly=(query==expected_query),
            saved_width=len(saved),expected_saved_width=len(expected_saved),
            actual_saved_bits=saved,expected_saved_bits=expected_saved,
            saved_all_fields_connected_exactly=(saved==expected_saved)))
    with args.json.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    proof=dict(status='EXISTING_ELABORATED_RECOVERY_PORT_WIRING',input=str(args.json),
        input_sha256=digest,no_new_hdl_eda_or_program_run=True,records=outcomes,
        all_selected_fields_connected_exactly=bool(outcomes) and all(
            o['query_all_fields_connected_exactly'] and o['saved_all_fields_connected_exactly'] for o in outcomes),
        caveat='Exact saved port-bit correspondence only, not a full branch-recovery correctness proof.')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(proof=str(args.out),all_selected_fields_connected_exactly=proof['all_selected_fields_connected_exactly'],
        modules=[{k:v for k,v in o.items() if not k.endswith('_bits')} for o in outcomes]),indent=2))


if __name__=='__main__':
    main()
