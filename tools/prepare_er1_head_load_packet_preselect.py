"""Prepare saved and head load packets before the actual head-response event."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A90_lsq_allocation_slot_preselect'
TARGET = BASE/'A91_head_load_packet_preselect'
REVIEW = BASE/'A91_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '48ab520879bc6dd259f481507e15cff5eacd75f29b6fdc7ce7a67fd0c8f4423d'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer HEAD_LOAD_IDENTITY_QUERY = 0,'
    text = once(original, marker, marker+'\n    parameter integer HEAD_LOAD_PACKET_PRESELECT = 0,')
    text = once(text, '    localparam integer REPORT_IDENTITY_WIDTH=ROB_TAG_WIDTH+REPORT_ROB_QUERY_WIDTH;',
        '''    localparam integer REPORT_IDENTITY_WIDTH=(HEAD_LOAD_PACKET_ACTIVE!=0) ?
        REPORT_WIDTH : ROB_TAG_WIDTH+REPORT_ROB_QUERY_WIDTH;
    localparam integer SAVED_IDENTITY_QUERY_LSB=(HEAD_LOAD_PACKET_ACTIVE!=0) ? REPORT_BASE_WIDTH : ROB_TAG_WIDTH;''')
    marker = '''        (REPORT_ROB_PREDECODE!=0) && HEAD_STORE_ACK_ACTIVE;'''
    text = once(text, marker, marker+'''
    localparam integer HEAD_LOAD_PACKET_ACTIVE=(HEAD_LOAD_PACKET_PRESELECT!=0) && HEAD_LOAD_IDENTITY_ACTIVE;
    localparam integer HEAD_PACKET_META_WIDTH=TAG_WIDTH+PHYS_ADDR_WIDTH+2;
    wire [LSQ_ENTRIES*HEAD_PACKET_META_WIDTH-1:0] head_packet_metadata_rows;
    wire [HEAD_PACKET_META_WIDTH-1:0] head_packet_metadata;
    wire [REPORT_BASE_WIDTH-1:0] prepared_report_payload;
    generate if(HEAD_LOAD_PACKET_ACTIVE!=0) begin:g_head_load_packet_metadata
        // ROB identity is reused from the existing head reader. Only the
        // remaining saved metadata needs this additional combinational read.
        rv32_frequency_array_read #(.WIDTH(HEAD_PACKET_META_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) head_reader (
            .rows_i(head_packet_metadata_rows),.index_i(head_reg),.value_o(head_packet_metadata));
        wire [REPORT_BASE_WIDTH-1:0] head_packet={
            head_packet_metadata[TAG_WIDTH+PHYS_ADDR_WIDTH+1],
            head_packet_metadata[TAG_WIDTH+PHYS_ADDR_WIDTH],
            head_packet_metadata[TAG_WIDTH +: PHYS_ADDR_WIDTH],
            dcache_resp_error_i,payload_response_value,
            head_packet_metadata[0 +: TAG_WIDTH],store_ack_rob_query_tag_o};
        // Head choice implies original report-valid; absent any valid saved
        // or held row the normal tree is0. No second wide validity mask needed.
        assign prepared_report_payload=load_report_identity_head_o ?
            head_packet : saved_identity_tree[1][0 +: REPORT_BASE_WIDTH];
    end else begin:g_original_load_packet
        assign head_packet_metadata=0;
        assign prepared_report_payload=report_payload_tree[1][0 +: REPORT_BASE_WIDTH];
    end endgenerate''')
    marker = '''                wire [REPORT_WIDTH-1:0] report_payload;'''
    text = once(text, marker, '''                wire [REPORT_BASE_WIDTH-1:0] saved_report_payload={
                    row_cancel,!retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};
                if(HEAD_LOAD_PACKET_ACTIVE!=0) begin:g_head_packet_metadata
                    assign head_packet_metadata_rows[report_row*HEAD_PACKET_META_WIDTH +: HEAD_PACKET_META_WIDTH]={
                        row_cancel,!retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                        make_lsq_tag(report_row,generation_mem[report_row])};
                end else begin:g_no_head_packet_metadata
                    assign head_packet_metadata_rows[report_row*HEAD_PACKET_META_WIDTH +: HEAD_PACKET_META_WIDTH]=0;
                end
'''+marker)
    marker = '''                    assign saved_identity_tree[REPORT_ROWS+report_row]=
                        {REPORT_IDENTITY_WIDTH{saved_grant}} &
                        {report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],rob_tag_mem[report_row]};'''
    text = once(text, marker, '''                    if(HEAD_LOAD_PACKET_ACTIVE!=0) begin:g_full_saved_packet
                        assign saved_identity_tree[REPORT_ROWS+report_row]=
                            {REPORT_IDENTITY_WIDTH{saved_grant}} &
                            {report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],saved_report_payload};
                    end else begin:g_original_saved_identity
                        assign saved_identity_tree[REPORT_ROWS+report_row]=
                            {REPORT_IDENTITY_WIDTH{saved_grant}} &
                            {report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],rob_tag_mem[report_row]};
                    end''')
    text = once(text, '            saved_identity_tree[1][ROB_TAG_WIDTH +: REPORT_ROB_QUERY_WIDTH]};',
        '            saved_identity_tree[1][SAVED_IDENTITY_QUERY_LSB +: REPORT_ROB_QUERY_WIDTH]};')
    marker = '        assign load_complete_rob_query_o=report_payload_tree[1][REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH];'
    text = once(text, marker, '''        if(HEAD_LOAD_PACKET_ACTIVE!=0) begin:g_prepared_packet_query
            assign load_complete_rob_query_o=load_report_identity_head_o ?
                load_report_identity_queries_o[REPORT_ROB_QUERY_WIDTH +: REPORT_ROB_QUERY_WIDTH] :
                saved_identity_tree[1][SAVED_IDENTITY_QUERY_LSB +: REPORT_ROB_QUERY_WIDTH];
        end else begin:g_original_packet_query
            assign load_complete_rob_query_o=report_payload_tree[1][REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH];
        end''')
    marker = next(line for line in text.splitlines() if line.strip().startswith('{load_complete_cancel_o,') and '=report_payload_tree' in line)
    text = once(text, marker, marker.replace('report_payload_tree[1][0 +: REPORT_BASE_WIDTH]','prepared_report_payload'))
    # Validity, slot choice, hold, capture, pop and every state command remain
    # original; only the complete packet/query preparation changes.
    marker = '    // Wide payload fields have no reset state.'
    assert text[text.index(marker):] == original[original.index(marker):]
    for marker in [
        'complete_slot_found=report_valid_tree[1];',
        'load_complete_valid_o=complete_slot_found;',
        'assign load_report_identity_head_o=fast_head_present && !report_hold_live;',
        'assign report_first[report_row]=report_hold_live_views[report_row/4]?',
        'wire capture=!reset_i && !flush_i && load_complete_valid_o && !load_complete_ready_i;']:
        assert marker in text, marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_HEAD_LOAD_IDENTITY_QUERY = '+str(default)+','
        text = once(original, marker, marker+'\n    parameter integer LSQ_HEAD_LOAD_PACKET_PRESELECT = '+str(default)+',')
        old = '.HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY)' if '/backend/' in name else '.LSQ_HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY)'
        new = '.HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT)' if '/backend/' in name else '.LSQ_HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT)'
        text = once(text, old, old+', '+new)
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_HEAD_LOAD_PACKET_PRESELECT_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_HEAD_LOAD_PACKET_PRESELECT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_HEAD_LOAD_PACKET_PRESELECT=1,
        head_load_packet_new_ff_bits=0,head_load_packet_new_sram_bits=0,head_load_packet_new_pipeline_edges=0,
        head_load_packet_additional_head_metadata_bits=24,head_load_packet_saved_candidate_width=85)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Prepare the exact full saved/held load packet and bank query independently of current response; reuse its existing A89 identity selector. Preselect head full LSQ ticket/physical destination/unretired/cancel and reuse saved head ROBtag. Actual head-fast/held choice selects complete prepared packet and original response formatted value/error. Head choice implies actual report-valid; absent a saved/held grant the normal tree is0, preserving idle0 without another wide valid mask. No per-row current-response value mux or general packet grant sits on that selected head path; actual report/capture/reclaim state and full identities remain original.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        head_load_report_public_packet_before_late_return=True,
        head_load_packet_preselect_limit='Complements A89 full live qualification by moving current head response outside per-row wide report routing, reducing late CDB/PRF physical identity and payload selection. Saved packet uses original complete state and priority; head uses existing response formatter/error. Adds combinational24-bit head metadata reader and broadens saved candidate routing from28 to85 bits in course profile; old selected tree may trim but no area/frequency claim. No new IPC edge or state.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'A89 prequalifies full identities, but the public packet still waits for per-row late report_first selection and each fast-response value/error mux before CDB/PRF write phys/tag/data. New saved candidate tree carries the exact original saved full packet plus query under the already response-independent saved/held grant. Head metadata is separately read at saved head, before current response; no same-cycle event is invented.',
            'Held-live always selects saved candidate and its original complete_value/error. Without held, fast_head_present selects actual head metadata plus exact original payload_response_value and dcache_resp_error_i. Without either, original saved priority candidate wins. Any selected normal/held row is saved complete, so original row_fast_response is0 there; fast head original row_fast_response is1 and its original packet is exactly the prepared head tuple. These cases preserve every public packet field on valid events.',
            'Head metadata packs original row_cancel,!retired,physical destination and full make_lsq_tag(row,current generation); full ROBtag reuses original saved head read. Field order remains cancel/unretired/phys/error/value/LSQtag/ROBtag, totalPHYS+ROBtag+LSQtag+35bits. Normal candidate identity tag remains lowROB_TAG_WIDTH bits, but query offset moves to REPORT_BASE_WIDTH only in full-packet mode. Public query and packet use same original head/held choice. Head choice implies fast_head_present and actual original validity; absent all valid reports, saved grants and head choice are0, so invalid outputs remain original0 without a second wide validity mask.',
            'Current full LSQ generation/valid/wait/request/type qualification and full ROB current valid/slot/GEN checks remain A89/original. Actual validity/slot choice, held capture/keep, response capture/error/format/forwarding, report-ready metadata event, accepted load/second-prefix reclaim, scalar head/count/reset/flush/recovery and all original state commands are byte-identical. Packet preparation does not consume ready or procedural public-valid outputs, avoiding new readiness/always-process feedback.',
            'Active only with A89 head identity profile, which requires A88 saved priority, head-only response mode, bank predecode and A85/A86 split ACK/head-reader path. Default0/missing profile/arbitrary-row bypass retain old packet tree and28-bit saved identity candidate. No new FF/SRAM/edge or output event capacity; standalone optional outputs remain coherent within profile.',
            'Course active mode broadens saved candidate28->85bits and adds24-bit head metadata combinational reader; old per-row response-selected public packet tree may become unused and trim, but no quantified area gain is assumed. Head read, saved arbitration, current response formatting and late final packet choice still require later aggregate timing/area measurement. No new IPC wait-edge removal; inherited A87 fast-store coverage cost/A84/A86 opportunities remain unmeasured.',
            'Manual source/packet field/ownership/hash review only; no HDL/lint/formal/simulation/synthesis/STA/unit tests. Future coherent coverage: held/stalled/saved/head reports and changing head behind buffered stores, simultaneous returns/errors/recovery, full recycled ROB/LSQ generations, retired loads, sign/size/forward merge, reset/flush/idle outputs, all parameter widths/fallback modes, actual report acceptance/reclaim and full RV32IM/course performance. Full goal still unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
