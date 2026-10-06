"""Precompute sparse LSQ allocation slots before atomic D admission."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A89_load_report_identity_prequalification'
TARGET = BASE/'A90_lsq_allocation_slot_preselect'
REVIEW = BASE/'A90_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '21dbc81c8ef633380c321ef050af447fac7994712c4998ab5e10461405ba9bec'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,',
        '''    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,
    // Optional atomic caller supplies its raw sparse memory-lane plan.
    // Whenever any actual allocation fires, its plan must equal fire_o.
    parameter integer ALLOC_SLOT_PRESELECT = 0,''')
    marker = next(line for line in text.splitlines() if 'alloc_valid_i,' in line and 'input' in line)
    text = once(text, marker, marker+'\n    input  wire [BE_WIDTH-1:0]           alloc_plan_valid_i,')
    marker = '            wire [31:0] offset=tail_reg+alloc_count_before_lane(payload_lane,alloc_fire_o);'
    text = once(text, marker, '''            wire [BE_WIDTH-1:0] slot_plan=(ALLOC_SLOT_PRESELECT!=0) ? alloc_plan_valid_i : alloc_fire_o;
            wire [31:0] offset=tail_reg+alloc_count_before_lane(payload_lane,slot_plan);''')
    marker = '''            assign physical_alloc_slots[physical_lane*SLOT_WIDTH +: SLOT_WIDTH]=
                alloc_lsq_tag_o[physical_lane*TAG_WIDTH+TAG_SLOT_LSB +: SLOT_WIDTH];'''
    text = once(text, marker, '''            assign physical_alloc_slots[physical_lane*SLOT_WIDTH +: SLOT_WIDTH]=
                (ALLOC_SLOT_PRESELECT!=0) ? payload_alloc_slot[physical_lane] :
                alloc_lsq_tag_o[physical_lane*TAG_WIDTH+TAG_SLOT_LSB +: SLOT_WIDTH];''')
    # Public tags/fire/count and all state command/ownership priorities stay
    # original. Only allocation index preparation is replaced in active mode.
    for start,end in [
        ('    always @* begin\n        // Allocation/response temporaries retain unconditional defaults.','    // transaction owner.'),
        ('    genvar metadata_row,metadata_lane;','endmodule')]:
        assert text[text.index(start):text.index(end)] == original[original.index(start):original.index(end)]
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = '+str(default)+','
        text = once(original, marker, marker+'\n    parameter integer LSQ_ALLOC_SLOT_PRESELECT = '+str(default)+',')
        if '/backend/' in name:
            marker = '    wire [BE_WIDTH-1:0] d_lsq_need=d_valid & (d_is_load | d_is_store);'
            text = once(text, marker, marker+'''
    localparam integer LSQ_ALLOC_SLOT_PRESELECT_ACTIVE=(LSQ_ALLOC_SLOT_PRESELECT!=0) &&
        (DISPATCH_PIPELINE!=0) && (DISPATCH_ELASTIC!=0);''')
            text = once(text, '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS)',
                '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT_ACTIVE)')
            text = once(text, '.alloc_valid_i(lsq_alloc_valid),',
                '.alloc_valid_i(lsq_alloc_valid), .alloc_plan_valid_i(d_lsq_need),')
        else:
            text = once(text, '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS)',
                '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .LSQ_ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LSQ_ALLOCATION_SLOT_PRESELECT_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_ALLOC_SLOT_PRESELECT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_ALLOC_SLOT_PRESELECT=1,
        lsq_alloc_slot_preselect_new_ff_bits=0,lsq_alloc_slot_preselect_new_sram_bits=0,lsq_alloc_slot_preselect_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'For original saved elastic atomic dispatch, precompute compacted LSQ allocation slots from saved tail and raw sparse D memory-lane demand before late D admission. Payload/metadata and physical-destination row decodes use those slots with original actual fire qualifiers. Public allocation tags/fire/count, full GEN and all state commands/priorities remain original. Disabled/non-atomic backend retains actual-fire prefix addressing.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        late_d_admission_removed_from_lsq_slot_prefix_address=True,
        lsq_alloc_slot_preselect_limit='A83 measured admission/tag-valid alias3.319ns feeds metadata lane1 allocation selection3.626ns and GEN write3.830ns. Existing payload slot is tail+prefix actual_fire, serializing late admission through prefix/add/row decode. Raw saved atomic plan permits early slot decode. Actual fire and FF write guards remain late; public ticket/other allocation selection paths remain. No additional IPC edge or measured timing/area gain.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Original payload_alloc_slot is saved tail plus alloc_count_before_lane(actual_fire). Every per-row metadata allocation match consequently waits for preceding late fires, prefix arithmetic and row decode. New active slots use raw saved sparse memory plan before D admission, then the original actual fire separately qualifies each original row write. Physical-destination slot uses same planned index rather than actual-fire-gated public ticket bits.',
            'Backend enables only with saved DISPATCH_PIPELINE and DISPATCH_ELASTIC. Raw plan=d_valid & (d_is_load|d_is_store); actual LSQ alloc_valid=rawplan & replicated d_admit. d_admit requires original total memory demand<=saved LSQ free count and excludes reset/flush/busy. If admit0, every actual fire is0. If admit1, every raw memory lane fits original LSQ loop before its capacity check, so actual_fire=rawplan. Thus on every actual fire, every predecessor fire prefix equals saved plan prefix and planned slot equals original actual slot.',
            'Sparse lane ordering, original tail wrap, per-lane actual fire, all allocation payload/tag/full GEN, reset/flush/recovery/pop/reclaim/head/count and pre-edge capacity remain unchanged. Only metadata/payload and physical slot preparation consume raw plan. Nonadmitted planned indices cannot write any row; a full queue cannot borrow a same-edge pop row. Plan paths depend only on saved D metadata/tail, never current PRF/CDB or allocation results, so no new dispatch feedback loop.',
            'Default0 and non-atomic backend use old actual-fire prefix and original public ticket bits. Optional standalone LSQ enabled input contract requires alloc_plan_valid_i equal actual fire vector whenever any allocation fires; contradictory component inputs are not claimed equivalent. Course wrapper supplies this contract algebraically through original atomic admission. Unsupported sparse packets still execute their original full admission/handshake rules.',
            'No new FF/SRAM/edge/adder/port capacity; original prefix arithmetic is retimed as combinational input preparation, with extra raw-plan wiring and possible changed sharing/fanout. Actual admission->allocation grant->write enable still remains, as do original public ticket preparation and allocation-load bypass. Mapping/area/Fmax and inherited A84-A89 coverage remain unmeasured.',
            'Source/ownership review only; no HDL/lint/formal/simulation/synthesis/STA/unit test. Future coherent coverage includes all sparse 1/2/4-lane plans, full/near-full/empty/wrapped queue, packet hold/replacement, simultaneous pop/allocate and current source WB, reset/flush/recovery, standalone/default/non-atomic profiles, full generations, physical destination/report identity and course/full RV32IM correctness. Full objective remains unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
