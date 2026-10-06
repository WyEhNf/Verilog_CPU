"""Carry exact direct-selection row validity beside the original LSQ winner."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A76_head_only_load_completion'
TARGET = BASE / 'A77_lsq_pick_local_validity'
REVIEW = BASE / 'A77_source_review.json'
MEASURED = Path('F:/CPU2026CourseRuns/ER1_A75_tier3_20261006')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    assert sha(PARENT / 'candidate.json') == '866e76d9d715a6a535d3e8985903ecca42b1678ca687ee13a0ac236831bb6b22'
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    timing = read(MEASURED / 'result/timing_only.json')
    assert timing['source_manifest_sha256'] == '1cda2e0da846695bed9e5e98d780e4669cb925748af447caf38a76cc0a0118f8'
    assert sha(MEASURED / 'result/synth/opt/report.json') == timing['official_report_sha256']
    critical = MEASURED / 'result/synth/opt/critical_paths.json'
    assert sha(critical) == 'bde33e7b095e85fe0477c5992475d330ef5efd988bdc439f15096fb2bf2ac3ac'
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer EMPTY_SELECTION_BYPASS = 0,',
        '''    parameter integer EMPTY_SELECTION_BYPASS = 0,
    // Carry the exact current-row direct-bypass predicate with the selected
    // packet, avoiding selected slot -> second row read -> qualification.
    parameter integer PICK_LOCAL_VALIDITY = 0,''')
    text = once(text, '    localparam integer PICK_PAYLOAD_WIDTH=GENERATION_WIDTH+ROB_TAG_WIDTH+40;',
        '    localparam integer PICK_PAYLOAD_WIDTH=GENERATION_WIDTH+ROB_TAG_WIDTH+40+((PICK_LOCAL_VALIDITY!=0)?1:0);')
    text = once(text, '''    assign {pick_generation,pick_rob_tag,pick_store_data,pick_store_mask,pick_load,pick_size,pick_unsigned}=
        pick_payload[1];''', '''    wire pick_direct_allowed;
    generate if(PICK_LOCAL_VALIDITY!=0) begin:g_pick_local_payload
        assign {pick_direct_allowed,pick_generation,pick_rob_tag,pick_store_data,
                pick_store_mask,pick_load,pick_size,pick_unsigned}=pick_payload[1];
    end else begin:g_pick_original_payload
        assign pick_direct_allowed=1'b0;
        assign {pick_generation,pick_rob_tag,pick_store_data,pick_store_mask,pick_load,pick_size,pick_unsigned}=
            pick_payload[1];
    end endgenerate''')
    text = once(text, '''        assign pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH]={
            generation_mem[query_row],rob_tag_mem[query_row],data_mem[query_row],mask_mem[query_row],
            load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};''', '''        if(PICK_LOCAL_VALIDITY!=0) begin:g_local_direct_predicate
            // This row predicate travels through the SAME PAYLOAD_SLOT alias
            // and SAME choose_left muxes as generation and the load packet.
            // Its selected generation therefore equals the old second read
            // by construction, including explicit SLOT_WIDTH overrides.
            wire direct_allowed=valid_mem[query_row] && load_mem[query_row] &&
                !store_mem[query_row] && !request_sent_mem[query_row] &&
                !complete_mem[query_row] && !response_wait_mem[query_row];
            assign pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH]={
                direct_allowed,generation_mem[query_row],rob_tag_mem[query_row],data_mem[query_row],mask_mem[query_row],
                load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};
        end else begin:g_original_direct_predicate
            assign pick_payload_rows[query_row*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH]={
                generation_mem[query_row],rob_tag_mem[query_row],data_mem[query_row],mask_mem[query_row],
                load_mem[query_row],size_mem[query_row],unsigned_mem[query_row]};
        end''')
    text = once(text, '''    wire [GENERATION_WIDTH-1:0] direct_row_generation;
    wire direct_row_valid,direct_row_sent,direct_row_complete,direct_row_wait,
        direct_row_store,direct_row_commit,direct_row_load,direct_row_retired;
    rv32_frequency_array_read #(.WIDTH(SELECT_STATE_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) direct_selection_state_read (
        .rows_i(selection_state_rows),.index_i(pick_slot[1]),
        .value_o({direct_row_generation,direct_row_valid,direct_row_sent,direct_row_complete,direct_row_wait,
                  direct_row_store,direct_row_commit,direct_row_load,direct_row_retired}));''', '''    wire direct_selection_qualified;
    generate if(PICK_LOCAL_VALIDITY!=0) begin:g_pick_local_direct_state
        assign direct_selection_qualified=pick_direct_allowed;
    end else begin:g_original_direct_state
        wire [GENERATION_WIDTH-1:0] direct_row_generation;
        wire direct_row_valid,direct_row_sent,direct_row_complete,direct_row_wait,
             direct_row_store,direct_row_commit,direct_row_load,direct_row_retired;
        rv32_frequency_array_read #(.WIDTH(SELECT_STATE_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) direct_selection_state_read (
            .rows_i(selection_state_rows),.index_i(pick_slot[1]),
            .value_o({direct_row_generation,direct_row_valid,direct_row_sent,direct_row_complete,direct_row_wait,
                      direct_row_store,direct_row_commit,direct_row_load,direct_row_retired}));
        assign direct_selection_qualified=direct_row_valid && direct_row_load && !direct_row_store &&
            !direct_row_sent && !direct_row_complete && !direct_row_wait &&
            pick_generation==direct_row_generation;
    end endgenerate''')
    text = once(text, '''        direct_row_valid && direct_row_load && !direct_row_store &&
        !direct_row_sent && !direct_row_complete && !direct_row_wait &&
        pick_generation==direct_row_generation;''', '        direct_selection_qualified;')
    # Request eligibility, circular oldest winner and byte forwarding keep
    # their original expressions. No state owner, handshake, edge or alias is
    # redefined; the added bit uses the original packet width/word partition.
    for start, end in [('    genvar age_slot;', '    initial begin\n        if ((BE_WIDTH'),
                       ('    // Three independent metadata groups', 'module rv32_lsq_request_owner')]:
        assert text[text.index(start):text.index(end)] == original[original.index(start):original.index(end)]
    for marker in ['localparam [SLOT_WIDTH-1:0] PAYLOAD_SLOT=query_row;',
                   'pick_payload_rows[PAYLOAD_SLOT*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH];',
                   'wire choose_left = pick_valid[2*pick_node]',
                   'pick_addr[pick_node],pick_payload[pick_node]}=chosen_packet;',
                   'selection_lsq_tag[3+SLOT_WIDTH +: GENERATION_WIDTH]==selection_row_generation &&']:
        assert marker in text, marker
    changes[name] = text
    for name, param in [('rtl/backend/rv32_backend_joint.v','LSQ_PICK_LOCAL_VALIDITY'),
                        ('rtl/cpu_core.v','LSQ_PICK_LOCAL_VALIDITY'),
                        ('rtl/course/student_top.v','LSQ_PICK_LOCAL_VALIDITY')]:
        text = (PARENT / name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        text = once(text, '    parameter integer LSQ_EMPTY_SELECTION_BYPASS = '+str(parent['parameter_overrides']['LSQ_EMPTY_SELECTION_BYPASS'] if name.endswith('student_top.v') else 0)+',',
            '    parameter integer LSQ_EMPTY_SELECTION_BYPASS = '+str(parent['parameter_overrides']['LSQ_EMPTY_SELECTION_BYPASS'] if name.endswith('student_top.v') else 0)+',\n    parameter integer '+param+' = '+str(default)+',')
        old = '.EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS)' if '/backend/' in name else '.LSQ_EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS)'
        new = old+', '+('.PICK_LOCAL_VALIDITY' if '/backend/' in name else '.LSQ_PICK_LOCAL_VALIDITY')+'(LSQ_PICK_LOCAL_VALIDITY)'
        text = once(text, old, new)
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LSQ_PICK_LOCAL_VALIDITY_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], LSQ_PICK_LOCAL_VALIDITY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], LSQ_PICK_LOCAL_VALIDITY=1,
        lsq_pick_current_direct_validity_bit=1, lsq_direct_selected_state_second_read_removed=True,
        lsq_pick_local_validity_new_ff_bits=0, lsq_pick_local_validity_new_sram_bits=0,
        lsq_pick_local_validity_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Qualify every current LSQ row for direct load selection locally; carry the single exact predicate through the original aliased payload leaves and choose_left packet tournament. Remove the selected-slot second current-row state read and tautological same-row generation comparison from the enabled direct-selection path. Preserve held-ticket generation checks, request eligibility, oldest order, forwarding, all actual handshakes and state updates.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a75_measured_timing=dict(run=str(MEASURED), timing_sha256=sha(MEASURED / 'result/timing_only.json'),
            critical_paths_sha256=sha(critical), fmax_mhz=timing['fmax_mhz'], area_um2=timing['area_um2'],
            longest_data_arrival_ns=3.282, original_direct_state_query_anchor_ns=1.11,
            original_direct_state_qualified_anchor_ns=1.548),
        lsq_pick_local_validity_limit='Exact structural row-read dependency removed, not a measured 0.438ns gain. Predicate mux and existing tournament/address/forwarding paths remain. No IPC gain is claimed for an equal-edge timing rewrite; A76 publication gain and cumulative mapping remain unmeasured.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'], changed_files=list(changes),
        measured_timing=record['material_gain_evidence']['a75_measured_timing'],
        tests_started=False, adopted=False, added_declared_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        source_arguments=[
            'A75 top5 STA paths all start LSQ addr_mem[11][3], enter original pick tournament, use selected slot to read current direct-selection state at1.110ns, reach direct-bypass control at1.548ns, then forwarding and state endpoint3.282ns. A75 measured299.240210MHz, total35658.771398um2; IPC was still pending when this candidate was prepared.',
            'Every original pick leaf slot is age_slot truncated to SLOT_WIDTH; pick payload is read using the identical PAYLOAD_SLOT truncated alias. New local validity is inserted in those same payload rows and follows that same alias and the exact choose_left muxes. Inductively every node has slot, generation and predicate from one identical leaf. Consequently the old second state read selects the same current generation and all six relevant state bits. Its generation equality is tautological without modifying or shortening saved tag checks.',
            'Selected predicate is current valid && load && !store && !request_sent && !complete && !response_wait. Reset/flush/recovery/selection_valid, original pick_valid and pick_load remain externally required. Thus original direct-bypass truth value and offered packet are preserved, including the original row aliases for explicit SLOT_WIDTH overrides. Invalid winners may carry arbitrary current payload, but pick_valid remains0 and disables the bypass.',
            'Default option0 retains the original second-read expression and base payload width. Option1 adds one combinational packet bit, partitioned by the original <=16bit word owners. No FF/SRAM/edge, extra request, readiness condition, cancellation relaxation, FIFO depth or age priority is added. Original saved selection generation/liveness check remains unchanged.',
            'Request eligibility/older hazards, oldest tournament structure and tie behavior, forwarding selection and held byte snapshots, actual cache request/response/complete handshake, row metadata commands and scalar count/head/tail updates are byte-identical. No HDL/lint/formal/simulation/synthesis/STA/unit job run; manual source/inductive ownership reasoning does not prove full dynamic equivalence.',
            'Future complete-batch scope: all direct/held/stalled requests, simultaneous allocation/reuse, loads/stores/unknown older stores and byte forwarding, reset/flush/recovery/stale tags, empty/full/wrapped occupancy, option0/1 and widths1/2/4, valid and invalid winners, supported LSQ powers of two and explicit slot-width aliases. Net area/Fmax/IPC unknown; no claimed guaranteed saving of the observed interval.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
