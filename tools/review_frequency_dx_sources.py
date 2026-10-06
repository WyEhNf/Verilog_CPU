"""Review source identities and clocked block text only; no HDL execution."""
import argparse
import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, BASE
from prepare_prf_precompare_and_store_imm12 import verify_parent


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def blocks(t):
    # Count begin/end in comment-free source, starting at each clocked block.
    # This is a source-text review, not a Verilog parser or equivalence test.
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',t,flags=re.S)
    result=[]
    for m in re.finditer(r'\balways\s*@\s*\(\s*posedge\b[^)]*\)\s*begin\b',clean):
        depth=1
        for tok in re.finditer(r'\b(begin|end)\b',clean[m.end():]):
            depth+=1 if tok[1]=='begin' else -1
            if depth==0:
                result.append(re.sub(r'\s+',' ',clean[m.start():m.end()+tok.end()]).strip())
                break
        else:
            raise ValueError('Unterminated block in source-text review')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',default='DX_dm1_request_locality_and_predecode')
    p.add_argument('--proof',type=Path,default=Path('F:/CPU2026Proofs/DX_source_review_20261005'))
    args=p.parse_args()
    candidate=ROOT/args.candidate
    dm1=ROOT/'DM1_lsq_report_bound_widths'
    active_path=Path('E:/Verilog_cpu/build/cpu2026/active_frequency_implementation_20261004.json')
    active=json.loads(active_path.read_text(encoding='utf-8'))
    for n,h in active['source_sha256'].items():
        assert sha(Path('E:/Verilog_cpu')/n)==h,n
    identities=[]
    chain=('DM1_lsq_report_bound_widths','DP_store_alloc_simm12',
                 'DT_completion_local_prf_enable','DU_lsq_report_rob_predecode',
                 'DV_negative_polarity_distribution','DW_predecode_and_polarity',
                 'DX_dm1_request_locality_and_predecode','DY_dm1_locality_and_store_simm12',
                 'DZ_recovery_and_icache_queue_domains',candidate.name)
    for name in dict.fromkeys(chain):
        p=ROOT/name
        verify_parent(p)
        identities.append(dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json')))
    cm=json.loads((candidate/'candidate.json').read_text(encoding='utf-8'))
    pm=json.loads((dm1/'candidate.json').read_text(encoding='utf-8'))
    changed=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    expected={'rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_lsq.v',
              'rtl/common/rv32_asap7_fanout.v','rtl/cpu_core.v'}
    if candidate.name in ('DZ_recovery_and_icache_queue_domains','EA_combined_control_locality'):
        expected.update(('rtl/backend/rv32_rat_recovery.v','rtl/cache/rv32_icache_nonblocking.v'))
    assert set(changed)==expected
    sequential=[]
    for n in cm['source_sha256']:
        if not n.endswith('.v'):
            continue
        old=blocks((dm1/n).read_text(encoding='utf-8'))
        new=blocks((candidate/n).read_text(encoding='utf-8'))
        assert old==new,'Compound clocked source equations changed: '+n
        sequential.append(dict(file=n,clocked_blocks=len(old),text_equal=True))
    source=(candidate/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    for n in ('dcache_req_valid_o','dcache_req_is_load_o','dcache_req_is_store_o',
              'dcache_req_addr_o','dcache_req_size_o','dcache_req_unsigned_o','dcache_req_mask_o',
              'dcache_req_rob_tag_o','dcache_req_lsq_tag_o','target_mask','fwd_mask','fwd_data','request_fire'):
        assert not re.search(r'^[ \t]*'+n+r'\s*(?:\[[^]]*\])?\s*=(?!=)',source,re.M),'Leftover procedural assignment: '+n
    assert 'module rv32_lsq_request_owner' in source
    for n in ('rtl/backend/rv32_completion_network.v','rtl/rv32_physical_register_file.v'):
        assert cm['source_sha256'][n]==pm['source_sha256'][n]
    proof=args.proof
    proof.mkdir(exist_ok=False)
    patch=''.join(''.join(difflib.unified_diff((dm1/n).read_text(encoding='utf-8').splitlines(keepends=True),
        (candidate/n).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile=dm1.name+'/'+n,tofile=candidate.name+'/'+n)) for n in changed)
    patch_path=candidate/'changes_vs_measured_DM1.patch'
    patch_path.write_text(patch,encoding='utf-8')
    parent=Path(cm['parent_candidate'])
    parent_patch=''.join(''.join(difflib.unified_diff((parent/n).read_text(encoding='utf-8').splitlines(keepends=True),
        (candidate/n).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile=parent.name+'/'+n,tofile=candidate.name+'/'+n))
        for n in cm['changed_files_vs_parent'])
    (candidate/'changes_vs_parent.patch').write_text(parent_patch,encoding='utf-8')
    baseline_patch=''.join(''.join(difflib.unified_diff((BASE/n).read_text(encoding='utf-8').splitlines(keepends=True),
        (candidate/n).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile='measured/'+n,tofile=candidate.name+'/'+n)) for n in cm['changed_files'])
    (candidate/'review.patch').write_text(baseline_patch,encoding='utf-8')
    review=dict(status='SOURCE_TEXT_AND_MANUAL_ALGEBRA_ONLY',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),verified_candidates=identities,
        changed_files_vs_measured_DM1=changed,patch=str(patch_path),patch_sha256=sha(patch_path),
        compound_clocked_block_text_review=sequential,
        compound_clocked_block_review_scope='Only always @(posedge ...) begin/end bodies. Single-statement payload writes are covered separately by manual correspondence.',
        new_declared_sequential_state_bits=0,ordinary_integer_pipeline_stages=10,
        no_compiler_lint_simulation_synthesis_sta_or_formal_run=True,
        completion_network_and_prf_source_unchanged_from_DM1=True,
        internal_enables={'STORE_ALLOC_IMM12':1,'LSQ_ROB_QUERY_PREDECODE':1},
        request_algebra={
            'A':'!flush && !recovery && candidate_found && !candidate_wait',
            'F':'A && selected_load',
            'M':'access_mask(selected_size)',
            'B':'selected original forwarding-hold/tree mask',
            'V':'A && (!selected_load || ((B & M) != M))',
            'forward_outputs':'F qualifies original target mask, forwarding mask and forwarding data',
            'request_fire':'V && cache_ready',
            'request_fields':'V qualifies selected size, full tags, relative load/store mask and inserted data; load/store flags retain selected_load; address remains ungated',
            'data_routing':'When V && selected_load, F is true, so inserting raw forwarding data then gating with V equals inserting previously F-gated data then gating with V.'},
        rob_query_reasoning=[
            'Every stored LSQ row decodes its ROB slot before the unchanged late report-row grant. The same grant carries full tags and two one-hot index banks.',
            'With a valid report, AND(low bank bit, high bank bit) selects exactly the original encoded ROB row. The normal valid and full generation comparison are retained.',
            'With no report both bank masks are zero. The differing unused ROB row-zero read is gated by producer-valid/full-tag-valid or valid load-error response. ALU branch training reads sources zero through three and is unchanged.',
            'Padding rows are zero, and the one-entry high bank handles zero index bits without an active zero-width slice.' ],
        distribution_reasoning=[
            'Root one inversion, negative internal node two inversions, positive leaf one inversion. Every externally observed leaf retains the original polarity.',
            'For LEAVES>1 each root-to-leaf route has two fewer inversions and saves LEAVES+1 inverter instances per bit. LEAVES=1 remains two inversions.',
            'Every internal driver feeds at most four next-stage gates, and every leaf retains an individual real driver. No externally imported cell or timing/library change.' ],
        shared_store_reasoning='The shared-store probe selects only pending store operations. Its CPU decoder immediate is sign-extended from instruction[31:25,11:7], the same contract used by the allocation specialization. Generic trace backends default STORE_ALLOC_IMM12 to zero and retain the full-width adder.',
        limitations='Source text and manual Boolean/algebra reasoning only. Not HDL syntax acceptance, formal four-state/parameter equivalence, mapped fanout, timing, area, IPC or full correctness proof.')
    if candidate.name in ('DZ_recovery_and_icache_queue_domains','EA_combined_control_locality'):
        old_icache=(dm1/'rtl/cache/rv32_icache_nonblocking.v').read_text(encoding='utf-8')
        new_icache=(candidate/'rtl/cache/rv32_icache_nonblocking.v').read_text(encoding='utf-8')
        assert 'always @(posedge clk_i) if(write_local) payload[queue_row]<={pc_i,epoch_i};' in old_icache
        assert '.clk_i(clk_i),.write_i(push && write_slot==queue_row),' in new_icache
        assert '.data_i({pc_i,epoch_i}),.data_o(payload[queue_row]));' in new_icache
        review['queue_manual_state_correspondence']={
            'same_payload_bits':'Two rows times (32+EPOCH_WIDTH), unreset, written on push && write_slot==row',
            'same_read_function':'Every 16-bit output group uses the same read_slot to choose the same two rows',
            'same_control_compound_block_text':True,'new_state_bits':0,
            'scope':'Single-statement row write becomes the existing word-bank owner with identical group write conditions; this is manual source correspondence, not tested equivalence.'}
        review['rat_recovery_manual_reasoning']='Eight groups duplicate identical killed/upper predicates. Every arch 1..31 reads the group (arch-1)/4; upper and arbitrary first-writer rules and branch-link override are unchanged.'
    if candidate.name=='EA_combined_control_locality':
        review['promoted_response_manual_reasoning']='Concatenating epoch/line/PC before the identical conditional select equals selecting each field separately; every word leaf carries the same response_promoted Boolean. Error bit, same-edge priority and write qualification are unchanged.'
    (proof/'source_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'review':str(proof/'source_review.json'), 'changed_RTL_files':len(changed),
                      'clocked_blocks_with_equal_source_text':sum(r['clocked_blocks'] for r in sequential),
                      'candidate_manifest_sha256':sha(candidate/'candidate.json'),'tests_started':False}))


if __name__=='__main__':main()
