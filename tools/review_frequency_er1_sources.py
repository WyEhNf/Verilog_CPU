"""Review ER1 packet/priority identities from source and saved EP paths."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_lsq_pick_slot_identity import lsq
from review_frequency_dx_sources import blocks


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    ap=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(ap)
    parent=ROOT/'EP_lsq_selection_payload_word_owners'
    draft=ROOT/'ER_parallel_lsq_pick_packet'
    candidate=ROOT/'ER1_parallel_lsq_pick_slot_identity'
    assert Path(active['candidate'])==parent and active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert active['current_measured_fmax_mhz']==361.0719322990127
    for p in (parent,draft,candidate):
        verify_parent(p)
    pm,cm=read(parent/'candidate.json'),read(candidate/'candidate.json')
    changed=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert changed==['rtl/backend/rv32_lsq.v']
    assert cm['new_declared_sequential_state_bits']==0 and len(cm['implemented_groups'])==20
    assert cm['parameter_overrides']==pm['parameter_overrides']==active['parameter_overrides']
    old=(parent/changed[0]).read_text(encoding='utf-8')
    new=(candidate/changed[0]).read_text(encoding='utf-8')
    assert lsq(old)==new
    assert 'pick_payload_read (' not in new
    for anchor in ('wire choose_left = pick_valid[2*pick_node] &&',
        'assign pick_valid[pick_node] = pick_valid[2*pick_node] || pick_valid[2*pick_node+1];',
        'assign pick_slot[LSQ_ENTRIES+age_slot] = age_slot;',
        'assign pick_age[LSQ_ENTRIES+age_slot] = entry_age[age_slot];',
        'assign pick_addr[LSQ_ENTRIES+age_slot] = addr_mem[age_slot];',
        'wire selection_input_fire=(REQUEST_PIPELINE!=0) && !reset_i && !flush_i && !recovery_valid_i &&',
        'localparam [SLOT_WIDTH-1:0] PAYLOAD_SLOT=query_row;'):
        assert anchor in new,anchor
        if not anchor.startswith('localparam'):
            assert anchor in old,anchor
    # The complete original comparison/priority expression is byte-identical.
    def choice_expression(t):
        start=t.index('            wire choose_left = pick_valid[2*pick_node] &&')
        return t[start:t.index('            assign pick_valid[pick_node]',start)]
    assert choice_expression(old)==choice_expression(new)
    total=0
    for n in cm['source_sha256']:
        if n.endswith('.v'):
            before=blocks((parent/n).read_text(encoding='utf-8'))
            assert before==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(before)
    assert total==69
    run=Path(active['frozen_run'])
    frozen=read(run/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert sha(active['pretest_report'])==active['pretest_report_sha256']
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    measured=read(run/'result/timing_only.json')
    assert measured['source_manifest_sha256']==active['frozen_manifest_sha256']
    assert measured['official_report_sha256']==sha(run/'result/synth/opt/report.json')
    saved_path=Path('F:/CPU2026Proofs/EP_mapped_paths_20261005/saved_path_analysis.json')
    saved=read(saved_path)
    assert saved['input_sha256']['critical_paths.json']==sha(run/'result/synth/opt/critical_paths.json')
    assert saved['input_sha256']['mapped.v']==sha(run/'result/synth/opt/mapped.v')
    through_payload_query=[p['rank'] for p in saved['paths'] if any(
        'lsq.pick_payload_read.query_tree.' in s['instance'] for s in p['segments'])]
    assert through_payload_query==[1,2,3,4,5]
    slow=[s for s in saved['dominant_segments'] if s['instance'] in ('_373906_','_373914_','_373917_','_376826_')]
    assert len(slow)==4
    proof=Path('F:/CPU2026Proofs/ER1_source_review_20261005')
    proof.mkdir(exist_ok=False)
    data=dict(status='COMPLETE_ER1_SOURCE_PACKET_PRIORITY_REVIEW_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),parent=str(parent),
        parent_manifest_sha256=sha(parent/'candidate.json'),changed_files=changed,
        source_groups=20,compound_clocked_blocks_text_equal=total,new_declared_state_bits=0,
        ordinary_integer_pipeline_depth=10,additional_LSQ_or_transaction_cycles=0,
        cached_first_hit_extra_cycle_inherited_from_EP=True,EP_current_inputs_unchanged=True,
        candidate_inputs_verified=len(cm['source_sha256']),worktree_inputs_verified=len(active['source_sha256']),
        frozen_EP_inputs_verified=len(frozen['snapshot_sha256']),
        measured_parent=dict(fmax_mhz=measured['fmax_mhz'],area_um2=measured['area_um2'],
            ipc=None,minimum_period_ns=measured['minimum_period_ns'],
            source_manifest_sha256=active['frozen_manifest_sha256']),
        reported_EP_paths_through_payload_query=through_payload_query,
        saved_path_analysis=str(saved_path),saved_path_analysis_sha256=sha(saved_path),
        four_high_load_gates=[{k:s[k] for k in ('instance','cell','delay_ns','fanout','net')} for s in slow],
        four_gate_delay_sum_ns=sum(s['delay_ns'] for s in slow),
        active_profile=cm['active_profile'],
        manual_binary_induction=[
            'Define P(r) as the old stored-row payload. Every original leaf slot is row assigned to SLOT_WIDTH; ER1 leaf packet is P(that exact truncated slot), not blindly P(physical row). This preserves explicit SLOT_WIDTH overrides too.',
            'At a leaf, slot/age/wrap/address are exactly old values and packet=P(slot). Assume both children have those identities. The original choose_left expression is byte-identical; every choose view equals that Boolean. All concatenated fields therefore follow the same child, giving parent packet=P(parent slot) and identical metadata.',
            'Induct through all nodes to root. Old array_read returns P(pick_slot[1]); new root packet returns the same P with full generation/ROB tag/data/mask/load/size/unsigned order. Address and tag come from their respective original leaves under the identical winner, not independently selected candidates.',
            'The original invalid/invalid branch also chooses right. ER1 uses that branch without a valid-only mask; no-candidate payload remains from the original root slot, typically final physical leaf, not an invented row0 default.',
            'With LSQ_ENTRIES1 there are no internal nodes: the existing leaf occupies root1, and both old read and new packet access its exact slot. Power-of-two entries, circular vs age comparison, and tie/invalid priorities remain original.',
            'SLOT_WIDTH bits for both slot and age plus wrap1/address32/payload(GENERATION_WIDTH+ROB_TAG_WIDTH+40) sum to PICK_SELECT_WIDTH. Input/output concatenations use exactly those widths/order. Current108 bits are seven word views, last word12 bits.',
            'All payload writers, request eligibility/older-store hazards, committed-store gating, full live/generation checks, selection_input_fire, flush/recovery and forwarding snapshots remain unchanged. The existing110-bit selection bank samples the same root fields on the same edge.',
            'Replacing encoded slot then late indexed payload read by full packet routing removes a real serial source connection. Partitioning the entire node bundle includes old address/metadata choices; it does not presume the public index alias is owned exclusively by payload reader.'
        ],architecture_triage=[
            'Current five published EP paths start from addr_mem[7][3], pass older-store/request eligibility, tournament choices and then pick_payload_read query/row decoding. Do not treat ordinary ALU stages or MMIO as the current limiter.',
            'Handle both full-packet-before-final-selection and bounded final node choices. Changing payload only could leave late slot/age/address mux controls wide, because slot bits can alias original choose decisions.',
            'EQ MMIO classifier and EM shared ROB query remain separate; no current published path justifies adding them.',
            'Registering all older-store hazard matrices, optimistic loads/replay, or changing issue/window parameters would require snapshots/invalidation/recovery/IPC changes. The existing no-new-state tree transpose is the first justified structural cut.',
            'A direct per-row one-hot priority packet OR is another representation, but computing separate winner/default masks introduces redundant priority and is less directly tied to the original tournament. Use identical original node decisions here.',
            'No additional source change is currently justified for this complete ER1 batch; new global Fmax/area remains unmeasured. Report before any measurement.'
        ],caveats=[
            'Source/hash and manual binary induction only; no HDL parser/compiler/lint/formal/simulation/synthesis/STA test.',
            'Four-state unknown mux merging may differ from one-hot indexed read. No claim of full four-state or whole-CPU equivalence; valid transaction qualifiers and reset behavior remain original.',
            'Choice views own <=16 RTL mux bits, not a guarantee of the exact final library input-pin load or timing.',
            'Additional buffers/parallel data paths can cost area or create a new path; no MHz estimate by subtracting old gate delays.',
            'Zero declared state increase does not imply identical mapped sequential area. Existing EP load-hit first-response extra cycle remains; current IPC/function and Tier3 are unverified.'
        ],adopted=False,new_test_started=False)
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=Path(active['ongoing_research_report'])
    text=report.read_text(encoding='utf-8')
    text+='''\n## EP 测量完成，ER1 完整请求包选择已实现但未测\n\nEP完成一次原生课程测量：361.071932MHz、2.76953125ns、总49,589.945634μm²含SRAM；相比EL1频率+35.2962%、面积-0.04655%，相对原面积+7.0833%。300MHz满足，略低于EF370.477569MHz。没有IPC/功能程序，不能宣布±10%IPC或Tier3完成。原始测量：`E:/Verilog_cpu/reports/frequency_EP_measurement_2026-10-05.md`。\n\n五条新最慢路径都从LSQ addr_mem[7][3]经过老store/request资格和选择，到pick_payload_read.query_tree/行解码再到暂存输入。四门负载67/68、延迟0.3363/0.3228/0.3972/0.3042ns，合计1.3605ns。后两项的公共index别名也可能等于原choose决策，不是payload_reader独占；方案同时处理完整树节点的地址/年龄/slot等选择消费者。\n\nER1只改LSQ组合结构：每节点仍用原choose_left，slot/age/wrap/address/完整generation+ROBtag+storedata+mask/load/size/unsigned一同传递，当前108位、7个最多16位选择域。取消赢得slot后再查67位payload的串行读。二值树归纳证明每节点packet等于原read(该节点slot)，无候选时仍执行原invalid/invalid右分支；保持原默认槽，不额外指定row0。叶payload按原SLOT_WIDTH的slot赋值取数据，兼容显式slot宽度截断；单条目root直接是叶。\n\nER草稿与最终ER1保留，均未测；ER1相对EP仅LSQ组合逻辑变化，69个复合时钟块相同，零新增状态/LSQ周期，普通整数流水线10级，继承EP首次hit多一拍。当前主工作区及冻结157输入仍为实测EP。源审查：`F:/CPU2026Proofs/ER1_source_review_20261005/source_review.json`。面积/全局Fmax未知，不能用1.3605ns直接相减预测频率。\n\nEQ与EM的限制不在新导出的最慢路径，继续分开。矩阵hazard寄存、乐观load重放、缩窗口/issue/PRF端口等仍有snapshot/失效/恢复和IPC成本；当前采用与原优先树严格对应的无新增边沿转置。完整ER1已经结束源审查；下一次必须冻结并先报告，再只测整体一次，不能单测节点或混入无证据备选。\n'''
    report.write_text(text,encoding='utf-8')
    record=None
    for p in (draft,candidate):
        item=dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json'),tests_started=False,adopted=False,
            role='Parallel full LSQ pick packet; source-only '+('final slot-identity version' if p==candidate else 'preserved draft'))
        if p==candidate:
            item.update(review=str(review),review_sha256=sha(review))
            record=item
        active['prepared_unmeasured_alternatives'].append(item)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),latest_review=record,
        role='EP timing complete; ER1 final source reviewed, no new measurement started')
    active['pending_source_research']=dict(next='Freeze ER1 and report before a single full timing-only job; no intermediate tests.',
        candidate=str(candidate),adopted=False,tests_started=False)
    active['source_research_decision']=data['architecture_triage'][-1]
    for item in active['prepared_unmeasured_alternatives']:
        if Path(item['candidate'])==parent:
            item.update(tests_started=True,role='Current measured EP:361.071932MHz, IPC/function untested; frozen result preserved')
    ap.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),candidate_manifest_sha256=data['candidate_manifest_sha256'],
        source_groups=20,clocked_blocks_text_equal=total,packet_bits=108,source_only=True,
        EP_inputs_unchanged=True,new_tests_started=False)))


if __name__=='__main__':
    main()
