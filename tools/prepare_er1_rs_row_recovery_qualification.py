"""Move recovery qualification ahead of the existing RS selection; no HDL run."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A60_frontend_direct_word_bounds'
TARGET = BASE / 'A61_rs_row_recovery_qualification'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A61_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_reservation_station.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RECOVERY_ISSUE_RELEASE = 0,',
        '''    parameter integer RECOVERY_ISSUE_RELEASE = 0,
    // Combinational row predicate selected with the original issue payload.
    // This does not filter ready candidates or change their age/rank policy.
    parameter integer ISSUE_RECOVERY_QUALIFICATION = 0,''')
    text = once(text, '    input  wire [BE_WIDTH-1:0]           issue_ready_i,',
        '''    input  wire [BE_WIDTH-1:0]           issue_ready_i,
    input  wire [ENTRIES-1:0]            entry_recovery_qualified_i,
    output wire [BE_WIDTH-1:0]           issue_recovery_qualified_o,''')
    text = once(text, '''    localparam integer ISSUE_DATA_WIDTH=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+
        64+STORE_DATA_WIDTH+METADATA_WIDTH+SLOT_WIDTH;''',
        '''    localparam integer ISSUE_BASE_DATA_WIDTH=OP_WIDTH+32+TAG_WIDTH+PHYS_ADDR_WIDTH+
        64+STORE_DATA_WIDTH+METADATA_WIDTH+SLOT_WIDTH;
    localparam integer ISSUE_DATA_WIDTH=ISSUE_BASE_DATA_WIDTH+
        ((ISSUE_RECOVERY_QUALIFICATION!=0)?1:0);''')
    text = once(text, '''                wire [ISSUE_DATA_WIDTH-1:0] payload={
                    op_mem[issue_row],pc_mem[issue_row],rob_tag_mem[issue_row],phys_rd_mem[issue_row],
                    src1_value_effective[issue_row],src2_value_effective[issue_row],
                    store_data_mem[issue_row],metadata_mem[issue_row],issue_row[SLOT_WIDTH-1:0]};''',
        '''                wire [ISSUE_BASE_DATA_WIDTH-1:0] base_payload={
                    op_mem[issue_row],pc_mem[issue_row],rob_tag_mem[issue_row],phys_rd_mem[issue_row],
                    src1_value_effective[issue_row],src2_value_effective[issue_row],
                    store_data_mem[issue_row],metadata_mem[issue_row],issue_row[SLOT_WIDTH-1:0]};
                wire [ISSUE_DATA_WIDTH-1:0] payload;
                if(ISSUE_RECOVERY_QUALIFICATION!=0) begin:g_qualification
                    assign payload={entry_recovery_qualified_i[issue_row],base_payload};
                end else begin:g_original_payload
                    assign payload=base_payload;
                end''')
    text = once(text, '        assign issue_valid_o[issue_lane]=|selections;',
        '''        assign issue_valid_o[issue_lane]=|selections;
        if(ISSUE_RECOVERY_QUALIFICATION!=0) begin:g_selected_qualification
            assign issue_recovery_qualified_o[issue_lane]=payload_tree[1][ISSUE_BASE_DATA_WIDTH];
        end else begin:g_no_qualification
            assign issue_recovery_qualified_o[issue_lane]=1'b0;
        end''')
    text = once(text, 'issue_slot_o[issue_lane*SLOT_WIDTH +: SLOT_WIDTH]}=payload_tree[1];',
        'issue_slot_o[issue_lane*SLOT_WIDTH +: SLOT_WIDTH]}=payload_tree[1][0 +: ISSUE_BASE_DATA_WIDTH];')
    a = '    genvar entry_index;'
    b = '    // Rank policy and ready remain unchanged.'
    assert text[text.index(a):text.index(b)] == original[original.index(a):original.index(b)]
    a = '    // Allocate a contiguous prefix and choose the oldest ready entries for'
    assert text[text.index(a):] == original[original.index(a):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text

    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RECOVERY_APPLY_OLDER_ISSUE = 0,',
        '    parameter integer RECOVERY_APPLY_OLDER_ISSUE = 0,\n    parameter integer RS_ROW_RECOVERY_QUALIFICATION = 0,')
    text = once(text, '    wire [BE_WIDTH-1:0] rs_issue_allowed;',
        '''    wire [BE_WIDTH-1:0] rs_issue_allowed;
    localparam integer RS_ROW_QUALIFICATION_ACTIVE=(RS_ROW_RECOVERY_QUALIFICATION!=0) &&
        (LOCAL_EXEC_RECOVERY!=0) && (ISSUE_PIPELINE==0);
    wire [RS_ENTRIES-1:0] rs_entry_recovery_qualified;
    wire [BE_WIDTH-1:0] raw_rs_issue_recovery_qualified;''')
    start = '            // Preview uses the live head. Apply uses the captured recovery'
    end = '            assign rs_issue_ready[io_lane] = rs_issue_allowed[io_lane] &&'
    old = text[text.index(start):text.index(end)]
    new = '''            if(RS_ROW_QUALIFICATION_ACTIVE!=0) begin:g_row_qualified_issue
                assign rs_issue_allowed[io_lane]=!branch_busy_domains[0] ||
                    raw_rs_issue_recovery_qualified[io_lane];
            end else begin:g_original_issue_qualification
''' + old + '            end\n'
    text = once(text, old, new)
    marker = '    // Registered RS selection / execution boundary.'
    row_logic = '''    // Evaluate the same preview/apply predicates from saved RS row tags.
    // Ready/rank selection then carries one qualified bit beside its payload;
    // a late wakeup cannot enter a post-selection ROB generation read.
    genvar qualification_row;
    generate if(RS_ROW_QUALIFICATION_ACTIVE!=0) begin:g_rs_row_qualification
        wire [RS_ENTRIES*EXEC_RECOVERY_WIDTH-1:0] packet_views;
        rv32_frequency_control_tree #(.WIDTH(EXEC_RECOVERY_WIDTH),.LEAVES(RS_ENTRIES)) packet_tree (
            .signal_i({recovery_domains[6],recovery_descriptor_occupancy,
                recovery_descriptor_head,execution_branch_age}),.views_o(packet_views));
        for(qualification_row=0;qualification_row<RS_ENTRIES;qualification_row=qualification_row+1) begin:g_row
            wire [TAG_WIDTH-1:0] row_tag=rs_entry_rob_tag[qualification_row*TAG_WIDTH +: TAG_WIDTH];
            wire [ROB_SLOT_WIDTH-1:0] row_age=row_tag[3 +: ROB_SLOT_WIDTH]-rob_head;
            wire [ROB_SLOT_WIDTH-1:0] pending_age=recovery_tag_views[3 +: ROB_SLOT_WIDTH]-rob_head;
            wire older_preview=(RECOVERY_PREVIEW_OLDER_ISSUE!=0) && branch_pending &&
                rob_recovery_preview && !recovery_descriptor_valid && !reset_i && !flush_i &&
                rs_entry_valid[qualification_row] && row_tag[0] &&
                row_age<pending_age && row_age<rob_occupancy;
            wire older_apply;
            if(RECOVERY_APPLY_ISSUE_ACTIVE!=0) begin:g_apply
                wire [ROB_LIVE_WIDTH-1:0] row_live;
                wire row_cancel;
                rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),.index_i(row_tag[3 +: ROB_SLOT_WIDTH]),.value_o(row_live));
                rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
                    .ENABLED(1),.KILL_BRANCH(1)) age_guard (
                    .packet_i(packet_views[qualification_row*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),
                    .active_i(rs_entry_valid[qualification_row]),.tag_i(row_tag),.cancel_o(row_cancel));
                assign older_apply=branch_pending && recovery_descriptor_valid && recovery_domains[4] &&
                    !reset_i && !flush_i && rs_entry_valid[qualification_row] && row_tag[0] &&
                    row_live[ROB_GENERATION_WIDTH] &&
                    row_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==row_live[0 +: ROB_GENERATION_WIDTH] &&
                    !row_cancel;
            end else begin:g_no_apply
                assign older_apply=1'b0;
            end
            assign rs_entry_recovery_qualified[qualification_row]=older_preview || older_apply;
        end
    end else begin:g_no_row_qualification
        assign rs_entry_recovery_qualified={RS_ENTRIES{1'b0}};
    end endgenerate

'''
    text = once(text, marker, row_logic + marker)
    text = once(text, '.RECOVERY_ISSUE_RELEASE(RECOVERY_APPLY_ISSUE_ACTIVE)) rs (',
        '.RECOVERY_ISSUE_RELEASE(RECOVERY_APPLY_ISSUE_ACTIVE), .ISSUE_RECOVERY_QUALIFICATION(RS_ROW_QUALIFICATION_ACTIVE)) rs (')
    text = once(text, '        .alloc_metadata_i(rs_alloc_metadata),',
        '''        .entry_recovery_qualified_i(rs_entry_recovery_qualified),
        .issue_recovery_qualified_o(raw_rs_issue_recovery_qualified),
        .alloc_metadata_i(rs_alloc_metadata),''')
    # All execution units, flush/release ownership, ROB/LSQ and registered
    # recovery updates remain parent source, outside the combinational branch.
    a = '    genvar pipe_lane;'
    assert text[text.index(a):] == original[original.index(a):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        text = (PARENT / name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer RECOVERY_APPLY_OLDER_ISSUE = {default},',
            f'    parameter integer RECOVERY_APPLY_OLDER_ISSUE = {default},\n    parameter integer RS_ROW_RECOVERY_QUALIFICATION = {default},')
        text = once(text, '.RECOVERY_APPLY_OLDER_ISSUE(RECOVERY_APPLY_OLDER_ISSUE),',
            '.RECOVERY_APPLY_OLDER_ISSUE(RECOVERY_APPLY_OLDER_ISSUE), .RS_ROW_RECOVERY_QUALIFICATION(RS_ROW_RECOVERY_QUALIFICATION),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], RS_ROW_RECOVERY_QUALIFICATION=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], rs_row_recovery_qualification=True,
        rs_row_qualification_added_ff_bits=0,rs_row_qualification_added_sram_bits=0,
        rs_row_qualification_added_pipeline_edges=0,rs_row_qualification_payload_bits=1,
        rs_row_qualification_rob_live_ports=8,rs_row_qualification_net_extra_rob_live_ports=6)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Compute original recovery-preview age and recovery-apply full ROB valid/GEN/strict-age qualification from each registered RS row before selection. Select one qualification bit with the unchanged issue payload/rank controls. Remove the enabled post-selected-tag ROB status read and age check from backend rs_issue_allowed. Keep execution-unit guards, state/release, all defaults and other pipeline modes.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        reference_a55r2_critical_region='Dcache return -> LSQ wake -> RS pick -> selected-tag ROB live/GEN -> MDU payload',
        post_selection_rob_read_removed=True,ready_rank_policy_unchanged=True,
        rs_row_qualification_mapped_gain_unknown=True,rs_row_qualification_area_risk='Six extra 9-bit ROB status query ports plus row age guards; only 519.469102 um2 measured area margin')
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_RS_ROW_RECOVERY_QUALIFICATION_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        added_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,added_issue_payload_bits=1,
        new_rob_live_read_ports=8,removed_rob_live_read_ports=2,net_extra_rob_live_read_ports=6,
        source_arguments=[
            'Original valid/rank predicates and selection bits remain byte-exact. One selected row per issue lane follows from exact decoded ready counts and a total pair/numeric age order. For a selected valid row, its saved tag equals the issue tag and its row_valid equals issue_valid. Its preview/apply predicate therefore equals the original selected-tag predicate for binary legal station states. This is a source argument, not RTL equivalence.',
            'ROB entry valid and all 8 GEN bits still read from current ROB state, not captured early. Apply still uses registered descriptor head/occupancy/branch age and KILL_BRANCH=1; strict older, in-occupancy, reset/flush, branch_pending and descriptor/domain qualifiers are all retained. Preview retains live head/occupancy and the same age bounds.',
            'The sideband changes no ready candidate, rank, operation, source payload, valid, acceptance or release policy. Original ALU/MDU incoming/held cancellation guards and selective-flush exact-once release remain byte-exact. No qualification is stored in an RS owner, so no new recovery state or stale cached generation contract.',
            'An empty issue lane reduces all payload/sideband bits to zero, retaining original !branch_busy permission. Adding one leading payload bit leaves all base-field bit offsets and old data intact. General widths crossing a 16-bit word boundary add a selection domain; course width stays within its current final domain.',
            'Backend/core/RS default0 use original post-selection checks; course top1. Feature active only with LOCAL_EXEC_RECOVERY!=0 and ISSUE_PIPELINE==0. Registered issue mode and standalone generic RS callers ignore the new input when disabled.',
            'Structural critical-path removal is supported by measured A55R2 named STA nodes, but measured MHz/area/IPC benefit is unknown. New 8 versus old 2 live queries may exceed the 519.469102 um2 margin and may increase ROB/control fanout; further source work must address this risk before a batch measurement.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Future meaningful verification must cover same-cycle wake/issue, ordinary/preview/apply recovery, full GEN mismatch/wrap, simultaneous held cancellation and new acceptance, selective exact-once release, empty issue, MDU routing/backpressure, and default/registered parameter fallbacks.'
        ])
    write(BASE/'A61_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__ == '__main__':
    main()
