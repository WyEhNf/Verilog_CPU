"""Prepare ES off-tree only: circular prefix grants and one-hot packet merge."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


PREFIX = '''        if(CIRCULAR_ORDER_POWER2 && LSQ_ENTRIES>1) begin:g_prefix_pick
            // Power-of-two leaves are in ascending physical order. Within
            // each wrap class the first eligible row wins; unwrapped rows
            // precede wrapped rows. No indexed read follows this decision.
            localparam integer GROUPS=(LSQ_ENTRIES+3)/4;
            wire [LSQ_ENTRIES-1:0] unwrapped,wrapped;
            wire [GROUPS-1:0] unwrapped_any,wrapped_any,wrapped_allowed;
            wire [PICK_SELECT_WIDTH-1:0] packet_tree [1:2*LSQ_ENTRIES-1];
            assign pick_valid[1]=|request_eligible;
            rv32_frequency_control_tree #(.LEAVES(GROUPS)) wrap_class_tree (
                .signal_i(!( |unwrapped_any)),.views_o(wrapped_allowed));
            for(genvar group_id=0;group_id<GROUPS;group_id=group_id+1) begin:g_group
                localparam integer LOW=group_id*4;
                localparam integer BITS=(LSQ_ENTRIES-LOW>=4)?4:LSQ_ENTRIES-LOW;
                wire before_unwrapped,before_wrapped;
                wire [3*BITS-1:0] group_views;
                assign unwrapped_any[group_id]=|unwrapped[LOW +: BITS];
                assign wrapped_any[group_id]=|wrapped[LOW +: BITS];
                if(group_id==0) begin:g_first
                    assign before_unwrapped=1'b0;
                    assign before_wrapped=1'b0;
                end else begin:g_later
                    assign before_unwrapped=|unwrapped_any[group_id-1:0];
                    assign before_wrapped=|wrapped_any[group_id-1:0];
                end
                rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(BITS)) prefix_tree (
                    .signal_i({wrapped_allowed[group_id],before_wrapped,before_unwrapped}),
                    .views_o(group_views));
                for(genvar local_row=0;local_row<BITS;local_row=local_row+1) begin:g_row
                    localparam integer ROW=LOW+local_row;
                    wire local_before_unwrapped,local_before_wrapped;
                    wire winner,packet_grant;
                    wire [PICK_SELECT_WORDS-1:0] grant_views;
                    wire [PICK_SELECT_WIDTH-1:0] row_packet={
                        pick_slot[LSQ_ENTRIES+ROW],pick_age[LSQ_ENTRIES+ROW],
                        pick_wrap[LSQ_ENTRIES+ROW],pick_addr[LSQ_ENTRIES+ROW],
                        pick_payload[LSQ_ENTRIES+ROW]};
                    assign unwrapped[ROW]=request_eligible[ROW] && !pick_wrap[LSQ_ENTRIES+ROW];
                    assign wrapped[ROW]=request_eligible[ROW] && pick_wrap[LSQ_ENTRIES+ROW];
                    if(local_row==0) begin:g_first
                        assign local_before_unwrapped=1'b0;
                        assign local_before_wrapped=1'b0;
                    end else begin:g_later
                        assign local_before_unwrapped=|unwrapped[ROW-1:LOW];
                        assign local_before_wrapped=|wrapped[ROW-1:LOW];
                    end
                    assign winner=(unwrapped[ROW] && !group_views[local_row*3] &&
                        !local_before_unwrapped) ||
                        (wrapped[ROW] && group_views[local_row*3+2] &&
                        !group_views[local_row*3+1] && !local_before_wrapped);
                    if(ROW==LSQ_ENTRIES-1) begin:g_default
                        // Preserve the original invalid/invalid right branch:
                        // with no eligible row, root metadata is the last leaf.
                        assign packet_grant=winner || !pick_valid[1];
                    end else begin:g_present
                        assign packet_grant=winner;
                    end
                    rv32_frequency_control_tree #(.LEAVES(PICK_SELECT_WORDS)) grant_tree (
                        .signal_i(packet_grant),.views_o(grant_views));
                    for(genvar word_id=0;word_id<PICK_SELECT_WORDS;word_id=word_id+1) begin:g_word
                        localparam integer WORD_LOW=word_id*16;
                        localparam integer WORD_BITS=(PICK_SELECT_WIDTH-WORD_LOW>=16)?16:PICK_SELECT_WIDTH-WORD_LOW;
                        assign packet_tree[LSQ_ENTRIES+ROW][WORD_LOW +: WORD_BITS]=
                            {WORD_BITS{grant_views[word_id]}} & row_packet[WORD_LOW +: WORD_BITS];
                    end
                end
            end
            for(genvar merge_node=1;merge_node<LSQ_ENTRIES;merge_node=merge_node+1) begin:g_merge
                assign packet_tree[merge_node]=packet_tree[2*merge_node] | packet_tree[2*merge_node+1];
            end
            assign {pick_slot[1],pick_age[1],pick_wrap[1],pick_addr[1],pick_payload[1]}=packet_tree[1];
        end else begin:g_original_pick
'''


def lsq(text):
    start=text.index('        for (pick_node = 1; pick_node < LSQ_ENTRIES; pick_node = pick_node + 1) begin : g_pick')
    end=text.index('        // Each byte independently selects the youngest overlapping older',start)
    original=text[start:end]
    return text[:start]+PREFIX+original+'        end\n'+text[end:]


def main():
    parent=ROOT/'ER1_parallel_lsq_pick_slot_identity'
    verify_parent(parent)
    out=prepare('ES_lsq_circular_prefix_packet',parent,{'rtl/backend/rv32_lsq.v':lsq},
        'Conditional source-only alternative: power-of-two circular priority is resolved by local/group prefix grants; full packet is merged one-hot. Non-power-of-two and single-row retain ER1 tournament. No new state, cycles, eligibility or authority changes.')
    pm=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    record_delta(out,parent,pm['implemented_groups']+['lsq_circular_two_class_prefix_packet'])
    path=out/'candidate.json'
    cm=json.loads(path.read_text(encoding='utf-8'))
    cm.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        ordinary_integer_pipeline_depth=10,extra_transaction_latency_cycles=0,
        measured_reference_run='F:/CPU2026CourseRuns/architecture_EP_20261005',
        active_profile=dict(LSQ_ENTRIES=16,prefix_groups=4,rows_per_group=4,
            packet_width=108,packet_words=7,maximum_mask_bits_per_leaf=16),
        adoption_condition='Unmeasured and unadopted; first review binary circular priority, default, exact leaf-slot payload, generic fallback and unchanged clocks. Only consider if completed ER1 paths justify another complete batch; report before any testing.',
        limitations=['No HDL elaboration or simulation or formal equivalence or EDA invoked.',
            'Unknown four-state mux/one-hot behavior may differ; binary proof only.',
            'Group broadcast, masked-OR depth and area may outweigh eliminated tournament control; no MHz prediction.',
            'All EP/ER1 extra cache-hit latency remains; IPC unknown.'])
    path.write_text(json.dumps(cm,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_groups=len(cm['implemented_groups']),new_state_bits=0,tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
