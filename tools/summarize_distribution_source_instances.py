"""Read an existing elaborated JSON for source-instance counts, not PPA proof."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    with args.json.open(encoding='utf-8') as f:
        modules=json.load(f)['modules']
    @lru_cache(None)
    def collect(name):
        m=modules[name]
        if m.get('attributes',{}).get('hdlname')=='rv32_frequency_control_tree':
            v=m['parameter_default_values']
            return Counter({(int(v['WIDTH'],2),int(v['LEAVES'],2)):1})
        result=Counter()
        for c in m.get('cells',{}).values():
            if c['type'] in modules:
                result.update(collect(c['type']))
        return result
    @lru_cache(None)
    def internal_nodes(leaves):
        if leaves==1:
            return 0
        children=min(4,leaves)
        q,r=divmod(leaves,children)
        return 1+sum(internal_nodes(q+(child<r)) for child in range(children))
    census=collect('student_top')
    old=new=roots=0
    rows=[]
    for (width,leaves),count in sorted(census.items()):
        inner=internal_nodes(leaves)
        old_each=2*(inner+leaves)*width
        new_each=(2 if leaves==1 else 2*inner+leaves-1)*width
        old+=count*old_each
        new+=count*new_each
        roots+=count
        rows.append({'width':width,'leaves':leaves,'root_instances':count,
                     'original_source_inversions':count*old_each,
                     'proposed_source_inversions':count*new_each,'source_instances_saved':count*(old_each-new_each)})
    with args.json.open('rb') as f:
        digest=hashlib.file_digest(f,'sha256').hexdigest()
    data={'status':'EXISTING_ELABORATION_SOURCE_INSTANCE_CENSUS_ONLY',
        'input':str(args.json),'input_sha256':digest,'no_eda_or_hdl_run':True,
        'root_control_tree_instances':roots,'distinct_parameter_pairs':len(census),
        'original_source_inversion_instances':old,'proposed_source_inversion_instances':new,
        'source_inversion_instances_saved':old-new,'source_inversion_saving_percent':100*(old-new)/old,
        'rows':rows,
        'limitation':'Counts elaborated RTL instances before constant/dead-logic pruning and mapping. Not a measured cell count, area, delay or frequency prediction. Topology/source algebra only.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k!='rows'}))


if __name__=='__main__':main()
