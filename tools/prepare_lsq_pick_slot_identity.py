"""Finish ER1 source-only, including explicit slot-width truncation identity."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta
from prepare_parallel_lsq_pick_packet import lsq as parallel_lsq


def lsq(text):
    return change(parallel_lsq(text),'''        assign pick_payload[LSQ_ENTRIES+query_row]=
            pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH];''',
        '''        // Match the original leaf slot assignment, including explicit
        // SLOT_WIDTH overrides, before replacing its indexed payload read.
        localparam [SLOT_WIDTH-1:0] PAYLOAD_SLOT=query_row;
        assign pick_payload[LSQ_ENTRIES+query_row]=
            pick_payload_rows[PAYLOAD_SLOT*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH];''')


def main():
    parent=ROOT/'EP_lsq_selection_payload_word_owners'
    draft=ROOT/'ER_parallel_lsq_pick_packet'
    verify_parent(parent)
    verify_parent(draft)
    lsq((parent/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8'))
    out=prepare('ER1_parallel_lsq_pick_slot_identity',parent,{'rtl/backend/rv32_lsq.v':lsq},
        'Complete packet carried through original LSQ tournament with <=16-bit choices. Leaf packet follows the original slot-width assignment even for explicit width overrides. Same binary priority/default/fields/authority/state/edges. Source only.')
    pm=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    record_delta(out,parent,pm['implemented_groups']+['lsq_parallel_pick_packet_and_choice_domains'])
    path=out/'candidate.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    data.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reused_parallel_preparation_script_sha256=hashlib.sha256((Path(__file__).parent/'prepare_parallel_lsq_pick_packet.py').read_bytes()).hexdigest(),
        measured_parent_run='F:/CPU2026CourseRuns/architecture_EP_20261005',
        measured_reference_run='F:/CPU2026CourseRuns/architecture_EP_20261005',
        preserved_draft_candidate=str(draft),preserved_draft_manifest_sha256=hashlib.sha256((draft/'candidate.json').read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        ordinary_integer_pipeline_depth=10,extra_transaction_latency_cycles=0,
        behavior='Inherits EP, including first empty-slot cache hit extra cycle. Only combinational LSQ pick changes. Original choose_left/valid/leaf slot/age/wrap/address exactly retained through packed word mux; full payload follows the same slot including default and SLOT_WIDTH truncation. All eligibility/generation/commit/recovery/selection-clock logic remains.',
        active_profile=dict(SLOT_WIDTH=4,GENERATION_WIDTH=10,ROB_TAG_WIDTH=17,
            pick_payload_width=67,pick_select_width=108,pick_select_words=7,
            internal_tournament_nodes=15,maximum_mux_bits_per_choice_leaf=16),
        source_evidence=['F:/CPU2026Proofs/EP_mapped_paths_20261005/saved_path_analysis.json',
            'F:/CPU2026Proofs/EP_existing_reports_20261005/summary.json'],
        adoption_condition='Complete source/packet priority/default/width/clock review and all justified new-path restructuring before freeze/pretest report and one overall timing measurement. No intermediate tests.')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_groups=len(data['implemented_groups']),new_state_bits=0,tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
