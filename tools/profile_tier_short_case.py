"""Observe one short case from an existing frozen candidate; no six-case rerun/PPA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from run_tier_candidate import read, sha, verify


def final_vcd_values(path):
    scopes, signals, values = [], {}, {}
    in_header = True
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            words = line.split()
            if not words:
                continue
            if in_header:
                if words[0] == '$scope':
                    scopes.append(words[2])
                elif words[0] == '$upscope':
                    scopes.pop()
                elif words[0] == '$var':
                    name = words[4]
                    if name.startswith('perf_') or name.startswith('debug_'):
                        signals.setdefault(words[3], []).append('.'.join(scopes+[name]))
                elif words[0] == '$enddefinitions':
                    in_header = False
            elif words[0].startswith('b') and len(words) == 2 and words[1] in signals:
                bits = words[0][1:]
                if set(bits) <= {'0','1'}:
                    values[words[1]] = int(bits,2)
            elif words[0][0] in '01' and words[0][1:] in signals:
                values[words[0][1:]] = int(words[0][0])
    return {name: values.get(code) for code,names in signals.items() for name in names}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--case',default='perf_vvadd')
    args=parser.parse_args()
    root=args.candidate.resolve();out=args.out.resolve();m=read(root/'manifest.json');verify(root,m)
    source=root/'source';h=m['host'];old=read(root/'build.json')
    if old['status']!='PASSED' or sha(root/'build/sim.exe')!=old['executable_sha256']:
        raise ValueError('Matching successful candidate build required')
    # Restrict to an existing measured short case; avoid unbounded profiling.
    measured=next(x for x in read(root/'perf.json')['results'] if x['name']==args.case)
    if measured['cycles']>30000:
        raise ValueError('Choose a short <=30000-cycle case')
    case=source/'testcases'/args.case
    out.mkdir(parents=True,exist_ok=False)
    command=list(old['command']);binary=out/'sim.exe';obj=out/'obj'
    command[command.index('--Mdir')+1]=str(obj);command[command.index('-o')+1]=str(binary)
    env=dict(os.environ);env['PATH']=h['runtime_bin']+os.pathsep+h['build_bin']+os.pathsep+env['PATH']
    env.update(VERILATOR_ROOT=h['verilator_root'],CPU2026_REAL_VERILATOR=h['verilator'],
        CPU2026_PGO='0',CPU2026_WORD_SIM='1',CPU2026_STABLE_MDU='0',CPU2026_ICO_PAIR='0',
        CPU2026_NATIVE_BITS='1',CPU2026_SPLIT_SCHEDULE='1',CPU2026_TRACE_DEPTH='2',
        CPU2026_COMPACT_IDS='0',CPU2026_UNROLL_STMTS='1000000')
    state=dict(status='BUILDING_OBSERVATION_BINARY',candidate=str(root),base_commit=m['base_commit'],
        manifest_sha256=sha(root/'manifest.json'),build_command=command,trace_depth=2,
        rtl_changed=False,official_harness_changed=False,claims_cpu_ppa=False,case=args.case)
    (out/'report.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    print('START one-case observation build',flush=True);started=time.monotonic()
    with (out/'build.log').open('w',encoding='utf-8') as stream:
        subprocess.run(command,cwd=source,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
    verify(root,m);state['build_seconds']=time.monotonic()-started
    expected=int((case/'expected.txt').read_text().strip(),0)
    run_command=[str(binary),str(case/'program.data'),str(expected),'30000','10',str(out/'wave.vcd')]
    with (out/'simulation.log').open('w',encoding='utf-8') as stream:
        subprocess.run(run_command,cwd=source,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
    log=(out/'simulation.log').read_text();match=re.search(r'PASS cycles=(\d+)',log)
    if not match or int(match[1])!=measured['cycles']:
        raise ValueError('Observation execution must preserve prior measured cycles')
    state.update(status='OBSERVED_ONE_SHORT_CASE',run_command=run_command,cycles=int(match[1]),
        source_identity_rechecked=True,counters=final_vcd_values(out/'wave.vcd'),
        executable_sha256=sha(binary),build_log_sha256=sha(out/'build.log'),
        simulation_log_sha256=sha(out/'simulation.log'),wave_sha256=sha(out/'wave.vcd'),
        scope='One short existing performance case, unchanged frozen RTL/harness, deeper trace only. Counters can overlap; not a new tier validation or PPA.')
    if not any('perf_lsq_full_cycles' in k for k in state['counters']):
        raise ValueError('Trace did not expose requested counters')
    (out/'report.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in state.items() if k in ('status','cycles','counters','build_seconds')},indent=2),flush=True)


if __name__=='__main__':
    main()
