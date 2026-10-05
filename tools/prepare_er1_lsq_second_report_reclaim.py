"""Reclaim a just-reported second prefix load; no HDL execution."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A70_recovery_rob_credit'
TARGET = BASE / 'A71_lsq_second_report_reclaim'
REVIEW = BASE / 'A71_source_review.json'


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
    text = once(original, '    parameter integer RECLAIM_WIDTH = 1,',
        '''    parameter integer RECLAIM_WIDTH = 1,
    // Allow the original single completion handshake to retire the second
    // completed load on an edge that already releases the first prefix row.
    parameter integer SECOND_REPORT_RECLAIM = 0,''')
    old = '''        // No second completion/acknowledgement port: this next load has
        // already published its full-tag completion on an earlier edge.
        // Stores remain queued until their original head-only ack handshake.
        assign metadata_second_pop=metadata_pop && occupancy_reg>=2 &&
            !reset_i && !flush_i && !recovery_valid_i && (&next_state);'''
    new = '''        // A second prefix load must be complete and published. The
        // existing single report port can publish this exact row on the
        // current edge; no extra completion/acknowledgement port is created.
        // Stores remain queued until their original head-only ack handshake.
        wire next_reported_now=load_complete_valid_o && load_complete_ready_i &&
            complete_slot_select==next_head;
        wire next_reclaimable=(SECOND_REPORT_RECLAIM!=0)?
            ((&next_state[3:1]) && (next_state[0] || next_reported_now)):
            (&next_state);
        assign metadata_second_pop=metadata_pop && occupancy_reg>=2 &&
            !reset_i && !flush_i && !recovery_valid_i && next_reclaimable;'''
    text = once(text, old, new)
    # Report arbitration/payload/locks and all forwarding/issue rules remain
    # byte exact. Metadata rows already share the same second-pop clear event.
    start = '    // Three independent metadata groups per physical LSQ row.'
    assert text[:text.index(start)].replace(
        '    // Allow the original single completion handshake to retire the second\n'
        '    // completed load on an edge that already releases the first prefix row.\n'
        '    parameter integer SECOND_REPORT_RECLAIM = 0,\n', '') == original[:original.index(start)]
    tail = '    initial begin\n        if(RECLAIM_WIDTH!=1 && RECLAIM_WIDTH!=2)'
    assert text[text.index(tail):] == original[original.index(tail):]
    for marker in [
        'head_reg <= advance_slot(head_reg, pop_count_calc);',
        'occupancy_reg <= occupancy_reg - pop_count_calc + alloc_count_calc;',
        'wire pop_event=metadata_events[metadata_row*7+6] &&',
        '(second_pop_views[metadata_row] &&',
        'head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==PREVIOUS_ROW)',
        'wire report_event=metadata_events[metadata_row*7+1] && complete_slot_select==metadata_row;',
    ]:
        assert marker in text, marker
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer LSQ_RECLAIM_WIDTH = 1,',
        '    parameter integer LSQ_RECLAIM_WIDTH = 1,\n    parameter integer LSQ_SECOND_REPORT_RECLAIM = 0,')
    text = once(text, '.RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),',
        '.RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .SECOND_REPORT_RECLAIM(LSQ_SECOND_REPORT_RECLAIM),')
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        text = (PARENT / name).read_text(encoding='utf-8')
        prior = 1 if default == 0 else 2
        text = once(text, f'    parameter integer LSQ_RECLAIM_WIDTH = {prior},',
            f'    parameter integer LSQ_RECLAIM_WIDTH = {prior},\n    parameter integer LSQ_SECOND_REPORT_RECLAIM = {default},')
        text = once(text, '.LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),',
            '.LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .LSQ_SECOND_REPORT_RECLAIM(LSQ_SECOND_REPORT_RECLAIM),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LSQ_SECOND_REPORT_RECLAIM_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], LSQ_SECOND_REPORT_RECLAIM=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], lsq_second_current_report_reclaim=True,
        lsq_second_report_new_ff_bits=0, lsq_second_report_new_sram_bits=0,
        lsq_report_ports_unchanged=True, lsq_store_ack_order_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'For two-row prefix reclaim, permit the second completed load to satisfy its publication requirement through the original current-edge report handshake. Original first-row reclaim, single report arbitration/hold/full tag/payload, store acknowledgement, actual allocation and all row/scalar pop updates stay unchanged; no extra port or state is added.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        second_prefix_load_current_report_wait_removed=True,
        second_report_reclaim_limit='Only applies when first row can already pop and second completed load owns an accepted report on this same edge. Original A36 towers LSQ-full750/5804 samples is an opportunity scale, not A71 gain. Added report-to-second-pop path needs future STA.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        source_arguments=[
            'Original first-row metadata_pop already permits a completed head load to reclaim through the current load_complete_valid/ready and complete_slot_select=head handshake. The second row previously required load_reported_mem from an earlier edge. This candidate applies the same current-report rule to exactly next_head, keeping its valid/load/complete requirements.',
            'One report port remains. If it selects head, next_reported_now is false. If head already published or is an acknowledged store, the report port may select next_head; that packet is consumed before the same edge clears its row. Both prefix rows then release. If report is held/backpressured, ready is false and second row stays allocated. No load is cleared before an accepted report, no additional report is created, and store rows cannot become second reclaim targets.',
            'The original full LSQ generation/range/live report selection and held report lock are unchanged. The accepted packet still carries its original ROB tag, physical destination, value/error and recovery cancel/unretired sidebands to the original completion owner. Existing tag-qualified return/wake/report readiness controls remain authoritative.',
            'Second-pop still requires occupancy>=2 and !reset/!flush/!recovery. Existing scalar pop_count, head advancement and occupancy subtraction already consume one shared pop count. Existing second_pop_views select exactly head and its circular successor for metadata clear. Allocation continues to use pre-edge free slots, so no same-row full replacement or new allocation feedback loop is introduced. Next wrap uses the original power-of-two depth requirement.',
            'Data/metadata command priority is unchanged: report event can set reported, then existing pop event clears valid/request_sent/complete/reported/ack. The report packet was already accepted into the downstream owner at that edge. Metadata for other rows, request pipeline, store commitment, forwarding hazards, older-store disambiguation and all memory transaction identities remain byte exact.',
            'Source reasoning/hash audit only; IPC and mapped area/frequency unmeasured. No FF/SRAM/pipeline edge or completion port added. The new complete-slot equality and ready predicate feed the existing second-pop/count path; timing must be assessed in a future reported coherent batch. Future coverage: head-old-reported/second-current-report, head-store-ack/second-load-report, head-current-report only, report-stall/held-row, circular head15/next0, occupancy1/2/full, second store/incomplete, cancellation/reset/recovery, load response same edge, widths1/2/4, RECLAIM_WIDTH1 and option0.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
