"""Prepare ER off-tree: route full packet in the original LSQ tournament."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


OLD_READ='''    rv32_frequency_array_read #(.WIDTH(PICK_PAYLOAD_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) pick_payload_read (
        .rows_i(pick_payload_rows),.index_i(pick_slot[1]),
        .value_o({pick_generation,pick_rob_tag,pick_store_data,pick_store_mask,pick_load,pick_size,pick_unsigned}));'''
NEW_READ='''    // The original tournament carries the complete row packet alongside
    // its winning slot. Avoid encode slot -> decode -> second payload read.
    assign {pick_generation,pick_rob_tag,pick_store_data,pick_store_mask,pick_load,pick_size,pick_unsigned}=
        pick_payload[1];'''
OLD_PICK='''            assign pick_slot[pick_node] = choose_left ? pick_slot[2*pick_node] : pick_slot[2*pick_node+1];
            assign pick_age[pick_node] = choose_left ? pick_age[2*pick_node] : pick_age[2*pick_node+1];
            assign pick_wrap[pick_node] = choose_left ? pick_wrap[2*pick_node] : pick_wrap[2*pick_node+1];
            // Carry the address alongside the winning age/slot. The cache
            // need not wait for a second binary-indexed read after selection.
            assign pick_addr[pick_node] = choose_left ? pick_addr[2*pick_node] : pick_addr[2*pick_node+1];'''
NEW_PICK='''            // All fields follow the identical original choose_left, even
            // when both children are invalid. Each final choice view owns
            // at most 16 mux bits; slot/address aliases cannot regain a wide
            // unpartitioned data-select consumer at this node.
            wire [PICK_SELECT_WORDS-1:0] choose_views;
            wire [PICK_SELECT_WIDTH-1:0] left_packet={
                pick_slot[2*pick_node],pick_age[2*pick_node],pick_wrap[2*pick_node],
                pick_addr[2*pick_node],pick_payload[2*pick_node]};
            wire [PICK_SELECT_WIDTH-1:0] right_packet={
                pick_slot[2*pick_node+1],pick_age[2*pick_node+1],pick_wrap[2*pick_node+1],
                pick_addr[2*pick_node+1],pick_payload[2*pick_node+1]};
            wire [PICK_SELECT_WIDTH-1:0] chosen_packet;
            rv32_frequency_control_tree #(.LEAVES(PICK_SELECT_WORDS)) choice_tree (
                .signal_i(choose_left),.views_o(choose_views));
            for(genvar pick_word=0;pick_word<PICK_SELECT_WORDS;pick_word=pick_word+1) begin:g_packet_word
                localparam integer LOW=pick_word*16;
                localparam integer BITS=(PICK_SELECT_WIDTH-LOW>=16)?16:PICK_SELECT_WIDTH-LOW;
                assign chosen_packet[LOW +: BITS]=choose_views[pick_word]?
                    left_packet[LOW +: BITS]:right_packet[LOW +: BITS];
            end
            assign {pick_slot[pick_node],pick_age[pick_node],pick_wrap[pick_node],
                    pick_addr[pick_node],pick_payload[pick_node]}=chosen_packet;'''


def lsq(text):
    text=change(text,'    localparam integer PICK_PAYLOAD_WIDTH=GENERATION_WIDTH+ROB_TAG_WIDTH+40;',
        '''    localparam integer PICK_PAYLOAD_WIDTH=GENERATION_WIDTH+ROB_TAG_WIDTH+40;
    localparam integer PICK_SELECT_WIDTH=2*SLOT_WIDTH+33+PICK_PAYLOAD_WIDTH;
    localparam integer PICK_SELECT_WORDS=(PICK_SELECT_WIDTH+15)/16;
    wire [PICK_PAYLOAD_WIDTH-1:0] pick_payload [1:2*LSQ_ENTRIES-1];''')
    text=change(text,OLD_READ,NEW_READ)
    text=change(text,'''            load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};
        assign candidate_state_rows''',
        '''            load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};
        assign pick_payload[LSQ_ENTRIES+query_row]=
            pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH];
        assign candidate_state_rows''')
    return change(text,OLD_PICK,NEW_PICK)


def main():
    parent=ROOT/'EP_lsq_selection_payload_word_owners'
    verify_parent(parent)
    lsq((parent/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8'))
    out=prepare('ER_parallel_lsq_pick_packet',parent,{'rtl/backend/rv32_lsq.v':lsq},
        'Route complete LSQ request payload in original oldest-first tournament and partition every slot/age/wrap/address/payload select into <=16-bit words. Remove late encoded-row payload read. Same priority/authority/state/edges; source only.')
    pm=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    record_delta(out,parent,pm['implemented_groups']+['lsq_parallel_pick_packet_and_choice_domains'])
    path=out/'candidate.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    data.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        measured_parent_run='F:/CPU2026CourseRuns/architecture_EP_20261005',
        measured_reference_run='F:/CPU2026CourseRuns/architecture_EP_20261005',
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        ordinary_integer_pipeline_depth=10,extra_transaction_latency_cycles=0,
        behavior='Inherits EP including intentional registered cache first-hit extra cycle. ER only changes combinational LSQ pick representation: identical original choose_left/valid/leaf identity, full tag and data aligned in one packet; all request hazards/live/commit/generation/selection clocks remain. No new state/transaction edge.',
        active_profile=dict(SLOT_WIDTH=4,GENERATION_WIDTH=10,ROB_TAG_WIDTH=17,
            pick_payload_width=67,pick_select_width=108,pick_select_words=7,internal_tournament_nodes=15,
            maximum_mux_bits_per_choice_leaf=16),
        source_evidence=['F:/CPU2026Proofs/EP_mapped_paths_20261005/saved_path_analysis.json',
            'F:/CPU2026Proofs/EP_existing_reports_20261005/summary.json'],
        adoption_condition='Review complete ER packet priority/default/width/clock identities, consider other new-path structural cuts, freeze and report before a single combined timing-only job. No ER test during preparation.')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_groups=len(data['implemented_groups']),new_declared_state_bits=0,tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
