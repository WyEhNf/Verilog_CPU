"""Expose parallel first-event RAS control; keep exact original prefix policy."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A73_ras_predecode_repeat_match'
TARGET = BASE / 'A74_ras_parallel_control'
REVIEW = BASE / 'A74_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/cpu_core.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer FRONTEND_RAS_PREDECODE = 0,',
        '''    parameter integer FRONTEND_RAS_PREDECODE = 0,
    parameter integer FRONTEND_RAS_PARALLEL_CONTROL = 0,''')
    start = "    always @* begin\n        ras_push = 1'b0;"
    tail = '    // The first accepted call wins; return/taken events close the'
    begin = text.index(start)
    end = text.index(tail, begin)
    legacy = text[begin:end]
    assert text.count(start) == 1 and legacy.count('always @*') == 1
    prefix = '''    generate if(FRONTEND_RAS_PARALLEL_CONTROL!=0) begin:g_parallel_ras_events
        wire [FE_WIDTH-1:0] response_accept_views;
        wire [FE_WIDTH-1:0] ras_events,ras_first_events,ras_call_grants,ras_return_grants;
        rv32_frequency_control_tree #(.LEAVES(FE_WIDTH)) response_accept_tree (
            .signal_i((ENABLE_PREDICTOR!=0) && if_resp_valid && if_resp_ready),
            .views_o(response_accept_views));
        for(genvar event_lane=0;event_lane<FE_WIDTH;event_lane=event_lane+1) begin:g_lane
            wire within_line;
            if(event_lane<4) begin:g_present
                // W+L<4 is W<=3-L, with a constant per-lane bound.
                assign within_line=response_base_pc[3:2]<=2'(3-event_lane);
            end else begin:g_outside_line
                assign within_line=1'b0;
            end
            assign ras_events[event_lane]=within_line &&
                (ras_query_flags[event_lane*2+1] || ras_query_flags[event_lane*2] || pred_taken_bus[event_lane]);
            if(event_lane==0) begin:g_first
                assign ras_first_events[event_lane]=ras_events[event_lane];
            end else begin:g_later
                assign ras_first_events[event_lane]=ras_events[event_lane] && !(|ras_events[event_lane-1:0]);
            end
            // Response acceptance is only a final local qualifier. A call
            // wins over a return flag exactly as the original if/else loop.
            assign ras_call_grants[event_lane]=response_accept_views[event_lane] &&
                ras_first_events[event_lane] && ras_query_flags[event_lane*2+1];
            assign ras_return_grants[event_lane]=response_accept_views[event_lane] &&
                ras_first_events[event_lane] && !ras_query_flags[event_lane*2+1] && ras_query_flags[event_lane*2];
        end
        always @* begin
            ras_push_lanes=ras_call_grants;
            ras_push=|ras_call_grants;
            ras_pop=(|ras_return_grants) && ras_count!=0;
        end
    end else begin:g_original_ras_events
'''
    text = text[:begin] + prefix + legacy + '    end endgenerate\n\n' + text[end:]
    assert legacy in text
    assert text[text.index(tail):] == original[original.index(tail):]
    for marker in [
        '.events_i(ras_push_lanes),.values_i(ras_return_addresses),.write_o(),.value_o(ras_push_address)',
        'wire write_event=!reset && ras_push && !ras_repeat_push && ras_sp==ras_row;',
        'else if(ras_push && !ras_repeat_push)',
        'else if(ras_pop && !ras_repeat_pop)',
    ]:
        assert marker in text, marker
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RAS_PREDECODE = 2,',
        '    parameter integer FRONTEND_RAS_PREDECODE = 2,\n    parameter integer FRONTEND_RAS_PARALLEL_CONTROL = 1,')
    text = once(text, '.FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE),',
        '.FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE), .FRONTEND_RAS_PARALLEL_CONTROL(FRONTEND_RAS_PARALLEL_CONTROL),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_RAS_PARALLEL_FIRST_EVENT_CONTROL_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], FRONTEND_RAS_PARALLEL_CONTROL=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], ras_parallel_first_event_control=True,
        ras_parallel_control_new_ff_bits=0, ras_parallel_control_new_sram_bits=0,
        ras_first_call_return_taken_policy_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Replace the accepted-response RAS scan with per-lane constant word bounds, parallel call/return/taken event predicates and independent first-event prefix masks. Keep response acceptance as the final local qualifier; route call grants and return Boolean directly. The original first-event/call-over-return/count-zero policy and payload/count/repetition owners are unchanged, with a byte-exact legacy fallback.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        ras_control_start_plus_lane_integer_dependency_removed=True,
        ras_acceptance_to_first_event_dependency_removed=True,
        ras_control_limit='Shorter explicit control structure, not a measured gain. Earlier conditional direction decisions remain necessary to preserve accepted-prefix semantics. Mapped timing/area and actual IPC remain unknown.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        original_fallback_block_sha256=hashlib.sha256(legacy.encode('utf-8')).hexdigest(),
        tests_started=False, adopted=False, new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        source_arguments=[
            'Let legal[L]=(word_start+L<4) and event[L]=legal[L] && (call[L] || return[L] || predicted_taken[L]). Original ras_event_found remains0 until the first such event and then suppresses all later lanes. Explicit first[L]=event[L] && !OR(event[0..L-1]) is the same first-event set, including earlier return at count0 and taken instructions that do not push/pop.',
            'Original accepts the RAS event only when ENABLE_PREDICTOR && if_resp_valid && if_resp_ready. This common predicate does not change which lane is first; it is factored into each final grant. Push[L]=accept && first[L] && call[L]. Pop=accept && count!=0 && OR(first[L] && !call[L] && return[L]). The !call term retains exact call-over-return priority even if both input flags are set.',
            'For unsigned two-bit word_start W and lane L0..3, W+L<4 is exactly W<=3-L. Higher lane indexes cannot fit in a four-word line and are constant false. No word-start addition/encoded event index is needed on the control path. FE1/2/4 maintain the original set of possible accepted events.',
            'New ras_push_lanes stays one-hot. Original selected return-PC payload, RAS word write, SP/count, compression match, repeat counts, overflow/new-word allocation, return target override and every frontend/predictor response/redirect rule remain byte exact. Source introduces no FF/SRAM/ordinary or recovery edge. Default flag0 elaborates the preserved original procedural block.',
            'This source removes acceptance as an input to the priority chain and removes per-lane integer bound arithmetic. It does not discard earlier predicted-taken dependencies: those are required to prevent a later call/return beyond the accepted prefix. Extra prefix reductions/electrical control leaves change mapped cost; frequency/area/IPC remain unmeasured.',
            'Manual Boolean/source/hash review only; no HDL/formal/unit/simulation/synthesis/STA execution. Future coherent coverage: every word_start/lane combination, earlier call/return/taken masks, both call+return flags, response-valid/ready/predictor disabled, count0/4, repeated/saturated calls and returns, redirect suppression, FE1/2/4 and option0.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
