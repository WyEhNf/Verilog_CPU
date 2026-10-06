"""Review the final EA-to-EF source combination without HDL or EDA execution."""
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from review_frequency_dx_sources import blocks


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    workspace=Path('E:/Verilog_cpu')
    active_path=workspace/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=json.loads(active_path.read_text(encoding='utf-8'))
    ea=ROOT/'EA_combined_control_locality'
    ef=ROOT/'EF_rob_commit_packet_domains'
    assert Path(active['candidate'])==ea and active['measurement_process_id'] is None
    assert active['current_measured_fmax_mhz']==328.20512820512823
    chain=[]
    for name in ('EA_combined_control_locality','ED_ea_shared_only_store_address',
                 'EE_lsq_direct_report_and_forward_hold','EF_rob_commit_packet_domains'):
        candidate=ROOT/name
        verify_parent(candidate)
        chain.append(dict(candidate=str(candidate),manifest_sha256=sha(candidate/'candidate.json')))
    for name,expected in active['source_sha256'].items():
        assert sha(workspace/name)==expected,name
    a=json.loads((ea/'candidate.json').read_text(encoding='utf-8'))
    b=json.loads((ef/'candidate.json').read_text(encoding='utf-8'))
    changes=[name for name,h in b['source_sha256'].items() if h!=a['source_sha256'][name]]
    assert set(changes)=={'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v',
                         'rtl/backend/rv32_lsq.v','rtl/backend/rv32_rob.v'}
    old_payload='        if(forwarding_payload_write) begin forwarding_hold_mask<=fwd_mask;forwarding_hold_data<=fwd_data;end\n'
    source_records=[]
    total=0
    for name in b['source_sha256']:
        if not name.endswith('.v'):
            continue
        old=(ea/name).read_text(encoding='utf-8')
        new=(ef/name).read_text(encoding='utf-8')
        refactor=name=='rtl/backend/rv32_lsq.v'
        if refactor:
            assert old.count(old_payload)==1 and 'forwarding_payload_write' not in new
            old=old.replace(old_payload,'',1)
            assert '.data_i({fwd_mask,fwd_data}),.data_o({forwarding_hold_mask,forwarding_hold_data}));' in new
            assert '.clk_i(clk_i),.write_i(forwarding_hold_write),' in new
        old_blocks=blocks(old)
        assert old_blocks==blocks(new),name
        total+=len(old_blocks)
        source_records.append(dict(file=name,compound_clocked_blocks=len(old_blocks),
            source_text_equal_except_relocated_36bit_forward_hold=refactor,
            all_existing_other_clocked_equations_text_equal=True))
    for name in ('rtl/backend/rv32_completion_network.v','rtl/rv32_physical_register_file.v',
                 'rtl/backend/rv32_reservation_station.v','rtl/backend/rv32_store_address_select.v'):
        assert b['source_sha256'][name]==a['source_sha256'][name]
    proof=Path('F:/CPU2026Proofs/EF_source_review_20261005')
    proof.mkdir(exist_ok=False)
    patch=''.join(''.join(difflib.unified_diff((ea/name).read_text(encoding='utf-8').splitlines(keepends=True),
        (ef/name).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile=ea.name+'/'+name,tofile=ef.name+'/'+name)) for name in changes)
    patch_path=ef/'changes_vs_measured_EA.patch'
    assert not patch_path.exists()
    patch_path.write_text(patch,encoding='utf-8')
    data=dict(status='FINAL_COMBINATION_SOURCE_REVIEW_ONLY_UNTESTED',created_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(ef),candidate_manifest_sha256=sha(ef/'candidate.json'),chain=chain,
        measured_reference='F:/CPU2026CourseRuns/architecture_EA_20261005',
        measured_reference_fmax_mhz=active['current_measured_fmax_mhz'],
        measured_reference_area_um2=active['current_measured_area_um2'],EA_worktree_inputs_verified=len(active['source_sha256']),
        changed_files_vs_EA=changes,ordinary_integer_pipeline_depth=10,new_declared_state_bits=0,
        compound_clocked_blocks_reviewed=total,source_records=source_records,
        review_scope='Source identities, compound begin/end clocked text and manual algebra/dataflow review. Single-statement clocked payload writes handled by explicit manual ownership correspondence; not HDL syntax, simulation, formal equivalence, timing or area.',
        groups=[
            dict(name='allocation_store_address_cut',reason='Actual EA critical path traverses allocation store adder after PRF. Disabled valid and payload remove that optional arithmetic chain.',tradeoff='No allocation-edge store address; shared probe throughput one per cycle, normal AGU retained. IPC delay bound unproven.'),
            dict(name='direct_lsq_report_grant',reason='Bypasses tournament binary row encode then per-row decode on the reported path.',algebra='Each valid tournament winner minimizes (wrap,row): valid-only child wins, both valid select non-wrap then left row for a tie. Direct first unwrapped eligible else first eligible returns that same minimum. No queue-state or one-hot input assumption needed for binary valid/wrap signals.'),
            dict(name='forwarding_hold_write_and_read_domains',reason='EA saved mapped leaf has 72 direct mux input pins for 36 payload bits.',algebra='Same 4 mask + 32 data unreset bits, old write expression and edge. 16/16/4 write/read groups use identical enables and operands; valid/reset/recovery/handshake unchanged.'),
            dict(name='rob_banked_commit_packet_domains',reason='EA mapped 86/82-load private cones reach commit; source bank row select masks a 197-bit packet.',algebra='New PRIORITY=0 selector computes the identical OR of masked packets with the same row fields, modulo query and final bank rotation. Holds for multiple selected rows too; no one-hot assumption.' )],
        saved_evidence=[ 'F:/CPU2026Proofs/EA_existing_reports_20261005/summary.json',
                        'F:/CPU2026Proofs/EA_mapped_paths_20261005/saved_path_analysis.json',
                        'F:/CPU2026Proofs/EA_mapped_load_census_20261005.json',
                        'F:/CPU2026Proofs/EA_high_load_cones_20261005/summary.json' ],
        caveats=[ 'No EF compiler, simulation, synthesis, STA or formal run.',
            'One-hot report selection algebra described for binary valid/wrap control; no executable four-state/parameter proof was run.',
            'Logical reachability of high-load private gates does not identify their complete Boolean function or prove timing sensitization.',
            'Clocked-text identity except relocated payload is not architectural equivalence: allocation-address availability intentionally changes.' ],
        patch=str(patch_path),patch_sha256=sha(patch_path),new_test_started=False)
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(ef),review=str(review),changed_files_vs_EA=changes,
                         compound_clocked_blocks_reviewed=total,new_test_started=False)))


if __name__=='__main__':
    main()
