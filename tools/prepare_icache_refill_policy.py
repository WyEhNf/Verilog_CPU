"""Isolate the optional pending-hit protection on I-cache refill victims.

Default1 preserves the existing replacement rule. Trial0 still picks an
invalid entry first, then LRU, but does not query the pending fetch hit.
This changes replacement decisions and may add misses; no cycle-equivalence
claim is made. Original RAM arbitration and every state field remain present.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(code,old,new):
    assert code.count(old)==1,old
    return code.replace(old,new)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--probe-template',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();out=a.outdir.resolve();assert not out.exists()
    original=a.source_root.resolve()/'rtl/cache/rv32_icache_nonblocking.v'
    code=original.read_text()
    code=replace(code,'    parameter integer NEXT_LINE_PREFETCH = 1,',
                 '    parameter integer REFILL_PROTECT_PENDING_HIT = 1,\n    parameter integer NEXT_LINE_PREFETCH = 1,')
    code=replace(code,'    wire refill_conflicts_with_hit = if_req_valid_i && request_hit &&',
                 '    wire refill_conflicts_with_hit = (REFILL_PROTECT_PENDING_HIT != 0) &&\n                                     if_req_valid_i && request_hit &&')
    tb=(ROOT/'tb/unit/rv32_icache_sram_tb.v').read_text()
    tb=replace(tb,'    parameter integer LINES = 16, WAYS = 2;',
               '    parameter integer LINES = 16, WAYS = 2, MSHRS = 4, PROTECT = 1;')
    tb=replace(tb,'.MSHR_ENTRIES(4),',
               '.MSHR_ENTRIES(MSHRS), .REFILL_PROTECT_PENDING_HIT(PROTECT),')
    probe=a.probe_template.read_text()
    probe=probe.replace('TAG_READ_MUX_IMPL','REFILL_PROTECT_PENDING_HIT')
    probe=replace(probe,"case = out/f'tag_read{variant}'","case = out/f'protect{variant}'")
    # Match current course CPU: MSHR8 => prefetch distance7.
    probe=replace(probe,'PREFETCH_DISTANCE=3, CACHE_LINES=128, CACHE_WAYS=2, REFILL_PROTECT_PENDING_HIT=variant)',
                  'PREFETCH_DISTANCE=7, CACHE_LINES=128, CACHE_WAYS=2, REFILL_PROTECT_PENDING_HIT=variant)')
    files={'rtl/cache/rv32_icache_nonblocking.v':code,
           'tb/unit/rv32_icache_sram_tb.v':tb,
           'tb/unit/rv32_icache_refill_policy_tb.v':(ROOT/'tb/unit/rv32_icache_refill_policy_tb.v').read_text(),
           'tools/probe_localized_component.py':probe}
    for name,text in files.items():
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    path=out/'baseline/rv32_icache_nonblocking.v';path.parent.mkdir(parents=True);path.write_bytes(original.read_bytes())
    result=dict(status='PREPARED',source=str(original),baseline_sha256=sha(original),
                files_sha256={n:sha(out/n) for n in files},
                default_preserves_existing_policy=True,trial_value=0,
                policy_change_may_add_misses=True,no_cycle_equivalence_claim=True,
                sram_arbitration_and_state_unchanged=True,cpu_integrated=False,
                prefetch_distance_for_component_ppa=7,preparer_sha256=sha(__file__))
    (out/'candidate_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
