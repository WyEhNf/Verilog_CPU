"""Inspect existing mapped recovery input wiring after width warnings; no EDA."""
import argparse
import hashlib
import json
from pathlib import Path
from census_saved_mapped_fanout import entries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    assert not args.out.exists()
    prefix='core.g_ooo_backend.backend.rob.'
    names={}
    for name,net in entries(args.json,'netnames'):
        if name.startswith(prefix) and any(x in name for x in (
            'chosen_age','chosen_slot','head_reg','occupancy','apply_slot','apply_age',
            'recovery_saved','recovery_preview','recovery_query','recovery_row_preview')):
            names[name]=dict(bits=net['bits'],offset=net.get('offset',0))
    roots={}
    for name,cell in entries(args.json,'cells'):
        if name.startswith(prefix) and name.endswith('.invert_root') and any(x in name for x in (
            'recovery_query_tree.g_driver[','recovery_preview_tree.g_driver[')):
            roots[name]=dict(type=cell['type'],connections=cell['connections'])
    with args.json.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    data=dict(status='SAVED_RECOVERY_CAST_WIRING_ONLY',input=str(args.json),input_sha256=digest,
        no_new_hdl_eda_or_program_run=True,selected_netnames=names,selected_cells=roots)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(roots=roots,other_net_samples={n:v for n,v in names.items()
        if any(n.endswith(x) for x in ('chosen_age','chosen_slot','apply_slot','apply_age','head_reg','occupancy_reg'))},
        selected_net_count=len(names)),indent=2))


if __name__=='__main__':
    main()
