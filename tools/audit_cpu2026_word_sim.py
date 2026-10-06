#!/usr/bin/env python3
"""Prove two-state helper equivalence; preserve the structural synthesis body."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def structural(text):
    """Strip only the added, nonnested CPU2026_WORD_SIM branches."""
    text = re.sub(r'// Equivalent two-state word form for the cycle-accurate simulator\.\n'
                  r'// Synthesis retains the original fanout/carry/ownership structure\.\n', '', text)
    text = re.sub(r'`ifdef CPU2026_WORD_SIM\n.*?`else\n(.*?)`endif\n',
                  lambda m: m[1], text, flags=re.S)
    return re.sub(r'`ifndef CPU2026_WORD_SIM\n(.*?)`endif\n',lambda m:m[1],text,flags=re.S)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('outdir', type=Path)
    ap.add_argument('--only', default='')
    ap.add_argument('--case-index',type=int)
    ap.add_argument('--source-only',action='store_true',
                    help='Check original synthesis bodies without running formal jobs')
    a = ap.parse_args()
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sources = [ROOT/'rtl/common/rv32_asap7_fanout.v',
               ROOT/'rtl/backend/rv32_rat_recovery.v',ROOT/'rtl/cache/rv32_dcache_control_banks.v']
    baseline = [out/'fanout_structural.v', out/'rat_structural.v',out/'cache_banks_structural.v']
    for current, old in zip(sources, baseline):
        assert structural(current.read_text()) == old.read_text(), current
    assert structural((ROOT/'rtl/backend/rv32_lsq.v').read_text()) == (out/'lsq_structural.v').read_text()
    if a.source_only:
        print(json.dumps({'structural_bodies_identical':True,'cpu_simulation_run':False,
                          'formal_jobs_run':False}))
        return 0
    gold = '\n'.join(p.read_text() for p in baseline)
    gate = '\n'.join(p.read_text() for p in sources)
    modules = re.findall(r'\bmodule\s+(\w+)', gold)
    def rename(text, suffix):
        return re.sub(r'\b('+ '|'.join(map(re.escape,modules))+r')\b',
                      lambda m: m[1]+suffix, text)
    (out/'gold.v').write_text(rename(gold,'_gold'),newline='\n')
    (out/'gate.v').write_text(rename(gate,'_gate'),newline='\n')
    cases = [
        ('rv32_frequency_negative_subtree',{'WIDTH':17,'LEAVES':5}),
        ('rv32_frequency_control_tree',{'WIDTH':32,'LEAVES':17}),
        ('rv32_frequency_word_bank',{'WIDTH':151}),
        ('rv32_frequency_event_select',{'WIDTH':37,'EVENTS':5,'PRIORITY':0}),
        ('rv32_frequency_event_select',{'WIDTH':37,'EVENTS':5,'PRIORITY':1}),
        ('rv32_frequency_first_two',{'ENTRIES':8}),
        ('rv32_frequency_array_read',{'WIDTH':37,'ENTRIES':7}),
        ('rv32_frequency_narrow_array_read',{'WIDTH':3,'ENTRIES':56}),
        ('rv32_frequency_array_read_bank_masks',{'WIDTH':9,'ENTRIES':56}),
        ('rv32_frequency_barrel32',{}),
        ('rv32_frequency_line_extract32',{}),
        ('rv32_frequency_line_insert32',{}),
        ('rv32_frequency_add32_select',{}),
        ('rv32_frequency_add64_select',{}),
        ('rv32_frequency_add_simm12',{'CLASS_COMPARE':0}),
        ('rv32_frequency_add_simm12',{'CLASS_COMPARE':1}),
        ('rv32_rat_recovery',{'ROB_ENTRIES':32,'PAW':6,'IMPL':1,'SUFFIX_KEEPS_BRANCH_MAPPING':1}),
        ('rv32_dcache_metadata_bank',{'GROUP_ID':0,'LOCAL_QUERY':1,'LOCAL_ACTION_DECODE':1}),
        ('rv32_dcache_metadata_bank',{'GROUP_ID':63,'LOCAL_QUERY':1,'LOCAL_ACTION_DECODE':1}),
        ('rv32_dcache_metadata_bank',{'GROUP_ID':0,'LOCAL_QUERY':0,'LOCAL_ACTION_DECODE':0}),
        ('rv32_rat_recovery',{'ROB_ENTRIES':32,'PAW':6,'IMPL':2,'SUFFIX_KEEPS_BRANCH_MAPPING':1}),
    ]
    config=json.loads((ROOT/'tools/course_windows_config.json').read_text())
    env=dict(os.environ)
    env['PATH']=';'.join([config['runtime_bin'],config['build_bin'],env['PATH']])
    report=out/'word_equivalence.json'
    previous=json.loads(report.read_text()) if report.exists() else {}
    results=previous.get('results',[])
    current_results=[]
    for index,(module,params) in enumerate(cases):
        if a.case_index is not None and index != a.case_index: continue
        if a.only and module not in a.only.split(','): continue
        stem=f'{index:02d}_{module}'
        script=out/(stem+'.ys');log=out/(stem+'.log')
        commands=[]
        for kind in ('gold','gate'):
            top=module+'_'+kind
            commands += [f'read_verilog -sv -DCPU2026_WORD_SIM "{(out/(kind+".v")).as_posix()}"']
            if params:
                commands += ['chparam '+' '.join(f'-set {key} {value}' for key,value in params.items())+' '+top]
            commands += [f'hierarchy -check -top {top}', 'setattr -mod -unset keep_hierarchy',
                         'setattr -unset keep_hierarchy','proc','memory_map','flatten','opt_clean',
                         f'rename -top {kind}','setattr -mod -unset top',f'design -stash {kind}','design -reset']
        commands += ['design -copy-from gold -as gold gold','design -copy-from gate -as gate gate',
                     'equiv_make gold gate equiv','hierarchy -check -top equiv','opt_clean',
                     'equiv_simple -short -seq 2','equiv_induct -seq 2','equiv_status -assert']
        script.write_text('\n'.join(commands)+'\n',newline='\n')
        start=time.monotonic()
        with log.open('w') as stream:
            try:
                result=subprocess.run([config['yosys'],'-T','-s',str(script)],env=env,
                    stdout=stream,stderr=subprocess.STDOUT,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
                status='PROVEN' if result.returncode==0 and 'Equivalence successfully proven!' in log.read_text(errors='replace') else 'FAILED'
            except subprocess.TimeoutExpired: status='TIMEOUT'
        result={'module':module,'parameters':params,'status':status,'seconds':time.monotonic()-start}
        current_results.append(result)
        results=[r for r in results if (r['module'],r['parameters'])!=(module,params)]
        results.append(result)
        print(json.dumps(result),flush=True)
        report.write_text(json.dumps({'structural_bodies_identical':True,
            'two_state_only':True,'whole_cpu_formal_claim':False,'results':results,
            'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}},indent=2)+'\n')
        if status!='PROVEN': print(log.read_text(errors='replace')[-1800:],flush=True)
    return 0 if all(r['status']=='PROVEN' for r in current_results) else 1


if __name__=='__main__': raise SystemExit(main())
