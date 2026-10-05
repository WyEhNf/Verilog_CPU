"""Separate planned LSQ allocation identity from its actual acceptance event."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A106_report_recovery_circular_compare'
TARGET = BASE/'A107_allocation_payload_preselect'
REVIEW = BASE/'A107_source_review.json'
FLAG = 'LSQ_ALLOC_PAYLOAD_PRESELECT'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == 'b73997a083925df36f827bc80dd3c9117b8d72f53c66d66bf6a97bd2c90f8e93'
    parent = read(PARENT/'candidate.json')
    assert not parent['tests_started'] and not parent['adopted']
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    files = ['rtl/backend/rv32_lsq.v', 'rtl/backend/rv32_backend_joint.v', 'rtl/cpu_core.v', 'rtl/course/student_top.v']
    originals = {n:(PARENT/n).read_text(encoding='utf-8') for n in files}
    texts = dict(originals)
    for name in files[1:]:
        default = 1 if name.endswith('student_top.v') else 0
        old = f'    parameter integer LSQ_ALLOC_SLOT_PRESELECT = {default},'
        texts[name] = once(texts[name], old, old+f'\n    parameter integer {FLAG} = {default},')
        if name != files[1]:
            old = '.LSQ_ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT),'
            texts[name] = once(texts[name], old, old+f' .{FLAG}({FLAG}),')

    name = files[0]
    old = '    parameter integer ALLOC_SLOT_PRESELECT = 0,'
    texts[name] = once(texts[name], old, old+'\n    parameter integer ALLOC_PAYLOAD_PRESELECT = 0,')
    old = '    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_lsq_tag_o,'
    texts[name] = once(texts[name], old, old+'''
    // Private payload is observed only with the original alloc_fire event.
    // The planned slot/full GEN can precede that late acceptance decision.
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] alloc_payload_tag_o,''')
    old = '''            assign payload_alloc_slot[payload_lane]=(offset>=LSQ_ENTRIES)?offset-LSQ_ENTRIES:offset;'''
    texts[name] = once(texts[name], old, old+'''
            if(ALLOC_PAYLOAD_PRESELECT!=0 && ALLOC_SLOT_PRESELECT!=0) begin:g_planned_identity
                assign alloc_payload_tag_o[payload_lane*TAG_WIDTH +: TAG_WIDTH]=
                    make_lsq_tag(payload_alloc_slot[payload_lane],
                        generation_next_mem[payload_alloc_slot[payload_lane]]);
            end else begin:g_original_identity
                assign alloc_payload_tag_o[payload_lane*TAG_WIDTH +: TAG_WIDTH]=
                    alloc_lsq_tag_o[payload_lane*TAG_WIDTH +: TAG_WIDTH];
            end''')
    old = '''                alloc_lsq_tag_o[early_lane*TAG_WIDTH+3 +: SLOT_WIDTH],
                alloc_lsq_tag_o[early_lane*TAG_WIDTH +: TAG_WIDTH],'''
    texts[name] = once(texts[name], old, '''                alloc_payload_tag_o[early_lane*TAG_WIDTH+3 +: SLOT_WIDTH],
                alloc_payload_tag_o[early_lane*TAG_WIDTH +: TAG_WIDTH],''')
    # This broad suffix contains row payload/metadata owners and every old
    # scalar sequential process. Only an independent private assignment above
    # it changes; all write events/priority/reset/recovery equations stay exact.
    marker = '        for(payload_row=0;payload_row<LSQ_ENTRIES;payload_row=payload_row+1) begin:g_payload_row'
    assert texts[name][texts[name].index(marker):] == originals[name][originals[name].index(marker):]
    start = '    always @* begin\n        // Allocation/response temporaries retain unconditional defaults.'
    end = '    // Admission is resolved beside bounded output groups.'
    assert texts[name][texts[name].index(start):texts[name].index(end)] == originals[name][originals[name].index(start):originals[name].index(end)]

    name = files[1]
    old = '    wire [BE_WIDTH*TAG_WIDTH-1:0] lsq_alloc_tag;'
    texts[name] = once(texts[name], old, old+'\n    wire [BE_WIDTH*TAG_WIDTH-1:0] lsq_alloc_payload_tag;')
    old = '    localparam integer RS_ELASTIC_SKIP_CAPACITY_ACTIVE='
    texts[name] = once(texts[name], old, '''    localparam integer LSQ_ALLOC_PAYLOAD_PRESELECT_ACTIVE=(LSQ_ALLOC_PAYLOAD_PRESELECT!=0) &&
        LSQ_ALLOC_SLOT_PRESELECT_ACTIVE;
'''+old)
    old = '.ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT_ACTIVE),'
    texts[name] = once(texts[name], old, old+' .ALLOC_PAYLOAD_PRESELECT(LSQ_ALLOC_PAYLOAD_PRESELECT_ACTIVE),')
    old = '.alloc_lsq_tag_o(lsq_alloc_tag),'
    texts[name] = once(texts[name], old, old+' .alloc_payload_tag_o(lsq_alloc_payload_tag),')
    old = '.alloc_is_store_i(d_is_store),.alloc_lsq_tag_i(lsq_alloc_tag),'
    texts[name] = once(texts[name], old, '.alloc_is_store_i(d_is_store),.alloc_lsq_tag_i(lsq_alloc_payload_tag),')
    old = '        .signal_i(lsq_alloc_tag),.views_o(d_rob_map_values));'
    texts[name] = once(texts[name], old, '        .signal_i(lsq_alloc_payload_tag),.views_o(d_rob_map_values));')
    for name in parent['source_sha256']:
        dest = TARGET/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, dest)
    for name, content in texts.items():
        (TARGET/name).write_text(content, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_PLANNED_LSQ_IDENTITY_SEPARATE_FROM_REAL_ALLOCATION_EVENT_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(TARGET), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'), changed_from_parent_files=files,
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], **{FLAG:1})
    record['enabled_profile'] = dict(parent['enabled_profile'],
        lsq_planned_allocation_payload=True, lsq_public_allocation_tag_unchanged=True,
        lsq_allocation_payload_uses_full_generation=True, lsq_allocation_actual_event_unchanged=True,
        lsq_allocation_payload_added_ff_bits=0, lsq_allocation_payload_added_sram_bits=0,
        lsq_allocation_payload_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Prepare full LSQ allocation tag from existing preselected sparse-lane slot and full generation_next row independently of late acceptance. Use this private tag only under unchanged actual allocation events at ROB-to-LSQ map, store RS link, and allocation-load selection. Public alloc_lsq_tag/fire/count/ready and all LSQ state equations unchanged. Default core/backend0 and active guard require original elastic dispatch+slot plan contract; other profiles select exact old tag. Real events retain all scarce-resource/flush/recovery gating.'
    ]
    write(TARGET/'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'], changed_files=files, tests_started=False,
        new_declared_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        public_lsq_allocator_byte_identical=True, lsq_payload_and_metadata_state_suffix_byte_identical=True,
        source_arguments=[
            'Original existing ALLOC_SLOT_PRESELECT contract states: whenever any actual allocation fires, raw alloc_plan_valid_i must equal fire_o. Backend passes d_lsq_need and actualvalid=d_lsq_need&d_admit. Elastic d_admit includes total sparse memory demand<=lsq_free_count, so all memory lanes fit and every need fires when admitted&&!flush; none fires otherwise. New active guard is newflag&&old slot-plan active, which requires DISPATCH_PIPELINE and DISPATCH_ELASTIC. No new admission credit is invented and no result feeds its own readiness.',
            'For any actual fired lane i, original allocator slot is tail+number of preceding fired memory lanes with the same one-wrap/truncated slot operation. Prepared payload_alloc_slot uses tail+number of preceding plan bits; equality of plan and fire gives identical slot. Both full tags call the same make_lsq_tag(slot,generation_next_mem[slot]) at the same pre-edge row, preserving every GEN,kind,valid bit, including original zero-generation raw values. The next-generation increment/zero repair state equation is untouched.',
            'ROB map d_matches imply d_valid&&actual lsq_alloc_fire&&!reset, hence private and old public tags are equal for every event participating in original priority. Store RS link allocation_packet captures slot only under actual LSQ allocation; private/public slots are equal. LSQ allocation_load_grant implies actualfire; both slot and full tag in every eligible packet therefore equal. Original event_select masks every ineligible packet and every empty choice. All selected packets, write_i and data_i observed at original state edges remain exact.',
            'For nonfiring lanes private payload may differ or refer to a nonowned slot; no actual write/selection observes it. Public alloc_lsq_tag_o remains the original conditional allocator value even during flush (original tag may be nonzero while alloc_fire=0). Original fire/count/ready/plan, allocation load grants, request/selection/hold priority, reset/flush/recovery cancellation, ROB map writes and link writes remain. Default0 or inactive slot-plan guard makes new privateoutput exactly original tag. Supported BE widths1/2/4 and LSQ power-of-two geometry keep old prefix semantics; entries smaller than width have only free-count-bounded actual events.',
            'This removes late actual-fire masking and slot/GEN query from identity payload consumers while retaining real-event controls, a structural separation at the allocation boundary. In A99 late ticket valid aliases d_rob_value_tree.signal_i[0] at2.982ns after212ps NAND3+112ps INV and then reaches LSQ state at3.253ns. New private valid is constant1 and its slot/GEN are early. Original public tag data may be pruned where all old consumers now use private payload, but that is not assumed: area/frequency remain unmeasured. No FF/SRAM/clock edges, retired timing changes or unsafe tag truncation.',
            'Only LSQ/backend/core/top plumbing and private packet inputs change. LSQ original allocator block and complete suffix from g_payload_row through all state owners/helpers are byte-identical. Backend downstream controls and per-ROB map state are untouched; only d_rob_value_tree data and store-link payload source change under exact event equality. Main E and A105 original running source/tool/report are not modified. No HDL/lint/formal/sim/synth/STA/unit tests or CPU builds here. Full goal not achieved or adopted.'
        ], candidate_metrics=None, goal_complete=False, adopted=False)
    write(REVIEW, proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
