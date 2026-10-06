"""Factor frontend capacity and next-PC directly from accepted prefix lanes."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A48_lsq_registered_address_bypass'
TARGET = BASE / 'A49_frontend_parallel_bundle_control'
CRITICAL = Path('F:/CPU2026Proofs/ER1_A41_critical_frontend_owner_20261005.json')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A49_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    critical = read(CRITICAL)
    assert not critical['new_sta'] and not critical['new_cpu_tests']
    changes = {}
    name = 'rtl/frontend/rv32_fetch_frontend.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RESPONSE_LOCAL_PC = 0,',
        '    parameter integer RESPONSE_LOCAL_PC = 0,\n    parameter integer PARALLEL_BUNDLE_CONTROL = 0,')
    text = once(text, '    wire queue_space = (count_reg + bundle_count <= FQ_DEPTH);',
        '''    wire parallel_queue_space;
    wire queue_space = (PARALLEL_BUNDLE_CONTROL!=0) ? parallel_queue_space :
        (count_reg + bundle_count <= FQ_DEPTH);''')
    text = once(text, '            wire [1:0] predicted_views;\n', '')
    text = once(text, '            wire [31:0] sequential_pc=response_base_pc+((response_lane+1)*32\'d4);\n', '')
    text = once(text, '''            rv32_frequency_control_tree #(.LEAVES(2)) predicted_tree (
                .signal_i(if_resp_pred_taken_i[response_lane]),.views_o(predicted_views));
            for(response_half=0;response_half<2;response_half=response_half+1) begin:g_half
                assign next_pc_values[response_lane*32+response_half*16 +: 16]=predicted_views[response_half]?
                    if_resp_pred_target_i[response_lane*32+response_half*16 +: 16]:sequential_pc[response_half*16 +: 16];
            end
            assign next_pc_classes[response_lane]=bundle_count==response_lane+1;''',
        '''            if(PARALLEL_BUNDLE_CONTROL==0) begin:g_legacy_next_pc
                wire [1:0] predicted_views;
                wire [31:0] sequential_pc=response_base_pc+((response_lane+1)*32'd4);
                rv32_frequency_control_tree #(.LEAVES(2)) predicted_tree (
                    .signal_i(if_resp_pred_taken_i[response_lane]),.views_o(predicted_views));
                for(response_half=0;response_half<2;response_half=response_half+1) begin:g_half
                    assign next_pc_values[response_lane*32+response_half*16 +: 16]=predicted_views[response_half]?
                        if_resp_pred_target_i[response_lane*32+response_half*16 +: 16]:sequential_pc[response_half*16 +: 16];
                end
                assign next_pc_classes[response_lane]=bundle_count==response_lane+1;
            end else begin:g_parallel_next_pc_unused
                assign next_pc_values[response_lane*32 +: 32]=32'b0;
                assign next_pc_classes[response_lane]=1'b0;
            end''')
    text = once(text, '''    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FE_WIDTH+1),.PRIORITY(0)) next_pc_selector (
        .events_i({(bundle_count==0),next_pc_classes}),
        .values_i({default_next_pc,next_pc_values}),.write_o(),.value_o(next_pc_comb));''',
        '''    generate if(PARALLEL_BUNDLE_CONTROL!=0) begin:g_parallel_bundle_control
        rv32_frontend_parallel_bundle_control #(.FE_WIDTH(FE_WIDTH),.FQ_DEPTH(FQ_DEPTH),
            .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) control (
            .base_pc_i(response_base_pc),.words_i(response_words),
            .taken_i(if_resp_pred_taken_i),.targets_i(if_resp_pred_target_i),
            .queue_count_i(count_reg),.response_error_i(if_resp_error_i),
            .queue_space_o(parallel_queue_space),.next_pc_o(next_pc_comb));
    end else begin:g_legacy_bundle_control
        assign parallel_queue_space=1'b0;
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FE_WIDTH+1),.PRIORITY(0)) next_pc_selector (
            .events_i({(bundle_count==0),next_pc_classes}),
            .values_i({default_next_pc,next_pc_values}),.write_o(),.value_o(next_pc_comb));
    end endgenerate''')
    helper = '''

// Same accepted prefix as bundle_count, without count encoding/decoding on
// next-PC or response-capacity paths. No new state or acceptance boundary.
module rv32_frontend_parallel_bundle_control #(
    parameter integer FE_WIDTH=4,FQ_DEPTH=16,LEGACY_SENTINEL_HALT=0
) (
    input wire [31:0] base_pc_i,
    input wire [FE_WIDTH*32-1:0] words_i,targets_i,
    input wire [FE_WIDTH-1:0] taken_i,
    input wire signed [31:0] queue_count_i,
    input wire response_error_i,
    output wire queue_space_o,
    output wire [31:0] next_pc_o
);
    wire [FE_WIDTH-1:0] stops,lane_live,capacity_violation;
    wire [2*FE_WIDTH:0] events;
    wire [(2*FE_WIDTH+1)*32-1:0] values;
    genvar lane;
    generate for(lane=0;lane<FE_WIDTH;lane=lane+1) begin:g_lane
        wire [2:0] word_number={1'b0,base_pc_i[3:2]}+3'(lane);
        wire prior_prefix_live;
        assign stops[lane]=taken_i[lane] || ((LEGACY_SENTINEL_HALT!=0) &&
            words_i[lane*32 +: 32]==32'h0ff00513);
        if(lane==0) begin:g_first
            assign prior_prefix_live=1'b1;
        end else begin:g_later
            assign prior_prefix_live=!(|stops[lane-1:0]);
        end
        assign lane_live[lane]=!response_error_i && prior_prefix_live && word_number<3'd4;
        wire ends_bundle=lane_live[lane] &&
            (stops[lane] || (lane==FE_WIDTH-1) || word_number==3'd3);
        // An error has no bundle. Otherwise exactly one live lane ends it.
        // Target/sequential events are disjoint and directly select data.
        assign events[2*lane]=ends_bundle && taken_i[lane];
        assign events[2*lane+1]=ends_bundle && !taken_i[lane];
        assign values[2*lane*32 +: 32]=targets_i[lane*32 +: 32];
        assign values[(2*lane+1)*32 +: 32]=base_pc_i+((lane+1)*32'd4);
        // Every live lane must fit. Parallel constant comparisons avoid the
        // bundle_count + occupancy adder, and preserve no dequeue credit.
        assign capacity_violation[lane]=lane_live[lane] &&
            queue_count_i>(FQ_DEPTH-(lane+1));
    end endgenerate
    assign events[2*FE_WIDTH]=response_error_i;
    assign values[2*FE_WIDTH*32 +: 32]=base_pc_i+32'd4;
    assign queue_space_o=(queue_count_i<=FQ_DEPTH) && !(|capacity_violation);
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2*FE_WIDTH+1),.PRIORITY(0)) next_pc_selector (
        .events_i(events),.values_i(values),.write_o(),.value_o(next_pc_o));
endmodule
'''
    # All original request/response owners, bundle/enqueue/dequeue construction,
    # payload writers, reset/redirect and queue state bodies remain source exact.
    marker = '    assign current_epoch_o = epoch_reg;'
    assert text[text.index(marker):] == original[original.index(marker):]
    text += helper
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 0,',
        '    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 0,\n    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 0,')
    text = once(text, '        .RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC &&',
        '        .PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL),\n        .RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC &&')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 1,',
        '    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 1,\n    parameter integer FRONTEND_PARALLEL_BUNDLE_CONTROL = 1,')
    text = once(text, '.FRONTEND_RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC),',
        '.FRONTEND_RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC), .FRONTEND_PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL),')
    changes[name] = text
    for name in parent['source_sha256']:
        dst = TARGET / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dst)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], FRONTEND_PARALLEL_BUNDLE_CONTROL=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], frontend_parallel_bundle_control=True,
        frontend_next_pc_avoids_bundle_count_decode=True, frontend_capacity_avoids_bundle_count_add=True,
        frontend_parallel_bundle_added_ff_bits=0, frontend_parallel_bundle_added_sram_bits=0,
        frontend_parallel_bundle_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Factor next-PC and response capacity directly from the same valid instruction prefix: parallel stop reductions, exactly one terminal lane, disjoint target/sequential events and constant occupancy comparisons. Preserve original bundle/enqueue/dequeue/queue state and all handshake/redirect ownership; no new fetch edge or storage.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a41_frozen_frontend_critical_proof_sha256=sha(CRITICAL),
        frontend_parallel_bundle_control_gain_and_mapped_cost_unknown=True,
        removed_serial_bundle_count_encode_decode_on_next_pc=True,
        removed_bundle_count_plus_occupancy_adder_on_response_capacity=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_FRONTEND_PARALLEL_BUNDLE_CONTROL_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For legal FE1/2/4 and base word0..3, lane_live is the original error-free contiguous prefix ending at the first taken/sentinel instruction or the available line/FE boundary. Prefixes use parallel reductions of earlier stops rather than the serial freeze/count loop. The original bundle_count body remains unchanged for enqueue and occupancy.',
            'Exactly one live lane ends a non-error bundle: its taken direction selects its original full target, otherwise its original PC+(lane+1)*4. The default PC+4 event exists only for response error, when the original bundle_count is0. Sentinel and taken on the same lane follow the old target precedence; sentinel-only selects sequential PC. No raw predictor/target/RAS or metadata behavior changes.',
            'Within the original reachable0..FQ_DEPTH occupancy range, all live lanes fitting is equivalent to count+bundle_count<=FQ_DEPTH. Each lane compares count against a constant depth-(lane+1); overflow of a live prefix lane denies the whole response. The explicit count<=depth guard also denies an overfull queue on an error response. Same-edge dequeue credit is not introduced.',
            'For parameter0 the original next-PC mux, bundle_count decode and queue-space adder elaborate unchanged. For parameter1 their per-lane retained inversion trees are not instantiated, avoiding electrically kept dead logic. Standalone/core defaults0; course top1. No sequential block/state declaration or payload writer changes.',
            'A41 mapped evidence places the measured longest path in the frontend PC/BHT/chained-request region at3.19ns arrival. This rewrite targets that region; the attribution does not prove the exact new logic was the old critical-cell owner or quantify a frequency gain. A48 predictor additions and LSQ/recovery paths remain unmeasured.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Later meaningful coverage includes FE1/2/4, all line-start words, first/middle/final taken and sentinel, simultaneous sentinel/taken, response error, full/near-full capacity boundaries, queue bypass and sustained backpressure, chained request stalls, redirect/epoch mismatch and legacy-mode fallback.'
        ])
    write(BASE / 'A49_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
