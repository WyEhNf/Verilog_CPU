"""Cut the fetch-to-refill-ready dependency using response-slot dominance.

Every accepted request implies response_slot_free. If a response slot is
free, memory can return immediately; otherwise no request fires and only
an already-recorded live demand needs a slot. Preserve default behavior and
prove the LOCAL_RESPONSE_READY=1 rewrite with pending-hit protection enabled.
The separate protection-off policy remains a measured performance tradeoff.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy-candidate',type=Path,required=True)
    p.add_argument('--formal-template-root',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();source=a.policy_candidate.resolve();template=a.formal_template_root.resolve();out=a.outdir.resolve()
    assert not out.exists()
    manifest=json.loads((source/'candidate_manifest.json').read_text())
    for name,h in manifest['files_sha256'].items():assert sha(source/name)==h
    code=(source/'rtl/cache/rv32_icache_nonblocking.v').read_text()
    assert 'assign if_req_ready_o = !reset_i && response_slot_free &&' in code
    assert 'wire request_fire = if_req_valid_i && if_req_ready_o;' in code
    code=replace(code,'    parameter integer REFILL_PROTECT_PENDING_HIT = 1,',
                 '    parameter integer LOCAL_RESPONSE_READY = 0,\n    parameter integer REFILL_PROTECT_PENDING_HIT = 1,')
    before='''    assign mem_resp_ready_o = !response_target_found ||
                              (!response_needs_slot || response_slot_free);'''
    after='''    // request_fire implies response_slot_free through if_req_ready_o.
    // With no response slot, same-cycle promotion cannot be accepted; only
    // the demand already stored in the MSHR can require an output slot.
    assign mem_resp_ready_o = (LOCAL_RESPONSE_READY != 0) ?
                              (response_slot_free || !response_target_found ||
                               mshr_prefetch[response_index] ||
                               (mshr_demand_epoch[response_index] != current_epoch_i)) :
                              (!response_target_found ||
                               (!response_needs_slot || response_slot_free));'''
    code=replace(code,before,after)
    tb=(source/'tb/unit/rv32_icache_sram_tb.v').read_text()
    tb=replace(tb,'.REFILL_PROTECT_PENDING_HIT(PROTECT),',
               '.REFILL_PROTECT_PENDING_HIT(PROTECT), .LOCAL_RESPONSE_READY(1),')
    collision=(source/'tb/unit/rv32_icache_refill_policy_tb.v').read_text()
    collision=replace(collision,'.REFILL_PROTECT_PENDING_HIT(PROTECT)) dut (',
                      '.REFILL_PROTECT_PENDING_HIT(PROTECT),.LOCAL_RESPONSE_READY(1)) dut (')
    probe=(source/'tools/probe_localized_component.py').read_text()
    probe=replace(probe,"    parser.add_argument('--candidate-root', type=Path, required=True)",
                  "    parser.add_argument('--candidate-root', type=Path, required=True)\n    parser.add_argument('--protect',type=int,choices=(0,1),default=1)")
    probe=replace(probe,"case = out/f'protect{variant}'","case = out/f'ready{variant}'")
    probe=replace(probe,'REFILL_PROTECT_PENDING_HIT=variant)',
                  'REFILL_PROTECT_PENDING_HIT=args.protect, LOCAL_RESPONSE_READY=variant)')
    protocol=(template/'tools/test_icache_parallel_read_protocol.py').read_text().replace('test_icache_parallel_read_protocol','test_icache_local_response_ready_protocol')
    formal=(template/'tools/test_icache_parallel_read_formal.py').read_text().replace('test_icache_parallel_read_formal','test_icache_local_response_ready_formal')
    formal=formal.replace('TAG_READ_MUX_IMPL','LOCAL_RESPONSE_READY')
    formal=replace(formal,'EPOCH_WIDTH=epoch, PREFETCH_DISTANCE=3, NEXT_LINE_PREFETCH=1)',
                   'EPOCH_WIDTH=epoch, PREFETCH_DISTANCE=7, NEXT_LINE_PREFETCH=1)')
    files={'rtl/cache/rv32_icache_nonblocking.v':code,'tb/unit/rv32_icache_sram_tb.v':tb,
           'tb/unit/rv32_icache_refill_policy_tb.v':collision,'tools/probe_localized_component.py':probe,
           'tools/test_icache_local_response_ready_protocol.py':protocol,
           'tools/test_icache_local_response_ready_formal.py':formal}
    for name,text in files.items():
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    original=source/'baseline/rv32_icache_nonblocking.v';path=out/'baseline/rv32_icache_nonblocking.v'
    path.parent.mkdir(parents=True);path.write_bytes(original.read_bytes())
    report=dict(status='PREPARED',baseline_sha256=sha(original),
                files_sha256={n:sha(out/n) for n in files},default_local_response_ready=0,
                default_protect_pending_hit=1,local_ready_intended_cycle_equivalent=True,
                protection_off_can_add_misses=True,cpu_integrated=False,
                readiness_logic_basis='request_fire implies response_slot_free; when slot unavailable, no same-cycle demand promotion is accepted',
                formal_policy_protection=1,formal_prefetch_distance=7,preparer_sha256=sha(__file__))
    (out/'candidate_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
