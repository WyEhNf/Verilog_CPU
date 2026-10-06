"""Specialize redirect capture ready to its exact existing contract."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A71_lsq_second_report_reclaim'
TARGET = BASE / 'A72_branch_capture_redirect_ready'
REVIEW = BASE / 'A72_source_review.json'
RUN = Path('F:/CPU2026CourseRuns/ER1_A69_tier3_20261006')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    timing = read(RUN / 'result/timing_only.json')
    plan = read(RUN / 'measurement_plan.json')
    assert timing['source_manifest_sha256'] == plan['source_manifest_sha256']
    assert timing['config_sha256'] == plan['config_sha256']
    report = RUN / 'result/synth/opt/report.json'
    assert sha(report) == timing['official_report_sha256']
    critical = RUN / 'result/synth/opt/critical_paths.json'
    paths = read(critical)['checks']
    assert len(paths) == 5
    main_path = paths[0]
    nets = [node.get('net', '') for node in main_path['source_path']]
    for marker in ['branch_capture_owner.data_o', 'out_cancel_guard',
                   'completion.g_direct_payload', 'g_producer_live_read[2]',
                   'response_read.g_event', 'bank_training_index', 'ras_return_address_selector']:
        assert any(marker in net for net in nets), marker
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer EARLY_FRONT_REDIRECT = 0,',
        '''    parameter integer EARLY_FRONT_REDIRECT = 0,
    // Capture knows valid+redirect+!pending. Use the exact corresponding
    // redirect-ready priority, independently of ordinary completion ready.
    parameter integer BRANCH_CAPTURE_REDIRECT_READY = 0,''')
    old = '''    genvar capture_lane;
    generate for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_branch_capture
        assign branch_capture_match[capture_lane]=!reset_i && !flush_i && !branch_pending &&
            alu_exec_valid[capture_lane] && alu_exec_ready[capture_lane] &&
            branch_training_live[capture_lane] && alu_exec_redirect_valid[capture_lane];'''
    new = '''    wire [BE_WIDTH-1:0] capture_redirect_claim=
        alu_exec_valid & alu_exec_redirect_valid & ~alu_exec_is_load;
    wire [BE_WIDTH-1:0] capture_redirect_ready;
    genvar capture_lane;
    generate for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_branch_capture
        // Under valid+redirect+!pending, the original ready loop selects
        // loads unconditionally; otherwise only earlier valid non-load
        // redirects can block this lane. Their GEN validity does not change
        // that original priority. Ordinary producer_ready cannot affect it.
        if(capture_lane==0) begin:g_first_ready
            assign capture_redirect_ready[capture_lane]=1'b1;
        end else begin:g_later_ready
            assign capture_redirect_ready[capture_lane]=alu_exec_is_load[capture_lane] ||
                !(|capture_redirect_claim[capture_lane-1:0]);
        end
        assign branch_capture_match[capture_lane]=!reset_i && !flush_i && !branch_pending &&
            alu_exec_valid[capture_lane] &&
            ((BRANCH_CAPTURE_REDIRECT_READY!=0)?capture_redirect_ready[capture_lane]:alu_exec_ready[capture_lane]) &&
            branch_training_live[capture_lane] && alu_exec_redirect_valid[capture_lane];'''
    text = once(text, old, new)
    # Keep source acceptance and every full lifetime/cancel guard untouched.
    ready_start = '    always @* begin\n        alu_exec_ready_r = {BE_WIDTH{1\'b0}};'
    ready_end = '    assign alu_exec_ready = alu_exec_ready_r;'
    assert text[text.index(ready_start):text.index(ready_end)+len(ready_end)] == original[
        original.index(ready_start):original.index(ready_end)+len(ready_end)]
    for marker in [
        'alu_exec_tag[training_lane*TAG_WIDTH] &&',
        'producer_live_reads[training_lane*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&',
        '(alu_exec_tag[training_lane*TAG_WIDTH+3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==',
        'branch_capture_grant[capture_lane]=branch_capture_match[capture_lane] &&',
        '!(|branch_capture_match[capture_lane-1:0]);',
        'assign redirect_valid_o=branch_capture_write;',
        '.clk_i(clk_i),.write_i(branch_capture_write),.data_i(branch_capture_next),.data_o(branch_capture_saved)',
    ]:
        assert marker in text, marker
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        text = (PARENT / name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer EARLY_FRONT_REDIRECT = {default},',
            f'    parameter integer EARLY_FRONT_REDIRECT = {default},\n    parameter integer BRANCH_CAPTURE_REDIRECT_READY = {default},')
        text = once(text, '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT),',
            '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT), .BRANCH_CAPTURE_REDIRECT_READY(BRANCH_CAPTURE_REDIRECT_READY),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_EXACT_BRANCH_CAPTURE_REDIRECT_READY_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], BRANCH_CAPTURE_REDIRECT_READY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], branch_capture_exact_redirect_ready=True,
        branch_capture_completion_ready_dependency_removed=True,
        branch_capture_ready_new_ff_bits=0, branch_capture_ready_new_sram_bits=0,
        branch_capture_ready_cycle_and_selection_policy_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Under the capture predicate valid+redirect+!branch_pending, specialize ALU ready to its exact original rule: loads are ready; a non-load redirect is ready iff no earlier valid non-load redirect claimed the sole pending slot. Keep the original ALU ready/consumption loop and full capture lifetime guards unchanged. Remove ordinary MDU/LSQ/completion-network ready as a structural capture input without changing selected branches or cycles.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a69_measured_fmax_mhz=timing['fmax_mhz'], a69_measured_total_area_um2=timing['area_um2'],
        a69_longest_data_arrival_ns=main_path['data_arrival_time']*1e9,
        a69_critical_paths_sha256=sha(critical), branch_capture_ready_manual_boolean_specialization=True,
        branch_capture_ready_limit='Removes the observed completion-ready detour structurally; remaining own-ALU recovery/full GEN, redirect/epoch/ICache and frontend prediction paths still need STA. No claim that Fmax is restored above300MHz.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        measured_a69_timing=dict(run=str(RUN), source_manifest_sha256=timing['source_manifest_sha256'],
            timing_only_sha256=sha(RUN / 'result/timing_only.json'), ppa_sha256=sha(report),
            critical_paths_sha256=sha(critical), fmax_mhz=timing['fmax_mhz'], area_um2=timing['area_um2'],
            worst_data_arrival_ns=main_path['data_arrival_time']*1e9,
            actual_ipc_not_in_this_timing_artifact=True),
        source_arguments=[
            'Original ALU ready loop: empty lanes are ready; valid loads are ready; valid non-load redirects are ready iff branch_pending=0 and no earlier valid non-load redirect set redirect_ready_found; valid ordinary non-load non-redirects use producer_ready. Only the third case can set redirect_ready_found.',
            'Capture match already requires !branch_pending, own valid and own redirect. Therefore own empty and ordinary cases cannot contribute. In this domain own load implies ready1; otherwise ready equals no earlier(valid && !is_load && redirect). Earlier stale GEN redirects still reserve the original ready priority and are deliberately included in capture_redirect_claim. This preserves even arbitrary load+redirect input tuples.',
            'The substituted ready changes no accepted branch for any input tuple: it equals the original ready whenever the remaining capture predicate is true. When that predicate is false both old/new match are false. Existing lowest matching-lane grant, complete capture values, packet enable, history checkpoint/repair and frontend redirect/epoch owners remain byte exact. No new branch may be consumed while pending.',
            'Original ALU ready loop, ordinary completion producer valid/ready, pending branch completion and MDU/LSQ owners are unchanged. Redirecting ALU results were already excluded from ordinary completion enqueue and used an independent pending-slot ready. This candidate exposes that existing contract to capture instead of altering readiness or creating a new result-retention protocol.',
            'All valid-bit/current-slot/full8GEN and existing ALU flush/cancel checks in branch_training_live and raw ALU valid remain. No false-path constraints or weaker lifetime guards are introduced. Existing non-redirect feedback still obeys its original completion acceptance. The removed input dependency is specifically general producer_ready under a predicate where the original value cannot depend on it.',
            'Observed A69 worst path travels from pending recovery tag through MDU cancellation and completion producer-live/ready, into redirect-dependent ICache response, predictor query index and RAS output. Structural specialization removes completion-ready as a capture input. Remaining recovery/own-ALU cancellation and frontend paths can remain slow; actual mapped Fmax/area and all functional equivalence are unverified until a later reported coherent batch.',
            'Manual Boolean/source/hash review only, no HDL/unit/formal/simulation/synthesis/STA job started. Future coverage: valid/stale-tag redirects in both lanes, prior empty/load/ordinary/stale redirect, simultaneous redirects, held branch under pending, producer_ready0/1, completion backpressure with MDU/LSQ, reset/flush, wrap/recovery, width1/2/4 and option0 fallback.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
