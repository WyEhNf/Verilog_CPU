"""Bound fast load publication to the LSQ head and reuse exact report owners."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A75_branch_capture_phase_valid'
TARGET = BASE / 'A76_head_only_load_completion'
REVIEW = BASE / 'A76_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer LOAD_COMPLETION_BYPASS = 0,',
        '''    // 0: saved publication; 1: original arbitrary-row response bypass;
    // 2: only the queue-head response can publish/reclaim on its return edge.
    parameter integer LOAD_COMPLETION_BYPASS = 0,''')
    text = once(text, '    wire [LSQ_ENTRIES-1:0] report_eligible,report_upper,report_first;',
        '''    wire [LSQ_ENTRIES-1:0] report_eligible,report_upper,report_first;
    wire [LSQ_ENTRIES-1:0] fast_head_reports;
    wire fast_head_present=|fast_head_reports;
    wire [REPORT_GRANT_DOMAINS-1:0] fast_head_priority_views;
    rv32_frequency_control_tree #(.LEAVES(REPORT_GRANT_DOMAINS)) fast_head_priority_tree (
        .signal_i(fast_head_present),.views_o(fast_head_priority_views));''')
    text = once(text, '''                wire row_fast_response=(LOAD_COMPLETION_BYPASS!=0) &&
                    !reset_i && !flush_i && !recovery_valid_i &&''',
        '''                wire row_fast_response=(LOAD_COMPLETION_BYPASS!=0) &&
                    ((LOAD_COMPLETION_BYPASS!=2) ||
                     head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH]==report_row) &&
                    !reset_i && !flush_i && !recovery_valid_i &&''')
    text = once(text, '''                assign report_eligible[report_row]=report_valid_tree[REPORT_ROWS+report_row];''',
        '''                assign report_eligible[report_row]=report_valid_tree[REPORT_ROWS+report_row];
                // A qualified head response is the oldest eligible row.
                // Held report ownership still wins; otherwise the head's
                // one-hot match need not wait for general age arbitration.
                assign fast_head_reports[report_row]=(LOAD_COMPLETION_BYPASS==2) &&
                    row_fast_response && row_in_report_range;''')
    text = once(text, '''                assign report_first[report_row]=report_hold_live_views[report_row/4]?
                    report_hold_matches[report_row]:report_priority;''',
        '''                assign report_first[report_row]=report_hold_live_views[report_row/4]?
                    report_hold_matches[report_row]:
                    (fast_head_priority_views[report_row/4]?fast_head_reports[report_row]:report_priority);''')
    text = once(text, '''    wire metadata_pop=(occupancy_reg!=0) && head_valid &&
        ((head_load && head_complete &&
          (head_reported || (load_complete_valid_o && load_complete_ready_i && complete_slot_select==head_reg))) ||
         (head_store && head_ack && store_ack_ready_i));''',
        '''    wire head_report_accepted=load_complete_valid_o && load_complete_ready_i && complete_slot_select==head_reg;
    wire metadata_pop=(occupancy_reg!=0) && head_valid &&
        ((head_load &&
          ((head_complete && (head_reported || head_report_accepted)) ||
           ((LOAD_COMPLETION_BYPASS==2) && fast_head_present && head_report_accepted))) ||
         (head_store && head_ack && store_ack_ready_i));''')
    # Response value/format/capture, held identity, actual report payload and
    # row/scalar clearing all use their original owners/command priorities.
    for marker in [
        'wire capture=!reset_i && !flush_i && load_complete_valid_o && !load_complete_ready_i;',
        '.clk_i(clk_i),.write_i(capture),.data_i(load_complete_lsq_tag_o),.data_o(report_hold_tag)',
        'tag_matches_slot(report_hold_tag_views[(report_row/4)*TAG_WIDTH +: TAG_WIDTH],report_row);',
        'tag_matches_slot(local_tag,match_row) && response_wait_mem[match_row];',
        'response_fire = dcache_resp_valid_i && response_match;',
        'dcache_resp_ready_o = 1\'b1;',
        'wire [31:0] payload_response_value=format_relative_value(',
        'if(report_event) begin load_reported_mem_write_data[metadata_row]=1\'b1;',
        'head_reg <= advance_slot(head_reg, pop_count_calc);',
        'occupancy_reg <= occupancy_reg - pop_count_calc + alloc_count_calc;',
    ]:
        assert marker in text, marker
    tail = '    initial begin\n        if(RECLAIM_WIDTH!=1 && RECLAIM_WIDTH!=2)'
    assert text[text.index(tail):] == original[original.index(tail):]
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer LOAD_COMPLETION_BYPASS = 0,',
        '    parameter integer LOAD_COMPLETION_BYPASS = 2,')
    changes[name] = text
    backend = (PARENT / 'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    for marker in [
        'assign lsq_load_complete_ready = producer_ready[LSQ_SOURCE];',
        'producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH]',
        'producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 + ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]',
        '.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS)',
    ]:
        assert marker in backend, marker
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    tag_width = int(parent['parameter_overrides'].get('GENERATION_WIDTH', 8)) + (int(parent['parameter_overrides']['ROB_ENTRIES'])-1).bit_length() + 3
    record = dict(parent)
    record.update(status='SOURCE_HEAD_ONLY_LOAD_COMPLETION_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], LOAD_COMPLETION_BYPASS=2)
    record['enabled_profile'] = dict(parent['enabled_profile'], LOAD_COMPLETION_BYPASS=2,
        head_only_load_completion=True, head_load_accepted_return_reclaim=True,
        load_report_hold_identity_bits=tag_width+1, head_fast_new_sram_bits=0,
        general_fast_response_publication_enabled=False)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Enable bounded completion mode2: only a generation-qualified live LSQ head load may use the current cache response value/error as a completion report. Existing held-report identity wins; otherwise that head is the oldest and directly selects its payload. Reclaim on the same accepted head report, without waiting for saved complete/reported. Preserve original full response capture, formatting/forwarding, actual CDB/ROB/PRF guards, store ack and all other load report paths.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        oldest_load_formal_completion_wait_edge_removed=True,
        accepted_head_load_reclaim_wait_edge_removed=True,
        head_fast_excludes_general_return_age_arbitration=True,
        prior_general_bypass_evidence=dict(candidate='A21_credit_guaranteed_dispatch_replace',
            fmax_mhz=247.40275428847548, ipc=0.9615883182384856,
            interpretation='Earlier different source and broader batch; not a causal isolated bypass gain and not transferable to A76.'),
        head_only_load_completion_limit='Only head returns without a live held report and with downstream acceptance save an edge. Existing separate return wake already speeds dependencies. Value/status to CDB/ROB/PRF and ready to head/pop/count are new timing risks; exact gains and area unknown.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_declared_ff_bits=tag_width+1, new_sram_bits=0,
        removed_pipeline_wait_edges_for_eligible_head_load=1, new_completion_ports=0,
        source_arguments=[
            'Mode2 qualifies the original fast-response predicate additionally by saved current LSQ head equality. Original tag_matches_slot includes LSQ valid/current generation; response_wait/request_sent/load/not-store/not-complete/not-reported and reset/flush/recovery exclusions remain. Only that unique head can become fast_head_reports; row_in_report_range preserves the original logical occupancy mask.',
            'A head row has age0, so if it is eligible it is the original oldest report candidate. The original held full-tag report still wins; only without a live held report does a current head reply directly select its one-hot payload. Saved reports for other rows retain original age/wrap arbitration; non-head cache responses only become reports after their original row capture. Mode1 keeps arbitrary-row original bypass; mode0 remains saved publication.',
            'Current report uses exactly the same response byte-forward merge, signed/unsigned formatting, error, physical destination, full LSQ/ROB identities, unretired and local cancellation sidebands as the original row capture. That capture still occurs unconditionally on the response edge. Backpressure locks the original full LSQ identity and subsequently reads the saved complete/value/error packet. No separate data buffer or cache backpressure loop is added.',
            'Only actual load_complete_valid && original ready && selected row=head can authorize early head pop. For mode2 that also requires fast_head_present, head_valid/load and nonempty occupancy. Packet is consumed by the original completion owner at the edge before original metadata-pop commands clear the row. Existing CDB producer live/current-slot/full8GEN authority remains unchanged; discarded stale reports retain original drain semantics.',
            'Existing response then report then pop command priority clears complete/reported/request_sent/response_wait only after publication; count/head/second-row clears share the original pop_count. Original allocation uses pre-edge capacity, so a full queue does not simultaneously allocate into the freed row. No extra completion/ack port, store ordering change, external memory transaction identity change or speculative alias bypass occurs. Apply disables all fast responses, so recovery keeps original count/tail and kill commands.',
            'Mode2 enables the original TAG_WIDTH-bit held report tag plus one valid bit, totaling17 declared FF for the course ROB32/GEN8 profile. No SRAM or extra result data buffer. Older load-response wake is already enabled and unchanged, so this targets formal commit and queue release, not a claimed second dependency-latency improvement. New fast payload/status and CDB-ready-to-pop paths need future STA; old A21 broad bypass reached247MHz and cannot be blindly reopened.',
            'Manual temporal ownership/source/hash reasoning only, no HDL/formal/unit/simulation/synthesis/STA run. Future coverage: head live load response accepted/stalled/held, non-head return, simultaneous older held report, complete/head reported fallback, error and partial byte/sign forwarding, stale LSQ/ROB GEN, full/empty/wrapped queue, second previously-reported row, same-edge allocation/retirement, recovery/reset/flush, widths1/2/4, modes0/1/2 and head-later external responses. Actual IPC/area/frequency unknown.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
