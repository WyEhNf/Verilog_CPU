"""Read source/identities only; archive the ES circular selection derivation."""
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_lsq_circular_prefix_packet import lsq, PREFIX
from review_frequency_dx_sources import blocks
from start_reused_frequency_programs_background import ACTIVE, sha, read


def main():
    main_root=Path('E:/Verilog_cpu')
    active=read(ACTIVE)
    parent=ROOT/'ER1_parallel_lsq_pick_slot_identity'
    candidate=ROOT/'ES_lsq_circular_prefix_packet'
    assert Path(active['candidate'])==parent
    for p in (parent,candidate):
        verify_parent(p)
    pm,cm=read(parent/'candidate.json'),read(candidate/'candidate.json')
    changed=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert changed==['rtl/backend/rv32_lsq.v']
    assert len(cm['implemented_groups'])==21
    assert cm['parameter_overrides']==pm['parameter_overrides']==active['parameter_overrides']
    name=changed[0]
    old=(parent/name).read_text(encoding='utf-8')
    new=(candidate/name).read_text(encoding='utf-8')
    assert new==lsq(old)
    start=old.index('        for (pick_node = 1; pick_node < LSQ_ENTRIES; pick_node = pick_node + 1) begin : g_pick')
    end=old.index('        // Each byte independently selects the youngest overlapping older',start)
    assert PREFIX+old[start:end]+'        end\n' in new
    total=0
    for n in cm['source_sha256']:
        if n.endswith('.v'):
            before=blocks((parent/n).read_text(encoding='utf-8'))
            assert before==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(before)
    assert total==69
    for n,h in active['source_sha256'].items():
        assert sha(main_root/n)==h,n
    run=Path(active['frozen_run'])
    frozen=read(run/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    report=main_root/'reports/frequency_ER1_background_research_2026-10-05.md'
    out=Path('F:/CPU2026Proofs/ES_source_review_20261005')
    assert not out.exists()
    out.mkdir()
    workflow_tools=['tools/start_reused_frequency_programs_background.py',
        'tools/record_reused_frequency_program_progress.py']
    record=dict(status='COMPLETE_ES_SOURCE_BINARY_PRIORITY_REVIEW_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),parent=str(parent),
        parent_manifest_sha256=sha(parent/'candidate.json'),changed_files=changed,source_groups=21,
        compound_clocked_blocks_text_equal=total,new_declared_state_bits=0,
        ordinary_integer_pipeline_depth=10,additional_LSQ_or_transaction_cycles=0,
        active_ER1_worktree_inputs_unchanged=len(active['source_sha256']),
        active_ER1_frozen_inputs_unchanged=len(frozen['snapshot_sha256']),
        source_review_script_sha256=sha(__file__),
        manual_binary_derivation=[
            'For power-of-two N>1, the original heap tournament has ascending physical leaves. When both children are valid, !left_wrap || right_wrap ranks unwrapped before wrapped, and chooses the left subtree within a class. Thus it selects the lexicographically smallest (wrap, physical row) among eligible rows.',
            'Unwrapped[r]=eligible[r]&&!wrap[r], wrapped[r]=eligible[r]&&wrap[r]. The group and local prefixes together mean no earlier physical row in the same class. An unwrapped grant needs its own eligible bit and no earlier unwrapped. A wrapped grant additionally needs no unwrapped anywhere. Therefore exactly one binary winner exists iff any eligible row exists, and it is the original winner.',
            'Group before vectors only include earlier complete groups; local before vectors only include rows before the current row in its own group. Their disjoint union is exactly [0,r). GROUPS and partial BITS handle N2 as one group of two, without negative or zero-width slices because generate first-group/row branches bypass slices.',
            'If all rows are invalid, original choose_left is false at every internal node, so root metadata comes from physical N-1. ES adds !pick_valid[1] only to that row grant. This remains one-hot and preserves all invalid/default fields rather than fabricating zeros.',
            'Each complete masked row packet is the exact original leaf tuple slot/age/wrap/address/payload. The ER1 payload leaf indexes by the original truncated SLOT_WIDTH slot; ES does not replace it with physical row data. Masked OR therefore preserves explicit slot-width overrides and keeps address/tag/data from the same original winning leaf.',
            'N1 and non-power-of-two N use the complete original ER1 tournament byte-for-byte, retaining original physical heap order, modular-age comparison, defaults and tie behavior.',
            'Root pick_valid is OR of unchanged eligibility bits, identical to original tree OR. Selection_live, full generation/ROB authority, older-store hazards, committed store permission, reset/flush/recovery, forwarding hold and selection_input_fire are outside the replaced combinational block. All 69 compound clock blocks remain text-identical; no new state or transaction edge.'
        ],
        workflow_source_review=dict(tools_sha256={n:sha(main_root/n) for n in workflow_tools},
            executed=False,program_phase_started=False,
            observations=['Starter requires a completed current timing identity, matching frozen/main/config/tool/report hashes, >=350MHz and original area upper limit, finalized human-visible program pretest, exact six perf/nineteen correctness names and no earlier program outputs.',
                'Starter requests --reuse-synth --correctness in one hidden native job. Wrapper already supports this phase; original timing report/dispatch/identity are preserved. No second synth or changed course script is requested.',
                'Separate observer follows the new program PID; old timing-only observer must not be used during program phase. Official case log format PASS[cycles]/FAIL and nineteen-case summary were read from the frozen course script.',
                'Observer verifies executable/Verilator/source and per-program instruction/cycle/GEOMEAN identity; full PASS requires six perf outputs, all nineteen correctness names and exact completed result hashes. This is static workflow review, not a executed workflow test.']),
        research_report=str(report),research_report_sha256=sha(report),
        tests_started=False,adopted=False,
        limitations=['Binary source derivation is not HDL elaboration, formal proof or full CPU correctness.',
            'Unknown four-state behavior can differ; bounded RTL masks do not predict mapped fanout, area or MHz.',
            'Conditional candidate only; adopt after new ER1 saved paths justify and all batch changes are finished.'])
    path=out/'source_review.json'
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    entry=dict(candidate=str(candidate),manifest_sha256=sha(candidate/'candidate.json'),
        tests_started=False,adopted=False,review=str(path),review_sha256=sha(path),
        role='Conditional parallel circular prefix/one-hot packet alternative; source only, await ER1 paths.')
    active['prepared_unmeasured_alternatives'].append(entry)
    active['pending_source_research']=[entry]
    active['ongoing_research_report']=str(report)
    active['last_background_source_research']=dict(report=str(report),report_sha256=sha(report),
        review=str(path),review_sha256=sha(path),candidate=str(candidate),
        ER1_inputs_unchanged=True,new_additional_test_started=False,
        program_workflow_tools_prepared_only=True,role='Background ER1 research; ES source-only conditional alternative')
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('status','candidate_manifest_sha256',
        'compound_clocked_blocks_text_equal','new_declared_state_bits','tests_started','adopted')}))


if __name__=='__main__':
    main()
