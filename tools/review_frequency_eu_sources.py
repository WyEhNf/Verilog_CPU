"""Archive EU source/field/arithmetic identities without running any test."""
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_prearbitration_store_addresses import backend, completion, prf
from review_frequency_dx_sources import blocks
from start_reused_frequency_programs_background import ACTIVE, sha, read


def main():
    main_root=Path('E:/Verilog_cpu')
    active=read(ACTIVE)
    parent=ROOT/'ER1_parallel_lsq_pick_slot_identity'
    es=ROOT/'ES_lsq_circular_prefix_packet'
    et=ROOT/'ET_prearbitration_producer_store_addresses'
    candidate=ROOT/'EU_prefix_pick_and_prearbitration_store_addresses'
    assert Path(active['candidate'])==parent and active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert active['current_measured_fmax_mhz']==371.41820819731595
    for p in (parent,es,et,candidate):
        verify_parent(p)
    pm,cm=read(parent/'candidate.json'),read(candidate/'candidate.json')
    transformations={'rtl/backend/rv32_backend_joint.v':backend,
        'rtl/backend/rv32_completion_network.v':completion,'rtl/rv32_physical_register_file.v':prf}
    changed=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert set(changed)==set(transformations)|{'rtl/backend/rv32_lsq.v'}
    for n,f in transformations.items():
        assert f((parent/n).read_text(encoding='utf-8'))==(et/n).read_text(encoding='utf-8')
        assert sha(et/n)==sha(candidate/n),n
    assert sha(candidate/'rtl/backend/rv32_lsq.v')==sha(es/'rtl/backend/rv32_lsq.v')
    assert len(cm['implemented_groups'])==22
    assert cm['parameter_overrides']==pm['parameter_overrides']==active['parameter_overrides']
    total=0
    for n in cm['source_sha256']:
        if n.endswith('.v'):
            before=blocks((parent/n).read_text(encoding='utf-8'))
            assert before==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(before)
    assert total==69
    # Selection/rank/held-source cursor logic and the original direct payload
    # and handshake bodies remain byte-identical, apart from the new export.
    old=(parent/'rtl/backend/rv32_completion_network.v').read_text(encoding='utf-8')
    new=(candidate/'rtl/backend/rv32_completion_network.v').read_text(encoding='utf-8')
    s=old.index('    // Reserve held sources using static tag comparisons.')
    e=old.index('    localparam integer DIRECT_META_WIDTH',s)
    assert old[s:e] in new
    old_backend=(parent/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    new_backend=(candidate/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    s=old_backend.index('            if(io_lane==CDB_WIDTH-1) begin:g_branch_link_route')
    e=old_backend.index('    // Ready is a contiguous, resource-qualified prefix',s)
    assert old_backend[s:e] in new_backend
    for n,h in active['source_sha256'].items():
        assert sha(main_root/n)==h,n
    run=Path(active['frozen_run'])
    frozen=read(run/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    es_review=Path('F:/CPU2026Proofs/ES_source_review_20261005/source_review.json')
    es_proof=read(es_review)
    assert es_proof['candidate_manifest_sha256']==sha(es/'candidate.json')
    paths_path=Path('F:/CPU2026Proofs/ER1_mapped_paths_20261005/saved_path_analysis.json')
    paths=read(paths_path)
    assert all(p['arrival_ns']==2.6319 for p in paths['paths'])
    first=paths['paths'][0]['segments']
    assert any('write_address/sum_o[30]' in p['net'] for p in first)
    assert not any('pick_payload_read' in p['net'] or 'g_pick.' in p['net'] for p in first)
    report=main_root/'reports/frequency_EU_source_research_2026-10-05.md'
    out=Path('F:/CPU2026Proofs/EU_source_review_20261005')
    assert not out.exists()
    out.mkdir()
    record=dict(status='COMPLETE_EU_SOURCE_ARITHMETIC_AND_PACKET_REVIEW_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),parent=str(parent),
        parent_manifest_sha256=sha(parent/'candidate.json'),changed_files=changed,source_groups=22,
        compound_clocked_blocks_text_equal=total,new_declared_state_bits=0,
        ordinary_integer_pipeline_depth=10,additional_LSQ_or_transaction_cycles=0,
        active_ER1_worktree_inputs_unchanged=len(active['source_sha256']),
        active_ER1_frozen_inputs_unchanged=len(frozen['snapshot_sha256']),
        source_review_script_sha256=sha(__file__),es_review=str(es_review),es_review_sha256=sha(es_review),
        mapped_paths=str(paths_path),mapped_paths_sha256=sha(paths_path),
        measured_parent=dict(fmax_mhz=active['current_measured_fmax_mhz'],
            area_um2=active['current_measured_area_um2'],ipc=None),
        actual_path_public_checkpoints=[dict(arrival_ns=x['arrival_ns'],net=x['net']) for x in first
            if any(k in x['net'] for k in ('report_bound_tree.signal','load_complete_rob_query_o',
                'live_read/value_o','select_tree.signal','value_tree.signal_i','write_address/sum_o'))],
        manual_binary_identities=[
            'In native direct completion mode, each selected_mask[lane] is the original one-hot source grant. New source_select_o exports exactly that mask AND !reset AND !flush, the same qualification as the original direct payload mask; no source/tag/hold/cursor/ready logic changes. Other completion modes export zero and never enable precomputation.',
            'For a nonempty one-hot direct lane, the original CDB data equals producer_value at the selected source. Each producer now computes add_simm12(value, current allocation offset) before the grant; the exact same source grant selects that sum. This equals add_simm12(original CDB data, offset), modulo 2^32.',
            'For an empty/reset/flush direct lane the original CDB data is zero. New event0 is !OR(source grants), with sign-extended current immediate (zero+signed12). It is mutually exclusive with source events and restores the exact old default. BE lanes beyond CDB_WIDTH export zero and use the same default.',
            'The original PRF data at lane CDB_WIDTH-1 is overridden by branch_pending_value iff branch_pending&&branch_pending_rd_we. A separate precomputed link sum follows exactly that predicate and the same current offset. This is CDB_WIDTH-1 for all valid widths, not a hardcoded BE_WIDTH-2. Original PRF physical destination and valid routing is unchanged.',
            'For allocation port a and write lane w, the flattened precomputed bus index is (a*BE_WIDTH+w)*32; PRF even read port rp=2*a reads that exact slice for address_events[w+1]. The highest legal matching write lane and !bypass_write stored fallback events remain original. P0/out-of-range read handling and stored-tree adder remain original.',
            'Offsets are current allocation-query inputs. They are not captured into producer/CDB state and need not stay fixed while a producer is held. Every sum recomputes with the same current d_imm[allocation_lane] as old PRF output; the original allocation handshake captures it. Thus no offset/tag epoch crosses a new edge.',
            'Existing positive control trees distribute producer/link bases before the parallel adders to avoid direct four-adder load at the original raw data bit. Their functional value is unchanged and no register is introduced. Their area/delay is not free.',
            'When PARALLEL_STORE_ADDRESS is false or completion mode is not2, SOURCE_STORE_ADDRESS is false; backend bus is constant zero and the PRF uses its byte-identical original write-lane adder branch. Standalone STORE_ADDRESS_PRECOMPUTED defaults0. All original data/ready/value storage behavior is preserved.',
            'EU LSQ content is SHA-identical to source-reviewed ES; compose its circular winner/default/exact leaf-slot payload proof with these three ET file transformations. All 69 compound clock blocks remain text-identical and no new state or transaction cycle is declared.'
        ],
        active_profile=cm['active_profile'],tests_started=False,adopted=False,
        research_report=str(report),research_report_sha256=sha(report),
        limitations=['Source identities and binary reasoning only; not HDL elaboration, formal equivalence, actual timing or full CPU correctness.',
            'Direct mask proof assumes the existing initialized legal rank/held-source invariants. Original same masks/logic are preserved; no new grants are invented.',
            'Unknown four-state arithmetic/mux behavior may differ, especially empty and multi-unknown grants.',
            'Extra adders, source distributions, masked OR and default selection can raise area or expose other paths. ES is a former-bottleneck backstop, not asserted to be an exported current top5 path. No MHz forecast.'])
    path=out/'source_review.json'
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    entries=[]
    for cand,role in ((et,'Source-side arithmetic intermediate; unmeasured/unadopted.'),
        (candidate,'Complete two-structure candidate; reviewed source only, report before any measurement.')):
        entries.append(dict(candidate=str(cand),manifest_sha256=sha(cand/'candidate.json'),
            tests_started=False,adopted=False,review=str(path),review_sha256=sha(path),role=role))
    active['prepared_unmeasured_alternatives'].extend(entries)
    active['pending_source_research']=entries
    active.update(ongoing_research_report=str(report),source_research_decision=
        'EU source implementation/review complete. No ET/EU test or adoption has begun; finish scope/freeze and concrete pretest report before one combined measurement.')
    active['last_background_source_research']=dict(report=str(report),report_sha256=sha(report),
        review=str(path),review_sha256=sha(path),candidate=str(candidate),
        ER1_inputs_unchanged=True,new_additional_test_started=False,
        role='ER1 completed; new critical-path architectural EU source reviewed, program phase remains dormant')
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('status','candidate_manifest_sha256','source_groups',
        'compound_clocked_blocks_text_equal','new_declared_state_bits','tests_started','adopted')}))


if __name__=='__main__':
    main()
