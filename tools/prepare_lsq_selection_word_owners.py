"""Prepare EP source only: move existing LSQ selection payload to word owners."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


OLD_DECLARATIONS = '''    reg selection_valid,selection_load,selection_unsigned;
    reg [SLOT_WIDTH-1:0] selection_slot;
    reg [TAG_WIDTH-1:0] selection_lsq_tag;
    reg [ROB_TAG_WIDTH-1:0] selection_rob_tag;
    reg [31:0] selection_addr,selection_store_data;
    reg [1:0] selection_size;
    reg [3:0] selection_store_mask;'''
NEW_DECLARATIONS = '''    reg selection_valid;
    wire selection_load,selection_unsigned;
    wire [SLOT_WIDTH-1:0] selection_slot;
    wire [TAG_WIDTH-1:0] selection_lsq_tag;
    wire [ROB_TAG_WIDTH-1:0] selection_rob_tag;
    wire [31:0] selection_addr,selection_store_data;
    wire [1:0] selection_size;
    wire [3:0] selection_store_mask;'''
OLD_TREE = '''    wire [4:0] selection_write_views;
    rv32_frequency_control_tree #(.LEAVES(5)) selection_write_tree (
        .signal_i(selection_input_fire),.views_o(selection_write_views));'''
NEW_OWNER = '''    // Same unreset selection fields, data and clock edge. Bound each final
    // qualified enable to at most 16 payload hold muxes, including the tags.
    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72;
    rv32_frequency_word_bank #(.WIDTH(SELECTION_PAYLOAD_WIDTH)) selection_payload_owner (
        .clk_i(clk_i),.write_i(selection_input_fire),
        .data_i({pick_slot[1],make_lsq_tag(pick_slot[1],pick_generation),pick_rob_tag,
                 pick_addr[1],pick_load,pick_size,pick_unsigned,pick_store_mask,pick_store_data}),
        .data_o({selection_slot,selection_lsq_tag,selection_rob_tag,selection_addr,
                 selection_load,selection_size,selection_unsigned,selection_store_mask,selection_store_data}));'''
OLD_WRITES = '''        if(selection_write_views[0]) begin
            selection_slot<=pick_slot[1];
            selection_lsq_tag<=make_lsq_tag(pick_slot[1],pick_generation);
            selection_rob_tag<=pick_rob_tag;
        end
        if(selection_write_views[1]) selection_addr<=pick_addr[1];
        if(selection_write_views[2]) begin
            selection_load<=pick_load;selection_size<=pick_size;
            selection_unsigned<=pick_unsigned;
        end
        if(selection_write_views[3]) selection_store_mask<=pick_store_mask;
        if(selection_write_views[4]) selection_store_data<=pick_store_data;
'''


def lsq(text):
    text=change(text,OLD_DECLARATIONS,NEW_DECLARATIONS)
    text=change(text,OLD_TREE,NEW_OWNER)
    return change(text,OLD_WRITES,'')


def main():
    parent=ROOT/'EO1_registered_cache_hit_reply'
    verify_parent(parent)
    lsq((parent/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8'))
    out=prepare('EP_lsq_selection_payload_word_owners',parent,
        {'rtl/backend/rv32_lsq.v':lsq},
        'Final stable-MMIO/register-hit combination plus <=16-bit ownership of the same unreset LSQ selection payload. No additional state or LSQ stage; no EDA/tests.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['lsq_selection_payload_word_ownership'])
    path=out/'candidate.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    data.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        measured_reference_run='F:/CPU2026CourseRuns/architecture_EL1_20261005',
        behavior='Inherits stable MMIO and existing-register load-hit response boundary from EO1, including intentional +1 first empty-slot hit response cycle. Same LSQ payload bits relocate into existing word-bank module with identical write/edge/data; validity/recovery unchanged. Ordinary integer pipeline10; no additional LSQ cycle or state.',
        selection_payload_width_expression='SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72',
        active_profile_selection_payload_bits=110,maximum_payload_bits_per_enable_leaf=16,
        source_evidence=['F:/CPU2026Proofs/EL1_mapped_paths_20261005/saved_path_analysis.json',
            'F:/CPU2026Proofs/EO1_source_review_20261005/source_review.json'],
        adoption_condition='Complete final source/handshake review, freeze, and report before one combined timing-only run. No intermediate testing.')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_groups=len(data['implemented_groups']),new_tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
