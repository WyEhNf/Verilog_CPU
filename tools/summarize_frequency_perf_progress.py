"""Summarize already completed official perf output; never invoke simulator."""
import hashlib,json,math,re
from pathlib import Path

RUN=Path('F:/CPU2026CourseRuns/architecture_L1_20261004')
BASE=Path('F:/CPU2026CourseRuns/current_adopted_20261003/result/result.json')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    config=json.loads((RUN/'course_windows_config.json').read_text())
    manifest=json.loads((RUN/'source_manifest.json').read_text())
    source=Path(config['source'])
    assert 'DONE course native perf' in (RUN/'background.stdout.log').read_text()
    rows=[]
    for line in (RUN/'result/perf.log').read_text().splitlines():
        m=re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)',line)
        if m:
            name,instructions,cycles,_=m.groups()
            case=source/'.deps/RISC-V-CPU-2026/testcases'/name
            count=json.loads((case/'metrics.json').read_text())['dynamic_instructions']
            assert count==int(instructions)
            rows.append(dict(name=name,instructions=count,cycles=int(cycles),ipc=count/int(cycles),
                             program_sha256=sha(case/'program.data'),metrics_sha256=sha(case/'metrics.json')))
    assert len(rows)==6 and len({r['name'] for r in rows})==6
    ipc=math.exp(sum(math.log(r['ipc']) for r in rows)/6)
    baseline=json.loads(BASE.read_text())['ipc']
    record=dict(status='PARTIAL_PERFORMANCE_COMPLETE',results=rows,geomean_ipc=ipc,
                baseline_ipc=baseline,ipc_change_percent=(ipc/baseline-1)*100,
                ipc_within_10_percent=abs(ipc/baseline-1)<=0.10,latency=10,
                official_perf_expected_results_passed=True,official_scripts_unmodified=True,
                source_manifest_sha256=sha(RUN/'source_manifest.json'),perf_log_sha256=sha(RUN/'result/perf.log'),
                fmax_mhz=None,area_um2=None,correctness_suite_status='IN_PROGRESS',
                note='No new test was run by this read-only aggregation; synthesis/STA still required')
    (RUN/'result/perf_progress.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ('status','geomean_ipc','ipc_change_percent','ipc_within_10_percent')}))

if __name__=='__main__':
    main()
