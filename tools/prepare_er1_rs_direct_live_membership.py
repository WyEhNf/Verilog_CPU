"""Use direct current-ROB membership predicates ahead of RS selection."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A61_rs_row_recovery_qualification'
TARGET = BASE / 'A62_rs_direct_live_membership'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A62_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RS_ROW_RECOVERY_QUALIFICATION = 0,',
        '    parameter integer RS_ROW_RECOVERY_QUALIFICATION = 0,\n    parameter integer RS_ROW_LIVE_MEMBERSHIP = 0,')
    text = once(text, '    wire [RS_ENTRIES-1:0] rs_entry_recovery_qualified;',
        '''    localparam integer RS_ROW_LIVE_MEMBERSHIP_ACTIVE=(RS_ROW_LIVE_MEMBERSHIP!=0) &&
        RS_ROW_QUALIFICATION_ACTIVE && (RECOVERY_APPLY_OLDER_ISSUE!=0);
    wire [RS_ENTRIES-1:0] rs_entry_current_live_match;
    wire [RS_ENTRIES-1:0] rs_entry_recovery_qualified;''')
    old = '''                wire [ROB_LIVE_WIDTH-1:0] row_live;
                wire row_cancel;
                rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),.index_i(row_tag[3 +: ROB_SLOT_WIDTH]),.value_o(row_live));'''
    new = '''                wire row_live_match;
                wire row_cancel;
                if(RS_ROW_LIVE_MEMBERSHIP_ACTIVE!=0) begin:g_direct_membership
                    localparam integer IDENTITY_WIDTH=ROB_SLOT_WIDTH+ROB_GENERATION_WIDTH;
                    localparam integer MEMBERSHIP_LEAVES=1<<ROB_SLOT_WIDTH;
                    localparam integer QUERY_DOMAINS=(ROB_ENTRIES+3)/4;
                    wire [QUERY_DOMAINS*IDENTITY_WIDTH-1:0] query_views;
                    wire live_tree [1:2*MEMBERSHIP_LEAVES-1];
                    rv32_frequency_control_tree #(.WIDTH(IDENTITY_WIDTH),.LEAVES(QUERY_DOMAINS)) query_tree (
                        .signal_i(row_tag[3 +: IDENTITY_WIDTH]),.views_o(query_views));
                    for(genvar member=0;member<MEMBERSHIP_LEAVES;member=member+1) begin:g_member
                        if(member<ROB_ENTRIES) begin:g_present
                            assign live_tree[MEMBERSHIP_LEAVES+member]=rob_entry_valid[member] &&
                                query_views[(member/4)*IDENTITY_WIDTH +: IDENTITY_WIDTH]==
                                {rob_entry_generation[member*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH],
                                 member[ROB_SLOT_WIDTH-1:0]};
                        end else begin:g_padding
                            assign live_tree[MEMBERSHIP_LEAVES+member]=1'b0;
                        end
                    end
                    for(genvar member_node=1;member_node<MEMBERSHIP_LEAVES;member_node=member_node+1) begin:g_or
                        assign live_tree[member_node]=live_tree[2*member_node] || live_tree[2*member_node+1];
                    end
                    assign row_live_match=row_tag[0] && live_tree[1];
                end else begin:g_original_live_read
                    wire [ROB_LIVE_WIDTH-1:0] row_live;
                    rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                        .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                        .rows_i(rob_live_rows),.index_i(row_tag[3 +: ROB_SLOT_WIDTH]),.value_o(row_live));
                    assign row_live_match=row_tag[0] && row_live[ROB_GENERATION_WIDTH] &&
                        row_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==row_live[0 +: ROB_GENERATION_WIDTH];
                end
                assign rs_entry_current_live_match[qualification_row]=row_live_match;'''
    text = once(text, old, new)
    text = once(text, '''                    !reset_i && !flush_i && rs_entry_valid[qualification_row] && row_tag[0] &&
                    row_live[ROB_GENERATION_WIDTH] &&
                    row_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==row_live[0 +: ROB_GENERATION_WIDTH] &&
                    !row_cancel;''',
        '''                    !reset_i && !flush_i && rs_entry_valid[qualification_row] &&
                    row_live_match && !row_cancel;''')
    text = once(text, '''            end else begin:g_no_apply
                assign older_apply=1'b0;
            end''',
        '''            end else begin:g_no_apply
                assign older_apply=1'b0;
                assign rs_entry_current_live_match[qualification_row]=1'b0;
            end''')
    text = once(text, '''    end else begin:g_no_row_qualification
        assign rs_entry_recovery_qualified={RS_ENTRIES{1'b0}};''',
        '''    end else begin:g_no_row_qualification
        assign rs_entry_current_live_match={RS_ENTRIES{1'b0}};
        assign rs_entry_recovery_qualified={RS_ENTRIES{1'b0}};''')
    a = '    generate if (EARLY_STORE_ADDRESS == 2) begin : g_shared_store_address'
    b = '    wire rob_mem_unsigned_mem'
    assert text[text.index(a):text.index(b)] == original[original.index(a):original.index(b)]
    a = '    genvar pipe_lane;'
    assert text[text.index(a):] == original[original.index(a):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        text = (PARENT / name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer RS_ROW_RECOVERY_QUALIFICATION = {default},',
            f'    parameter integer RS_ROW_RECOVERY_QUALIFICATION = {default},\n    parameter integer RS_ROW_LIVE_MEMBERSHIP = {default},')
        text = once(text, '.RS_ROW_RECOVERY_QUALIFICATION(RS_ROW_RECOVERY_QUALIFICATION),',
            '.RS_ROW_RECOVERY_QUALIFICATION(RS_ROW_RECOVERY_QUALIFICATION), .RS_ROW_LIVE_MEMBERSHIP(RS_ROW_LIVE_MEMBERSHIP),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        tests_started=False,adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],RS_ROW_LIVE_MEMBERSHIP=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],rs_row_direct_live_membership=True,
        rs_row_qualification_rob_live_ports=0,rs_row_qualification_net_extra_rob_live_ports=-2,
        rs_current_membership_probes=8,store_probe_reuses_rs_current_membership=False,
        rs_direct_membership_added_ff_bits=0,rs_direct_membership_added_sram_bits=0,
        rs_direct_membership_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Replace each optional 9-bit RS-row ROB valid/GEN lookup with an OR of current ROB entry valid and exact {GEN,slot} matches. Return one bit, retaining all GEN bits and padded-slot invalidation. Preserve the store probe independent live/GEN lookup on its selected store ROB tag.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        nine_bit_row_live_muxes_replaced_by_one_bit_membership=True,store_selected_tag_live_read_removed=False,
        direct_membership_actual_area_and_frequency_unknown=True,
        rs_row_qualification_area_risk='8 parallel full GEN+slot membership probes; wide live-read buses removed but net area and fanout still unmeasured')
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_RS_DIRECT_LIVE_MEMBERSHIP_UNTESTED',candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        changed_files=list(changes),tests_started=False,adopted=False,added_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,
        current_full_gen_membership_probes=8,removed_a61_nine_bit_query_ports=8,
        source_arguments=[
            'For each binary slot x, the original padded array read returns {valid[x],GEN[x]} for x<ROB_ENTRIES and zero otherwise. tag_valid && valid[x] && tag_GEN==GEN[x] is therefore exactly OR_j(tag_valid && valid[j] && {tag_GEN,x}=={GEN[j],j}). Unique constant slot j prevents multiple matches. All 8 GEN bits and tag-valid are kept; out-of-range padded slots always return false.',
            'Current ROB valid/generation state still supplies every predicate in the same cycle. This does not substitute a captured mask or assume that a saved tag must be live. Generation mismatch and slot reuse remain checked. Per-row exact match is independent from load wake/RS selection.',
            'The linked store selector returns the LSQ store ROB tag while selecting an RS base row through an allocation-owned slot link. They agree under the link invariant, but replacing the selected store tag generation check with an RS row check would rely on that invariant. The independent store live/GEN read and entire shared store-address block stay byte-exact.',
            'Source removes 8 A61 row 9-bit read paths, replacing them with 8 full GEN+slot one-bit membership probes. Relative to A60 the two original selected-issue queries disappear; new membership comparators still cost logic and are not claimed to save measured area.',
            'Full live-match sideband is zero when row qualification/apply mode is disabled. Backend/core defaults0, course top1. No new clocked block, FF, SRAM or pipeline edge.',
            'No HDL/lint/simulation/synthesis/STA/unit execution; correctness and area/frequency/IPC gains remain unmeasured. Further coverage includes arbitrary valid/GEN/slot combinations, ROB1/non-power-of-two/depth32/64, store selector linked/unlinked/stale-link recovery, invalid/no selection and old option fallbacks.'
        ])
    write(BASE/'A62_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__ == '__main__':
    main()
