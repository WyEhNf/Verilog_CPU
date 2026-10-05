"""Select one saved D store identity before late PRF/address qualification."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A82_lsq_pick_onehot'
TARGET = BASE/'A83_fast_store_identity_preselect'
REVIEW = BASE/'A83_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'c9716c1e338830f96e6eb06a6e31f9376a23b6dd54ac93331c0fa456d821fa1d'
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer FAST_STORE_COMPLETE = 0,',
        '    parameter integer FAST_STORE_COMPLETE = 0,\n    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,')
    text = once(text, '    wire [BE_WIDTH-1:0] ready_store_candidates,store_without_agu,rob_fast_store_valid;',
        '''    wire [BE_WIDTH-1:0] ready_store_candidates,store_without_agu,rob_fast_store_valid;
    wire [BE_WIDTH-1:0] potential_store_candidates,potential_store_grants;
    wire [TAG_WIDTH-1:0] preselected_store_tag;
    // Identity selection depends only on the already saved D packet. It
    // intentionally precedes PRF readiness and address-class qualification.
    rv32_frequency_event_select #(.WIDTH(TAG_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) store_identity_selector (
        .events_i(potential_store_grants),.values_i(d_tag),.write_o(),.value_o(preselected_store_tag));
    wire [BE_WIDTH-1:0] rob_fast_store_publish_valid=(FAST_STORE_IDENTITY_PRESELECT!=0) ?
        {{(BE_WIDTH-1){1'b0}},(|rob_fast_store_valid)} : rob_fast_store_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] rob_fast_store_publish_tag=(FAST_STORE_IDENTITY_PRESELECT!=0) ?
        {{((BE_WIDTH-1)*TAG_WIDTH){1'b0}},preselected_store_tag} : d_tag;''')
    old = '''            if(ready_store_lane==0) begin:g_first
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane];
            end else begin:g_later
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane] &&
                    !(|ready_store_candidates[ready_store_lane-1:0]);
            end'''
    new = '''            wire ordinary_store_metadata=(op==`RV32IM_OP_SB && size==2'd0) ||
                (op==`RV32IM_OP_SH && size==2'd1) || (op==`RV32IM_OP_SW && size==2'd2);
            assign potential_store_candidates[ready_store_lane]=(FAST_STORE_IDENTITY_PRESELECT!=0) &&
                d_valid[ready_store_lane] && d_is_store[ready_store_lane] && !d_is_load[ready_store_lane] &&
                ordinary_store_metadata && canonical_immediate &&
                d_store_data[ready_store_lane*32 +: 32]==32'b0;
            if(ready_store_lane==0) begin:g_first
                assign potential_store_grants[ready_store_lane]=potential_store_candidates[ready_store_lane];
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane] &&
                    ((FAST_STORE_IDENTITY_PRESELECT==0) || potential_store_grants[ready_store_lane]);
            end else begin:g_later
                assign potential_store_grants[ready_store_lane]=potential_store_candidates[ready_store_lane] &&
                    !(|potential_store_candidates[ready_store_lane-1:0]);
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane] &&
                    ((FAST_STORE_IDENTITY_PRESELECT!=0) ? potential_store_grants[ready_store_lane] :
                    !(|ready_store_candidates[ready_store_lane-1:0]));
            end'''
    text = once(text, old, new)
    text = once(text, '        assign ready_store_candidates={BE_WIDTH{1\'b0}};',
        '''        assign potential_store_candidates=0;
        assign potential_store_grants=0;
        assign ready_store_candidates={BE_WIDTH{1'b0}};''')
    text = once(text, '.FAST_STORE_COMPLETE(FAST_STORE_COMPLETE_ACTIVE),',
        '.FAST_STORE_COMPLETE(FAST_STORE_COMPLETE_ACTIVE), .FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT),')
    text = once(text, '.fast_store_valid_i(rob_fast_store_valid), .fast_store_tag_i(d_tag),',
        '.fast_store_valid_i(rob_fast_store_publish_valid), .fast_store_tag_i(rob_fast_store_publish_tag),')
    assert text[text.index('    // Count raw D demand') : text.index('    rv32_rob #')] == original[original.index('    // Count raw D demand') : original.index('    rv32_rob #')]
    changes[name] = text
    name = 'rtl/backend/rv32_rob.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer FAST_STORE_COMPLETE = 0,',
        '    parameter integer FAST_STORE_COMPLETE = 0,\n    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,')
    text = once(text, '    localparam integer FAST_STORE_DOMAINS=(ROB_ENTRIES+3)/4;',
        '''    // Preselected mode carries one early saved identity and one late
    // accepted event, retaining the complete current row/GEN/valid check.
    localparam integer FAST_STORE_OWNER_LANES=(FAST_STORE_IDENTITY_PRESELECT!=0) ? 1 : BE_WIDTH;
    localparam integer FAST_STORE_DOMAINS=(ROB_ENTRIES+3)/4;''')
    for old, new in [
        ('wire [FAST_STORE_DOMAINS*BE_WIDTH-1:0] fast_store_valid_views;', 'wire [FAST_STORE_DOMAINS*FAST_STORE_OWNER_LANES-1:0] fast_store_valid_views;'),
        ('wire [FAST_STORE_DOMAINS*BE_WIDTH*TAG_WIDTH-1:0] fast_store_tag_views;', 'wire [FAST_STORE_DOMAINS*FAST_STORE_OWNER_LANES*TAG_WIDTH-1:0] fast_store_tag_views;'),
        ('#(.WIDTH(BE_WIDTH),.LEAVES(FAST_STORE_DOMAINS)) valid_tree', '#(.WIDTH(FAST_STORE_OWNER_LANES),.LEAVES(FAST_STORE_DOMAINS)) valid_tree'),
        ('.signal_i(fast_store_valid_i),.views_o(fast_store_valid_views)', '.signal_i(fast_store_valid_i[FAST_STORE_OWNER_LANES-1:0]),.views_o(fast_store_valid_views)'),
        ('#(.WIDTH(BE_WIDTH*TAG_WIDTH),.LEAVES(FAST_STORE_DOMAINS)) tag_tree', '#(.WIDTH(FAST_STORE_OWNER_LANES*TAG_WIDTH),.LEAVES(FAST_STORE_DOMAINS)) tag_tree'),
        ('.signal_i(fast_store_tag_i),.views_o(fast_store_tag_views)', '.signal_i(fast_store_tag_i[FAST_STORE_OWNER_LANES*TAG_WIDTH-1:0]),.views_o(fast_store_tag_views)'),
        ('wire [BE_WIDTH-1:0] fast_store_matches;', 'wire [FAST_STORE_OWNER_LANES-1:0] fast_store_matches;'),
        ('fast_lane<BE_WIDTH;fast_lane=fast_lane+1', 'fast_lane<FAST_STORE_OWNER_LANES;fast_lane=fast_lane+1'),
        ('((command_row/4)*BE_WIDTH+fast_lane)*TAG_WIDTH', '((command_row/4)*FAST_STORE_OWNER_LANES+fast_lane)*TAG_WIDTH'),
        ('fast_store_valid_views[(command_row/4)*BE_WIDTH+fast_lane]', 'fast_store_valid_views[(command_row/4)*FAST_STORE_OWNER_LANES+fast_lane]')]:
        text = once(text, old, new)
    assert text[text.index('            wire fast_store_completed='): ] == original[original.index('            wire fast_store_completed='): ]
    for marker in ['wire target=tag_matches(tag,command_row) && store_mem[command_row] &&',
                   '(tag[GEN_LSB +: GENERATION_WIDTH] == generation_mem[slot])']:
        assert marker in text, marker
    changes[name] = text
    for name in ['rtl/cpu_core.v', 'rtl/course/student_top.v']:
        text = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        old = '    parameter integer FAST_STORE_COMPLETE = '+str(default)+','
        text = once(text, old, old+'\n    parameter integer FAST_STORE_IDENTITY_PRESELECT = '+str(default)+',')
        text = once(text, '.FAST_STORE_COMPLETE(FAST_STORE_COMPLETE),',
            '.FAST_STORE_COMPLETE(FAST_STORE_COMPLETE), .FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_FAST_STORE_IDENTITY_PRESELECT_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_IDENTITY_PRESELECT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_IDENTITY_PRESELECT=1,
        fast_store_full_identity_comparisons_at_rob32_be2=32,
        fast_store_identity_preselect_new_ff_bits=0,fast_store_identity_preselect_new_sram_bits=0,
        fast_store_identity_preselect_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Select the lowest potential ordinary store from saved D metadata before PRF readiness/address qualification. Only that identity can fast-complete with all original late conditions and actual LSQ allocation. ROB compares one complete early identity per row instead of BE identities; later stores retain RS/ALU. Original mode0 keeps lowest ready store and vector ROB ownership. No full GEN/valid check or ordered side effect is removed.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        fast_store_identity_compare_instances_before_at_rob32_be2=64,
        fast_store_identity_compare_instances_after_at_rob32_be2=32,
        fast_store_identity_preselect_limit='Saves structurally duplicated full identity comparisons/domain lanes before late allocation-valid, but adds an early TAG-width selector. If first potential store is not ready, later ready stores keep ordinary execution and may use more RS capacity than A82. Exact area, mapping timing and IPC tradeoff unknown; not a measured saving.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'A75 measured area leaves341.23um2. A79-A82 send every BE saved identity independently despite at most one logical accepted event, requiring ROB_ENTRIES*BE_WIDTH full tag targets before late valid. Course32/2 therefore64 targets. New mode preselects an identity from saved D validity/type/op/size/canonical immediate/zero explicit override, requiring only32 full targets; compare width and every8GEN bit remain unchanged.',
            'Potential grants are first-prefix mutually exclusive and independent of PRF readiness/RAM/alignment. Late ready candidates are exactly A82. store_without_agu=potential_grant AND ready_candidate: at most one store removed from RS, and actual LSQ alloc_fire remains necessary for publish. If selected store is unready, no other store is skipped or falsely completed. Later stores execute their original RS/ALU path.',
            'Preselected TAG is the unchanged saved D tag associated with the only possible fast event. Selected-valid OR reduction is used only after genuine allocation; ROB input lane0 carries that exact tag/event and higher lanes0. ROB still checks original valid/row/full GEN/store/non-rd/non-branch/non-halt and normal recovery mode. Ready/MMIO state writes and all ordinary completion/state dominance are byte-identical.',
            'Retain original vector port widths. Parameter0 preserves A82 original lowest-ready selection and BE independent targets; default standalone remains0. Unsupported fast profiles publish no event. Core-decoded legal stores have rd_we/branch/halt0, preserved store metadata and canonical12 immediate; invalid independent trace metadata combinations are not asserted to be equivalent.',
            'No FF/SRAM/edge/new port. Cost tradeoff: an early TAG-width selector versus fewer GEN comparators/tag-domain wires; excludes later-ready-store bypass when older potential store is unready. No numerical area/IPC/Fmax gain is claimed. Manual source reasoning/hashes only, no HDL/lint/formal/simulation/synthesis/STA/unit tests.',
            'Future coherent validation: first/second/both ready and unready stores, noncontiguous D after recovery, loads/branches/MDU mixtures, explicit data overrides, WB paths, actual stalls/full queues, stale GEN/reuse/reset/recovery/ordinary completion priority, MMIO terminal stores, width1/2/4, mode0/1 and all fallback profiles; full RV32IM and ordered commit requirements remain.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
