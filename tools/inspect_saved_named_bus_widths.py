"""Read selected public bus bits from an existing mapped JSON; no HDL/EDA."""
import argparse
import hashlib
import json
from pathlib import Path
from census_saved_mapped_fanout import entries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    parser.add_argument('--suffixes',nargs='+',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    assert not args.out.exists()
    selected={}
    for name,item in entries(args.json,'netnames'):
        if any(name.endswith(s) for s in args.suffixes):
            selected[name]=dict(width=len(item['bits']),bits=item['bits'],offset=item.get('offset',0),
                source=item.get('attributes',{}).get('src'))
    with args.json.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    result=dict(status='READ_EXISTING_PUBLIC_BUS_BITS_ONLY',input=str(args.json),input_sha256=digest,
        requested_suffixes=args.suffixes,netnames=selected,no_new_hdl_eda_or_simulation=True)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({name:dict(width=n['width'],bits=n['bits'][:85]) for name,n in selected.items()},indent=2))


if __name__=='__main__':
    main()
