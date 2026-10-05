"""Source-only LSQ reclamation: original head plus an already-reported next load."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A40_compact_gshare_parallel_feedback'
TARGET = BASE / 'A41_lsq_two_prefix_reclaim'
PROFILE = Path('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    profile = read(PROFILE)
    towers = next(r for r in profile['results'] if r['name'] == 'perf_towers')
    assert towers['cycles_exact_a36'] and towers['official_answer_passed']
    assert towers['observations']['lsq_full'] == 750
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,',
                '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,\n    parameter integer RECLAIM_WIDTH = 1,')
    text = once(text, '''    wire metadata_forward=candidate_found && candidate_load &&''',
                '''    wire metadata_second_pop;
    wire [LSQ_ENTRIES-1:0] second_pop_views;
    wire [1:0] metadata_pop_count=metadata_pop?
        (metadata_second_pop?2'd2:2'd1):2'd0;
    generate if(RECLAIM_WIDTH==2 && LSQ_ENTRIES>1) begin:g_two_prefix_reclaim
        wire [SLOT_WIDTH-1:0] next_head=head_reg+1'b1;
        wire [LSQ_ENTRIES*4-1:0] rows;
        wire [3:0] next_state;
        for(genvar reclaim_row=0;reclaim_row<LSQ_ENTRIES;reclaim_row=reclaim_row+1) begin:g_row
            assign rows[reclaim_row*4 +: 4]={valid_mem[reclaim_row],load_mem[reclaim_row],
                complete_mem[reclaim_row],load_reported_mem[reclaim_row]};
        end
        rv32_frequency_array_read #(.WIDTH(4),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) next_read (
            .rows_i(rows),.index_i(next_head),.value_o(next_state));
        // No second completion/acknowledgement port: this next load has
        // already published its full-tag completion on an earlier edge.
        // Stores remain queued until their original head-only ack handshake.
        assign metadata_second_pop=metadata_pop && occupancy_reg>=2 &&
            !reset_i && !flush_i && !recovery_valid_i && (&next_state);
        rv32_frequency_control_tree #(.LEAVES(LSQ_ENTRIES)) pop_tree (
            .signal_i(metadata_second_pop),.views_o(second_pop_views));
    end else begin:g_single_prefix_reclaim
        assign metadata_second_pop=1'b0;
        assign second_pop_views=0;
    end endgenerate
    initial begin
        if(RECLAIM_WIDTH!=1 && RECLAIM_WIDTH!=2)
            $fatal(1,"LSQ reclaim width must be1/2");
    end
    wire metadata_forward=candidate_found && candidate_load &&''')
    text = once(text, '''        wire pop_event=metadata_events[metadata_row*7+6] && head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==metadata_row;''',
                '''        // Compare against the predecessor constant before the late pop
        // event. Both cleared rows and the scalar head/count share one count.
        localparam integer PREVIOUS_ROW=(metadata_row+LSQ_ENTRIES-1)%LSQ_ENTRIES;
        wire pop_event=metadata_events[metadata_row*7+6] &&
            (head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==metadata_row ||
             (second_pop_views[metadata_row] &&
              head_query_views[metadata_row*SLOT_WIDTH +: SLOT_WIDTH]==PREVIOUS_ROW));''')
    text = once(text, '''            pop_count_calc = ((occupancy_reg != 0) && head_valid &&
                              ((head_load && head_complete &&
                                (head_reported ||
                                 (load_complete_valid_o && load_complete_ready_i &&
                                  (complete_slot_select == head_reg)))) ||
                               (head_store && head_ack && store_ack_ready_i))) ? 1 : 0;''',
                '''            pop_count_calc = metadata_pop_count;''')
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,',
                '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,\n    parameter integer LSQ_RECLAIM_WIDTH = 1,')
    text = once(text, '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .LOCAL_REPORT_CANCEL',
                '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .LOCAL_REPORT_CANCEL')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,',
                '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,\n    parameter integer LSQ_RECLAIM_WIDTH = 1,')
    text = once(text, '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS),',
                '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 1,',
                '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 1,\n    parameter integer LSQ_RECLAIM_WIDTH = 2,')
    text = once(text, '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS),',
                '.ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS), .LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),')
    changes[name] = text
    for name in parent['source_sha256']:
        target = TARGET / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, target)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
                  parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
                  changed_from_parent_files=list(changes),
                  source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
                  preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], LSQ_RECLAIM_WIDTH=2)
    record['enabled_profile'] = dict(parent['enabled_profile'], lsq_two_prefix_reclaim=True,
        second_reclaim_requires_prior_load_report=True, lsq_added_state_bits=0,
        store_ack_ports_unchanged=1, load_completion_ports_unchanged=1)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Reclaim original LSQ head plus the immediately following already-complete/already-reported load in one normal edge. Head/count and both row invalidations share one0/1/2 prefix count. Store ack/report protocols and request/forward/recovery/generation authority remain unchanged; add no state, capacity, ports, or pipeline edge.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a36_three_case_profile_sha256=sha(PROFILE),
        a36_towers_lsq_full_samples=750, a36_towers_active_samples=5804,
        a36_towers_average_lsq_occupancy=68109/5804,
        original_max_lsq_allocate_per_edge=2, original_max_lsq_reclaim_per_edge=1,
        new_max_lsq_reclaim_per_edge=2, new_lsq_reclaim_added_ff_bits=0,
        lsq_prefix_reclaim_ipc_and_mapped_area_and_timing_unmeasured=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_LSQ_TWO_PREFIX_RECLAIM_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        tests_started=False, adopted=False,
        source_arguments=[
            'A36 towers LSQ occupancy averages11.735/16 and is full750/5804 active samples. Trace-present/all-blocked2053 samples overlap other stalls; reclaim benefit is unmeasured and these counters are not additive removable cycles.',
            'The original head-pop predicate is exact parent source, including head completion current-handshake permission and head-only store acknowledgement. A second pop requires first pop, occupancy>=2, normal cycle, and the immediately next row valid/load/complete/load_reported from registered state.',
            'Second row must be a load whose completion was accepted on an earlier edge. No second completion report, store acknowledgement, speculative store write or early retirement is introduced. Already-reported load rows contain no outstanding cache-response authority.',
            'Every reclaimed row uses the original pop_event metadata clears; head advances and occupancy subtracts that same prefix count. Tail/allocation count remain original. Generation changes only on original allocation; late packets are still rejected using full LSQ/ROB tags.',
            'The predecessor-constant comparison handles wrap without a per-row head+1 carry chain. Both count2 with an exact two-entry queue and ordinary head wrap use original advance_slot semantics.',
            'Reset, global flush and selective recovery retain their original higher priority. Additional second pop is explicitly disabled on those edges. Pending preview remains a normal cycle with the original completed-load semantics.',
            'Allocation still uses registered free capacity and cannot write a newly freed full-queue row on the same edge. No new combinational cache/producer-ready-to-dispatch allocation-credit path is introduced.',
            'RECLAIM_WIDTH1 and LSQ_ENTRIES1 retain single-head behavior. Width2 needs only a four-bit next-row read, scalar prefix control, row constant comparisons, and priced control distribution; no storage, capacity or interface changes.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Meaningful later coverage needs first-store/second-load, two already-reported loads, blocked second load, consecutive stores, occupancy1/2/full, wrap, current head report handshake, backpressure/errors, recovery concurrent with completions, and stale response after reuse.'
        ])
    write(BASE / 'A41_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'added_ff_bits', 'tests_started')})


if __name__ == '__main__':
    main()
