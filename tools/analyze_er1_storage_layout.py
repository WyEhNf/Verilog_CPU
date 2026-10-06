"""Inspect existing elaboration storage layout; no synthesis or simulation."""
from collections import defaultdict
import json
from pathlib import Path
from manage_frozen_baseline_programs import sha, write

RUN=Path('F:/CPU2026CourseRuns/architecture_ER1_20261005')
OUT=Path('F:/CPU2026Proofs/ER1_storage_layout_v2_20261005.json')


def main():
    assert not OUT.exists()
    path=RUN/'result/synth/opt/elaborated.json'
    modules=json.loads(path.read_text())['modules']
    rows=[]
    def visit(kind, location):
        module=modules[kind]
        if module.get('attributes',{}).get('hdlname')=='rv32_frequency_word_bank':
            rows.append(dict(instance=location, bits=len(module['ports']['data_o']['bits'])))
            return
        for name,cell in module.get('cells',{}).items():
            child=cell['type']
            if child in modules and not int(modules[child].get('attributes',{}).get('blackbox','0'),2):
                visit(child,location+'/'+name)
    visit('student_top','student_top')
    grouped=defaultdict(lambda:dict(instances=0,bits=0,samples=[]))
    for row in rows:
        name=row['instance']
        # Collapse physical row numbers while retaining field ownership.
        import re
        group=re.sub(r'\[\d+\]', '[*]', name)
        entry=grouped[group]
        entry['instances']+=1; entry['bits']+=row['bits']
        if len(entry['samples'])<2:entry['samples'].append(name)
    result=dict(status='EXISTING_ELABORATION_STORAGE_LAYOUT', run=str(RUN),
                elaboration_sha256=sha(path),source_manifest_sha256=sha(RUN/'source_manifest.json'),
                word_bank_declared_bits=sum(r['bits'] for r in rows),
                word_bank_instances=len(rows),
                groups=[dict(instance_pattern=k,**v) for k,v in sorted(grouped.items(),key=lambda kv:kv[1]['bits'],reverse=True)],
                limitation='Declared elaborated bits; mapping may prune constant or unused bits. Not area attribution or a candidate measurement.',
                supersedes_invalid_module_name_scan=str(OUT.with_name('ER1_storage_layout_20261005.json')),
                new_synthesis_run=False,new_simulation_run=False)
    write(OUT,result)
    print(json.dumps(dict(total_bits=result['word_bank_declared_bits'],groups=result['groups'][:18])))


if __name__=='__main__':main()
