"""Freeze and enforce the user's +/-10% whole-CPU area/IPC frequency-first goal.

The reference is immutable, not the preceding candidate. Only a complete
same-build CPU result and53 native cases can satisfy the final stage gate.
"""
import argparse
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

from prepare_icache_selective_hierarchy import read, sha


def validate_hashes(result):
    assert result['input_sha256']
    for name, expected in result['input_sha256'].items():
        assert sha(name) == expected.lower(), 'Changed evidence: '+name


def values(result):
    assert result['status']=='VERIFIED' and result['all_correctness_cases']==29
    return dict(area_um2=Decimal(str(result['area']['area_um2'])),
                ipc=Decimal(str(result['geomean_ipc'])),
                frequency_mhz=Decimal(str(result['fmax_mhz'])))


def write(path, value):
    assert not path.exists(), 'Preserve existing evidence'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='mode',required=True)
    freeze=sub.add_parser('freeze')
    freeze.add_argument('--baseline',type=Path,required=True)
    freeze.add_argument('--out',type=Path,required=True)
    check=sub.add_parser('check')
    check.add_argument('--contract',type=Path,required=True)
    check.add_argument('--result',type=Path,required=True)
    check.add_argument('--native-audit',type=Path,required=True)
    check.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    if a.mode=='freeze':
        baseline=read(a.baseline); validate_hashes(baseline); b=values(baseline)
        assert baseline['sram_instances']==37
        result=dict(status='FROZEN',created_at=datetime.now().astimezone().isoformat(),
            objective='First approach300MHz with wholeCPU area and IPC each within10percent of the fixed current baseline',
            baseline_result=str(a.baseline.resolve()),baseline_sha256=sha(a.baseline),
            baseline_netlist_sha256=baseline['netlist_sha256'],
            baseline={k:str(v) for k,v in b.items()},
            limits={k:dict(min=str(b[k]*Decimal('0.9')),max=str(b[k]*Decimal('1.1')))
                    for k in ('area_um2','ipc')},frequency_target_mhz='300',
            interpretation='Symmetric inclusive10percent against current adopted legal-ADDI baseline; no rolling reference',
            scope='One complete CPU build, all actual SRAM priced and timed, original six benchmark geomean,53 native regressions',
            original_tier3_remains_separate=True,tool_sha256=sha(__file__))
    else:
        contract=read(a.contract); assert contract['status']=='FROZEN'
        assert sha(contract['baseline_result'])==contract['baseline_sha256']
        assert sha(__file__)==contract['tool_sha256']
        baseline=read(contract['baseline_result']);validate_hashes(baseline)
        candidate=read(a.result);validate_hashes(candidate); c=values(candidate)
        native=read(a.native_audit);validate_hashes(native)
        assert native['status']=='VERIFIED' and native['cases']==29
        assert native['added_native_cases']==8 and native['additional_isa_cases']==16
        assert Path(native['gate']).resolve()==Path(candidate['directory']).resolve()
        manifest_path=(Path(candidate['directory'])/'build/build_manifest.json').resolve()
        assert native['input_sha256'][str(manifest_path)]==candidate['input_sha256'][str(manifest_path)]==sha(manifest_path)
        bench=read(Path(candidate['directory'])/'benchmark.json')
        assert Decimal(str(bench['geomean_ipc']))==c['ipc']
        metrics={k:dict(value=str(c[k]),change_percent=str((c[k]/Decimal(contract['baseline'][k])-1)*100),
                    within_10percent=Decimal(contract['limits'][k]['min'])<=c[k]<=Decimal(contract['limits'][k]['max']))
                 for k in ('area_um2','ipc')}
        reached=c['frequency_mhz']>=Decimal(contract['frequency_target_mhz'])
        result=dict(status='VERIFIED',metrics=metrics,frequency_mhz=str(c['frequency_mhz']),
            frequency_target_reached=reached,stage_goal_achieved=reached and all(v['within_10percent'] for v in metrics.values()),
            original_tier3_achieved=candidate['tier3_achieved'],
            input_sha256={str(p.resolve()):sha(p) for p in (a.contract,a.result,a.native_audit,Path(__file__))},
            netlist_sha256=candidate['netlist_sha256'],all_sram_included=True)
    write(a.out,result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
