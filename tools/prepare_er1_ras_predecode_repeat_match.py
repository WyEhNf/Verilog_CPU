"""Precompute compressed RAS address match before accepted-call selection."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A72_branch_capture_redirect_ready'
TARGET = BASE / 'A73_ras_predecode_repeat_match'
REVIEW = BASE / 'A73_source_review.json'
RUN = Path('F:/CPU2026CourseRuns/ER1_A69_tier3_20261006')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    critical = RUN / 'result/synth/opt/critical_paths.json'
    path = read(critical)['checks'][0]
    anchors = [node for node in path['source_path'] if
        'ras_return_address_selector.g_event' in node.get('net', '') and 'views_o' in node.get('net', '')]
    assert anchors and path['data_arrival_time'] > anchors[-1]['arrival']
    timing = read(RUN / 'result/timing_only.json')
    assert sha(RUN / 'result/synth/opt/report.json') == timing['official_report_sha256']
    changes = {}
    name = 'rtl/cpu_core.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RAS_REPEAT_COMPRESSION = 0,',
        '''    parameter integer RAS_REPEAT_COMPRESSION = 0,
    // Compare possible call return PCs before late accepted-call selection.
    parameter integer RAS_REPEAT_MATCH_PREDECODE = 0,''')
    text = once(text, '''        assign ras_repeat_push=ras_push && ras_count!=0 &&
            ras_target==ras_push_address && !(&top_repeats);''',
        '''        wire selected_repeat_match;
        if(RAS_REPEAT_MATCH_PREDECODE!=0) begin:g_predecoded_match
            wire [FE_WIDTH-1:0] lane_matches;
            if(FE_WIDTH<=4) begin:g_shared_pc_parts
                // +4..+16 changes only word bits and one carry into [31:4].
                // Reuse two early high comparisons for all supported lanes.
                wire [27:0] next_pc_high=response_base_pc[31:4]+28'd1;
                wire high_same=ras_target[31:4]==response_base_pc[31:4];
                wire high_next=ras_target[31:4]==next_pc_high;
                wire low_same=ras_target[1:0]==response_base_pc[1:0];
                for(genvar match_lane=0;match_lane<FE_WIDTH;match_lane=match_lane+1) begin:g_lane
                    wire [1:0] return_word=response_base_pc[3:2]+2'(match_lane+1);
                    wire carry_high;
                    if(match_lane==3) begin:g_full_line
                        assign carry_high=1'b1;
                    end else begin:g_partial_line
                        assign carry_high=response_base_pc[3:2]>=2'(3-match_lane);
                    end
                    assign lane_matches[match_lane]=low_same &&
                        ras_target[3:2]==return_word && (carry_high?high_next:high_same);
                end
            end else begin:g_general_pc_parts
                for(genvar match_lane=0;match_lane<FE_WIDTH;match_lane=match_lane+1) begin:g_lane
                    assign lane_matches[match_lane]=
                        ras_target==ras_return_addresses[match_lane*32 +: 32];
                end
            end
            // The original first-call rule makes ras_push_lanes one-hot.
            // Late predictor/response acceptance now selects one bit only.
            rv32_frequency_event_select #(.WIDTH(1),.EVENTS(FE_WIDTH),.PRIORITY(0)) match_select (
                .events_i(ras_push_lanes),.values_i(lane_matches),
                .write_o(),.value_o(selected_repeat_match));
        end else begin:g_selected_address_match
            assign selected_repeat_match=ras_target==ras_push_address;
        end
        assign ras_repeat_push=ras_push && ras_count!=0 &&
            selected_repeat_match && !(&top_repeats);''')
    # Preserve call/return prefix selection, address payload, physical stack,
    # count/SP and each repetition counter update exactly.
    start = '    // Consecutive lane PCs route to disjoint low-index predictor banks.'
    assert text[text.index(start):] == original[original.index(start):]
    for marker in [
        'assign ras_return_addresses[predictor_lane*32 +: 32]=response_base_pc+((predictor_lane+1)*32\'d4);',
        'if (!ras_event_found && (ras_word_index < 4))',
        'ras_event_found = 1;',
        'wire allocate=!reset && ras_push && !ras_repeat_push && ras_sp==repeat_row;',
        'wire increment=!reset && ras_repeat_push && ras_top_index==repeat_row;',
        'wire decrement=!reset && ras_repeat_pop && ras_top_index==repeat_row;',
        'assign ras_repeat_pop=ras_pop && top_repeats!=0;',
    ]:
        assert marker in text, marker
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer RAS_REPEAT_COMPRESSION = 1,',
        '    parameter integer RAS_REPEAT_COMPRESSION = 1,\n    parameter integer RAS_REPEAT_MATCH_PREDECODE = 1,')
    text = once(text, '.RAS_REPEAT_COMPRESSION(RAS_REPEAT_COMPRESSION),',
        '.RAS_REPEAT_COMPRESSION(RAS_REPEAT_COMPRESSION), .RAS_REPEAT_MATCH_PREDECODE(RAS_REPEAT_MATCH_PREDECODE),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_RAS_PREDECODE_REPEAT_MATCH_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], RAS_REPEAT_MATCH_PREDECODE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], ras_repeat_match_predecode=True,
        ras_repeat_match_new_ff_bits=0, ras_repeat_match_new_sram_bits=0,
        ras_repeat_match_shared_high_comparisons=2, ras_call_return_and_repeat_policy_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Precompute each possible call return-PC match to current RAS top before accepted-call selection. FE1/2/4 share comparisons for PC[31:4] and PC[31:4]+1, plus per-lane two-bit return word/carry. The original one-hot call grants select one Boolean equality result; keep the original selected return-PC payload and stack/repetition/count updates. Remove late32bit selected-PC to equality dependency without state or cycle changes.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        ras_repeat_late_payload_to_equality_dependency_removed=True,
        a69_ras_selector_anchor_arrival_ns=anchors[-1]['arrival']*1e9,
        a69_post_ras_selector_endpoint_interval_ns=(path['data_arrival_time']-anchors[-1]['arrival'])*1e9,
        ras_repeat_match_limit='Structural timing dependency removed, not a measured interval reduction. Earlier PC arithmetic/RAS top read and new compare fanout remain. Equality logic gates add area; exact mapped total area/Fmax remain unknown.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        measured_path_sha256=sha(critical), source_arguments=[
            'Original first-event loop sets at most one ras_push_lanes bit. A return or predicted-taken prior lane also closes the prefix. On ras_push, original selected payload equals the return PC of that sole lane; equality of selected payload to RAS top therefore equals selecting that lane\'s precomputed equality. No grant gives selected_repeat_match0, but ras_push0 masks it exactly.',
            'For lane L in0..3, add4*(L+1) to any32bit response base PC. Bits1:0 stay equal; return word is (base_word+L+1) modulo4. Carry into upper28bits is base_word>=3-L, and is always1 for L3. Upper result is base_high+carry modulo2^28. The split comparisons therefore equal the original32bit constant addition/equality, including odd low bits and 0xffffffff wrap. This reasoning does not assume aligned instruction PC.',
            'FE1/2/4 use exactly their original respective candidate addresses and common high comparisons. FE>4 retains full per-lane equality fallback; option0 retains selected-address equality. Compression0 still discards all comparison logic and uses original ordinary stack behavior. Count0/full repeat/overflow handling, reset and push-vs-pop priority stay byte exact.',
            'The original response acceptance, first call/return/taken selection, selected32bit return payload, 4-word stack, SP/count and all four repetition-counter owners are unchanged. The candidate changes only where equality is computed, with no additional FF/SRAM/pipeline edge and no new speculative RAS policy.',
            'A69 critical path includes late ras_return_address_selector event selection at3.578ns and endpoint at4.293ns. This source removes the wide selected payload to equality dependency; it does not prove that the entire0.715ns interval is saved. The new two high comparators, shared increment and fanout can change mapped area/timing; all actual metrics remain unmeasured.',
            'Manual source/Boolean/arithmetic/hash audit only; no HDL/formal/unit/simulation/synthesis/STA execution. Future coherent coverage: first call in each lane, earlier return/taken termination, multiple call flags, same/different top, physical count0/4, repeat0/full, push/pop, response stall/redirect, return word carry3/2/1/0, high overflow, FE1/2/4, option0 and compression0.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
