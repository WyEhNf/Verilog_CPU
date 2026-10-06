"""Record final EP source/handshake reasoning without invoking HDL or EDA."""
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_lsq_selection_word_owners import lsq, OLD_WRITES, NEW_OWNER
from review_frequency_dx_sources import blocks


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    ap=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(ap)
    measured=ROOT/'EL1_cache_response_match_before_select'
    parent=ROOT/'EO1_registered_cache_hit_reply'
    candidate=ROOT/'EP_lsq_selection_payload_word_owners'
    previous_review=Path('F:/CPU2026Proofs/EO1_source_review_20261005/source_review.json')
    prior=read(previous_review)
    assert Path(active['candidate'])==measured and active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    chain=[measured,ROOT/'EN1_mmio_narrow_stable_domains',parent,candidate]
    for p in chain:
        verify_parent(p)
    assert prior['candidate_manifest_sha256']==sha(parent/'candidate.json')
    saved_record=next(x for x in active['prepared_unmeasured_alternatives'] if Path(x['candidate'])==parent)
    assert saved_record['review_sha256']==sha(previous_review)
    pm,cm,mm=read(parent/'candidate.json'),read(candidate/'candidate.json'),read(measured/'candidate.json')
    delta=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert delta==['rtl/backend/rv32_lsq.v']
    combined_delta=[n for n,h in cm['source_sha256'].items() if h!=mm['source_sha256'][n]]
    assert combined_delta==['rtl/backend/rv32_lsq.v','rtl/cache/rv32_dcache_nonblocking.v','rtl/cpu_core.v']
    assert cm['parameter_overrides']==pm['parameter_overrides']==active['parameter_overrides']
    assert cm['new_declared_sequential_state_bits']==0 and len(cm['implemented_groups'])==19
    old=(parent/delta[0]).read_text(encoding='utf-8')
    new=(candidate/delta[0]).read_text(encoding='utf-8')
    assert lsq(old)==new
    assert 'selection_write_views' not in new and NEW_OWNER in new
    normalized=change(old,OLD_WRITES,'')
    assert blocks(normalized)==blocks(new)
    before,after=blocks(old),blocks(new)
    changed_clock_blocks=sum(a!=b for a,b in zip(before,after))
    assert len(before)==len(after) and changed_clock_blocks==1
    unchanged_other=0
    for n in cm['source_sha256']:
        if n.endswith('.v') and n!=delta[0]:
            assert blocks((parent/n).read_text(encoding='utf-8'))==blocks((candidate/n).read_text(encoding='utf-8')),n
            unchanged_other+=len(blocks((parent/n).read_text(encoding='utf-8')))
    equal_clock_count=unchanged_other+len(before)-1
    assert equal_clock_count==68
    common=(candidate/'rtl/common/rv32_asap7_fanout.v').read_text(encoding='utf-8')
    for anchor in ('localparam integer WORDS=(WIDTH+15)/16;',
        'always @(posedge clk_i) if(write_words[word_id])',
        'data_o[LOW +: BITS]<=data_i[LOW +: BITS];'):
        assert anchor in common,anchor
    # All original payload writers are the explicit suffix removed above.
    import re
    fields=['selection_slot','selection_lsq_tag','selection_rob_tag','selection_addr',
        'selection_load','selection_size','selection_unsigned','selection_store_mask','selection_store_data']
    for field in fields:
        assert len(re.findall(r'\b'+field+r'\s*<=',old))==1,field
        assert not re.search(r'\b'+field+r'\s*<=',new),field
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    run=Path(active['frozen_run'])
    frozen=read(run/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    proof=Path('F:/CPU2026Proofs/EP_source_review_20261005')
    proof.mkdir(exist_ok=False)
    patch=proof/'changes_vs_measured_EL1.patch'
    patch.write_text(''.join(''.join(difflib.unified_diff(
        (measured/n).read_text(encoding='utf-8').splitlines(True),
        (candidate/n).read_text(encoding='utf-8').splitlines(True),
        fromfile=measured.name+'/'+n,tofile=candidate.name+'/'+n)) for n in combined_delta),encoding='utf-8')
    data=dict(status='FINAL_EP_COMBINATION_SOURCE_REVIEW_ONLY_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),
        chain=[dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json')) for p in chain],
        inherited_handshake_review=str(previous_review),inherited_handshake_review_sha256=sha(previous_review),
        changed_files_vs_parent=delta,changed_files_vs_EL1=combined_delta,
        candidate_inputs_verified=len(cm['source_sha256']),EL1_worktree_inputs_verified=len(active['source_sha256']),
        EL1_frozen_inputs_verified=len(frozen['snapshot_sha256']),EL1_inputs_unchanged=True,
        ordinary_integer_pipeline_depth=10,new_declared_state_bits=0,source_groups=19,
        compound_clocked_blocks_text_equal=equal_clock_count,
        compound_clocked_block_payload_suffix_relocated=1,
        remaining_selection_validity_clock_text_equal=True,
        single_statement_word_bank_clock_manually_reviewed=True,
        clock_text_is_not_cycle_equivalence=True,
        selection_payload_width_expression='SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72',
        active_profile=dict(LSQ_ENTRIES=16,SLOT_WIDTH=4,TAG_WIDTH=17,ROB_TAG_WIDTH=17,
            payload_bits=110,word_enable_leaves=7,maximum_bits_per_leaf=16),
        source_reasoning=[
            'Old five views all equal selection_input_fire. The only writers of all nine payload fields were the removed suffix; no payload reset exists. New word-bank writes the same concatenated values on the same positive edge whenever its seven views of selection_input_fire are true.',
            'Input and output field orders and widths are identical: slot, full LSQ tag, full ROB tag, address32, load1, size2, unsigned1, store mask4, store data32. No field truncation or generation-width change.',
            'When write0 each payload field holds in its existing semantic stage. REQUEST_PIPELINE0, reset, flush and recovery still disable selection_input_fire; selection_valid/forwarding_hold_valid and kill/discard/done priorities are unchanged.',
            'Width is symbolic for all supported parameters; ceil(width/16) leaves each own at most16 bits. Current110 bits relocate to seven leaves, replacing original address leaf32 bits/64 input pins and tag group38 bits.',
            'No new declared state or LSQ latency. Synthesis may retain duplicate slot/tag bits separately after write-owner splitting, so zero source state growth does not assert equal mapped sequential area.',
            'MMIO active-byte/whole-request stability and registered-hit backpressure reasoning are inherited verbatim from the hash-linked EO1 review. The hit first-response +1 cycle remains intentional.'
        ],architecture_triage=prior['architecture_triage']+[
            'The measured EL1 path also traverses the 64-pin selection-address write leaf (0.1189ns). Relocate the same payload into <=16-bit owners and measure together with the two structural chain cuts; do not run this change separately.',
            'This closes the concrete wide write-enable endpoint exposed by the current path. No further source transformation has sufficient current limiting-path evidence to join this batch.'
        ],caveats=prior['caveats']+[
            'The compound block checker does not parse the single-statement word-bank always body; its edge/hold/no-reset behavior was reviewed directly.',
            'This is source and handshake reasoning, not executable HDL validation or formal proof.'
        ],patch=str(patch),patch_sha256=sha(patch),adopted=False,new_test_started=False)
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=root/'reports/frequency_EL1_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8')
    text+='''\n## EP：组合加入 LSQ 选择字段的写使能分组\n\nEL1 路径末尾还经过 selection_write_tree 的地址写叶，服务32位 hold mux（64输入连接），延迟0.1189ns。EP 将原有全部选择 payload 的同拍写入移到已有 word-bank：宽度 SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72，当前110位、7组，每组最多16位。输入/输出字段顺序相同，完整 LSQ/ROB tag 保留，原 selection_valid/forwarding_hold_valid 的 reset/flush/recovery/kill/done 优先级完全相同。没有新状态或 LSQ 阶段；映射后的重复位是否合并仍待测。\n\n完整组合现为 EL1→EN1→EO1→EP；相对 EL1 仅 LSQ/Dcache/CPU core 三文件变化。68个复合时钟块文本原样，一个时钟块仅移除旧 payload 写入后其余文本相同；word-bank 的单语句时钟写另行人工核对。继承 EO1 的17域 MMIO 与首次空槽 hit+1拍。审查：`F:/CPU2026Proofs/EP_source_review_20261005/source_review.json`。本次 source/hash/握手审查未调用任何 HDL/EDA；当前主工作区仍 EL1。下次只能冻结 EP 并先报告，再测完整19组组合一次，不能单测 EN1/EO1/EP 子项。\n'''
    report.write_text(text,encoding='utf-8')
    record=dict(candidate=str(candidate),manifest_sha256=sha(candidate/'candidate.json'),tests_started=False,
        adopted=False,role='Final19-group stable-MMIO/register-hit/LSQ word-owner combination',
        review=str(review),review_sha256=sha(review))
    active['prepared_unmeasured_alternatives'].append(record)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),latest_review=record,
        role='EP final combined source review complete, no new measurement started')
    active['pending_source_research']=dict(next='Freeze EP, report final scope, then one combined timing-only run.',
        candidate=str(candidate),adopted=False,tests_started=False)
    active['source_research_decision']='Final19-group EP combines qualified MMIO consumer locality, existing registered cache response boundary, and same-stage LSQ word write ownership. EM/classification remain separate. Report before test.'
    ap.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),candidate_manifest_sha256=data['candidate_manifest_sha256'],
        compound_clocked_blocks_equal=equal_clock_count,payload_bits_relocated=110,
        source_groups=19,EL1_inputs_unchanged=True,new_tests_started=False)))


if __name__=='__main__':
    main()
