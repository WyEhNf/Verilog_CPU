"""Select row age-cancel with issue payload; preserve all held-result guards."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A62_rs_direct_live_membership'
TARGET = BASE / 'A63_rs_predecode_issue_cancel'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A63_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_reservation_station.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer ISSUE_RECOVERY_QUALIFICATION = 0,',
        '    parameter integer ISSUE_RECOVERY_QUALIFICATION = 0,\n    parameter integer ISSUE_RECOVERY_CANCEL = 0,')
    text = once(text, '    output wire [BE_WIDTH-1:0]           issue_recovery_qualified_o,',
        '''    output wire [BE_WIDTH-1:0]           issue_recovery_qualified_o,
    input  wire [ENTRIES-1:0]            entry_issue_cancel_i,
    output wire [BE_WIDTH-1:0]           issue_cancel_o,''')
    text = once(text, '''    localparam integer ISSUE_DATA_WIDTH=ISSUE_BASE_DATA_WIDTH+
        ((ISSUE_RECOVERY_QUALIFICATION!=0)?1:0);''',
        '''    localparam integer ISSUE_QUALIFIED_DATA_WIDTH=ISSUE_BASE_DATA_WIDTH+
        ((ISSUE_RECOVERY_QUALIFICATION!=0)?1:0);
    localparam integer ISSUE_DATA_WIDTH=ISSUE_QUALIFIED_DATA_WIDTH+
        ((ISSUE_RECOVERY_CANCEL!=0)?1:0);''')
    text = once(text, '''                wire [ISSUE_DATA_WIDTH-1:0] payload;
                if(ISSUE_RECOVERY_QUALIFICATION!=0) begin:g_qualification
                    assign payload={entry_recovery_qualified_i[issue_row],base_payload};
                end else begin:g_original_payload
                    assign payload=base_payload;
                end''',
        '''                wire [ISSUE_QUALIFIED_DATA_WIDTH-1:0] qualified_payload;
                if(ISSUE_RECOVERY_QUALIFICATION!=0) begin:g_qualification
                    assign qualified_payload={entry_recovery_qualified_i[issue_row],base_payload};
                end else begin:g_original_payload
                    assign qualified_payload=base_payload;
                end
                wire [ISSUE_DATA_WIDTH-1:0] payload;
                if(ISSUE_RECOVERY_CANCEL!=0) begin:g_cancel_sideband
                    assign payload={entry_issue_cancel_i[issue_row],qualified_payload};
                end else begin:g_no_cancel_sideband
                    assign payload=qualified_payload;
                end''')
    text = once(text, '        assign issue_valid_o[issue_lane]=|selections;',
        '''        assign issue_valid_o[issue_lane]=|selections;
        if(ISSUE_RECOVERY_CANCEL!=0) begin:g_selected_cancel
            assign issue_cancel_o[issue_lane]=payload_tree[1][ISSUE_QUALIFIED_DATA_WIDTH];
        end else begin:g_no_cancel
            assign issue_cancel_o[issue_lane]=1'b0;
        end''')
    a = '    genvar entry_index;'
    b = '    // Rank policy and ready remain unchanged.'
    assert text[text.index(a):text.index(b)] == original[original.index(a):original.index(b)]
    a = '    // Allocate a contiguous prefix and choose the oldest ready entries for'
    assert text[text.index(a):] == original[original.index(a):]
    changes[name] = text

    for name in ('rtl/rv32i_alu.v', 'rtl/backend/rv32m_mdu_reservation_station.v'):
        original = (PARENT / name).read_text(encoding='utf-8')
        text = once(original, '    parameter integer RECOVERY_OLDER_ISSUE = 0,',
            '    parameter integer RECOVERY_OLDER_ISSUE = 0,\n    parameter integer ISSUE_RECOVERY_PREDECODE = 0,')
        text = once(text, '    input  wire                         issue_valid_i,',
            '''    input  wire                         issue_valid_i,
    input  wire                         issue_cancel_i,''')
        start = '    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),'
        position = text.index(start, text.index('    wire issue_cancel;'))
        end = text.index('\n', text.index('.cancel_o(issue_cancel));',position))
        old = text[position:end]
        new = '''    generate if(ISSUE_RECOVERY_PREDECODE!=0 && SELECTIVE_RECOVERY!=0) begin:g_predecoded_issue_cancel
        // The caller carries the same registered-packet age predicate with
        // the selected payload. Qualify it with this unit's actual valid.
        assign issue_cancel=issue_valid_i && issue_cancel_i;
    end else begin:g_original_issue_cancel
''' + old + '\n    end endgenerate'
        text = once(text, old, new)
        marker = '    wire result_visible =' if name=='rtl/rv32i_alu.v' else '    assign issue_ready_o ='
        assert text[text.index(marker):] == original[original.index(marker):]
        assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
        changes[name] = text

    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RS_ROW_LIVE_MEMBERSHIP = 0,',
        '    parameter integer RS_ROW_LIVE_MEMBERSHIP = 0,\n    parameter integer RS_PREDECODE_ISSUE_CANCEL = 0,')
    text = once(text, '    wire [RS_ENTRIES-1:0] rs_entry_current_live_match;',
        '''    localparam integer RS_ISSUE_CANCEL_PREDECODE_ACTIVE=(RS_PREDECODE_ISSUE_CANCEL!=0) &&
        RS_ROW_QUALIFICATION_ACTIVE && (RECOVERY_APPLY_OLDER_ISSUE!=0);
    wire [RS_ENTRIES-1:0] rs_entry_issue_cancel;
    wire [BE_WIDTH-1:0] raw_rs_issue_cancel;
    wire mdu_issue_cancel;
    wire [RS_ENTRIES-1:0] rs_entry_current_live_match;''')
    text = once(text, '                assign rs_entry_current_live_match[qualification_row]=row_live_match;',
        '''                assign rs_entry_current_live_match[qualification_row]=row_live_match;
                assign rs_entry_issue_cancel[qualification_row]=row_cancel;''')
    text = once(text, '                assign rs_entry_current_live_match[qualification_row]=1\'b0;',
        '''                assign rs_entry_current_live_match[qualification_row]=1'b0;
                assign rs_entry_issue_cancel[qualification_row]=1'b0;''')
    text = once(text, '        assign rs_entry_current_live_match={RS_ENTRIES{1\'b0}};',
        '''        assign rs_entry_current_live_match={RS_ENTRIES{1'b0}};
        assign rs_entry_issue_cancel={RS_ENTRIES{1'b0}};''')
    text = once(text, '.ISSUE_RECOVERY_QUALIFICATION(RS_ROW_QUALIFICATION_ACTIVE)) rs (',
        '.ISSUE_RECOVERY_QUALIFICATION(RS_ROW_QUALIFICATION_ACTIVE), .ISSUE_RECOVERY_CANCEL(RS_ISSUE_CANCEL_PREDECODE_ACTIVE)) rs (')
    text = once(text, '        .entry_recovery_qualified_i(rs_entry_recovery_qualified),',
        '''        .entry_issue_cancel_i(rs_entry_issue_cancel), .issue_cancel_o(raw_rs_issue_cancel),
        .entry_recovery_qualified_i(rs_entry_recovery_qualified),''')
    text = once(text, '    localparam integer MDU_ISSUE_PAYLOAD_WIDTH=`RV32IM_OP_WIDTH+64+TAG_WIDTH+PAW;',
        '''    localparam integer MDU_ISSUE_BASE_PAYLOAD_WIDTH=`RV32IM_OP_WIDTH+64+TAG_WIDTH+PAW;
    localparam integer MDU_ISSUE_PAYLOAD_WIDTH=MDU_ISSUE_BASE_PAYLOAD_WIDTH+
        ((RS_ISSUE_CANCEL_PREDECODE_ACTIVE!=0)?1:0);''')
    old = '''        assign mdu_values[mdu_route_lane*MDU_ISSUE_PAYLOAD_WIDTH +: MDU_ISSUE_PAYLOAD_WIDTH]={
            rs_issue_op[mdu_route_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH],
            rs_issue_src1[mdu_route_lane*32 +: 32],rs_issue_src2[mdu_route_lane*32 +: 32],
            rs_issue_tag[mdu_route_lane*TAG_WIDTH +: TAG_WIDTH],rs_issue_phys[mdu_route_lane*PAW +: PAW]};'''
    new = '''        wire [MDU_ISSUE_BASE_PAYLOAD_WIDTH-1:0] base_payload={
            rs_issue_op[mdu_route_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH],
            rs_issue_src1[mdu_route_lane*32 +: 32],rs_issue_src2[mdu_route_lane*32 +: 32],
            rs_issue_tag[mdu_route_lane*TAG_WIDTH +: TAG_WIDTH],rs_issue_phys[mdu_route_lane*PAW +: PAW]};
        if(RS_ISSUE_CANCEL_PREDECODE_ACTIVE!=0) begin:g_cancel_sideband
            assign mdu_values[mdu_route_lane*MDU_ISSUE_PAYLOAD_WIDTH +: MDU_ISSUE_PAYLOAD_WIDTH]=
                {raw_rs_issue_cancel[mdu_route_lane],base_payload};
        end else begin:g_original_payload
            assign mdu_values[mdu_route_lane*MDU_ISSUE_PAYLOAD_WIDTH +: MDU_ISSUE_PAYLOAD_WIDTH]=base_payload;
        end'''
    text = once(text, old, new)
    text = once(text, '''    rv32_frequency_event_select #(.WIDTH(MDU_ISSUE_PAYLOAD_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) mdu_payload_selector (
        .events_i(mdu_select),.values_i(mdu_values),.write_o(),
        .value_o({mdu_issue_op,mdu_issue_src1,mdu_issue_src2,mdu_issue_tag,mdu_issue_phys}));''',
        '''    wire [MDU_ISSUE_PAYLOAD_WIDTH-1:0] mdu_selected_payload;
    rv32_frequency_event_select #(.WIDTH(MDU_ISSUE_PAYLOAD_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) mdu_payload_selector (
        .events_i(mdu_select),.values_i(mdu_values),.write_o(),.value_o(mdu_selected_payload));
    assign {mdu_issue_op,mdu_issue_src1,mdu_issue_src2,mdu_issue_tag,mdu_issue_phys}=
        mdu_selected_payload[0 +: MDU_ISSUE_BASE_PAYLOAD_WIDTH];
    generate if(RS_ISSUE_CANCEL_PREDECODE_ACTIVE!=0) begin:g_mdu_selected_cancel
        assign mdu_issue_cancel=mdu_selected_payload[MDU_ISSUE_BASE_PAYLOAD_WIDTH];
    end else begin:g_no_mdu_selected_cancel
        assign mdu_issue_cancel=1'b0;
    end endgenerate''')
    for unit in ('alu','mdu'):
        text = once(text, f'.RECOVERY_OLDER_ISSUE(RECOVERY_APPLY_ISSUE_ACTIVE)) {unit} (',
            f'.RECOVERY_OLDER_ISSUE(RECOVERY_APPLY_ISSUE_ACTIVE), .ISSUE_RECOVERY_PREDECODE(RS_ISSUE_CANCEL_PREDECODE_ACTIVE)) {unit} (')
    text = once(text, '                .issue_ready_o(alu_issue_ready[alu_lane]),',
        '''                .issue_cancel_i(raw_rs_issue_cancel[alu_lane]),
                .issue_ready_o(alu_issue_ready[alu_lane]),''')
    text = once(text, '.issue_valid_i(mdu_issue_valid),',
        '.issue_valid_i(mdu_issue_valid), .issue_cancel_i(mdu_issue_cancel),')
    a = '    rv32_lsq #'
    assert text[text.index(a):] == original[original.index(a):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    for name, default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text = (PARENT/name).read_text(encoding='utf-8')
        text = once(text,f'    parameter integer RS_ROW_LIVE_MEMBERSHIP = {default},',
            f'    parameter integer RS_ROW_LIVE_MEMBERSHIP = {default},\n    parameter integer RS_PREDECODE_ISSUE_CANCEL = {default},')
        text = once(text,'.RS_ROW_LIVE_MEMBERSHIP(RS_ROW_LIVE_MEMBERSHIP),',
            '.RS_ROW_LIVE_MEMBERSHIP(RS_ROW_LIVE_MEMBERSHIP), .RS_PREDECODE_ISSUE_CANCEL(RS_PREDECODE_ISSUE_CANCEL),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination=TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],RS_PREDECODE_ISSUE_CANCEL=1)
    record['enabled_profile']=dict(parent['enabled_profile'],rs_predecode_issue_cancel=True,
        rs_issue_recovery_sideband_total_bits=2,rs_predecode_cancel_removed_unit_guards=3,
        rs_predecode_cancel_added_ff_bits=0,rs_predecode_cancel_added_sram_bits=0,
        rs_predecode_cancel_added_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Select each already-computed RS-row KILL_BRANCH age-cancel result with its unchanged issue payload. Forward it to direct ALU issue and through the unchanged MDU lane payload selector. Gate the bit with each unit actual issue_valid; remove enabled incoming-tag age decoders while retaining every held ALU/MDU/MUL/DIV cancellation guard and all state-update/accept/release rules.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        selected_tag_alu_mdu_incoming_age_decode_removed=True,precomputed_rs_row_cancel_shared=True,
        rs_cancel_sideband_actual_area_and_frequency_unknown=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_RS_PREDECODE_ISSUE_CANCEL_UNTESTED',candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        changed_files=list(changes),tests_started=False,adopted=False,added_ff_bits=0,added_sram_bits=0,
        added_pipeline_edges=0,new_issue_payload_bits=1,total_recovery_sideband_bits=2,
        removed_incoming_unit_age_guards=3,held_result_age_guards_preserved=True,
        source_arguments=[
            'A61/A62 row_cancel already applies the original rv32_execution_recovery_cancel KILL_BRANCH=1 function to the same registered recovery packet and saved RS tag. Selection remains unchanged and one-hot per lane. For any actually selected row, row_valid=1 and tag equals selected issue tag. Thus issue_valid && selected(row_cancel) equals the old cancel(active=issue_valid, selected_tag), including invalid-tag/branch-equal/younger/out-of-occupancy predicates for binary legal states.',
            'ALU actual issue_valid includes original permission, lane range, RS valid and non-M routing. MDU actual issue_valid comes from its unchanged allowed M-class lane mask. Both units mask the sideband with this actual valid; idle/disallowed/unrouted units therefore retain old cancel=0. MDU payload selector carries the bit with exactly the same lane select as op/operands/tag/physical destination.',
            'Only incoming issue-tag cancel decode moves. ALU result/shift cancellation and MDU pending/MUL/DIV cancellation, visibility, held-owner state, canceled-result replacement priorities, acceptance/backpressure and all arithmetic remain byte-exact. Full GEN checks continue in row qualification and completion owners.',
            'One new leading RS payload bit and one optional leading MDU routing payload bit are combinational; no FF/SRAM/pipeline edge. Course payloads stay in existing 16-bit selector domains. Base field bit positions, issue selections, ready/rank and release state are unchanged.',
            'New backend flag requires row qualification, direct issue, local recovery and apply-older-issue. Backend/core/RS/ALU/MDU defaults0 keep original guards; course top1. Disabled and registered issue modes ignore new sidebands. Unit SELECTIVE_RECOVERY0 still retains original disabled guard even if external predecode parameter is set.',
            'Measured A55R2 named path includes ALU issue_cancel_guard and post-selected-tag ROB live/GEN before MDU routing. A61-A63 remove those selected-tag dependencies, but mapped timing, area and IPC are not measured. Wide current-membership comparators and new control fanout remain area/timing risks.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Later batch verification must cover full RV32IM, selective recovery with old canceled result/new older accept, blocked surviving results, active MDU launch/MUL/DIV cancellation, GEN mismatch/wrap, simultaneous load wake and issue, all defaults/registered modes, official six IPC cases and full correctness suite before adoption.'
        ])
    write(BASE/'A63_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
